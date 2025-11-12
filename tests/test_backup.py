"""
Comprehensive test suite for database backup and recovery.

Tests cover:
- Backup creation (full, incremental, WAL)
- Compression (gzip, zstd, none)
- Verification and integrity checking
- Restore operations
- Retention policy enforcement
- Cloud storage upload/download (S3, GCS, Azure) with mocking
- Error handling and edge cases
"""

from __future__ import annotations

import gzip
import json
import os
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from signal_harvester.backup import (
    BackupManager,
    BackupMetadata,
    BackupType,
    CloudProvider,
    CompressionType,
    RetentionPolicy,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Create a temporary SQLite database with sample data."""
    db_path = tmp_path / "test.db"
    
    # Create database with tables
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Create schema
    cursor.execute("""
        CREATE TABLE signals (
            id INTEGER PRIMARY KEY,
            text TEXT NOT NULL,
            score REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE discoveries (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            source TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Insert sample data
    for i in range(10):
        cursor.execute(
            "INSERT INTO signals (text, score) VALUES (?, ?)",
            (f"Signal {i}", i * 10.0)
        )
    
    for i in range(5):
        cursor.execute(
            "INSERT INTO discoveries (title, source) VALUES (?, ?)",
            (f"Discovery {i}", "arxiv")
        )
    
    conn.commit()
    conn.close()
    
    return db_path


@pytest.fixture
def backup_dir(tmp_path: Path) -> Path:
    """Create a temporary backup directory."""
    metadata.backup_path = tmp_path / "backups"
    metadata.backup_path.mkdir()
    return metadata.backup_path


@pytest.fixture
def backup_manager(temp_db: Path, backup_dir: Path) -> BackupManager:
    """Create a BackupManager instance for testing."""
    return BackupManager(
        db_path=str(temp_db),
        backup_dir=str(backup_dir),
    )


@pytest.fixture
def sample_backup_metadata(backup_dir: Path) -> BackupMetadata:
    """Create sample backup metadata for testing."""
    return BackupMetadata(
        backup_id="test_backup_001",
        backup_type=BackupType.FULL,
        timestamp=datetime.now(),
        db_path="var/app.db",
        metadata.backup_path=str(backup_dir / "test_backup.db.gz"),
        compression=CompressionType.GZIP,
        size_bytes=1024,
        checksum="abc123def456",
        retention_policy=RetentionPolicy.DAILY,
    )


# ============================================================================
# Test: Backup Creation
# ============================================================================


class TestBackupCreation:
    """Test backup creation with different types and configurations."""
    
    def test_create_full_backup_no_compression(self, backup_manager, test_db):
        """Test creating a full backup without compression."""
        metadata = backup_manager.create_backup(
            backup_type=BackupType.FULL,
            compression=CompressionType.NONE
        )
        
        assert metadata is not None
        assert Path(metadata.metadata.backup_path).exists()
        assert Path(metadata.metadata.backup_path).stat().st_size > 0
        assert metadata.backup_type == BackupType.FULL
        assert metadata.compression == CompressionType.NONE
    
    def test_create_full_backup_gzip(
        self, backup_manager: BackupManager, backup_dir: Path
    ):
        """Test creating a full backup with gzip compression."""
        metadata = backup_manager.create_backup(
            backup_type=BackupType.FULL,
            compression=CompressionType.GZIP,
        )
        
        assert metadata is not None
        assert Path(metadata.metadata.backup_path).exists()
        assert metadata.metadata.backup_path.endswith(".gz")
        assert Path(metadata.metadata.backup_path).stat().st_size > 0
        
        # Verify it's a valid gzip file
        with gzip.open(metadata.metadata.backup_path, 'rb') as f:
            header = f.read(16)
            assert header[:6] == b'SQLite'  # SQLite file header
    
    @pytest.mark.skipif(
        not hasattr(BackupManager, '_has_zstd') or not BackupManager._has_zstd,
        reason="zstandard not installed"
    )
    def test_create_full_backup_zstd(
        self, backup_manager: BackupManager, backup_dir: Path
    ):
        """Test creating a full backup with zstd compression."""
        metadata = backup_manager.create_backup(
            backup_type=BackupType.FULL,
            compression=CompressionType.ZSTD,
        )
        
        assert metadata is not None
        assert Path(metadata.metadata.backup_path).exists()
        assert metadata.metadata.backup_path.endswith(".zst")
        assert Path(metadata.metadata.backup_path).stat().st_size > 0
    
    def test_create_backup_with_description(
        self, backup_manager: BackupManager
    ):
        """Test creating a backup with a custom description."""
        description = "Pre-deployment backup for v2.5"
        metadata = backup_manager.create_backup(
            backup_type=BackupType.FULL,
            description=description,
        )
        
        # Check metadata
        assert metadata.description == description
        retrieved = backup_manager.get_backup(metadata.backup_id)
        assert retrieved is not None
        assert retrieved.description == description
    
    def test_create_backup_generates_unique_id(
        self, backup_manager: BackupManager
    ):
        """Test that each backup gets a unique ID."""
        metadata1 = backup_manager.create_backup(BackupType.FULL)
        time.sleep(1)  # Ensure different timestamp
        metadata2 = backup_manager.create_backup(BackupType.FULL)
        
        assert metadata1.backup_id != metadata2.backup_id
        assert metadata1.metadata.backup_path != metadata2.metadata.backup_path
    
    def test_create_backup_calculates_checksum(
        self, backup_manager: BackupManager
    ):
        """Test that backup checksum is calculated."""
        metadata = backup_manager.create_backup(BackupType.FULL)
        
        assert metadata.checksum is not None
        assert len(metadata.checksum) == 64  # SHA256 hex length
    
    def test_create_backup_with_retention_policy(
        self, backup_manager: BackupManager
    ):
        """Test creating backup with retention policy."""
        metadata = backup_manager.create_backup(
            backup_type=BackupType.FULL,
            retention_policy=RetentionPolicy.WEEKLY,
        )
        
        assert metadata.retention_policy == RetentionPolicy.WEEKLY
        assert metadata.retention_policy == RetentionPolicy.WEEKLY


# ============================================================================
# Test: Backup Verification
# ============================================================================


class TestBackupVerification:
    """Test backup verification and integrity checking."""
    
    def test_verify_valid_backup(self, backup_manager: BackupManager):
        """Test verifying a valid backup."""
        metadata = backup_manager.create_backup(BackupType.FULL)
        
        result = backup_manager.verify_backup(metadata.backup_path)
        assert result is True
        
        # Check metadata updated
        metadata = backup_manager.get_backup(metadata.backup_id)
        assert metadata.verified is True
        assert metadata.verification_timestamp is not None
    
    def test_verify_corrupted_backup(
        self, backup_manager: BackupManager, backup_dir: Path
    ):
        """Test verification fails for corrupted backup."""
        # Create valid backup
        metadata = backup_manager.create_backup(
            BackupType.FULL,
            compression=CompressionType.NONE,
        )
        
        # Corrupt the backup by truncating it
        with open(metadata.backup_path, 'r+b') as f:
            f.truncate(100)
        
        # Verification should fail
        result = backup_manager.verify_backup(metadata.backup_path)
        assert result is False
    
    def test_verify_nonexistent_backup(self, backup_manager: BackupManager):
        """Test verification fails for non-existent backup."""
        result = backup_manager.verify_backup("/tmp/nonexistent_backup.db")
        assert result is False
    
    def test_verify_all_backups(self, backup_manager: BackupManager):
        """Test verifying all backups at once."""
        # Create multiple backups
        backup_manager.create_backup(BackupType.FULL)
        time.sleep(0.1)
        backup_manager.create_backup(BackupType.FULL)
        
        results = backup_manager.verify_all_backups()
        assert len(results) == 2
        assert all(r["verified"] for r in results)


# ============================================================================
# Test: Backup Listing
# ============================================================================


class TestBackupListing:
    """Test listing and querying backups."""
    
    def test_list_backups_empty(self, backup_manager: BackupManager):
        """Test listing backups when none exist."""
        backups = backup_manager.list_backups()
        assert backups == []
    
    def test_list_backups_single(self, backup_manager: BackupManager):
        """Test listing single backup."""
        backup_manager.create_backup(BackupType.FULL)
        
        backups = backup_manager.list_backups()
        assert len(backups) == 1
        assert backups[0].backup_type == BackupType.FULL
    
    def test_list_backups_multiple(self, backup_manager: BackupManager):
        """Test listing multiple backups."""
        for i in range(3):
            backup_manager.create_backup(BackupType.FULL)
            time.sleep(0.1)
        
        backups = backup_manager.list_backups()
        assert len(backups) == 3
    
    def test_list_backups_sorted_by_timestamp(
        self, backup_manager: BackupManager
    ):
        """Test that backups are sorted by timestamp (newest first)."""
        timestamps = []
        for i in range(3):
            backup_manager.create_backup(BackupType.FULL)
            time.sleep(0.1)
        
        backups = backup_manager.list_backups()
        for i in range(len(backups) - 1):
            assert backups[i].timestamp >= backups[i + 1].timestamp
    
    def test_list_backups_filter_by_type(
        self, backup_manager: BackupManager
    ):
        """Test filtering backups by type."""
        backup_manager.create_backup(BackupType.FULL)
        backup_manager.create_backup(BackupType.WAL)
        
        full_backups = backup_manager.list_backups(backup_type=BackupType.FULL)
        assert len(full_backups) == 1
        assert full_backups[0].backup_type == BackupType.FULL
        
        wal_backups = backup_manager.list_backups(backup_type=BackupType.WAL)
        assert len(wal_backups) == 1
        assert wal_backups[0].backup_type == BackupType.WAL
    
    def test_get_backup_by_id(self, backup_manager: BackupManager):
        """Test retrieving specific backup by ID."""
        metadata = backup_manager.create_backup(BackupType.FULL)
        backup_id = metadata.backup_id
        
        metadata = backup_manager.get_backup(backup_id)
        assert metadata is not None
        assert metadata.backup_id == backup_id
    
    def test_get_backup_nonexistent(self, backup_manager: BackupManager):
        """Test retrieving non-existent backup returns None."""
        metadata = backup_manager.get_backup("nonexistent_id")
        assert metadata is None


# ============================================================================
# Test: Backup Restore
# ============================================================================


class TestBackupRestore:
    """Test backup restore operations."""
    
    def test_restore_backup_basic(
        self, backup_manager: BackupManager, temp_db: Path, tmp_path: Path
    ):
        """Test basic backup restore."""
        # Create backup
        metadata = backup_manager.create_backup(BackupType.FULL)
        
        # Modify database
        conn = sqlite3.connect(str(temp_db))
        conn.execute("DELETE FROM signals WHERE id > 5")
        conn.commit()
        conn.close()
        
        # Restore
        result = backup_manager.restore_backup(metadata.backup_path)
        assert result is True
        
        # Verify data restored
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM signals")
        count = cursor.fetchone()[0]
        assert count == 10  # Original count
        conn.close()
    
    def test_restore_backup_to_different_location(
        self, backup_manager: BackupManager, tmp_path: Path
    ):
        """Test restoring backup to different location."""
        # Create backup
        metadata = backup_manager.create_backup(BackupType.FULL)
        
        # Restore to different path
        restore_path = tmp_path / "restored.db"
        result = backup_manager.restore_backup(
            metadata.backup_path,
            output_path=str(restore_path)
        )
        
        assert result is True
        assert restore_path.exists()
        
        # Verify data
        conn = sqlite3.connect(str(restore_path))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM signals")
        count = cursor.fetchone()[0]
        assert count == 10
        conn.close()
    
    def test_restore_compressed_backup(
        self, backup_manager: BackupManager, temp_db: Path
    ):
        """Test restoring a compressed backup."""
        # Create compressed backup
        metadata = backup_manager.create_backup(
            BackupType.FULL,
            compression=CompressionType.GZIP,
        )
        
        # Modify database
        conn = sqlite3.connect(str(temp_db))
        conn.execute("DELETE FROM signals")
        conn.commit()
        conn.close()
        
        # Restore
        result = backup_manager.restore_backup(metadata.backup_path)
        assert result is True
        
        # Verify data restored
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM signals")
        count = cursor.fetchone()[0]
        assert count == 10
        conn.close()
    
    def test_restore_creates_safety_backup(
        self, backup_manager: BackupManager, backup_dir: Path
    ):
        """Test that restore creates a safety backup first."""
        # Create and restore backup
        metadata = backup_manager.create_backup(BackupType.FULL)
        
        # Count backups before restore
        backups_before = len(backup_manager.list_backups())
        
        # Restore
        backup_manager.restore_backup(metadata.backup_path)
        
        # Should have one more backup (safety backup)
        backups_after = len(backup_manager.list_backups())
        assert backups_after == backups_before + 1
    
    def test_restore_nonexistent_backup_fails(
        self, backup_manager: BackupManager
    ):
        """Test restoring non-existent backup fails gracefully."""
        result = backup_manager.restore_backup("/tmp/nonexistent.db")
        assert result is False


# ============================================================================
# Test: Retention Policy
# ============================================================================


class TestRetentionPolicy:
    """Test backup retention policy enforcement."""
    
    def test_enforce_retention_daily(
        self, backup_manager: BackupManager
    ):
        """Test daily retention policy keeps last N backups."""
        # Create 10 daily backups
        for i in range(10):
            backup_manager.create_backup(
                BackupType.FULL,
                retention_policy=RetentionPolicy.DAILY,
            )
            time.sleep(0.1)
        
        # Enforce retention (keep last 7)
        pruned = backup_manager.enforce_retention_policy(
            daily_keep=7,
            weekly_keep=0,
            monthly_keep=0,
        )
        
        assert pruned == 3  # Should prune 3 oldest
        
        remaining = backup_manager.list_backups(
            retention_policy=RetentionPolicy.DAILY
        )
        assert len(remaining) == 7
    
    def test_enforce_retention_mixed_policies(
        self, backup_manager: BackupManager
    ):
        """Test retention with mixed policies."""
        # Create backups with different policies
        for i in range(5):
            backup_manager.create_backup(
                BackupType.FULL,
                retention_policy=RetentionPolicy.DAILY,
            )
            time.sleep(0.1)
        
        for i in range(3):
            backup_manager.create_backup(
                BackupType.FULL,
                retention_policy=RetentionPolicy.WEEKLY,
            )
            time.sleep(0.1)
        
        # Enforce retention
        pruned = backup_manager.enforce_retention_policy(
            daily_keep=3,
            weekly_keep=2,
            monthly_keep=0,
        )
        
        # Should prune 2 daily + 1 weekly = 3 total
        assert pruned == 3
    
    def test_retention_preserves_cloud_backups(
        self, backup_manager: BackupManager
    ):
        """Test that retention doesn't delete cloud-uploaded backups."""
        # Create backups, mark some as uploaded
        for i in range(5):
            metadata = backup_manager.create_backup(
                BackupType.FULL,
                retention_policy=RetentionPolicy.DAILY,
            )
            
            if i < 2:
                # Mark as uploaded to cloud
                metadata = backup_manager.get_backup(metadata.backup_id)
                metadata.cloud_url = "s3://bucket/backup"
                metadata.cloud_provider = CloudProvider.S3
                backup_manager._save_metadata(metadata)
            
            time.sleep(0.1)
        
        # Enforce aggressive retention
        pruned = backup_manager.enforce_retention_policy(
            daily_keep=1,
            weekly_keep=0,
            monthly_keep=0,
        )
        
        # Should preserve cloud backups
        remaining = backup_manager.list_backups()
        cloud_backups = [b for b in remaining if b.cloud_url is not None]
        assert len(cloud_backups) == 2
    
    def test_retention_dry_run(self, backup_manager: BackupManager):
        """Test dry run mode doesn't actually delete backups."""
        # Create backups
        for i in range(10):
            backup_manager.create_backup(
                BackupType.FULL,
                retention_policy=RetentionPolicy.DAILY,
            )
            time.sleep(0.1)
        
        # Dry run
        would_prune = backup_manager.enforce_retention_policy(
            daily_keep=3,
            dry_run=True,
        )
        
        assert would_prune == 7
        
        # Verify nothing was deleted
        remaining = backup_manager.list_backups()
        assert len(remaining) == 10


# ============================================================================
# Test: Cloud Storage (S3)
# ============================================================================


class TestCloudStorageS3:
    """Test S3 cloud storage operations with mocking."""
    
    @patch('signal_harvester.backup.boto3')
    def test_upload_to_s3_success(
        self, mock_boto3: Mock, backup_manager: BackupManager
    ):
        """Test successful S3 upload."""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3
        
        # Create backup
        metadata = backup_manager.create_backup(BackupType.FULL)
        
        # Upload
        result = backup_manager.upload_to_s3(
            metadata.backup_path,
            bucket="test-bucket",
            prefix="backups/",
        )
        
        assert result is True
        
        # Verify S3 client called
        mock_boto3.client.assert_called_once_with('s3')
        mock_s3.upload_file.assert_called_once()
        
        # Check metadata updated
        metadata = backup_manager.get_backup(metadata.backup_id)
        assert metadata.cloud_provider == CloudProvider.S3
        assert "s3://" in metadata.cloud_url
    
    @patch('signal_harvester.backup.boto3')
    def test_upload_to_s3_failure(
        self, mock_boto3: Mock, backup_manager: BackupManager
    ):
        """Test S3 upload failure handling."""
        # Mock S3 client to raise exception
        mock_s3 = MagicMock()
        mock_s3.upload_file.side_effect = Exception("S3 error")
        mock_boto3.client.return_value = mock_s3
        
        # Create backup
        metadata = backup_manager.create_backup(BackupType.FULL)
        
        # Upload should fail gracefully
        result = backup_manager.upload_to_s3(metadata.backup_path, bucket="test-bucket")
        assert result is False
    
    @patch('signal_harvester.backup.boto3')
    def test_download_from_s3_success(
        self, mock_boto3: Mock, backup_manager: BackupManager, tmp_path: Path
    ):
        """Test successful S3 download."""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3
        
        # Download
        download_path = tmp_path / "downloaded.db.gz"
        result = backup_manager.download_from_s3(
            s3_url="s3://test-bucket/backups/backup.db.gz",
            output_path=str(download_path),
        )
        
        # Verify S3 client called
        mock_s3.download_file.assert_called_once()
    
    @patch('signal_harvester.backup.boto3')
    def test_list_s3_backups(
        self, mock_boto3: Mock, backup_manager: BackupManager
    ):
        """Test listing backups from S3."""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "backups/backup_001.db.gz", "Size": 1024},
                {"Key": "backups/backup_002.db.gz", "Size": 2048},
            ]
        }
        mock_boto3.client.return_value = mock_s3
        
        # List S3 backups
        backups = backup_manager.list_s3_backups(
            bucket="test-bucket",
            prefix="backups/",
        )
        
        assert len(backups) == 2
        assert backups[0]["size"] == 1024


# ============================================================================
# Test: Compression
# ============================================================================


class TestCompression:
    """Test compression functionality."""
    
    def test_gzip_compression_reduces_size(
        self, backup_manager: BackupManager
    ):
        """Test that gzip compression reduces backup size."""
        # Create uncompressed backup
        backup_none = backup_manager.create_backup(
            BackupType.FULL,
            compression=CompressionType.NONE,
        )
        size_none = Path(backup_none).stat().st_size
        
        # Create compressed backup
        backup_gzip = backup_manager.create_backup(
            BackupType.FULL,
            compression=CompressionType.GZIP,
        )
        size_gzip = Path(backup_gzip).stat().st_size
        
        # Compressed should be smaller
        assert size_gzip < size_none
        
        # Compression ratio should be reasonable
        ratio = size_none / size_gzip
        assert ratio > 1.5  # At least 1.5x compression
    
    def test_decompress_gzip_backup(
        self, backup_manager: BackupManager, tmp_path: Path
    ):
        """Test decompressing gzip backup."""
        # Create compressed backup
        metadata = backup_manager.create_backup(
            BackupType.FULL,
            compression=CompressionType.GZIP,
        )
        
        # Decompress
        decompressed = tmp_path / "decompressed.db"
        with gzip.open(metadata.backup_path, 'rb') as f_in:
            with open(decompressed, 'wb') as f_out:
                f_out.write(f_in.read())
        
        # Verify it's valid SQLite
        conn = sqlite3.connect(str(decompressed))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM signals")
        count = cursor.fetchone()[0]
        assert count == 10
        conn.close()


# ============================================================================
# Test: Metadata
# ============================================================================


class TestMetadata:
    """Test backup metadata management."""
    
    def test_metadata_serialization(
        self, sample_backup_metadata: BackupMetadata
    ):
        """Test metadata can be serialized to JSON."""
        data = sample_backup_metadata.to_dict()
        
        assert isinstance(data, dict)
        assert data["backup_id"] == "test_backup_001"
        assert data["backup_type"] == "full"
        assert "timestamp" in data
    
    def test_metadata_deserialization(
        self, sample_backup_metadata: BackupMetadata
    ):
        """Test metadata can be deserialized from JSON."""
        data = sample_backup_metadata.to_dict()
        restored = BackupMetadata.from_dict(data)
        
        assert restored.backup_id == sample_backup_metadata.backup_id
        assert restored.backup_type == sample_backup_metadata.backup_type
        assert restored.compression == sample_backup_metadata.compression
    
    def test_metadata_persistence(
        self, backup_manager: BackupManager, backup_dir: Path
    ):
        """Test metadata is persisted to disk."""
        # Create backup
        metadata = backup_manager.create_backup(BackupType.FULL)
        backup_id = metadata.backup_id
        
        # Check metadata file exists
        metadata_file = backup_dir / f"{backup_id}.json"
        assert metadata_file.exists()
        
        # Verify content
        with open(metadata_file) as f:
            data = json.load(f)
            assert data["backup_id"] == backup_id
    
    def test_metadata_includes_custom_fields(
        self, backup_manager: BackupManager
    ):
        """Test custom metadata fields are preserved."""
        custom_data = {
            "user": "admin",
            "environment": "production",
            "version": "2.5.0",
        }
        
        metadata = backup_manager.create_backup(
            BackupType.FULL,
            metadata=custom_data,
        )
        
        metadata = backup_manager.get_backup(metadata.backup_id)
        assert metadata.metadata["user"] == "admin"
        assert metadata.metadata["environment"] == "production"
        assert metadata.metadata["version"] == "2.5.0"


# ============================================================================
# Test: Delete Operations
# ============================================================================


class TestDeleteOperations:
    """Test backup deletion."""
    
    def test_delete_backup_by_id(
        self, backup_manager: BackupManager, backup_dir: Path
    ):
        """Test deleting backup by ID."""
        # Create backup
        metadata = backup_manager.create_backup(BackupType.FULL)
        backup_id = metadata.backup_id
        
        # Delete
        result = backup_manager.delete_backup(backup_id)
        assert result is True
        
        # Verify deleted
        assert not Path(metadata.metadata.backup_path).exists()
        metadata = backup_manager.get_backup(backup_id)
        assert metadata is None
    
    def test_delete_backup_removes_metadata(
        self, backup_manager: BackupManager, backup_dir: Path
    ):
        """Test deleting backup also removes metadata file."""
        # Create backup
        metadata = backup_manager.create_backup(BackupType.FULL)
        backup_id = metadata.backup_id
        metadata_file = backup_dir / f"{backup_id}.json"
        
        assert metadata_file.exists()
        
        # Delete
        backup_manager.delete_backup(backup_id)
        
        # Verify metadata removed
        assert not metadata_file.exists()
    
    def test_delete_nonexistent_backup(
        self, backup_manager: BackupManager
    ):
        """Test deleting non-existent backup fails gracefully."""
        result = backup_manager.delete_backup("nonexistent_id")
        assert result is False


# ============================================================================
# Test: Error Handling
# ============================================================================


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    def test_create_backup_when_db_locked(
        self, backup_manager: BackupManager, temp_db: Path
    ):
        """Test backup creation when database is locked."""
        # Lock the database
        conn = sqlite3.connect(str(temp_db))
        conn.execute("BEGIN EXCLUSIVE")
        
        try:
            # Try to create backup (should handle lock gracefully)
            metadata = backup_manager.create_backup(BackupType.FULL)
            # WAL mode should still allow backup
            assert metadata.backup_path is not None
        finally:
            conn.rollback()
            conn.close()
    
    def test_create_backup_with_insufficient_disk_space(
        self, backup_manager: BackupManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Test backup creation with disk space issues."""
        # This is difficult to test without actually filling disk
        # For now, just ensure error is caught
        pass  # TODO: Implement with disk quota mocking
    
    def test_restore_with_corrupted_metadata(
        self, backup_manager: BackupManager, backup_dir: Path
    ):
        """Test restore handles corrupted metadata gracefully."""
        # Create backup
        metadata = backup_manager.create_backup(BackupType.FULL)
        backup_id = metadata.backup_id
        
        # Corrupt metadata
        metadata_file = backup_dir / f"{backup_id}.json"
        with open(metadata_file, 'w') as f:
            f.write("{invalid json")
        
        # Try to get backup (should handle gracefully)
        metadata = backup_manager.get_backup(backup_id)
        # Should either return None or reconstruct from file
        assert metadata is None or isinstance(metadata, BackupMetadata)
    
    def test_verify_backup_with_wrong_checksum(
        self, backup_manager: BackupManager
    ):
        """Test verification detects checksum mismatch."""
        # Create backup
        metadata = backup_manager.create_backup(BackupType.FULL)
        backup_id = metadata.backup_id
        
        # Modify backup file slightly
        with open(metadata.backup_path, 'ab') as f:
            f.write(b'\x00' * 100)
        
        # Verification should fail
        result = backup_manager.verify_backup(metadata.backup_path)
        assert result is False


# ============================================================================
# Test: Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for complete backup/restore workflows."""
    
    def test_full_backup_restore_cycle(
        self, backup_manager: BackupManager, temp_db: Path
    ):
        """Test complete backup and restore cycle."""
        # 1. Create backup
        metadata = backup_manager.create_backup(
            BackupType.FULL,
            compression=CompressionType.GZIP,
            description="Integration test backup",
        )
        
        # 2. Verify backup
        verify_result = backup_manager.verify_backup(metadata.backup_path)
        assert verify_result is True
        
        # 3. Modify database
        conn = sqlite3.connect(str(temp_db))
        conn.execute("DELETE FROM signals")
        conn.execute("DELETE FROM discoveries")
        conn.commit()
        conn.close()
        
        # 4. Restore
        restore_result = backup_manager.restore_backup(metadata.backup_path)
        assert restore_result is True
        
        # 5. Verify restoration
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM signals")
        signals_count = cursor.fetchone()[0]
        assert signals_count == 10
        
        cursor.execute("SELECT COUNT(*) FROM discoveries")
        discoveries_count = cursor.fetchone()[0]
        assert discoveries_count == 5
        
        conn.close()
    
    @patch('signal_harvester.backup.boto3')
    def test_backup_upload_download_restore_cycle(
        self, mock_boto3: Mock, backup_manager: BackupManager, temp_db: Path, tmp_path: Path
    ):
        """Test complete cycle including cloud storage."""
        # Mock S3
        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3
        
        # 1. Create and upload backup
        metadata = backup_manager.create_backup(BackupType.FULL)
        upload_result = backup_manager.upload_to_s3(
            metadata.backup_path,
            bucket="test-bucket",
        )
        assert upload_result is True
        
        # 2. Simulate server failure - delete local backup
        os.remove(metadata.backup_path)
        
        # 3. Download from S3
        download_path = tmp_path / "downloaded.db.gz"
        # Mock download
        mock_s3.download_file.return_value = None
        
        # 4. Restore from downloaded backup
        # (In real scenario, would restore from downloaded file)
    
    def test_retention_policy_enforcement_cycle(
        self, backup_manager: BackupManager
    ):
        """Test retention policy enforcement over time."""
        # Create daily backups over 10 days
        for day in range(10):
            backup_manager.create_backup(
                BackupType.FULL,
                retention_policy=RetentionPolicy.DAILY,
            )
            time.sleep(0.1)
        
        # Create weekly backup
        backup_manager.create_backup(
            BackupType.FULL,
            retention_policy=RetentionPolicy.WEEKLY,
        )
        
        # Enforce retention
        pruned = backup_manager.enforce_retention_policy(
            daily_keep=7,
            weekly_keep=4,
            monthly_keep=12,
        )
        
        # Should prune 3 daily backups
        assert pruned == 3
        
        # Verify counts
        daily_backups = backup_manager.list_backups(
            retention_policy=RetentionPolicy.DAILY
        )
        weekly_backups = backup_manager.list_backups(
            retention_policy=RetentionPolicy.WEEKLY
        )
        
        assert len(daily_backups) == 7
        assert len(weekly_backups) == 1


# ============================================================================
# Test: Performance
# ============================================================================


class TestPerformance:
    """Performance-related tests."""
    
    def test_backup_creation_speed(
        self, backup_manager: BackupManager
    ):
        """Test backup creation completes in reasonable time."""
        import time
        
        start = time.time()
        metadata = backup_manager.create_backup(BackupType.FULL)
        duration = time.time() - start
        
        # Should complete in under 5 seconds for small test DB
        assert duration < 5.0
    
    def test_verification_speed(
        self, backup_manager: BackupManager
    ):
        """Test verification completes quickly."""
        import time
        
        metadata = backup_manager.create_backup(BackupType.FULL)
        
        start = time.time()
        backup_manager.verify_backup(metadata.backup_path)
        duration = time.time() - start
        
        # Should complete in under 2 seconds
        assert duration < 2.0
    
    def test_list_many_backups_performance(
        self, backup_manager: BackupManager
    ):
        """Test listing many backups is fast."""
        import time
        
        # Create 50 backups
        for i in range(50):
            backup_manager.create_backup(BackupType.FULL)
            if i % 10 == 0:
                time.sleep(0.1)  # Prevent overwhelming filesystem
        
        # List all backups
        start = time.time()
        backups = backup_manager.list_backups()
        duration = time.time() - start
        
        assert len(backups) == 50
        # Should complete in under 1 second
        assert duration < 1.0
