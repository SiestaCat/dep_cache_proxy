"""Unit tests for dependency set and hash calculation."""

import pytest
from domain.dependency_set import DependencySet, DependencyFile, calculate_file_hash


class TestDependencySet:
    """Test cases for DependencySet class."""
    
    def test_calculate_bundle_hash_deterministic(self):
        """Test that bundle hash is deterministic for same inputs."""
        files = [
            DependencyFile("package.json", b'{"name": "test"}'),
            DependencyFile("node_modules/lib/index.js", b'console.log("hello");'),
        ]
        
        dep_set1 = DependencySet(
            manager="npm",
            files=files,
            node_version="18.0.0",
            npm_version="9.0.0"
        )
        
        dep_set2 = DependencySet(
            manager="npm",
            files=files,
            node_version="18.0.0", 
            npm_version="9.0.0"
        )
        
        assert dep_set1.calculate_bundle_hash() == dep_set2.calculate_bundle_hash()
    
    def test_calculate_bundle_hash_different_manager(self):
        """Test that different managers produce different hashes."""
        files = [DependencyFile("composer.json", b'{"require": {}}')]
        
        npm_set = DependencySet(
            manager="npm",
            files=files,
            node_version="18.0.0"
        )
        
        composer_set = DependencySet(
            manager="composer",
            files=files,
            php_version="8.1.0"
        )
        
        assert npm_set.calculate_bundle_hash() != composer_set.calculate_bundle_hash()
    
    def test_calculate_bundle_hash_file_order_independent(self):
        """Test that file order doesn't affect hash."""
        files1 = [
            DependencyFile("a.txt", b"content a"),
            DependencyFile("b.txt", b"content b"),
        ]
        
        files2 = [
            DependencyFile("b.txt", b"content b"),
            DependencyFile("a.txt", b"content a"),
        ]
        
        dep_set1 = DependencySet(
            manager="npm",
            files=files1,
            node_version="18.0.0"
        )
        
        dep_set2 = DependencySet(
            manager="npm",
            files=files2,
            node_version="18.0.0"
        )
        
        assert dep_set1.calculate_bundle_hash() == dep_set2.calculate_bundle_hash()
    
    def test_get_file_hashes(self):
        """Test file hash calculation."""
        files = [
            DependencyFile("package.json", b'{"name": "test"}'),
            DependencyFile("index.js", b'console.log("hello");'),
        ]
        
        dep_set = DependencySet(
            manager="npm",
            files=files
        )
        
        file_hashes = dep_set.get_file_hashes()
        
        assert len(file_hashes) == 2
        assert "package.json" in file_hashes
        assert "index.js" in file_hashes
        assert len(file_hashes["package.json"]) == 64  # SHA256 produces 64 hex chars
        assert len(file_hashes["index.js"]) == 64
    
    def test_calculate_bundle_hash_version_changes(self):
        """Test that version changes affect bundle hash."""
        files = [DependencyFile("package.json", b'{"name": "test"}')]
        
        dep_set1 = DependencySet(
            manager="npm",
            files=files,
            node_version="18.0.0",
            npm_version="9.0.0"
        )
        
        dep_set2 = DependencySet(
            manager="npm",
            files=files,
            node_version="18.0.1",  # Different node version
            npm_version="9.0.0"
        )
        
        assert dep_set1.calculate_bundle_hash() != dep_set2.calculate_bundle_hash()


class TestFileHash:
    """Test cases for file hash calculation."""
    
    def test_calculate_file_hash_empty(self):
        """Test hash of empty file."""
        content = b""
        hash_value = calculate_file_hash(content)
        # SHA256 of empty string
        assert hash_value == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    
    def test_calculate_file_hash_deterministic(self):
        """Test that same content produces same hash."""
        content = b"Hello, World!"
        hash1 = calculate_file_hash(content)
        hash2 = calculate_file_hash(content)
        assert hash1 == hash2
    
    def test_calculate_file_hash_different_content(self):
        """Test that different content produces different hashes."""
        content1 = b"Hello, World!"
        content2 = b"Hello, Python!"
        hash1 = calculate_file_hash(content1)
        hash2 = calculate_file_hash(content2)
        assert hash1 != hash2
    
    def test_calculate_file_hash_large_file(self):
        """Test hash calculation for content larger than block size."""
        # Create content larger than 8KB block size
        content = b"a" * 10000  # 10KB
        hash_value = calculate_file_hash(content)
        assert len(hash_value) == 64  # SHA256 produces 64 hex characters