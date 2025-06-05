# Test Enhancement Plan

## Issues Found

### 1. Version Key Format Inconsistencies
- **Issue**: Tests use API format keys (node/npm/php) but some components might expect internal format (runtime/package_manager)
- **Risk**: Tests pass but real-world usage fails

### 2. Missing Test Scenarios

#### test_installer.py
- Missing tests for yarn installer (mentioned in docker_utils and handle_cache_request)
- Missing tests for alternative version key formats (runtime/package_manager)
- Missing tests for subprocess timeout scenarios
- Missing tests for partial file collection failures
- Missing tests for symlink handling in node_modules/vendor
- Missing tests for large file handling
- Missing tests for special characters in file paths

#### test_api.py
- Missing tests for malformed base64 in request
- Missing tests for extremely large file uploads
- Missing tests for concurrent API requests
- Missing tests for rate limiting scenarios
- Missing tests for invalid bundle hash formats
- Missing tests for missing Content-Type headers
- Missing tests for CORS handling

#### test_handle_cache_request.py
- Missing tests for yarn manager
- Missing tests for file permission errors during installation
- Missing tests for disk space issues
- Missing tests for corrupted cache scenarios
- Missing tests for race conditions in cache operations

#### test_file_system_cache_repository.py
- Missing tests for file system permission errors
- Missing tests for corrupted index files
- Missing tests for hash collision scenarios (extremely rare but possible)
- Missing tests for network file system behaviors
- Missing tests for file locking issues

#### test_docker_utils.py
- Missing tests for yarn support
- Missing tests for poetry, pipenv managers
- Missing tests for Docker daemon connection issues
- Missing tests for Docker image pull failures
- Missing tests for container resource limits

#### test_dependency_set.py
- Missing tests for extremely large files (GB+)
- Missing tests for binary file handling
- Missing tests for Unicode file names
- Missing tests for file read errors during hashing

#### test_api_key_validator.py
- Missing tests for malformed Bearer tokens
- Missing tests for extremely long API keys
- Missing tests for timing attack resilience validation

#### test_e2e_docker.py
- Missing tests for real Docker integration (currently mocked)
- Missing tests for version mismatch scenarios
- Missing tests for Docker-in-Docker scenarios

### 3. Real-World Data Issues
- Tests use simple mock data ("lockfile content", "manifest content")
- Real package.json and package-lock.json have complex structures
- Real composer.json and composer.lock have specific formats
- File paths in real projects can be deeply nested with special characters

### 4. Error Message Validation
- Many tests check for error occurrence but not specific error messages
- Error messages might change and break tests unnecessarily

### 5. Security Test Gaps
- No tests for path traversal attempts
- No tests for malicious file content
- No tests for resource exhaustion attacks
- No tests for concurrent request flooding

## Recommendations

1. Create fixture files with real package manager file formats
2. Add parameterized tests for both version key formats
3. Add stress tests for large files and many files
4. Add security-focused test scenarios
5. Add integration tests that use actual package managers (in CI only)
6. Add performance benchmarks to catch regressions
7. Add fuzz testing for input validation