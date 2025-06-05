import subprocess
import json
import logging
from typing import Dict, Optional, List, Tuple
import tempfile
import os
import shlex
import sys
from pathlib import Path

# Add the project root to the Python path to enable imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from application.dtos import InstallationResult, FileData

logger = logging.getLogger(__name__)


class DockerUtils:
    """Utilities for handling dependency installation using Docker when version mismatches occur."""
    
    def __init__(self, use_docker: bool = False):
        """
        Initialize Docker utilities.
        
        Args:
            use_docker: Whether to use Docker for version mismatches
        """
        self.use_docker = use_docker
        self._docker_available = None
    
    def is_available(self) -> bool:
        """Check if Docker is available (alias for is_docker_available)."""
        return self.is_docker_available()
    
    def is_docker_available(self) -> bool:
        """Check if Docker is available and running."""
        if self._docker_available is not None:
            return self._docker_available
            
        try:
            result = subprocess.run(
                ["docker", "version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            self._docker_available = result.returncode == 0
            if not self._docker_available:
                logger.warning("Docker command failed: %s", result.stderr)
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning("Docker not available: %s", e)
            self._docker_available = False
            
        return self._docker_available
    
    def _install_with_docker_internal(
        self,
        manager: str,
        version: str,
        lockfile_content: bytes,
        manifest_content: Optional[bytes] = None,
        custom_args: Optional[List[str]] = None
    ) -> List[Tuple[str, bytes]]:
        """
        Install dependencies using Docker with specific manager version.
        
        Args:
            manager: Package manager name (npm, composer, etc.)
            version: Required version of the package manager
            lockfile_content: Content of the lockfile
            manifest_content: Optional manifest file content (package.json, composer.json)
            
        Returns:
            List of tuples (relative_path, file_content)
            
        Raises:
            RuntimeError: If Docker installation fails
        """
        if not self.use_docker:
            raise RuntimeError("Docker usage is disabled")
            
        if not self.is_docker_available():
            raise RuntimeError("Docker is not available")
            
        # Create temporary directory for installation
        with tempfile.TemporaryDirectory() as temp_dir:
            # Write lockfile
            lockfile_name = self._get_lockfile_name(manager)
            lockfile_path = os.path.join(temp_dir, lockfile_name)
            with open(lockfile_path, 'wb') as f:
                f.write(lockfile_content)
            
            # Write manifest if provided
            if manifest_content:
                manifest_name = self._get_manifest_name(manager)
                manifest_path = os.path.join(temp_dir, manifest_name)
                with open(manifest_path, 'wb') as f:
                    f.write(manifest_content)
            
            # Get Docker image for manager/version
            image = self._get_docker_image(manager, version)
            
            # Build install command
            install_cmd = self._get_install_command(manager, custom_args)
            
            # Run Docker container
            docker_cmd = [
                "docker", "run", "--rm",
                "-v", f"{temp_dir}:/app",
                "-w", "/app",
                image,
                "sh", "-c", install_cmd
            ]
            
            logger.info("Running Docker command: %s", ' '.join(docker_cmd))
            
            try:
                result = subprocess.run(
                    docker_cmd,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minutes timeout
                )
                
                if result.returncode != 0:
                    raise RuntimeError(f"Docker installation failed: {result.stderr}")
                    
            except subprocess.TimeoutExpired:
                raise RuntimeError("Docker installation timed out")
            
            # Collect installed files
            return self._collect_files(temp_dir, manager)
    
    def _get_lockfile_name(self, manager: str) -> str:
        """Get the lockfile name for a package manager."""
        lockfile_names = {
            "npm": "package-lock.json",
            "yarn": "yarn.lock",
            "composer": "composer.lock",
            "pipenv": "Pipfile.lock",
            "poetry": "poetry.lock"
        }
        return lockfile_names.get(manager, f"{manager}.lock")
    
    def _get_manifest_name(self, manager: str) -> str:
        """Get the manifest file name for a package manager."""
        manifest_names = {
            "npm": "package.json",
            "yarn": "package.json",
            "composer": "composer.json",
            "pipenv": "Pipfile",
            "poetry": "pyproject.toml"
        }
        return manifest_names.get(manager, f"{manager}.json")
    
    def _get_docker_image(self, manager: str, version: str) -> str:
        """Get the appropriate Docker image for manager/version."""
        # Sanitize version to prevent command injection
        safe_version = shlex.quote(version)
        
        if manager in ["npm", "yarn"]:
            # Use official Node.js image
            node_version = safe_version.split(':')[0] if ':' in safe_version else safe_version
            return f"node:{node_version}-alpine"
        elif manager == "composer":
            # Use official Composer image
            return f"composer:{safe_version}"
        elif manager in ["pipenv", "poetry"]:
            # Use Python image
            python_version = safe_version.split(':')[0] if ':' in safe_version else safe_version
            return f"python:{python_version}-alpine"
        else:
            raise RuntimeError(f"Unsupported manager for Docker: {manager}")
    
    def _get_install_command(self, manager: str, custom_args: Optional[List[str]] = None) -> str:
        """Get the installation command for a package manager."""
        commands = {
            "npm": "npm ci --ignore-scripts",
            "yarn": "yarn install --frozen-lockfile --ignore-scripts",
            "composer": "composer install --no-scripts --no-autoloader",
            "pipenv": "pipenv install --deploy --ignore-pipfile",
            "poetry": "poetry install --no-interaction"
        }
        
        base_cmd = commands.get(manager)
        if not base_cmd:
            raise RuntimeError(f"Unsupported manager: {manager}")
        
        # Add custom arguments if provided
        if custom_args:
            base_cmd += " " + " ".join(custom_args)
            
        # For Python managers, install the tool first
        if manager == "pipenv":
            return f"pip install pipenv && {base_cmd}"
        elif manager == "poetry":
            return f"pip install poetry && {base_cmd}"
            
        return base_cmd
    
    def _collect_files(self, directory: str, manager: str) -> List[Tuple[str, bytes]]:
        """Collect all installed files from a directory."""
        files = []
        install_dirs = self._get_install_directories(manager)
        
        for install_dir in install_dirs:
            dir_path = os.path.join(directory, install_dir)
            if not os.path.exists(dir_path):
                continue
                
            for root, _, filenames in os.walk(dir_path):
                for filename in filenames:
                    file_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(file_path, directory)
                    
                    try:
                        with open(file_path, 'rb') as f:
                            content = f.read()
                        files.append((rel_path, content))
                    except Exception as e:
                        logger.warning(f"Failed to read file {file_path}: {e}")
                        
        return files
    
    def _get_install_directories(self, manager: str) -> List[str]:
        """Get the directories where dependencies are installed."""
        directories = {
            "npm": ["node_modules"],
            "yarn": ["node_modules"],
            "composer": ["vendor"],
            "pipenv": [".venv"],
            "poetry": [".venv"]
        }
        return directories.get(manager, [])
    
    def install_with_docker(
        self,
        work_dir: str,
        manager: str,
        versions: Dict[str, str],
        custom_args: Optional[List[str]] = None
    ) -> InstallationResult:
        """
        Install dependencies using Docker - interface matching HandleCacheRequest expectations.
        
        Args:
            work_dir: Working directory containing manifest and lockfile
            manager: Package manager name
            versions: Version dictionary
            custom_args: Optional custom arguments
            
        Returns:
            InstallationResult with success status and files
        """
        if not self.use_docker:
            return InstallationResult(
                success=False,
                files=[],
                error_message="Docker usage is disabled"
            )
            
        if not self.is_docker_available():
            return InstallationResult(
                success=False,
                files=[],
                error_message="Docker is not available"
            )
        
        try:
            work_path = Path(work_dir)
            
            # Read manifest and lockfile
            manifest_name = self._get_manifest_name(manager)
            lockfile_name = self._get_lockfile_name(manager)
            
            manifest_path = work_path / manifest_name
            lockfile_path = work_path / lockfile_name
            
            manifest_content = manifest_path.read_bytes() if manifest_path.exists() else None
            lockfile_content = lockfile_path.read_bytes() if lockfile_path.exists() else b''
            
            # Get version string for Docker
            version = self._get_version_for_docker(manager, versions)
            
            # Call the original docker method
            file_tuples = self._install_with_docker_internal(
                manager, version, lockfile_content, manifest_content, custom_args
            )
            
            # Convert to FileData objects
            files = [FileData(rel_path, content) for rel_path, content in file_tuples]
            
            return InstallationResult(
                success=True,
                files=files,
                error_message=None
            )
            
        except Exception as e:
            return InstallationResult(
                success=False,
                files=[],
                error_message=f"Docker installation failed: {str(e)}"
            )
    
    def _get_version_for_docker(self, manager: str, versions: Dict[str, str]) -> str:
        """Extract version string for Docker from versions dict."""
        if manager in ['npm', 'yarn']:
            # Use node version for Docker image
            return versions.get('node', versions.get('runtime', 'latest'))
        elif manager == 'composer':
            # Use php version
            return versions.get('php', versions.get('runtime', 'latest'))
        else:
            return 'latest'