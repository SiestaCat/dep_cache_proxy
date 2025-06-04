import unittest
from unittest.mock import patch, MagicMock, call
import subprocess
import tempfile
import os
from infrastructure.docker_utils import DockerUtils


class TestDockerUtils(unittest.TestCase):
    
    def setUp(self):
        self.docker_utils = DockerUtils(use_docker=True)
    
    @patch('subprocess.run')
    def test_is_docker_available_success(self, mock_run):
        """Test Docker availability check when Docker is running."""
        mock_run.return_value = MagicMock(returncode=0)
        
        result = self.docker_utils.is_docker_available()
        
        self.assertTrue(result)
        mock_run.assert_called_once_with(
            ["docker", "version"],
            capture_output=True,
            text=True,
            timeout=5
        )
    
    @patch('subprocess.run')
    def test_is_docker_available_failure(self, mock_run):
        """Test Docker availability check when Docker is not running."""
        mock_run.return_value = MagicMock(returncode=1, stderr="Docker daemon not running")
        
        result = self.docker_utils.is_docker_available()
        
        self.assertFalse(result)
    
    @patch('subprocess.run')
    def test_is_docker_available_timeout(self, mock_run):
        """Test Docker availability check when command times out."""
        mock_run.side_effect = subprocess.TimeoutExpired("docker", 5)
        
        result = self.docker_utils.is_docker_available()
        
        self.assertFalse(result)
    
    @patch('subprocess.run')
    def test_is_docker_available_not_installed(self, mock_run):
        """Test Docker availability check when Docker is not installed."""
        mock_run.side_effect = FileNotFoundError()
        
        result = self.docker_utils.is_docker_available()
        
        self.assertFalse(result)
    
    def test_get_lockfile_name(self):
        """Test lockfile name resolution for different managers."""
        test_cases = [
            ("npm", "package-lock.json"),
            ("yarn", "yarn.lock"),
            ("composer", "composer.lock"),
            ("pipenv", "Pipfile.lock"),
            ("poetry", "poetry.lock"),
            ("unknown", "unknown.lock")
        ]
        
        for manager, expected in test_cases:
            with self.subTest(manager=manager):
                result = self.docker_utils._get_lockfile_name(manager)
                self.assertEqual(result, expected)
    
    def test_get_manifest_name(self):
        """Test manifest file name resolution for different managers."""
        test_cases = [
            ("npm", "package.json"),
            ("yarn", "package.json"),
            ("composer", "composer.json"),
            ("pipenv", "Pipfile"),
            ("poetry", "pyproject.toml"),
            ("unknown", "unknown.json")
        ]
        
        for manager, expected in test_cases:
            with self.subTest(manager=manager):
                result = self.docker_utils._get_manifest_name(manager)
                self.assertEqual(result, expected)
    
    def test_get_docker_image(self):
        """Test Docker image selection for different managers."""
        test_cases = [
            ("npm", "14.17.0", "node:14.17.0-alpine"),
            ("npm", "16.13.0:7.10.0", "node:16.13.0-alpine"),
            ("yarn", "14.17.0", "node:14.17.0-alpine"),
            ("composer", "2.0.0", "composer:2.0.0"),
            ("pipenv", "3.9", "python:3.9-alpine"),
            ("poetry", "3.8:1.1.0", "python:3.8-alpine")
        ]
        
        for manager, version, expected in test_cases:
            with self.subTest(manager=manager, version=version):
                result = self.docker_utils._get_docker_image(manager, version)
                self.assertEqual(result, expected)
    
    def test_get_docker_image_unsupported(self):
        """Test Docker image selection for unsupported manager."""
        with self.assertRaises(RuntimeError) as context:
            self.docker_utils._get_docker_image("unsupported", "1.0.0")
        
        self.assertIn("Unsupported manager for Docker", str(context.exception))
    
    def test_get_install_command(self):
        """Test install command generation for different managers."""
        test_cases = [
            ("npm", "npm ci --ignore-scripts"),
            ("yarn", "yarn install --frozen-lockfile --ignore-scripts"),
            ("composer", "composer install --no-scripts --no-autoloader"),
            ("pipenv", "pip install pipenv && pipenv install --deploy --ignore-pipfile"),
            ("poetry", "pip install poetry && poetry install --no-interaction")
        ]
        
        for manager, expected in test_cases:
            with self.subTest(manager=manager):
                result = self.docker_utils._get_install_command(manager)
                self.assertEqual(result, expected)
    
    def test_get_install_command_unsupported(self):
        """Test install command generation for unsupported manager."""
        with self.assertRaises(RuntimeError) as context:
            self.docker_utils._get_install_command("unsupported")
        
        self.assertIn("Unsupported manager", str(context.exception))
    
    def test_get_install_directories(self):
        """Test installation directory identification."""
        test_cases = [
            ("npm", ["node_modules"]),
            ("yarn", ["node_modules"]),
            ("composer", ["vendor"]),
            ("pipenv", [".venv"]),
            ("poetry", [".venv"]),
            ("unknown", [])
        ]
        
        for manager, expected in test_cases:
            with self.subTest(manager=manager):
                result = self.docker_utils._get_install_directories(manager)
                self.assertEqual(result, expected)
    
    @patch('subprocess.run')
    def test_install_with_docker_success(self, mock_run):
        """Test successful Docker installation."""
        # Mock Docker availability
        self.docker_utils._docker_available = True
        
        # Mock subprocess run
        mock_run.return_value = MagicMock(returncode=0, stdout="Installation successful")
        
        # Mock file operations and collection
        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value = MagicMock()
            
            with patch.object(self.docker_utils, '_collect_files') as mock_collect:
                mock_collect.return_value = [
                    ("node_modules/package1/index.js", b"console.log('test');"),
                    ("node_modules/package1/package.json", b'{"name": "package1"}')
                ]
                
                # Run installation
                lockfile_content = b'{"dependencies": {}}'
                manifest_content = b'{"name": "test"}'
                
                result = self.docker_utils.install_with_docker(
                    "npm", "14.17.0", lockfile_content, manifest_content
                )
            
            # Verify results
            self.assertEqual(len(result), 2)
            self.assertEqual(result[0][0], "node_modules/package1/index.js")
            
            # Verify Docker command
            docker_cmd = mock_run.call_args[0][0]
            self.assertEqual(docker_cmd[0:3], ["docker", "run", "--rm"])
            self.assertIn("node:14.17.0-alpine", docker_cmd)
            self.assertIn("npm ci --ignore-scripts", docker_cmd)
    
    def test_install_with_docker_disabled(self):
        """Test Docker installation when Docker is disabled."""
        docker_utils = DockerUtils(use_docker=False)
        
        with self.assertRaises(RuntimeError) as context:
            docker_utils.install_with_docker("npm", "14.17.0", b"lockfile")
        
        self.assertIn("Docker usage is disabled", str(context.exception))
    
    @patch('subprocess.run')
    def test_install_with_docker_not_available(self, mock_run):
        """Test Docker installation when Docker is not available."""
        mock_run.return_value = MagicMock(returncode=1)
        
        with self.assertRaises(RuntimeError) as context:
            self.docker_utils.install_with_docker("npm", "14.17.0", b"lockfile")
        
        self.assertIn("Docker is not available", str(context.exception))
    
    @patch('subprocess.run')
    def test_install_with_docker_failure(self, mock_run):
        """Test Docker installation failure."""
        # Mock Docker availability
        self.docker_utils._docker_available = True
        
        # Mock subprocess run failure
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="npm ERR! Failed to install dependencies"
        )
        
        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value = MagicMock()
            
            with self.assertRaises(RuntimeError) as context:
                self.docker_utils.install_with_docker("npm", "14.17.0", b"lockfile")
            
            self.assertIn("Docker installation failed", str(context.exception))
            self.assertIn("npm ERR!", str(context.exception))
    
    @patch('subprocess.run')
    def test_install_with_docker_timeout(self, mock_run):
        """Test Docker installation timeout."""
        # Mock Docker availability
        self.docker_utils._docker_available = True
        
        # Mock subprocess timeout
        mock_run.side_effect = subprocess.TimeoutExpired("docker", 300)
        
        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value = MagicMock()
            
            with self.assertRaises(RuntimeError) as context:
                self.docker_utils.install_with_docker("npm", "14.17.0", b"lockfile")
            
            self.assertIn("Docker installation timed out", str(context.exception))
    
    def test_collect_files(self):
        """Test file collection from installation directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test files
            os.makedirs(os.path.join(temp_dir, "node_modules", "package1"))
            
            file1_path = os.path.join(temp_dir, "node_modules", "package1", "index.js")
            with open(file1_path, 'wb') as f:
                f.write(b"console.log('test');")
            
            file2_path = os.path.join(temp_dir, "node_modules", "package1", "package.json")
            with open(file2_path, 'wb') as f:
                f.write(b'{"name": "package1"}')
            
            # Collect files
            result = self.docker_utils._collect_files(temp_dir, "npm")
            
            # Verify results
            self.assertEqual(len(result), 2)
            
            # Sort for consistent testing
            result.sort(key=lambda x: x[0])
            
            self.assertEqual(result[0][0], "node_modules/package1/index.js")
            self.assertEqual(result[0][1], b"console.log('test');")
            
            self.assertEqual(result[1][0], "node_modules/package1/package.json")
            self.assertEqual(result[1][1], b'{"name": "package1"}')
    
    def test_collect_files_missing_directory(self):
        """Test file collection when install directory doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Don't create node_modules directory
            result = self.docker_utils._collect_files(temp_dir, "npm")
            
            # Should return empty list
            self.assertEqual(result, [])


if __name__ == '__main__':
    unittest.main()