import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os
import json

from interfaces.api import app, initialize_app, Config
from application.dtos import CacheResponse


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
        
        request_data = {
            'manager': 'npm',
            'versions': {'runtime': '14.17.0', 'package_manager': '6.14.13'},
            'lockfile_content': 'lockfile content',
            'manifest_content': 'manifest content'
        }
        
        # Act
        response = client.post("/v1/cache", json=request_data)
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data['bundle_hash'] == 'abc123'
        assert data['download_url'] == 'http://localhost:8000/download/abc123.zip'
        assert data['is_cache_hit'] is True
    
    @patch('interfaces.api.HandleCacheRequest')
    def test_cache_dependencies_validation_error(self, mock_handler_class, client):
        """Test cache request with validation error."""
        # Arrange
        mock_handler = Mock()
        mock_handler.handle.side_effect = ValueError("Invalid manager")
        mock_handler_class.return_value = mock_handler
        
        request_data = {
            'manager': 'invalid_manager',
            'versions': {'runtime': '1.0.0'},
            'lockfile_content': 'lockfile content',
            'manifest_content': 'manifest content'
        }
        
        # Act
        response = client.post("/v1/cache", json=request_data)
        
        # Assert
        assert response.status_code == 400
        assert 'Invalid manager' in response.json()['detail']
    
    @patch('interfaces.api.HandleCacheRequest')
    def test_cache_dependencies_internal_error(self, mock_handler_class, client):
        """Test cache request with internal error."""
        # Arrange
        mock_handler = Mock()
        mock_handler.handle.side_effect = Exception("Internal error")
        mock_handler_class.return_value = mock_handler
        
        request_data = {
            'manager': 'npm',
            'versions': {'runtime': '14.17.0', 'package_manager': '6.14.13'},
            'lockfile_content': 'lockfile content',
            'manifest_content': 'manifest content'
        }
        
        # Act
        response = client.post("/v1/cache", json=request_data)
        
        # Assert
        assert response.status_code == 500
        assert 'Internal server error' in response.json()['detail']
    
    def test_cache_dependencies_missing_fields(self, client):
        """Test cache request with missing required fields."""
        # Missing manager
        response = client.post("/v1/cache", json={
            'versions': {'runtime': '14.17.0'},
            'lockfile_content': 'content',
            'manifest_content': 'content'
        })
        assert response.status_code == 422
        
        # Missing versions
        response = client.post("/v1/cache", json={
            'manager': 'npm',
            'lockfile_content': 'content',
            'manifest_content': 'content'
        })
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
                
                response = client.post("/v1/cache", json={
                    'manager': 'npm',
                    'versions': {'runtime': '14.17.0'},
                    'lockfile_content': 'content',
                    'manifest_content': 'content'
                })
                assert response.status_code == 401
                assert 'API key required' in response.json()['detail']
                
                # Request with invalid API key
                response = client.post("/v1/cache", 
                    headers={'X-Api-Key': 'invalid-key'},
                    json={
                        'manager': 'npm',
                        'versions': {'runtime': '14.17.0'},
                        'lockfile_content': 'content',
                        'manifest_content': 'content'
                    })
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
                    
                    response = client.post("/v1/cache", 
                        headers={'X-Api-Key': 'test-key-123'},
                        json={
                            'manager': 'npm',
                            'versions': {'runtime': '14.17.0'},
                            'lockfile_content': 'content',
                            'manifest_content': 'content'
                        })
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
        
        response = client.post("/v1/cache", json={
            'manager': 'npm',
            'versions': {'runtime': '14.17.0'},
            'lockfile_content': 'content',
            'manifest_content': 'content'
        })
        
        assert response.status_code == 500
        assert 'Server not properly configured' in response.json()['detail']