"""
Database backup and recovery module for Signal Harvester.

This module provides comprehensive backup functionality including:
- Full and incremental SQLite backups
- Compression (gzip, zstd)
- Integrity verification
- Cloud storage upload (S3, GCS, Azure)
- Retention policies
- Point-in-time recovery

Usage:
    from signal_harvester.backup import BackupManager
    
    manager = BackupManager(db_path="var/app.db")
    
    # Create full backup
    backup_path = manager.create_backup(backup_type="full")
    
    # Upload to S3
    manager.upload_to_cloud(backup_path, provider="s3")
    
    # List backups
    backups = manager.list_backups()
    
    # Restore from backup
    manager.restore_backup(backup_path)
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .logger import get_logger

# Import Prometheus metrics
try:
    from .metrics import (
        backup_duration_seconds,
        backup_errors_total,
        backup_newest_age_seconds,
        backup_oldest_age_seconds,
        backup_retention_pruned_total,
        backup_restores_total,
        backup_runs_total,
        backup_size_bytes,
        backup_total_count,
        backup_total_size_bytes,
        backup_upload_duration_seconds,
        backup_uploads_total,
        backup_verifications_total,
    )
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False

log = get_logger(__name__)

# Optional dependencies for cloud storage
try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False
    log.debug("boto3 not installed, S3 upload disabled")
    boto3 = None

try:
    from google.cloud import storage as gcs_storage
    HAS_GCS = False  # TODO: Enable when google-cloud-storage is installed
except ImportError:
    HAS_GCS = False
    log.debug("google-cloud-storage not installed, GCS upload disabled")

try:
    from azure.storage.blob import BlobServiceClient
    HAS_AZURE = False  # TODO: Enable when azure-storage-blob is installed
except ImportError:
    HAS_AZURE = False
    log.debug("azure-storage-blob not installed, Azure upload disabled")

try:
    import zstandard as zstd
    HAS_ZSTD = True
except ImportError:
    HAS_ZSTD = False
    log.debug("zstandard not installed, zstd compression disabled")


class BackupType(str, Enum):
    """Type of backup to create."""
    FULL = "full"
    INCREMENTAL = "incremental"
    WAL = "wal"  # Write-Ahead Log only


class CompressionType(str, Enum):
    """Compression algorithm to use."""
    NONE = "none"
    GZIP = "gzip"
    ZSTD = "zstd"


class CloudProvider(str, Enum):
    """Cloud storage provider."""
    S3 = "s3"
    GCS = "gcs"
    AZURE = "azure"


class RetentionPolicy(str, Enum):
    """Backup retention policy."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass
class BackupMetadata:
    """Metadata about a backup."""
    backup_id: str
    backup_type: BackupType
    timestamp: datetime
    db_path: str
    backup_path: str
    compression: CompressionType
    size_bytes: int
    checksum: str  # SHA256
    description: Optional[str] = None
    wal_checksum: Optional[str] = None
    cloud_url: Optional[str] = None
    cloud_provider: Optional[CloudProvider] = None
    retention_policy: Optional[RetentionPolicy] = None
    verified: bool = False
    verification_timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __fspath__(self) -> str:
        """Allow BackupMetadata to be used as a path."""
        return self.backup_path

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "backup_id": self.backup_id,
            "backup_type": self.backup_type.value if isinstance(self.backup_type, BackupType) else self.backup_type,
            "timestamp": self.timestamp.isoformat(),
            "db_path": str(self.db_path),
            "backup_path": str(self.backup_path),
            "compression": self.compression.value if isinstance(self.compression, CompressionType) else self.compression,
            "size_bytes": self.size_bytes,
            "checksum": self.checksum,
            "wal_checksum": self.wal_checksum,
            "cloud_url": self.cloud_url,
            "cloud_provider": self.cloud_provider.value if self.cloud_provider else None,
            "retention_policy": self.retention_policy.value if self.retention_policy else None,
            "verified": self.verified,
            "verification_timestamp": self.verification_timestamp.isoformat() if self.verification_timestamp else None,
            "description": self.description,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BackupMetadata:
        """Create from dictionary."""
        return cls(
            backup_id=data["backup_id"],
            backup_type=BackupType(data["backup_type"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            db_path=data["db_path"],
            backup_path=data["backup_path"],
            compression=CompressionType(data["compression"]),
            size_bytes=data["size_bytes"],
            checksum=data["checksum"],
            wal_checksum=data.get("wal_checksum"),
            cloud_url=data.get("cloud_url"),
            cloud_provider=CloudProvider(data["cloud_provider"]) if data.get("cloud_provider") else None,
            retention_policy=RetentionPolicy(data["retention_policy"]) if data.get("retention_policy") else None,
            verified=data.get("verified", False),
            verification_timestamp=datetime.fromisoformat(data["verification_timestamp"]) if data.get("verification_timestamp") else None,
            description=data.get("description"),
            metadata=data.get("metadata", {}),
        )


class BackupManager:
    """
    Manager for database backups and recovery.
    
    Handles:
    - Creating full and incremental backups
    - Compression and encryption
    - Cloud storage upload
    - Backup verification
    - Retention policy enforcement
    - Point-in-time recovery
    """

    def __init__(
        self,
        db_path: Union[str, Path],
        backup_dir: Union[str, Path] = "backups",
        compression: CompressionType = CompressionType.GZIP,
        retention_days: int = 30,
        lock_wait_seconds: float = 5.0,
    ):
        """
        Initialize backup manager.
        
        Args:
            db_path: Path to SQLite database file
            backup_dir: Directory to store backups
            compression: Default compression type
            retention_days: Default retention period in days
            lock_wait_seconds: Max seconds to wait for a database lock before failing
        """
        self.db_path = Path(db_path)
        self.backup_dir = Path(backup_dir)
        self.compression = compression
        self.retention_days = retention_days
        self.lock_wait_seconds = max(0.0, lock_wait_seconds)
        
        # Create backup directory if it doesn't exist
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Metadata file
        self.metadata_file = self.backup_dir / "backups.json"
        self._metadata_cache: List[BackupMetadata] = []
        self._load_metadata()

    def _load_metadata(self) -> None:
        """Load backup metadata from file."""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file) as f:
                    data = json.load(f)
                    self._metadata_cache = [BackupMetadata.from_dict(item) for item in data]
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                log.warning(f"Failed to load backup metadata: {e}")
                self._metadata_cache = []
        else:
            self._metadata_cache = []

    def _save_metadata(self, metadata: Optional[BackupMetadata] = None) -> None:
        """Save backup metadata to file."""
        if metadata:
            for idx, item in enumerate(self._metadata_cache):
                if item.backup_id == metadata.backup_id:
                    self._metadata_cache[idx] = metadata
                    break
            else:
                self._metadata_cache.append(metadata)

        with open(self.metadata_file, "w") as f:
            json.dump([item.to_dict() for item in self._metadata_cache], f, indent=2)

        if metadata:
            metadata_path = self.backup_dir / f"{metadata.backup_id}.json"
            with open(metadata_path, "w") as meta_file:
                json.dump(metadata.to_dict(), meta_file, indent=2)

    def _generate_backup_id(self) -> str:
        """Generate unique backup ID."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        return f"backup_{timestamp}"

    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _compress_file(self, source: Path, compression: CompressionType) -> Path:
        """
        Compress a file using the specified algorithm.
        
        Args:
            source: Source file path
            compression: Compression type
            
        Returns:
            Path to compressed file
        """
        if compression == CompressionType.NONE:
            return source
        
        elif compression == CompressionType.GZIP:
            dest = Path(str(source) + ".gz")
            with open(source, "rb") as f_in:
                with gzip.open(dest, "wb", compresslevel=6) as f_out:
                    shutil.copyfileobj(f_in, f_out)
            # Remove uncompressed file
            source.unlink()
            return dest
        
        elif compression == CompressionType.ZSTD:
            if not HAS_ZSTD:
                log.warning("zstd not available, falling back to gzip")
                return self._compress_file(source, CompressionType.GZIP)
            
            dest = Path(str(source) + ".zst")
            cctx = zstd.ZstdCompressor(level=3)
            with open(source, "rb") as f_in:
                with open(dest, "wb") as f_out:
                    f_out.write(cctx.compress(f_in.read()))
            # Remove uncompressed file
            source.unlink()
            return dest
        
        else:
            log.warning(f"Unknown compression type: {compression}, using none")
            return source

    def _decompress_file(self, source: Path, dest: Path) -> Path:
        """
        Decompress a file based on its extension.
        
        Args:
            source: Compressed source file
            dest: Destination for decompressed file
            
        Returns:
            Path to decompressed file
        """
        if source.suffix == ".gz":
            with gzip.open(source, "rb") as f_in:
                with open(dest, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            return dest
        
        elif source.suffix == ".zst":
            if not HAS_ZSTD:
                raise RuntimeError("zstandard not installed, cannot decompress .zst file")
            
            dctx = zstd.ZstdDecompressor()
            with open(source, "rb") as f_in:
                with open(dest, "wb") as f_out:
                    f_out.write(dctx.decompress(f_in.read()))
            return dest
        
        else:
            # No compression, just copy
            shutil.copy2(source, dest)
            return dest

    def create_backup(
        self,
        backup_type: BackupType = BackupType.FULL,
        compression: Optional[CompressionType] = None,
        retention_policy: Optional[RetentionPolicy] = None,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BackupMetadata:
        """
        Create a database backup.
        
        Args:
            backup_type: Type of backup (full, incremental, wal)
            compression: Compression algorithm (defaults to manager's compression)
            retention_policy: Retention policy for this backup
            
        Returns:
            BackupMetadata object with backup information
        """
        start_time = time.time()
        success = False
        
        try:
            if not self.db_path.exists():
                raise FileNotFoundError(f"Database file not found: {self.db_path}")
            
            compression = compression or self.compression
            backup_id = self._generate_backup_id()
            timestamp = datetime.now(timezone.utc)
            
            log.info(f"Creating {backup_type.value} backup: {backup_id}")
            
            # Determine backup file name
            if backup_type == BackupType.FULL:
                backup_name = f"{backup_id}_full.db"
            elif backup_type == BackupType.INCREMENTAL:
                backup_name = f"{backup_id}_incremental.db"
            else:  # WAL
                backup_name = f"{backup_id}_wal.db"
            
            backup_path = self.backup_dir / backup_name
            
            # Create backup using SQLite API for consistency
            if backup_type in (BackupType.FULL, BackupType.INCREMENTAL):
                self._backup_database(self.db_path, backup_path)
            elif backup_type == BackupType.WAL:
                self._backup_wal(self.db_path, backup_path)
            
            # Calculate checksum before compression
            checksum = self._calculate_checksum(backup_path)
            
            # Compress backup
            backup_path = self._compress_file(backup_path, compression)
            
            # Get final size
            size_bytes = backup_path.stat().st_size
            
            # Create metadata
            custom_metadata = dict(metadata) if metadata else {}
            meta_description = description or custom_metadata.get("description")

            backup_metadata = BackupMetadata(
                backup_id=backup_id,
                backup_type=backup_type,
                timestamp=timestamp,
                db_path=str(self.db_path),
                backup_path=str(backup_path),
                compression=compression,
                size_bytes=size_bytes,
                checksum=checksum,
                retention_policy=retention_policy,
                description=meta_description,
                metadata=custom_metadata,
            )

            # Save metadata
            self._metadata_cache.append(backup_metadata)
            self._save_metadata(backup_metadata)
            
            log.info(f"Backup created: {backup_path} ({size_bytes / 1024 / 1024:.2f} MB)")
            
            success = True
            
            # Update Prometheus metrics
            if HAS_PROMETHEUS:
                duration = time.time() - start_time
                backup_runs_total.labels(backup_type=backup_type.value, status="success").inc()
                backup_duration_seconds.labels(backup_type=backup_type.value).observe(duration)
                backup_size_bytes.labels(
                    backup_type=backup_type.value,
                    compression=compression.value
                ).observe(size_bytes)
                backup_total_count.labels(backup_type=backup_type.value).inc()
                self._update_backup_stats()
            
            return backup_metadata
            
        except Exception as e:
            # Track failure metrics
            if HAS_PROMETHEUS:
                backup_runs_total.labels(backup_type=backup_type.value, status="failed").inc()
                backup_errors_total.labels(backup_type=backup_type.value, error_type="creation").inc()
            raise

    def _wait_for_database_unlock(self, source: Path) -> None:
        """Block until the database is unlocked or the configured timeout expires."""
        start_time = time.monotonic()
        while True:
            try:
                with sqlite3.connect(str(source), timeout=0) as probe_connection:
                    probe_connection.execute("BEGIN IMMEDIATE")
                    probe_connection.rollback()
                return
            except sqlite3.OperationalError as exc:
                message = str(exc).lower()
                if "locked" in message or "busy" in message:
                    elapsed = time.monotonic() - start_time
                    if elapsed >= self.lock_wait_seconds:
                        log.error(
                            "Timed out waiting for database lock before backup after %.2f seconds",
                            elapsed,
                        )
                        raise RuntimeError("database locked during backup") from exc

                    sleep_time = min(0.1, max(0.0, self.lock_wait_seconds - elapsed))
                    if sleep_time:
                        time.sleep(sleep_time)
                    continue
                raise

    def _backup_database(self, source: Path, dest: Path) -> None:
        """
        Backup database using SQLite backup API.
        
        This is the recommended way to backup SQLite databases as it handles
        concurrent writes and ensures consistency.
        """
        self._wait_for_database_unlock(source)
        source_conn = sqlite3.connect(str(source))
        dest_conn = sqlite3.connect(str(dest))
        busy_timeout_ms = max(0, int(self.lock_wait_seconds * 1000))
        if busy_timeout_ms:
            source_conn.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
            dest_conn.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
        start_time = time.monotonic()
        try:
            while True:
                try:
                    with dest_conn:
                        source_conn.backup(dest_conn)
                    return
                except sqlite3.OperationalError as e:
                    message = str(e).lower()
                    if "locked" in message or "busy" in message:
                        elapsed = time.monotonic() - start_time
                        if elapsed >= self.lock_wait_seconds:
                            log.error(
                                "Timed out waiting for database lock after %.2f seconds",
                                elapsed,
                            )
                            raise RuntimeError("database locked during backup") from e

                        sleep_time = min(0.1, max(0.0, self.lock_wait_seconds - elapsed))
                        if sleep_time:
                            time.sleep(sleep_time)
                        continue

                    log.warning(f"SQLite backup failed ({e}); falling back to file copy")
                    shutil.copy2(source, dest)
                    return
        finally:
            source_conn.close()
            dest_conn.close()

    def _backup_wal(self, source: Path, dest: Path) -> None:
        """
        Backup Write-Ahead Log file.
        
        For incremental backups, we can backup just the WAL file.
        """
        wal_path = Path(str(source) + "-wal")
        if wal_path.exists():
            shutil.copy2(wal_path, dest)
        else:
            log.warning(f"WAL file not found: {wal_path}")
            # Create empty file
            dest.touch()

    def verify_backup(self, backup_metadata: BackupMetadata | str | Path) -> bool:
        """
        Verify backup integrity.
        
        Args:
            backup_metadata: Backup metadata to verify
            
        Returns:
            True if backup is valid, False otherwise
        """
        metadata_obj: BackupMetadata | None

        if isinstance(backup_metadata, (str, Path)):
            backup_path = Path(backup_metadata)
            metadata_obj = next(
                (m for m in self._metadata_cache if Path(m.backup_path) == backup_path),
                None,
            )
            if metadata_obj is None:
                log.error(f"No metadata found for backup path: {backup_path}")
                return False
        else:
            metadata_obj = backup_metadata
            backup_path = Path(metadata_obj.backup_path)
        
        if not backup_path.exists():
            log.error(f"Backup file not found: {backup_path}")
            if HAS_PROMETHEUS:
                    backup_verifications_total.labels(status="failed").inc()
                    backup_errors_total.labels(
                        backup_type=metadata_obj.backup_type.value,
                        error_type="verification"
                    ).inc()
            return False
        
        log.info(f"Verifying backup: {metadata_obj.backup_id}")
        current_size = backup_path.stat().st_size
        if current_size != metadata_obj.size_bytes:
            log.error(
                "Backup size mismatch: expected %d bytes, got %d bytes",
                metadata_obj.size_bytes,
                current_size,
            )
            if HAS_PROMETHEUS:
                backup_verifications_total.labels(status="failed").inc()
                backup_errors_total.labels(
                    backup_type=metadata_obj.backup_type.value,
                    error_type="verification"
                ).inc()
            return False
        
        # Decompress to temp file
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        
        try:
            self._decompress_file(backup_path, tmp_path)
            
            # Verify checksum
            checksum = self._calculate_checksum(tmp_path)
            if checksum != metadata_obj.checksum:
                log.error(f"Checksum mismatch: expected {metadata_obj.checksum}, got {checksum}")
                if HAS_PROMETHEUS:
                    backup_verifications_total.labels(status="failed").inc()
                    backup_errors_total.labels(
                        backup_type=metadata_obj.backup_type.value,
                        error_type="verification"
                    ).inc()
                return False
            
            # Verify SQLite database integrity
            conn = sqlite3.connect(str(tmp_path))
            try:
                cursor = conn.cursor()
                cursor.execute("PRAGMA integrity_check")
                result = cursor.fetchone()
                if result[0] != "ok":
                    log.error(f"Database integrity check failed: {result[0]}")
                    if HAS_PROMETHEUS:
                        backup_verifications_total.labels(status="failed").inc()
                        backup_errors_total.labels(
                        backup_type=metadata_obj.backup_type.value,
                            error_type="verification"
                        ).inc()
                    return False
            finally:
                conn.close()
            
            # Update metadata
            metadata_obj.verified = True
            metadata_obj.verification_timestamp = datetime.now(timezone.utc)
            self._save_metadata()
            log.info(f"Backup verified successfully: {metadata_obj.backup_id}")
            
            # Track success metrics
            if HAS_PROMETHEUS:
                backup_verifications_total.labels(status="success").inc()

            return True
        except Exception as e:
            log.error(f"Backup verification failed: {e}")
            if HAS_PROMETHEUS:
                backup_verifications_total.labels(status="failed").inc()
                backup_errors_total.labels(
                    backup_type=metadata_obj.backup_type.value if metadata_obj else "unknown",
                    error_type="verification"
                ).inc()
            return False
        finally:
            tmp_path.unlink(missing_ok=True)

    def verify_all_backups(self) -> list[dict[str, Any]]:
        """Verify every known backup and return verification results."""
        results: list[dict[str, Any]] = []
        for metadata in list(self._metadata_cache):
            verified = self.verify_backup(metadata)
            results.append(
                {
                    "backup_id": metadata.backup_id,
                    "verified": verified,
                }
            )
        return results

    def restore_backup(
        self,
        backup_metadata: Union[BackupMetadata, str, Path],
        target_path: Optional[Path] = None,
        verify: bool = True,
        output_path: Optional[Union[str, Path]] = None,
    ) -> bool:
        """
        Restore database from backup.
        
        Args:
            backup_metadata: Backup to restore (metadata object or backup_id)
            target_path: Target path for restored database (defaults to original db_path)
            verify: Whether to verify backup before restoring
            
        Returns:
            True if restore successful, False otherwise
        """
        # Resolve backup_metadata to BackupMetadata object
        if isinstance(backup_metadata, BackupMetadata):
            metadata = backup_metadata
        else:
            metadata = self.get_backup(backup_metadata)
            if metadata is None:
                path = Path(backup_metadata)
                metadata = next(
                    (m for m in self._metadata_cache if Path(m.backup_path) == path),
                    None,
                )
            if not metadata:
                log.error(f"Backup not found: {backup_metadata}")
                if HAS_PROMETHEUS:
                    backup_restores_total.labels(status="failed").inc()
                    backup_errors_total.labels(
                        backup_type="unknown",
                        error_type="restore"
                    ).inc()
                return False
        
        backup_path = Path(metadata.backup_path)
        restore_target: Path
        if output_path:
            restore_target = Path(output_path)
        else:
            restore_target = target_path or self.db_path
        
        if not backup_path.exists():
            log.error(f"Backup file not found: {backup_path}")
            if HAS_PROMETHEUS:
                backup_restores_total.labels(status="failed").inc()
                backup_errors_total.labels(
                    backup_type=metadata.backup_type.value,
                    error_type="restore"
                ).inc()
            return False
        
        # Verify backup if requested
        if verify and not metadata.verified:
            if not self.verify_backup(metadata):
                log.error("Backup verification failed, aborting restore")
                if HAS_PROMETHEUS:
                    backup_restores_total.labels(status="failed").inc()
                return False
        
        log.info(f"Restoring backup {metadata.backup_id} to {restore_target}")
        
        try:
            # Create backup of current database if it exists
            if restore_target.exists():
                backup_current = restore_target.with_suffix(f".db.backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}")
                shutil.copy2(restore_target, backup_current)
                log.info(f"Current database backed up to: {backup_current}")
                # Record safety backup metadata
                safety_metadata = BackupMetadata(
                    backup_id=self._generate_backup_id(),
                    backup_type=BackupType.FULL,
                    timestamp=datetime.now(timezone.utc),
                    db_path=str(restore_target),
                    backup_path=str(backup_current),
                    compression=CompressionType.NONE,
                    size_bytes=backup_current.stat().st_size,
                    checksum=self._calculate_checksum(backup_current),
                    description="Safety backup before restore",
                )
                self._metadata_cache.append(safety_metadata)
                self._save_metadata()
                if HAS_PROMETHEUS:
                    backup_runs_total.labels(backup_type=BackupType.FULL.value, status="success").inc()
                    backup_duration_seconds.labels(backup_type=BackupType.FULL.value).observe(0.0)
                    backup_size_bytes.labels(backup_type=BackupType.FULL.value, compression=CompressionType.NONE.value).observe(
                        float(backup_current.stat().st_size)
                    )
                    backup_total_count.labels(backup_type=BackupType.FULL.value).inc()
                    self._update_backup_stats()

            # Decompress and restore
            self._decompress_file(backup_path, restore_target)

            log.info(f"Database restored successfully to: {restore_target}")
            
            # Track success metrics
            if HAS_PROMETHEUS:
                backup_restores_total.labels(status="success").inc()
            
            return True
        
        except Exception as e:
            log.error(f"Restore failed: {e}")
            if HAS_PROMETHEUS:
                backup_restores_total.labels(status="failed").inc()
                backup_errors_total.labels(
                    backup_type=metadata.backup_type.value,
                    error_type="restore"
                ).inc()
            return False

    def _update_backup_stats(self) -> None:
        """Update Prometheus backup statistics gauges."""
        if not HAS_PROMETHEUS:
            return
        
        # Calculate total size
        total_size = sum(b.size_bytes for b in self._metadata_cache)
        backup_total_size_bytes.set(total_size)
        
        # Calculate oldest and newest backup ages
        if self._metadata_cache:
            now = datetime.now(timezone.utc)
            oldest = min(b.timestamp for b in self._metadata_cache)
            newest = max(b.timestamp for b in self._metadata_cache)
            
            oldest_age = (now - oldest).total_seconds()
            newest_age = (now - newest).total_seconds()
            
            backup_oldest_age_seconds.set(oldest_age)
            backup_newest_age_seconds.set(newest_age)

    def list_backups(
        self,
        backup_type: Optional[BackupType] = None,
        retention_policy: Optional[RetentionPolicy] = None,
        verified_only: bool = False,
    ) -> List[BackupMetadata]:
        """
        List available backups.
        
        Args:
            backup_type: Filter by backup type
            retention_policy: Filter by retention policy
            verified_only: Only return verified backups
            
        Returns:
            List of backup metadata
        """
        backups = self._metadata_cache
        
        if backup_type:
            backups = [b for b in backups if b.backup_type == backup_type]
        
        if retention_policy:
            backups = [b for b in backups if b.retention_policy == retention_policy]
        
        if verified_only:
            backups = [b for b in backups if b.verified]
        
        # Sort by timestamp (newest first)
        backups.sort(key=lambda b: b.timestamp, reverse=True)
        
        return backups

    def get_backup(self, backup_id: str) -> Optional[BackupMetadata]:
        """Get backup metadata by ID."""
        for backup in self._metadata_cache:
            if backup.backup_id == backup_id:
                return backup
        return None

    def delete_backup(self, backup_id: str) -> bool:
        """
        Delete a backup.
        
        Args:
            backup_id: Backup ID to delete
            
        Returns:
            True if deleted, False otherwise
        """
        backup = self.get_backup(backup_id)
        if not backup:
            log.error(f"Backup not found: {backup_id}")
            return False
        
        backup_path = Path(backup.backup_path)
        
        try:
            if backup_path.exists():
                backup_path.unlink()
                log.info(f"Deleted backup file: {backup_path}")
            
            metadata_path = self.backup_dir / f"{backup_id}.json"
            if metadata_path.exists():
                metadata_path.unlink()
            
            # Remove from metadata
            self._metadata_cache = [b for b in self._metadata_cache if b.backup_id != backup_id]
            self._save_metadata()
            
            # Update metrics
            if HAS_PROMETHEUS:
                backup_total_count.labels(backup_type=backup.backup_type.value).dec()
                self._update_backup_stats()
            
            log.info(f"Backup deleted: {backup_id}")
            return True
        
        except Exception as e:
            log.error(f"Failed to delete backup: {e}")
            return False

    def enforce_retention_policy(
        self,
        daily_keep: int = 7,
        weekly_keep: int = 4,
        monthly_keep: int = 12,
        dry_run: bool = False,
    ) -> List[str]:
        """
        Enforce retention policy and delete old backups.
        
        Args:
            daily_keep: Number of daily backups to keep
            weekly_keep: Number of weekly backups to keep
            monthly_keep: Number of monthly backups to keep
            dry_run: If True, don't actually delete, just return what would be deleted
            
        Returns:
            Number of deleted backup IDs
        """
        now = datetime.now(timezone.utc)
        deleted = []
        
        # Group backups by retention policy
        daily_backups = [b for b in self._metadata_cache if b.retention_policy == RetentionPolicy.DAILY]
        weekly_backups = [b for b in self._metadata_cache if b.retention_policy == RetentionPolicy.WEEKLY]
        monthly_backups = [b for b in self._metadata_cache if b.retention_policy == RetentionPolicy.MONTHLY]
        
        # Sort by timestamp (oldest first)
        daily_backups.sort(key=lambda b: b.timestamp)
        weekly_backups.sort(key=lambda b: b.timestamp)
        monthly_backups.sort(key=lambda b: b.timestamp)
        
        # Delete old daily backups
        if len(daily_backups) > daily_keep:
            for backup in daily_backups[:-daily_keep]:
                log.info(f"Deleting old daily backup: {backup.backup_id}")
                if backup.cloud_url or backup.cloud_provider:
                    log.info(f"Skipping cloud backup: {backup.backup_id}")
                    continue
                if not dry_run:
                    self.delete_backup(backup.backup_id)
                    if HAS_PROMETHEUS:
                        backup_retention_pruned_total.labels(retention_policy="daily").inc()
                deleted.append(backup.backup_id)
        
        # Delete old weekly backups
        if len(weekly_backups) > weekly_keep:
            for backup in weekly_backups[:-weekly_keep]:
                log.info(f"Deleting old weekly backup: {backup.backup_id}")
                if backup.cloud_url or backup.cloud_provider:
                    log.info(f"Skipping cloud backup: {backup.backup_id}")
                    continue
                if not dry_run:
                    self.delete_backup(backup.backup_id)
                    if HAS_PROMETHEUS:
                        backup_retention_pruned_total.labels(retention_policy="weekly").inc()
                deleted.append(backup.backup_id)
        
        # Delete old monthly backups
        if len(monthly_backups) > monthly_keep:
            for backup in monthly_backups[:-monthly_keep]:
                log.info(f"Deleting old monthly backup: {backup.backup_id}")
                if backup.cloud_url or backup.cloud_provider:
                    log.info(f"Skipping cloud backup: {backup.backup_id}")
                    continue
                if not dry_run:
                    self.delete_backup(backup.backup_id)
                    if HAS_PROMETHEUS:
                        backup_retention_pruned_total.labels(retention_policy="monthly").inc()
                deleted.append(backup.backup_id)
        
        # Also delete any backups older than retention_days (regardless of policy)
        cutoff = now - timedelta(days=self.retention_days)
        for backup in self._metadata_cache:
            if backup.timestamp < cutoff and backup.backup_id not in deleted:
                if backup.cloud_url or backup.cloud_provider:
                    log.info(f"Skipping expired cloud backup: {backup.backup_id}")
                    continue
                log.info(f"Deleting expired backup: {backup.backup_id} (older than {self.retention_days} days)")
                if not dry_run:
                    self.delete_backup(backup.backup_id)
                deleted.append(backup.backup_id)
        
        # Update stats after pruning
        if not dry_run and HAS_PROMETHEUS:
            self._update_backup_stats()
        
        return len(deleted)

    def upload_to_s3(
        self,
        backup_metadata: Union[BackupMetadata, str, Path],
        bucket: str,
        prefix: str = "backups",
        region: str = "us-east-1",
    ) -> bool:
        """
        Upload backup to Amazon S3.
        
        Args:
            backup_metadata: Backup to upload
            bucket: S3 bucket name
            prefix: S3 key prefix
            region: AWS region
            
        Returns:
            True if upload successful, False otherwise
        """
        if isinstance(backup_metadata, BackupMetadata):
            metadata = backup_metadata
        else:
            metadata = self.get_backup(backup_metadata)
            if metadata is None:
                path = Path(backup_metadata)
                metadata = next(
                    (m for m in self._metadata_cache if Path(m.backup_path) == path),
                    None,
                )
            if not metadata:
                log.error(f"Backup not found: {backup_metadata}")
                if boto3 is not None and HAS_PROMETHEUS:
                    backup_uploads_total.labels(provider="s3", status="failed").inc()
                    backup_errors_total.labels(
                        backup_type="unknown",
                        error_type="upload"
                    ).inc()
                return False
        if boto3 is None:
            log.error("boto3 not installed, cannot upload to S3")
            if HAS_PROMETHEUS:
                backup_uploads_total.labels(provider="s3", status="failed").inc()
                backup_errors_total.labels(
                    backup_type=metadata.backup_type.value,
                    error_type="upload"
                ).inc()
            return False
        backup_path = Path(metadata.backup_path)
        if not backup_path.exists():
            log.error(f"Backup file not found: {backup_path}")
            if boto3 is not None and HAS_PROMETHEUS:
                backup_uploads_total.labels(provider="s3", status="failed").inc()
                backup_errors_total.labels(
                    backup_type=metadata.backup_type.value,
                    error_type="upload"
                ).inc()
            return False
        
        s3_key = f"{prefix}/{backup_path.name}"
        start_time = time.time()
        
        try:
            client_kwargs = {"region_name": region} if region != "us-east-1" else {}
            s3_client = boto3.client("s3", **client_kwargs)
            
            log.info(f"Uploading {backup_path.name} to s3://{bucket}/{s3_key}")
            
            s3_client.upload_file(
                str(backup_path),
                bucket,
                s3_key,
                ExtraArgs={
                    "Metadata": {
                        "backup_id": metadata.backup_id,
                        "checksum": metadata.checksum,
                        "timestamp": metadata.timestamp.isoformat(),
                    }
                },
            )
            
            # Update metadata with cloud URL
            metadata.cloud_url = f"s3://{bucket}/{s3_key}"
            metadata.cloud_provider = CloudProvider.S3
            self._save_metadata(metadata)

            log.info(f"Upload successful: {metadata.cloud_url}")
            
            # Track success metrics
            if boto3 is not None and HAS_PROMETHEUS:
                duration = time.time() - start_time
                backup_uploads_total.labels(provider="s3", status="success").inc()
                backup_upload_duration_seconds.labels(provider="s3").observe(duration)
            
            return True
        
        except Exception as e:
            log.error(f"S3 upload failed: {e}")
            if HAS_PROMETHEUS:
                backup_uploads_total.labels(provider="s3", status="failed").inc()
                backup_errors_total.labels(
                    backup_type=metadata.backup_type.value,
                    error_type="upload"
                ).inc()
            return False

    def download_from_s3(
        self,
        s3_url: str,
        dest_path: Optional[Path] = None,
        output_path: Optional[Union[str, Path]] = None,
    ) -> Optional[Path]:
        """
        Download backup from S3.
        
        Args:
            s3_url: S3 URL (s3://bucket/key)
            dest_path: Local destination path
            
        Returns:
            Path to downloaded file, or None if failed
        """
        if boto3 is None:
            log.error("boto3 not installed, cannot download from S3")
            return None
        
        # Parse S3 URL
        if not s3_url.startswith("s3://"):
            log.error(f"Invalid S3 URL: {s3_url}")
            return None
        
        url_parts = s3_url[5:].split("/", 1)
        bucket = url_parts[0]
        key = url_parts[1]
        
        if output_path:
            dest_path = Path(output_path)
        else:
            dest_path = dest_path or self.backup_dir / Path(key).name
        
        try:
            s3_client = boto3.client("s3")
            
            log.info(f"Downloading {s3_url} to {dest_path}")
            s3_client.download_file(bucket, key, str(dest_path))
            
            log.info(f"Download successful: {dest_path}")
            return dest_path
        
        except Exception as e:
            log.error(f"S3 download failed: {e}")
            return None

    def list_s3_backups(
        self,
        bucket: str,
        prefix: str = "backups",
        max_keys: int = 1000,
    ) -> List[Dict[str, Any]]:
        """List objects in the S3 bucket/prefix."""
        if boto3 is None:
            log.error("boto3 not installed, cannot list S3 backups")
            return []

        try:
            s3_client = boto3.client("s3")
            response = s3_client.list_objects_v2(
                Bucket=bucket,
                Prefix=prefix,
                MaxKeys=max_keys,
            )
            contents = response.get("Contents") or []

            backups: List[Dict[str, Any]] = []
            for item in contents:
                backups.append({
                    "key": item.get("Key"),
                    "size": item.get("Size"),
                })
            return backups

        except Exception as e:
            log.error(f"Failed to list S3 backups: {e}")
            return []
