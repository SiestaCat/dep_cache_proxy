from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional
import subprocess
import os
import sys

# Add the project root to the Python path to enable imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from application.dtos import InstallationResult, FileData


class DependencyInstaller(ABC):
    """Abstract base class for dependency installers."""
    
    def __init__(self, custom_args: Optional[List[str]] = None):
        """Initialize with optional custom arguments."""
        self.custom_args = custom_args or []
    
    @abstractmethod
    def install(self, work_dir: str) -> InstallationResult:
        """Install dependencies in the given directory."""
        pass
    
    @property
    @abstractmethod
    def output_folder_name(self) -> str:
        """Return the name of the output folder (e.g., 'node_modules', 'vendor')."""
        pass
    
    @property
    @abstractmethod
    def lockfile_name(self) -> str:
        """Return the name of the lockfile for this manager."""
        pass
    
    @property
    @abstractmethod
    def manifest_name(self) -> str:
        """Return the name of the manifest file for this manager."""
        pass
    
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


class NpmInstaller(DependencyInstaller):
    """Installer for npm packages."""
    
    def __init__(self, node_version: str, npm_version: str, custom_args: Optional[List[str]] = None):
        super().__init__(custom_args)
        self.node_version = node_version
        self.npm_version = npm_version
    
    def install(self, work_dir: str) -> InstallationResult:
        """Install npm dependencies using npm ci or npm install."""
        work_path = Path(work_dir)
        lockfile_path = work_path / self.lockfile_name
        
        # Check if lockfile exists before installation
        lockfile_existed = lockfile_path.exists() and lockfile_path.stat().st_size > 0
        
        if lockfile_existed:
            # Use npm ci when lockfile is present
            cmd = ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"]
        else:
            # Use npm install when lockfile is missing
            cmd = ["npm", "install", "--ignore-scripts", "--no-audit", "--no-fund"]
        
        # Add custom arguments if provided
        cmd.extend(self.custom_args)
        
        env = os.environ.copy()
        env["NODE_ENV"] = "production"
        
        result = subprocess.run(
            cmd,
            cwd=work_dir,
            env=env,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            return InstallationResult(
                success=False,
                files=[],
                error_message=f"npm install failed: {result.stderr}"
            )
        
        # Collect installed files
        files = self._collect_files(Path(work_dir) / self.output_folder_name)
        
        # If npm install was used (lockfile didn't exist), check if one was generated
        if not lockfile_existed:
            if lockfile_path.exists():
                lockfile_content = lockfile_path.read_bytes()
                files.append(FileData(self.lockfile_name, lockfile_content))
        
        return InstallationResult(
            success=True,
            files=files,
            error_message=None
        )
    
    @property
    def output_folder_name(self) -> str:
        return "node_modules"
    
    @property
    def lockfile_name(self) -> str:
        return "package-lock.json"
    
    @property
    def manifest_name(self) -> str:
        return "package.json"


class ComposerInstaller(DependencyInstaller):
    """Installer for PHP Composer packages."""
    
    def __init__(self, php_version: str, custom_args: Optional[List[str]] = None):
        super().__init__(custom_args)
        self.php_version = php_version
    
    def install(self, work_dir: str) -> InstallationResult:
        """Install composer dependencies."""
        cmd = [
            "composer", "install",
            "--prefer-dist",
            "--no-scripts", "--no-interaction",
            "--optimize-autoloader"
        ]
        
        # Add custom arguments if provided
        cmd.extend(self.custom_args)
        
        result = subprocess.run(
            cmd,
            cwd=work_dir,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            return InstallationResult(
                success=False,
                files=[],
                error_message=f"composer install failed: {result.stderr}"
            )
        
        # Collect installed files
        files = self._collect_files(Path(work_dir) / self.output_folder_name)
        
        return InstallationResult(
            success=True,
            files=files,
            error_message=None
        )
    
    @property
    def output_folder_name(self) -> str:
        return "vendor"
    
    @property
    def lockfile_name(self) -> str:
        return "composer.lock"
    
    @property
    def manifest_name(self) -> str:
        return "composer.json"


class InstallerFactory:
    """Factory for creating dependency installers."""
    
    def get_installer(self, manager: str, versions: Dict[str, str], custom_args: Optional[List[str]] = None) -> DependencyInstaller:
        """Create and return the appropriate installer for the given manager."""
        if manager == "npm":
            node_version = versions.get("node")
            npm_version = versions.get("npm")
            if not node_version or not npm_version:
                raise ValueError("Missing node or npm version for npm manager")
            return NpmInstaller(node_version, npm_version, custom_args)
        
        elif manager == "composer":
            php_version = versions.get("php")
            if not php_version:
                raise ValueError("Missing php version for composer manager")
            return ComposerInstaller(php_version, custom_args)
        
        else:
            raise ValueError(f"Unsupported manager: {manager}")
    
    def create_installer(self, manager: str, versions: Dict[str, str], custom_args: Optional[List[str]] = None) -> DependencyInstaller:
        """Alias for get_installer to match usage in HandleCacheRequest."""
        return self.get_installer(manager, versions, custom_args)