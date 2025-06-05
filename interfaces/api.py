from typing import Optional, List
import os
import io
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Header, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from application.dtos import CacheRequest, CacheResponse
from application.handle_cache_request import HandleCacheRequest
from infrastructure.api_key_validator import ApiKeyValidator
from infrastructure.file_system_cache_repository import FileSystemCacheRepository
from infrastructure.docker_utils import DockerUtils
from domain.installer import InstallerFactory


class Config:
    def __init__(
        self,
        cache_dir: str,
        supported_versions: dict,
        use_docker_on_version_mismatch: bool = False,
        is_public: bool = False,
        api_keys: Optional[List[str]] = None,
        base_url: str = "http://localhost:8000"
    ):
        self.cache_dir = cache_dir
        self.supported_versions = supported_versions
        self.use_docker_on_version_mismatch = use_docker_on_version_mismatch
        self.is_public = is_public
        self.api_keys = api_keys or []
        self.base_url = base_url.rstrip('/')


class CacheRequestModel(BaseModel):
    manager: str = Field(..., description="Package manager (npm, composer, etc.)")
    versions: dict = Field(..., description="Version information for the manager")
    lockfile_content: str = Field(..., description="Content of the lock file")
    manifest_content: str = Field(..., description="Content of the manifest file")


config: Optional[Config] = None
cache_repository: Optional[FileSystemCacheRepository] = None
api_key_validator: Optional[ApiKeyValidator] = None
docker_utils: Optional[DockerUtils] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global cache_repository, docker_utils
    if config:
        cache_repository = FileSystemCacheRepository(Path(config.cache_dir))
        docker_utils = DockerUtils()
    yield
    # Shutdown
    pass


app = FastAPI(
    title="DepCacheProxy Server",
    description="Dependency caching proxy server",
    version="1.0.0",
    lifespan=lifespan
)


def validate_api_key(x_api_key: Optional[str] = Header(None)) -> None:
    """Validate API key if authentication is enabled."""
    if config and not config.is_public:
        if not api_key_validator:
            raise HTTPException(status_code=500, detail="Server configuration error")
        
        if not x_api_key:
            raise HTTPException(status_code=401, detail="API key required")
        
        if not api_key_validator.validate(x_api_key):
            raise HTTPException(status_code=401, detail="Invalid API key")


@app.post("/v1/cache", response_model=CacheResponse, dependencies=[Depends(validate_api_key)])
async def cache_dependencies(request: CacheRequestModel):
    """
    Process a cache request for dependencies.
    
    This endpoint:
    1. Validates the request
    2. Checks if dependencies are already cached
    3. If not cached, installs dependencies and caches them
    4. Returns the bundle hash and download URL
    """
    if not config or not cache_repository:
        raise HTTPException(status_code=500, detail="Server not properly configured")
    
    # Create request handler
    handler = HandleCacheRequest(
        cache_repository=cache_repository,
        installer_factory=InstallerFactory(),
        docker_utils=docker_utils,
        supported_versions=config.supported_versions,
        use_docker_on_version_mismatch=config.use_docker_on_version_mismatch
    )
    
    # Convert to application DTO
    cache_request = CacheRequest(
        manager=request.manager,
        versions=request.versions,
        lockfile_content=request.lockfile_content.encode('utf-8'),
        manifest_content=request.manifest_content.encode('utf-8')
    )
    
    try:
        # Handle the request
        response = handler.handle(cache_request)
        
        # Add base URL to download URL
        response.download_url = f"{config.base_url}/download/{response.bundle_hash}.zip"
        
        return response
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/download/{bundle_hash}.zip", dependencies=[Depends(validate_api_key)])
async def download_bundle(bundle_hash: str):
    """
    Download a cached bundle as a ZIP file.
    
    This endpoint retrieves a previously cached bundle and streams it as a ZIP file.
    """
    if not cache_repository:
        raise HTTPException(status_code=500, detail="Server not properly configured")
    
    try:
        # Get the ZIP file path
        zip_path = cache_repository.get_bundle_zip_path(bundle_hash)
        
        if not zip_path or not zip_path.exists():
            raise HTTPException(status_code=404, detail="Bundle not found")
        
        # Stream the file
        def iterfile():
            with open(zip_path, 'rb') as f:
                while chunk := f.read(8192):
                    yield chunk
        
        return StreamingResponse(
            iterfile(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename={bundle_hash}.zip"
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving bundle: {str(e)}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


def initialize_app(
    cache_dir: str,
    supported_versions: dict,
    use_docker_on_version_mismatch: bool = False,
    is_public: bool = False,
    api_keys: Optional[List[str]] = None,
    base_url: str = "http://localhost:8000"
):
    """Initialize the FastAPI application with configuration."""
    global config, api_key_validator
    
    config = Config(
        cache_dir=cache_dir,
        supported_versions=supported_versions,
        use_docker_on_version_mismatch=use_docker_on_version_mismatch,
        is_public=is_public,
        api_keys=api_keys,
        base_url=base_url
    )
    
    # Initialize API key validator
    if not is_public and api_keys:
        api_key_validator = ApiKeyValidator(api_keys)
    
    # Create cache directory if it doesn't exist
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    
    return app