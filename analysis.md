# Extended Analysis of **DepCacheProxy** (`dep_cache_proxy`)

This document details exhaustively the design, architecture, and workflow of the **DepCacheProxy** project, a library/proxy for caching and serving package dependencies (e.g., `node_modules`, `vendor`) to speed up build processes (for example, in Docker containers) and serve as a download backend in environments with unstable networks. It is designed in Python, following DDD (Domain-Driven Design) and SOLID principles, and divided into two main components: client and server.

---

## Table of Contents

- [Extended Analysis of **DepCacheProxy** (`dep_cache_proxy`)](#extended-analysis-of-depcacheproxy-dep_cache_proxy)
  - [Table of Contents](#table-of-contents)
  - [1. Objectives and Context](#1-objectives-and-context)
  - [2. Functional and Non-Functional Requirements](#2-functional-and-non-functional-requirements)
    - [2.1 Functional Requirements (FR)](#21-functional-requirements-fr)
    - [2.2 Non-Functional Requirements (NFR)](#22-non-functional-requirements-nfr)
  - [3. Overall Architecture Overview (DDD + SOLID)](#3-overall-architecture-overview-ddd--solid)
    - [SOLID Principles Applied (Examples)](#solid-principles-applied-examples)
  - [4. Main Components](#4-main-components)
    - [4.1 Client (`dep_cache_proxy_client`)](#41-client-dep_cache_proxy_client)
      - [4.1.1 CLI Parameters and Validations](#411-cli-parameters-and-validations)
    - [4.2 Server (`dep_cache_proxy_server`)](#42-server-dep_cache_proxy_server)
      - [4.2.1 CLI Parameters and Validations](#421-cli-parameters-and-validations)
  - [5. Domain Model and Hashing](#5-domain-model-and-hashing)
    - [5.1 Entity: `DependencySet`](#51-entity-dependencyset)
    - [5.2 Entity: `CacheObject`](#52-entity-cacheobject)
    - [5.3 Entity/Aggregate: `CacheRepository` (Interface)](#53-entityaggregate-cacherepository-interface)
    - [5.4 Domain Service: `HashCalculator`](#54-domain-service-hashcalculator)
  - [6. Cache Directory Structure](#6-cache-directory-structure)
  - [7. Complete Workflow](#7-complete-workflow)
  - [8. Implementation Details and Pseudocode](#8-implementation-details-and-pseudocode)
    - [8.1 Client Pseudocode](#81-client-pseudocode)
      - [Comments on Client Pseudocode](#comments-on-client-pseudocode)
    - [8.2 Server Pseudocode](#82-server-pseudocode)
      - [Comments on Server Pseudocode](#comments-on-server-pseudocode)
  - [9. HTTP API and Route Schema](#9-http-api-and-route-schema)
    - [9.1 Main Routes](#91-main-routes)
    - [9.2 Request and Response Schema](#92-request-and-response-schema)
      - [9.2.1 `CacheRequestDTO`](#921-cacherequestdto)
      - [9.2.2 `CacheResponseDTO`](#922-cacheresponsedto)
  - [10. Usage Scenarios and Test Cases](#10-usage-scenarios-and-test-cases)
    - [10.1 Scenario 1: NPM Cache Hit (Public Server)](#101-scenario-1-npm-cache-hit-public-server)
    - [10.2 Scenario 2: Composer Cache Miss (Server with API Key)](#102-scenario-2-composer-cache-miss-server-with-api-key)
    - [10.3 Scenario 3: Request with Invalid API Key](#103-scenario-3-request-with-invalid-api-key)
    - [10.4 Scenario 4: Unsupported Manager](#104-scenario-4-unsupported-manager)
  - [11. Security, Scalability, and Common Errors Notes](#11-security-scalability-and-common-errors-notes)
    - [11.1 Security](#111-security)
    - [11.2 Scalability and Concurrency](#112-scalability-and-concurrency)
    - [11.3 Common Errors and How to Handle Them](#113-common-errors-and-how-to-handle-them)
  - [12. Conclusions](#12-conclusions)

---

## 1. Objectives and Context

1. **Cache Dependencies**

   * Store downloaded packages locally (on the server’s disk) based on `package.json` + `package-lock.json` (or `composer.json` + `composer.lock`) to avoid redundant downloads and save bandwidth and time.
   * Each unique combination of definition files + lockfile generates a *specific hash*. That hash identifies a “version of the dependency set.”

2. **Provide a Proxy/Download Backup**

   * In environments where the client’s network is unstable (timeouts, latency), the **DepCacheProxy** server acts as a secondary source so the client can retrieve a pre-built ZIP of dependencies instead of downloading directly from npm or Packagist.

3. **Accelerate Docker Build Processes or Other Pipelines**

   * Instead of always running `npm install` / `npm ci` or `composer install`, you can download a ZIP containing the pre-filled `node_modules` or `vendor` folder, avoiding installation time.

4. **Extensible Support for Multiple Package Managers**

   * Although examples are shown with NPM and Composer, **DepCacheProxy** is designed generically for arbitrary package managers.
   * Key points to parameterize:

     * Type of manager (NPM/Composer/Others)
     * Possible versions of NodeJS/NPM or PHP/Composer (optional)
     * Specific commands to install dependencies

5. **Design Principles**

   * **DDD (Domain-Driven Design)**: Separate the domain layer (hash model, cache objects, invalidation logic), the application layer (services for package generation, compression, API key verification, ZIP reconstruction), and the infrastructure layer (disk persistence, HTTP server).
   * **SOLID**: Clean classes, each module with a single responsibility, dependency injection to facilitate unit testing and extensibility.

6. **Language and Paradigms**

   * **Python 3.x**, leveraging standard modules (`hashlib`, `tempfile`, `subprocess`, `zipfile`, `http.server` or light frameworks like FastAPI/Flask).
   * Modular architecture: `domain/`, `application/`, `infrastructure/`, `interfaces/` (for DDD).

7. **Two Parts**

   * **CLI Client**: Executable `dep_cache_proxy_client` which:

     1. Gathers dependency definition files (`package.json`, `package-lock.json` or `composer.json`, `composer.lock`) and optional version(s).
     2. Calculates a local hash of the combination of files.
     3. Calls the server’s HTTP endpoint (`dep_cache_proxy_server`) with parameters: URL, manager, API key (optional), list of files (embedded or multipart).
     4. If the cache exists on the server, it receives a direct download URL. If not, it waits for the server to generate the ZIP and return the URL.
     5. Downloads the ZIP and extracts it into the appropriate folder (`node_modules/` or `vendor/`).

   * **HTTP Server**: Executable `dep_cache_proxy_server` which:

     1. Exposes an HTTP route (for example, `POST /v1/cache`) to receive the client’s request.
     2. Validates API key (unless `--is_public` is true).
     3. Validates that the `manager` (instead of “type”) is supported (`npm`, `composer`, or extensible).
     4. Calculates the hash based on the received file contents.
     5. Searches in its cache tree (`cache/objects/`) if the folder for that hash exists.

        * If it exists, immediately returns the download URL.
        * If not, proceeds to create a temporary folder:

          1. Extracts `package.json` and `package-lock.json` into that temporary directory.
          2. Executes the installation command (`npm ci --ignore-scripts --cache .` or `composer install --no-dev --prefer-dist`).
          3. When finished, copies the `node_modules`/`vendor` folder to the cache directory structured by hash (see section 6).
          4. Generates a ZIP containing that cached folder.
          5. Saves in `cache/objects/` the metadata:

             * File `<hash>.<manager>.hash` containing a list of relative paths and checksums (optional) to allow ZIP reconstruction without needing to decompress the cache (e.g., list of files with sizes and paths).
          6. Exposes to the client the unique URL (for example, `http://<host>:<port>/download/<hash>.zip`).
     6. Responds with JSON `{ "download_url": "http://..." }`.

8. **API Keys and Security**

   * The server can operate in **public** mode (`--is_public=true`), in which case it does not validate keys. By default (`--is_public=false`), it requires the client to send `--apikey=KEY` and compares it against the managed list (`--api-keys="KEY1,KEY2,KEY3"`).
   * The endpoint returns `401 Unauthorized` if API key validation fails.

9. **Persistent Cache**

   * **cache\_dir**: configurable directory where the cache structure is stored (default `./cache/`).
   * Under `cache_dir`, we find:

     * `objects/` (structure based on object hashes)
     * `metadata/` (optional: request logs, hash index, expiration)

10. **Design Keys**

    * Each combination of files and optional versions produces a single SHA256 hash (or SHA1+date, configurable).
    * Directory structure based on hash:

      ```
      cache/
      └── objects/
          ├── 12/34/1234abcd.../
          │   ├── node_modules/...
          │   └── <hash>.npm.hash
          ├── ab/cd/abcd1234.../
          │   ├── vendor/...
          │   └── <hash>.composer.hash
          └── ...
      ```
    * The file `<hash>.<manager>.hash` contains:

      * A list of relative paths inside the final folder (to reconstruct the ZIP without traversing the entire tree).
      * Checksums of each file (optionally) to validate integrity.

11. **CLI Parameters**

    * **Client**:

      ```
      dep_cache_proxy_client <endpoint_url> <manager> --apikey=<APIKEY> --files=<file1>,<file2>[,...] [--node-version=<VERSION>] [--npm-version=<VERSION>] [--php-version=<VERSION>]
      ```

      > Note that we rename the `<type>` parameter to **`<manager>`** for clarity: e.g., `npm`, `composer`, `yarn`, etc.

      * `<endpoint_url>`: base address of the server (e.g., `https://my.website/uri`).
      * `<manager>`: string identifier of the package manager (e.g., `npm`, `composer`).
      * `--apikey`: client API key (if required).
      * `--files`: comma-separated list of definition files + lockfile. E.g.: `package.json,package-lock.json` or `composer.json,composer.lock`.
      * Optional flags:

        * `--node-version`: NodeJS version (e.g., `14.17.0`).
        * `--npm-version`: NPM version (e.g., `6.14.13`).
        * `--php-version`: PHP version (for Composer).
      * Internally, the client:

        1. Reads the files and generates the hash.
        2. Makes a `POST` to `/<api_version>/cache` with JSON/multipart:

           ```jsonc
           {
             "manager": "npm",
             "hash": "abcdef1234...",
             "files": {
               "package.json": "<base64_content>",
               "package-lock.json": "<base64_content>"
             },
             "versions": {
               "node": "14.17.0",
               "npm": "6.14.13"
             }
           }
           ```
        3. Receives a response with `{ "download_url": "http://..." }`.
        4. Downloads the ZIP and extracts it into `./node_modules/`.

    * **Server**:

      ```
      dep_cache_proxy_server <port> --cache_dir=<CACHE_DIR> [--is_public] [--api-keys=<KEY1>,<KEY2>,...]
      ```

      * `<port>`: port to listen on (e.g., `8080`).
      * `--cache_dir`: base path for the cache (e.g., `/var/lib/dep_cache_proxy/cache`).
      * `--is_public`: boolean flag (default `false`) that disables API key validation.
      * `--api-keys`: comma-separated list of valid API keys (only if `--is_public` is `false`).

---

## 2. Functional and Non-Functional Requirements

### 2.1 Functional Requirements (FR)

1. **FR1**: The system must accept client requests containing:

   * Dependency manager identifier (`manager`).
   * Definition files (`package.json`, `package-lock.json`, `composer.json`, `composer.lock`, etc.).
   * Optional environment versions (`node`, `npm`, `php`).
   * API key (if not in public mode).

2. **FR2**: Calculate a unique hash based on:

   * Content of each file sent.
   * (Optional) specified version(s).
   * Dependency manager.
   * The resulting hash must be deterministic for identical content inputs.

3. **FR3**: Validate that the `manager` is supported. If not, return `400 Bad Request` with message “Manager not supported”.

4. **FR4**: Check if a cache exists for the calculated hash.

   * If it exists, immediately respond with the download URL.
   * If not, enqueue/execute the dependency generation process.

5. **FR5**: Generate dependencies in a temporary directory, running the appropriate command:

   * NPM: `npm ci --ignore-scripts --cache .` (respecting `node-version` and `npm-version` if provided).
   * Composer: `composer install --no-dev --prefer-dist` (respecting `php-version`).
   * Other managers: commands defined in configuration or plugin.

6. **FR6**: Copy the resulting folder (`node_modules` or `vendor`) to the cache structure based on hash (`cache/objects/<subdirs>`).

7. **FR7**: Generate a metadata file `<hash>.<manager>.hash` inside the cached folder, listing:

   * Relative paths of all cached files/folders.
   * Optionally, individual checksums.

8. **FR8**: Compress the cached folder into a ZIP (`<hash>.zip`) and expose an endpoint for downloading it:

   * `GET /download/<hash>.zip` ⇒ delivers the ZIP.

9. **FR9**: If the server is in closed mode (`--is_public=false`), validate the API key in every request.

10. **FR10**: The client must:

    * Collect the files specified in `--files`.
    * Locally calculate the same hash as the server.
    * Make a `POST` to the server with encoded data (JSON or multipart).
    * Download the ZIP if necessary and extract it into the local dependency folder.

11. **FR11**: Provide clear logs of each step, significant errors, and metrics (cache hit time, hit ratio, installation time). (Extensible)

### 2.2 Non-Functional Requirements (NFR)

1. **NFR1 (Efficiency)**:

   * Hash calculation must be fast, using streaming if files are large.
   * The server must handle concurrency (for example, with an ASGI server like Uvicorn/Starlette or Flask + Gunicorn).

2. **NFR2 (Scalability)**:

   * Allow multiple dependency generation processes to run simultaneously.
   * Consider future use of distributed storage (e.g., S3) to cache large objects.

3. **NFR3 (Extensibility)**:

   * Add new package managers without modifying core logic, using design patterns (Factory Method or Strategy).

4. **NFR4 (Security)**:

   * Validate inputs and sanitize file names.
   * Avoid injections (for example, in the manager name or paths).
   * Securely validate API key signatures (constant-time comparators).

5. **NFR5 (Portability)**:

   * Run on Linux and macOS (common CI environments).
   * Avoid highly specific native dependencies.

6. **NFR6 (Maintainability)**:

   * Follow PEP8 conventions, document with docstrings and type hints.
   * Unit and integration tests (pytest).

7. **NFR7 (Availability)**:

   * The server does not support HTTPS natively; it is assumed to run behind a reverse proxy (Nginx, Traefik) providing TLS.

---

## 3. Overall Architecture Overview (DDD + SOLID)

DDD Approach:

* **Domain Layer** (`domain/`):

  * Main entities:

    * `DependencySet` (represents a combination of files + manager + versions + hash).
    * `CacheObject` (represents the cached folder with its `<hash>.<manager>.hash` metadata file).
  * Aggregates:

    * `CacheRepository` (interface for cached object persistence).
  * Domain services:

    * `HashCalculator` (logic to combine files and generate hash).

* **Application Layer** (`application/`):

  * Use cases (Interactors):

    * `HandleCacheRequest` (main flow: receive request, validate, orchestrate cache lookup/generation).
    * `GenerateDependencies` (invokes the manager with specific versions).
    * `CompressCacheObject` (creates the ZIP and builds the URL).
    * `ValidateApiKey` (manages authorization).
    * `ListSupportedManagers` (optional).
  * DTOs (Data Transfer Objects):

    * `CacheRequestDTO` (fields: manager, files, versions, api\_key).
    * `CacheResponseDTO` (fields: download\_url, cache\_hit: bool).

* **Infrastructure Layer** (`infrastructure/`):

  * Concrete implementations:

    * `FileSystemCacheRepository` (local persistence under `cache/objects`).
    * `PostgreSQLCacheRepository` (optional, for extended metadata).
    * `SubprocessDependencyInstaller` (executes `npm`, `composer`, etc.).
    * `HTTPServer` (ASGI with FastAPI/Starlette or Flask).
  * Adapters/Gateways:

    * `LocalLogger` (writes logs to disk or stdout).

* **Interfaces / Entry Points** (`interfaces/`):

  * `main.py` to start the HTTP server (`dep_cache_proxy_server`).
  * `cli_client.py` for the client (`dep_cache_proxy_client`).
  * Controllers (in an MVC-like architecture):

    * `CacheController` (maps HTTP request to `CacheRequestDTO`, invokes use case, and returns HTTP response).

* **CLI Application** (`cli/`):

  * `ClientCLI` (handles arguments with `argparse` or `click`, formats the request, deserializes the response).

### SOLID Principles Applied (Examples)

1. **S (Single Responsibility Principle)**

   * `HashCalculator`: single responsibility → compute hash.
   * `FileSystemCacheRepository`: single responsibility → store/retrieve data on the file system.
   * `CacheController`: single responsibility → receive HTTP, validate minimal inputs, invoke use case.

2. **O (Open/Closed Principle)**

   * Add a new package manager without modifying `HandleCacheRequest`. Instead, implement a new class that extends `DependencyInstaller` and configure it in a `ManagerFactory`.

3. **L (Liskov Substitution Principle)**

   * Subclasses of `CacheRepository` (e.g., `FileSystemCacheRepository`, `S3CacheRepository`) adhere to the same interface without breaking clients.

4. **I (Interface Segregation Principle)**

   * Separate interfaces: `DependencyInstaller` (only installation methods) and `CacheRepository` (only CRUD methods for cache).

5. **D (Dependency Inversion Principle)**

   * The `HandleCacheRequest` use case depends on abstractions (`ICacheRepository`, `IDependencyInstaller`), not concrete implementations.

---

## 4. Main Components

### 4.1 Client (`dep_cache_proxy_client`)

* **Objective**: Read local project files, compute hash, send request to the server, and, if the response contains a ZIP URL, download and extract dependencies into the local dependency folder.

* **Responsibilities (SRP)**:

  1. Parse CLI arguments.
  2. Read content of specified files.
  3. Calculate local hash of `DependencySet`.
  4. Construct and send HTTP request to the server.
  5. Receive response: URL or error.
  6. If applicable, download ZIP and extract it to the appropriate folder.
  7. Handle network errors with configurable retries.

* **External Dependencies**:

  * HTTP library (e.g., `requests`).
  * Compression library (`zipfile`).

* **Proposed Modules**:

  * `client/cli.py`
  * `client/hash_calculator.py`
  * `client/http_client.py`
  * `client/downloader.py`

* **Example Invocation**:

  ```bash
  # With npm manager
  dep_cache_proxy_client https://my.server/api npm --apikey=ABCD1234 --files=package.json,package-lock.json --node-version=14.20.0 --npm-version=6.14.13

  # With composer manager and public server
  dep_cache_proxy_client http://localhost:8080 composer --files=composer.json,composer.lock
  ```

#### 4.1.1 CLI Parameters and Validations

* **Positional Arguments**:

  1. `<endpoint_url>`: Base server URL (e.g., `http://localhost:8080/api`)
  2. `<manager>`: Dependency manager identifier (`npm`, `composer`, or others supported).

* **Flags**:

  * `--apikey=<APIKEY>` (optional if the server is public; otherwise required).
  * `--files=<file1>,<file2>[,...]` (*string list*) - required, at least two files (definition + lock).
  * `--node-version=<VERSION>` and `--npm-version=<VERSION>` (only if `manager == "npm"`).
  * `--php-version=<VERSION>` (only if `manager == "composer"`).
  * `--timeout=<seconds>` (optional, default 60s) for HTTP requests.

* **Possible Errors**:

  * Missing files or files not found on local disk → abort with an error message.
  * `manager` invalid/not supported → abort.
  * Missing API key when the server requires it → abort.

* **Expected Output**:

  * Console message indicating whether it was a “cache hit” or “cache miss + generation.”
  * Download URL of the ZIP.
  * Download and extraction progress.
  * Exit code 0 on success, ≠0 on errors.

---

### 4.2 Server (`dep_cache_proxy_server`)

* **Objective**: Receive cache requests, decide whether the cache exists or needs to be generated, and serve the resulting ZIP.

* **Responsibilities**:

  1. Parse startup arguments: `port`, `--cache_dir`, `--is_public`, `--api-keys`.
  2. Initialize repositories (e.g., `FileSystemCacheRepository(cache_dir)`).
  3. Configure HTTP router (FastAPI/Flask) with endpoints:

     * `POST /v1/cache` → receives JSON/multipart and returns JSON with download URL.
     * `GET /download/<hash>.zip` → serves the ZIP.
  4. Validate API key on each request if `--is_public == False`.
  5. Validate the requested `manager`.
  6. Orchestrate cache use cases (hit/miss).
  7. Log and gather metrics (optional).

* **External Dependencies**:

  * `fastapi` + `uvicorn` (or `Flask` + `gunicorn`).
  * `hashlib`, `tempfile`, `subprocess`, `zipfile`, `os`, `shutil`.

* **Proposed Modules**:

  * `server/main.py`
  * `server/controllers/cache_controller.py`
  * `server/application/usecases/handle_cache_request.py`
  * `server/domain/hash_calculator.py`
  * `server/infrastructure/file_system_cache_repository.py`
  * `server/infrastructure/dependency_installer.py`
  * `server/infrastructure/zip_util.py`
  * `server/infrastructure/api_key_validator.py`

#### 4.2.1 CLI Parameters and Validations

* **Positional Argument**:

  1. `<port>` (integer, e.g., `8080`).
* **Flags**:

  * `--cache_dir=<CACHE_DIR>` (absolute or relative path, e.g., `./cache`).
  * `--is_public` (boolean, default `False`).
  * `--api-keys=<KEY1>,<KEY2>,...` (comma-separated string list, required if `--is_public` is `False`).
* **Possible Errors**:

  * Invalid `port` (not an integer in the range 1–65535).
  * `cache_dir` not accessible or not writable.
  * Missing `--api-keys` when `--is_public` is `False`.

---

## 5. Domain Model and Hashing

### 5.1 Entity: `DependencySet`

* **Attributes**:

  * `manager: str`
  * `file_contents: Dict[str, bytes]` → key: filename (e.g., `"package.json"`), value: content in bytes.
  * `versions: Dict[str, str]` → optional, e.g., `{ "node": "14.17.0", "npm": "6.14.13" }`.
  * `hash: str` (resulting hexadecimal SHA256).

* **Main Method**:

  * `calculate_hash() -> str`:

    1. Sort filenames deterministically (alphabetically).
    2. Concatenate: `manager + "\n"` → to differentiate `npm` vs `composer`.
    3. For each filename in order:

       * Read its content (bytes) and feed into `hashlib.sha256`.
    4. For each `(key, value)` in `versions` (sorted by key):

       * Concatenate `"key=value\n"`.
       * Feed those bytes into `hashlib.sha256`.
    5. Return the 64-character hex digest.

* **Rationale**:

  * Including `manager` in the hash prevents collisions between different ecosystems.
  * Including optional `versions` ensures that changing a version produces a new hash and thus triggers dependency regeneration.

---

### 5.2 Entity: `CacheObject`

* **Attributes**:

  * `hash: str`
  * `manager: str`
  * `cache_path: Path` → root folder on disk where the cache resides:

    ```
    cache_dir/objects/<h0h1>/<h2h3>/<hash>.<manager>/
    ```
  * `meta_file: Path` → `cache_path / "<hash>.<manager>.hash"`.
  * `zip_file: Path` → `cache_path / "<hash>.zip"`.

* **Methods**:

  * `exists() -> bool`: checks if `cache_path` exists and contains both `meta_file` and `zip_file`.
  * `write_metadata(file_list: List[str])`: generates the `<hash>.<manager>.hash` file with lines:

    ```
    <relative_path>;<file_size>;<checksum (optional)>
    ```
  * `compress_all()`: generates the ZIP from the entire internal folder (`node_modules` or `vendor`).

---

### 5.3 Entity/Aggregate: `CacheRepository` (Interface)

* **Methods** (contract):

  1. `get(cache_key: str) -> Optional[CacheObject]`: returns `CacheObject` if it exists, or `None` otherwise.
  2. `save(cache_object: CacheObject) -> None`: saves the object to disk (creates folders, writes metadata).
  3. `list_all() -> List[CacheObject]` (optional, for cleanup/monitoring).
  4. `delete(cache_key: str) -> None` (optional, for invalidation).

* **Main Implementation**:

  * `FileSystemCacheRepository(cache_dir: Path)`:

    * `get(...)`: checks existence of `cache_dir / "objects" / subdirs / "<hash>.<manager>"`.
    * `save(...)`: creates necessary folders and moves files.
    * `delete(...)`: deletes the entire folder associated with the key.

---

### 5.4 Domain Service: `HashCalculator`

* **Responsibility**: Accept a `DependencySet` and return the `hash: str`.

---

## 6. Cache Directory Structure

A **two-level directory structure based on the first two bytes of the hash** is used to avoid too many files in a single directory. Example tree:

```
<cache_dir>/
└── objects/
    ├── 00/00/   # hashes starting with "0000..."
    ├── 00/01/
    ├── ...
    ├── ab/cd/   # hashes starting with "abcd..."
    │   └── <hash>.npm/
    │       ├── node_modules/...
    │       ├── <hash>.npm.hash
    │       └── <hash>.zip
    ├── ef/01/
    └── ... (256 x 256 possible combinations: "00" to "ff" / "00" to "ff")
```

* **Naming Convention**

  * Level-1 directory: the first two hexadecimal characters of the hash (`h[0:2]`).
  * Level-2 directory: the next two characters (`h[2:4]`).
  * Final folder name: `"<hash>.<manager>"`.

* **Contents of `<hash>.<manager>` Folder**:

  * Subfolder `node_modules/` or `vendor/` (depending on `manager`).
  * Metadata file: `<hash>.<manager>.hash`.
  * Compressed file: `<hash>.zip`.

* **Metadata File** (`<hash>.<manager>.hash`)

  * Each line format (separated by `\n`):

    ```
    <relative_path>;<size_bytes>;<sha256_hex>
    ```

    * Example:

      ```
      node_modules/packageA/index.js;12034;ff3a2b...
      node_modules/packageB/lib/util.js;4531;9ac8d1...
      ```

With this metadata, the server can reconstruct the ZIP without needing to read every file if they are already stored individually, or validate the cache’s integrity.

---

## 7. Complete Workflow

Below is each step of the general workflow, from the user invoking the client to obtaining local dependencies:

1. **Client Start**

   ```
   $ dep_cache_proxy_client https://server:8080/api npm --apikey=KEY123 --files=package.json,package-lock.json --node-version=14.20.0 --npm-version=6.14.13
   ```

   * The client parses arguments and checks that `package.json` and `package-lock.json` exist.
   * Reads both files in binary mode (bytes).
   * Instantiates a `DependencySet(manager="npm")` object and populates it with those contents and optional versions.
   * Calls `HashCalculator.calculate_hash(dependency_set)` → obtains `hex_hash` (e.g., `ab12cd34ef56...`).
   * Constructs a JSON request:

     ```jsonc
     {
       "manager": "npm",
       "hash": "ab12cd34ef56...",
       "files": {
         "package.json": "<base64_content>",
         "package-lock.json": "<base64_content>"
       },
       "versions": {
         "node": "14.20.0",
         "npm": "6.14.13"
       }
     }
     ```
   * Sends a `POST https://server:8080/api/v1/cache` with header `Authorization: Bearer KEY123` and the above JSON.

2. **Server Reception**

   * FastAPI (or Flask) maps `POST /v1/cache` to `CacheController.handle_request()`.
   * Extracts the JWT from the `Authorization: Bearer` header.
   * If `is_public == False`, calls `ValidateApiKey.check(api_key)` (compares against the internal list).

     * If validation fails, responds `401 Unauthorized`.
   * Extracts `manager`, `hash`, `files`, `versions` from the JSON.
   * Validates that `manager` is supported (e.g., `if manager not in ["npm","composer"] → 400`).
   * Calls `HandleCacheRequest.execute(request_dto)`, where `request_dto.manager == "npm"`, `request_dto.hash == "ab12..."`, etc.

3. **Use Case: `HandleCacheRequest`**

   ```python
   class HandleCacheRequest:
       def __init__(self, cache_repo: ICacheRepository, installer_factory: InstallerFactory, zip_util: ZipUtil):
           self.cache_repo = cache_repo
           self.installer_factory = installer_factory
           self.zip_util = zip_util

       def execute(self, request: CacheRequestDTO) -> CacheResponseDTO:
           cache_key = f"{request.hash}.{request.manager}"
           cache_obj = self.cache_repo.get(cache_key)
           if cache_obj and cache_obj.exists():
               # Cache Hit
               download_url = build_download_url(request.hash, request.manager)
               return CacheResponseDTO(download_url=download_url, cache_hit=True)
           else:
               # Cache Miss → Generate dependencies
               temp_dir = create_temp_dir(prefix=cache_key)
               # 1) Decode base64 files and write them in temp_dir
               for name, b64_content in request.files.items():
                   write_file(temp_dir / name, base64_decode(b64_content))
               # 2) Install dependencies
               installer = self.installer_factory.get_installer(request.manager, request.versions)
               installer.install(temp_dir)

               # 3) Copy generated folder (node_modules/vendor) to cache_dir
               final_cache_dir = self.cache_repo.compute_path(cache_key)
               copy_tree(temp_dir / installer.output_folder_name, final_cache_dir / installer.output_folder_name)

               # 4) Generate metadata
               file_list = list_all_files(final_cache_dir / installer.output_folder_name)
               checksum_list = compute_checksums(final_cache_dir / installer.output_folder_name)
               self.zip_util.write_metadata(final_cache_dir, cache_key, request.manager, file_list, checksum_list)

               # 5) Compress the cache
               zip_path = final_cache_dir / f"{request.hash}.zip"
               self.zip_util.compress_folder(final_cache_dir / installer.output_folder_name, zip_path)

               # 6) Register in repo (persist metadata)
               cache_obj = CacheObject(hash=request.hash, manager=request.manager, cache_path=final_cache_dir)
               self.cache_repo.save(cache_obj)

               download_url = build_download_url(request.hash, request.manager)
               return CacheResponseDTO(download_url=download_url, cache_hit=False)
   ```

   * When finished, `HandleCacheRequest.execute()` returns a `CacheResponseDTO` with `download_url` and a boolean `cache_hit`.

4. **Response to Client**

   * `CacheController` wraps the result in JSON, e.g.:

     ```jsonc
     {
       "download_url": "http://server:8080/download/ab12cd34ef56....zip",
       "cache_hit": false
     }
     ```
   * The client receives the response:

     * If `cache_hit == true`, it prints “Cache hit: downloading...”
     * If `cache_hit == false`, it prints “Cache miss: server is generating dependencies. Downloading when ready...”

5. **Downloading the ZIP**

   * The client performs `GET http://server:8080/download/ab12cd34ef56....zip` and saves it to disk, e.g., `./dep_cache/ab12cd34ef56....zip`.
   * Extracts the ZIP to the appropriate local dependency folder:

     * If `manager == "npm"`, it extracts into `./node_modules/`.
     * If `manager == "composer"`, it extracts into `./vendor/`.
   * The client may delete the temporary ZIP or keep it in a local cache.

6. **Final Delivery**

   * The client ends up with the updated dependencies folder on disk:

     ```
     project/
     ├── package.json
     ├── package-lock.json
     └── node_modules/  # Sourced from the downloaded ZIP
     ```
   * If the same flow is repeated with identical `package.json` + `package-lock.json` (no version changes), it will be a pure **cache hit**, avoiding regeneration on the server.

7. **Cleanup (Optional)**

   * The server could periodically (via cronjob or scheduler) invoke a `PurgeOldCaches` use case to delete unreferenced or expired hashes after N days.

---

## 8. Implementation Details and Pseudocode

Below is Python-oriented pseudocode respecting DDD/SOLID conventions. The goal is that other AIs (e.g., Claude) can read and implement it directly.

### 8.1 Client Pseudocode

```python
#!/usr/bin/env python3
import argparse
import base64
import hashlib
import json
import os
import sys
import tempfile
import zipfile
import requests   # pip install requests

# ----------------------------------------
# Domain / Utility: HashCalculator (client)
# ----------------------------------------
class HashCalculator:
    @staticmethod
    def calculate_hash(manager: str, file_paths: list[str], versions: dict) -> str:
        """
        Calculates SHA256 based on:
            1. manager (e.g. "npm")
            2. contents of each file (in alphabetical order)
            3. optional versions (sorted by key)
        """
        sha = hashlib.sha256()
        sha.update(manager.encode("utf-8"))
        sha.update(b"\n")
        # Read and process each file
        for file_name in sorted(file_paths):
            with open(file_name, "rb") as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    sha.update(chunk)
        # Process optional versions
        for k in sorted(versions.keys()):
            v = versions[k]
            line = f"{k}={v}\n".encode("utf-8")
            sha.update(line)
        return sha.hexdigest()

# ----------------------------------------
# Client: Main CLI
# ----------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(
        description="DepCacheProxy CLI Client"
    )
    parser.add_argument("endpoint_url", type=str, help="Base server URL (http://host:port/api)")
    parser.add_argument("manager", type=str, help="Dependency manager (npm, composer, etc.)")
    parser.add_argument("--apikey", type=str, required=False, help="API Key (if applicable)")
    parser.add_argument(
        "--files", type=str, required=True,
        help="Comma-separated files, e.g. package.json,package-lock.json"
    )
    parser.add_argument("--node-version", type=str, required=False, help="NodeJS version (only for npm)")
    parser.add_argument("--npm-version", type=str, required=False, help="NPM version (only for npm)")
    parser.add_argument("--php-version", type=str, required=False, help="PHP version (only for composer)")
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout in seconds")
    return parser.parse_args()

def main():
    args = parse_args()
    endpoint = args.endpoint_url.rstrip("/")
    manager = args.manager.lower()
    api_key = args.apikey
    # Validate supported managers locally (or rely on server for full validation)
    supported = ["npm", "composer"]
    if manager not in supported:
        print(f"ERROR: Manager '{manager}' not supported. Options: {', '.join(supported)}")
        sys.exit(1)

    # Parse file list
    file_list = [f.strip() for f in args.files.split(",")]
    if len(file_list) < 2:
        print("ERROR: You must specify at least two files: definition + lockfile")
        sys.exit(1)
    # Verify existence of files
    for fp in file_list:
        if not os.path.isfile(fp):
            print(f"ERROR: File not found: {fp}")
            sys.exit(1)

    # Build versions dictionary
    versions = {}
    if manager == "npm":
        if args.node_version:
            versions["node"] = args.node_version
        if args.npm_version:
            versions["npm"] = args.npm_version
    elif manager == "composer":
        if args.php_version:
            versions["php"] = args.php_version

    # Calculate local hash
    hash_hex = HashCalculator.calculate_hash(manager, file_list, versions)
    print(f"[INFO] Calculated hash: {hash_hex}")

    # Read and encode files in base64
    files_b64 = {}
    for fp in file_list:
        with open(fp, "rb") as f:
            bcontent = f.read()
            files_b64[os.path.basename(fp)] = base64.b64encode(bcontent).decode("utf-8")

    # Build JSON payload
    payload = {
        "manager": manager,
        "hash": hash_hex,
        "files": files_b64,
        "versions": versions
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Send POST to /v1/cache
    url_cache = f"{endpoint}/v1/cache"
    print(f"[INFO] Sending request to {url_cache} ...")
    try:
        resp = requests.post(url_cache, headers=headers, data=json.dumps(payload), timeout=args.timeout)
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] HTTP connection failure: {e}")
        sys.exit(1)

    if resp.status_code == 401:
        print("ERROR: Unauthorized. Verify your API Key.")
        sys.exit(1)
    elif resp.status_code != 200:
        print(f"ERROR: Server returned code {resp.status_code}: {resp.text}")
        sys.exit(1)

    resp_data = resp.json()
    download_url = resp_data.get("download_url")
    cache_hit = resp_data.get("cache_hit", False)
    if not download_url:
        print("ERROR: Invalid server response (missing download_url).")
        sys.exit(1)

    if cache_hit:
        print("[INFO] Cache hit: downloading compressed package...")
    else:
        print("[INFO] Cache miss: server is generating dependencies. Downloading when ready...")

    # Download the ZIP
    try:
        zip_resp = requests.get(download_url, stream=True, timeout=args.timeout)
        if zip_resp.status_code != 200:
            print(f"ERROR: Could not download ZIP (status {zip_resp.status_code}).")
            sys.exit(1)
        # Create a temporary file for the ZIP
        tmp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        with open(tmp_zip.name, "wb") as f:
            for chunk in zip_resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        print(f"[INFO] ZIP downloaded at {tmp_zip.name}")
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Failed to download ZIP: {e}")
        sys.exit(1)

    # Extract ZIP to local dependency folder
    if manager == "npm":
        target_dir = os.path.join(os.getcwd(), "node_modules")
    elif manager == "composer":
        target_dir = os.path.join(os.getcwd(), "vendor")
    else:
        # Default: extract into "deps" folder
        target_dir = os.path.join(os.getcwd(), "deps")

    # Remove existing folder (if exists) to avoid conflicts
    if os.path.isdir(target_dir):
        print(f"[INFO] Removing existing folder: {target_dir}")
        import shutil
        shutil.rmtree(target_dir)

    os.makedirs(target_dir, exist_ok=True)
    with zipfile.ZipFile(tmp_zip.name, "r") as zip_ref:
        zip_ref.extractall(target_dir)
    print(f"[INFO] Dependencies extracted to: {target_dir}")

    # Optional: remove local ZIP
    os.remove(tmp_zip.name)
    print("[INFO] Process completed successfully.")
    sys.exit(0)

if __name__ == "__main__":
    main()
```

#### Comments on Client Pseudocode

1. **Modular Structure**:

   * `HashCalculator` is decoupled from the rest. If the algorithm changes (e.g., to SHA1), only that class is modified.
   * The pipeline is clearly defined (reading, hashing, sending, downloading).
   * Uses `requests` for HTTP.

2. **Validations**:

   * Checks for file existence.
   * Minimal validation of `manager`.
   * Handles HTTP status codes (200, 401, others).

3. **Exception Handling**:

   * Catches network errors (`RequestException`).
   * Exits with a non-zero code for traceability.

4. **ZIP Extraction**:

   * Removes any existing folder to avoid version mixing.
   * Extracts all contents into the folder indicated by `manager`.

---

### 8.2 Server Pseudocode

```python
#!/usr/bin/env python3
import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

# External dependencies:
# pip install fastapi uvicorn python-multipart aiofiles

from fastapi import FastAPI, HTTPException, UploadFile, File, Header, Request
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

# ---------------------------------------
# DOMAIN: Entities and Value Objects
# ---------------------------------------

class DependencySet:
    """
    Entity representing the unique combination of:
    - manager (npm, composer)
    - file contents (definition + lockfile)
    - optional versions (node, npm, php)
    """
    def __init__(self, manager: str, file_contents: Dict[str, bytes], versions: Dict[str, str]):
        self.manager = manager
        self.file_contents = file_contents  # {"package.json": b"...", "package-lock.json": b"..."}
        self.versions = versions            # {"node":"14.20.0", "npm":"6.14.13"}
        self.hash = self.calculate_hash()

    def calculate_hash(self) -> str:
        sha = hashlib.sha256()
        sha.update(self.manager.encode("utf-8"))
        sha.update(b"\n")
        for name in sorted(self.file_contents.keys()):
            content = self.file_contents[name]
            sha.update(content)
        for key in sorted(self.versions.keys()):
            val = self.versions[key]
            sha.update(f"{key}={val}\n".encode("utf-8"))
        return sha.hexdigest()

class CacheObject:
    """
    Represents the object cached on disk, with paths to:
    - output_folder: folder containing node_modules or vendor
    - meta_file: .hash file
    - zip_file: .zip file
    """
    def __init__(self, base_dir: Path, hash_hex: str, manager: str):
        self.hash = hash_hex
        self.manager = manager
        # Level-1 directory = first two chars, level-2 = next two
        h0_2 = hash_hex[0:2]
        h2_4 = hash_hex[2:4]
        self.cache_root = base_dir / "objects" / h0_2 / h2_4 / f"{hash_hex}.{manager}"
        self.output_folder_name = "node_modules" if manager == "npm" else "vendor"
        self.output_folder = self.cache_root / self.output_folder_name
        self.meta_file = self.cache_root / f"{hash_hex}.{manager}.hash"
        self.zip_file = self.cache_root / f"{hash_hex}.zip"

    def exists(self) -> bool:
        return self.cache_root.is_dir() and self.meta_file.is_file() and self.zip_file.is_file()

# ---------------------------------------
# DOMAIN: Interfaces / Repositories
# ---------------------------------------
class ICacheRepository:
    def get(self, cache_key: str) -> Optional[CacheObject]:
        raise NotImplementedError
    def save(self, cache_obj: CacheObject) -> None:
        raise NotImplementedError
    def compute_path(self, cache_key: str) -> Path:
        raise NotImplementedError

class FileSystemCacheRepository(ICacheRepository):
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        # Ensure 'objects' exists under base_dir
        (self.base_dir / "objects").mkdir(parents=True, exist_ok=True)

    def compute_path(self, cache_key: str) -> Path:
        # cache_key = "<hash>.<manager>"
        hash_hex, manager = cache_key.split(".")
        h0_2 = hash_hex[0:2]
        h2_4 = hash_hex[2:4]
        return self.base_dir / "objects" / h0_2 / h2_4 / cache_key

    def get(self, cache_key: str) -> Optional[CacheObject]:
        target = self.compute_path(cache_key)
        # Validate presence of meta_file and zip_file
        hash_hex, manager = cache_key.split(".")
        obj = CacheObject(self.base_dir, hash_hex, manager)
        if obj.exists():
            return obj
        return None

    def save(self, cache_obj: CacheObject) -> None:
        # Assume all files/folders already exist on disk
        # Just ensure the root path is created
        cache_obj.cache_root.mkdir(parents=True, exist_ok=True)
        # (Files have already been copied by the use case)
        # Metadata and ZIP are already created externally, so no further action
        return

# ---------------------------------------
# DOMAIN: Dependency Installers
# ---------------------------------------
class DependencyInstaller:
    """
    Common interface for generating dependencies:
    - npm: runs 'npm ci'
    - composer: runs 'composer install'
    """
    def __init__(self, versions: Dict[str, str]):
        self.versions = versions

    @property
    def output_folder_name(self) -> str:
        raise NotImplementedError

    def install(self, work_dir: Path) -> None:
        """
        Must copy definition files into work_dir, then run the install command
        and produce the output folder under work_dir / output_folder_name
        """
        raise NotImplementedError

class NpmInstaller(DependencyInstaller):
    @property
    def output_folder_name(self) -> str:
        return "node_modules"

    def install(self, work_dir: Path) -> None:
        # Optional: Install specific Node and NPM versions (via nvm or similar)
        node_version = self.versions.get("node")
        npm_version = self.versions.get("npm")
        # (In this pseudocode, assume the correct versions are already installed on the host)
        # Run npm ci in work_dir
        cmd = ["npm", "ci", "--ignore-scripts", "--cache", str(work_dir / ".npm_cache")]
        # Example: if using npx to run a specific version
        # if node_version: cmd = ["npx", f"node@{node_version}", ...]
        process = subprocess.run(cmd, cwd=str(work_dir), capture_output=True)
        if process.returncode != 0:
            # Raise exception to propagate error
            raise RuntimeError(f"npm ci failed: {process.stderr.decode()}")

class ComposerInstaller(DependencyInstaller):
    @property
    def output_folder_name(self) -> str:
        return "vendor"

    def install(self, work_dir: Path) -> None:
        php_version = self.versions.get("php")
        # Run composer install
        cmd = ["composer", "install", "--no-dev", "--prefer-dist", "--no-interaction", "--no-scripts"]
        process = subprocess.run(cmd, cwd=str(work_dir), capture_output=True)
        if process.returncode != 0:
            raise RuntimeError(f"composer install failed: {process.stderr.decode()}")

class InstallerFactory:
    def get_installer(self, manager: str, versions: Dict[str, str]) -> DependencyInstaller:
        if manager == "npm":
            return NpmInstaller(versions)
        elif manager == "composer":
            return ComposerInstaller(versions)
        else:
            raise ValueError(f"Installer not implemented for manager '{manager}'")

# ---------------------------------------
# DOMAIN: Compression / Metadata Utilities
# ---------------------------------------
class ZipUtil:
    @staticmethod
    def list_all_files(root: Path) -> List[Path]:
        """
        Returns a list of relative Paths for all files under 'root'
        """
        files = []
        for dirpath, _, filenames in os.walk(root):
            for fn in filenames:
                full_path = Path(dirpath) / fn
                rel = full_path.relative_to(root)
                files.append(rel)
        return files

    @staticmethod
    def compute_checksums(root: Path) -> Dict[str, str]:
        """
        For each file in root, compute sha256 and return dict {relative_path: checksum}
        """
        checksums = {}
        for rel in ZipUtil.list_all_files(root):
            full = root / rel
            sha = hashlib.sha256()
            with open(full, "rb") as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    sha.update(chunk)
            checksums[str(rel)] = sha.hexdigest()
        return checksums

    @staticmethod
    def write_metadata(cache_dir: Path, hash_hex: str, manager: str,
                       file_list: List[Path], checksums: Dict[str, str]) -> None:
        """
        Writes the file <hash>.<manager>.hash inside cache_dir,
        with lines formatted: relative_path;size;checksum
        """
        meta_path = cache_dir / f"{hash_hex}.{manager}.hash"
        with open(meta_path, "w", encoding="utf-8") as meta_f:
            for rel in sorted(file_list):
                full = cache_dir / manager / rel if manager == "npm" else cache_dir / manager / rel
                size = (cache_dir / rel).stat().st_size if (cache_dir / rel).exists() else 0
                chksum = checksums.get(str(rel), "")
                # Form line
                line = f"{rel};{size};{chksum}\n"
                meta_f.write(line)

    @staticmethod
    def compress_folder(src_folder: Path, zip_path: Path) -> None:
        """
        Compresses src_folder contents into zip_path (without including the root folder).
        """
        parent = zip_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for dirpath, _, filenames in os.walk(src_folder):
                for fn in filenames:
                    full = Path(dirpath) / fn
                    rel = full.relative_to(src_folder)
                    zf.write(full, arcname=str(rel))

# ---------------------------------------
# DOMAIN: API Key Validator
# ---------------------------------------
class ApiKeyValidator:
    def __init__(self, valid_keys: List[str]):
        # Store keys in memory; they could be hashed or encrypted if needed
        self.keys = set(valid_keys)

    def validate(self, api_key: str) -> bool:
        return api_key in self.keys

# ---------------------------------------
# APPLICATION: Use Cases
# ---------------------------------------
class CacheRequestDTO(BaseModel):
    manager: str
    hash: str
    files: Dict[str, str]       # base64: {"package.json": "<...>", ...}
    versions: Dict[str, str]    # {"node":"14.20.0","npm":"6.14.13"}

class CacheResponseDTO(BaseModel):
    download_url: str
    cache_hit: bool

class HandleCacheRequest:
    def __init__(self, cache_repo: ICacheRepository, installer_factory: InstallerFactory, zip_util: ZipUtil):
        self.cache_repo = cache_repo
        self.installer_factory = installer_factory
        self.zip_util = zip_util

    def execute(self, request_dto: CacheRequestDTO, base_download_url: str) -> CacheResponseDTO:
        cache_key = f"{request_dto.hash}.{request_dto.manager}"
        cache_obj = self.cache_repo.get(cache_key)
        if cache_obj and cache_obj.exists():
            # Cache Hit
            download_url = f"{base_download_url}/download/{request_dto.hash}.zip"
            return CacheResponseDTO(download_url=download_url, cache_hit=True)
        # Cache Miss → generate dependencies
        # 1) Create temp directory
        temp_dir = Path(tempfile.mkdtemp(prefix=cache_key))
        # 2) Decode base64 files and write in temp_dir
        for fname, b64 in request_dto.files.items():
            data = base64.b64decode(b64)
            fpath = temp_dir / fname
            with open(fpath, "wb") as wf:
                wf.write(data)
        # 3) Install dependencies
        installer = self.installer_factory.get_installer(request_dto.manager, request_dto.versions)
        # Copy lockfile to root of installation folder (many managers expect the file in cwd)
        # Assume workdir: temp_dir
        try:
            installer.install(temp_dir)
        except Exception as e:
            # Clean up temp and raise error 500
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise e

        # 4) Copy generated folder to cache_dir
        cache_path = self.cache_repo.compute_path(cache_key)
        # Destination folder: <cache_dir>/objects/.../<hash>.<manager>/node_modules (or vendor)
        final_output = cache_path / installer.output_folder_name
        final_output.parent.mkdir(parents=True, exist_ok=True)
        # Recursively copy temp_dir/node_modules → final_output
        shutil.copytree(temp_dir / installer.output_folder_name, final_output)

        # 5) Generate metadata
        file_list = self.zip_util.list_all_files(final_output)
        checksums = self.zip_util.compute_checksums(final_output)
        self.zip_util.write_metadata(cache_path, request_dto.hash, request_dto.manager, file_list, checksums)

        # 6) Compress cache
        zip_path = cache_path / f"{request_dto.hash}.zip"
        self.zip_util.compress_folder(final_output, zip_path)

        # 7) Persist cache_obj in repo
        cache_obj = CacheObject(cache_path.parent.parent.parent, request_dto.hash, request_dto.manager)
        self.cache_repo.save(cache_obj)

        # 8) Clean up temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)

        download_url = f"{base_download_url}/download/{request_dto.hash}.zip"
        return CacheResponseDTO(download_url=download_url, cache_hit=False)

# ---------------------------------------
# INTERFACES / ENTRYPOINT: FastAPI Server
# ---------------------------------------
def create_app(cache_dir: Path, is_public: bool, api_keys: List[str], base_download_url: str) -> FastAPI:
    app = FastAPI()
    cache_repo = FileSystemCacheRepository(cache_dir)
    installer_factory = InstallerFactory()
    zip_util = ZipUtil()
    validator = ApiKeyValidator(api_keys) if not is_public else None
    handler = HandleCacheRequest(cache_repo, installer_factory, zip_util)

    # Route to generate or retrieve cache
    @app.post("/v1/cache", response_model=CacheResponseDTO)
    async def cache_endpoint(request: Request):
        # API Key
        if not is_public:
            auth: Optional[str] = request.headers.get("Authorization")
            if not auth or not auth.startswith("Bearer "):
                raise HTTPException(status_code=401, detail="Missing Authorization Bearer <APIKEY>")
            key = auth.split(" ")[1]
            if not validator.validate(key):
                raise HTTPException(status_code=401, detail="Invalid API Key")

        payload = await request.json()
        try:
            dto = CacheRequestDTO(**payload)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")

        # Validate supported manager
        supported = ["npm", "composer"]
        if dto.manager not in supported:
            raise HTTPException(status_code=400, detail=f"Manager not supported: {dto.manager}")

        # Invoke use case
        try:
            response_dto = handler.execute(dto, base_download_url)
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=f"Error generating dependencies: {e}")
        return JSONResponse(status_code=200, content=response_dto.dict())

    # Route to download the ZIP
    @app.get("/download/{hash}.zip")
    async def download_endpoint(hash: str):
        # Note: no API key is validated here; the user already provided it when creating
        # Optionally, additional control (TTL, unique tokens, etc.) could be implemented
        # Build the disk path
        # To derive manager, try both possible managers
        for manager in ["npm", "composer"]:
            h0_2 = hash[0:2]
            h2_4 = hash[2:4]
            cache_path = cache_dir / "objects" / h0_2 / h2_4
            folder = cache_path / f"{hash}.{manager}"
            zip_path = folder / f"{hash}.zip"
            if zip_path.is_file():
                return FileResponse(zip_path, filename=f"{hash}.zip", media_type="application/zip")
        raise HTTPException(status_code=404, detail="ZIP not found")

    return app

def parse_args():
    parser = argparse.ArgumentParser(description="DepCacheProxy Server")
    parser.add_argument("port", type=int, help="HTTP port to listen on (e.g., 8080)")
    parser.add_argument("--cache_dir", type=str, required=True, help="Base cache directory")
    parser.add_argument("--is_public", action="store_true", default=False, help="If set, server is public (no API key)")
    parser.add_argument("--api-keys", type=str, required=False, help="Comma-separated list of valid API keys")
    return parser.parse_args()

def main():
    args = parse_args()
    port = args.port
    cache_dir = Path(args.cache_dir)
    is_public = args.is_public
    api_keys = []
    if not is_public:
        if not args.api_keys:
            print("ERROR: You must provide --api-keys when not public.")
            sys.exit(1)
        api_keys = [k.strip() for k in args.api_keys.split(",") if k.strip()]
    # Verify cache_dir is writable
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"ERROR: Cannot create/access cache_dir '{cache_dir}': {e}")
        sys.exit(1)

    # Construct base_download_url (without trailing slash)
    base_download_url = f"http://localhost:{port}"
    # Create FastAPI app
    app = create_app(cache_dir, is_public, api_keys, base_download_url)
    # Run with Uvicorn
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
```

#### Comments on Server Pseudocode

1. **DDD Structure**

   * Divided into `domain/` (entities: `DependencySet`, `CacheObject`; repository: `ICacheRepository`), `application/` (`HandleCacheRequest`), `infrastructure/` (`FileSystemCacheRepository`, `NpmInstaller`, `ComposerInstaller`, `ZipUtil`, `ApiKeyValidator`) and `interfaces/` (`create_app`, endpoints).

2. **API Key Validation**

   * Performed at the start of `cache_endpoint`. If it fails, a `HTTPException(401)` is thrown.

3. **Dependency Installation**

   * `InstallerFactory` chooses the correct `DependencyInstaller` based on `manager`.
   * Each `DependencyInstaller` implements `install(work_dir)` and throws an exception if it fails.

4. **File System Persistence**

   * `FileSystemCacheRepository` stores the structure as created by the use case.
   * The `get(cache_key)` method builds a `CacheObject` temporarily and calls `exists()`.

5. **Metadata and ZIP Generation**

   * `ZipUtil.list_all_files()` obtains a recursive list of files in the dependencies folder.
   * `ZipUtil.compute_checksums()` computes SHA256 for each file.
   * `ZipUtil.write_metadata()` writes the `.hash` file with `path;size;checksum`.
   * `ZipUtil.compress_folder()` generates the ZIP, which is then served by `FileResponse`.

6. **HTTP Routes**

   * `POST /v1/cache`: receives JSON, returns JSON with URL and cache status (hit/miss).
   * `GET /download/{hash}.zip`: looks in both managers (`npm`, `composer`) for the ZIP and returns it.

7. **Errors and Exceptions**

   * If `manager` not supported → `400 Bad Request`.
   * If error during dependency installation → `500 Internal Server Error`.
   * If ZIP not found when attempting download → `404 Not Found`.

8. **Concurrency**

   * FastAPI + Uvicorn allow asynchronous concurrency.
   * Concurrent `POST /v1/cache` requests for the same hash can cause a “race condition” when copying folders.

     * It is recommended to implement a **locking** mechanism (e.g., a `.lock` file or use of `asyncio.Lock`) per `cache_key` so only one process generates the same hash at a time; others wait.

---

## 9. HTTP API and Route Schema

### 9.1 Main Routes

| Method | Route                  | Description                                          | Request Body                 | Responses                                                                                                                           |
| ------ | ---------------------- | ---------------------------------------------------- | ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| POST   | `/v1/cache`            | Request dependency cache: hit/miss and download URL. | JSON (see `CacheRequestDTO`) | `200 OK` → `{ download_url: str, cache_hit: bool }` <br> `400 Bad Request` <br> `401 Unauthorized` <br> `500 Internal Server Error` |
| GET    | `/download/{hash}.zip` | Download the generated ZIP for the provided hash.    | None                         | `200 OK` → ZIP <br> `404 Not Found`                                                                                                 |

### 9.2 Request and Response Schema

#### 9.2.1 `CacheRequestDTO`

```jsonc
{
  "manager": "npm",
  "hash": "ab12cd34ef56...",
  "files": {
    "package.json": "<base64_content>",
    "package-lock.json": "<base64_content>"
  },
  "versions": {
    "node": "14.20.0",
    "npm": "6.14.13"
  }
}
```

* **Fields**:

  * `manager` (string, required): dependency manager identifier (`npm`, `composer`, etc.).
  * `hash` (string, required): SHA256 hash calculated by the client.
  * `files` (map\<string, string>, required): dictionary mapping filename → Base64-encoded content.
  * `versions` (map\<string, string>, optional): key/value pairs of versions. E.g., `{ "node": "14.20.0", "npm": "6.14.13" }` for NPM; `{ "php": "8.1.0" }` for Composer.

#### 9.2.2 `CacheResponseDTO`

```jsonc
{
  "download_url": "http://server:8080/download/ab12cd34ef56....zip",
  "cache_hit": true
}
```

* **Fields**:

  * `download_url` (string, required): absolute URL to download the ZIP.
  * `cache_hit` (boolean, required): indicates if it was a “hit” (existing cache) or “miss” (generated).

---

## 10. Usage Scenarios and Test Cases

Below are different usage scenarios with expected inputs and validations.

### 10.1 Scenario 1: NPM Cache Hit (Public Server)

1. **Client invokes**:

   ```bash
   dep_cache_proxy_client http://localhost:8080 npm --files=package.json,package-lock.json
   ```
2. **Client**:

   * Calculates hash (e.g., `ff0033aa...`).
   * Sends `POST /v1/cache` with payload (no Authorization, since the server is public).
3. **Server**:

   * `is_public = True` → does not validate the key.
   * `manager="npm"` supported.
   * `cache_key="ff0033aa....npm"`.
   * `cache_repo.get("ff0033aa....npm")` → returns `CacheObject` because it exists.
   * Responds `200 OK` with JSON:

     ```jsonc
     { "download_url": "http://localhost:8080/download/ff0033aa....zip", "cache_hit": true }
     ```
4. **Client**:

   * Downloads the ZIP and extracts it into `./node_modules/`.
   * Completes successfully.

**Tests**:

* Verify that `download_url` points to an existing, valid ZIP.
* Confirm that the `node_modules/` folder matches the expected content and version.

---

### 10.2 Scenario 2: Composer Cache Miss (Server with API Key)

1. **Server** started with:

   ```bash
   dep_cache_proxy_server 8080 --cache_dir=./cache --api-keys=KEY1,KEY2
   ```
2. **Client invokes**:

   ```bash
   dep_cache_proxy_client http://localhost:8080 composer --apikey=KEY1 --files=composer.json,composer.lock --php-version=8.1.0
   ```
3. **Client**:

   * Calculates hash (e.g., `aa11bb22...`).
   * Sends `POST /v1/cache` with `Authorization: Bearer KEY1` and payload.
4. **Server**:

   * Validates API key `KEY1` → OK.
   * `manager="composer"`, hash doesn’t exist in cache.
   * Creates `temp_dir="tmp/aa11bb22..."`.
   * Writes `composer.json` + `composer.lock` into temp.
   * Runs `composer install --no-dev --prefer-dist` in temp.

     * Result: `temp/vendor/` with dependencies.
   * Copies `temp/vendor/` to `cache/objects/aa/11/aa11bb22....composer/vendor/`.
   * Computes file list and checksums.
   * Writes `cache/objects/aa/11/aa11bb22....composer/aa11bb22....composer.hash`.
   * Compresses to `cache/objects/aa/11/aa11bb22....composer/aa11bb22....zip`.
   * Cleans up `temp_dir`.
   * Returns `200 OK` with `{"download_url":"http://localhost:8080/download/aa11bb22....zip", "cache_hit": false}`.
5. **Client**:

   * Downloads the ZIP and extracts into `./vendor/`.
   * Completes successfully.

**Tests**:

* Verify structure under `cache/objects/aa/11/aa11bb22....composer/`.
* Confirm that `composer install` runs properly on the server/container.
* Confirm that `cache_hit` becomes `true` on a subsequent call with the same files.

---

### 10.3 Scenario 3: Request with Invalid API Key

1. **Client invokes**:

   ```bash
   dep_cache_proxy_client http://localhost:8080 npm --apikey=INVALID --files=package.json,package-lock.json
   ```
2. **Server**:

   * Receives `Authorization: Bearer INVALID`.
   * `validator.validate("INVALID")` → `False`.
   * Returns `401 Unauthorized` with JSON:

     ```jsonc
     { "detail": "Invalid API Key" }
     ```
3. **Client**:

   * Detects `resp.status_code == 401` and exits with an error message.

---

### 10.4 Scenario 4: Unsupported Manager

1. **Client invokes**:

   ```bash
   dep_cache_proxy_client http://localhost:8080 pip --files=requirements.txt,requirements.lock
   ```
2. **Client**:

   * `manager="pip"` is not in `supported=["npm","composer"]`.
   * Prints: `ERROR: Manager 'pip' not supported. Options: npm, composer` and exits.

*Optionally*, if validation were moved to the server:

* The server would receive the `POST` and return `400 Bad Request` with detail “Manager not supported: pip”.

---

## 11. Security, Scalability, and Common Errors Notes

### 11.1 Security

1. **Input Validation**

   * The `manager` field must be compared against a whitelist of allowed managers.
   * Filenames (`package.json`, etc.) are assumed safe; nevertheless, do not permit relative paths with `../`.
   * **Do not execute potentially malicious scripts**:

     * For NPM, use `--ignore-scripts` to prevent running `preinstall`/`postinstall`.
     * For Composer, use `--no-scripts` to avoid hooks.

2. **Command Injection**

   * When forming the `npm ci` or `composer install` command, do not concatenate strings insecurely.
   * Use argument lists in `subprocess.run([...])`.

3. **API Key**

   * Store keys in memory (or in a secure store).
   * Compare with constant-time comparison to avoid timing attacks.
   * Do not log `--api-keys` in plaintext.

4. **ZIP Delivery**

   * Serve files only from `cache/objects`. Avoid exposing arbitrary file system paths.
   * Prevent clients from downloading any other file on the server (do not expose file system routes).

5. **HTTPS**

   * The server **does not** support HTTPS natively. Use a reverse proxy (Nginx, Traefik) for TLS/SSL.

---

### 11.2 Scalability and Concurrency

1. **Serving Multiple Concurrent Requests**

   * FastAPI + Uvicorn (configured with multiple workers) provides concurrency.
   * Avoid race conditions:

     * **Lock per hash**: If two clients request the same `hash` simultaneously, both might enter the “cache miss” block. The first generates the cache; the second tries to generate at the same time → possible corruption.
     * **Solutions**:

       * Use a file-system lock, e.g., `flock` on a file `<cache_path>.lock`.
       * Or use an in-memory lock: `locks = {}` with `asyncio.Lock` keyed by `cache_key`.

2. **Cache Size**

   * Configure retention policies:

     * Maximum number of entries.
     * Expire caches older than N days.
     * Provide manual deletion (`delete(cache_key)`).

3. **Using S3 or Others**

   * Instead of `FileSystemCacheRepository`, implement an `S3CacheRepository`, storing objects (folders and ZIPs) in an S3 bucket.
   * Keep metadata locally (e.g., in an RDS database) or in DynamoDB, pointing to S3 URLs.

---

### 11.3 Common Errors and How to Handle Them

1. **Hash Mismatch between Client and Server**

   * Ensure the hash algorithm is identical.
   * Verify that files are sorted correctly and `versions` keys are sorted the same way.

2. **Failure in `npm ci` or `composer install`**

   * Check that the correct versions of Node/NPM/PHP/Composer exist on the server.
   * Inspect logs (`stdout` and `stderr`) to detect compatibility issues.
   * The server should report the exact error to the client (500 with detail).

3. **Directory Permissions**

   * Ensure `cache_dir` is writable by the process user.
   * If the server runs without root permissions, verify the user can write to `cache_dir`.

4. **Improper Temporary Folder Cleanup**

   * If the install process fails, remove the temporary folder (`temp_dir`) to avoid leftover artifacts.
   * Use `shutil.rmtree(temp_dir, ignore_errors=True)` in a `finally` block.

5. **ZIP Exceeds Allowed Size**

   * Some proxies or HTTP clients limit response size.
   * Consider chunked transfer or resumable downloads (beyond initial version scope).

---

## 12. Conclusions

The **DepCacheProxy** project (`dep_cache_proxy`) provides a generic, scalable solution to cache and serve dependencies for package managers like NPM or Composer, accelerating build pipelines and mitigating unstable network issues. By following DDD and SOLID principles, it achieves a modular, maintainable, and extensible architecture:

* **Domain**: Entities `DependencySet` and `CacheObject`, repository `ICacheRepository`.
* **Application**: Use case `HandleCacheRequest` orchestrates validation, dependency generation, and compression logic.
* **Infrastructure**: `FileSystemCacheRepository`, `NpmInstaller`, `ComposerInstaller`, `ZipUtil`, `ApiKeyValidator`.
* **Interfaces**: FastAPI for server (`POST /v1/cache`, `GET /download/{hash}.zip`), CLI client using `requests` and `argparse`.

The provided pseudocode can serve as a direct basis for implementing the library in Python. Comprehensive testing, CI integration, and Docker deployment are recommended, mounting `cache_dir` as a volume and configuring a reverse proxy for TLS.