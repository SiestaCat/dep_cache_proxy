import base64
import tempfile
import shutil
import os
from pathlib import Path
from typing import Dict, List, Optional

from domain.cache_repository import ICacheRepository
from domain.blob_storage import BlobStorage
from domain.installer import InstallerFactory
from domain.dependency_set import DependencySet, DependencyFile
from infrastructure.docker_utils import DockerUtils
from application.dtos import CacheRequest, CacheResponse, FileData, InstallationResult


class HandleCacheRequest:
    """Orchestrates the cache request handling process."""
    
    def __init__(
        self,
        cache_repo: ICacheRepository,
        blob_storage: BlobStorage,
        installer_factory: InstallerFactory,
        docker_utils: DockerUtils,
        supported_versions_node: Dict[str, str],
        supported_versions_php: List[str],
        use_docker_on_mismatch: bool
    ):
        self.cache_repo = cache_repo
        self.blob_storage = blob_storage
        self.installer_factory = installer_factory
        self.docker_utils = docker_utils
        self.supported_versions_node = supported_versions_node
        self.supported_versions_php = supported_versions_php
        self.use_docker_on_mismatch = use_docker_on_mismatch
    
    def execute(self, request: CacheRequest, base_download_url: str) -> CacheResponse:
        """Process a cache request and return the response."""
        manager = request.manager
        versions = request.versions
        
        # Validate manager
        if manager not in ["npm", "composer"]:
            raise ValueError(f"Unsupported manager: {manager}")
        
        # Determine if we need to use Docker
        use_docker = self._should_use_docker(manager, versions)
        
        # Calculate bundle hash from request
        bundle_hash = self._calculate_bundle_hash(request)
        
        # Check if bundle already exists
        if self.cache_repo.exists_bundle(bundle_hash):
            return CacheResponse(
                bundle_hash=bundle_hash,
                download_url=f"{base_download_url}/download/{bundle_hash}.zip",
                cache_hit=True,
                installation_method="cached"
            )
        
        # Cache miss - need to install and cache
        installation_result = self._install_dependencies(request, use_docker)
        
        if not installation_result.success:
            raise RuntimeError(f"Installation failed: {installation_result.error_message}")
        
        # Store files as blobs and create index
        self._store_installation_result(bundle_hash, manager, versions, installation_result.files)
        
        # Generate ZIP file
        self.cache_repo.generate_bundle_zip(bundle_hash)
        
        return CacheResponse(
            bundle_hash=bundle_hash,
            download_url=f"{base_download_url}/download/{bundle_hash}.zip",
            cache_hit=False,
            installation_method=installation_result.installation_method
        )
    
    def _should_use_docker(self, manager: str, versions: Dict[str, str]) -> bool:
        """Determine if Docker should be used for installation."""
        if not self.use_docker_on_mismatch:
            return False
        
        if manager == "npm":
            node_ver = versions.get("node")
            npm_ver = versions.get("npm")
            if not node_ver or not npm_ver:
                raise ValueError("Missing node or npm version")
            
            supported_npm = self.supported_versions_node.get(node_ver)
            return supported_npm != npm_ver
        
        elif manager == "composer":
            php_ver = versions.get("php")
            if not php_ver:
                raise ValueError("Missing php version")
            
            return php_ver not in self.supported_versions_php
        
        return False
    
    def _calculate_bundle_hash(self, request: CacheRequest) -> str:
        """Calculate the bundle hash from the cache request."""
        # Create DependencyFile objects from request
        dep_files = []
        
        # Add lock file
        lock_content = base64.b64decode(request.lock_content)
        lockfile_name = self._get_lockfile_name(request.manager)
        dep_files.append(DependencyFile(lockfile_name, lock_content))
        
        # Add manifest file if present
        if request.manifest_content:
            manifest_content = base64.b64decode(request.manifest_content)
            manifest_name = self._get_manifest_name(request.manager)
            dep_files.append(DependencyFile(manifest_name, manifest_content))
        
        # Create DependencySet and calculate hash
        dep_set = DependencySet(
            manager=request.manager,
            versions=request.versions,
            files=dep_files
        )
        
        return dep_set.calculate_bundle_hash()
    
    def _get_lockfile_name(self, manager: str) -> str:
        """Get the lockfile name for the given manager."""
        lockfile_names = {
            "npm": "package-lock.json",
            "composer": "composer.lock"
        }
        return lockfile_names.get(manager, "")
    
    def _get_manifest_name(self, manager: str) -> str:
        """Get the manifest file name for the given manager."""
        manifest_names = {
            "npm": "package.json",
            "composer": "composer.json"
        }
        return manifest_names.get(manager, "")
    
    def _install_dependencies(self, request: CacheRequest, use_docker: bool) -> InstallationResult:
        """Install dependencies either natively or using Docker."""
        temp_dir = Path(tempfile.mkdtemp(prefix="dep_cache_"))
        
        try:
            # Write files to temp directory
            lock_content = base64.b64decode(request.lock_content)
            lockfile_name = self._get_lockfile_name(request.manager)
            (temp_dir / lockfile_name).write_bytes(lock_content)
            
            if request.manifest_content:
                manifest_content = base64.b64decode(request.manifest_content)
                manifest_name = self._get_manifest_name(request.manager)
                (temp_dir / manifest_name).write_bytes(manifest_content)
            
            if use_docker:
                # Use Docker for installation
                success = self.docker_utils.install_with_docker(
                    temp_dir,
                    request.manager,
                    request.versions
                )
                
                if not success:
                    return InstallationResult(
                        success=False,
                        files=[],
                        error_message="Docker installation failed"
                    )
                
                files = self._collect_installed_files(temp_dir, request.manager)
                return InstallationResult(
                    success=True,
                    files=files,
                    installation_method="docker"
                )
            
            else:
                # Use native installer
                installer = self.installer_factory.get_installer(request.manager, request.versions)
                
                try:
                    installer.install(temp_dir)
                except Exception as e:
                    return InstallationResult(
                        success=False,
                        files=[],
                        error_message=str(e)
                    )
                
                files = self._collect_installed_files(temp_dir, request.manager)
                return InstallationResult(
                    success=True,
                    files=files,
                    installation_method="native"
                )
        
        finally:
            # Clean up temp directory
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def _collect_installed_files(self, temp_dir: Path, manager: str) -> List[FileData]:
        """Collect all installed files from the output directory."""
        output_dirs = {
            "npm": "node_modules",
            "composer": "vendor"
        }
        
        output_dir = output_dirs.get(manager)
        if not output_dir:
            return []
        
        files = []
        output_path = temp_dir / output_dir
        
        if not output_path.exists():
            return []
        
        for root, _, filenames in os.walk(output_path):
            for filename in filenames:
                file_path = Path(root) / filename
                relative_path = str(file_path.relative_to(output_path))
                content = file_path.read_bytes()
                files.append(FileData(relative_path, content))
        
        return files
    
    def _store_installation_result(
        self,
        bundle_hash: str,
        manager: str,
        versions: Dict[str, str],
        files: List[FileData]
    ) -> None:
        """Store installation files as blobs and create index."""
        index_data = {}
        
        # Store each file as a blob
        for file_data in files:
            file_hash = self.blob_storage.store_file_content(file_data.content)
            index_data[file_data.relative_path] = file_hash
        
        # Determine manager version string
        if manager == "npm":
            node_ver = versions.get("node", "")
            npm_ver = versions.get("npm", "")
            manager_version = f"{node_ver}_{npm_ver}"
        elif manager == "composer":
            manager_version = versions.get("php", "")
        else:
            manager_version = ""
        
        # Save index
        self.cache_repo.save_index(bundle_hash, manager, manager_version, index_data)