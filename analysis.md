# Análisis Extendido de **DepCacheProxy** (`dep_cache_proxy`)

Este documento actualiza y amplía el análisis detallado de **DepCacheProxy**, incorporando nuevos requisitos sobre versiones, uso de Docker para instalación de dependencias, constantes de algoritmo de hash, estructura de índices de hash y consideraciones de pruebas. Está pensado para ser consumido por otras IA (por ejemplo, Claude) y como guía completa para desarrolladores.

---

## Tabla de Contenidos

1. [Objetivos y Contexto](#objetivos-y-contexto)  
2. [Requisitos Funcionales y No Funcionales](#requisitos-funcionales-y-no-funcionales)  
3. [Visión General de la Arquitectura (DDD + SOLID)](#visión-general-de-la-arquitectura-ddd--solid)  
4. [Componentes Principales](#componentes-principales)  
   1. [Cliente (`dep_cache_proxy_client`)](#cliente-dep_cache_proxy_client)  
   2. [Servidor (`dep_cache_proxy_server`)](#servidor-dep_cache_proxy_server)  
5. [Modelo de Dominio y Hashing](#modelo-de-dominio-y-hashing)  
6. [Estructura de Directorios en Cache](#estructura-de-directorios-en-cache)  
7. [Flujo de Trabajo Completo](#flujo-de-trabajo-completo)  
8. [Detalles de Implementación y Pseudocódigo](#detalles-de-implementación-y-pseudocódigo)  
   1. [Pseudocódigo Cliente](#pseudocódigo-cliente)  
   2. [Pseudocódigo Servidor](#pseudocódigo-servidor)  
   3. [Funciones Auxiliares Comunes](#funciones-auxiliares-comunes)  
9. [API HTTP y Esquema de Rutas](#api-http-y-esquema-de-rutas)  
10. [Estructura de Pruebas](#estructura-de-pruebas)  
11. [Escenarios de Uso y Casos de Prueba](#escenarios-de-uso-y-casos-de-prueba)  
12. [Notas de Seguridad, Escalabilidad y Errores Comunes](#notas-de-seguridad-escalabilidad-y-errores-comunes)  
13. [Facilidad para Añadir Nuevos Managers](#facilidad-para-añadir-nuevos-managers)  
14. [Conclusiones](#conclusiones)  

---

## 1. Objetivos y Contexto

Este análisis describe cómo diseñar **DepCacheProxy** para:

1. **Cachear dependencias**  
   - Guardar localmente (en disco del servidor) los paquetes descargados a partir de `package.json` + `package.lock` (o `composer.json` + `composer.lock`), evitando redundancias.  
   - Cada combinación de ficheros de definición + lockfile + versiones genera un _hash específico_.  

2. **Proveer proxy/respaldo de descarga**  
   - En entornos con red inestable, el servidor de cache provee un ZIP preconstruido de `node_modules` o `vendor`, evitando timeouts.  

3. **Acelerar pipelines (por ejemplo, Docker)**  
   - Descarga del ZIP en lugar de ejecutar `npm install` o `composer install` localmente.  

4. **Gestión de versiones y Docker**  
   - Si el cliente solicita una versión de Node/NPM o PHP/Composer distinta a las soportadas, el servidor puede:  
     - **Error** (por defecto), o  
     - **Usar Docker** para ejecutar la imagen apropiada y generar las dependencias.  

5. **Almacenamiento de índices de hash**  
   - Además de guardar los archivos cacheados, se debe mantener una carpeta `cache/indices/` donde residan los índices de hash (metadatos) nombrados con la versión del manager.  

6. **Pruebas**  
   - Se definirán pruebas unitarias, de integración, funcionales y end-to-end.  

7. **Extensibilidad a nuevos managers**  
   - El sistema debe permitir agregar fácilmente gestores de dependencias adicionales (por ejemplo, Yarn, Pip, etc.) con mínima configuración.  

8. **Diseño DDD + SOLID**  
   - Separación de dominio, aplicación e infraestructura.  
   - Cada módulo con responsabilidad única.  

9. **Implementación en Python**  
   - Uso de constantes para algoritmos de hash y rutas de directorios.  
   - Uso de Docker (si se elige) para aislar versiones.  

10. **Dos Partes**  
   - **Cliente CLI**: `dep_cache_proxy_client`.  
   - **Servidor HTTP**: `dep_cache_proxy_server`.  

---

## 2. Requisitos Funcionales y No Funcionales

### 2.1 Requisitos Funcionales (RF)

1. **RF1**: El cliente CLI (`dep_cache_proxy_client`) debe aceptar:  
   - `<endpoint_url>` (URL del servidor).  
   - `<manager>` (identificador, por ejemplo, `npm`, `composer`).  
   - `--apikey=<APIKEY>` (opcional si el servidor es público).  
   - `--files=<file1>,<file2>` (definición + lockfile).  
   - **Opcionales en el cliente** (pero **obligatorios en el servidor**):
     - `--node-version=<VERSIÓN>` y `--npm-version=<VERSIÓN>` (para `npm`).  
     - `--php-version=<VERSIÓN>` (para `composer`).  

2. **RF2**: El servidor CLI (`dep_cache_proxy_server`) debe aceptar (y obligatoriamente):
   - `<port>` (puerto HTTP).  
   - `--cache_dir=<CACHE_DIR>` (directorio base de cache).  
   - `--supported-versions-node=<VERSIÓN_NODO>,<VERSIÓN_NPM>,...` (lista de pares `node_version:npm_version` separados por comas).  
   - `--supported-versions-php=<VERSIÓN_PHP>,...` (si usa Composer).  
   - `--use-docker-on-version-mismatch` (booleano; si se habilita, en caso de que el cliente solicite versión no soportada, el servidor genera dependencias usando Docker).  
   - `--is_public` (booleano, opcional; default `false`).  
   - `--api-keys=<KEY1>,<KEY2>,...` (obligatorio si `--is_public=false`).

3. **RF3**: Cálculo de **hash**:
   - Utilizar constante global para el algoritmo de hash (por ejemplo, `HASH_ALGORITHM = "sha256"`).  
   - Incluir en el hash:
     1. `manager` (ej. `"npm"` o `"composer"`).  
     2. Versiones solicitadas (por ejemplo, `"node=14.20.0"`, `"npm=6.14.13"`, `"php=8.1.0"`).  
     3. Contenido exacto de cada fichero enviado (`.json`, `.lock`).  
   - Almacenar en constantes:
     ```python
     HASH_ALGORITHM = "sha256"
     HASH_BLOCK_SIZE = 8192
     ```
   - El hash resultante será un hex digest de 64 caracteres.

4. **RF4**: Estructura de cache en disco:
   - **`cache/objects/`** → Carpeta base donde se guardan todos los archivos cacheados de `node_modules` o `vendor`.  
     - Subdirectorios basados en los dos primeros pares de caracteres hexadecimales del hash (dos niveles).  
     - En cada carpeta `<hash>.<manager>` se guarda:
       - Todos los archivos de `node_modules/` o `vendor/`.
       - Se genera un **índice de hash de archivos** (metadata) con nombre `<hash>.<manager>.<manager_version>.index` (por ejemplo, `ab12cd34.npm.14.20.0_6.14.13.index`).
       - Se genera el ZIP `<hash>.zip`.  
   - **`cache/indices/`** → Carpeta donde se almacenan únicamente los índices de hash (metadata) de cada combinación.  
     - Cada archivo de índice debe incluir en su nombre:  
       ```
       <hash>.<manager>.<manager_version>.index
       ```
       - Para NPM, `manager_version` = `<node_version>_<npm_version>` (por ejemplo, `14.20.0_6.14.13`).  
       - Para Composer, `manager_version` = `<php_version>` (por ejemplo, `8.1.0`).  

5. **RF5**: Verificación de versiones:
   - El servidor mantiene en memoria (o lee de configuración) las versiones soportadas para cada manager.  
   - Si el cliente envía una combinación de versiones **que no coincide** con las soportadas:  
     - **Si** `--use-docker-on-version-mismatch=false` → devolver `400 Bad Request` “Versión no soportada”.  
     - **Si** `--use-docker-on-version-mismatch=true` → invocar `docker run` con la imagen apropiada para generar dependencias.  

6. **RF6**: Proceso de generación de dependencias:
   1. Crear carpeta temporal (`temp_dir`) para cada petición (por ejemplo, `/tmp/dep_cache_<hash>/`).  
   2. Escribir en `temp_dir` los ficheros `.json` y `.lock` recibidos.  
   3. Instalar dependencias:
      - **Sin Docker** (versiones soportadas): ejecutar comandos locales:
        - NPM: 
          ```bash
          npm ci --ignore-scripts --no-audit --cache .npm_cache
          ```
        - Composer:
          ```bash
          composer install --no-dev --prefer-dist --no-scripts
          ```
      - **Con Docker** (versiones no soportadas y `--use-docker-on-version-mismatch=true`):
        - Para NPM:
          ```bash
          docker run --rm \
            -v <temp_dir>:/usr/src/app \
            -w /usr/src/app \
            node:<node_version> \
            sh -c "npm ci --ignore-scripts --no-audit --cache .npm_cache"
          ```
        - Para Composer:
          ```bash
          docker run --rm \
            -v <temp_dir>:/app \
            -w /app \
            composer:<php_version> \
            sh -c "composer install --no-dev --prefer-dist --no-scripts"
          ```
   4. Dentro de `temp_dir` habrá `node_modules/` o `vendor/`.  
   5. Copiar recursivamente todo el contenido de `temp_dir/node_modules/` (o `vendor/`) a `cache/objects/<subdir>/.../<hash>.<manager>/node_modules` (o `vendor/`).  
   6. Generar índice de hash de todos los archivos copiados, guardándolo en:
      - `cache/objects/<h0h1>/<h2h3>/<hash>.<manager>/<hash>.<manager>.<manager_version>.index`  
      - Y en paralelo, copiar ese índice a `cache/indices/<hash>.<manager>.<manager_version>.index`.  
   7. Generar ZIP de la carpeta:
      - `zip -r <hash>.zip node_modules/` (o `vendor/`).  
      - Mover `zip` a `cache/objects/.../<hash>.zip`.  
   8. Limpiar `temp_dir`.  

7. **RF7**: Cliente debe:
   - Calcular hash local (usando constantes de algoritmo).  
   - Enviar JSON al servidor con:
     - `manager`, `hash`, `files` (base64), `versions`.  
   - Descargar el ZIP si es “hit” o esperar a que se genere en caso de “miss”.  
   - Descomprimir en la carpeta local de dependencias (`node_modules/` o `vendor/`).  

8. **RF8**: Pruebas:
   - **Pruebas Unitarias**:  
     - `HashCalculator` → casos de hash idéntico con entradas iguales.  
     - `ApiKeyValidator` → validar claves válidas e inválidas.  
     - `InstallerFactory` → crear instancias correctas según manager.  
   - **Pruebas de Integración**:
     - Test completo de `HandleCacheRequest` en modo “hit” y “miss”.  
     - Verificar que los artefactos en `cache/objects` e `indices` existan y contengan metadatos correctos.  
   - **Pruebas Funcionales**:
     - `cli_client` envía petición a un servidor real (puede ser instancia local de FastAPI) y verifica comportamiento en entorno “hit” y “miss”.  
   - **Pruebas End-to-End**:
     - Desplegar servidor en Docker, usar cliente en otro contenedor o máquina, verificar ZIP final y extracción de dependencias.  

### 2.2 Requisitos No Funcionales (RNF)

1. **RNF1 (Eficiencia)**:  
   - Uso de hashing en streaming (`HASH_BLOCK_SIZE = 8192`).  
   - Caching de índices separados para evitar recalcular lista de archivos en cada petición.  

2. **RNF2 (Escalabilidad)**:  
   - Concurrencia segura con locks por hash.  
   - Fácilmente reemplazable `FileSystemCacheRepository` por almacenamiento distribuido (S3).  

3. **RNF3 (Extensibilidad)**:  
   - Patrón Factory/Strategy para nuevos managers.  
   - Documentación clara en `README.md` sobre cómo agregar un nuevo `DependencyInstaller`.  

4. **RNF4 (Seguridad)**:  
   - Saneamiento de inputs (`manager`, nombres de archivos).  
   - `--ignore-scripts` y `--no-scripts` para evitar ejecución de código malicioso.  

5. **RNF5 (Portabilidad)**:  
   - Funciona en Linux/macOS.  
   - Requiere Docker si `--use-docker-on-version-mismatch=true` y no se dispone de una versión local soportada.  

6. **RNF6 (Mantenibilidad)**:  
   - PEP8, type hints, docstrings.  
   - Pruebas automatizadas en `pytest`.  

7. **RNF7 (Disponibilidad)**:  
   - Sin HTTPS nativo; usar proxy inverso para TLS.  

---

## 3. Visión General de la Arquitectura (DDD + SOLID)

### 3.1 Capas y Paquetes

````

dep\_cache\_proxy/
├── client/
│   ├── cli.py
│   ├── hash\_calculator.py
│   ├── http\_client.py
│   └── downloader.py
├── server/
│   ├── domain/
│   │   ├── dependency\_set.py
│   │   ├── cache\_object.py
│   │   ├── cache\_repository.py
│   │   ├── hash\_constants.py
│   │   ├── installer.py
│   │   └── zip\_util.py
│   ├── application/
│   │   ├── dtos.py
│   │   └── handle\_cache\_request.py
│   ├── infrastructure/
│   │   ├── file\_system\_cache\_repository.py
│   │   ├── api\_key\_validator.py
│   │   └── docker\_utils.py
│   └── interfaces/
│       └── main.py
├── cache/
│   ├── objects/
│   │   └── ... (estructura de hashes)
│   └── indices/
│       └── ... (índices de hash con versiones)
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── functional/
│   └── e2e/
└── README.md

````

- `hash_constants.py`: define constantes de hashing:
  ```python
  HASH_ALGORITHM = "sha256"
  HASH_BLOCK_SIZE = 8192
````

* `installer.py`: interfaz y clases concretas (NpmInstaller, ComposerInstaller) que pueden ejecutar localmente o usar Docker según configuración.

### 3.2 Principios SOLID

1. **S (Single Responsibility)**

   * `HashCalculator`: solo calcula hash.
   * `FileSystemCacheRepository`: solo maneja disco.
   * `ApiKeyValidator`: solo valida claves.

2. **O (Open/Closed)**

   * Para agregar un nuevo manager, crear subclase de `DependencyInstaller` sin cambiar clases existentes.

3. **L (Liskov Substitution)**

   * Subclases de `ICacheRepository` pueden sustituir a la versión de sistema de archivos sin romper lógica.

4. **I (Interface Segregation)**

   * Separar interfaces: `IDependencyInstaller` para instalación, `ICacheRepository` para persistencia.

5. **D (Dependency Inversion)**

   * Casos de uso (`HandleCacheRequest`) dependen de abstracciones (`ICacheRepository`, `IDependencyInstaller`), no de implementaciones concretas.

---

## 4. Componentes Principales

### 4.1 Cliente (`dep_cache_proxy_client`)

#### 4.1.1 Objetivos

* Leer archivos locales de dependencias.
* Calcular hash localmente (usando constantes).
* Enviar petición JSON al servidor.
* Descarga y extracción del ZIP.

#### 4.1.2 Módulos

* **`client/cli.py`**: parseo de argumentos y flujo principal.
* **`client/hash_calculator.py`**: lógica de hashing.
* **`client/http_client.py`**: construcción de petición HTTP y manejo de respuestas.
* **`client/downloader.py`**: descarga y extracción del ZIP.

#### 4.1.3 Argumentos CLI

```bash
dep_cache_proxy_client <endpoint_url> <manager> \
  --apikey=<APIKEY> \
  --files=<file1>,<file2> \
  [--node-version=<VERSION>] [--npm-version=<VERSION>] \
  [--php-version=<VERSION>] \
  [--timeout=<segundos>]
```

* `<endpoint_url>`: URL base del servidor (`http://host:port/api`).
* `<manager>`: identificador (`npm`, `composer`, etc.).
* Flags:

  * `--apikey` (opcional si servidor es público; en otro caso, obligatorio).
  * `--files` (obligatorio; lista separada por comas).
  * `--node-version`, `--npm-version` (opcionales, relevantes solo para `npm`).
  * `--php-version` (opcional, relevante solo para `composer`).
  * `--timeout` (por defecto 60 segundos).

#### 4.1.4 Flujo Cliente (resumido)

1. Parsear argumentos y validar archivos.
2. Construir diccionario `versions` según manager.
3. Calcular hash local con `HashCalculator` (incluye versiones en hash).
4. Leer cada fichero en binario, codificar en Base64.
5. Construir JSON:

   ```jsonc
   {
     "manager": "npm",
     "hash": "abcdef1234...",
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
6. Enviar `POST <endpoint_url>/v1/cache` con cabecera `Authorization: Bearer <APIKEY>`.
7. Si `200 OK`, parsear `download_url` y `cache_hit`.
8. Descargar ZIP y extraer en carpeta (`node_modules` o `vendor`).

---

### 4.2 Servidor (`dep_cache_proxy_server`)

#### 4.2.1 Objetivos

* Recibir peticiones de cache y devolver URL de descarga.
* Validar API key (si aplica).
* Verificar versiones solicitadas contra versiones soportadas.
* En caso de desajuste de versión:

  * **Error** o
  * **Generar dependencias con Docker** (si se configura).
* Gestionar cache en disco: `cache/objects/`, `cache/indices/`.

#### 4.2.2 Módulos

* **`server/domain/hash_constants.py`**

  ```python
  HASH_ALGORITHM = "sha256"
  HASH_BLOCK_SIZE = 8192
  ```
* **`server/domain/dependency_set.py`**: define la entidad `DependencySet` y cálculo de hash.
* **`server/domain/cache_object.py`**: define `CacheObject` y paths en disco.
* **`server/domain/cache_repository.py`**: interfaz `ICacheRepository`.
* **`server/domain/installer.py`**: interfaz `DependencyInstaller` + implementaciones (NpmInstaller, ComposerInstaller).
* **`server/domain/zip_util.py`**: utilidades para listado de archivos, checksums, compresión.
* **`server/infrastructure/file_system_cache_repository.py`**: implementación de `ICacheRepository`.
* **`server/infrastructure/api_key_validator.py`**: validador de API keys.
* **`server/infrastructure/docker_utils.py`**: funciones auxiliares para ejecutar comandos Docker.
* **`server/application/dtos.py`**: define `CacheRequestDTO` y `CacheResponseDTO`.
* **`server/application/handle_cache_request.py`**: orquesta la lógica de hit/miss, generación y persistencia.
* **`server/interfaces/main.py`**: define FastAPI, parseo de argumentos de servidor y arranque de Uvicorn.

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

* `<port>`: entero (ej. `8080`).
* `--cache_dir`: carpeta base de cache (ej. `./cache`).
* `--supported-versions-node`: lista separada por comas de pares `node_version:npm_version`. Ej: `14.20.0:6.14.13,16.15.0:8.5.0`.
* `--supported-versions-php`: lista separada por comas de versiones `php`. Ej: `8.1.0,7.4.0`.
* `--use-docker-on-version-mismatch`: si se pasa, el servidor usará Docker para generar dependencias cuando la versión solicitada no esté en la lista soportada.
* `--is_public`: si está presente, el servidor no valida API key.
* `--api-keys`: lista separada por comas de claves válidas (obligatorio si `--is_public=false`).

#### 4.2.4 Flujo Servidor (resumido)

1. Parsear argumentos y validar `cache_dir` (crearlo si no existe).
2. Leer `supported_versions_node` y `supported_versions_php` en memoria (diccionarios o sets).
3. Inicializar `FileSystemCacheRepository(cache_dir)`.
4. Inicializar `ApiKeyValidator(api_keys)` si `is_public=false`.
5. Crear FastAPI con:

   * `POST /v1/cache` → `cache_endpoint()`.
   * `GET /download/{hash}.zip` → `download_endpoint()`.
6. En `cache_endpoint()`:

   1. Validar API key (si aplica).
   2. Parsear JSON y crear `CacheRequestDTO`.
   3. Verificar `dto.manager` en `["npm","composer"]` (o lista dinámica de managers).
   4. Verificar versiones solicitadas:

      * Para `npm`: `(node_version, npm_version)` en `supported_versions_node`.
      * Para `composer`: `php_version` en `supported_versions_php`.
      * Si no está soportada:

        * Si `--use-docker-on-version-mismatch=false`:

          * Retornar `400 Bad Request`: “Versión no soportada”.
        * Si `--use-docker-on-version-mismatch=true`:

          * Marcar `use_docker = True` en DTO (o en el manejador).
   5. Llamar a `handler.execute(dto, base_download_url, use_docker)`.
   6. Devolver JSON con `download_url` y `cache_hit`.
7. En `download_endpoint(hash)`:

   * Buscar en `cache/objects/<h0h1>/<h2h3>/<hash>.<manager>/<hash>.zip`.
   * Si existe, retornar `FileResponse`.
   * Si no, `404 Not Found`.

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
from pathlib import Path
from typing import Dict

from .hash_constants import HASH_ALGORITHM, HASH_BLOCK_SIZE

class DependencySet:
    """
    Representa:
      - manager: "npm" o "composer"
      - file_contents: {"package.json": b"...", "package.lock": b"..."}
      - versions: {"node": "14.20.0", "npm": "6.14.13"} para npm,
                  {"php": "8.1.0"} para composer.
    Calcula un hash SHA256 incluyendo manager, versiones y contenido de ficheros.
    """
    def __init__(self, manager: str, file_contents: Dict[str, bytes], versions: Dict[str, str]):
        self.manager = manager
        self.file_contents = file_contents
        self.versions = versions
        self.hash = self.calculate_hash()

    def calculate_hash(self) -> str:
        sha = hashlib.new(HASH_ALGORITHM)
        # Incluir manager
        sha.update(self.manager.encode("utf-8"))
        sha.update(b"\n")
        # Incluir cada archivo en orden alfabético
        for name in sorted(self.file_contents.keys()):
            content = self.file_contents[name]
            # Alimentar por bloques
            idx = 0
            while idx < len(content):
                chunk = content[idx: idx + HASH_BLOCK_SIZE]
                sha.update(chunk)
                idx += HASH_BLOCK_SIZE
        # Incluir versiones, ordenadas por clave
        for key in sorted(self.versions.keys()):
            val = self.versions[key]
            line = f"{key}={val}\n".encode("utf-8")
            sha.update(line)
        return sha.hexdigest()
```

* **Notas**:

  * El algoritmo está en `HASH_ALGORITHM`.
  * El tamaño de bloque en `HASH_BLOCK_SIZE`.
  * El hash resultante incluye manager y versiones, por lo que variaciones de versión producen hash distinto.

### 5.3 Entidad: `CacheObject` (`cache_object.py`)

```python
# server/domain/cache_object.py
from pathlib import Path

class CacheObject:
    """
    Representa la cache de una combinación específica:
      - hash: hex string
      - manager: "npm" o "composer"
      - manager_version: para npm, "<node_version>_<npm_version>"; para composer, "<php_version>"
    Define rutas para:
      - output_folder (node_modules/ o vendor/)
      - meta_index_file: <hash>.<manager>.<manager_version>.index
      - zip_file: <hash>.zip
    """
    def __init__(self, base_dir: Path, hash_hex: str, manager: str, manager_version: str):
        self.hash = hash_hex
        self.manager = manager
        self.manager_version = manager_version  # ej. "14.20.0_6.14.13" o "8.1.0"
        h0_2 = hash_hex[0:2]
        h2_4 = hash_hex[2:4]
        # Ruta final de este cache object:
        self.cache_root = base_dir / "objects" / h0_2 / h2_4 / f"{hash_hex}.{manager}"
        # Carpeta interna con dependencias:
        self.output_folder_name = "node_modules" if manager == "npm" else "vendor"
        self.output_folder = self.cache_root / self.output_folder_name
        # Archivo de índice de hash (metadata)
        self.meta_index_file = self.cache_root / f"{hash_hex}.{manager}.{manager_version}.index"
        # Archivo ZIP
        self.zip_file = self.cache_root / f"{hash_hex}.zip"

    def exists(self) -> bool:
        return (
            self.cache_root.is_dir()
            and self.meta_index_file.is_file()
            and self.zip_file.is_file()
        )
```

### 5.4 Entidad/Interfaz: `ICacheRepository` (`cache_repository.py`)

```python
# server/domain/cache_repository.py
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from .cache_object import CacheObject

class ICacheRepository(ABC):
    @abstractmethod
    def get(self, cache_key: str, manager_version: str) -> Optional[CacheObject]:
        """
        Retorna CacheObject si existe, o None en otro caso.
        cache_key: "<hash>.<manager>"
        manager_version: versión combinada (ej. "14.20.0_6.14.13")
        """
        pass

    @abstractmethod
    def save(self, cache_obj: CacheObject) -> None:
        """
        Persiste en disco el CacheObject (asume que los archivos ya están
        en disco en las rutas apropiadas).
        """
        pass

    @abstractmethod
    def compute_path(self, cache_key: str) -> Path:
        """
        Dado cache_key, retorna la ruta absoluta donde debería residir.
        """
        pass
```

---

## 6. Estructura de Directorios en Cache

El servidor mantendrá dos carpetas principales bajo `cache_dir`:

```
<cache_dir>/
├── objects/
│   ├── 00/00/
│   │   ├── <hash>.npm/
│   │   │   ├── node_modules/...
│   │   │   ├── <hash>.npm.<manager_version>.index
│   │   │   └── <hash>.zip
│   │   └── <hash2>.composer/
│   │       ├── vendor/...
│   │       ├── <hash2>.composer.<manager_version>.index
│   │       └── <hash2>.zip
│   ├── 00/01/
│   └── ...
├── indices/
│   ├── <hash>.npm.<manager_version>.index
│   └── <hash2>.composer.<manager_version>.index
└── logs/  (opcional, para registros de operación)
```

* **`objects/`**:

  * Guarda los archivos reales de `node_modules` y `vendor`.
  * Cada carpeta `<hash>.<manager>` incluye:

    * Subcarpeta con dependencias (`node_modules/` o `vendor/`).
    * Indice de hash de archivos: `<hash>.<manager>.<manager_version>.index`.
    * ZIP: `<hash>.zip`.

* **`indices/`**:

  * Duplicado centralizado de todos los índices de hash, para poder listarlos sin recorrer `objects/`.
  * Cada índice lleva en su nombre la versión del manager.

### 6.1 Nombre de Índices de Hash

* Para NPM:

  ```
  <hash>.npm.<node_version>_<npm_version>.index
  ```

  Ejemplo: `ab12cd34.npm.14.20.0_6.14.13.index`

* Para Composer:

  ```
  <hash>.composer.<php_version>.index
  ```

  Ejemplo: `aa11bb22.composer.8.1.0.index`

Los índices contienen líneas con formato:

```
<ruta_relativa>;<tamaño_bytes>;<sha256_hex>
```

Ejemplo:

```
node_modules/packageA/index.js;12034;ff3a2b...
node_modules/packageB/lib/util.js;4531;9ac8d1...
```

---

## 7. Flujo de Trabajo Completo

A continuación, el flujo actualizado incorporando la lógica de versiones y Docker:

1. **Cliente**

   ```bash
   dep_cache_proxy_client https://servidor:8080/api npm \
       --apikey=MI_API_KEY \
       --files=package.json,package.lock \
       --node-version=14.20.0 \
       --npm-version=6.14.13
   ```

   * El cliente lee `package.json` y `package.lock`.
   * Construye `versions = {"node": "14.20.0", "npm": "6.14.13"}`.
   * Crea `DependencySet(manager="npm", file_contents, versions)`.
   * `hash_local = dependency_set.calculate_hash()`.
   * Codifica ficheros en Base64 y arma payload JSON.
   * Envía `POST https://servidor:8080/api/v1/cache` con:

     * Headers: `Authorization: Bearer MI_API_KEY`.
     * JSON:

       ```jsonc
       {
         "manager": "npm",
         "hash": "ab12cd34...",
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
   * Espera respuesta.

2. **Servidor: `POST /v1/cache`**

   * FastAPI recibe la request y ejecuta `cache_endpoint(request)`.
   * **Validar API Key** (si `--is_public=false`):

     * Obtener header `Authorization`, extraer clave y verificar con `ApiKeyValidator`.
     * Si inválida → `HTTP 401 Unauthorized`.
   * Parsear JSON en `CacheRequestDTO`.
   * **Validar Manager**:

     * Si `dto.manager` no está en lista (p.ej., `["npm","composer"]`), → `HTTP 400 Bad Request`.
   * **Validar Versiones**:

     * Para `npm`: formar tupla `(node_version, npm_version)` de `dto.versions`.

       * Si no está en `supported_versions_node`:

         * Si `use_docker_on_version_mismatch == False`:

           * `HTTP 400 Bad Request: "Versión de Node/NPM no soportada"`.
         * Si `use_docker_on_version_mismatch == True`:

           * Marcar `use_docker = True`.
     * Para `composer`:

       * `php_version = dto.versions["php"]`.
       * Si no está en `supported_versions_php`:

         * Igual lógica de error vs Docker.
   * **Calcular `cache_key`**:

     ```
     cache_key = f"{dto.hash}.{dto.manager}"
     manager_version = 
         "14.20.0_6.14.13"  # Para npm
         o
         "8.1.0"           # Para composer
     ```
   * `cache_obj = cache_repo.get(cache_key, manager_version)`

     * Si existe y `cache_obj.exists()` → **Cache Hit**:

       * `download_url = f"{base_download_url}/download/{dto.hash}.zip"`.
       * Responder `200 OK`: `{"download_url": ..., "cache_hit": true}`.
     * Si no existe → **Cache Miss**:

       1. `temp_dir = mkdtemp(prefix=cache_key)`.
       2. Escribir ficheros `.json` y `.lock` en `temp_dir`.
       3. Determinar `use_docker` según validación de versiones.
       4. `installer = InstallerFactory.get_installer(dto.manager, dto.versions)`
       5. Si `use_docker == False` → `installer.install(temp_dir)` (local).
          Si `use_docker == True` → `installer.install_with_docker(temp_dir, dto.versions)`.
       6. Tras instalación, en `temp_dir` existe `node_modules/` o `vendor/`.
       7. **Copiar a Cache**:

          * `final_cache_dir = cache_repo.compute_path(cache_key)`
          * `copytree(temp_dir/<output_folder>, final_cache_dir/<output_folder>)`
       8. **Generar Índice de Hash de Archivos**:

          * `file_list = ZipUtil.list_all_files(final_cache_dir/<output_folder>)`
          * `checksums = ZipUtil.compute_checksums(final_cache_dir/<output_folder>)`
          * `ZipUtil.write_index(final_cache_dir, dto.hash, dto.manager, manager_version, file_list, checksums)`

            * Esto crea en `final_cache_dir`:

              ```
              <hash>.<manager>.<manager_version>.index
              ```
          * Copiar ese index también a `cache_dir/indices/`.
       9. **Comprimir**:

          * `zip_path = final_cache_dir / f"{dto.hash}.zip"`
          * `ZipUtil.compress_folder(final_cache_dir/<output_folder>, zip_path)`
       10. **Persistir en Repo**:

           * `cache_obj = CacheObject(cache_dir, dto.hash, dto.manager, manager_version)`
           * `cache_repo.save(cache_obj)`
       11. **Eliminar `temp_dir`**.
       12. `download_url = f"{base_download_url}/download/{dto.hash}.zip"`
       13. Responder `200 OK`: `{"download_url": ..., "cache_hit": false}`.

3. **Cliente**

   * Recibe respuesta JSON.
   * Si `cache_hit == true`:

     * Descarga `GET <download_url>`, extrae ZIP en `./node_modules/` (o `./vendor/`).
   * Si `cache_hit == false`:

     * Espera a que el servidor termine la generación y responda con URL (en el mismo request).
     * Descarga y extrae.

4. **Descarga de ZIP**

   * Cliente hace `GET /download/<hash>.zip`.
   * Servidor en `download_endpoint(hash)`:

     * Busca en `cache/objects/<h0h1>/<h2h3>/<hash>.<manager>/<hash>.zip`.
     * Si existe, retorna `FileResponse`.
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

# ----------------------------
# Dominio / Util: HashCalculator
# ----------------------------
from .hash_calculator import HASH_ALGORITHM, HASH_BLOCK_SIZE

class HashCalculator:
    @staticmethod
    def calculate_hash(manager: str, file_paths: list[str], versions: dict) -> str:
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

# ----------------------------
# Cliente: Main CLI
# ----------------------------
def parse_args():
    parser = argparse.ArgumentParser(
        description="Cliente CLI de DepCacheProxy"
    )
    parser.add_argument("endpoint_url", type=str, help="URL base del servidor (http://host:port/api)")
    parser.add_argument("manager", type=str, help="Gestor de dependencias (npm, composer, etc.)")
    parser.add_argument("--apikey", type=str, required=False, help="API Key (si aplica)")
    parser.add_argument(
        "--files", type=str, required=True,
        help="Ficheros separados por coma, e.g. package.json,package.lock"
    )
    parser.add_argument("--node-version", type=str, required=False, help="Versión de NodeJS (solo para npm)")
    parser.add_argument("--npm-version", type=str, required=False, help="Versión de NPM (solo para npm)")
    parser.add_argument("--php-version", type=str, required=False, help="Versión de PHP (solo para composer)")
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

    # Calcular hash local
    hash_hex = HashCalculator.calculate_hash(manager, file_list, versions)
    print(f"[INFO] Hash calculado: {hash_hex}")

    # Leer y codificar ficheros en base64
    files_b64 = {}
    for fp in file_list:
        with open(fp, "rb") as f:
            files_b64[os.path.basename(fp)] = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "manager": manager,
        "hash": hash_hex,
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
        print("[INFO] Cache hit: descargando paquete comprimido...")
    else:
        print("[INFO] Cache miss: el servidor está generando dependencias. Descargando cuando esté listo...")

    # Descargar ZIP
    try:
        zip_resp = requests.get(download_url, stream=True, timeout=args.timeout)
        if zip_resp.status_code != 200:
            print(f"ERROR: No se pudo descargar ZIP (código {zip_resp.status_code}).")
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

    # Extraer ZIP en carpeta local de dependencias
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

# Importar dominio e infraestructura
from server.domain.hash_constants import HASH_ALGORITHM, HASH_BLOCK_SIZE
from server.domain.dependency_set import DependencySet
from server.domain.cache_object import CacheObject
from server.domain.cache_repository import ICacheRepository
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
        installer_factory: InstallerFactory,
        zip_util: ZipUtil,
        supported_versions_node: Dict[str, str],
        supported_versions_php: List[str],
        use_docker: bool
    ):
        self.cache_repo = cache_repo
        self.installer_factory = installer_factory
        self.zip_util = zip_util
        self.supported_versions_node = supported_versions_node  # {"14.20.0":"6.14.13", ...}
        self.supported_versions_php = supported_versions_php    # ["8.1.0","7.4.0", ...]
        self.use_docker = use_docker

    def execute(self, request_dto: CacheRequestDTO, base_download_url: str) -> CacheResponseDTO:
        manager = request_dto.manager
        hash_hex = request_dto.hash
        versions = request_dto.versions

        # Determinar manager_version
        if manager == "npm":
            node_ver = versions.get("node")
            npm_ver = versions.get("npm")
            if not node_ver or not npm_ver:
                raise RuntimeError("Faltan versiones de Node/NPM")
            manager_version = f"{node_ver}_{npm_ver}"
            # Verificar versiones soportadas
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

        cache_key = f"{hash_hex}.{manager}"
        cache_obj = self.cache_repo.get(cache_key, manager_version)
        if cache_obj and cache_obj.exists():
            download_url = f"{base_download_url}/download/{hash_hex}.zip"
            return CacheResponseDTO(download_url=download_url, cache_hit=True)

        # Cache Miss
        # 1) Crear carpeta temporal
        temp_dir = Path(tempfile.mkdtemp(prefix=cache_key))
        # 2) Escribir ficheros decodificados en temp_dir
        for fname, b64 in request_dto.files.items():
            data = base64.b64decode(b64)
            with open(temp_dir / fname, "wb") as wf:
                wf.write(data)

        # 3) Instalar dependencias
        installer = self.installer_factory.get_installer(manager, versions)
        try:
            if use_docker_exec:
                # Usar Docker para generar dependencias
                run_in_docker(temp_dir, manager, versions)
            else:
                # Instalar localmente
                installer.install(temp_dir)
        except Exception as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise RuntimeError(f"Error al instalar dependencias: {e}")

        # 4) Copiar carpetas de dependencias a cache
        final_cache_dir = self.cache_repo.compute_path(cache_key)
        output_folder = installer.output_folder_name  # "node_modules" o "vendor"
        src_folder = temp_dir / output_folder
        dest_folder = final_cache_dir / output_folder
        dest_folder.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_folder, dest_folder)

        # 5) Generar índice de hash de archivos
        file_list = self.zip_util.list_all_files(dest_folder)
        checksums = self.zip_util.compute_checksums(dest_folder)
        self.zip_util.write_index(
            final_cache_dir, hash_hex, manager, manager_version, file_list, checksums
        )
        # Copiar índice a cache/indices
        idx_src = final_cache_dir / f"{hash_hex}.{manager}.{manager_version}.index"
        idx_dest = final_cache_dir.parent.parent.parent / "indices" / idx_src.name
        idx_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(idx_src, idx_dest)

        # 6) Comprimir carpeta de dependencias
        zip_path = final_cache_dir / f"{hash_hex}.zip"
        self.zip_util.compress_folder(dest_folder, zip_path)

        # 7) Persistir en repo
        cache_obj = CacheObject(final_cache_dir.parent.parent.parent, hash_hex, manager, manager_version)
        self.cache_repo.save(cache_obj)

        # 8) Limpiar carpeta temporal
        shutil.rmtree(temp_dir, ignore_errors=True)

        download_url = f"{base_download_url}/download/{hash_hex}.zip"
        return CacheResponseDTO(download_url=download_url, cache_hit=False)

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
    cache_repo = FileSystemCacheRepository(cache_dir)
    installer_factory = InstallerFactory()
    zip_util = ZipUtil()
    validator = ApiKeyValidator(api_keys) if not is_public else None
    handler = HandleCacheRequest(
        cache_repo, installer_factory, zip_util,
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

        payload = await request.json()
        try:
            dto = CacheRequestDTO(**payload)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Payload inválido: {e}")

        # Validar manager soportado
        supported_managers = ["npm", "composer"]  # Podría ampliarse dinámicamente
        if dto.manager not in supported_managers:
            raise HTTPException(status_code=400, detail=f"Manager no soportado: {dto.manager}")

        try:
            response_dto = handler.execute(dto, base_download_url)
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))
        except RuntimeError as re:
            raise HTTPException(status_code=500, detail=str(re))
        return JSONResponse(status_code=200, content=response_dto.dict())

    @app.get("/download/{hash}.zip")
    async def download_endpoint(hash: str):
        # Buscar ZIP en objects/ para cualquier manager
        for manager in ["npm", "composer"]:
            # Reconstruir rutas
            h0_2 = hash[0:2]
            h2_4 = hash[2:4]
            cache_root = cache_dir / "objects" / h0_2 / h2_4
            folder_npm = cache_root / f"{hash}.{manager}"
            zip_path = folder_npm / f"{hash}.zip"
            if zip_path.is_file():
                return FileResponse(zip_path, filename=f"{hash}.zip", media_type="application/zip")
        raise HTTPException(status_code=404, detail="ZIP no encontrado")

    return app

def parse_args():
    parser = argparse.ArgumentParser(description="Servidor DepCacheProxy")
    parser.add_argument("port", type=int, help="Puerto HTTP donde escuchará (ej. 8080)")
    parser.add_argument("--cache_dir", type=str, required=True, help="Directorio base de cache")
    parser.add_argument(
        "--supported-versions-node", type=str, required=True,
        help="Lista de pares node_version:npm_version separados por comas, e.g. 14.20.0:6.14.13,16.15.0:8.5.0"
    )
    parser.add_argument(
        "--supported-versions-php", type=str, required=True,
        help="Lista de versiones de PHP separadas por comas, e.g. 8.1.0,7.4.0"
    )
    parser.add_argument(
        "--use-docker-on-version-mismatch",
        action="store_true",
        help="Si se especifica, usar Docker para generar dependencias cuando la versión no está soportada"
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

    # Parsear supported_versions_node en dict
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

    # Verificar cache_dir
    try:
        (cache_dir / "objects").mkdir(parents=True, exist_ok=True)
        (cache_dir / "indices").mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"ERROR: No se puede crear accesos en cache_dir '{cache_dir}': {e}")
        sys.exit(1)

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

#### 8.2.1 Comentarios de Pseudocódigo Servidor

* **Constantes de Hash** definidas en `hash_constants.py`.
* **Validación de versiones**:

  * Se comparan tuplas `(node, npm)` contra el dict `supported_versions_node`.
  * Si no coincide y `use_docker_on_version_mismatch=true`, se usa Docker.
  * En caso contrario, se lanza `ValueError` para producir `400 Bad Request`.
* **Docker**:

  * Función `run_in_docker(temp_dir, manager, versions)` en `server/infrastructure/docker_utils.py` gestiona ejecución con `subprocess.run(["docker", ...])`.
* **Índices de Hash**:

  * Generación de `<hash>.<manager>.<manager_version>.index` y copia concurrente a `cache/indices/`.

---

## 9. API HTTP y Esquema de Rutas

### 9.1 Rutas

| Método | Ruta                   | Descripción                                                 | Request Body      | Respuestas                                                                                                    |
| ------ | ---------------------- | ----------------------------------------------------------- | ----------------- | ------------------------------------------------------------------------------------------------------------- |
| POST   | `/v1/cache`            | Solicita cache de dependencias: hit/miss y URL de descarga. | `CacheRequestDTO` | `200 OK` → `CacheResponseDTO` <br> `400 Bad Request` <br> `401 Unauthorized` <br> `500 Internal Server Error` |
| GET    | `/download/{hash}.zip` | Descarga el ZIP generado para el hash proporcionado.        | Ninguno           | `200 OK` → ZIP <br> `404 Not Found`                                                                           |

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

* **Campos**:

  * `manager` (string, obligatorio).
  * `hash` (string, obligatorio).
  * `files` (map\<string, string>, obligatorio).
  * `versions` (map\<string, string>, obligatorio):

    * Para `npm`: debe incluir `"node"` y `"npm"`.
    * Para `composer`: debe incluir `"php"`.

### 9.3 `CacheResponseDTO`

```jsonc
{
  "download_url": "http://server:8080/download/ab12cd34ef56... .zip",
  "cache_hit": true
}
```

* **Campos**:

  * `download_url` (string, obligatorio).
  * `cache_hit` (boolean, obligatorio).

---

## 10. Estructura de Pruebas

Para asegurar calidad y cobertura, se recomienda organizar pruebas en:

```
tests/
├── unit/
│   ├── test_hash_calculator.py          # Pruebas de hashing
│   ├── test_api_key_validator.py        # Pruebas de validador de API Key
│   ├── test_installer_factory.py        # Pruebas de fábrica de instaladores
│   └── test_zip_util.py                 # Pruebas de utilidades de ZIP
├── integration/
│   ├── test_handle_cache_request_hit.py   # Flujo de cache hit
│   ├── test_handle_cache_request_miss.py  # Flujo de cache miss
│   └── test_docker_installation.py        # Verificar que run_in_docker funciona
├── functional/
│   ├── test_cli_client_request.py         # Verificar cliente → servidor (modo mock)
│   └── test_server_download_endpoint.py    # Verificar descarga de ZIP
└── e2e/
    ├── test_end_to_end_npm.py             # Configurar contenedores: servidor+cliente Docker
    └── test_end_to_end_composer.py        # Mismo para Composer
```

### 10.1 Pruebas Unitarias

* **`test_hash_calculator.py`**

  * Caso 1: Mismos ficheros y versiones → mismo hash.
  * Caso 2: Diferente versión de NPM → hash distinto.
* **`test_api_key_validator.py`**

  * Clave válida → `validate` devuelve `True`.
  * Clave inválida → `False`.
* **`test_installer_factory.py`**

  * `get_installer("npm", {...})` → instancia `NpmInstaller`.
  * `get_installer("composer", {...})` → instancia `ComposerInstaller`.
  * `get_installer("otro")` → lanza `ValueError`.
* **`test_zip_util.py`**

  * `list_all_files` retorna lista correcta de rutas relativas.
  * `compute_checksums` produce checksums correctos.
  * `compress_folder` genera ZIP válida.

### 10.2 Pruebas de Integración

* **`test_handle_cache_request_hit.py`**

  * Preparar `cache_repo` con carpeta de cache existente (usando `CacheObject`) y verificar que `handler.execute` retorna `cache_hit=True` y URL correcta.
* **`test_handle_cache_request_miss.py`**

  * Crear un `CacheRequestDTO` con hash nuevo.
  * Asegurarse de que tras `execute`, existen:

    * Carpeta `cache/objects/.../<hash>.<manager>/node_modules` o `vendor`.
    * Índice en `cache/objects/.../<hash>.<manager>/<hash>.<manager>.<manager_version>.index` y en `cache/indices/`.
    * Archivo ZIP correcto.
    * `cache_hit=False`.
* **`test_docker_installation.py`**

  * Verificar que, dada versión no soportada y `use_docker=true`, `run_in_docker` cree carpeta `node_modules/` o `vendor/` en `temp_dir`.

### 10.3 Pruebas Funcionales

* **`test_cli_client_request.py`**

  * Ejecutar `dep_cache_proxy_client` apuntando a un servidor FastAPI levantado en modo test (usando `TestClient` de FastAPI).
  * Verificar mensajes de consola y resultado de extracción en carpeta adecuada.
* **`test_server_download_endpoint.py`**

  * Insertar manualmente un ZIP en `cache/objects/.../<hash>.<manager>/`.
  * Hacer `GET /download/<hash>.zip` y verificar content-type y contenido.

### 10.4 Pruebas End-to-End

* **`test_end_to_end_npm.py`**

  * Levantar contenedor Docker con la imagen del servidor.
  * Montar volumen local como `cache_dir`.
  * Ejecutar `dep_cache_proxy_client` en otro contenedor o en host.
  * Verificar que el ZIP se genera, se descarga y se extrae correctamente en contenedor host.
* **`test_end_to_end_composer.py`**

  * Similar para Composer.

> **Nota**: Utilizar `pytest` y fixtures para aislar entornos temporales (`tmp_path`).

---

## 11. Escenarios de Uso y Casos de Prueba

### 11.1 Escenario 1: Cache hit en NPM (Servidor público, versión soportada)

1. **Servidor** se arranca con:

   ```bash
   dep_cache_proxy_server 8080 \
     --cache_dir=./cache \
     --supported-versions-node=14.20.0:6.14.13,16.15.0:8.5.0 \
     --supported-versions-php=8.1.0 \
     --use-docker-on-version-mismatch \
     --is_public
   ```

   * `is_public=True` → no valida API key.
   * Versiones soportadas:

     * Node/NPM: `(14.20.0,6.14.13)` y `(16.15.0,8.5.0)`.
     * PHP: `8.1.0`.

2. **Cache existente**:

   * `cache/objects/ab/12/ab12cd34.npm/node_modules/...` y `ab12cd34.npm.14.20.0_6.14.13.index`, `ab12cd34.zip`.

3. **Cliente**:

   ```bash
   dep_cache_proxy_client http://localhost:8080/npm npm \
     --files=package.json,package.lock \
     --node-version=14.20.0 \
     --npm-version=6.14.13
   ```

   * Calcula hash `ab12cd34`.
   * Envía `POST /v1/cache` con JSON y recibe:

     ```jsonc
     { "download_url": "http://localhost:8080/download/ab12cd34.zip", "cache_hit": true }
     ```
   * El cliente descarga y extrae en `./node_modules/`.

4. **Resultado**: Cache hit exitoso sin generar nada nuevo.

---

### 11.2 Escenario 2: Cache miss en Composer (Servidor con API key, versión soportada)

1. **Servidor** arranca con:

   ```bash
   dep_cache_proxy_server 8080 \
     --cache_dir=./cache \
     --supported-versions-node=14.20.0:6.14.13 \
     --supported-versions-php=8.1.0,7.4.0 \
     --api-keys=KEY1,KEY2
   ```

   * `use_docker_on_version_mismatch` no se especifica (default `false`).
   * Versiones soportadas:

     * Node/NPM: `(14.20.0,6.14.13)`.
     * PHP: `8.1.0`, `7.4.0`.

2. **Cliente**:

   ```bash
   dep_cache_proxy_client http://localhost:8080/api composer \
     --apikey=KEY1 \
     --files=composer.json,composer.lock \
     --php-version=8.1.0
   ```

   * Hash calculado: `aa11bb22`.
   * Envía petición:

     ```jsonc
     {
       "manager": "composer",
       "hash": "aa11bb22",
       "files": { "composer.json": "<base64>", "composer.lock": "<base64>" },
       "versions": { "php": "8.1.0" }
     }
     ```
   * Servidor valida API key → OK.
   * `php_version = "8.1.0"` está en `supported_versions_php`.
   * `cache_repo.get("aa11bb22.composer", "8.1.0")` → `None` (no existe).
   * Crea `temp_dir`, escribe ficheros, ejecuta `installer.install(temp_dir)` que hace:

     ```bash
     cd temp_dir
     composer install --no-dev --prefer-dist --no-scripts
     ```
   * Copia `temp_dir/vendor` a `cache/objects/aa/11/aa11bb22.composer/vendor`.
   * Genera índice `aa11bb22.composer.8.1.0.index` en:

     ```
     cache/objects/aa/11/aa11bb22.composer/aa11bb22.composer.8.1.0.index
     ```

     y copia a:

     ```
     cache/indices/aa11bb22.composer.8.1.0.index
     ```
   * Genera `aa11bb22.zip` con `/vendor` y lo coloca en:

     ```
     cache/objects/aa/11/aa11bb22.composer/aa11bb22.zip
     ```
   * Limpia `temp_dir`.

3. **Respuesta**:

   ```jsonc
   { "download_url": "http://localhost:8080/download/aa11bb22.zip", "cache_hit": false }
   ```

4. **Cliente**:

   * Descarga y descomprime en `./vendor/`.

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

   * `use_docker_on_version_mismatch=false` (default).

2. **Cliente**:

   ```bash
   dep_cache_proxy_client http://localhost:8080/api npm \
     --apikey=KEY1 \
     --files=package.json,package.lock \
     --node-version=16.15.0 \
     --npm-version=8.5.0
   ```

   * Hash `cc33dd44`.
   * Servidor valida versiones:

     * `(16.15.0,8.5.0)` **no** está en `supported_versions_node`.
     * `use_docker_on_version_mismatch==false` →

       * `handler.execute` lanza `ValueError("Versión de Node/NPM no soportada")`.
   * `cache_endpoint` captura `ValueError` y responde:

     ```http
     HTTP 400 Bad Request
     Content-Type: application/json

     { "detail": "Versión de Node/NPM no soportada" }
     ```

3. **Cliente**:

   * Recibe `resp.status_code == 400` y muestra mensaje de error en consola.

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

   * `use_docker_on_version_mismatch=true`.

2. **Cliente**:

   ```bash
   dep_cache_proxy_client http://localhost:8080/api npm \
     --apikey=KEY1 \
     --files=package.json,package.lock \
     --node-version=16.15.0 \
     --npm-version=8.5.0
   ```

   * Hash `dd55ee66`.
   * Servidor valida versiones, detecta desajuste:

     * `use_docker_exec = True`.
   * Crea `temp_dir`, escribe ficheros.
   * Llama a `run_in_docker(temp_dir, "npm", {"node":"16.15.0","npm":"8.5.0"})`:

     ```bash
     docker run --rm \
       -v /tmp/dep_cache_dd55ee66:/usr/src/app \
       -w /usr/src/app \
       node:16.15.0 \
       sh -c "npm ci --ignore-scripts --no-audit --cache .npm_cache"
     ```
   * Docker genera `node_modules/` en `temp_dir`.
   * Continúa como en cache miss: copia a `cache/objects/dd/55/dd55ee66.npm/node_modules`, genera índice, comprime, etc.
   * Responde `200 OK` con `cache_hit=false` y `download_url`.

3. **Cliente**:

   * Descarga ZIP y extrae en `./node_modules/`.

---

## 12. Notas de Seguridad, Escalabilidad y Errores Comunes

(Se mantienen las mismas notas generales que en la versión anterior, con énfasis en el uso de Docker.)

### 12.1 Seguridad

1. **Saneamiento de Inputs**:

   * Validar `manager` contra lista blanca.
   * Verificar que `versions` estén en formato esperado (por ejemplo, regex para semver).

2. **Ejecución de Comandos**:

   * Sin Docker: usar listas en `subprocess.run([...])`.
   * Con Docker: no concatenar cadenas con variables sin sanitizar (`node_version`, etc.).

3. **API Keys**:

   * Guardar con hashing si se desea mayor seguridad.
   * Comparar de forma constante (timing-safe).

4. **Entrega de ZIP**:

   * No exponer rutas de sistema fuera de `cache/objects`.

5. **Docker**:

   * Asegurarse de que las imágenes oficiales (`node:<versión>`, `composer:<php_version>`) sean confiables.

### 12.2 Escalabilidad

1. **Concurrencia y Locks**:

   * Implementar lock por `cache_key` para evitar múltiples procesos generando la misma cache simultáneamente.
   * Ejemplo: crear archivo `<cache_root>.lock` y usar `fcntl.flock`.

2. **Retención de Cache**:

   * Políticas de expiración:

     * TTL (p. ej., borrar caches > 30 días sin uso).
     * Mantener un contador de accesos para cache más usados.

3. **Almacenamiento Distribuido**:

   * Reemplazar `FileSystemCacheRepository` por `S3CacheRepository` u otro backend.

### 12.3 Errores Comunes

1. **Desajuste de Hash**:

   * Verificar que se usan las mismas constantes de hashing en cliente y servidor.

2. **Falla en Instalación con Docker**:

   * Verificar que Docker esté instalado y corriendo en el servidor.
   * Asegurarse de que el usuario del proceso tenga permisos para invocar Docker.

3. **Volumen Montado Incorrectamente**:

   * Asegurar que `-v <temp_dir>:/usr/src/app` en Docker mapea correctamente.

4. **Permisos en `cache_dir`**:

   * El proceso de servidor necesita permisos de lectura/escritura en `cache/`.

5. **Carpeta Temporal no Borrada**:

   * En caso de error, siempre llamar a `shutil.rmtree(temp_dir, ignore_errors=True)` en un bloque `finally`.

---

## 13. Facilidad para Añadir Nuevos Managers

Para agregar un nuevo gestor de dependencias (por ejemplo, Yarn, Pip), seguir estos pasos:

1. **Crear Subclase de `DependencyInstaller`**

   * En `server/domain/installer.py`, añadir:

     ```python
     class YarnInstaller(DependencyInstaller):
         @property
         def output_folder_name(self) -> str:
             return "node_modules"  # o la carpeta que Yarn use

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
2. **Actualizar `InstallerFactory`**

   * Modificar método `get_installer`:

     ```python
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
3. **Modificar Validación de Manager**

   * En `cache_endpoint`, permitir `manager == "yarn"`.
   * En validación de versiones, exigir `node_version` para Yarn (similar a NPM).
4. **Actualizar `supported_managers`**

   * Agregar `"yarn"` en la lista de managers soportados.
5. **Actualizar Documentación**

   * Agregar sección en `README.md` describiendo cómo configurar `supported-versions-node` para Yarn.
   * Incluir ejemplo de uso:

     ```bash
     dep_cache_proxy_client http://localhost:8080/api yarn \
       --apikey=KEY \
       --files=package.json,yarn.lock \
       --node-version=14.20.0
     ```
6. **Pruebas para el Nuevo Manager**

   * Agregar tests unitarios en `tests/unit/test_installer_factory.py`.
   * Agregar tests de integración en `tests/integration/test_handle_cache_request_yarn.py`.
   * Agregar pruebas funcionales y E2E similares a las de NPM.

Así, añadir un nuevo manager implica crear la clase del instalador, actualizar la fábrica e incluirlo en la validación de `manager` y en las configuraciones de versiones.

---

## 14. Conclusiones

Este análisis extendido incorpora:

* **Opciones de servidor** para manejar versiones no soportadas con Docker.
* **Requerimiento de hacer obligatorias** las versiones en el servidor, mientras que en el cliente siguen siendo opcionales.
* **Constantes de hash** definidas en `hash_constants.py`.
* **Estructura de cache** revisada, con índices separados y nombres que incluyen versiones de manager.
* **Carpetas temporales** para `node_modules` y `vendor` antes de copiar a cache.
* **Detalle de pruebas**: unitarias, integración, funcionales y end-to-end.
* **Guía clara para agregar nuevos managers**.

Con esta documentación, un equipo de desarrollo o una IA como Claude puede implementar **DepCacheProxy** en Python, estructurado en módulos DDD/SOLID, con toda la lógica de versiones, Docker, hashing y cache.