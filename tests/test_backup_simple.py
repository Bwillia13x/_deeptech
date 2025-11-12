"""
Simple test suite for backup functionality.

Tests the actual BackupManager API with proper return types.
"""

import gzip
import shutil
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from signal_harvester.backup import (
    BackupManager,
    BackupMetadata,
    BackupType,
    CompressionType,
    RetentionPolicy,
)


@pytest.fixture
def temp_dir(tmp_path):
    """Create temporary directory for tests."""
    test_dir = tmp_path / "backup_test"
    test_dir.mkdir()
    yield test_dir
    # Cleanup
    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def test_db(temp_dir):
    """Create a test SQLite database."""
    db_path = temp_dir / "test.db"
    
    # Create database with some data
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE test_table (
            id INTEGER PRIMARY KEY,
            name TEXT,
            value INTEGER
        )
    """)
    cursor.execute("INSERT INTO test_table (name, value) VALUES ('test1', 100)")
    cursor.execute("INSERT INTO test_table (name, value) VALUES ('test2', 200)")
    conn.commit()
    conn.close()
    
    return db_path


@pytest.fixture
def backup_manager(test_db, temp_dir):
    """Create BackupManager instance."""
    backup_dir = temp_dir / "backups"
    backup_dir.mkdir()
    
    manager = BackupManager(
        db_path=test_db,
        backup_dir=backup_dir,
        compression=CompressionType.GZIP
    )
    
    return manager


class TestBackupCreation:
    """Test backup creation functionality."""
    
    def test_create_full_backup(self, backup_manager):
        """Test creating a full backup."""
        metadata = backup_manager.create_backup(backup_type=BackupType.FULL)
        
        assert metadata is not None
        assert isinstance(metadata, BackupMetadata)
        assert metadata.backup_type == BackupType.FULL
        assert Path(metadata.backup_path).exists()
        assert metadata.size_bytes > 0
        assert metadata.checksum is not None
    
    def test_create_backup_with_gzip(self, backup_manager):
        """Test backup with gzip compression."""
        metadata = backup_manager.create_backup(
            backup_type=BackupType.FULL,
            compression=CompressionType.GZIP
        )
        
        assert metadata.compression == CompressionType.GZIP
        assert metadata.backup_path.endswith(".gz")
        assert Path(metadata.backup_path).exists()
        
        # Verify it's a valid gzip file
        with gzip.open(metadata.backup_path, 'rb') as f:
            header = f.read(16)
            assert header[:6] == b'SQLite'
    
    def test_create_backup_with_retention_policy(self, backup_manager):
        """Test backup with retention policy."""
        metadata = backup_manager.create_backup(
            retention_policy=RetentionPolicy.DAILY
        )
        
        assert metadata.retention_policy == RetentionPolicy.DAILY
    
    def test_unique_backup_ids(self, backup_manager):
        """Test that each backup gets unique ID."""
        m1 = backup_manager.create_backup()
        time.sleep(1)  # Ensure different timestamp
        m2 = backup_manager.create_backup()
        
        assert m1.backup_id != m2.backup_id


class TestBackupListing:
    """Test backup listing functionality."""
    
    def test_list_empty(self, backup_manager):
        """Test listing when no backups exist."""
        backups = backup_manager.list_backups()
        assert backups == []
    
    def test_list_single_backup(self, backup_manager):
        """Test listing single backup."""
        metadata = backup_manager.create_backup()
        
        backups = backup_manager.list_backups()
        assert len(backups) == 1
        assert backups[0].backup_id == metadata.backup_id
    
    def test_list_multiple_backups(self, backup_manager):
        """Test listing multiple backups."""
        m1 = backup_manager.create_backup()
        time.sleep(1)
        m2 = backup_manager.create_backup()
        
        backups = backup_manager.list_backups()
        assert len(backups) == 2
        
        ids = [b.backup_id for b in backups]
        assert m1.backup_id in ids
        assert m2.backup_id in ids
    
    def test_get_backup_by_id(self, backup_manager):
        """Test retrieving specific backup."""
        metadata = backup_manager.create_backup()
        
        retrieved = backup_manager.get_backup(metadata.backup_id)
        assert retrieved is not None
        assert retrieved.backup_id == metadata.backup_id
    
    def test_get_nonexistent_backup(self, backup_manager):
        """Test retrieving non-existent backup returns None."""
        result = backup_manager.get_backup("nonexistent_id")
        assert result is None


class TestBackupVerification:
    """Test backup verification functionality."""
    
    def test_verify_valid_backup(self, backup_manager):
        """Test verifying a valid backup."""
        metadata = backup_manager.create_backup()
        
        result = backup_manager.verify_backup(metadata)
        assert result is True
    
    def test_verify_nonexistent_backup(self, backup_manager, temp_dir):
        """Test verifying non-existent backup fails."""
        # Create fake metadata pointing to non-existent file
        fake_metadata = BackupMetadata(
            backup_id="fake",
            backup_type=BackupType.FULL,
            timestamp=datetime.now(),
            db_path=str(backup_manager.db_path),
            backup_path=str(temp_dir / "nonexistent.db.gz"),
            compression=CompressionType.GZIP,
            size_bytes=1000,
            checksum="fake"
        )
        
        result = backup_manager.verify_backup(fake_metadata)
        assert result is False


class TestBackupRestore:
    """Test backup restore functionality."""
    
    def test_restore_backup(self, backup_manager, temp_dir):
        """Test restoring a backup."""
        # Create backup
        metadata = backup_manager.create_backup()
        
        # Modify original database
        conn = sqlite3.connect(backup_manager.db_path)
        conn.execute("DELETE FROM test_table")
        conn.commit()
        conn.close()
        
        # Restore from backup (using backup_id string)
        result = backup_manager.restore_backup(metadata.backup_id)
        assert result is True
        
        # Verify data restored
        conn = sqlite3.connect(backup_manager.db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM test_table")
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 2  # Original data restored
    
    def test_restore_to_different_location(self, backup_manager, temp_dir):
        """Test restoring to different location."""
        metadata = backup_manager.create_backup()
        
        restore_path = temp_dir / "restored.db"
        result = backup_manager.restore_backup(
            metadata.backup_id,
            target_path=restore_path
        )
        
        assert result is True
        assert restore_path.exists()
        
        # Verify it's a valid SQLite database
        conn = sqlite3.connect(restore_path)
        cursor = conn.execute("SELECT COUNT(*) FROM test_table")
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 2


class TestRetentionPolicy:
    """Test backup retention functionality."""
    
    def test_enforce_retention_daily(self, backup_manager):
        """Test retention policy enforcement."""
        # Create multiple backups
        for i in range(10):
            backup_manager.create_backup(
                retention_policy=RetentionPolicy.DAILY
            )
            time.sleep(0.1)
        
        # Apply retention (keep last 3 daily)
        deleted = backup_manager.enforce_retention_policy(
            daily_keep=3,
            weekly_keep=4,
            monthly_keep=12
        )
        
        assert len(deleted) >= 7  # Should delete at least 7 old ones
        
        remaining = backup_manager.list_backups()
        assert len(remaining) <= 3


class TestDeleteOperations:
    """Test backup deletion functionality."""
    
    def test_delete_backup(self, backup_manager):
        """Test deleting a backup."""
        metadata = backup_manager.create_backup()
        
        result = backup_manager.delete_backup(metadata.backup_id)
        assert result is True
        
        # Verify backup file deleted
        assert not Path(metadata.backup_path).exists()
        
        # Verify removed from list
        backups = backup_manager.list_backups()
        assert len(backups) == 0
    
    def test_delete_nonexistent_backup(self, backup_manager):
        """Test deleting non-existent backup."""
        result = backup_manager.delete_backup("nonexistent_id")
        assert result is False


class TestMetadata:
    """Test backup metadata handling."""
    
    def test_metadata_persistence(self, backup_manager):
        """Test metadata persists across manager instances."""
        # Create backup
        metadata = backup_manager.create_backup()
        
        # Create new manager instance
        new_manager = BackupManager(
            db_path=backup_manager.db_path,
            backup_dir=backup_manager.backup_dir
        )
        
        # Verify backup still listed
        backups = new_manager.list_backups()
        assert len(backups) == 1
        assert backups[0].backup_id == metadata.backup_id
    
    def test_metadata_includes_checksum(self, backup_manager):
        """Test metadata includes valid checksum."""
        metadata = backup_manager.create_backup()
        
        assert metadata.checksum is not None
        assert len(metadata.checksum) == 64  # SHA256 hex


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
