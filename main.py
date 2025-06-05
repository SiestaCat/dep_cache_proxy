#!/usr/bin/env python3
"""
DepCacheProxy Server - Main entry point

Usage:
    dep_cache_proxy_server <port> \
        --cache_dir=<CACHE_DIR> \
        --supported-versions-node=<NODE_VER>:<NPM_VER>,... \
        --supported-versions-php=<PHP_VER>,... \
        [--use-docker-on-version-mismatch] \
        [--is_public] \
        [--api-keys=<KEY1>,<KEY2>,...] \
        [--base-url=<BASE_URL>]
"""

import argparse
import sys
import uvicorn
from typing import Dict, List, Optional

from interfaces.api import initialize_app


def parse_supported_versions(version_string: str) -> List[Dict[str, str]]:
    """Parse version string like '14.17.0:6.14.13,16.13.0:8.1.0' into list of dicts."""
    if not version_string:
        return []
    
    versions = []
    for pair in version_string.split(','):
        parts = pair.strip().split(':')
        if len(parts) >= 2:
            # For Node.js: node_version:npm_version
            versions.append({
                'runtime': parts[0],
                'package_manager': parts[1]
            })
        elif len(parts) == 1:
            # For other managers: just version
            versions.append({
                'runtime': parts[0]
            })
    
    return versions


def main():
    parser = argparse.ArgumentParser(
        description='DepCacheProxy Server - Dependency caching proxy',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # Required arguments
    parser.add_argument('port', type=int, help='Port to listen on')
    parser.add_argument('--cache_dir', required=True, help='Directory to store cache')
    
    # Supported versions for different package managers
    parser.add_argument('--supported-versions-node', 
                       help='Supported Node.js versions (format: NODE_VER:NPM_VER,...)')
    parser.add_argument('--supported-versions-php', 
                       help='Supported PHP versions (format: PHP_VER,...)')
    parser.add_argument('--supported-versions-python', 
                       help='Supported Python versions (format: PYTHON_VER,...)')
    parser.add_argument('--supported-versions-ruby', 
                       help='Supported Ruby versions (format: RUBY_VER,...)')
    
    # Optional arguments
    parser.add_argument('--use-docker-on-version-mismatch', action='store_true',
                       help='Use Docker when requested version is not supported')
    parser.add_argument('--is_public', action='store_true',
                       help='Run server without authentication')
    parser.add_argument('--api-keys', 
                       help='Comma-separated list of API keys for authentication')
    parser.add_argument('--base-url', default='http://localhost:8000',
                       help='Base URL for download links (default: http://localhost:8000)')
    parser.add_argument('--host', default='0.0.0.0',
                       help='Host to bind to (default: 0.0.0.0)')
    
    args = parser.parse_args()
    
    # Build supported versions dictionary
    supported_versions = {}
    
    if args.supported_versions_node:
        supported_versions['npm'] = parse_supported_versions(args.supported_versions_node)
        supported_versions['yarn'] = parse_supported_versions(args.supported_versions_node)
    
    if args.supported_versions_php:
        supported_versions['composer'] = parse_supported_versions(args.supported_versions_php)
    
    if args.supported_versions_python:
        supported_versions['pip'] = parse_supported_versions(args.supported_versions_python)
        supported_versions['pipenv'] = parse_supported_versions(args.supported_versions_python)
        supported_versions['poetry'] = parse_supported_versions(args.supported_versions_python)
    
    if args.supported_versions_ruby:
        supported_versions['bundler'] = parse_supported_versions(args.supported_versions_ruby)
    
    # Parse API keys
    api_keys = None
    if args.api_keys:
        api_keys = [key.strip() for key in args.api_keys.split(',') if key.strip()]
    
    # Validate configuration
    if not args.is_public and not api_keys:
        print("Error: Either --is_public must be set or --api-keys must be provided", file=sys.stderr)
        sys.exit(1)
    
    # Update base URL with actual port if using default
    base_url = args.base_url
    if base_url == 'http://localhost:8000' and args.port != 8000:
        base_url = f'http://localhost:{args.port}'
    
    # Initialize the FastAPI app
    app = initialize_app(
        cache_dir=args.cache_dir,
        supported_versions=supported_versions,
        use_docker_on_version_mismatch=args.use_docker_on_version_mismatch,
        is_public=args.is_public,
        api_keys=api_keys,
        base_url=base_url
    )
    
    # Run the server
    print(f"Starting DepCacheProxy server on {args.host}:{args.port}")
    print(f"Cache directory: {args.cache_dir}")
    print(f"Public mode: {args.is_public}")
    print(f"Docker fallback: {args.use_docker_on_version_mismatch}")
    
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == '__main__':
    main()