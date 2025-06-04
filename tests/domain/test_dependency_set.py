"""Unit tests for dependency set and hash calculation."""

import pytest
from domain.dependency_set import DependencySet, DependencyFile, calculate_file_hash


class TestDependencySet:
    """Test cases for DependencySet class."""
    
    def test_calculate_bundle_hash_deterministic(self):
        """Test that bundle hash is deterministic for same inputs."""
        files = [
            DependencyFile("package.json", "abc123", 1024),
            DependencyFile("node_modules/lib/index.js", "def456", 2048),
        ]
        
        dep_set1 = DependencySet(
            manager="npm",
            versions={"node": "18.0.0", "npm": "9.0.0"},
            files=files
        )
        
        dep_set2 = DependencySet(
            manager="npm",
            versions={"node": "18.0.0", "npm": "9.0.0"},
            files=files
        )
        
        assert dep_set1.calculate_bundle_hash() == dep_set2.calculate_bundle_hash()
    
    def test_calculate_bundle_hash_different_manager(self):
        """Test that different managers produce different hashes."""
        files = [DependencyFile("composer.json", "abc123", 512)]
        
        npm_set = DependencySet(
            manager="npm",
            versions={"node": "18.0.0"},
            files=files
        )
        
        composer_set = DependencySet(
            manager="composer",
            versions={"php": "8.1.0"},
            files=files
        )
        
        assert npm_set.calculate_bundle_hash() != composer_set.calculate_bundle_hash()
    
    def test_calculate_bundle_hash_file_order_independent(self):
        """Test that file order doesn't affect hash."""
        files1 = [
            DependencyFile("a.txt", "hash1", 100),
            DependencyFile("b.txt", "hash2", 200),
        ]
        
        files2 = [
            DependencyFile("b.txt", "hash2", 200),
            DependencyFile("a.txt", "hash1", 100),
        ]
        
        dep_set1 = DependencySet(
            manager="npm",
            versions={"node": "18.0.0"},
            files=files1
        )
        
        dep_set2 = DependencySet(
            manager="npm",
            versions={"node": "18.0.0"},
            files=files2
        )
        
        assert dep_set1.calculate_bundle_hash() == dep_set2.calculate_bundle_hash()
    
    def test_to_index_dict(self):
        """Test conversion to index dictionary format."""
        files = [
            DependencyFile("package.json", "abc123", 1024),
            DependencyFile("node_modules/lib/index.js", "def456", 2048),
        ]
        
        dep_set = DependencySet(
            manager="npm",
            versions={"node": "18.0.0", "npm": "9.0.0"},
            files=files
        )
        
        index_dict = dep_set.to_index_dict()
        
        assert index_dict["manager"] == "npm"
        assert index_dict["versions"] == {"node": "18.0.0", "npm": "9.0.0"}
        assert "bundle_hash" in index_dict
        assert len(index_dict["files"]) == 2
        assert index_dict["files"][0]["path"] == "package.json"
        assert index_dict["files"][0]["hash"] == "abc123"
        assert index_dict["files"][0]["size"] == 1024


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