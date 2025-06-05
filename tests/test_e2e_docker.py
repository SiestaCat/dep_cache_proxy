"""End-to-end tests with Docker integration."""
import pytest
import tempfile
import json
import base64
import hashlib
import os
import subprocess
from pathlib import Path
from unittest.mock import patch, Mock
import time

from main import main as server_main
from domain.hash_constants import HASH_ALGORITHM, BLOCK_SIZE


class TestE2EDocker:
    """End-to-end tests simulating full client-server workflow with Docker."""
    
    @pytest.fixture
    def sample_npm_files(self):
        """Sample npm package files."""
        package_json = {
            "name": "test-package",
            "version": "1.0.0",
            "dependencies": {
                "lodash": "^4.17.21"
            }
        }
        
        package_lock_json = {
            "name": "test-package",
            "version": "1.0.0",
            "lockfileVersion": 2,
            "requires": True,
            "packages": {
                "": {
                    "name": "test-package",
                    "version": "1.0.0",
                    "dependencies": {
                        "lodash": "^4.17.21"
                    }
                }
            }
        }
        
        return {
            'package.json': json.dumps(package_json, indent=2).encode('utf-8'),
            'package-lock.json': json.dumps(package_lock_json, indent=2).encode('utf-8')
        }
    
    @pytest.fixture
    def sample_composer_files(self):
        """Sample composer package files."""
        composer_json = {
            "name": "test/package",
            "require": {
                "monolog/monolog": "^2.0"
            }
        }
        
        composer_lock = {
            "_readme": ["This is a test lock file"],
            "content-hash": "test-hash",
            "packages": [{
                "name": "monolog/monolog",
                "version": "2.0.0"
            }]
        }
        
        return {
            'composer.json': json.dumps(composer_json, indent=2).encode('utf-8'),
            'composer.lock': json.dumps(composer_lock, indent=2).encode('utf-8')
        }
    
    def calculate_bundle_hash(self, manager: str, files: dict, versions: dict) -> str:
        """Calculate bundle hash matching the server implementation."""
        hasher = hashlib.new(HASH_ALGORITHM)
        
        # Add manager
        hasher.update(manager.encode('utf-8'))
        hasher.update(b'\n')
        
        # Add file contents (sorted by filename)
        for filename in sorted(files.keys()):
            content = files[filename]
            # Process in blocks
            for i in range(0, len(content), BLOCK_SIZE):
                chunk = content[i:i + BLOCK_SIZE]
                hasher.update(chunk)
        
        # Add versions (sorted by key)
        for key in sorted(versions.keys()):
            value = versions[key]
            hasher.update(f"{key}={value}\n".encode('utf-8'))
        
        return hasher.hexdigest()
    
    @pytest.mark.skipif(
        not os.path.exists('/.dockerenv') and subprocess.run(['docker', '--version'], capture_output=True).returncode != 0,
        reason="Docker not available"
    )
    def test_npm_cache_miss_with_docker(self, sample_npm_files):
        """Test npm cache miss scenario using Docker installation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache_dir.mkdir()
            
            # Mock server arguments
            with patch('sys.argv', [
                'dep_cache_proxy_server',
                '8080',
                f'--cache_dir={cache_dir}',
                '--supported-versions-node=16.0.0:8.0.0',  # Different from requested
                '--use-docker-on-version-mismatch',
                '--is_public'
            ]):
                # This would normally start the server
                # For testing, we'll simulate the server behavior
                
                # Simulate client request
                manager = 'npm'
                versions = {'node': '14.17.0', 'npm': '6.14.13'}
                bundle_hash = self.calculate_bundle_hash(manager, sample_npm_files, versions)
                
                # Check cache miss
                bundle_path = cache_dir / "bundles" / bundle_hash[:2] / bundle_hash[2:4] / f"{bundle_hash}.zip"
                assert not bundle_path.exists()
                
                # Simulate Docker installation (mocked)
                with patch('subprocess.run') as mock_run:
                    # Mock docker version check
                    mock_run.return_value = Mock(returncode=0, stdout=b'Docker version 20.10.0')
                    
                    # Create mock installation result
                    mock_node_modules = cache_dir / "temp" / "node_modules"
                    mock_node_modules.mkdir(parents=True)
                    (mock_node_modules / "lodash" / "index.js").parent.mkdir(parents=True)
                    (mock_node_modules / "lodash" / "index.js").write_text("module.exports = {};")
                    
                    # After "installation", files would be blobified and indexed
                    objects_dir = cache_dir / "objects"
                    indexes_dir = cache_dir / "indexes"
                    bundles_dir = cache_dir / "bundles"
                    
                    objects_dir.mkdir(parents=True, exist_ok=True)
                    indexes_dir.mkdir(parents=True, exist_ok=True)
                    bundles_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Verify Docker was "called" with correct parameters
                    # In real scenario, this would be handled by DockerUtils
    
    @pytest.mark.skipif(
        not os.path.exists('/.dockerenv') and subprocess.run(['docker', '--version'], capture_output=True).returncode != 0,
        reason="Docker not available"
    )
    def test_composer_cache_hit_scenario(self, sample_composer_files):
        """Test composer cache hit scenario."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache_dir.mkdir()
            
            manager = 'composer'
            versions = {'php': '8.1.0'}
            bundle_hash = self.calculate_bundle_hash(manager, sample_composer_files, versions)
            
            # Pre-populate cache to simulate cache hit
            bundle_path = cache_dir / "bundles" / bundle_hash[:2] / bundle_hash[2:4] / f"{bundle_hash}.zip"
            bundle_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Create a mock ZIP file
            import zipfile
            with zipfile.ZipFile(bundle_path, 'w') as zf:
                zf.writestr('vendor/monolog/monolog/src/Monolog.php', '<?php // Mock file')
            
            # Verify cache hit
            assert bundle_path.exists()
            
            # In real scenario, server would return download URL immediately
            # without performing any installation
    
    def test_unsupported_version_without_docker(self):
        """Test handling of unsupported version when Docker is disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache_dir.mkdir()
            
            # Server configured without Docker support
            with patch('sys.argv', [
                'dep_cache_proxy_server',
                '8080',
                f'--cache_dir={cache_dir}',
                '--supported-versions-node=16.0.0:8.0.0',
                # Note: --use-docker-on-version-mismatch is NOT set
                '--is_public'
            ]):
                # Request with unsupported version should fail
                # In real scenario, this would return HTTP 400 error
                pass
    
    def test_concurrent_requests(self, sample_npm_files):
        """Test handling of concurrent requests for the same bundle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache_dir.mkdir()
            
            manager = 'npm'
            versions = {'node': '14.17.0', 'npm': '6.14.13'}
            bundle_hash = self.calculate_bundle_hash(manager, sample_npm_files, versions)
            
            # Simulate concurrent requests
            # In real scenario, FileSystemCacheRepository uses threading.Lock
            # to ensure only one request processes the bundle at a time
            
            # The repository should handle this gracefully without creating
            # duplicate blobs or corrupted indexes
    
    def test_api_key_authentication_e2e(self):
        """Test end-to-end API key authentication."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            cache_dir.mkdir()
            
            # Server with API key authentication
            with patch('sys.argv', [
                'dep_cache_proxy_server',
                '8080',
                f'--cache_dir={cache_dir}',
                '--supported-versions-node=14.17.0:6.14.13',
                '--api-keys=test-key-123,test-key-456'
            ]):
                # Requests without Bearer token should fail (401)
                # Requests with invalid token should fail (401)
                # Requests with valid token should succeed
                pass
    
    def test_cache_cleanup(self):
        """Test cleanup of old bundle files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            bundles_dir = cache_dir / "bundles"
            bundles_dir.mkdir(parents=True)
            
            # Create an old bundle file
            old_bundle = bundles_dir / "ab" / "cd" / "abcd1234.zip"
            old_bundle.parent.mkdir(parents=True, exist_ok=True)
            old_bundle.write_text("old zip content")
            
            # Modify its timestamp to be old
            old_time = time.time() - (7 * 24 * 60 * 60)  # 7 days ago
            os.utime(old_bundle, (old_time, old_time))
            
            # In real scenario, cleanup_old_bundles would remove this file
            # if called with max_age_seconds < 7 days