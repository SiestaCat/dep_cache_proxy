import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional
from .hash_constants import HASH_ALGORITHM, BLOCK_SIZE


@dataclass
class DependencyFile:
    relative_path: str
    content: bytes


@dataclass
class DependencySet:
    manager: str
    files: List[DependencyFile]
    node_version: Optional[str] = None
    npm_version: Optional[str] = None
    php_version: Optional[str] = None
    
    def calculate_bundle_hash(self) -> str:
        hasher = hashlib.new(HASH_ALGORITHM)
        
        hasher.update(self.manager.encode('utf-8'))
        hasher.update(b'\x00')
        
        if self.node_version:
            hasher.update(f"node:{self.node_version}".encode('utf-8'))
            hasher.update(b'\x00')
        
        if self.npm_version:
            hasher.update(f"npm:{self.npm_version}".encode('utf-8'))
            hasher.update(b'\x00')
        
        if self.php_version:
            hasher.update(f"php:{self.php_version}".encode('utf-8'))
            hasher.update(b'\x00')
        
        sorted_files = sorted(self.files, key=lambda f: f.relative_path)
        
        for file in sorted_files:
            hasher.update(file.relative_path.encode('utf-8'))
            hasher.update(b'\x00')
            
            for i in range(0, len(file.content), BLOCK_SIZE):
                block = file.content[i:i + BLOCK_SIZE]
                hasher.update(block)
            
            hasher.update(b'\x00')
        
        return hasher.hexdigest()
    
    def get_file_hashes(self) -> Dict[str, str]:
        file_hashes = {}
        
        for file in self.files:
            hasher = hashlib.new(HASH_ALGORITHM)
            hasher.update(file.content)
            file_hashes[file.relative_path] = hasher.hexdigest()
        
        return file_hashes