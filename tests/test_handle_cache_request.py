import pytest
from unittest.mock import Mock, MagicMock, patch, PropertyMock
import tempfile
import os

from application.handle_cache_request import HandleCacheRequest
from application.dtos import CacheRequest, CacheResponse, FileData, InstallationResult
from domain.dependency_set import DependencySet, DependencyFile
from domain.installer import DependencyInstaller
from infrastructure.file_system_cache_repository import FileSystemCacheRepository
from infrastructure.docker_utils import DockerUtils


class TestHandleCacheRequest:
    """Test cases for HandleCacheRequest orchestration."""
    
    @pytest.fixture
    def mock_cache_repository(self):
        """Create a mock cache repository."""
        return Mock(spec=FileSystemCacheRepository)
    
    @pytest.fixture
    def mock_installer_factory(self):
        """Create a mock installer factory."""
        return Mock()
    
    @pytest.fixture
    def mock_docker_utils(self):
        """Create a mock Docker utils."""
        mock = Mock(spec=DockerUtils)
        mock.is_available = Mock(return_value=True)
        return mock
    
    @pytest.fixture
    def supported_versions(self):
        """Create supported versions configuration."""
        return {
            'npm': [
                {'runtime': '14.17.0', 'package_manager': '6.14.13'},
                {'runtime': '16.13.0', 'package_manager': '8.1.0'}
            ]
        }
    
    @pytest.fixture
    def handler(self, mock_cache_repository, mock_installer_factory, mock_docker_utils, supported_versions):
        """Create a HandleCacheRequest instance."""
        return HandleCacheRequest(
            cache_repository=mock_cache_repository,
            installer_factory=mock_installer_factory,
            docker_utils=mock_docker_utils,
            supported_versions=supported_versions,
            use_docker_on_version_mismatch=True
        )
    
    @patch('application.handle_cache_request.DependencySet')
    def test_cache_hit(self, mock_dep_set_class, handler, mock_cache_repository, mock_installer_factory):
        """Test handling a cache hit."""
        # Arrange
        request = CacheRequest(
            manager='npm',
            versions={'runtime': '14.17.0', 'package_manager': '6.14.13'},
            lockfile_content=b'lockfile content',
            manifest_content=b'manifest content'
        )
        
        expected_hash = 'abc123'
        mock_cache_repository.has_bundle.return_value = True
        
        # Mock installer for getting file names
        mock_installer = Mock()
        mock_installer.lockfile_name = 'package-lock.json'
        mock_installer.manifest_name = 'package.json'
        mock_installer_factory.create_installer.return_value = mock_installer
        
        # Mock DependencySet
        mock_dep_set = Mock()
        mock_dep_set.calculate_bundle_hash.return_value = expected_hash
        mock_dep_set_class.return_value = mock_dep_set
        
        # Act
        response = handler.handle(request)
        
        # Assert
        assert response.bundle_hash == expected_hash
        assert response.is_cache_hit is True
        assert response.download_url == f'/download/{expected_hash}.zip'
        mock_cache_repository.has_bundle.assert_called_once_with(expected_hash)
    
    @patch('application.handle_cache_request.DependencySet')
    def test_cache_miss_with_native_install(self, mock_dep_set_class, handler, 
                                          mock_cache_repository, mock_installer_factory):
        """Test handling a cache miss with native installation."""
        # Arrange
        request = CacheRequest(
            manager='npm',
            versions={'runtime': '14.17.0', 'package_manager': '6.14.13'},
            lockfile_content=b'lockfile content',
            manifest_content=b'manifest content'
        )
        
        expected_hash = 'abc123'
        mock_cache_repository.has_bundle.return_value = False
        
        # Mock installer
        mock_installer = Mock(spec=DependencyInstaller)
        mock_installer.lockfile_name = 'package-lock.json'
        mock_installer.manifest_name = 'package.json'
        mock_installer.output_folder = 'node_modules'
        mock_installer.install.return_value = InstallationResult(
            success=True,
            files=[
                FileData('foo/index.js', b'console.log("foo")'),
                FileData('bar/index.js', b'console.log("bar")')
            ],
            error_message=None
        )
        mock_installer_factory.create_installer.return_value = mock_installer
        
        # Mock DependencySet - need two instances
        mock_dep_set_for_hash = Mock()
        mock_dep_set_for_hash.calculate_bundle_hash.return_value = expected_hash
        
        mock_dep_set_for_store = Mock()
        mock_dep_set_for_store.files = [
            DependencyFile('foo/index.js', b'console.log("foo")'),
            DependencyFile('bar/index.js', b'console.log("bar")')
        ]
        mock_dep_set_for_store.to_index_dict.return_value = {'files': {}}
        
        # Return different instances for different calls
        mock_dep_set_class.side_effect = [mock_dep_set_for_hash, mock_dep_set_for_store]
        
        # Act
        response = handler.handle(request)
        
        # Assert
        assert response.bundle_hash == expected_hash
        assert response.is_cache_hit is False
        assert response.download_url == f'/download/{expected_hash}.zip'
        
        # Verify installer was used
        mock_installer_factory.create_installer.assert_called_with(
            'npm', {'runtime': '14.17.0', 'package_manager': '6.14.13'}
        )
        mock_installer.install.assert_called_once()
        
        # Verify files were stored
        mock_cache_repository.store_dependency_set.assert_called_once()
        mock_cache_repository.generate_bundle_zip.assert_called_once_with(expected_hash)
    
    @patch('application.handle_cache_request.DependencySet')
    def test_cache_miss_with_docker_install(self, mock_dep_set_class, handler, mock_cache_repository, 
                                          mock_installer_factory, mock_docker_utils):
        """Test handling a cache miss with Docker installation due to version mismatch."""
        # Arrange
        request = CacheRequest(
            manager='npm',
            versions={'runtime': '18.0.0', 'package_manager': '9.0.0'},  # Unsupported version
            lockfile_content=b'lockfile content',
            manifest_content=b'manifest content'
        )
        
        expected_hash = 'xyz789'
        mock_cache_repository.has_bundle.return_value = False
        
        # Mock installer for file names
        mock_installer = Mock()
        mock_installer.lockfile_name = 'package-lock.json'
        mock_installer.manifest_name = 'package.json'
        mock_installer_factory.create_installer.return_value = mock_installer
        
        # Mock Docker installation
        mock_docker_utils.is_available.return_value = True
        mock_docker_utils.install_with_docker.return_value = InstallationResult(
            success=True,
            files=[
                FileData('foo/index.js', b'console.log("foo")'),
                FileData('bar/index.js', b'console.log("bar")')
            ],
            error_message=None
        )
        
        # Mock DependencySet
        mock_dep_set_for_hash = Mock()
        mock_dep_set_for_hash.calculate_bundle_hash.return_value = expected_hash
        
        mock_dep_set_for_store = Mock()
        mock_dep_set_for_store.files = []
        mock_dep_set_for_store.to_index_dict.return_value = {'files': {}}
        
        mock_dep_set_class.side_effect = [mock_dep_set_for_hash, mock_dep_set_for_store]
        
        # Act
        response = handler.handle(request)
        
        # Assert
        assert response.bundle_hash == expected_hash
        assert response.is_cache_hit is False
        
        # Verify Docker was used
        mock_docker_utils.install_with_docker.assert_called_once()
        
        # Verify files were stored
        mock_cache_repository.store_dependency_set.assert_called_once()
        mock_cache_repository.generate_bundle_zip.assert_called_once_with(expected_hash)
    
    def test_installation_failure(self, handler, mock_cache_repository, mock_installer_factory):
        """Test handling installation failure."""
        # Arrange
        request = CacheRequest(
            manager='npm',
            versions={'runtime': '14.17.0', 'package_manager': '6.14.13'},
            lockfile_content=b'lockfile content',
            manifest_content=b'manifest content'
        )
        
        mock_cache_repository.has_bundle.return_value = False
        
        # Mock installer for file names
        mock_installer_for_hash = Mock()
        mock_installer_for_hash.lockfile_name = 'package-lock.json'
        mock_installer_for_hash.manifest_name = 'package.json'
        
        # Mock failed installation
        mock_installer_for_install = Mock(spec=DependencyInstaller)
        mock_installer_for_install.lockfile_name = 'package-lock.json'
        mock_installer_for_install.manifest_name = 'package.json'
        mock_installer_for_install.install.return_value = InstallationResult(
            success=False,
            files=[],
            error_message='Installation failed: npm error'
        )
        
        # Return different mocks for different calls
        mock_installer_factory.create_installer.side_effect = [
            mock_installer_for_hash,  # For hash calculation
            mock_installer_for_install  # For actual installation
        ]
        
        # Act & Assert
        with pytest.raises(RuntimeError, match='Installation failed: npm error'):
            handler.handle(request)
    
    def test_unsupported_manager(self, handler, mock_cache_repository, mock_installer_factory):
        """Test handling unsupported package manager."""
        # Arrange
        request = CacheRequest(
            manager='unknown_manager',
            versions={'runtime': '1.0.0'},
            lockfile_content=b'lockfile content',
            manifest_content=b'manifest content'
        )
        
        mock_cache_repository.has_bundle.return_value = False
        
        # Mock installer factory to raise exception for unknown manager
        mock_installer_factory.create_installer.side_effect = ValueError("Unsupported manager: unknown_manager")
        
        # Act & Assert
        with pytest.raises(ValueError, match='Unsupported manager'):
            handler.handle(request)
    
    def test_docker_not_available_for_unsupported_version(self, handler, mock_cache_repository, 
                                                         mock_docker_utils, mock_installer_factory):
        """Test handling unsupported version when Docker is not available."""
        # Arrange
        request = CacheRequest(
            manager='npm',
            versions={'runtime': '18.0.0', 'package_manager': '9.0.0'},  # Unsupported version
            lockfile_content=b'lockfile content',
            manifest_content=b'manifest content'
        )
        
        mock_cache_repository.has_bundle.return_value = False
        mock_docker_utils.is_available.return_value = False
        
        # Mock installer for file names
        mock_installer = Mock()
        mock_installer.lockfile_name = 'package-lock.json'
        mock_installer.manifest_name = 'package.json'
        mock_installer_factory.create_installer.return_value = mock_installer
        
        # Act & Assert
        with pytest.raises(ValueError, match='Unsupported npm version'):
            handler.handle(request)
    
    def test_version_support_check(self, handler):
        """Test version support checking."""
        # Supported version
        assert handler._is_version_supported('npm', {'runtime': '14.17.0', 'package_manager': '6.14.13'})
        
        # Unsupported version
        assert not handler._is_version_supported('npm', {'runtime': '18.0.0', 'package_manager': '9.0.0'})
        
        # Unknown manager
        assert not handler._is_version_supported('unknown', {'runtime': '1.0.0'})
    
    def test_version_support_with_api_format(self, handler):
        """Test version support with actual API request format (node/npm keys)."""
        # Test npm with node/npm keys (as sent by API)
        assert handler._is_version_supported('npm', {'node': '14.17.0', 'npm': '6.14.13'})
        assert not handler._is_version_supported('npm', {'node': '18.0.0', 'npm': '9.0.0'})
        
        # Test yarn with node/yarn keys (need to add yarn to supported versions first)
        handler.supported_versions['yarn'] = [
            {'runtime': '14.17.0', 'package_manager': '1.22.0'}
        ]
        assert handler._is_version_supported('yarn', {'node': '14.17.0', 'yarn': '1.22.0'})
        
        # Test composer with php key
        handler.supported_versions['composer'] = [{'runtime': '8.1.0'}]
        assert handler._is_version_supported('composer', {'php': '8.1.0'})
        assert not handler._is_version_supported('composer', {'php': '7.0.0'})
    
    def test_version_normalization_edge_cases(self, handler):
        """Test edge cases in version normalization."""
        # Mixed format (should still work)
        assert handler._is_version_supported('npm', {'node': '14.17.0', 'package_manager': '6.14.13'})
        
        # Missing version info
        assert not handler._is_version_supported('npm', {'node': '14.17.0'})  # Missing npm version
        assert not handler._is_version_supported('npm', {})  # Empty versions
        
        # Extra fields should be ignored
        assert handler._is_version_supported('npm', {
            'node': '14.17.0', 
            'npm': '6.14.13',
            'extra': 'ignored'
        })
    
    def test_determine_installation_method_native(self, handler):
        """Test determining native installation method."""
        method = handler._determine_installation_method(
            'npm', 
            {'runtime': '14.17.0', 'package_manager': '6.14.13'}
        )
        assert method == 'native'
    
    def test_determine_installation_method_docker(self, handler, mock_docker_utils):
        """Test determining Docker installation method."""
        mock_docker_utils.is_available.return_value = True
        
        method = handler._determine_installation_method(
            'npm', 
            {'runtime': '18.0.0', 'package_manager': '9.0.0'}  # Unsupported
        )
        assert method == 'docker'
    
    def test_determine_installation_method_error(self, handler, mock_docker_utils):
        """Test error when no installation method is available."""
        handler.use_docker_on_version_mismatch = False
        
        with pytest.raises(ValueError, match='Unsupported npm version'):
            handler._determine_installation_method(
                'npm', 
                {'runtime': '18.0.0', 'package_manager': '9.0.0'}  # Unsupported
            )
    
    @patch('application.handle_cache_request.DependencySet')
    def test_cache_request_with_api_format_versions(self, mock_dep_set_class, handler, 
                                                   mock_cache_repository, mock_installer_factory):
        """Test handling cache request with API format versions (node/npm keys)."""
        # Arrange
        request = CacheRequest(
            manager='npm',
            versions={'node': '14.17.0', 'npm': '6.14.13'},  # API format
            lockfile_content=b'lockfile content',
            manifest_content=b'manifest content'
        )
        
        expected_hash = 'api-format-hash'
        mock_cache_repository.has_bundle.return_value = False
        
        # Mock installer
        mock_installer = Mock(spec=DependencyInstaller)
        mock_installer.lockfile_name = 'package-lock.json'
        mock_installer.manifest_name = 'package.json'
        mock_installer.output_folder = 'node_modules'
        mock_installer.install.return_value = InstallationResult(
            success=True,
            files=[FileData('test/file.js', b'content')],
            error_message=None
        )
        mock_installer_factory.create_installer.return_value = mock_installer
        
        # Mock DependencySet
        mock_dep_set = Mock()
        mock_dep_set.calculate_bundle_hash.return_value = expected_hash
        mock_dep_set_class.return_value = mock_dep_set
        
        # Act
        response = handler.handle(request)
        
        # Assert
        assert response.bundle_hash == expected_hash
        assert response.is_cache_hit is False
        
        # Verify the installer was called with the original API format versions
        mock_installer_factory.create_installer.assert_called_with(
            'npm', {'node': '14.17.0', 'npm': '6.14.13'}
        )
    
    def test_determine_installation_method_with_api_format(self, handler, mock_docker_utils):
        """Test installation method determination with API format versions."""
        # Native installation with API format
        method = handler._determine_installation_method(
            'npm', 
            {'node': '14.17.0', 'npm': '6.14.13'}  # API format
        )
        assert method == 'native'
        
        # Docker required with API format (handler has use_docker_on_version_mismatch=True)
        mock_docker_utils.is_available.return_value = True
        method = handler._determine_installation_method(
            'npm', 
            {'node': '18.0.0', 'npm': '9.0.0'}  # Unsupported in API format
        )
        assert method == 'docker'
        
        # Test error when Docker is not available
        handler.use_docker_on_version_mismatch = False
        with pytest.raises(ValueError, match='Unsupported npm version'):
            handler._determine_installation_method(
                'npm', 
                {'node': '18.0.0', 'npm': '9.0.0'}  # Unsupported in API format
            )