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

This server component follows Domain-Driven Design (DDD) and SOLID principles.

**⚠️ IMPORTANT - Project Structure**: 
- **DO NOT create a `server/` directory**
- All code should be organized directly in the root-level directories: `domain/`, `infrastructure/`, `application/`, `interfaces/`
- Import paths should use these directories directly (e.g., `from domain.cache_repository import ...`)
- The project structure is flat, without a parent `server/` directory

### Server Features
- Stores individual files as blobs in `cache/objects/` (content-addressable)
- Maintains JSON indices mapping relative paths to file hashes
- Generates ZIP files from blobs on demand
- Supports Docker for handling unsupported versions
- Provides RESTful API for client interactions

**Note**: The client component (`dep_cache_proxy_client`) is maintained in a separate repository.

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

When implementing this server:

1. Start with the domain models in `domain/`:
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

5. Add comprehensive tests following the structure in `analysis.md`

## Dependencies (planned)

Based on the design, the server will need:
- Python 3.x
- FastAPI and uvicorn
- pytest (testing)
- Docker (optional, for version mismatch handling)

## Security Considerations

- Validate all inputs (manager names, versions)
- Use `--ignore-scripts` and `--no-scripts` for package installations
- Implement timing-safe API key comparison
- Sanitize Docker command parameters