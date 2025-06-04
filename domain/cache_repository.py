from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from pathlib import Path
from .dependency_set import DependencySet


class CacheRepository(ABC):
    """
    Abstract repository interface for managing cached dependencies.
    
    This interface defines the contract for storing and retrieving
    dependency sets, indexes, and bundle files.
    """
    
    @abstractmethod
    def store_dependency_set(self, dependency_set: DependencySet) -> None:
        """
        Store a dependency set in the cache.
        
        This should:
        1. Store all individual file blobs in the objects directory
        2. Create/update the index file mapping paths to hashes
        3. Mark the bundle as available for generation
        
        Args:
            dependency_set: The dependency set to store
            
        Raises:
            IOError: If storage operations fail
        """
        pass
    
    @abstractmethod
    def get_index(self, bundle_hash: str) -> Optional[Dict[str, str]]:
        """
        Retrieve the index for a given bundle hash.
        
        The index maps relative file paths to their content hashes.
        
        Args:
            bundle_hash: The hash of the dependency bundle
            
        Returns:
            Dictionary mapping paths to hashes, or None if not found
        """
        pass
    
    @abstractmethod
    def has_bundle(self, bundle_hash: str) -> bool:
        """
        Check if a bundle exists in the cache.
        
        Args:
            bundle_hash: The hash of the dependency bundle
            
        Returns:
            True if the bundle exists, False otherwise
        """
        pass
    
    @abstractmethod
    def get_blob(self, blob_hash: str) -> Optional[bytes]:
        """
        Retrieve a file blob by its hash.
        
        Args:
            blob_hash: The SHA256 hash of the file content
            
        Returns:
            The file content as bytes, or None if not found
        """
        pass
    
    @abstractmethod
    def store_blob(self, blob_hash: str, content: bytes) -> None:
        """
        Store a file blob with its hash.
        
        Args:
            blob_hash: The SHA256 hash of the file content
            content: The file content to store
            
        Raises:
            IOError: If storage fails
        """
        pass
    
    @abstractmethod
    def generate_bundle_zip(self, bundle_hash: str) -> Optional[Path]:
        """
        Generate a ZIP file from stored blobs for a bundle.
        
        This should:
        1. Read the index for the bundle
        2. Retrieve all blobs referenced in the index
        3. Create a ZIP file with the proper directory structure
        4. Store the ZIP in the bundles directory
        
        Args:
            bundle_hash: The hash of the dependency bundle
            
        Returns:
            Path to the generated ZIP file, or None if bundle not found
            
        Raises:
            IOError: If ZIP generation fails
        """
        pass
    
    @abstractmethod
    def get_bundle_zip_path(self, bundle_hash: str) -> Optional[Path]:
        """
        Get the path to a bundle's ZIP file if it exists.
        
        Args:
            bundle_hash: The hash of the dependency bundle
            
        Returns:
            Path to the ZIP file, or None if not generated yet
        """
        pass
    
    @abstractmethod
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the cache.
        
        Returns:
            Dictionary containing:
            - total_blobs: Number of unique file blobs
            - total_indexes: Number of bundle indexes
            - total_bundles: Number of generated ZIP files
            - cache_size_bytes: Total size of all cached data
        """
        pass