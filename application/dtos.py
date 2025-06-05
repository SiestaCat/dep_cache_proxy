from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class FileData:
    relative_path: str
    content: bytes


@dataclass
class CacheRequest:
    manager: str
    versions: Dict[str, str]
    lockfile_content: bytes
    manifest_content: bytes
    custom_args: Optional[List[str]] = None


@dataclass
class CacheResponse:
    bundle_hash: str
    download_url: str
    is_cache_hit: bool


@dataclass
class InstallationResult:
    success: bool
    files: List[FileData]
    error_message: Optional[str] = None