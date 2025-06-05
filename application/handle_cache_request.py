import tempfile
import shutil
import os
from pathlib import Path
from typing import Dict, List, Optional

from domain.dependency_set import DependencySet, DependencyFile
from domain.installer import InstallerFactory
from infrastructure.file_system_cache_repository import FileSystemCacheRepository
from infrastructure.docker_utils import DockerUtils
from application.dtos import CacheRequest, CacheResponse, FileData, InstallationResult


class HandleCacheRequest:
    """Orchestrates the cache request handling process."""
    
    def __init__(
        self,
        cache_repository: FileSystemCacheRepository,
        installer_factory: InstallerFactory,
        docker_utils: Optional[DockerUtils],
        supported_versions: Dict[str, List[Dict[str, str]]],
        use_docker_on_version_mismatch: bool = False
    ):
        self.cache_repository = cache_repository
        self.installer_factory = installer_factory
        self.docker_utils = docker_utils
        self.supported_versions = supported_versions
        self.use_docker_on_version_mismatch = use_docker_on_version_mismatch
    
    def handle(self, request: CacheRequest) -> CacheResponse:
        """Process a cache request and return the response."""
        # Calculate bundle hash
        bundle_hash = self._calculate_bundle_hash(request)
        
        # Check if bundle exists (cache hit)
        if self.cache_repository.has_bundle(bundle_hash):
            return CacheResponse(
                bundle_hash=bundle_hash,
                download_url=f"/download/{bundle_hash}.zip",
                is_cache_hit=True
            )
        
        # Cache miss - determine installation method
        installation_method = self._determine_installation_method(
            request.manager, 
            request.versions
        )
        
        # Install dependencies
        if installation_method == 'docker':
            installation_result = self._install_with_docker(request)
        else:
            installation_result = self._install_natively(request)
        
        if not installation_result.success:
            raise RuntimeError(f"Installation failed: {installation_result.error_message}")
        
        # Create dependency set with installed files
        dep_files = [
            DependencyFile(file.relative_path, file.content)
            for file in installation_result.files
        ]
        
        dependency_set = DependencySet(
            manager=request.manager,
            files=dep_files,
            **self._get_version_kwargs(request.manager, request.versions)
        )
        
        # Store in cache
        self._store_dependency_set(dependency_set, bundle_hash)
        
        return CacheResponse(
            bundle_hash=bundle_hash,
            download_url=f"/download/{bundle_hash}.zip",
            is_cache_hit=False
        )
    
    def _calculate_bundle_hash(self, request: CacheRequest) -> str:
        """Calculate the bundle hash from the request."""
        # Create dependency files from request
        files = []
        
        # Get lockfile and manifest names
        installer = self.installer_factory.create_installer(
            request.manager, request.versions
        )
        
        # Add lockfile
        files.append(DependencyFile(
            installer.lockfile_name,
            request.lockfile_content
        ))
        
        # Add manifest
        files.append(DependencyFile(
            installer.manifest_name,
            request.manifest_content
        ))
        
        # Create dependency set
        dep_set = DependencySet(
            manager=request.manager,
            files=files,
            **self._get_version_kwargs(request.manager, request.versions)
        )
        
        return dep_set.calculate_bundle_hash()
    
    def _get_version_kwargs(self, manager: str, versions: Dict[str, str]) -> Dict[str, str]:
        """Convert versions dict to kwargs for DependencySet."""
        kwargs = {}
        
        if manager in ('npm', 'yarn'):
            # Handle both API format (node/npm) and internal format (runtime/package_manager)
            if 'node' in versions:
                kwargs['node_version'] = versions['node']
            elif 'runtime' in versions:
                kwargs['node_version'] = versions['runtime']
                
            if 'npm' in versions:
                kwargs['npm_version'] = versions['npm']
            elif 'yarn' in versions:
                kwargs['npm_version'] = versions['yarn']  # yarn also uses npm_version in DependencySet
            elif 'package_manager' in versions:
                kwargs['npm_version'] = versions['package_manager']
        elif manager == 'composer':
            if 'php' in versions:
                kwargs['php_version'] = versions['php']
            elif 'runtime' in versions:
                kwargs['php_version'] = versions['runtime']
        
        return kwargs
    
    def _is_version_supported(self, manager: str, versions: Dict[str, str]) -> bool:
        """Check if the given versions are supported."""
        if manager not in self.supported_versions:
            return False
        
        supported_list = self.supported_versions[manager]
        
        # Convert request versions to the expected format
        normalized_versions = {}
        if manager in ('npm', 'yarn'):
            # Map node -> runtime, npm/yarn -> package_manager
            if 'node' in versions:
                normalized_versions['runtime'] = versions['node']
            elif 'runtime' in versions:
                normalized_versions['runtime'] = versions['runtime']
                
            if 'npm' in versions:
                normalized_versions['package_manager'] = versions['npm']
            elif 'yarn' in versions:
                normalized_versions['package_manager'] = versions['yarn']
            elif 'package_manager' in versions:
                normalized_versions['package_manager'] = versions['package_manager']
        elif manager == 'composer':
            # Map php -> runtime
            if 'php' in versions:
                normalized_versions['runtime'] = versions['php']
            elif 'runtime' in versions:
                normalized_versions['runtime'] = versions['runtime']
        else:
            # For other managers, use as-is
            normalized_versions = versions
        
        # Now check against supported versions
        for supported in supported_list:
            # Check if all required fields are present and match
            match = True
            
            # First check if all required fields from supported version are present
            for key in supported.keys():
                if key not in normalized_versions:
                    match = False
                    break
                if supported[key] != normalized_versions.get(key):
                    match = False
                    break
            
            if match:
                return True
        
        return False
    
    def _determine_installation_method(self, manager: str, versions: Dict[str, str]) -> str:
        """Determine whether to use native or Docker installation."""
        if self._is_version_supported(manager, versions):
            return 'native'
        
        if self.use_docker_on_version_mismatch and self.docker_utils and self.docker_utils.is_available():
            return 'docker'
        
        raise ValueError(f"Unsupported {manager} version and Docker is not available")
    
    def _install_natively(self, request: CacheRequest) -> InstallationResult:
        """Install dependencies using native package manager."""
        temp_dir = Path(tempfile.mkdtemp(prefix="dep_cache_"))
        
        try:
            # Get installer
            installer = self.installer_factory.create_installer(
                request.manager, request.versions
            )
            
            # Write lockfile and manifest
            (temp_dir / installer.lockfile_name).write_bytes(request.lockfile_content)
            (temp_dir / installer.manifest_name).write_bytes(request.manifest_content)
            
            # Install
            result = installer.install(str(temp_dir))
            
            return result
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def _install_with_docker(self, request: CacheRequest) -> InstallationResult:
        """Install dependencies using Docker."""
        if not self.docker_utils:
            return InstallationResult(
                success=False,
                files=[],
                error_message="Docker utils not available"
            )
        
        temp_dir = Path(tempfile.mkdtemp(prefix="dep_cache_"))
        
        try:
            # Get installer for file names
            installer = self.installer_factory.create_installer(
                request.manager, request.versions
            )
            
            # Write lockfile and manifest
            (temp_dir / installer.lockfile_name).write_bytes(request.lockfile_content)
            (temp_dir / installer.manifest_name).write_bytes(request.manifest_content)
            
            # Install with Docker
            return self.docker_utils.install_with_docker(
                str(temp_dir),
                request.manager,
                request.versions
            )
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def _collect_files(self, directory: Path) -> List[FileData]:
        """Collect all files from a directory."""
        files = []
        
        if not directory.exists():
            return files
        
        for root, _, filenames in os.walk(directory):
            for filename in filenames:
                file_path = Path(root) / filename
                relative_path = str(file_path.relative_to(directory))
                content = file_path.read_bytes()
                files.append(FileData(relative_path, content))
        
        return files
    
    def _store_dependency_set(self, dependency_set: DependencySet, bundle_hash: str) -> None:
        """Store the dependency set in the cache repository."""
        # The repository handles all storage operations internally
        self.cache_repository.store_dependency_set(dependency_set)
        
        # Generate the bundle ZIP file
        self.cache_repository.generate_bundle_zip(bundle_hash)