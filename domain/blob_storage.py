import hashlib
from pathlib import Path
from typing import Optional
from .hash_constants import HASH_ALGORITHM, BLOCK_SIZE


class BlobStorage:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.objects_dir = cache_dir / "objects"
        self.objects_dir.mkdir(parents=True, exist_ok=True)
    
    def _calculate_hash(self, content: bytes) -> str:
        hasher = hashlib.new(HASH_ALGORITHM)
        hasher.update(content)
        return hasher.hexdigest()
    
    def _get_blob_path(self, hash_value: str) -> Path:
        return self.objects_dir / hash_value[:2] / hash_value[2:4] / hash_value
    
    def store_blob(self, content: bytes) -> str:
        hash_value = self._calculate_hash(content)
        blob_path = self._get_blob_path(hash_value)
        
        if not blob_path.exists():
            blob_path.parent.mkdir(parents=True, exist_ok=True)
            blob_path.write_bytes(content)
        
        return hash_value
    
    def get_blob(self, hash_value: str) -> Optional[bytes]:
        blob_path = self._get_blob_path(hash_value)
        
        if blob_path.exists():
            return blob_path.read_bytes()
        
        return None
    
    def blob_exists(self, hash_value: str) -> bool:
        return self._get_blob_path(hash_value).exists()