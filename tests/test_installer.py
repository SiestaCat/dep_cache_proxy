import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import subprocess

from domain.installer import (
    DependencyInstaller,
    NpmInstaller,
    ComposerInstaller,
    InstallerFactory
)


class TestNpmInstaller:
    def test_npm_installer_properties(self):
        installer = NpmInstaller("14.20.0", "6.14.13")
        
        assert installer.node_version == "14.20.0"
        assert installer.npm_version == "6.14.13"
        assert installer.output_folder_name == "node_modules"
        assert installer.lockfile_name == "package-lock.json"
        assert installer.manifest_name == "package.json"
    
    @patch('os.walk')
    @patch('subprocess.run')
    def test_npm_install_success(self, mock_run, mock_walk, tmp_path):
        mock_run.return_value = Mock(returncode=0, stderr="")
        # Mock os.walk to return some files
        node_modules_path = tmp_path / "node_modules"
        node_modules_path.mkdir()
        test_file = node_modules_path / "test.js"
        test_file.write_bytes(b"test content")
        mock_walk.return_value = [(str(node_modules_path), [], ["test.js"])]
        
        installer = NpmInstaller("14.20.0", "6.14.13")
        result = installer.install(str(tmp_path))
        
        assert result.success is True
        assert result.error_message is None
        assert len(result.files) > 0
        
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        
        assert args[0] == ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"]
        assert kwargs['cwd'] == str(tmp_path)
        assert 'env' in kwargs
        assert kwargs['env']['NODE_ENV'] == 'production'
    
    @patch('subprocess.run')
    def test_npm_install_failure(self, mock_run, tmp_path):
        mock_run.return_value = Mock(returncode=1, stderr="npm install failed")
        
        installer = NpmInstaller("14.20.0", "6.14.13")
        result = installer.install(str(tmp_path))
        
        assert result.success is False
        assert result.error_message == "npm install failed: npm install failed"
        assert len(result.files) == 0


class TestComposerInstaller:
    def test_composer_installer_properties(self):
        installer = ComposerInstaller("8.1.0")
        
        assert installer.php_version == "8.1.0"
        assert installer.output_folder_name == "vendor"
        assert installer.lockfile_name == "composer.lock"
        assert installer.manifest_name == "composer.json"
    
    @patch('os.walk')
    @patch('subprocess.run')
    def test_composer_install_success(self, mock_run, mock_walk, tmp_path):
        mock_run.return_value = Mock(returncode=0, stderr="")
        # Mock os.walk to return some files
        vendor_path = tmp_path / "vendor"
        vendor_path.mkdir()
        test_file = vendor_path / "test.php"
        test_file.write_bytes(b"<?php echo 'test';")
        mock_walk.return_value = [(str(vendor_path), [], ["test.php"])]
        
        installer = ComposerInstaller("8.1.0")
        result = installer.install(str(tmp_path))
        
        assert result.success is True
        assert result.error_message is None
        assert len(result.files) > 0
        
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        
        expected_cmd = [
            "composer", "install",
            "--no-dev", "--prefer-dist",
            "--no-scripts", "--no-interaction",
            "--optimize-autoloader"
        ]
        assert args[0] == expected_cmd
        assert kwargs['cwd'] == str(tmp_path)
    
    @patch('subprocess.run')
    def test_composer_install_failure(self, mock_run, tmp_path):
        mock_run.return_value = Mock(returncode=1, stderr="composer install failed")
        
        installer = ComposerInstaller("8.1.0")
        result = installer.install(str(tmp_path))
        
        assert result.success is False
        assert result.error_message == "composer install failed: composer install failed"
        assert len(result.files) == 0


class TestInstallerFactory:
    def test_create_npm_installer(self):
        factory = InstallerFactory()
        versions = {"node": "14.20.0", "npm": "6.14.13"}
        
        installer = factory.get_installer("npm", versions)
        
        assert isinstance(installer, NpmInstaller)
        assert installer.node_version == "14.20.0"
        assert installer.npm_version == "6.14.13"
    
    def test_create_npm_installer_missing_node_version(self):
        factory = InstallerFactory()
        versions = {"npm": "6.14.13"}
        
        with pytest.raises(ValueError) as exc_info:
            factory.get_installer("npm", versions)
        
        assert "Missing node or npm version" in str(exc_info.value)
    
    def test_create_npm_installer_missing_npm_version(self):
        factory = InstallerFactory()
        versions = {"node": "14.20.0"}
        
        with pytest.raises(ValueError) as exc_info:
            factory.get_installer("npm", versions)
        
        assert "Missing node or npm version" in str(exc_info.value)
    
    def test_create_composer_installer(self):
        factory = InstallerFactory()
        versions = {"php": "8.1.0"}
        
        installer = factory.get_installer("composer", versions)
        
        assert isinstance(installer, ComposerInstaller)
        assert installer.php_version == "8.1.0"
    
    def test_create_composer_installer_missing_php_version(self):
        factory = InstallerFactory()
        versions = {}
        
        with pytest.raises(ValueError) as exc_info:
            factory.get_installer("composer", versions)
        
        assert "Missing php version" in str(exc_info.value)
    
    def test_unsupported_manager(self):
        factory = InstallerFactory()
        versions = {"python": "3.9.0"}
        
        with pytest.raises(ValueError) as exc_info:
            factory.get_installer("pip", versions)
        
        assert "Unsupported manager: pip" in str(exc_info.value)