import pytest
import tempfile
import shutil
import json
import zipfile
import os
import hashlib
from pathlib import Path
from infrastructure.file_system_cache_repository import FileSystemCacheRepository
from domain.blob_storage import BlobStorage
from domain.dependency_set import DependencySet, DependencyFile
from domain.hash_constants import HASH_ALGORITHM


class TestFileSystemCacheRepository:
    @pytest.fixture
    def temp_cache_dir(self):
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def repository(self, temp_cache_dir):
        return FileSystemCacheRepository(temp_cache_dir)
    
    def test_initialization_creates_directories(self, temp_cache_dir):
        repo = FileSystemCacheRepository(temp_cache_dir)
        
        assert (temp_cache_dir / "objects").exists()
        assert (temp_cache_dir / "indexes").exists()
        assert (temp_cache_dir / "bundles").exists()
    
    def test_has_bundle_returns_false_for_nonexistent(self, repository):
        assert not repository.has_bundle("nonexistent_hash")
    
    def test_store_dependency_set_creates_index_and_blobs(self, repository, temp_cache_dir):
        files = [
            DependencyFile("file1.txt", b"content1"),
            DependencyFile("dir/file2.txt", b"content2"),
        ]
        dep_set = DependencySet("npm", files, node_version="14.0.0", npm_version="8.0.0")
        bundle_hash = dep_set.calculate_bundle_hash()
        
        repository.store_dependency_set(dep_set)
        
        index_path = temp_cache_dir / "indexes" / bundle_hash[:2] / bundle_hash[2:4] / f"{bundle_hash}.json"
        assert index_path.exists()
        
        with open(index_path, 'r') as f:
            index_data = json.load(f)
        
        assert "file1.txt" in index_data
        assert "dir/file2.txt" in index_data
        
        hasher1 = hashlib.new(HASH_ALGORITHM)
        hasher1.update(b"content1")
        file1_hash = hasher1.hexdigest()
        
        hasher2 = hashlib.new(HASH_ALGORITHM)
        hasher2.update(b"content2")
        file2_hash = hasher2.hexdigest()
        
        assert index_data["file1.txt"] == file1_hash
        assert index_data["dir/file2.txt"] == file2_hash
        
        blob1_path = temp_cache_dir / "objects" / file1_hash[:2] / file1_hash[2:4] / file1_hash
        blob2_path = temp_cache_dir / "objects" / file2_hash[:2] / file2_hash[2:4] / file2_hash
        
        assert blob1_path.exists()
        assert blob2_path.exists()
        assert blob1_path.read_bytes() == b"content1"
        assert blob2_path.read_bytes() == b"content2"
    
    def test_has_bundle_returns_true_after_storing(self, repository):
        files = [DependencyFile("file.txt", b"content")]
        dep_set = DependencySet("npm", files, node_version="14.0.0", npm_version="8.0.0")
        
        repository.store_dependency_set(dep_set)
        
        assert repository.has_bundle(dep_set.calculate_bundle_hash())
    
    def test_get_index_returns_stored_index(self, repository):
        files = [
            DependencyFile("file1.txt", b"content1"),
            DependencyFile("file2.txt", b"content2"),
        ]
        dep_set = DependencySet("npm", files, node_version="14.0.0", npm_version="8.0.0")
        bundle_hash = dep_set.calculate_bundle_hash()
        
        repository.store_dependency_set(dep_set)
        
        index = repository.get_index(bundle_hash)
        assert index is not None
        assert "file1.txt" in index
        assert "file2.txt" in index
    
    def test_get_index_returns_none_for_nonexistent(self, repository):
        assert repository.get_index("nonexistent") is None
    
    def test_generate_bundle_zip_from_index(self, repository, temp_cache_dir):
        files = [
            DependencyFile("file1.txt", b"content1"),
            DependencyFile("dir/file2.txt", b"content2"),
        ]
        dep_set = DependencySet("npm", files, node_version="14.0.0", npm_version="8.0.0")
        bundle_hash = dep_set.calculate_bundle_hash()
        
        repository.store_dependency_set(dep_set)
        
        bundle_path = repository.generate_bundle_zip(bundle_hash)
        assert bundle_path is not None
        assert bundle_path.exists()
        assert bundle_path.suffix == ".zip"
        
        with zipfile.ZipFile(bundle_path, 'r') as zf:
            assert set(zf.namelist()) == {"file1.txt", "dir/file2.txt"}
            assert zf.read("file1.txt") == b"content1"
            assert zf.read("dir/file2.txt") == b"content2"
    
    def test_get_bundle_zip_path_returns_existing(self, repository, temp_cache_dir):
        bundle_hash = "test_bundle_hash"
        bundle_path = temp_cache_dir / "bundles" / "te" / "st" / "test_bundle_hash.zip"
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        
        with zipfile.ZipFile(bundle_path, 'w') as zf:
            zf.writestr("test.txt", "test content")
        
        result = repository.get_bundle_zip_path(bundle_hash)
        assert result == bundle_path
    
    def test_get_bundle_zip_path_returns_none_for_nonexistent(self, repository):
        assert repository.get_bundle_zip_path("nonexistent") is None
    
    def test_generate_bundle_zip_returns_none_for_nonexistent(self, repository):
        assert repository.generate_bundle_zip("nonexistent") is None
    
    def test_cleanup_old_bundles(self, repository, temp_cache_dir):
        import time
        
        old_bundle_path = temp_cache_dir / "bundles" / "ol" / "d_" / "old_bundle.zip"
        old_bundle_path.parent.mkdir(parents=True, exist_ok=True)
        old_bundle_path.write_text("old")
        
        new_bundle_path = temp_cache_dir / "bundles" / "ne" / "w_" / "new_bundle.zip"
        new_bundle_path.parent.mkdir(parents=True, exist_ok=True)
        new_bundle_path.write_text("new")
        
        old_time = time.time() - 7200
        os.utime(old_bundle_path, (old_time, old_time))
        
        repository.cleanup_old_bundles(3600)
        
        assert not old_bundle_path.exists()
        assert new_bundle_path.exists()
    
    def test_deduplication_stores_same_content_once(self, repository, temp_cache_dir):
        same_content = b"duplicate content"
        
        files1 = [DependencyFile("file1.txt", same_content)]
        files2 = [DependencyFile("file2.txt", same_content)]
        
        dep_set1 = DependencySet("npm", files1, node_version="14.0.0", npm_version="8.0.0")
        dep_set2 = DependencySet("npm", files2, node_version="14.0.0", npm_version="8.0.1")
        
        repository.store_dependency_set(dep_set1)
        repository.store_dependency_set(dep_set2)
        
        hasher = hashlib.new(HASH_ALGORITHM)
        hasher.update(same_content)
        file_hash = hasher.hexdigest()
        blob_path = temp_cache_dir / "objects" / file_hash[:2] / file_hash[2:4] / file_hash
        
        assert blob_path.exists()
        
        objects_count = sum(1 for _ in (temp_cache_dir / "objects").rglob("*") if _.is_file())
        assert objects_count == 1
    
    def test_thread_safety(self, repository):
        import threading
        import concurrent.futures
        
        def store_files(bundle_id):
            files = [DependencyFile(f"file_{bundle_id}.txt", f"content_{bundle_id}".encode())]
            dep_set = DependencySet("npm", files, node_version="14.0.0", npm_version=f"8.0.{bundle_id}")
            repository.store_dependency_set(dep_set)
            bundle_hash = dep_set.calculate_bundle_hash()
            return repository.generate_bundle_zip(bundle_hash)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(store_files, i) for i in range(20)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        assert all(result is not None for result in results)
        assert all(result.exists() for result in results)
    
    def test_get_blob_and_store_blob(self, repository):
        blob_hash = "test_hash"
        content = b"test content"
        
        assert repository.get_blob(blob_hash) is None
        
        repository.store_blob(blob_hash, content)
        
        retrieved = repository.get_blob(blob_hash)
        assert retrieved == content
    
    def test_get_cache_stats(self, repository):
        files = [
            DependencyFile("file1.txt", b"content1"),
            DependencyFile("file2.txt", b"content2"),
        ]
        dep_set = DependencySet("npm", files, node_version="14.0.0", npm_version="8.0.0")
        
        repository.store_dependency_set(dep_set)
        repository.generate_bundle_zip(dep_set.calculate_bundle_hash())
        
        stats = repository.get_cache_stats()
        
        assert stats["total_blobs"] == 2
        assert stats["total_indexes"] == 1
        assert stats["total_bundles"] == 1
        assert stats["cache_size_bytes"] > 0