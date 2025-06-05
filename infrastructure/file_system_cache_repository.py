import os
import json
import shutil
import zipfile
import hashlib
from pathlib import Path
from typing import Dict, Optional, List, Tuple, Any
import threading
from domain.cache_repository import CacheRepository
from domain.blob_storage import BlobStorage
from domain.dependency_set import DependencySet
from domain.hash_constants import HASH_ALGORITHM
from domain.zip_util import ZipUtil


class FileSystemCacheRepository(CacheRepository):
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.objects_dir = cache_dir / "objects"
        self.indexes_dir = cache_dir / "indexes"
        self.bundles_dir = cache_dir / "bundles"
        
        self.objects_dir.mkdir(parents=True, exist_ok=True)
        self.indexes_dir.mkdir(parents=True, exist_ok=True)
        self.bundles_dir.mkdir(parents=True, exist_ok=True)
        
        self._lock = threading.Lock()
        self.blob_storage = BlobStorage(self.objects_dir)
        self.zip_util = ZipUtil()
    
    def store_dependency_set(self, dependency_set: DependencySet) -> None:
        """Store a dependency set in the cache."""
        with self._lock:
            bundle_hash = dependency_set.calculate_bundle_hash()
            index_data = {}
            
            for file in dependency_set.files:
                file_hash = self._calculate_hash(file.content)
                self.store_blob(file_hash, file.content)
                index_data[file.relative_path] = file_hash
            
            # Extract manager and version info from dependency_set
            manager = dependency_set.manager
            manager_version = self._get_manager_version(dependency_set)
            
            # Save index with proper naming
            self.save_index(bundle_hash, manager, manager_version, index_data)
    
    def _get_manager_version(self, dependency_set: DependencySet) -> str:
        """Extract manager version string from dependency set."""
        if dependency_set.manager == "npm":
            node_ver = dependency_set.node_version
            npm_ver = dependency_set.npm_version
            if node_ver and npm_ver:
                return f"{node_ver}_{npm_ver}"
            return "unknown"
        elif dependency_set.manager == "composer":
            php_ver = dependency_set.php_version
            return php_ver if php_ver else "unknown"
        else:
            return "unknown"
    
    def save_index(self, bundle_hash: str, manager: str, manager_version: str, index_data: Dict[str, str]) -> None:
        """Save index with proper naming convention."""
        # Create index filename: <bundle_hash>.<manager>.<manager_version>.index
        index_filename = f"{bundle_hash}.{manager}.{manager_version}.index"
        index_path = self.indexes_dir / bundle_hash[:2] / bundle_hash[2:4] / index_filename
        
        index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(index_path, 'w') as f:
            json.dump(index_data, f, indent=2, sort_keys=True)
    
    def get_index(self, bundle_hash: str) -> Optional[Dict[str, str]]:
        """Retrieve the index for a given bundle hash."""
        # Look for any index file matching the bundle hash pattern
        pattern_dir = self.indexes_dir / bundle_hash[:2] / bundle_hash[2:4]
        if not pattern_dir.exists():
            return None
            
        # Find any index file starting with bundle_hash
        for index_file in pattern_dir.glob(f"{bundle_hash}.*"):
            if index_file.is_file() and index_file.suffix == ".index":
                with open(index_file, 'r') as f:
                    return json.load(f)
        
        # Fallback to legacy path for compatibility
        legacy_path = self._get_legacy_index_path(bundle_hash)
        if legacy_path.exists():
            with open(legacy_path, 'r') as f:
                return json.load(f)
        
        return None
    
    def _get_legacy_index_path(self, bundle_hash: str) -> Path:
        """Get legacy index path for backward compatibility."""
        return self.indexes_dir / bundle_hash[:2] / bundle_hash[2:4] / f"{bundle_hash}.json"
    
    def has_bundle(self, bundle_hash: str) -> bool:
        """Check if a bundle exists in the cache."""
        bundle_path = self._get_bundle_path(bundle_hash)
        return bundle_path.exists()
    
    def exists_bundle(self, bundle_hash: str) -> bool:
        """Alias for has_bundle() to maintain compatibility."""
        return self.has_bundle(bundle_hash)
    
    def get_blob(self, blob_hash: str) -> Optional[bytes]:
        """Retrieve a file blob by its hash."""
        return self.blob_storage.get_blob(blob_hash)
    
    def store_blob(self, blob_hash: str, content: bytes) -> None:
        """Store a file blob with its hash."""
        # The blob_hash parameter is ignored since BlobStorage calculates its own hash
        # This is for compatibility with the interface
        actual_hash = self.blob_storage.store_blob(content)
        if actual_hash != blob_hash:
            # Log warning if hashes don't match (in production code)
            pass
    
    def save_blob(self, file_hash: str, content: bytes) -> None:
        """Alias for store_blob() to maintain compatibility."""
        self.store_blob(file_hash, content)
    
    def generate_bundle_zip(self, bundle_hash: str) -> Optional[Path]:
        """Generate a ZIP file from stored blobs for a bundle."""
        with self._lock:
            index_data = self.get_index(bundle_hash)
            if not index_data:
                return None
            
            bundle_path = self._get_bundle_path(bundle_hash)
            bundle_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Use ZipUtil to create ZIP from blobs
            self.zip_util.create_zip_from_blobs(bundle_path, index_data, self.blob_storage)
            
            return bundle_path
    
    def get_bundle_zip_path(self, bundle_hash: str) -> Optional[Path]:
        """Get the path to a bundle's ZIP file if it exists."""
        bundle_path = self._get_bundle_path(bundle_hash)
        if bundle_path.exists():
            return bundle_path
        return None
    
    def get_blob_path(self, file_hash: str) -> Path:
        """Returns the absolute path to the blob given its hash."""
        return self.blob_storage.get_blob_path(file_hash)
    
    def save_bundle_zip(self, bundle_hash: str, zip_content_path: Path) -> None:
        """Saves (or overwrites) the generated ZIP in cache/bundles/<bundle_hash>.zip."""
        bundle_path = self._get_bundle_path(bundle_hash)
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(zip_content_path, bundle_path)
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about the cache."""
        total_blobs = 0
        total_indexes = 0
        total_bundles = 0
        cache_size_bytes = 0
        
        for blob_file in self.objects_dir.rglob("*"):
            if blob_file.is_file():
                total_blobs += 1
                cache_size_bytes += blob_file.stat().st_size
        
        for index_file in self.indexes_dir.rglob("*.index"):
            if index_file.is_file():
                total_indexes += 1
                cache_size_bytes += index_file.stat().st_size
        
        # Also count legacy .json indexes
        for index_file in self.indexes_dir.rglob("*.json"):
            if index_file.is_file():
                total_indexes += 1
                cache_size_bytes += index_file.stat().st_size
        
        for bundle_file in self.bundles_dir.rglob("*.zip"):
            if bundle_file.is_file():
                total_bundles += 1
                cache_size_bytes += bundle_file.stat().st_size
        
        return {
            "total_blobs": total_blobs,
            "total_indexes": total_indexes,
            "total_bundles": total_bundles,
            "cache_size_bytes": cache_size_bytes
        }
    
    def cleanup_old_bundles(self, max_age_seconds: int) -> None:
        """Remove old bundle ZIP files to save space."""
        import time
        current_time = time.time()
        
        for bundle_file in self.bundles_dir.rglob("*.zip"):
            if current_time - bundle_file.stat().st_mtime > max_age_seconds:
                try:
                    bundle_file.unlink()
                except OSError:
                    pass
    
    def _get_bundle_path(self, bundle_hash: str) -> Path:
        return self.bundles_dir / bundle_hash[:2] / bundle_hash[2:4] / f"{bundle_hash}.zip"
    
    def _get_blob_path(self, file_hash: str) -> Path:
        return self.objects_dir / file_hash[:2] / file_hash[2:4] / file_hash
    
    def _calculate_hash(self, content: bytes) -> str:
        hasher = hashlib.new(HASH_ALGORITHM)
        hasher.update(content)
        return hasher.hexdigest()