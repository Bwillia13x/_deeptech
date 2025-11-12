"""
Automated backup scheduler for Signal Harvester.

This module provides scheduled backup functionality using APScheduler.
Supports daily, weekly, and monthly backup schedules with automatic
cloud upload and retention policy enforcement.
"""

from __future__ import annotations

import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .backup import BackupManager, BackupType, CompressionType, RetentionPolicy
from .config import get_config
from .logger import get_logger

log = get_logger(__name__)


class BackupScheduler:
    """
    Automated backup scheduler.
    
    Schedules and executes backups according to configured schedule.
    Handles daily, weekly, and monthly backups with automatic uploads
    and retention policy enforcement.
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize backup scheduler.
        
        Args:
            config_path: Path to configuration file
        """
        self.config = get_config(config_path)
        self.backup_config = self.config.app.backup
        
        if not self.backup_config.enabled:
            log.warning("Backup is disabled in configuration")
            raise RuntimeError("Backup is disabled in configuration")
        
        self.manager = BackupManager(
            db_path=self.config.app.database_path,
            backup_dir=self.backup_config.backup_dir,
            compression=CompressionType(self.backup_config.compression),
            retention_days=self.backup_config.retention_days,
        )
        
        self.scheduler = BlockingScheduler()
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, signum: int, frame: any) -> None:
        """Handle shutdown signals gracefully."""
        log.info(f"Received signal {signum}, shutting down...")
        self.stop()
        sys.exit(0)

    def _create_backup(
        self,
        backup_type: BackupType,
        retention_policy: RetentionPolicy,
    ) -> None:
        """
        Create a backup with automatic upload and verification.
        
        Args:
            backup_type: Type of backup to create
            retention_policy: Retention policy for the backup
        """
        try:
            log.info(f"Starting {backup_type.value} backup ({retention_policy.value} retention)")
            
            # Create backup
            backup_metadata = self.manager.create_backup(
                backup_type=backup_type,
                compression=CompressionType(self.backup_config.compression),
                retention_policy=retention_policy,
            )
            
            size_mb = backup_metadata.size_bytes / 1024 / 1024
            log.info(f"Backup created: {backup_metadata.backup_id} ({size_mb:.2f} MB)")
            
            # Verify if enabled
            if self.backup_config.verification.verify_after_backup:
                log.info("Verifying backup...")
                if self.manager.verify_backup(backup_metadata):
                    log.info("Backup verified successfully")
                else:
                    log.error("Backup verification failed")
                    return
            
            # Upload to cloud if enabled
            if self.backup_config.s3.enabled and self.backup_config.s3.upload_after_backup:
                log.info(f"Uploading to S3 bucket '{self.backup_config.s3.bucket}'...")
                success = self.manager.upload_to_s3(
                    backup_metadata,
                    bucket=self.backup_config.s3.bucket,
                    prefix=self.backup_config.s3.prefix,
                    region=self.backup_config.s3.region,
                )
                if success:
                    log.info(f"Uploaded to {backup_metadata.cloud_url}")
                else:
                    log.error("Upload failed")
            
            log.info(f"Backup completed: {backup_metadata.backup_id}")
        
        except Exception as e:
            log.exception(f"Backup failed: {e}")

    def daily_backup(self) -> None:
        """Execute daily backup."""
        self._create_backup(BackupType.FULL, RetentionPolicy.DAILY)

    def weekly_backup(self) -> None:
        """Execute weekly backup."""
        self._create_backup(BackupType.FULL, RetentionPolicy.WEEKLY)

    def monthly_backup(self) -> None:
        """Execute monthly backup."""
        self._create_backup(BackupType.FULL, RetentionPolicy.MONTHLY)

    def enforce_retention(self) -> None:
        """Enforce retention policy and clean up old backups."""
        try:
            log.info("Enforcing retention policy...")
            deleted = self.manager.enforce_retention_policy(
                daily_keep=self.backup_config.retention.daily_keep,
                weekly_keep=self.backup_config.retention.weekly_keep,
                monthly_keep=self.backup_config.retention.monthly_keep,
                dry_run=False,
            )
            if deleted:
                log.info(f"Deleted {len(deleted)} old backup(s): {', '.join(deleted)}")
            else:
                log.info("No backups to prune")
        except Exception as e:
            log.exception(f"Retention enforcement failed: {e}")

    def add_jobs(self) -> None:
        """Add scheduled jobs to the scheduler."""
        schedule = self.backup_config.schedule
        
        # Daily backup
        if schedule.daily_enabled:
            hour, minute = schedule.daily_time.split(":")
            trigger = CronTrigger(hour=hour, minute=minute)
            self.scheduler.add_job(
                self.daily_backup,
                trigger=trigger,
                id="daily_backup",
                name="Daily Backup",
                replace_existing=True,
            )
            log.info(f"Scheduled daily backup at {schedule.daily_time} UTC")
        
        # Weekly backup
        if schedule.weekly_enabled:
            hour, minute = schedule.weekly_time.split(":")
            # Convert day name to APScheduler format (mon, tue, wed, etc.)
            day_of_week = schedule.weekly_day.lower()[:3]
            trigger = CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute)
            self.scheduler.add_job(
                self.weekly_backup,
                trigger=trigger,
                id="weekly_backup",
                name="Weekly Backup",
                replace_existing=True,
            )
            log.info(f"Scheduled weekly backup on {schedule.weekly_day} at {schedule.weekly_time} UTC")
        
        # Monthly backup
        if schedule.monthly_enabled:
            hour, minute = schedule.monthly_time.split(":")
            trigger = CronTrigger(day=schedule.monthly_day, hour=hour, minute=minute)
            self.scheduler.add_job(
                self.monthly_backup,
                trigger=trigger,
                id="monthly_backup",
                name="Monthly Backup",
                replace_existing=True,
            )
            log.info(f"Scheduled monthly backup on day {schedule.monthly_day} at {schedule.monthly_time} UTC")
        
        # Daily retention enforcement (run at 5am UTC)
        self.scheduler.add_job(
            self.enforce_retention,
            trigger=CronTrigger(hour=5, minute=0),
            id="retention_enforcement",
            name="Retention Enforcement",
            replace_existing=True,
        )
        log.info("Scheduled daily retention enforcement at 05:00 UTC")

    def start(self) -> None:
        """Start the backup scheduler."""
        log.info("Starting backup scheduler...")
        
        # Add jobs
        self.add_jobs()
        
        # Print scheduled jobs
        log.info(f"Scheduler started with {len(self.scheduler.get_jobs())} job(s)")
        for job in self.scheduler.get_jobs():
            log.info(f"  - {job.name}: {job.trigger}")
        
        # Start scheduler (blocking)
        try:
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            log.info("Scheduler stopped")

    def stop(self) -> None:
        """Stop the backup scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            log.info("Scheduler stopped")


def run_scheduler(config_path: Optional[Path] = None) -> None:
    """
    Run the backup scheduler.
    
    Args:
        config_path: Path to configuration file
    """
    try:
        scheduler = BackupScheduler(config_path=config_path)
        scheduler.start()
    except Exception as e:
        log.exception(f"Scheduler failed to start: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_scheduler()
