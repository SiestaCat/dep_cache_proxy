import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os
import json
import base64
from io import BytesIO

from interfaces.api import app, initialize_app, Config
from application.dtos import CacheResponse, InstallationResult, FileData


class TestAPI:
    """Test cases for API endpoints."""
    
    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def test_app(self, temp_cache_dir):
        """Create a test FastAPI app instance."""
        # Initialize app with test configuration
        initialize_app(
            cache_dir=temp_cache_dir,
            supported_versions={
                'npm': [
                    {'runtime': '14.17.0', 'package_manager': '6.14.13'},
                    {'runtime': '16.13.0', 'package_manager': '8.1.0'}
                ]
            },
            use_docker_on_version_mismatch=False,
            is_public=True,  # Public mode for easier testing
            api_keys=None,
            base_url='http://localhost:8000'
        )
        return app
    
    @pytest.fixture
    def client(self, test_app):
        """Create a test client with lifespan events."""
        # TestClient handles lifespan events automatically
        with TestClient(test_app) as client:
            yield client
    
    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}
    
    @patch('interfaces.api.HandleCacheRequest')
    def test_cache_dependencies_success(self, mock_handler_class, client):
        """Test successful cache request."""
        # Arrange
        mock_handler = Mock()
        mock_handler.handle.return_value = CacheResponse(
            bundle_hash='abc123',
            download_url='/download/abc123.zip',
            is_cache_hit=True
        )
        mock_handler_class.return_value = mock_handler
        
        # Create multipart form data with file[] array
        files = [
            ('file', ('package-lock.json', BytesIO(b'lockfile content'), 'application/json')),
            ('file', ('package.json', BytesIO(b'manifest content'), 'application/json'))
        ]
        data = {
            'manager': 'npm',
            'hash': 'abc123',
            'versions': json.dumps({'node': '14.17.0', 'npm': '6.14.13'})
        }
        
        # Act
        response = client.post("/v1/cache", data=data, files=files)
        
        # Assert
        assert response.status_code == 200
        response_data = response.json()
        assert response_data['download_url'] == 'http://localhost:8000/download/abc123.zip'
        assert response_data['cache_hit'] is True
    
    def test_cache_dependencies_validation_error(self, client):
        """Test cache request with validation error."""
        # Create multipart form data with invalid manager
        files = [
            ('file', ('package-lock.json', BytesIO(b'lockfile content'), 'application/json')),
            ('file', ('package.json', BytesIO(b'manifest content'), 'application/json'))
        ]
        data = {
            'manager': 'invalid_manager',
            'hash': 'invalid_hash',
            'versions': json.dumps({'runtime': '1.0.0'})
        }
        
        # Act
        response = client.post("/v1/cache", data=data, files=files)
        
        # Assert
        assert response.status_code == 400
        assert 'Unsupported manager' in response.json()['detail']
    
    @patch('interfaces.api.HandleCacheRequest')
    def test_cache_dependencies_internal_error(self, mock_handler_class, client):
        """Test cache request with internal error."""
        # Arrange
        mock_handler = Mock()
        mock_handler.handle.side_effect = Exception("Internal error")
        mock_handler_class.return_value = mock_handler
        
        # Create multipart form data with file[] array
        files = [
            ('file', ('package-lock.json', BytesIO(b'lockfile content'), 'application/json')),
            ('file', ('package.json', BytesIO(b'manifest content'), 'application/json'))
        ]
        data = {
            'manager': 'npm',
            'hash': 'test_hash',
            'versions': json.dumps({'node': '14.17.0', 'npm': '6.14.13'})
        }
        
        # Act
        response = client.post("/v1/cache", data=data, files=files)
        
        # Assert
        assert response.status_code == 500
        assert 'Internal server error' in response.json()['detail']
    
    def test_cache_dependencies_missing_fields(self, client):
        """Test cache request with missing required fields."""
        # Missing manager
        files = [
            ('file', ('package-lock.json', BytesIO(b'content'), 'application/json')),
            ('file', ('package.json', BytesIO(b'content'), 'application/json'))
        ]
        data = {
            'hash': 'test_hash',
            'versions': json.dumps({'runtime': '14.17.0'})
        }
        response = client.post("/v1/cache", data=data, files=files)
        assert response.status_code == 422
        
        # Missing versions
        files = [
            ('file', ('package-lock.json', BytesIO(b'content'), 'application/json')),
            ('file', ('package.json', BytesIO(b'content'), 'application/json'))
        ]
        data = {
            'manager': 'npm',
            'hash': 'test_hash'
        }
        response = client.post("/v1/cache", data=data, files=files)
        assert response.status_code == 422
    
    def test_download_bundle_success(self, client, temp_cache_dir):
        """Test successful bundle download."""
        # Create a test ZIP file using the same directory structure as the repository
        bundle_hash = 'test123abcdef'  # Need longer hash for directory structure
        bundles_dir = os.path.join(temp_cache_dir, 'bundles', bundle_hash[:2], bundle_hash[2:4])
        os.makedirs(bundles_dir, exist_ok=True)
        
        zip_path = os.path.join(bundles_dir, f'{bundle_hash}.zip')
        with open(zip_path, 'wb') as f:
            f.write(b'PK\x03\x04')  # ZIP file header
        
        # Act
        response = client.get(f"/download/{bundle_hash}.zip")
        
        # Assert
        assert response.status_code == 200
        assert response.headers['content-type'] == 'application/zip'
        assert f'filename={bundle_hash}.zip' in response.headers['content-disposition']
        assert response.content.startswith(b'PK\x03\x04')
    
    def test_download_bundle_not_found(self, client):
        """Test bundle download when file doesn't exist."""
        response = client.get("/download/nonexistent.zip")
        assert response.status_code == 404
        assert response.json()['detail'] == 'Bundle not found'
    
    def test_cache_request_with_real_api_version_format(self, temp_cache_dir):
        """Test cache request with actual API version format (node/npm keys)."""
        # Initialize app with supported versions
        test_app = initialize_app(
            cache_dir=temp_cache_dir,
            supported_versions={
                'npm': [
                    {'runtime': '14.20.0', 'package_manager': '6.14.13'},
                    {'runtime': '16.15.0', 'package_manager': '8.5.0'}
                ]
            },
            is_public=True
        )
        
        # Create a pre-existing bundle to test version validation with cache hit
        bundle_hash = 'a5cb864746fb36608c41186cf3322bcc3357eaa1512daa34a04c55df1bef59f3'
        bundles_dir = os.path.join(temp_cache_dir, 'bundles', bundle_hash[:2], bundle_hash[2:4])
        os.makedirs(bundles_dir, exist_ok=True)
        
        # Create indexes directory 
        indexes_dir = os.path.join(temp_cache_dir, 'indexes', bundle_hash[:2], bundle_hash[2:4])
        os.makedirs(indexes_dir, exist_ok=True)
        
        # Create a dummy ZIP file
        zip_path = os.path.join(bundles_dir, f'{bundle_hash}.zip')
        with open(zip_path, 'wb') as f:
            f.write(b'PK\x03\x04')  # ZIP file header
            
        # Create a dummy index file
        index_path = os.path.join(indexes_dir, f'{bundle_hash}.npm.14.20.0_6.14.13.index')
        with open(index_path, 'w') as f:
            json.dump({'files': {}}, f)
        
        with TestClient(test_app) as client:
            # Test with supported version using API format keys
            files = [
                ('file', ('package-lock.json', BytesIO(b'lockfile content'), 'application/json')),
                ('file', ('package.json', BytesIO(b'{"name": "test"}'), 'application/json'))
            ]
            data = {
                'manager': 'npm',
                'hash': 'a5cb864746fb36608c41186cf3322bcc3357eaa1512daa34a04c55df1bef59f3',
                'versions': json.dumps({
                    'node': '14.20.0',  # Using 'node' instead of 'runtime'
                    'npm': '6.14.13'    # Using 'npm' instead of 'package_manager'
                })
            }
            response = client.post("/v1/cache", data=data, files=files)
            
            # Should succeed with supported version (cache hit)
            assert response.status_code == 200
            response_data = response.json()
            assert 'download_url' in response_data
            assert response_data['cache_hit'] is True  # Should be cache hit since we pre-created the bundle
            
            # Test with unsupported version using API format keys
            files = [
                ('file', ('package-lock.json', BytesIO(b'lockfile content'), 'application/json')),
                ('file', ('package.json', BytesIO(b'{"name": "test"}'), 'application/json'))
            ]
            data = {
                'manager': 'npm',
                'hash': 'test_unsupported_hash',
                'versions': json.dumps({
                    'node': '18.0.0',  # Unsupported version
                    'npm': '9.0.0'     # Unsupported version
                })
            }
            response = client.post("/v1/cache", data=data, files=files)
            
            # Should fail with unsupported version
            assert response.status_code == 400
            assert 'Unsupported npm version' in response.json()['detail']
    
    def test_api_key_authentication(self):
        """Test API key authentication."""
        # Initialize app with API key authentication
        with tempfile.TemporaryDirectory() as tmpdir:
            test_app = initialize_app(
                cache_dir=tmpdir,
                supported_versions={'npm': []},
                is_public=False,
                api_keys=['test-key-123', 'test-key-456']
            )
            
            with TestClient(test_app) as client:
                # Request without API key
                response = client.get("/health")  # Health check doesn't require auth
                assert response.status_code == 200
                
                files = [
                    ('file', ('package-lock.json', BytesIO(b'content'), 'application/json')),
                    ('file', ('package.json', BytesIO(b'content'), 'application/json'))
                ]
                data = {
                    'manager': 'npm',
                    'hash': 'test_hash',
                    'versions': json.dumps({'node': '14.17.0', 'npm': '6.14.13'})
                }
                response = client.post("/v1/cache", data=data, files=files)
                assert response.status_code == 401
                assert 'Authorization' in response.json()['detail']
                
                # Request with invalid API key
                files = [
                    ('file', ('package-lock.json', BytesIO(b'content'), 'application/json')),
                    ('file', ('package.json', BytesIO(b'content'), 'application/json'))
                ]
                data = {
                    'manager': 'npm',
                    'hash': 'test_hash',
                    'versions': json.dumps({'node': '14.17.0', 'npm': '6.14.13'})
                }
                response = client.post("/v1/cache", 
                    headers={'Authorization': 'Bearer invalid-key'},
                    data=data, files=files)
                assert response.status_code == 401
                assert 'Invalid API key' in response.json()['detail']
                
                # Request with valid API key
                with patch('interfaces.api.HandleCacheRequest') as mock_handler_class:
                    mock_handler = Mock()
                    mock_handler.handle.return_value = CacheResponse(
                        bundle_hash='abc123',
                        download_url='/download/abc123.zip',
                        is_cache_hit=True
                    )
                    mock_handler_class.return_value = mock_handler
                    
                    files = [
                        ('file', ('package-lock.json', BytesIO(b'content'), 'application/json')),
                        ('file', ('package.json', BytesIO(b'content'), 'application/json'))
                    ]
                    data = {
                        'manager': 'npm',
                        'hash': 'test_hash',
                        'versions': json.dumps({'node': '14.17.0', 'npm': '6.14.13'})
                    }
                    response = client.post("/v1/cache", 
                        headers={'Authorization': 'Bearer test-key-123'},
                        data=data, files=files)
                    # Should not return 401
                    assert response.status_code == 200
    
    def test_config_initialization(self):
        """Test configuration initialization."""
        config = Config(
            cache_dir='/tmp/cache',
            supported_versions={'npm': []},
            use_docker_on_version_mismatch=True,
            is_public=False,
            api_keys=['key1', 'key2'],
            base_url='https://example.com/'
        )
        
        assert config.cache_dir == '/tmp/cache'
        assert config.supported_versions == {'npm': []}
        assert config.use_docker_on_version_mismatch is True
        assert config.is_public is False
        assert config.api_keys == ['key1', 'key2']
        assert config.base_url == 'https://example.com'  # Trailing slash removed
    
    @patch('interfaces.api.cache_repository')
    def test_server_not_configured_error(self, mock_repo, client):
        """Test error when server is not properly configured."""
        # Simulate uninitialized repository
        mock_repo.__bool__.return_value = False
        
        files = [
            ('file', ('package-lock.json', BytesIO(b'content'), 'application/json')),
            ('file', ('package.json', BytesIO(b'content'), 'application/json'))
        ]
        data = {
            'manager': 'npm',
            'hash': 'test_hash',
            'versions': json.dumps({'node': '14.17.0', 'npm': '6.14.13'})
        }
        response = client.post("/v1/cache", data=data, files=files)
        
        assert response.status_code == 500
        assert 'Server not properly configured' in response.json()['detail']


class TestAPIEdgeCases:
    """Additional edge case tests for API endpoints."""
    
    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def client(self, temp_cache_dir):
        """Create a test client with initialized app."""
        test_app = initialize_app(
            cache_dir=temp_cache_dir,
            supported_versions={
                "npm": [{"runtime": "14.20.0", "package_manager": "6.14.13"}]
            },
            is_public=True
        )
        with TestClient(test_app) as client:
            yield client
    
    def test_cache_request_with_malformed_json_versions(self, client):
        """Test cache request with invalid JSON in versions field."""
        files = [
            ('file', ('package-lock.json', BytesIO(b'lockfile content'), 'application/json')),
            ('file', ('package.json', BytesIO(b'{"name": "test"}'), 'application/json'))
        ]
        data = {
            'manager': 'npm',
            'hash': 'test_hash',
            'versions': 'not-valid-json{{{'
        }
        response = client.post("/v1/cache", data=data, files=files)
        
        assert response.status_code == 400
        assert "Invalid versions JSON" in response.json()["detail"]
    
    def test_cache_request_with_empty_files(self, client):
        """Test cache request with empty file content."""
        files = [
            ('file', ('package-lock.json', BytesIO(b''), 'application/json')),
            ('file', ('package.json', BytesIO(b''), 'application/json'))
        ]
        data = {
            'manager': 'npm',
            'hash': 'test_hash',
            'versions': json.dumps({"node": "14.20.0", "npm": "6.14.13"})
        }
        response = client.post("/v1/cache", data=data, files=files)
        
        # Should reject empty manifest file
        assert response.status_code == 400
        assert "Missing required manifest file" in response.json()["detail"]
    
    @patch('interfaces.api.HandleCacheRequest')
    def test_cache_request_without_lockfile_npm(self, mock_handler_class, client):
        """Test npm cache request without lockfile (should run npm install)."""
        # Arrange
        mock_handler = Mock()
        mock_handler.handle.return_value = CacheResponse(
            bundle_hash='generated123',
            download_url='/download/generated123.zip',
            is_cache_hit=False
        )
        mock_handler_class.return_value = mock_handler
        
        # Only provide manifest file, no lockfile
        files = [
            ('file', ('package.json', BytesIO(b'{"name": "test", "dependencies": {}}'), 'application/json'))
        ]
        data = {
            'manager': 'npm',
            'hash': 'test_hash_no_lock',
            'versions': json.dumps({"node": "14.20.0", "npm": "6.14.13"})
        }
        response = client.post("/v1/cache", data=data, files=files)
        
        # Should succeed - npm install will generate lockfile
        assert response.status_code == 200
        response_data = response.json()
        assert 'download_url' in response_data
        assert response_data['cache_hit'] is False
    
    def test_cache_request_without_lockfile_composer(self, client):
        """Test composer cache request without lockfile (always optional)."""
        with patch('interfaces.api.HandleCacheRequest') as mock_handler_class:
            mock_handler = Mock()
            mock_handler.handle.return_value = CacheResponse(
                bundle_hash='composer123',
                download_url='/download/composer123.zip',
                is_cache_hit=False
            )
            mock_handler_class.return_value = mock_handler
            
            # Only provide composer.json, no composer.lock
            files = [
                ('file', ('composer.json', BytesIO(b'{"require": {"monolog/monolog": "^2.0"}}'), 'application/json'))
            ]
            data = {
                'manager': 'composer',
                'hash': 'composer_hash_no_lock',
                'versions': json.dumps({"php": "8.1.0"})
            }
            response = client.post("/v1/cache", data=data, files=files)
            
            # Should succeed - composer.lock is always optional
            assert response.status_code == 200
    
    def test_cache_request_with_very_long_hash(self, client):
        """Test cache request with extremely long hash value."""
        long_hash = "a" * 1000  # 1000 character hash
        
        files = [
            ('file', ('package-lock.json', BytesIO(b'content'), 'application/json')),
            ('file', ('package.json', BytesIO(b'{"name": "test"}'), 'application/json'))
        ]
        data = {
            'manager': 'npm',
            'hash': long_hash,
            'versions': json.dumps({"node": "14.20.0", "npm": "6.14.13"})
        }
        response = client.post("/v1/cache", data=data, files=files)
        
        # Should handle long hashes (might fail on file system limits)
        assert response.status_code in [200, 400, 500]
    
    def test_cache_request_with_special_characters_in_hash(self, client):
        """Test cache request with special characters in hash."""
        special_hash = "test/../../../etc/passwd"  # Path traversal attempt
        
        files = [
            ('file', ('package-lock.json', BytesIO(b'content'), 'application/json')),
            ('file', ('package.json', BytesIO(b'{"name": "test"}'), 'application/json'))
        ]
        data = {
            'manager': 'npm',
            'hash': special_hash,
            'versions': json.dumps({"node": "14.20.0", "npm": "6.14.13"})
        }
        response = client.post("/v1/cache", data=data, files=files)
        
        # Should reject or sanitize dangerous paths
        assert response.status_code in [400, 500]
    
    def test_download_with_path_traversal(self, client):
        """Test download endpoint with path traversal attempt."""
        response = client.get("/download/../../../etc/passwd.zip")
        assert response.status_code == 404
    
    def test_cache_request_with_unknown_manager(self, client):
        """Test cache request with unknown package manager."""
        files = [
            ('file', ('unknown.lock', BytesIO(b'content'), 'application/json')),
            ('file', ('unknown.json', BytesIO(b'content'), 'application/json'))
        ]
        data = {
            'manager': 'unknown_manager',
            'hash': 'test_hash',
            'versions': json.dumps({"runtime": "1.0.0"})
        }
        response = client.post("/v1/cache", data=data, files=files)
        
        assert response.status_code == 400
        assert "Unsupported manager" in response.json()["detail"]
    
    def test_bearer_token_edge_cases(self):
        """Test various Bearer token formats."""
        test_app = initialize_app(
            cache_dir=tempfile.mkdtemp(),
            supported_versions={"npm": []},
            is_public=False,
            api_keys=["valid-key"]
        )
        
        with TestClient(test_app) as client:
            # Missing Bearer prefix
            response = client.get(
                "/download/test.zip",
                headers={"Authorization": "valid-key"}
            )
            assert response.status_code == 401
            
            # Extra spaces
            response = client.get(
                "/download/test.zip",
                headers={"Authorization": "Bearer  valid-key"}  # Double space
            )
            assert response.status_code == 401
            
            # Case sensitivity
            response = client.get(
                "/download/test.zip",
                headers={"Authorization": "bearer valid-key"}  # lowercase
            )
            assert response.status_code == 401
            
            # Empty bearer token
            response = client.get(
                "/download/test.zip",
                headers={"Authorization": "Bearer "}
            )
            assert response.status_code == 401
