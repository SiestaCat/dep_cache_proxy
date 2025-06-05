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


class TestDependencySetEdgeCases:
    """Additional edge case tests for DependencySet."""
    
    def test_dependency_set_with_no_files(self):
        """Test dependency set with empty file list."""
        dep_set = DependencySet(
            manager="npm",
            files=[],
            node_version="14.0.0",
            npm_version="6.0.0"
        )
        
        # Should still produce a valid hash
        bundle_hash = dep_set.calculate_bundle_hash()
        assert bundle_hash is not None
        assert len(bundle_hash) == 64
    
    def test_dependency_set_with_duplicate_filenames(self):
        """Test handling of duplicate file paths."""
        files = [
            DependencyFile("duplicate.js", b"content1"),
            DependencyFile("duplicate.js", b"content2"),  # Same path, different content
        ]
        
        dep_set = DependencySet(
            manager="npm",
            files=files,
            node_version="14.0.0"
        )
        
        # Should handle duplicates (last one wins in dict)
        file_hashes = dep_set.get_file_hashes()
        assert len(file_hashes) == 1
        assert "duplicate.js" in file_hashes
    
    def test_dependency_set_with_binary_files(self):
        """Test handling of binary file content."""
        binary_content = bytes(range(256))  # All possible byte values
        files = [
            DependencyFile("binary.bin", binary_content),
            DependencyFile("text.txt", b"normal text")
        ]
        
        dep_set = DependencySet(
            manager="npm",
            files=files
        )
        
        file_hashes = dep_set.get_file_hashes()
        assert len(file_hashes) == 2
        assert all(len(h) == 64 for h in file_hashes.values())
    
    def test_dependency_set_with_null_bytes(self):
        """Test handling of null bytes in content."""
        files = [
            DependencyFile("null.bin", b"\x00\x00\x00"),
            DependencyFile("mixed.bin", b"text\x00more\x00text")
        ]
        
        dep_set = DependencySet(
            manager="npm",
            files=files
        )
        
        bundle_hash = dep_set.calculate_bundle_hash()
        assert bundle_hash is not None
    
    def test_get_file_hashes_format(self):
        """Test the format of file hashes."""
        files = [
            DependencyFile("package.json", b'{"name": "test"}'),
            DependencyFile("src/index.js", b'console.log("test");')
        ]
        
        dep_set = DependencySet(
            manager="npm",
            files=files,
            node_version="14.0.0",
            npm_version="6.0.0"
        )
        
        file_hashes = dep_set.get_file_hashes()
        
        assert isinstance(file_hashes, dict)
        assert "package.json" in file_hashes
        assert "src/index.js" in file_hashes
        
        # Check hash format
        for path, hash_value in file_hashes.items():
            assert isinstance(hash_value, str)
            assert len(hash_value) == 64
            assert all(c in "0123456789abcdef" for c in hash_value)
    
    def test_calculate_file_hash_with_exact_block_size(self):
        """Test file hash with content exactly matching block size."""
        # Create content exactly 8KB (8192 bytes)
        content = b"x" * 8192
        hash_value = calculate_file_hash(content)
        assert len(hash_value) == 64
    
    def test_calculate_file_hash_with_multiple_blocks(self):
        """Test file hash with content spanning multiple blocks."""
        # Create content that's 3.5 blocks (28KB + 4KB)
        content = b"y" * (8192 * 3 + 4096)
        hash_value = calculate_file_hash(content)
        assert len(hash_value) == 64
    
    def test_dependency_set_version_variations(self):
        """Test different version specification formats."""
        files = [DependencyFile("test.txt", b"content")]
        
        # Test with only manager version
        dep_set1 = DependencySet(
            manager="composer",
            files=files,
            php_version="8.1.0"
        )
        
        # Test npm with both versions
        dep_set2 = DependencySet(
            manager="npm",
            files=files,
            node_version="14.0.0",
            npm_version="6.0.0"
        )
        
        # Both should produce valid hashes
        assert dep_set1.calculate_bundle_hash() is not None
        assert dep_set2.calculate_bundle_hash() is not None
        
        # Different versions should produce different hashes
        assert dep_set1.calculate_bundle_hash() != dep_set2.calculate_bundle_hash()
    
    def test_manager_version_string_generation(self):
        """Test generation of manager version strings."""
        files = [DependencyFile("test.txt", b"content")]
        
        # NPM with both versions
        dep_set = DependencySet(
            manager="npm",
            files=files,
            node_version="14.20.0",
            npm_version="6.14.13"
        )
        
        # Check that versions affect the hash
        bundle_hash1 = dep_set.calculate_bundle_hash()
        
        # Change version
        dep_set.npm_version = "6.14.14"
        bundle_hash2 = dep_set.calculate_bundle_hash()
        
        assert bundle_hash1 != bundle_hash2
        assert len(bundle_hash1) == 64
        assert len(bundle_hash2) == 64