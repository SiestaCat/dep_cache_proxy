from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional
import subprocess
import os


class DependencyInstaller(ABC):
    """Abstract base class for dependency installers."""
    
    @abstractmethod
    def install(self, work_dir: Path) -> None:
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


class NpmInstaller(DependencyInstaller):
    """Installer for npm packages."""
    
    def __init__(self, node_version: str, npm_version: str):
        self.node_version = node_version
        self.npm_version = npm_version
    
    def install(self, work_dir: Path) -> None:
        """Install npm dependencies using npm ci."""
        cmd = ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"]
        
        env = os.environ.copy()
        env["NODE_ENV"] = "production"
        
        result = subprocess.run(
            cmd,
            cwd=str(work_dir),
            env=env,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"npm install failed: {result.stderr}")
    
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
    
    def __init__(self, php_version: str):
        self.php_version = php_version
    
    def install(self, work_dir: Path) -> None:
        """Install composer dependencies."""
        cmd = [
            "composer", "install",
            "--no-dev", "--prefer-dist",
            "--no-scripts", "--no-interaction",
            "--optimize-autoloader"
        ]
        
        result = subprocess.run(
            cmd,
            cwd=str(work_dir),
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"composer install failed: {result.stderr}")
    
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
    
    def get_installer(self, manager: str, versions: Dict[str, str]) -> DependencyInstaller:
        """Create and return the appropriate installer for the given manager."""
        if manager == "npm":
            node_version = versions.get("node")
            npm_version = versions.get("npm")
            if not node_version or not npm_version:
                raise ValueError("Missing node or npm version for npm manager")
            return NpmInstaller(node_version, npm_version)
        
        elif manager == "composer":
            php_version = versions.get("php")
            if not php_version:
                raise ValueError("Missing php version for composer manager")
            return ComposerInstaller(php_version)
        
        else:
            raise ValueError(f"Unsupported manager: {manager}")