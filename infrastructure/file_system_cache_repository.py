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
    
    def store_dependency_set(self, dependency_set: DependencySet) -> None:
        """Store a dependency set in the cache."""
        with self._lock:
            bundle_hash = dependency_set.calculate_bundle_hash()
            index_data = {}
            
            for file in dependency_set.files:
                file_hash = self._calculate_hash(file.content)
                self.store_blob(file_hash, file.content)
                index_data[file.relative_path] = file_hash
            
            index_path = self._get_index_path(bundle_hash)
            index_path.parent.mkdir(parents=True, exist_ok=True)
            with open(index_path, 'w') as f:
                json.dump(index_data, f, indent=2, sort_keys=True)
    
    def get_index(self, bundle_hash: str) -> Optional[Dict[str, str]]:
        """Retrieve the index for a given bundle hash."""
        index_path = self._get_index_path(bundle_hash)
        if index_path.exists():
            with open(index_path, 'r') as f:
                return json.load(f)
        return None
    
    def has_bundle(self, bundle_hash: str) -> bool:
        """Check if a bundle exists in the cache."""
        index_path = self._get_index_path(bundle_hash)
        bundle_path = self._get_bundle_path(bundle_hash)
        return index_path.exists() or bundle_path.exists()
    
    def get_blob(self, blob_hash: str) -> Optional[bytes]:
        """Retrieve a file blob by its hash."""
        blob_path = self._get_blob_path(blob_hash)
        if blob_path.exists():
            return blob_path.read_bytes()
        return None
    
    def store_blob(self, blob_hash: str, content: bytes) -> None:
        """Store a file blob with its hash."""
        blob_path = self._get_blob_path(blob_hash)
        if not blob_path.exists():
            blob_path.parent.mkdir(parents=True, exist_ok=True)
            blob_path.write_bytes(content)
    
    def generate_bundle_zip(self, bundle_hash: str) -> Optional[Path]:
        """Generate a ZIP file from stored blobs for a bundle."""
        index_data = self.get_index(bundle_hash)
        if not index_data:
            return None
        
        bundle_path = self._get_bundle_path(bundle_hash)
        
        with self._lock:
            if bundle_path.exists():
                return bundle_path
            
            bundle_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = bundle_path.with_suffix('.tmp')
            
            try:
                with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for relative_path, file_hash in index_data.items():
                        content = self.get_blob(file_hash)
                        if content is None:
                            raise FileNotFoundError(f"Blob {file_hash} not found for {relative_path}")
                        zf.writestr(relative_path, content)
                
                temp_path.replace(bundle_path)
                return bundle_path
            except Exception:
                if temp_path.exists():
                    temp_path.unlink()
                raise
    
    def get_bundle_zip_path(self, bundle_hash: str) -> Optional[Path]:
        """Get the path to a bundle's ZIP file if it exists."""
        bundle_path = self._get_bundle_path(bundle_hash)
        if bundle_path.exists():
            return bundle_path
        return None
    
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
    
    def _get_index_path(self, bundle_hash: str) -> Path:
        return self.indexes_dir / bundle_hash[:2] / bundle_hash[2:4] / f"{bundle_hash}.json"
    
    def _get_bundle_path(self, bundle_hash: str) -> Path:
        return self.bundles_dir / bundle_hash[:2] / bundle_hash[2:4] / f"{bundle_hash}.zip"
    
    def _get_blob_path(self, file_hash: str) -> Path:
        return self.objects_dir / file_hash[:2] / file_hash[2:4] / file_hash
    
    def _calculate_hash(self, content: bytes) -> str:
        hasher = hashlib.new(HASH_ALGORITHM)
        hasher.update(content)
        return hasher.hexdigest()