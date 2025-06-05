from typing import Optional, List, Dict
import os
import io
import json
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Header, Response, File, UploadFile, Form
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


class CacheResponseDTO(BaseModel):
    """Response model matching analysis.md specification."""
    download_url: str = Field(..., description="URL to download the bundle ZIP")
    cache_hit: bool = Field(..., description="Whether the bundle was already cached")


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


def validate_api_key(authorization: Optional[str] = Header(None)) -> None:
    """Validate API key using Bearer token format."""
    if config and not config.is_public:
        if not api_key_validator:
            raise HTTPException(status_code=500, detail="Server configuration error")
        
        if not authorization:
            raise HTTPException(status_code=401, detail="Missing Authorization Bearer <APIKEY>")
        
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Invalid authorization format. Use Bearer <APIKEY>")
        
        api_key = authorization.split(" ", 1)[1]
        if not api_key_validator.validate(api_key):
            raise HTTPException(status_code=401, detail="Invalid API key")


@app.post("/v1/cache", response_model=CacheResponseDTO, dependencies=[Depends(validate_api_key)])
async def cache_dependencies(
    manager: str = Form(...),
    hash: str = Form(...),
    versions: str = Form(...),
    lockfile: UploadFile = File(...),
    manifest: UploadFile = File(...)
):
    """
    Process a cache request for dependencies.
    
    This endpoint:
    1. Validates the request
    2. Checks if dependencies are already cached
    3. If not cached, installs dependencies and caches them
    4. Returns the bundle hash and download URL
    
    Parameters:
    - manager: Package manager (npm, composer, etc.)
    - hash: Pre-calculated bundle hash
    - versions: JSON string with version information
    - lockfile: Lockfile upload (package-lock.json, composer.lock, etc.)
    - manifest: Manifest file upload (package.json, composer.json, etc.)
    """
    if not config or not cache_repository:
        raise HTTPException(status_code=500, detail="Server not properly configured")
    
    # Parse versions JSON
    try:
        versions_dict = json.loads(versions)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid versions JSON")
    
    # Validate manager
    if manager not in ["npm", "composer", "yarn"]:
        raise HTTPException(status_code=400, detail=f"Unsupported manager: {manager}")
    
    # Read file contents
    try:
        lockfile_content = await lockfile.read()
        manifest_content = await manifest.read()
        
        if not lockfile_content or not manifest_content:
            raise ValueError("Empty file content")
            
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading files: {str(e)}")
    
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
        manager=manager,
        versions=versions_dict,
        lockfile_content=lockfile_content,
        manifest_content=manifest_content
    )
    
    try:
        # Handle the request
        response = handler.handle(cache_request)
        
        # Convert response to match API spec
        return CacheResponseDTO(
            download_url=f"{config.base_url}{response.download_url}",
            cache_hit=response.is_cache_hit
        )
    
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