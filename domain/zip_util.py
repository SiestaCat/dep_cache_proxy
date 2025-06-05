"""ZIP utility for creating ZIP files from blob storage."""
import zipfile
from pathlib import Path
from typing import Dict

from .blob_storage import BlobStorage


class ZipUtil:
    """Utility class for creating ZIP files from blob storage."""
    
    @staticmethod
    def create_zip_from_blobs(
        zip_path: Path, 
        index_data: Dict[str, str], 
        blob_storage: BlobStorage
    ) -> None:
        """
        Creates a ZIP at zip_path. For each (relative_path, file_hash)
        in index_data, read the blob via blob_storage.read_blob(file_hash)
        and add it to the ZIP with arcname=relative_path.
        
        Args:
            zip_path: Path where the ZIP file should be created
            index_data: Dictionary mapping relative paths to file hashes
            blob_storage: BlobStorage instance to read blobs from
        """
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel_path, file_hash in index_data.items():
                blob_bytes = blob_storage.read_blob(file_hash)
                # To add bytes, use writestr
                zf.writestr(rel_path, blob_bytes)