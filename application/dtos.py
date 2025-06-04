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
    lock_content: str
    manifest_content: Optional[str]


@dataclass
class CacheResponse:
    bundle_hash: str
    download_url: str
    cache_hit: bool
    installation_method: str  # 'cached', 'native', 'docker'


@dataclass
class InstallationResult:
    success: bool
    files: List[FileData]
    error_message: Optional[str] = None
    installation_method: str = 'native'