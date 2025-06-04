"""Domain model for dependency sets and bundle hash calculation."""

import hashlib
from typing import List, Dict, Any
from dataclasses import dataclass, field
from .hash_constants import HASH_ALGORITHM, BLOCK_SIZE


@dataclass
class DependencyFile:
    """Represents a single file in a dependency set."""
    relative_path: str
    content_hash: str
    size: int


@dataclass
class DependencySet:
    """Represents a set of dependencies with metadata for hash calculation."""
    manager: str  # npm, composer, etc.
    versions: Dict[str, str]  # e.g., {"node": "18.0.0", "npm": "9.0.0"}
    files: List[DependencyFile] = field(default_factory=list)
    
    def calculate_bundle_hash(self) -> str:
        """
        Calculate the bundle hash for this dependency set.
        
        The hash includes:
        - Manager name
        - Sorted versions
        - Sorted file paths and their hashes
        """
        hasher = hashlib.new(HASH_ALGORITHM)
        
        # Add manager
        hasher.update(self.manager.encode('utf-8'))
        hasher.update(b'\n')
        
        # Add sorted versions
        for key in sorted(self.versions.keys()):
            hasher.update(f"{key}:{self.versions[key]}".encode('utf-8'))
            hasher.update(b'\n')
        
        # Add sorted files
        for file in sorted(self.files, key=lambda f: f.relative_path):
            hasher.update(f"{file.relative_path}:{file.content_hash}:{file.size}".encode('utf-8'))
            hasher.update(b'\n')
        
        return hasher.hexdigest()
    
    def to_index_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for index storage."""
        return {
            "manager": self.manager,
            "versions": self.versions,
            "bundle_hash": self.calculate_bundle_hash(),
            "files": [
                {
                    "path": f.relative_path,
                    "hash": f.content_hash,
                    "size": f.size
                }
                for f in self.files
            ]
        }


def calculate_file_hash(file_content: bytes) -> str:
    """
    Calculate the hash of a file's content using the configured algorithm.
    
    Args:
        file_content: The file content as bytes
        
    Returns:
        The hexadecimal hash string
    """
    hasher = hashlib.new(HASH_ALGORITHM)
    
    # Process in blocks for memory efficiency
    for i in range(0, len(file_content), BLOCK_SIZE):
        hasher.update(file_content[i:i + BLOCK_SIZE])
    
    return hasher.hexdigest()