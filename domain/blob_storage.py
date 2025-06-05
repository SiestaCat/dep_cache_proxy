import hashlib
from pathlib import Path
from typing import Optional
from .hash_constants import HASH_ALGORITHM, BLOCK_SIZE


class BlobStorage:
    """
    Encapsulates logic for storing and retrieving file blobs in cache/objects.
    """
    
    def __init__(self, objects_dir: Path):
        self.objects_dir = objects_dir
        self.objects_dir.mkdir(parents=True, exist_ok=True)
    
    def compute_file_hash(self, file_path: Path) -> str:
        """
        Calculates the SHA256 of a file's content in blocks.
        """
        sha = hashlib.new(HASH_ALGORITHM)
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(BLOCK_SIZE)
                if not chunk:
                    break
                sha.update(chunk)
        return sha.hexdigest()
    
    def get_blob_path(self, file_hash: str) -> Path:
        """
        Physical path of the blob: <objects_dir>/<h0h1>/<h2h3>/<file_hash>
        """
        h0_2 = file_hash[0:2]
        h2_4 = file_hash[2:4]
        dir_path = self.objects_dir / h0_2 / h2_4
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path / file_hash
    
    def save_blob(self, file_path: Path) -> str:
        """
        Reads the file at file_path, calculates its hash, and saves its content
        in cache/objects/.../<file_hash> if not already present. Returns file_hash.
        """
        file_hash = self.compute_file_hash(file_path)
        dest = self.get_blob_path(file_hash)
        if not dest.is_file():
            # Only write if it does not already exist
            with open(file_path, "rb") as src, open(dest, "wb") as dst:
                while True:
                    chunk = src.read(BLOCK_SIZE)
                    if not chunk:
                        break
                    dst.write(chunk)
        return file_hash
    
    def read_blob(self, file_hash: str) -> bytes:
        """
        Returns the content of the blob with file_hash.
        """
        path = self.get_blob_path(file_hash)
        with open(path, "rb") as f:
            return f.read()
    
    # Keep compatibility methods for existing code
    def _calculate_hash(self, content: bytes) -> str:
        hasher = hashlib.new(HASH_ALGORITHM)
        hasher.update(content)
        return hasher.hexdigest()
    
    def _get_blob_path(self, hash_value: str) -> Path:
        return self.get_blob_path(hash_value)
    
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