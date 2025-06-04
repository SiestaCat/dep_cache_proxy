"""Domain model for dependency sets and bundle hash calculation."""

import hashlib
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from .hash_constants import HASH_ALGORITHM, BLOCK_SIZE


@dataclass
class DependencyFile:
    """Represents a single file in a dependency set."""
    relative_path: str
    content: bytes


@dataclass
class DependencySet:
    """Represents a set of dependencies with metadata for hash calculation."""
    manager: str  # npm, composer, etc.
    files: List[DependencyFile] = field(default_factory=list)
    node_version: Optional[str] = None
    npm_version: Optional[str] = None
    php_version: Optional[str] = None
    
    def calculate_bundle_hash(self) -> str:
        """
        Calculate the bundle hash for this dependency set.
        
        The hash includes:
        - Manager name
        - Version information
        - Sorted file paths and their content hashes
        """
        hasher = hashlib.new(HASH_ALGORITHM)
        
        # Add manager
        hasher.update(self.manager.encode('utf-8'))
        hasher.update(b'\x00')
        
        # Add version information in a consistent order
        if self.node_version:
            hasher.update(f"node:{self.node_version}".encode('utf-8'))
            hasher.update(b'\x00')
        
        if self.npm_version:
            hasher.update(f"npm:{self.npm_version}".encode('utf-8'))
            hasher.update(b'\x00')
        
        if self.php_version:
            hasher.update(f"php:{self.php_version}".encode('utf-8'))
            hasher.update(b'\x00')
        
        # Sort files by path for deterministic hashing
        sorted_files = sorted(self.files, key=lambda f: f.relative_path)
        
        for file in sorted_files:
            hasher.update(file.relative_path.encode('utf-8'))
            hasher.update(b'\x00')
            
            # Hash file content in blocks
            for i in range(0, len(file.content), BLOCK_SIZE):
                block = file.content[i:i + BLOCK_SIZE]
                hasher.update(block)
            
            hasher.update(b'\x00')
        
        return hasher.hexdigest()
    
    def get_file_hashes(self) -> Dict[str, str]:
        """Get a mapping of file paths to their content hashes."""
        file_hashes = {}
        
        for file in self.files:
            hasher = hashlib.new(HASH_ALGORITHM)
            hasher.update(file.content)
            file_hashes[file.relative_path] = hasher.hexdigest()
        
        return file_hashes


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