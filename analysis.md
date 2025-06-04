# Análisis Actualizado de **DepCacheProxy** (`dep_cache_proxy`)

Este documento corrige y amplía el diseño de **DepCacheProxy** para reflejar que en `cache/objects` **no** se guardan las carpetas completas `node_modules` ni `vendor`, sino únicamente **objetos individuales** (archivos) identificados por su hash. El índice de cada conjunto mapea rutas relativas a hashes de archivos, y el ZIP final se genera reconociendo esos blobs.

---

## Tabla de Contenidos

- [Análisis Actualizado de **DepCacheProxy** (`dep_cache_proxy`)](#análisis-actualizado-de-depcacheproxy-dep_cache_proxy)
  - [Tabla de Contenidos](#tabla-de-contenidos)
  - [1. Objetivos y Contexto](#1-objetivos-y-contexto)
  - [2. Requisitos Funcionales y No Funcionales](#2-requisitos-funcionales-y-no-funcionales)
    - [2.1 Requisitos Funcionales (RF)](#21-requisitos-funcionales-rf)
    - [2.2 Requisitos No Funcionales (RNF)](#22-requisitos-no-funcionales-rnf)
  - [3. Visión General de la Arquitectura (DDD + SOLID)](#3-visión-general-de-la-arquitectura-ddd--solid)
  - [4. Componentes Principales](#4-componentes-principales)
    - [4.1 Cliente (`dep_cache_proxy_client`)](#41-cliente-dep_cache_proxy_client)
      - [4.1.1 Objetivos](#411-objetivos)
      - [4.1.2 Módulos](#412-módulos)
      - [4.1.3 Argumentos CLI](#413-argumentos-cli)
    - [4.2 Servidor (`dep_cache_proxy_server`)](#42-servidor-dep_cache_proxy_server)
      - [4.2.1 Objetivos](#421-objetivos)
      - [4.2.2 Módulos](#422-módulos)
      - [4.2.3 Argumentos CLI Servidor](#423-argumentos-cli-servidor)
  - [5. Modelo de Dominio y Hashing](#5-modelo-de-dominio-y-hashing)
    - [5.1 Constantes de Hash (`hash_constants.py`)](#51-constantes-de-hash-hash_constantspy)
    - [5.2 Entidad: `DependencySet` (`dependency_set.py`)](#52-entidad-dependencyset-dependency_setpy)
    - [5.3 Interfaz: `ICacheRepository` (`cache_repository.py`)](#53-interfaz-icacherepository-cache_repositorypy)
    - [5.4 Lógica de Blobs de Archivos (`blob_storage.py`)](#54-lógica-de-blobs-de-archivos-blob_storagepy)
  - [6. Estructura de Directorios en Cache](#6-estructura-de-directorios-en-cache)
  - [7. Flujo de Trabajo Completo](#7-flujo-de-trabajo-completo)
  - [8. Detalles de Implementación y Pseudocódigo](#8-detalles-de-implementación-y-pseudocódigo)
    - [8.1 Pseudocódigo Cliente](#81-pseudocódigo-cliente)
    - [8.2 Pseudocódigo Servidor](#82-pseudocódigo-servidor)
    - [8.3 Funciones Auxiliares Comunes](#83-funciones-auxiliares-comunes)
      - [8.3.1 `ZipUtil` para ZIP a partir de blobs (`zip_util.py`)](#831-ziputil-para-zip-a-partir-de-blobs-zip_utilpy)
  - [9. API HTTP y Esquema de Rutas](#9-api-http-y-esquema-de-rutas)
    - [9.1 Rutas](#91-rutas)
    - [9.2 `CacheRequestDTO`](#92-cacherequestdto)
    - [9.3 `CacheResponseDTO`](#93-cacheresponsedto)
  - [10. Estructura de Pruebas](#10-estructura-de-pruebas)
    - [10.1 Pruebas Unitarias](#101-pruebas-unitarias)
    - [10.2 Pruebas de Integración](#102-pruebas-de-integración)
    - [10.3 Pruebas Funcionales](#103-pruebas-funcionales)
    - [10.4 Pruebas End-to-End](#104-pruebas-end-to-end)
  - [11. Escenarios de Uso y Casos de Prueba](#11-escenarios-de-uso-y-casos-de-prueba)
    - [11.1 Escenario 1: Cache Hit en NPM](#111-escenario-1-cache-hit-en-npm)
    - [11.2 Escenario 2: Cache Miss en Composer](#112-escenario-2-cache-miss-en-composer)
    - [11.3 Escenario 3: Versión no soportada sin Docker](#113-escenario-3-versión-no-soportada-sin-docker)
    - [11.4 Escenario 4: Versión no soportada con Docker](#114-escenario-4-versión-no-soportada-con-docker)
  - [12. Notas de Seguridad, Escalabilidad y Errores Comunes](#12-notas-de-seguridad-escalabilidad-y-errores-comunes)
    - [12.1 Seguridad](#121-seguridad)
    - [12.2 Escalabilidad](#122-escalabilidad)
    - [12.3 Errores Comunes](#123-errores-comunes)
  - [13. Facilidad para Añadir Nuevos Managers](#13-facilidad-para-añadir-nuevos-managers)
  - [14. Conclusiones](#14-conclusiones)

---

## 1. Objetivos y Contexto

Este análisis documenta el diseño de **DepCacheProxy** con las siguientes prioridades:

1. **Cachear dependencias mediante blobs de archivos**  
   - Cada archivo (por ejemplo, `file.js`, `subfolder/file.js`) dentro de `node_modules/` o `vendor/` se almacena como un “objeto” individual en `cache/objects`, usando un hash de su contenido como nombre de archivo.  
   - Se evita guardar la estructura de carpetas completa en `cache/objects`.  

2. **Índice de ruta → hash**  
   - Para cada conjunto de dependencias (bundle), se genera un índice JSON que mapea rutas relativas (por ejemplo, `"file.js"`, `"subfolder/file.js"`) a hashes de archivos.  
   - Ese índice se guarda en `cache/indices` con nombre `<bundle_hash>.<manager>.<manager_version>.index`.  

3. **ZIP reconstruido desde blobs**  
   - Cuando el servidor necesita entregar el ZIP al cliente, lee el índice y, para cada entrada, recupera el blob correspondiente de `cache/objects/<h0h1>/<h2h3>/<file_hash>` y lo añade al ZIP en la ruta adecuada.  
   - El ZIP generado se almacena en `cache/bundles/<bundle_hash>.zip` (se puede omitir el almacenamiento permanente si se reconstruye a demanda).  

4. **Soporte de versiones y Docker**  
   - Igual que antes: validar versiones contra lo soportado; si no coincide y `--use-docker-on-version-mismatch=true`, usar Docker para instalar en contenedor.  

5. **Estructura DDD + SOLID**  
   - Dominio, aplicación e infraestructura separados.  
   - Módulos con responsabilidad única.  

6. **Pruebas**  
   - Definición de pruebas unitarias, integración, funcionales y end-to-end.  

7. **Extensibilidad a nuevos managers**  
   - Patrón Factory/Strategy para `DependencyInstaller`.  

8. **Implementación en Python**  
   - Constantes para algoritmo de hash (`HASH_ALGORITHM`, `HASH_BLOCK_SIZE`).  
   - Gestión de carpetas temporales para instalar dependencias.  

---

## 2. Requisitos Funcionales y No Funcionales

### 2.1 Requisitos Funcionales (RF)

1. **RF1**: El cliente CLI (`dep_cache_proxy_client`) debe aceptar:
   - `<endpoint_url>` (URL del servidor).
   - `<manager>` (ej. `npm`, `composer`).
   - `--apikey=<APIKEY>` (opcional si el servidor es público).
   - `--files=<file1>,<file2>` (definición + lockfile).
   - **Opciones de versión** (opcionales en cliente, obligatorias en servidor):
     - `--node-version=<VERSIÓN>` y `--npm-version=<VERSIÓN>` (para `npm`).
     - `--php-version=<VERSIÓN>` (para `composer`).

2. **RF2**: El servidor CLI (`dep_cache_proxy_server`) debe aceptar:
   - `<port>` (puerto HTTP).
   - `--cache_dir=<CACHE_DIR>` (directorio base para cache).
   - `--supported-versions-node=<NODE_VER1>:<NPM_VER1>,<NODE_VER2>:<NPM_VER2>,...`.
   - `--supported-versions-php=<PHP_VER1>,<PHP_VER2>,...`.
   - `--use-docker-on-version-mismatch` (booleano, usar Docker si la versión no está soportada).
   - `--is_public` (booleano, default `false`).
   - `--api-keys=<KEY1>,<KEY2>,...` (requerido si `--is_public=false`).

3. **RF3**: Cálculo de **bundle hash**:
   - Usar constantes:
     ```python
     HASH_ALGORITHM = "sha256"
     HASH_BLOCK_SIZE = 8192
     ```
   - Incluir en el hash (determinista):
     1. `manager` (p. ej. `"npm"`).
     2. Versiones solicitadas (por ejemplo, `"node=14.20.0"`, `"npm=6.14.13"`, `"php=8.1.0"`).
     3. Contenido de cada fichero (`.json` y `.lock`), en orden alfabético por nombre de fichero.

4. **RF4**: Cache de **blobs de archivos**:
   - En `cache/objects/` se almacenan únicamente **archivos individuales**, no carpetas.
   - Cada archivo recibe un hash propio (SHA256) basado en su contenido.
   - La ruta en disco de un blob de archivo `file.js` con `file_hash = "aabb12323232322..."` es:
     ```
     cache/objects/aa/bb/aabb12323232322...  
     ```
     (dos niveles basados en los dos primeros pares de caracteres hex de `file_hash`).

5. **RF5**: Índice de cada bundle:
   - Para cada bundle (bundle_hash generado a partir de `package.json`, `package.lock`, versiones, etc.), se crea un archivo JSON en:
     ```
     cache/indices/<bundle_hash>.<manager>.<manager_version>.index
     ```
   - Formato de índice (JSON):
     ```json
     {
       "file.js": "aabb12323232322...",
       "subfolder/file.js": "eecc1232132132121...",
       "...": "..."
     }
     ```
   - Este índice mapea ruta relativa → hash de blob.

6. **RF6**: ZIP reconstruido:
   - Para entregar el ZIP al cliente:
     1. Leer índice del bundle.
     2. Para cada clave `"ruta_relativa"` y valor `"file_hash"`:
        - Leer blob `cache/objects/<h0h1>/<h2h3>/<file_hash>`.
        - Añadirlo al ZIP con `arcname=ruta_relativa`.
     3. Generar `<bundle_hash>.zip` y almacenarlo en:
        ```
        cache/bundles/<bundle_hash>.zip
        ```
     - Opcional: regenerar cada vez o mantener persistido el ZIP.

7. **RF7**: Validación de versiones en servidor:
   - Para `npm`: tuple `(node_version, npm_version)` debe existir en `supported_versions_node`.
   - Para `composer`: `php_version` debe existir en `supported_versions_php`.
   - Si no coincide:
     - Si `--use-docker-on-version-mismatch=false`: responder `400 Bad Request`.
     - Si `--use-docker-on-version-mismatch=true`: usar Docker para instalar dependencias en un contenedor con la versión solicitada.

8. **RF8**: Cliente:
   - Calcular **bundle hash** localmente (usando constantes).
   - Enviar JSON al servidor con:
     - `manager`, `hash`, `files` (Base64), `versions`.
   - Recibir `download_url` y `cache_hit`.
   - Descargar ZIP y extraer en carpeta local de dependencias (`node_modules/` o `vendor/`).

9. **RF9**: Pruebas:
   - **Unitarias**:
     - `HashCalculator`.
     - `ApiKeyValidator`.
     - `InstallerFactory`.
     - `ZipUtil` (listado, checksums, ZIP).
   - **Integración**:
     - `HandleCacheRequest` (hit y miss).
     - Verificar `cache/objects`, `cache/indices` e `indices`.
   - **Funcionales**:
     - `dep_cache_proxy_client` → servidor FastAPI.
     - `GET /download/{bundle_hash}.zip`.
   - **End-to-End**:
     - Con contenedores Docker servidor+cliente.
     - Verificar extracción completa.

### 2.2 Requisitos No Funcionales (RNF)

1. **RNF1 (Eficiencia)**:
   - Hash en streaming (`HASH_BLOCK_SIZE`).
   - Evitar duplicar blobs (si el mismo archivo ya existe, no sobrescribir).

2. **RNF2 (Escalabilidad)**:
   - Concurrencia segura: evitar que dos peticiones simultáneas al mismo bundle generen blobs duplicados.
   - Locks por `bundle_hash` durante el almacenamiento.

3. **RNF3 (Extensibilidad)**:
   - Patrón Factory para `DependencyInstaller` (poder agregar Yarn, Pip, etc.).
   - Documentar pasos para añadir un nuevo manager.

4. **RNF4 (Seguridad)**:
   - Saneamiento de `manager`, `versions`.
   - `--ignore-scripts` y `--no-scripts` para NPM/Composer.
   - Comandos Docker parametrizados, sin inyección de comandos.

5. **RNF5 (Portabilidad)**:
   - Python 3.x en Linux/macOS.
   - Docker opcional, cuando se exija instalación con versiones no soportadas localmente.

6. **RNF6 (Mantenibilidad)**:
   - PEP8, type hints, docstrings.
   - Pruebas en `pytest`.
   - Separación DDD + SOLID.

7. **RNF7 (Disponibilidad)**:
   - Servidor sin HTTPS nativo; típico detrás de proxy TLS.

---

## 3. Visión General de la Arquitectura (DDD + SOLID)

````

dep\_cache\_proxy/
├── client/
│   ├── cli.py
│   ├── hash\_calculator.py
│   ├── http\_client.py
│   └── downloader.py
├── server/
│   ├── domain/
│   │   ├── hash\_constants.py
│   │   ├── dependency\_set.py
│   │   ├── cache\_repository.py
│   │   ├── blob\_storage.py
│   │   ├── installer.py
│   │   └── zip\_util.py
│   ├── infrastructure/
│   │   ├── file\_system\_cache\_repository.py
│   │   ├── api\_key\_validator.py
│   │   └── docker\_utils.py
│   ├── application/
│   │   ├── dtos.py
│   │   └── handle\_cache\_request.py
│   └── interfaces/
│       └── main.py
├── cache/
│   ├── objects/
│   │   └── (blobs por hash)
│   ├── indices/
│   │   └── (índices bundle → {ruta: file\_hash})
│   └── bundles/
│       └── (ZIPs de cada bundle)
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── functional/
│   └── e2e/
└── README.md

````

- `hash_constants.py`: constantes de algoritmo (`sha256`) y bloque.
- `blob_storage.py`: lógica para almacenar blobs de archivos en `cache/objects`.
- `zip_util.py`: reconstruye ZIP leyendo blobs según índice.
- `handle_cache_request.py`: orquesta hit/miss, almacenamiento de blobs, índice y ZIP.

---

## 4. Componentes Principales

### 4.1 Cliente (`dep_cache_proxy_client`)

#### 4.1.1 Objetivos

- Leer archivos locales (`.json`, `.lock`).
- Calcular **bundle hash** local.
- Enviar JSON al servidor.
- Recibir `download_url` y `cache_hit`.
- Descargar ZIP y extraer en carpeta local.

#### 4.1.2 Módulos

- **`client/cli.py`**: parseo de argumentos y flujo principal.
- **`client/hash_calculator.py`**: hashing con `HASH_ALGORITHM` y `HASH_BLOCK_SIZE`.
- **`client/http_client.py`**: envía petición al servidor y maneja respuestas.
- **`client/downloader.py`**: descarga y extrae ZIP.

#### 4.1.3 Argumentos CLI

```bash
dep_cache_proxy_client <endpoint_url> <manager> \
  --apikey=<APIKEY> \
  --files=<file1>,<file2> \
  [--node-version=<VERSION>] [--npm-version=<VERSION>] \
  [--php-version=<VERSION>] \
  [--timeout=<segundos>]
````

* `<endpoint_url>`: URL del servidor (`http://host:port/api`).
* `<manager>`: `npm`, `composer`, etc.
* `--apikey`: clave API si aplica.
* `--files`: lista de ficheros (definición + lock).
* `--node-version` y `--npm-version` (solo para `npm`).
* `--php-version` (solo para `composer`).
* `--timeout` (default 60s).

---

### 4.2 Servidor (`dep_cache_proxy_server`)

#### 4.2.1 Objetivos

* Recibir peticiones de cache.

* Validar API key (si no es público).

* Verificar versiones solicitadas.

* En caso de “cache miss”:

  1. Crear carpeta temporal.
  2. Instalar dependencias (local o Docker).
  3. Para cada archivo resultante, calcular `file_hash` (SHA256), y almacenar blob en `cache/objects`.
  4. Crear índice JSON en `cache/indices` mapeando ruta relativa → `file_hash`.
  5. Reconstruir ZIP desde blobs y guardarlo en `cache/bundles/<bundle_hash>.zip`.
  6. Responder con `download_url`.

* En caso de “cache hit”:

  * Devolver inmediatamente `download_url` sin regenerar.

#### 4.2.2 Módulos

* **`server/domain/hash_constants.py`**: `HASH_ALGORITHM`, `HASH_BLOCK_SIZE`.
* **`server/domain/dependency_set.py`**: cálculo de **bundle hash**.
* **`server/domain/cache_repository.py`**: interfaz `ICacheRepository`.
* **`server/domain/blob_storage.py`**: lógica para escribir y leer blobs en `cache/objects`.
* **`server/domain/installer.py`**: `DependencyInstaller` + `NpmInstaller`, `ComposerInstaller`.
* **`server/domain/zip_util.py`**: generar ZIP a partir de índice y blobs.
* **`server/infrastructure/file_system_cache_repository.py`**: implementa `ICacheRepository` en disco.
* **`server/infrastructure/api_key_validator.py`**: validación de API keys.
* **`server/infrastructure/docker_utils.py`**: funciones auxiliares para Docker.
* **`server/application/dtos.py`**: `CacheRequestDTO`, `CacheResponseDTO`.
* **`server/application/handle_cache_request.py`**: orquesta hit/miss, almacenamiento de blobs, índice y ZIP.
* **`server/interfaces/main.py`**: arranque FastAPI, parseo de args.

#### 4.2.3 Argumentos CLI Servidor

```bash
dep_cache_proxy_server <port> \
  --cache_dir=<CACHE_DIR> \
  --supported-versions-node=<NODE_VER1>:<NPM_VER1>,<NODE_VER2>:<NPM_VER2>,... \
  --supported-versions-php=<PHP_VER1>,<PHP_VER2>,... \
  [--use-docker-on-version-mismatch] \
  [--is_public] \
  [--api-keys=<KEY1>,<KEY2>,...]
```

* `<port>`: entero (e.g., `8080`).
* `--cache_dir`: carpeta base para `objects`, `indices`, `bundles`.
* `--supported-versions-node`: ej. `14.20.0:6.14.13,16.15.0:8.5.0`.
* `--supported-versions-php`: ej. `8.1.0,7.4.0`.
* `--use-docker-on-version-mismatch`: activar Docker si versión no soportada.
* `--is_public`: servidor público (sin API key).
* `--api-keys`: lista de claves válidas (requerido si `--is_public=false`).

---

## 5. Modelo de Dominio y Hashing

### 5.1 Constantes de Hash (`hash_constants.py`)

```python
# server/domain/hash_constants.py

HASH_ALGORITHM = "sha256"
HASH_BLOCK_SIZE = 8192
```

### 5.2 Entidad: `DependencySet` (`dependency_set.py`)

```python
# server/domain/dependency_set.py
import hashlib
from typing import Dict
from .hash_constants import HASH_ALGORITHM, HASH_BLOCK_SIZE

class DependencySet:
    """
    Representa la combinación única de:
      - manager: "npm" o "composer"
      - file_contents: {"package.json": b"...", "package.lock": b"..."}
      - versions: {"node":"14.20.0","npm":"6.14.13"} o {"php":"8.1.0"}
    Calcula un hash SHA256 incluyendo manager, versiones y contenido de ficheros.
    """
    def __init__(self, manager: str, file_contents: Dict[str, bytes], versions: Dict[str, str]):
        self.manager = manager
        self.file_contents = file_contents
        self.versions = versions
        self.hash = self.calculate_hash()

    def calculate_hash(self) -> str:
        sha = hashlib.new(HASH_ALGORITHM)
        sha.update(self.manager.encode("utf-8"))
        sha.update(b"\n")
        for name in sorted(self.file_contents.keys()):
            content = self.file_contents[name]
            idx = 0
            while idx < len(content):
                chunk = content[idx: idx + HASH_BLOCK_SIZE]
                sha.update(chunk)
                idx += HASH_BLOCK_SIZE
        for key in sorted(self.versions.keys()):
            val = self.versions[key]
            sha.update(f"{key}={val}\n".encode("utf-8"))
        return sha.hexdigest()
```

### 5.3 Interfaz: `ICacheRepository` (`cache_repository.py`)

```python
# server/domain/cache_repository.py
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

class CacheObject:
    """
    Representa metadatos de un bundle:
      - bundle_hash: hash de bundle
      - manager: "npm" o "composer"
      - manager_version: ej. "14.20.0_6.14.13" o "8.1.0"
    """
    def __init__(self, bundle_hash: str, manager: str, manager_version: str):
        self.bundle_hash = bundle_hash
        self.manager = manager
        self.manager_version = manager_version

class ICacheRepository(ABC):
    @abstractmethod
    def exists_bundle(self, bundle_hash: str) -> bool:
        """
        Verifica si ya existe un ZIP para este bundle hash.
        """
        pass

    @abstractmethod
    def get_index(self, bundle_hash: str, manager: str, manager_version: str) -> Path:
        """
        Retorna la ruta al índice JSON si existe, o None.
        """
        pass

    @abstractmethod
    def save_index(self, bundle_hash: str, manager: str, manager_version: str, index_data: dict) -> None:
        """
        Guarda el índice JSON en cache/indices.
        """
        pass

    @abstractmethod
    def save_blob(self, file_hash: str, content: bytes) -> None:
        """
        Guarda el blob de archivo en cache/objects/<h0h1>/<h2h3>/<file_hash>, si no existe.
        """
        pass

    @abstractmethod
    def get_blob_path(self, file_hash: str) -> Path:
        """
        Retorna la ruta absoluta al blob dado su hash.
        """
        pass

    @abstractmethod
    def save_bundle_zip(self, bundle_hash: str, zip_content_path: Path) -> None:
        """
        Guarda (o sobrescribe) el ZIP generado en cache/bundles/<bundle_hash>.zip.
        """
        pass

    @abstractmethod
    def get_bundle_zip_path(self, bundle_hash: str) -> Path:
        """
        Retorna la ruta al ZIP de bundle si existe.
        """
        pass
```

### 5.4 Lógica de Blobs de Archivos (`blob_storage.py`)

```python
# server/domain/blob_storage.py
import os
import hashlib
from pathlib import Path
from typing import Tuple

from .hash_constants import HASH_ALGORITHM, HASH_BLOCK_SIZE

class BlobStorage:
    """
    Encapsula la lógica de almacenar y recuperar blobs de archivos en cache/objects.
    """

    def __init__(self, objects_dir: Path):
        self.objects_dir = objects_dir
        self.objects_dir.mkdir(parents=True, exist_ok=True)

    def compute_file_hash(self, file_path: Path) -> str:
        """
        Calcula SHA256 del contenido de un archivo en bloques.
        """
        sha = hashlib.new(HASH_ALGORITHM)
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(HASH_BLOCK_SIZE)
                if not chunk:
                    break
                sha.update(chunk)
        return sha.hexdigest()

    def get_blob_path(self, file_hash: str) -> Path:
        """
        Ruta física del blob: <objects_dir>/<h0h1>/<h2h3>/<file_hash>
        """
        h0_2 = file_hash[0:2]
        h2_4 = file_hash[2:4]
        dir_path = self.objects_dir / h0_2 / h2_4
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path / file_hash

    def save_blob(self, file_path: Path) -> str:
        """
        Lee el archivo en file_path, calcula su hash, y guarda el contenido
        en cache/objects/.../<file_hash> si no existe. Retorna file_hash.
        """
        file_hash = self.compute_file_hash(file_path)
        dest = self.get_blob_path(file_hash)
        if not dest.is_file():
            # Solo escribir si no existe
            with open(file_path, "rb") as src, open(dest, "wb") as dst:
                while True:
                    chunk = src.read(HASH_BLOCK_SIZE)
                    if not chunk:
                        break
                    dst.write(chunk)
        return file_hash

    def read_blob(self, file_hash: str) -> bytes:
        """
        Retorna contenido del blob con file_hash.
        """
        path = self.get_blob_path(file_hash)
        with open(path, "rb") as f:
            return f.read()
```

---

## 6. Estructura de Directorios en Cache

Bajo `<cache_dir>` habrá tres subcarpetas principales:

```
<cache_dir>/
├── objects/
│   ├── aa/bb/aabb12323232322...   # blob de archivo con hash aabb...
│   ├── ee/cc/eecc1232132132121... # blob de archivo con hash eecc...
│   └── ...
├── indices/
│   ├── <bundle_hash>.npm.14.20.0_6.14.13.index
│   ├── <bundle_hash2>.composer.8.1.0.index
│   └── ...
└── bundles/
    ├── <bundle_hash>.zip
    ├── <bundle_hash2>.zip
    └── ...
```

* **`objects/`**

  * Almacena blobs de archivos individuales (sin extensión), nombrados por `file_hash`.
  * Dos niveles de directorio: primer par `h[0:2]`, segundo par `h[2:4]`.

* **`indices/`**

  * Cada índice es un archivo JSON con contenido:

    ```json
    {
      "file.js": "aabb12323232322...",
      "subfolder/file.js": "eecc1232132132121...",
      ...
    }
    ```
  * Nombre: `<bundle_hash>.<manager>.<manager_version>.index`.
  * Ejemplo: `ab12cd34.npm.14.20.0_6.14.13.index`.

* **`bundles/`**

  * Contiene ZIPs finales:

    ```
    <bundle_hash>.zip
    ```
  * Generados a partir del índice y los blobs.

---

## 7. Flujo de Trabajo Completo

1. **Cliente** invoca:

   ```bash
   dep_cache_proxy_client https://servidor:8080/api npm \
     --apikey=MI_API_KEY \
     --files=package.json,package.lock \
     --node-version=14.20.0 \
     --npm-version=6.14.13
   ```

   * Lee `package.json` y `package.lock`.
   * Construye `versions = {"node":"14.20.0","npm":"6.14.13"}`.
   * Calcula **bundle\_hash** con `DependencySet.calculate_hash()`.
   * Codifica ficheros en Base64 y arma payload JSON:

     ```jsonc
     {
       "manager": "npm",
       "hash": "<bundle_hash>",
       "files": {
         "package.json": "<base64>",
         "package.lock": "<base64>"
       },
       "versions": {
         "node": "14.20.0",
         "npm": "6.14.13"
       }
     }
     ```
   * Envía `POST https://servidor:8080/api/v1/cache` con:

     * Headers: `Authorization: Bearer MI_API_KEY`.
     * JSON anterior.

2. **Servidor: `POST /v1/cache`**

   * FastAPI recibe en `cache_endpoint()`.
   * **Valida API Key** (si `--is_public=false`).
   * Parsear JSON a `CacheRequestDTO`.
   * **Validar Manager** (`npm` o `composer`).
   * **Validar Versiones**:

     * Para `npm`: `(node_version,npm_version)` debe estar en `supported_versions_node`.
     * Para `composer`: `php_version` en `supported_versions_php`.
     * Si hay mismatch:

       * Si `use_docker_on_version_mismatch=false`:
         → `400 Bad Request: "Versión no soportada"`.
       * Si `use_docker_on_version_mismatch=true`:
         → `use_docker = True`.
   * `bundle_hash = dto.hash`; `manager_version = "14.20.0_6.14.13"` (en este ejemplo).
   * Verificar si existe ZIP ya grabado en `cache/bundles/<bundle_hash>.zip`:

     * Si existe → **Cache Hit**:

       * Responder `{ "download_url": "http://.../download/<bundle_hash>.zip", "cache_hit": true }`.
     * Si no existe → **Cache Miss**:

       1. `temp_dir = mkdtemp(prefix=bundle_hash)`.
       2. Decodificar ficheros Base64 y escribir en `temp_dir`.
       3. Crear carpeta `temp_dir/node_modules` (o `temp_dir/vendor`) tras instalar:

          * Si `use_docker`:

            ```bash
            docker run --rm \
              -v <temp_dir>:/usr/src/app \
              -w /usr/src/app \
              node:<node_version> \
              sh -c "npm ci --ignore-scripts --no-audit --cache .npm_cache"
            ```

            o para Composer:

            ```bash
            docker run --rm \
              -v <temp_dir>:/app \
              -w /app \
              composer:<php_version> \
              sh -c "composer install --no-dev --prefer-dist --no-scripts"
            ```
          * Si **sin Docker**:

            * NPM:

              ```bash
              npm ci --ignore-scripts --no-audit --cache .npm_cache
              ```
            * Composer:

              ```bash
              composer install --no-dev --prefer-dist --no-scripts
              ```
       4. **Blobificar archivos**:

          * Instanciar `blob_storage = BlobStorage(cache_dir/"objects")`.
          * Inicializar `index_data = {}` (diccionario `rel_path -> file_hash`).
          * Para cada archivo en `temp_dir/node_modules/` (o `temp_dir/vendor/`):

            * `rel_path = ruta relativa desde temp_dir/node_modules` (o `vendor`).
            * `file_hash = blob_storage.save_blob(temp_dir/<output_folder>/<rel_path>)`.
            * `index_data[rel_path] = file_hash`.
       5. **Guardar índice**:

          * Ruta de índice:

            ```
            cache/indices/<bundle_hash>.<manager>.<manager_version>.index
            ```
          * Guardar `index_data` como JSON en esa ruta.
       6. **Generar ZIP**:

          * `zip_path = cache_dir/"bundles"/f"{bundle_hash}.zip"`.
          * Para cada `rel_path, file_hash` en `index_data`:

            * `blob_bytes = blob_storage.read_blob(file_hash)`.
            * Añadir a ZIP con `arcname = rel_path`.
       7. **Respuesta**:

          * `{ "download_url": "http://.../download/<bundle_hash>.zip", "cache_hit": false }`.
       8. **Limpiar**: `shutil.rmtree(temp_dir, ignore_errors=True)`.

3. **Cliente**:

   * Recibe `download_url` y `cache_hit`.
   * Si `cache_hit=true`, descarga el ZIP directamente; si `false`, también lo descarga.
   * Extrae en `node_modules/` o `vendor/`.

4. **Descarga de ZIP**:

   * El cliente hace `GET /download/<bundle_hash>.zip`.
   * El servidor, en `download_endpoint(bundle_hash)`, verifica que `cache/bundles/<bundle_hash>.zip` existe:

     * Si existe, retorna `FileResponse` con ese ZIP.
     * Si no, `404 Not Found`.

---

## 8. Detalles de Implementación y Pseudocódigo

### 8.1 Pseudocódigo Cliente

```python
#!/usr/bin/env python3
# client/cli.py

import argparse
import base64
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile
import requests

from .hash_calculator import HASH_ALGORITHM, HASH_BLOCK_SIZE

class HashCalculator:
    @staticmethod
    def calculate_hash(manager: str, file_paths: list[str], versions: dict) -> str:
        """
        Calcula SHA256 con:
          1. manager
          2. contenido de ficheros (ordenados alfabéticamente)
          3. versiones (ordenadas por clave)
        """
        sha = hashlib.new(HASH_ALGORITHM)
        sha.update(manager.encode("utf-8"))
        sha.update(b"\n")
        for file_name in sorted(file_paths):
            with open(file_name, "rb") as f:
                while True:
                    chunk = f.read(HASH_BLOCK_SIZE)
                    if not chunk:
                        break
                    sha.update(chunk)
        for k in sorted(versions.keys()):
            v = versions[k]
            sha.update(f"{k}={v}\n".encode("utf-8"))
        return sha.hexdigest()

def parse_args():
    parser = argparse.ArgumentParser(description="Cliente CLI de DepCacheProxy")
    parser.add_argument("endpoint_url", type=str, help="URL base del servidor (http://host:port/api)")
    parser.add_argument("manager", type=str, help="Gestor de dependencias (npm, composer, etc.)")
    parser.add_argument("--apikey", type=str, required=False, help="API Key (si aplica)")
    parser.add_argument("--files", type=str, required=True, help="Ficheros: package.json,package.lock o composer.json,composer.lock")
    parser.add_argument("--node-version", type=str, required=False, help="Versión de NodeJS (solo npm)")
    parser.add_argument("--npm-version", type=str, required=False, help="Versión de NPM (solo npm)")
    parser.add_argument("--php-version", type=str, required=False, help="Versión de PHP (solo composer)")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout HTTP en segundos")
    return parser.parse_args()

def main():
    args = parse_args()
    endpoint = args.endpoint_url.rstrip("/")
    manager = args.manager.lower()
    api_key = args.apikey

    supported = ["npm", "composer"]
    if manager not in supported:
        print(f"ERROR: Gestor '{manager}' no soportado. Opciones: {', '.join(supported)}")
        sys.exit(1)

    file_list = [f.strip() for f in args.files.split(",")]
    if len(file_list) < 2:
        print("ERROR: Debe especificar al menos dos ficheros: definición + lockfile")
        sys.exit(1)
    for fp in file_list:
        if not os.path.isfile(fp):
            print(f"ERROR: Archivo no encontrado: {fp}")
            sys.exit(1)

    versions = {}
    if manager == "npm":
        if not args.node_version or not args.npm_version:
            print("ERROR: Debe especificar --node-version y --npm-version para npm")
            sys.exit(1)
        versions["node"] = args.node_version
        versions["npm"] = args.npm_version
    elif manager == "composer":
        if not args.php_version:
            print("ERROR: Debe especificar --php-version para composer")
            sys.exit(1)
        versions["php"] = args.php_version

    # Calcular bundle hash
    bundle_hash = HashCalculator.calculate_hash(manager, file_list, versions)
    print(f"[INFO] Bundle hash: {bundle_hash}")

    # Leer y codificar ficheros en base64
    files_b64 = {}
    for fp in file_list:
        with open(fp, "rb") as f:
            files_b64[os.path.basename(fp)] = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "manager": manager,
        "hash": bundle_hash,
        "files": files_b64,
        "versions": versions
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    url_cache = f"{endpoint}/v1/cache"
    print(f"[INFO] Enviando petición a {url_cache} ...")
    try:
        resp = requests.post(url_cache, headers=headers, data=json.dumps(payload), timeout=args.timeout)
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Fallo en conexión HTTP: {e}")
        sys.exit(1)

    if resp.status_code == 401:
        print("ERROR: Unauthorized. Verifica tu API Key.")
        sys.exit(1)
    elif resp.status_code != 200:
        print(f"ERROR: Servidor devolvió código {resp.status_code}: {resp.text}")
        sys.exit(1)

    resp_data = resp.json()
    download_url = resp_data.get("download_url")
    cache_hit = resp_data.get("cache_hit", False)
    if not download_url:
        print("ERROR: Respuesta inválida del servidor (falta download_url).")
        sys.exit(1)

    if cache_hit:
        print("[INFO] Cache hit: descargando ZIP...")
    else:
        print("[INFO] Cache miss: generando dependencias. Descargando cuando esté listo...")

    # Descargar ZIP
    try:
        zip_resp = requests.get(download_url, stream=True, timeout=args.timeout)
        if zip_resp.status_code != 200:
            print(f"ERROR: Fallo al descargar ZIP (código {zip_resp.status_code})")
            sys.exit(1)
        tmp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        with open(tmp_zip.name, "wb") as f:
            for chunk in zip_resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        print(f"[INFO] ZIP descargado en {tmp_zip.name}")
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Fallo al descargar ZIP: {e}")
        sys.exit(1)

    # Extraer ZIP en carpeta local dependencias
    if manager == "npm":
        target_dir = os.path.join(os.getcwd(), "node_modules")
    elif manager == "composer":
        target_dir = os.path.join(os.getcwd(), "vendor")
    else:
        target_dir = os.path.join(os.getcwd(), "deps")

    if os.path.isdir(target_dir):
        print(f"[INFO] Eliminando carpeta existente: {target_dir}")
        shutil.rmtree(target_dir)

    os.makedirs(target_dir, exist_ok=True)
    with zipfile.ZipFile(tmp_zip.name, "r") as zip_ref:
        zip_ref.extractall(target_dir)
    print(f"[INFO] Dependencias extraídas en: {target_dir}")

    os.remove(tmp_zip.name)
    print("[INFO] Proceso completado con éxito.")
    sys.exit(0)

if __name__ == "__main__":
    main()
```

---

### 8.2 Pseudocódigo Servidor

```python
#!/usr/bin/env python3
# server/interfaces/main.py

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

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from server.domain.hash_constants import HASH_ALGORITHM, HASH_BLOCK_SIZE
from server.domain.dependency_set import DependencySet
from server.domain.blob_storage import BlobStorage
from server.domain.cache_repository import ICacheRepository, CacheObject
from server.infrastructure.file_system_cache_repository import FileSystemCacheRepository
from server.infrastructure.api_key_validator import ApiKeyValidator
from server.infrastructure.docker_utils import run_in_docker
from server.domain.installer import InstallerFactory
from server.domain.zip_util import ZipUtil

# ----------------------------
# Application: DTOs
# ----------------------------
class CacheRequestDTO(BaseModel):
    manager: str
    hash: str
    files: Dict[str, str]       # {"package.json": "<base64>", ...}
    versions: Dict[str, str]    # {"node":"14.20.0","npm":"6.14.13"} o {"php":"8.1.0"}

class CacheResponseDTO(BaseModel):
    download_url: str
    cache_hit: bool

# ----------------------------
# Application: HandleCacheRequest
# ----------------------------
class HandleCacheRequest:
    def __init__(
        self,
        cache_repo: ICacheRepository,
        blob_storage: BlobStorage,
        installer_factory: InstallerFactory,
        zip_util: ZipUtil,
        supported_versions_node: Dict[str, str],
        supported_versions_php: List[str],
        use_docker: bool
    ):
        self.cache_repo = cache_repo
        self.blob_storage = blob_storage
        self.installer_factory = installer_factory
        self.zip_util = zip_util
        self.supported_versions_node = supported_versions_node
        self.supported_versions_php = supported_versions_php
        self.use_docker = use_docker

    def execute(self, request_dto: CacheRequestDTO, base_download_url: str) -> CacheResponseDTO:
        manager = request_dto.manager
        bundle_hash = request_dto.hash
        versions = request_dto.versions

        # Determinar manager_version
        if manager == "npm":
            node_ver = versions.get("node")
            npm_ver = versions.get("npm")
            if not node_ver or not npm_ver:
                raise RuntimeError("Faltan versiones de Node/NPM")
            manager_version = f"{node_ver}_{npm_ver}"
            supported_npm_ver = self.supported_versions_node.get(node_ver)
            if supported_npm_ver != npm_ver:
                if not self.use_docker:
                    raise ValueError("Versión de Node/NPM no soportada")
                else:
                    use_docker_exec = True
            else:
                use_docker_exec = False
        elif manager == "composer":
            php_ver = versions.get("php")
            if not php_ver:
                raise RuntimeError("Falta versión de PHP")
            manager_version = php_ver
            if php_ver not in self.supported_versions_php:
                if not self.use_docker:
                    raise ValueError("Versión de PHP no soportada")
                else:
                    use_docker_exec = True
            else:
                use_docker_exec = False
        else:
            raise ValueError(f"Manager no implementado: {manager}")

        # Verificar existencia de ZIP
        if self.cache_repo.exists_bundle(bundle_hash):
            download_url = f"{base_download_url}/download/{bundle_hash}.zip"
            return CacheResponseDTO(download_url=download_url, cache_hit=True)

        # Cache Miss: generar
        temp_dir = Path(tempfile.mkdtemp(prefix=bundle_hash))
        try:
            # Escribir ficheros decodificados en temp_dir
            for fname, b64 in request_dto.files.items():
                data = base64.b64decode(b64)
                (temp_dir / fname).write_bytes(data)

            # Instalar dependencias (local o Docker)
            installer = self.installer_factory.get_installer(manager, versions)
            if use_docker_exec:
                run_in_docker(temp_dir, manager, versions)
            else:
                installer.install(temp_dir)

            # 1) Blobificar archivos
            index_data: Dict[str, str] = {}
            output_folder = installer.output_folder_name  # "node_modules" o "vendor"
            for dirpath, _, filenames in os.walk(temp_dir / output_folder):
                for fn in filenames:
                    full_path = Path(dirpath) / fn
                    rel_path = str(full_path.relative_to(temp_dir / output_folder))
                    file_hash = self.blob_storage.save_blob(full_path)
                    index_data[rel_path] = file_hash

            # 2) Guardar índice
            self.cache_repo.save_index(bundle_hash, manager, manager_version, index_data)

            # 3) Generar ZIP a partir de blobs
            zip_path = self.cache_repo.get_bundle_zip_path(bundle_hash)
            self.zip_util.create_zip_from_blobs(zip_path, index_data, self.blob_storage)

            return CacheResponseDTO(
                download_url=f"{base_download_url}/download/{bundle_hash}.zip",
                cache_hit=False
            )

        except Exception as e:
            # Limpieza en caso de error
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise RuntimeError(f"Error al procesar bundle: {e}")

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

# ----------------------------
# Interfaces / Entrypoint: FastAPI
# ----------------------------
def create_app(
    cache_dir: Path,
    is_public: bool,
    api_keys: List[str],
    supported_versions_node: Dict[str, str],
    supported_versions_php: List[str],
    use_docker_on_mismatch: bool,
    base_download_url: str
) -> FastAPI:
    app = FastAPI()

    # Inicializar repositorios e infraestructura
    objects_dir = cache_dir / "objects"
    indices_dir = cache_dir / "indices"
    bundles_dir = cache_dir / "bundles"
    objects_dir.mkdir(parents=True, exist_ok=True)
    indices_dir.mkdir(parents=True, exist_ok=True)
    bundles_dir.mkdir(parents=True, exist_ok=True)

    cache_repo = FileSystemCacheRepository(cache_dir)
    blob_storage = BlobStorage(objects_dir)
    installer_factory = InstallerFactory()
    zip_util = ZipUtil()
    validator = ApiKeyValidator(api_keys) if not is_public else None

    handler = HandleCacheRequest(
        cache_repo, blob_storage, installer_factory, zip_util,
        supported_versions_node, supported_versions_php, use_docker_on_mismatch
    )

    @app.post("/v1/cache", response_model=CacheResponseDTO)
    async def cache_endpoint(request: Request):
        # Validar API Key si no es público
        if not is_public:
            auth: Optional[str] = request.headers.get("Authorization")
            if not auth or not auth.startswith("Bearer "):
                raise HTTPException(status_code=401, detail="Falta Authorization Bearer <APIKEY>")
            key = auth.split(" ")[1]
            if not validator.validate(key):
                raise HTTPException(status_code=401, detail="API Key inválida")

        # Parsear payload
        payload = await request.json()
        try:
            dto = CacheRequestDTO(**payload)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Payload inválido: {e}")

        supported_managers = ["npm", "composer"]
        if dto.manager not in supported_managers:
            raise HTTPException(status_code=400, detail=f"Manager no soportado: {dto.manager}")

        try:
            response_dto = handler.execute(dto, base_download_url)
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))
        except RuntimeError as re:
            raise HTTPException(status_code=500, detail=str(re))

        return JSONResponse(status_code=200, content=response_dto.dict())

    @app.get("/download/{bundle_hash}.zip")
    async def download_endpoint(bundle_hash: str):
        zip_path = cache_dir / "bundles" / f"{bundle_hash}.zip"
        if zip_path.is_file():
            return FileResponse(zip_path, filename=f"{bundle_hash}.zip", media_type="application/zip")
        raise HTTPException(status_code=404, detail="ZIP no encontrado")

    return app

def parse_args():
    parser = argparse.ArgumentParser(description="Servidor DepCacheProxy")
    parser.add_argument("port", type=int, help="Puerto HTTP donde escuchará (ej. 8080)")
    parser.add_argument("--cache_dir", type=str, required=True, help="Directorio base de cache")
    parser.add_argument(
        "--supported-versions-node", type=str, required=True,
        help="Pares node_version:npm_version separados por comas, ej. 14.20.0:6.14.13,16.15.0:8.5.0"
    )
    parser.add_argument(
        "--supported-versions-php", type=str, required=True,
        help="Lista de versiones de PHP separadas por comas, ej. 8.1.0,7.4.0"
    )
    parser.add_argument(
        "--use-docker-on-version-mismatch",
        action="store_true",
        help="Usar Docker para instalar dependencias si la versión no está soportada"
    )
    parser.add_argument("--is_public", action="store_true", default=False, help="Servidor público (sin API key)")
    parser.add_argument("--api-keys", type=str, required=False, help="Claves válidas separadas por comas")
    return parser.parse_args()

def main():
    args = parse_args()
    port = args.port
    cache_dir = Path(args.cache_dir)
    use_docker = args.use_docker_on_version_mismatch
    is_public = args.is_public

    supported_versions_node = {}
    for pair in args.supported_versions_node.split(","):
        node_v, npm_v = pair.split(":")
        supported_versions_node[node_v.strip()] = npm_v.strip()

    supported_versions_php = [v.strip() for v in args.supported_versions_php.split(",")]

    api_keys = []
    if not is_public:
        if not args.api_keys:
            print("ERROR: Debe proporcionar --api-keys cuando no es público.")
            sys.exit(1)
        api_keys = [k.strip() for k in args.api_keys.split(",") if k.strip()]

    # Crear estructura de cache
    (cache_dir / "objects").mkdir(parents=True, exist_ok=True)
    (cache_dir / "indices").mkdir(parents=True, exist_ok=True)
    (cache_dir / "bundles").mkdir(parents=True, exist_ok=True)

    base_download_url = f"http://localhost:{port}"
    app = create_app(
        cache_dir, is_public, api_keys,
        supported_versions_node, supported_versions_php, use_docker, base_download_url
    )
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
```

---

### 8.3 Funciones Auxiliares Comunes

#### 8.3.1 `ZipUtil` para ZIP a partir de blobs (`zip_util.py`)

```python
# server/domain/zip_util.py
import zipfile
from pathlib import Path
from typing import Dict
from .blob_storage import BlobStorage

class ZipUtil:
    @staticmethod
    def create_zip_from_blobs(zip_path: Path, index_data: Dict[str, str], blob_storage: BlobStorage) -> None:
        """
        Crea un ZIP en zip_path. Para cada par (ruta_relativa, file_hash)
        en index_data, lee el blob con blob_storage.read_blob(file_hash)
        y lo añade al ZIP con arcname=ruta_relativa.
        """
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel_path, file_hash in index_data.items():
                blob_bytes = blob_storage.read_blob(file_hash)
                # Para añadir bytes, usar un archivo temporal o writestr
                zf.writestr(rel_path, blob_bytes)
```

---

## 9. API HTTP y Esquema de Rutas

### 9.1 Rutas

| Método | Ruta                          | Descripción                                                 | Request Body      | Respuestas                                                                                                    |
| ------ | ----------------------------- | ----------------------------------------------------------- | ----------------- | ------------------------------------------------------------------------------------------------------------- |
| POST   | `/v1/cache`                   | Solicita cache de dependencias: hit/miss y URL de descarga. | `CacheRequestDTO` | `200 OK` → `CacheResponseDTO` <br> `400 Bad Request` <br> `401 Unauthorized` <br> `500 Internal Server Error` |
| GET    | `/download/{bundle_hash}.zip` | Descarga el ZIP generado para el bundle\_hash especificado. | Ninguno           | `200 OK` → ZIP <br> `404 Not Found`                                                                           |

### 9.2 `CacheRequestDTO`

```jsonc
{
  "manager": "npm",
  "hash": "ab12cd34ef56...",
  "files": {
    "package.json": "<base64_contenido>",
    "package.lock": "<base64_contenido>"
  },
  "versions": {
    "node": "14.20.0",
    "npm": "6.14.13"
  }
}
```

* `manager`: string (obligatorio).
* `hash`: string (bundle hash, obligatorio).
* `files`: map\<string, string> (ficheros en Base64, obligatorio).
* `versions`: map\<string, string> (obligatorio):

  * Para `npm`: requiere `"node"` y `"npm"`.
  * Para `composer`: requiere `"php"`.

### 9.3 `CacheResponseDTO`

```jsonc
{
  "download_url": "http://server:8080/download/ab12cd34ef56... .zip",
  "cache_hit": true
}
```

* `download_url`: string (obligatorio).
* `cache_hit`: boolean (obligatorio).

---

## 10. Estructura de Pruebas

```
tests/
├── unit/
│   ├── test_hash_calculator.py
│   ├── test_api_key_validator.py
│   ├── test_installer_factory.py
│   ├── test_blob_storage.py
│   └── test_zip_util.py
├── integration/
│   ├── test_handle_cache_request_hit.py
│   ├── test_handle_cache_request_miss.py
│   └── test_docker_installation.py
├── functional/
│   ├── test_cli_client_request.py
│   └── test_server_download_endpoint.py
└── e2e/
    ├── test_end_to_end_npm.py
    └── test_end_to_end_composer.py
```

### 10.1 Pruebas Unitarias

* **`test_hash_calculator.py`**:

  * Verificar que entradas idénticas producen el mismo hash.
  * Verificar que cambiar un byte en `package.json` cambia el hash.

* **`test_api_key_validator.py`**:

  * `validate(key_valida) == True`.
  * `validate(key_invalida) == False`.

* **`test_installer_factory.py`**:

  * `get_installer("npm", ...)` → instancia `NpmInstaller`.
  * `get_installer("composer", ...)` → instancia `ComposerInstaller`.
  * `get_installer("otro", ...)` lanza `ValueError`.

* **`test_blob_storage.py`**:

  * Crear archivo temporal con contenido fijo. `save_blob` devuelve un `file_hash`.
  * Verificar que `get_blob_path(file_hash)` existe y su contenido coincide.
  * Llamar `save_blob` repetido no sobrescribe (no cambia contenido).

* **`test_zip_util.py`**:

  * Con un índice de prueba que apunte a blobs generados en `blob_storage`, llamar `create_zip_from_blobs` y verificar que el ZIP contiene archivos con rutas correctas y contenido válido.

### 10.2 Pruebas de Integración

* **`test_handle_cache_request_hit.py`**:

  * Precondición: generar un bundle previamente (run `handler.execute` sobre un request).
  * Llamar de nuevo `handler.execute` con el mismo `bundle_hash` y verificar que retorna `cache_hit=True` sin crear blobs ni índices nuevos.

* **`test_handle_cache_request_miss.py`**:

  * Simular un `CacheRequestDTO` con bundle nuevo.
  * Verificar que, tras `execute`, existen:

    * Blobs en `cache/objects/`.
    * Índice JSON en `cache/indices/`.
    * ZIP en `cache/bundles/`.
  * Verificar que `cache_hit=False`.

* **`test_docker_installation.py`**:

  * Configurar `use_docker_on_mismatch=True` y pasar versiones no soportadas.
  * Verificar que `run_in_docker` crea `node_modules/` o `vendor/` en carpeta temporal y luego se blobifica.

### 10.3 Pruebas Funcionales

* **`test_cli_client_request.py`**:

  * Usar `TestClient` de FastAPI para levantar servidor en memoria.
  * Ejecutar CLI (`subprocess.run([...])`) apuntando a ese servidor.
  * Verificar que el CLI imprime mensajes esperados y que, tras finalizar, `node_modules/` local existe con contenido.

* **`test_server_download_endpoint.py`**:

  * Insertar manualmente un ZIP en `cache/bundles/<bundle_hash>.zip`.
  * Hacer `GET /download/<bundle_hash>.zip` y validar que el contenido coincide byte a byte con el ZIP insertado.

### 10.4 Pruebas End-to-End

* **`test_end_to_end_npm.py`**:

  * Levantar contenedor Docker con la imagen del servidor.
  * Montar volumen local a `/cache`.
  * Ejecutar CLI en otro contenedor o en host apuntando al servidor Docker.
  * Verificar que `node_modules/` final coincide con entorno de pruebas.

* **`test_end_to_end_composer.py`**:

  * Análogo para Composer.

---

## 11. Escenarios de Uso y Casos de Prueba

### 11.1 Escenario 1: Cache Hit en NPM

1. **Servidor** arranca:

   ```bash
   dep_cache_proxy_server 8080 \
     --cache_dir=./cache \
     --supported-versions-node=14.20.0:6.14.13,16.15.0:8.5.0 \
     --supported-versions-php=8.1.0 \
     --use-docker-on-version-mismatch \
     --is_public
   ```
2. **Bundle existente**:

   * Supongamos que `bundle_hash = "ab12cd34..."` ya se procesó antes, y existe:

     * Blobs en `cache/objects/...`.
     * Índice `cache/indices/ab12cd34.npm.14.20.0_6.14.13.index`.
     * ZIP en `cache/bundles/ab12cd34.zip`.
3. **Cliente**:

   ```bash
   dep_cache_proxy_client http://localhost:8080/api npm \
     --files=package.json,package.lock \
     --node-version=14.20.0 \
     --npm-version=6.14.13
   ```

   * Calcula `bundle_hash = "ab12cd34..."`.
   * Envía `POST /v1/cache`.
   * Servidor detecta ZIP existente → responde:

     ```jsonc
     { "download_url": "http://localhost:8080/download/ab12cd34.zip", "cache_hit": true }
     ```
   * Cliente descarga y extrae en `./node_modules/`.

---

### 11.2 Escenario 2: Cache Miss en Composer

1. **Servidor**:

   ```bash
   dep_cache_proxy_server 8080 \
     --cache_dir=./cache \
     --supported-versions-node=14.20.0:6.14.13 \
     --supported-versions-php=8.1.0,7.4.0 \
     --api-keys=KEY1
   ```
2. **Cliente**:

   ```bash
   dep_cache_proxy_client http://localhost:8080/api composer \
     --apikey=KEY1 \
     --files=composer.json,composer.lock \
     --php-version=8.1.0
   ```

   * Calcula `bundle_hash = "aa11bb22..."`.
   * Servidor ve que no existe ZIP.
   * Crea `temp_dir`, escribe ficheros, ejecuta `composer install --no-dev --prefer-dist --no-scripts`.
   * En `temp_dir/vendor/`, blobifica cada archivo:

     * Por ejemplo, `vendor/packageA/index.php` → `file_hash = "eecc1232..."`.
     * Se guarda en `cache/objects/ee/cc/eecc1232...`.
     * `index_data["packageA/index.php"] = "eecc1232..."`.
   * Guarda índice JSON en:

     ```
     cache/indices/aa11bb22.composer.8.1.0.index
     ```
   * Genera ZIP en `cache/bundles/aa11bb22.zip` usando blobs:

     * Dentro de `zip`, rutea `packageA/index.php` con contenido de blob.
   * Responde:

     ```jsonc
     { "download_url": "http://localhost:8080/download/aa11bb22.zip", "cache_hit": false }
     ```
3. **Cliente**:

   * Descarga y extrae en `./vendor/`.

---

### 11.3 Escenario 3: Versión no soportada sin Docker

1. **Servidor**:

   ```bash
   dep_cache_proxy_server 8080 \
     --cache_dir=./cache \
     --supported-versions-node=14.20.0:6.14.13 \
     --supported-versions-php=8.1.0 \
     --api-keys=KEY1
   ```

   * `use_docker_on_version_mismatch=false`.
2. **Cliente**:

   ```bash
   dep_cache_proxy_client http://localhost:8080/api npm \
     --apikey=KEY1 \
     --files=package.json,package.lock \
     --node-version=16.15.0 \
     --npm-version=8.5.0
   ```

   * Calcula `bundle_hash`.
   * Servidor detecta mismatch en `(16.15.0,8.5.0)` y `use_docker=false` → `400 Bad Request` con detalle `"Versión de Node/NPM no soportada"`.
3. **Cliente**:

   * Recibe `resp.status_code == 400` y finaliza con error.

---

### 11.4 Escenario 4: Versión no soportada con Docker

1. **Servidor**:

   ```bash
   dep_cache_proxy_server 8080 \
     --cache_dir=./cache \
     --supported-versions-node=14.20.0:6.14.13 \
     --supported-versions-php=8.1.0 \
     --use-docker-on-version-mismatch \
     --api-keys=KEY1
   ```
2. **Cliente**:

   ```bash
   dep_cache_proxy_client http://localhost:8080/api npm \
     --apikey=KEY1 \
     --files=package.json,package.lock \
     --node-version=16.15.0 \
     --npm-version=8.5.0
   ```

   * Servidor detecta mismatch y `use_docker=true`.
   * En `temp_dir`, ejecuta:

     ```bash
     docker run --rm \
       -v <temp_dir>:/usr/src/app \
       -w /usr/src/app \
       node:16.15.0 \
       sh -c "npm ci --ignore-scripts --no-audit --cache .npm_cache"
     ```
   * Continúa blobificando, indexando y generando ZIP.
   * Responde con `cache_hit=false`.

---

## 12. Notas de Seguridad, Escalabilidad y Errores Comunes

### 12.1 Seguridad

1. **Validación de Inputs**:

   * `manager` debe compararse en lista blanca.
   * `versions` validarse con regex de semver.

2. **Ejecución de Comandos**:

   * Local: `subprocess.run([...])` con lista explícita de argumentos.
   * Docker: lista en `run_in_docker`, evitando interpolaciones inseguras.

3. **API Key**:

   * Comparar de forma segura (timing-safe).
   * No imprimir `--api-keys` en logs.

4. **ZIP y Blobs**:

   * Solo servir archivos de `cache/bundles` y blobs de `cache/objects`.
   * No exponer rutas de sistema fuera de `<cache_dir>`.

### 12.2 Escalabilidad

1. **Concurrencia**:

   * Lock por `bundle_hash` durante el flujo de “miss”:

     * Crear un lock file (`cache_dir/locks/<bundle_hash>.lock`) con `fcntl.flock`.
     * Otros procesos esperan hasta que se libere lock.

2. **Retención de Cache**:

   * Cronjob para eliminar bundles > X días sin acceso.
   * Mantener contador de accesos en metadatos (opcional).

3. **Almacenamiento Distribuido**:

   * Sustituir `FileSystemCacheRepository` por `S3CacheRepository`.
   * Ajustar `blob_storage` para usar S3.

### 12.3 Errores Comunes

1. **Desajuste de Hash**:

   * Verificar mismas constantes en cliente y servidor.
   * Confirmar orden alfabético de ficheros y versiones.

2. **Falla en Docker**:

   * Verificar Docker instalado y permisos.
   * Asegurar que la imagen (e.g., `node:16.15.0`) exista localmente o se pueda descargar.

3. **Permisos de Carpetas**:

   * Proceso debe poder escribir en `<cache_dir>`.

4. **Carpeta Temporal no Eliminada**:

   * En todos los flujos, llamar a `shutil.rmtree(temp_dir, ignore_errors=True)`.

---

## 13. Facilidad para Añadir Nuevos Managers

Para añadir un gestor nuevo (e.g., Yarn, Pip), seguir:

1. **Crear subclase de `DependencyInstaller` en `server/domain/installer.py`**

   ```python
   class YarnInstaller(DependencyInstaller):
       @property
       def output_folder_name(self) -> str:
           return "node_modules"  # si Yarn coloca dependencias ahí

       def install(self, work_dir: Path) -> None:
           cmd = ["yarn", "install", "--frozen-lockfile"]
           process = subprocess.run(cmd, cwd=str(work_dir), capture_output=True)
           if process.returncode != 0:
               raise RuntimeError(f"Yarn install falló: {process.stderr.decode()}")

       def install_with_docker(self, work_dir: Path, versions: Dict[str, str]) -> None:
           node_ver = versions.get("node")
           if not node_ver:
               raise RuntimeError("Especificar node_version para Yarn en Docker")
           cmd = [
               "docker", "run", "--rm",
               "-v", f"{work_dir}:/usr/src/app",
               "-w", "/usr/src/app",
               f"node:{node_ver}",
               "sh", "-c", "yarn install --frozen-lockfile"
           ]
           process = subprocess.run(cmd, capture_output=True)
           if process.returncode != 0:
               raise RuntimeError(f"Yarn install en Docker falló: {process.stderr.decode()}")
   ```

2. **Actualizar `InstallerFactory`**:

   ```python
   class InstallerFactory:
       def get_installer(self, manager: str, versions: Dict[str, str]) -> DependencyInstaller:
           if manager == "npm":
               return NpmInstaller(versions)
           elif manager == "composer":
               return ComposerInstaller(versions)
           elif manager == "yarn":
               return YarnInstaller(versions)
           else:
               raise ValueError(f"Installer no implementado para manager '{manager}'")
   ```

3. **Modificar Validación de Manager**:

   * En `cache_endpoint`, incluir `"yarn"` en `supported_managers`.
   * En validación de versiones, exigir `node_version` para Yarn (similar a NPM).

4. **Actualizar Configuración de Versiones**:

   * `--supported-versions-node` sirve tanto para NPM como Yarn.

5. **Agregar Pruebas**:

   * `tests/unit/test_installer_factory.py`: verificar que `"yarn"` devuelve instancia `YarnInstaller`.
   * `tests/integration/test_handle_cache_request_yarn.py`: flujo “hit/miss” para Yarn.
   * Pruebas funcionales y E2E análogas a NPM.

---

## 14. Conclusiones

Este análisis actualizado corrige la estrategia de almacenamiento en `cache/objects` para que contenga **solo blobs de archivos individuales**, indexados por ruta relativa → file hash. El índice de cada bundle reside en `cache/indices` y los ZIP finales en `cache/bundles`. Se mantienen los requisitos de versiones y uso opcional de Docker, las constantes de hash, la separación DDD + SOLID y una exhaustiva estrategia de pruebas (unitarias, integración, funcionales y E2E). Con esta documentación, se facilita la implementación y el mantenimiento, así como la adición de nuevos gestores de dependencias.