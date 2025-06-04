"""Hash constants for the dependency cache system."""

HASH_ALGORITHM = "sha256"
BLOCK_SIZE = 8192  # 8KB block size for file processing
HASH_PREFIX_LENGTH = 2  # Use first 2 characters for directory structure (e.g., aa/bb/aabb1234...)