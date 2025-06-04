# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**This repository contains the server component (`dep_cache_proxy_server`) of the DepCacheProxy system.**

DepCacheProxy is a dependency caching proxy system designed to cache and serve dependency installations (npm, composer, etc.) to avoid redundant installations. The system consists of a client CLI and a server that stores dependencies as individual file blobs with content-addressable storage.

## Current Status

**IMPORTANT**: This project is currently being implemented. The `analysis.md` file contains the complete architectural design and specifications. Implementation started on 2025-01-06.

**⚠️ CRITICAL - Progress Tracking**: 
- **ALWAYS update `CLAUDE.PROGRESS.md` after implementing any feature or making progress**
- **ALWAYS update this `CLAUDE.md` file if the project status changes**
- **NEVER forget to update these files - they are essential for tracking project progress**
- The `CLAUDE.PROGRESS.md` file tracks implementation progress with dates and details

## Architecture

The system follows Domain-Driven Design (DDD) and SOLID principles with these key components:

### Client (`dep_cache_proxy_client`)
- Calculates bundle hash locally using SHA256
- Sends requests to server with dependency files
- Downloads and extracts cached dependencies

### Server (`dep_cache_proxy_server`)
- Stores individual files as blobs in `cache/objects/` (content-addressable)
- Maintains JSON indices mapping relative paths to file hashes
- Generates ZIP files from blobs on demand
- Supports Docker for handling unsupported versions

### Storage Structure
```
cache/
├── objects/     # Individual file blobs (e.g., aa/bb/aabb1232...)
├── indices/     # JSON mappings of paths to hashes
└── bundles/     # Generated ZIP files
```

## Key Design Decisions

1. **File-level deduplication**: Each file is stored once based on content hash
2. **Hash calculation**: Uses SHA256 with 8KB block size, includes manager, versions, and file contents
3. **Version management**: Server validates versions and can use Docker for unsupported versions
4. **API**: RESTful with POST `/v1/cache` and GET `/download/{bundle_hash}.zip`

## Development Commands

Since the project hasn't been implemented yet, here are the planned commands based on the design:

### Client Usage (planned)
```bash
dep_cache_proxy_client <endpoint_url> <manager> \
  --apikey=<APIKEY> \
  --files=<file1>,<file2> \
  [--node-version=<VERSION>] [--npm-version=<VERSION>] \
  [--php-version=<VERSION>]
```

### Server Usage (planned)
```bash
dep_cache_proxy_server <port> \
  --cache_dir=<CACHE_DIR> \
  --supported-versions-node=<NODE_VER>:<NPM_VER>,... \
  --supported-versions-php=<PHP_VER>,... \
  [--use-docker-on-version-mismatch] \
  [--is_public] \
  [--api-keys=<KEY1>,<KEY2>,...]
```

### Testing (planned)
The design includes comprehensive test coverage:
- Unit tests for hash calculation, blob storage, installers
- Integration tests for cache hit/miss scenarios
- Functional tests for CLI and API endpoints
- End-to-end tests with Docker

## Implementation Guidance

When implementing this system:

1. Start with the domain models in `server/domain/`:
   - `hash_constants.py` - Define SHA256 and 8KB block size
   - `dependency_set.py` - Bundle hash calculation
   - `blob_storage.py` - File blob management
   - `cache_repository.py` - Repository interface

2. Implement the infrastructure layer:
   - `file_system_cache_repository.py`
   - `api_key_validator.py`
   - `docker_utils.py`

3. Build the application layer:
   - DTOs for request/response
   - `handle_cache_request.py` orchestration

4. Create the interfaces:
   - FastAPI server with endpoints
   - CLI client with argument parsing

5. Add comprehensive tests following the structure in `analysis.md`

## Dependencies (planned)

Based on the design, the project will likely need:
- Python 3.x
- FastAPI and uvicorn (server)
- requests (client)
- pytest (testing)
- Docker (optional, for version mismatch handling)

## Security Considerations

- Validate all inputs (manager names, versions)
- Use `--ignore-scripts` and `--no-scripts` for package installations
- Implement timing-safe API key comparison
- Sanitize Docker command parameters