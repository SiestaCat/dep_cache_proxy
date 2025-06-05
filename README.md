# DepCacheProxy Server

A high-performance dependency caching proxy server that stores and serves cached dependency installations (npm, composer, etc.) to avoid redundant installations. Part of the DepCacheProxy system.

## Overview

DepCacheProxy Server implements a content-addressable storage system for dependency files, providing:

- **File-level deduplication**: Each file is stored once based on content hash
- **On-demand ZIP generation**: Bundles are created from individual file blobs
- **Version management**: Validates package manager versions and supports Docker fallback
- **RESTful API**: Simple HTTP interface for cache operations
- **High performance**: Block-based hashing, concurrent request handling

## Features

- ✅ Content-addressable blob storage for individual files
- ✅ JSON indexes mapping file paths to content hashes
- ✅ Automatic ZIP bundle generation from stored blobs
- ✅ Support for npm and composer (extensible to other package managers)
- ✅ Docker integration for handling unsupported package manager versions
- ✅ API key authentication with Bearer tokens
- ✅ Thread-safe concurrent request handling
- ✅ Comprehensive test coverage (86 tests)

## Architecture

The server follows Domain-Driven Design (DDD) principles with clear separation of concerns:

```
dep_cache_proxy_server/
├── domain/           # Core business logic and entities
├── infrastructure/   # External service implementations
├── application/      # Use case orchestration
├── interfaces/       # HTTP API layer
└── cache/           # Cache storage directory
    ├── objects/     # Content-addressed file blobs
    ├── indexes/     # JSON path-to-hash mappings
    └── bundles/     # Generated ZIP files
```

## Installation

### Prerequisites

- Python 3.8+
- pip
- (Optional) Docker for handling unsupported package manager versions

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd dep_cache_proxy_server
```

2. Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

Or install manually:
```bash
pip install fastapi uvicorn pydantic httpx pytest
```

## Usage

### Starting the Server

Basic usage:
```bash
python main.py 8080 \
  --cache_dir=./cache \
  --supported-versions-node=14.20.0:6.14.13,16.15.0:8.5.0 \
  --supported-versions-php=8.1.0,7.4.0 \
  --is_public
```

With authentication:
```bash
python main.py 8080 \
  --cache_dir=./cache \
  --supported-versions-node=14.20.0:6.14.13,16.15.0:8.5.0 \
  --supported-versions-php=8.1.0 \
  --api-keys=secret-key-1,secret-key-2
```

With Docker fallback for unsupported versions:
```bash
python main.py 8080 \
  --cache_dir=./cache \
  --supported-versions-node=14.20.0:6.14.13 \
  --supported-versions-php=8.1.0 \
  --use-docker-on-version-mismatch \
  --api-keys=secret-key-1
```

### Server Options

- `<port>`: HTTP port to listen on (required)
- `--cache_dir`: Base directory for cache storage (required)
- `--supported-versions-node`: Comma-separated list of `node:npm` version pairs
- `--supported-versions-php`: Comma-separated list of PHP versions
- `--use-docker-on-version-mismatch`: Use Docker when requested version is unsupported
- `--is_public`: Run as public server (no API key required)
- `--api-keys`: Comma-separated list of valid API keys (required unless `--is_public`)

## API Documentation

### POST /v1/cache

Request caching of dependencies. Returns download URL for the cached bundle.

**Request Headers:**
- `Authorization: Bearer <api-key>` (required unless server is public)
- `Content-Type: application/json`

**Request Body:**
```json
{
  "manager": "npm",
  "hash": "calculated-bundle-hash",
  "files": {
    "package.json": "<base64-encoded-content>",
    "package-lock.json": "<base64-encoded-content>"
  },
  "versions": {
    "node": "14.20.0",
    "npm": "6.14.13"
  }
}
```

**Response (200 OK):**
```json
{
  "download_url": "http://server:8080/download/<bundle-hash>.zip",
  "cache_hit": true
}
```

**Error Responses:**
- `400 Bad Request`: Invalid request or unsupported version
- `401 Unauthorized`: Missing or invalid API key
- `500 Internal Server Error`: Server processing error

### GET /download/{bundle_hash}.zip

Download a cached dependency bundle.

**Response:**
- `200 OK`: ZIP file stream
- `404 Not Found`: Bundle not found

### GET /health

Health check endpoint.

**Response (200 OK):**
```json
{
  "status": "healthy"
}
```

## Client Integration

The server is designed to work with the DepCacheProxy client. Example client usage:

```bash
dep_cache_proxy_client https://server:8080 npm \
  --apikey=MY_API_KEY \
  --files=package.json,package-lock.json \
  --node-version=14.20.0 \
  --npm-version=6.14.13
```

The client will:
1. Calculate bundle hash locally
2. Send cache request to server
3. Download and extract the ZIP bundle

## Cache Storage Structure

```
cache/
├── objects/          # Individual file blobs
│   ├── aa/bb/       # Two-level directory structure
│   │   └── aabb...  # Content-addressed file
│   └── cc/dd/
│       └── ccdd...
├── indexes/          # Bundle indexes
│   └── <hash>.<manager>.<version>.index
└── bundles/          # Generated ZIP files
    └── <bundle-hash>.zip
```

## Development

### Running Tests

Run all tests:
```bash
python -m pytest tests/ -v
```

Run specific test categories:
```bash
# Unit tests only
python -m pytest tests/test_*.py -v

# Domain tests
python -m pytest tests/domain/ -v

# End-to-end tests
python -m pytest tests/test_e2e_docker.py -v
```

### Test Coverage

The project includes comprehensive test coverage:
- Unit tests for all domain models and utilities
- Integration tests for repositories and handlers  
- API endpoint tests with authentication
- End-to-end tests simulating real workflows

### Adding New Package Managers

To add support for a new package manager:

1. Create a new installer in `domain/installer.py`:
```python
class YarnInstaller(DependencyInstaller):
    @property
    def output_folder_name(self) -> str:
        return "node_modules"
    
    def install(self, work_dir: Path) -> InstallationResult:
        # Implementation
```

2. Update the `InstallerFactory` to include the new manager

3. Add version support in command-line arguments

4. Update Docker utilities if needed

## Security Considerations

- All package installations use `--ignore-scripts` or `--no-scripts` flags
- API keys are compared using timing-safe comparison
- Input validation for all manager names and versions
- Docker commands are properly parameterized to prevent injection
- File paths are sanitized and restricted to cache directory

## Performance Optimization

- **File deduplication**: Same files are stored only once
- **Block-based hashing**: 8KB blocks for efficient processing
- **Concurrent handling**: Thread-safe operations with proper locking
- **On-demand generation**: ZIP files created only when needed
- **Streaming downloads**: Large files streamed efficiently

## Deployment

### Production Deployment

1. Use a process manager like systemd or supervisor:
```bash
# /etc/systemd/system/depcacheproxy.service
[Unit]
Description=DepCacheProxy Server
After=network.target

[Service]
Type=simple
User=depcache
WorkingDirectory=/opt/depcacheproxy
ExecStart=/opt/depcacheproxy/venv/bin/python main.py 8080 --cache_dir=/var/cache/depcacheproxy ...
Restart=always

[Install]
WantedBy=multi-user.target
```

2. Run behind a reverse proxy (nginx/Apache) for TLS termination

3. Set up regular cache cleanup:
```bash
# Cron job to clean old bundles
0 2 * * * find /var/cache/depcacheproxy/bundles -mtime +30 -delete
```

### Docker Deployment

Create a Dockerfile:
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080
CMD ["python", "main.py", "8080", "--cache_dir=/cache"]
```

Run with Docker:
```bash
docker run -d \
  -p 8080:8080 \
  -v depcache:/cache \
  -e API_KEYS=secret-key-1,secret-key-2 \
  depcacheproxy-server
```

## Monitoring

The server provides cache statistics through the repository:
- Total cached bundles
- Total stored blobs
- Total indexes
- Cache directory sizes

## Troubleshooting

### Common Issues

1. **"Unsupported version" errors**
   - Add the version to `--supported-versions-*` flags
   - Or enable `--use-docker-on-version-mismatch`

2. **Permission errors**
   - Ensure the process has write access to cache directory
   - Check Docker socket permissions if using Docker

3. **Large cache size**
   - Implement regular cleanup of old bundles
   - Monitor blob deduplication effectiveness

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

[Specify your license here]

## Related Projects

- [dep_cache_proxy_client](https://github.com/yourusername/dep_cache_proxy_client) - Client CLI for DepCacheProxy