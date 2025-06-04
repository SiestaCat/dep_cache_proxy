# Análisis Extendido de **DepCacheProxy** (`dep_cache_proxy`)

Este documento detalla de forma exhaustiva el diseño, arquitectura y flujo de trabajo del proyecto **DepCacheProxy**, una librería/proxy para cachear y servir dependencias de paquetes (por ejemplo, `node_modules`, `vendor`) con el fin de acelerar procesos de construcción (por ejemplo, en contenedores Docker) y servir como backend de descarga en entornos con redes inestables. Está diseñado en Python, siguiendo principios DDD (Domain-Driven Design) y SOLID, y dividido en dos componentes principales: cliente y servidor.

---

## Tabla de Contenidos

- [Análisis Extendido de **DepCacheProxy** (`dep_cache_proxy`)](#análisis-extendido-de-depcacheproxy-dep_cache_proxy)
  - [Tabla de Contenidos](#tabla-de-contenidos)
  - [1. Objetivos y Contexto](#1-objetivos-y-contexto)
  - [2. Requisitos Funcionales y No Funcionales](#2-requisitos-funcionales-y-no-funcionales)
    - [2.1 Requisitos Funcionales (RF)](#21-requisitos-funcionales-rf)
    - [2.2 Requisitos No Funcionales (RNF)](#22-requisitos-no-funcionales-rnf)
  - [3. Visión General de la Arquitectura (DDD + SOLID)](#3-visión-general-de-la-arquitectura-ddd--solid)
    - [Principios SOLID aplicados (ejemplos)](#principios-solid-aplicados-ejemplos)
  - [4. Componentes Principales](#4-componentes-principales)
    - [4.1 Cliente (`dep_cache_proxy_client`)](#41-cliente-dep_cache_proxy_client)
      - [4.1.1 Parámetros CLI y Validaciones](#411-parámetros-cli-y-validaciones)
    - [4.2 Servidor (`dep_cache_proxy_server`)](#42-servidor-dep_cache_proxy_server)
      - [4.2.1 Parámetros CLI y Validaciones](#421-parámetros-cli-y-validaciones)
  - [5. Modelo de Dominio y Hashing](#5-modelo-de-dominio-y-hashing)
    - [5.1 Entidad: `DependencySet`](#51-entidad-dependencyset)
    - [5.2 Entidad: `CacheObject`](#52-entidad-cacheobject)
    - [5.3 Entidad/Agregado: `CacheRepository` (Interfaz)](#53-entidadagregado-cacherepository-interfaz)
    - [5.4 Dominio: `HashCalculator`](#54-dominio-hashcalculator)
  - [6. Estructura de Directorios en Cache](#6-estructura-de-directorios-en-cache)
  - [7. Flujo de Trabajo Completo](#7-flujo-de-trabajo-completo)
  - [8. Detalles de Implementación y Pseudocódigo](#8-detalles-de-implementación-y-pseudocódigo)
    - [8.1 Pseudocódigo Cliente](#81-pseudocódigo-cliente)
      - [Comentarios de Pseudocódigo Cliente](#comentarios-de-pseudocódigo-cliente)
    - [8.2 Pseudocódigo Servidor](#82-pseudocódigo-servidor)
      - [Comentarios de Pseudocódigo Servidor](#comentarios-de-pseudocódigo-servidor)
  - [9. API HTTP y Esquema de Rutas](#9-api-http-y-esquema-de-rutas)
    - [9.1 Rutas Principales](#91-rutas-principales)
    - [9.2 Esquema de Request y Response](#92-esquema-de-request-y-response)
      - [9.2.1 `CacheRequestDTO`](#921-cacherequestdto)
      - [9.2.2 `CacheResponseDTO`](#922-cacheresponsedto)
  - [10. Escenarios de Uso y Casos de Prueba](#10-escenarios-de-uso-y-casos-de-prueba)
    - [10.1 Escenario 1: Cache hit en NPM (Servidor público)](#101-escenario-1-cache-hit-en-npm-servidor-público)
    - [10.2 Escenario 2: Cache miss en Composer (Servidor con API key)](#102-escenario-2-cache-miss-en-composer-servidor-con-api-key)
    - [10.3 Escenario 3: Petición con API key inválida](#103-escenario-3-petición-con-api-key-inválida)
    - [10.4 Escenario 4: Manager no soportado](#104-escenario-4-manager-no-soportado)
  - [11. Notas de Seguridad, Escalabilidad y Errores Comunes](#11-notas-de-seguridad-escalabilidad-y-errores-comunes)
    - [11.1 Seguridad](#111-seguridad)
    - [11.2 Escalabilidad y Concurrencia](#112-escalabilidad-y-concurrencia)
    - [11.3 Errores Comunes y Cómo Manejarlos](#113-errores-comunes-y-cómo-manejarlos)
  - [12. Conclusiones](#12-conclusiones)

---

## 1. Objetivos y Contexto

1. **Cachear dependencias**  
   - Guardar localmente (en disco del servidor) los paquetes descargados a partir de `package.json` + `package.lock` (o `composer.json` + `composer.lock`) para evitar descargas redundantes y ahorrar ancho de banda y tiempo.  
   - Cada combinación única de ficheros de definición + lockfile genera un _hash específico_. Ese hash identifica una “versión de conjunto de dependencias”.  

2. **Proveer un proxy/respaldo de descarga**  
   - En entornos donde la red del cliente sea inestable (timeouts, latencia), el servidor **DepCacheProxy** actúa como fuente secundaria para que el cliente recupere el ZIP preconstruido de dependencias en lugar de descargar directo de npm o Packagist.  

3. **Acelerar procesos de construcción Docker u otros pipelines**  
   - En lugar de ejecutar siempre `npm install` / `npm ci` o `composer install`, se puede descargar el ZIP que contiene la carpeta `node_modules` o `vendor` ya cargada, evitando tiempo de instalación.  

4. **Soporte extensible a múltiples gestores de dependencias**  
   - Aunque se muestran ejemplos con NPM y Composer, la librería **DepCacheProxy** está diseñada de forma genérica para “package managers” arbitrarios.  
   - Puntos clave a parametrizar:  
     - Tipo de gestor (NPM/Composer/Otros)  
     - Versiones posibles de NodeJS/NPM o PHP/Composer (opcionales)  
     - Comandos concretos para instalar dependencias  

5. **Principios de diseño**  
   - **DDD (Domain-Driven Design)**: Separar capa de dominio (modelo de hashes, objetos de cache, lógica de invalidez), capa de aplicación (servicios de generación de paquetes, compresión, verificación de API key, reconstrucción de ZIP) e infraestructura (persistencia en disco, HTTP server).  
   - **SOLID**: Clases limpias, cada módulo con responsabilidad única, inyección de dependencias para facilitar pruebas unitarias y extensibilidad.  

6. **Lenguaje y Paradigmas**  
   - **Python 3.x**, aprovechando módulos estándar (`hashlib`, `tempfile`, `subprocess`, `zipfile`, `http.server` o frameworks ligeros como FastAPI/Flask).  
   - Arquitectura modular: `domain/`, `application/`, `infrastructure/`, `interfaces/` (para DDD).  

7. **Dos Partes**  
   - **Cliente CLI**: Ejecutable `dep_cache_proxy_client` que:  
     1. Recoge ficheros de definición de dependencias (`package.json`, `package.lock` o `composer.json`, `composer.lock`) y versión(es) opcionales.  
     2. Calcula un hash local de la combinación de ficheros.  
     3. Llama al endpoint HTTP del servidor (`dep_cache_proxy_server`) con parámetros: URL, gestor, API key (opcional), lista de ficheros (embebidos o multipart).  
     4. Si existe la cache en servidor, recibe una URL de descarga directa. Si no existe, espera a que el servidor genere el ZIP y devuelva URL.  
     5. Descarga el ZIP y descomprime en la carpeta propiamente correspondiente (`node_modules/` o `vendor/`).  

   - **Servidor HTTP**: Ejecutable `dep_cache_proxy_server` que:  
     1. Expone ruta HTTP (por ejemplo, `POST /v1/cache`) para recibir la request de cliente.  
     2. Valida API key (a menos que `--is_public` true).  
     3. Valida que el `manager` (en lugar de “type”) es soportado (`npm`, `composer`, o extensible).  
     4. Calcula el hash basado en el contenido de ficheros recibidos.  
     5. Busca en su árbol de cache (`cache/objects/`) si existe la carpeta de objetos para ese hash.  
        - Si existe, retorna inmediatamente la URL de descarga.  
        - Si no, procede a crear un folder temporal:  
          1. Extrae ficheros `package.json` y `package.lock` en dicho temporal.  
          2. Ejecuta comando de instalación (`npm ci --ignore-scripts --cache .` o `composer install --no-dev --prefer-dist`).  
          3. Cuando finaliza, copia la carpeta `node_modules`/`vendor` al directorio de cache estructurado por hash (ver punto 6).  
          4. Genera un ZIP con contenido de esa carpeta cacheada.  
          5. Guarda en `cache/objects/` los metadatos:  
             - Archivo `<hash>.<manager>.hash` que contiene lista de paths relativos y checksums (opcional) para permitir reconstrucción de ZIP sin tener que descomprimir el cache (p. ej. lista de ficheros con tamaños y rutas).  
          6. Ofrece al cliente la URL única (por ejemplo, `http://<host>:<port>/download/<hash>.zip`).  
     6. Responde con JSON `{ "download_url": "http://..." }`.  

8. **API Keys y Seguridad**  
   - El servidor puede operar en modo **público** (`--is_public=true`), en cuyo caso no valida keys. Por defecto (`--is_public=false`), exige al cliente enviar `--apikey=KEY` y lo compara contra la lista administrada (`--api-keys="KEY1,KEY2,KEY3"`).  
   - El endpoint devolverá `401 Unauthorized` si falla la validación de API key.  

9. **Cache Persistente**  
   - **cache_dir**: directorio configurable donde se guarda la estructura de cache (por defecto `./cache/`).  
   - Dentro de `cache_dir` encontramos:  
     - `objects/` (estructura basada en hash de objetos)  
     - `metadata/` (opcional: logs de requests, índice de hashes, expiración)  

10. **Llaves de Diseño**  
    - Cada combinación de ficheros y versiones opcionales produce un único hash SHA256 (o SHA1+fecha, configurable).  
    - Estructura de directorios en base a hash:  
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
    - El archivo `<hash>.<manager>.hash` contiene:  
      - Lista de rutas relativas dentro de la carpeta final (para reconstruir el ZIP sin recorrrer todo el árbol).  
      - Checksums de cada archivo (opcionalmente) para validar integridad.  

11. **Parámetros de CLI**  
    - **Cliente**:  
      ```
      dep_cache_proxy_client <endpoint_url> <manager> --apikey=<APIKEY> --files=<file1>,<file2>[,...] [--node-version=<VERSION>] [--npm-version=<VERSION>] [--php-version=<VERSION>]
      ```  
      > Nótese que renombramos el parámetro `<type>` a **`<manager>`** para mayor claridad: ej. `npm`, `composer`, `yarn`, etc.  
      - `<endpoint_url>`: dirección base del servidor (p. ej. `https://my.website/uri`).  
      - `<manager>`: string identificador del gestor de dependencias (p. ej. `npm`, `composer`).  
      - `--apikey`: clave API del cliente (si se requiere).  
      - `--files`: lista separada por comas de ficheros de definición + lockfile. Ej: `package.json,package.lock` o `composer.json,composer.lock`.  
      - Flags opcionales:  
        - `--node-version`: versión de NodeJS (p. ej. `14.17.0`).  
        - `--npm-version`: versión de NPM (p. ej. `6.14.13`).  
        - `--php-version`: versión de PHP (para Composer).  
      - Internamente, el cliente:  
        1. Lee los ficheros y produce el hash.  
        2. Hace `POST` a `/<versión_api>/cache` con JSON/multipart:  
           ```jsonc
           {
             "manager": "npm",
             "hash": "abcdef1234...",
             "files": {
               "package.json": "<contenido_base64>",
               "package.lock": "<contenido_base64>"
             },
             "versions": {
               "node": "14.17.0",
               "npm": "6.14.13"
             }
           }
           ```  
        3. Recibe respuesta con `{ "download_url": "http://..." }`.  
        4. Descarga el ZIP y lo descomprime en `./node_modules/`.

    - **Servidor**:  
      ```
      dep_cache_proxy_server <port> --cache_dir=<CACHE_DIR> [--is_public] [--api-keys=<KEY1>,<KEY2>,...]
      ```  
      - `<port>`: puerto donde escuchar (p. ej. `8080`).  
      - `--cache_dir`: ruta base para cache (p. ej. `/var/lib/dep_cache_proxy/cache`).  
      - `--is_public`: flag booleana (default `false`) que deshabilita validación de API key.  
      - `--api-keys`: lista separada por comas de API keys válidas (solo si `--is_public` es `false`).  

---

## 2. Requisitos Funcionales y No Funcionales

### 2.1 Requisitos Funcionales (RF)

1. **RF1**: El sistema debe aceptar peticiones de clientes que contengan:  
   - Identificador de gestor de dependencias (`manager`).  
   - Ficheros de definición (`package.json`, `package.lock`, `composer.json`, `composer.lock`, etc.).  
   - Versiones opcionales de entornos (`node`, `npm`, `php`).  
   - API key (si no está en modo público).  

2. **RF2**: Calcular un hash único basado en:  
   - Contenido de cada fichero enviado.  
   - (Opcional) versión(es) especificadas.  
   - Gestor de dependencias.  
   - El hash resultante debe ser determinista para identidades de contenidos idénticos.  

3. **RF3**: Validar que el `manager` es soportado. Si no, devolver `400 Bad Request` con mensaje “Manager no soportado”.

4. **RF4**: Comprobar si existe cache para el hash calculado.  
   - Si existe, responder inmediatamente con URL de descarga.  
   - Si no existe, encolar/ejecutar proceso de generación de dependencias.  

5. **RF5**: Generar las dependencias en un directorio temporal, ejecutando comando adecuado:  
   - NPM: `npm ci --ignore-scripts --cache .` (respetando `node-version` y `npm-version` si se proporcionan).  
   - Composer: `composer install --no-dev --prefer-dist` (respetando `php-version`).  
   - Otros gestores: comandos definidos en configuración o plugin.  

6. **RF6**: Copiar la carpeta resultante (`node_modules` o `vendor`) a la estructura de cache basada en hash (`cache/objects/<subdirs>`).  

7. **RF7**: Generar archivo de metadatos `<hash>.<manager>.hash` dentro de la carpeta cacheada, listando:  
   - Rutas relativas de todos los archivos/carpetas cacheadas.  
   - Opcionalmente, checksums individuales.  

8. **RF8**: Comprimir la carpeta cacheada en un ZIP (`<hash>.zip`) y exponer endpoint para descargarlo:  
   - `GET /download/<hash>.zip` ⇒ entrega el ZIP.  

9. **RF9**: Si el servidor está en modo cerrado (`--is_public=false`), validar API key en cada petición.  

10. **RF10**: El cliente debe:  
    - Recolectar ficheros definidos en `--files`.  
    - Calcular localmente el mismo hash que el servidor.  
    - Hacer `POST` al servidor con datos codificados (JSON o multipart).  
    - Descargar ZIP en caso necesario y descomprimir en la carpeta de dependencias local.  

11. **RF11**: Proveer logs claros de cada paso, errores significativos y métricas (tiempo de cache hit, hit ratio, tiempo de instalación). (Extensible)  

### 2.2 Requisitos No Funcionales (RNF)

1. **RNF1 (Eficiencia)**:  
   - El cálculo de hash debe ser rápido, usando streaming si los ficheros son grandes.  
   - El servidor debe manejar concurrencia (por ejemplo, con servidor ASGI como Uvicorn/Starlette o Flask + Gunicorn).  

2. **RNF2 (Escalabilidad)**:  
   - Permitir múltiples procesos de generación de dependencias simultáneamente.  
   - Pensar en uso futuro de almacenamiento distribuido (p. ej. S3) para cachear objetos gigantes.  

3. **RNF3 (Extensibilidad)**:  
   - Añadir nuevos gestores de dependencias sin modificar la lógica central, usando patrones de diseño (Factory Method o Strategy).  

4. **RNF4 (Seguridad)**:  
   - Validar inputs y sanitizar nombres de archivos.  
   - Evitar inyecciones (por ejemplo, en el nombre del gestor o rutas).  
   - Validar firma de API keys de forma segura (comparadores constantes).  

5. **RNF5 (Portabilidad)**:  
   - Funcionar en Linux y macOS (entornos comunes de CI).  
   - Evitar dependencias nativas muy específicas.  

6. **RNF6 (Mantenibilidad)**:  
   - Seguir convenciones PEP8, documentación con docstrings y tipo de anotaciones (type hints).  
   - Pruebas unitarias y de integración (pytest).  

7. **RNF7 (Disponibilidad)**:  
   - El servidor no soportará HTTPS directamente, se asume que estará detrás de un proxy inverso (Nginx, Traefik) que provea TLS.  

---

## 3. Visión General de la Arquitectura (DDD + SOLID)

Enfoque DDD:  
- **Capa de Dominio** (`domain/`):  
  - Entidades principales:  
    - `DependencySet` (representa combinación de ficheros + manager + versiones + hash).  
    - `CacheObject` (representa la carpeta cacheada con su metadato `<hash>.<manager>.hash`).  
  - Agregados:  
    - `CacheRepository` (interfaz para persistencia de objetos cacheados).  
  - Servicios de Dominio:  
    - `HashCalculator` (lógica para combinar ficheros y generar hash).  

- **Capa de Aplicación** (`application/`):  
  - Casos de uso (Use Cases / Interactors):  
    - `HandleCacheRequest` (flujo principal: recibir request, validar, orquestar cálculo/almacenamiento o recuperación de cache).  
    - `GenerateDependencies` (invoca al gestor con versiones específicas).  
    - `CompressCacheObject` (genera ZIP y construye URL).  
    - `ValidateApiKey` (gestiona autorización).  
    - `ListSupportedManagers` (opcional).  
  - DTOs (Data Transfer Objects):  
    - `CacheRequestDTO` (fields: manager, archivos, versiones, api_key).  
    - `CacheResponseDTO` (fields: download_url, cache_hit: bool).  

- **Capa de Infraestructura** (`infrastructure/`):  
  - Implementaciones concretas:  
    - `FileSystemCacheRepository` (persistencia local en `cache/objects`).  
    - `PostgreSQLCacheRepository` (opcional, para metadata extendido).  
    - `SubprocessDependencyInstaller` (ejecución de `npm`, `composer`, etc.).  
    - `HTTPServer` (ASGI con FastAPI/Starlette o Flask).  
  - Adaptadores / Gateways:  
    - `LocalLogger` (escribe logs en disco o stdout).  

- **Capa de Interfaces / Entrypoints** (`interfaces/`):  
  - `main.py` para iniciar el servidor HTTP (`dep_cache_proxy_server`).  
  - `cli_client.py` para el cliente (`dep_cache_proxy_client`).  
  - Controllers (en arquitectura MVC):  
    - `CacheController` (mapea request HTTP a `CacheRequestDTO`, llama a caso de uso y retorna respuesta HTTP).  

- **Aplicación CLI** (`cli/`):  
  - `ClientCLI` (maneja argumentos con `argparse` o `click`, formatea request, deserializa respuesta).  

### Principios SOLID aplicados (ejemplos)

1. **S (Single Responsibility Principle)**  
   - `HashCalculator`: única responsabilidad → calcular hash.  
   - `FileSystemCacheRepository`: única responsabilidad → almacenar/recuperar datos en el sistema de archivos.  
   - `CacheController`: única responsabilidad → recibir HTTP, validar inputs mínimos, invocar caso de uso.  

2. **O (Open/Closed Principle)**  
   - Añadir nuevo gestor de dependencias sin modificar `HandleCacheRequest`. Sino, implementar clase nueva que extienda `DependencyInstaller` y configurarla en una `ManagerFactory`.  

3. **L (Liskov Substitution Principle)**  
   - Pueden crearse subclases de `CacheRepository` (p. ej. `FileSystemCacheRepository`, `S3CacheRepository`) que cumplan la misma interfaz sin romper clientes.  

4. **I (Interface Segregation Principle)**  
   - Separar interfaces de `DependencyInstaller` (solo métodos de instalación), de `CacheRepository` (solo métodos de CRUD en cache).  

5. **D (Dependency Inversion Principle)**  
   - El caso de uso `HandleCacheRequest` no depende de implementaciones concretas, sino de interfaces/prefijos de abstracción (`ICacheRepository`, `IDependencyInstaller`).  

---

## 4. Componentes Principales

### 4.1 Cliente (`dep_cache_proxy_client`)

- **Objetivo**: Leer archivos locales de proyecto, calcular hash, hacer petición al servidor y, en caso de respuesta con URL de ZIP, descargarlo y descomprimirlo en la carpeta de dependencias local.

- **Responsabilidades (SRP)**:  
  1. Parsear argumentos CLI.  
  2. Leer contenido de ficheros especificados.  
  3. Calcular hash local de `DependencySet`.  
  4. Construir y enviar petición HTTP al servidor.  
  5. Recibir response: URL o error.  
  6. Si procede, descargar ZIP y descomprimir en ruta correspondiente.  
  7. Manejar errores de red, reintentos configurables.  

- **Dependencias externas**:  
  - Librerías HTTP (ej. `requests`).  
  - Librerías de compresión (`zipfile`).  

- **Módulos propuestos**:  
  - `client/cli.py`  
  - `client/hash_calculator.py`  
  - `client/http_client.py`  
  - `client/downloader.py`  

- **Ejemplo de Invocación**:  
  ```bash
  # Con gestor npm
  dep_cache_proxy_client https://mi.servidor/api npm --apikey=ABCD1234 --files=package.json,package.lock --node-version=14.20.0 --npm-version=6.14.13

  # Con gestor composer y servidor público
  dep_cache_proxy_client http://localhost:8080 composer --files=composer.json,composer.lock
````

#### 4.1.1 Parámetros CLI y Validaciones

* **Posicionales**:

  1. `<endpoint_url>`: URL base del servidor (p. ej. `http://localhost:8080/api`)
  2. `<manager>`: identificador de gestor (`npm`, `composer`, o aquellos que se admitan).

* **Flags**:

  * `--apikey=<APIKEY>` (opcional si el servidor es público; en caso contrario, obligatorio).
  * `--files=<file1>,<file2>[,...]` (*string listado*) - obligatorio con al menos dos ficheros (definición + lock).
  * `--node-version=<VERSION>` y `--npm-version=<VERSION>` (solo cuando `manager == "npm"`).
  * `--php-version=<VERSION>` (solo cuando `manager == "composer"`).
  * `--timeout=<segundos>` (opcional, por defecto 60s) para peticiones HTTP.

* **Errores posibles**:

  * Faltan ficheros o no existen en el disco local → abortar con mensaje de error.
  * `manager` no válido / no soportado → abortar.
  * Sin clave API cuando el servidor la requiere → abortar.

* **Salida esperada**:

  * Mensaje en consola indicando si fue "cache hit" o "cache miss + generación".
  * URL de descarga del ZIP.
  * Progreso de descarga y extracción.
  * Código de salida 0 en caso de éxito, ≠0 en errores.

### 4.2 Servidor (`dep_cache_proxy_server`)

* **Objetivo**: Recibir solicitudes de cache, decidir si existe cache o hay que generarla, y servir el ZIP resultante.

* **Responsabilidades**:

  1. Parsear argumentos de arranque: `port`, `--cache_dir`, `--is_public`, `--api-keys`.
  2. Inicializar repositorios (p. ej. `FileSystemCacheRepository(cache_dir)`).
  3. Configurar router HTTP (FastAPI/Flask) con endpoints:

     * `POST /v1/cache` → recibe JSON/multipart y devuelve JSON con URL de descarga.
     * `GET /download/<hash>.zip` → entrega el ZIP.
  4. Validar API key en cada request si `--is_public == False`.
  5. Validador de `manager`.
  6. Orquestar los casos de uso de cache (hit/miss).
  7. Registrar logs y métricas (opcionalmente).

* **Dependencias externas**:

  * `fastapi` + `uvicorn` (o `Flask` + `gunicorn`).
  * `hashlib`, `tempfile`, `subprocess`, `zipfile`, `os`, `shutil`.

* **Módulos propuestos**:

  * `server/main.py`
  * `server/controllers/cache_controller.py`
  * `server/application/usecases/handle_cache_request.py`
  * `server/domain/hash_calculator.py`
  * `server/infrastructure/file_system_cache_repository.py`
  * `server/infrastructure/dependency_installer.py`
  * `server/infrastructure/zip_util.py`
  * `server/infrastructure/api_key_validator.py`

#### 4.2.1 Parámetros CLI y Validaciones

* **Posicional**:

  1. `<port>` (entero, p. ej. `8080`).
* **Flags**:

  * `--cache_dir=<CACHE_DIR>` (ruta absoluta o relativa, p. ej. `./cache`).
  * `--is_public` (booleano, default `False`).
  * `--api-keys=<KEY1>,<KEY2>,...` (string separada por comas, opcional si `--is_public` es `True`).
* **Errores posibles**:

  * `port` no válido (no integer dentro de rango 1–65535).
  * `cache_dir` no accesible o no escribible.
  * `--api-keys` ausente cuando `--is_public` es `False`.

---

## 5. Modelo de Dominio y Hashing

### 5.1 Entidad: `DependencySet`

* Atributos:

  * `manager: str`
  * `file_contents: Dict[str, bytes]` → clave: nombre de archivo (ej. `"package.json"`), valor: contenido en bytes.
  * `versions: Dict[str, str]` → opcional, p. ej. `{ "node": "14.17.0", "npm": "6.14.13" }`.
  * `hash: str` (SHA256 hexa resultante).

* **Método principal**:

  * `calculate_hash() -> str`:

    1. Ordenar nombres de archivo de forma determinista (alfabéticamente).
    2. Concatenar: `manager + "\n"` → para diferenciar `npm` vs `composer`.
    3. Para cada nombre de archivo en orden:

       * Tomar su contenido (bytes) y hacer streaming a `hashlib.sha256`.
    4. Para cada par (key, value) dentro de `versions` (ordenar por clave):

       * Concatenar `"key=value\n"`.
       * Alimentar bytes a `hashlib.sha256`.
    5. Devolver hex digest de 64 caracteres.

* **Justificación**:

  * Al incluir `manager` en hash, evitamos colisiones entre diferentes ecosistemas.
  * Incluir `versions` opcionales asegura que cambiar de versión cause nuevo hash y, por ende, regeneración de dependencias.

### 5.2 Entidad: `CacheObject`

* Atributos:

  * `hash: str`
  * `manager: str`
  * `cache_path: Path` → carpeta raíz en disco donde reside la cache:

    ```
    cache_dir/objects/<h0h1>/<h2h3>/<hash>.<manager>/
    ```
  * `meta_file: Path` → `cache_path / "<hash>.<manager>.hash"`.
  * `zip_file: Path` → `cache_path / "<hash>.zip"`.

* **Métodos**:

  * `exists() -> bool`: verifica si `cache_path` existe y contiene `meta_file` y `zip_file`.
  * `write_metadata(file_list: List[str])`: genera el archivo `<hash>.<manager>.hash` con líneas:

    ```
    <relative_path>;<filesize>;<checksum (opcional)>
    ```
  * `compress_all()`: genera el ZIP de la carpeta interna completa (`node_modules` o `vendor`).

### 5.3 Entidad/Agregado: `CacheRepository` (Interfaz)

* **Métodos** (contrato):

  1. `get(cache_key: str) -> Optional[CacheObject]`: retorna `CacheObject` si existe, o `None` si no.
  2. `save(cache_object: CacheObject) -> None`: guarda el objeto en disco (crea carpetas, escribe metadatos).
  3. `list_all() -> List[CacheObject]` (opcional, para limpieza/monitorización).
  4. `delete(cache_key: str) -> None` (opcional, para invalidación).

* **Implementación principal**:

  * `FileSystemCacheRepository(cache_dir: Path)`:

    * `get(...)`: comprueba existencia de `cache_dir / "objects" / subdirs / "<hash>.<manager>"`.
    * `save(...)`: crea las carpetas necesarias y mueve archivos.
    * `delete(...)`: borra carpeta entera asociada.

### 5.4 Dominio: `HashCalculator`

* Única responsabilidad: tomar `DependencySet` y devolver `hash: str`.

---

## 6. Estructura de Directorios en Cache

Se utiliza una **estructura de directorios basada en los dos primeros bytes del hash** para evitar tener demasiados ficheros en un solo directorio. Ejemplo de árbol:

```
<cache_dir>/
└── objects/
    ├── 00/00/   # hashes que empiezan con "0000..."
    ├── 00/01/
    ├── ...
    ├── ab/cd/   # hashes que empiezan con "abcd..."
    │   └── <hash>.npm/
    │       ├── node_modules/...
    │       ├── <hash>.npm.hash
    │       └── <hash>.zip
    ├── ef/01/
    └── ... (256 x 256 posibles combinaciones: "00" a "ff" / "00" a "ff")
```

* **Convención de nombres**

  * Directorio de nivel 1: los dos primeros caracteres hexadecimales del hash (`h[0:2]`).
  * Directorio de nivel 2: los siguientes dos caracteres (`h[2:4]`).
  * Nombre de carpeta final: `"<hash>.<manager>"`.

* **Contenido de carpeta `<hash>.<manager>`**:

  * Subcarpeta `node_modules/` o `vendor/` (dependiendo de `manager`).
  * Archivo de metadatos: `<hash>.<manager>.hash`.
  * Archivo comprimido: `<hash>.zip`.

* **Archivo de metadatos** (`<hash>.<manager>.hash`)

  * Formato de cada línea (separadas por `\n`):

    ```
    <ruta_relativa>;<tamaño_bytes>;<sha256_hex>
    ```

    * Ejemplo:

      ```
      node_modules/packageA/index.js;12034;ff3a2b...
      node_modules/packageB/lib/util.js;4531;9ac8d1...
      ```

Con esta información, el servidor puede reconstruir el ZIP sin necesidad de leer todos los ficheros si ya están almacenados individuales, o validar la integridad de la cache.

---

## 7. Flujo de Trabajo Completo

A continuación se describe cada paso del flujo general, desde que el usuario invoca el cliente hasta que se obtienen las dependencias locales:

1. **Inicio Cliente**

   ```
   $ dep_cache_proxy_client https://server:8080/api npm --apikey=KEY123 --files=package.json,package.lock --node-version=14.20.0 --npm-version=6.14.13
   ```

   * El cliente parsea argumentos y verifica que los ficheros `package.json` y `package.lock` existen.
   * Lee ambos archivos en modo binario (bytes).
   * Instancia un objeto `DependencySet(manager="npm")` y lo alimenta con esos contenidos y versiones opcionales.
   * Llama a `HashCalculator.calculate_hash(dependency_set)` → obtiene `hex_hash` (por ejemplo: `ab12cd34ef56...`).
   * Construye un JSON de petición:

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
   * Envía `POST https://server:8080/api/v1/cache` con cabecera `Authorization: Bearer KEY123` y el JSON anterior.

2. **Recepción en Servidor**

   * FastAPI (o Flask) mapea `POST /v1/cache` al método `CacheController.handle_request()`.
   * Extrae JWT de cabecera o `Authorization: Bearer`.
   * Si `is_public == False`, invoca `ValidateApiKey.check(api_key)` (compara con la lista interna).

     * Si falla, responde `401 Unauthorized`.
   * Extrae campos `manager`, `hash`, `files`, `versions` del JSON.
   * Valida que `manager` está soportado (p. ej., `if manager not in ["npm","composer"] → 400`).
   * Llama a `HandleCacheRequest.execute(request_dto)`, donde `request_dto.manager == "npm"`, `request_dto.hash == "ab12..."`, etc.

3. **Caso de Uso: `HandleCacheRequest`**

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
               # Cache Miss → Generar dependencias
               temp_dir = create_temp_dir(prefix=cache_key)
               # 1) Decodificar archivos base64 y escribir en temp_dir
               for name, b64_content in request.files.items():
                   write_file(temp_dir / name, base64_decode(b64_content))
               # 2) Instalar dependencias
               installer = self.installer_factory.get_installer(request.manager, request.versions)
               installer.install(temp_dir)

               # 3) Copiar carpeta generada (node_modules/vendor) a cache_dir
               final_cache_dir = self.cache_repo.compute_path(cache_key)
               copy_tree(temp_dir / installer.output_folder_name, final_cache_dir / installer.output_folder_name)

               # 4) Generar metadatos
               file_list = list_all_files(final_cache_dir / installer.output_folder_name)
               checksum_list = compute_checksums(final_cache_dir / installer.output_folder_name)
               self.zip_util.write_metadata(final_cache_dir, cache_key, request.manager, file_list, checksum_list)

               # 5) Comprimir cache
               zip_path = final_cache_dir / f"{request.hash}.zip"
               self.zip_util.compress_folder(final_cache_dir / installer.output_folder_name, zip_path)

               # 6) Registrar en repo (persistir metadatos)
               cache_obj = CacheObject(hash=request.hash, manager=request.manager, cache_path=final_cache_dir)
               self.cache_repo.save(cache_obj)

               download_url = build_download_url(request.hash, request.manager)
               return CacheResponseDTO(download_url=download_url, cache_hit=False)
   ```

   * Al finalizar, `HandleCacheRequest.execute()` retorna un `CacheResponseDTO` con el campo `download_url` y un booleano `cache_hit`.

4. **Respuesta al Cliente**

   * `CacheController` envuelve el resultado en JSON, p. ej.:

     ```jsonc
     {
       "download_url": "http://server:8080/download/ab12cd34ef56... .zip",
       "cache_hit": false
     }
     ```
   * El cliente recibe la respuesta:

     * Si `cache_hit == true`, muestra “Cache hit: descargando...”
     * Si `cache_hit == false`, muestra “Cache miss: generando dependencias. Descargando cuando esté listo...”

5. **Descarga del ZIP**

   * El cliente realiza `GET http://server:8080/download/ab12cd34ef56... .zip` y guarda en disco local, p. ej. `./dep_cache/ab12cd34ef56... .zip`.
   * Descomprime el ZIP en carpeta local predeterminada de dependencias:

     * Si `manager == "npm"`, extrae contenido comprimido en `./node_modules/`.
     * Si `manager == "composer"`, extrae en `./vendor/`.
   * El cliente puede borrar el ZIP temporal o guardarlo en un cache local.

6. **Entrega Final**

   * El cliente termina con la carpeta de dependencias actualizada en disco:

     ```
     proyecto/
     ├── package.json
     ├── package.lock
     └── node_modules/  # Proveniente del ZIP descargado
     ```
   * Si se repite el mismo flujo con idéntica combinación de `package.json`+`package.lock` (sin cambios de versión), será un **cache hit** puro y instantáneo, evitando la regeneración del servidor.

7. **Limpieza (opcional)**

   * El servidor podría periódicamente (cronjob o scheduler) invocar un caso de uso `PurgeOldCaches` para eliminar hashes no referenciados o expirados después de N días.

---

## 8. Detalles de Implementación y Pseudocódigo

A continuación se muestra pseudocódigo orientado a Python, respetando convenciones DDD/SOLID. El objetivo es que otras IA (e.g., Claude) puedan leerlo e implementarlo directamente.

### 8.1 Pseudocódigo Cliente

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
# Dominio / Util: HashCalculator (cliente)
# ----------------------------------------
class HashCalculator:
    @staticmethod
    def calculate_hash(manager: str, file_paths: list[str], versions: dict) -> str:
        """
        Calcula SHA256 en función de:
            1. manager (e.g. "npm")
            2. contenido de cada fichero (en orden alfabético)
            3. versiones opcionales (ordenadas por clave)
        """
        sha = hashlib.sha256()
        sha.update(manager.encode("utf-8"))
        sha.update(b"\n")
        # Leer y procesar cada fichero
        for file_name in sorted(file_paths):
            with open(file_name, "rb") as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    sha.update(chunk)
        # Procesar versiones opcionales
        for k in sorted(versions.keys()):
            v = versions[k]
            line = f"{k}={v}\n".encode("utf-8")
            sha.update(line)
        return sha.hexdigest()

# ----------------------------------------
# Cliente: Main CLI
# ----------------------------------------
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
    # Validar manager soportado localmente (sin o con verificación completa en servidor)
    supported = ["npm", "composer"]
    if manager not in supported:
        print(f"ERROR: Gestor '{manager}' no soportado. Opciones: {', '.join(supported)}")
        sys.exit(1)

    # Parsear lista de ficheros
    file_list = [f.strip() for f in args.files.split(",")]
    if len(file_list) < 2:
        print("ERROR: Debe especificar al menos dos ficheros: definición + lockfile")
        sys.exit(1)
    # Verificar existencias
    for fp in file_list:
        if not os.path.isfile(fp):
            print(f"ERROR: Archivo no encontrado: {fp}")
            sys.exit(1)

    # Construir diccionario de versiones
    versions = {}
    if manager == "npm":
        if args.node_version:
            versions["node"] = args.node_version
        if args.npm_version:
            versions["npm"] = args.npm_version
    elif manager == "composer":
        if args.php_version:
            versions["php"] = args.php_version

    # Calcular hash local
    hash_hex = HashCalculator.calculate_hash(manager, file_list, versions)
    print(f"[INFO] Hash calculado: {hash_hex}")

    # Leer y codificar ficheros en base64
    files_b64 = {}
    for fp in file_list:
        with open(fp, "rb") as f:
            bcontent = f.read()
            files_b64[os.path.basename(fp)] = base64.b64encode(bcontent).decode("utf-8")

    # Construir payload JSON
    payload = {
        "manager": manager,
        "hash": hash_hex,
        "files": files_b64,
        "versions": versions
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Hacer POST a /v1/cache
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
        # Crear carpeta temporal para guardar ZIP
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
        # Default: extraer en carpeta "deps"
        target_dir = os.path.join(os.getcwd(), "deps")

    # Eliminar carpeta existente (si existe) para evitar conflictos
    if os.path.isdir(target_dir):
        print(f"[INFO] Eliminando carpeta existente: {target_dir}")
        import shutil
        shutil.rmtree(target_dir)

    os.makedirs(target_dir, exist_ok=True)
    with zipfile.ZipFile(tmp_zip.name, "r") as zip_ref:
        zip_ref.extractall(target_dir)
    print(f"[INFO] Dependencias extraídas en: {target_dir}")

    # Opcional: eliminar ZIP local
    os.remove(tmp_zip.name)
    print("[INFO] Proceso completado con éxito.")
    sys.exit(0)

if __name__ == "__main__":
    main()
```

#### Comentarios de Pseudocódigo Cliente

1. **Estructura modular**:

   * `HashCalculator` está desacoplado del resto. Si se cambia algoritmo (por ejemplo, a SHA1), solo se modifica esa clase.
   * El pipeline está claramente definido (lectura, hash, envío, descarga).
   * Uso de librería `requests` para HTTP.

2. **Validaciones**:

   * Comprobación de existencia de ficheros.
   * Validación mínima de `manager`.
   * Control de códigos HTTP (200, 401, otros).

3. **Manejo de excepciones**:

   * Captura de errores de red (`RequestException`).
   * Salida con código de error en consola para trazabilidad.

4. **Extracción de ZIP**:

   * Elimina carpeta previa para evitar mezclas de versiones.
   * Extrae todo el contenido en la carpeta indicada por `manager`.

---

### 8.2 Pseudocódigo Servidor

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

# Dependencias externas:
# pip install fastapi uvicorn python-multipart aiofiles

from fastapi import FastAPI, HTTPException, UploadFile, File, Header, Request
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

# ---------------------------------------
# DOMAIN: Entidades y Value Objects
# ---------------------------------------

class DependencySet:
    """
    Entidad que representa la combinación única de:
    - manager (npm, composer)
    - contenidos de ficheros (definición + lockfile)
    - versiones opcionales (node, npm, php)
    """
    def __init__(self, manager: str, file_contents: Dict[str, bytes], versions: Dict[str, str]):
        self.manager = manager
        self.file_contents = file_contents  # {"package.json": b"...", "package.lock": b"..."}
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
    Representa el objeto cacheado en disco, con rutas a:
    - output_folder: carpeta donde se guardan node_modules o vendor
    - meta_file: archivo .hash
    - zip_file: archivo .zip
    """
    def __init__(self, base_dir: Path, hash_hex: str, manager: str):
        self.hash = hash_hex
        self.manager = manager
        # Directorio de nivel 1 = dos primeros caracteres, nivel 2 = siguientes dos
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
# DOMAIN: Interfaces / Repositorios
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
        # Asegurarse que existe 'objects' bajo base_dir
        (self.base_dir / "objects").mkdir(parents=True, exist_ok=True)

    def compute_path(self, cache_key: str) -> Path:
        # cache_key = "<hash>.<manager>"
        hash_hex, manager = cache_key.split(".")
        h0_2 = hash_hex[0:2]
        h2_4 = hash_hex[2:4]
        return self.base_dir / "objects" / h0_2 / h2_4 / cache_key

    def get(self, cache_key: str) -> Optional[CacheObject]:
        target = self.compute_path(cache_key)
        # Validar existencia de meta_file y zip_file
        hash_hex, manager = cache_key.split(".")
        obj = CacheObject(self.base_dir, hash_hex, manager)
        if obj.exists():
            return obj
        return None

    def save(self, cache_obj: CacheObject) -> None:
        # Asumir que todas las carpetas y ficheros ya existen en disco
        # Solo se asegura la ruta principal
        cache_obj.cache_root.mkdir(parents=True, exist_ok=True)
        # (Los archivos ya han sido copiados por el caso de uso)
        # Metadata y ZIP ya creados externamente, por lo que no hay más acción
        return

# ---------------------------------------
# DOMAIN: Instaladores de Dependencias
# ---------------------------------------
class DependencyInstaller:
    """
    Interfaz común para generar dependencias:
    - npm: ejecuta 'npm ci'
    - composer: ejecuta 'composer install'
    """
    def __init__(self, versions: Dict[str, str]):
        self.versions = versions

    @property
    def output_folder_name(self) -> str:
        raise NotImplementedError

    def install(self, work_dir: Path) -> None:
        """
        Debe clonar los ficheros de definición en work_dir, luego ejecutar comando de instalación
        y generar folder de salida en work_dir / output_folder_name
        """
        raise NotImplementedError

class NpmInstaller(DependencyInstaller):
    @property
    def output_folder_name(self) -> str:
        return "node_modules"

    def install(self, work_dir: Path) -> None:
        # Opcional: Instalar versión específica de Node y NPM (usa nvm o similares)
        node_version = self.versions.get("node")
        npm_version = self.versions.get("npm")
        # (En este pseudocódigo, se asume que la versión adecuada ya está instalada en el host)
        # Ejecutar comando npm ci dentro de work_dir
        cmd = ["npm", "ci", "--ignore-scripts", "--cache", str(work_dir / ".npm_cache")]
        # Ejemplo: si se quiere usar npx para ejecutar una versión específica
        # if node_version: cmd = ["npx", f"node@{node_version}", ...]
        process = subprocess.run(cmd, cwd=str(work_dir), capture_output=True)
        if process.returncode != 0:
            # Arrojar excepción para propagar error
            raise RuntimeError(f"npm ci falló: {process.stderr.decode()}")

class ComposerInstaller(DependencyInstaller):
    @property
    def output_folder_name(self) -> str:
        return "vendor"

    def install(self, work_dir: Path) -> None:
        php_version = self.versions.get("php")
        # Ejecutar composer install
        cmd = ["composer", "install", "--no-dev", "--prefer-dist", "--no-interaction", "--no-scripts"]
        process = subprocess.run(cmd, cwd=str(work_dir), capture_output=True)
        if process.returncode != 0:
            raise RuntimeError(f"composer install falló: {process.stderr.decode()}")

class InstallerFactory:
    def get_installer(self, manager: str, versions: Dict[str, str]) -> DependencyInstaller:
        if manager == "npm":
            return NpmInstaller(versions)
        elif manager == "composer":
            return ComposerInstaller(versions)
        else:
            raise ValueError(f"Installer no implementado para manager '{manager}'")

# ---------------------------------------
# DOMAIN: Utilidades de Compresión / Metadata
# ---------------------------------------
class ZipUtil:
    @staticmethod
    def list_all_files(root: Path) -> List[Path]:
        """
        Retorna lista de Paths relativos de todos los archivos dentro de 'root'
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
        Para cada archivo en root, calcula sha256 y retorna dict {ruta_relativa: checksum}
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
        Escribe el archivo <hash>.<manager>.hash dentro de cache_dir, 
        con líneas formato: ruta_relativa;tamaño;checksum
        """
        meta_path = cache_dir / f"{hash_hex}.{manager}.hash"
        with open(meta_path, "w", encoding="utf-8") as meta_f:
            for rel in sorted(file_list):
                full = cache_dir / manager / rel if manager == "npm" else cache_dir / manager / rel
                size = (cache_dir / rel).stat().st_size if (cache_dir / rel).exists() else 0
                chksum = checksums.get(str(rel), "")
                # Formar línea
                line = f"{rel};{size};{chksum}\n"
                meta_f.write(line)

    @staticmethod
    def compress_folder(src_folder: Path, zip_path: Path) -> None:
        """
        Comprime el contenido de src_folder en zip_path (sin incluir carpeta raíz).
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
# DOMAIN: Validador de API Key
# ---------------------------------------
class ApiKeyValidator:
    def __init__(self, valid_keys: List[str]):
        # Guardar keys en memoria; se pueden cifrar/hashes si se requiere
        self.keys = set(valid_keys)

    def validate(self, api_key: str) -> bool:
        return api_key in self.keys

# ---------------------------------------
# APPLICATION: Casos de Uso / UseCases
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
        # Cache Miss → generar dependencias
        # 1) Crear carpeta temporal
        temp_dir = Path(tempfile.mkdtemp(prefix=cache_key))
        # 2) Decodificar archivos base64 y escribir en temp_dir
        for fname, b64 in request_dto.files.items():
            data = base64.b64decode(b64)
            fpath = temp_dir / fname
            with open(fpath, "wb") as wf:
                wf.write(data)
        # 3) Instalar dependencias
        installer = self.installer_factory.get_installer(request_dto.manager, request_dto.versions)
        # Copiar lockfile a padre del folder de instalación (muchos gestores esperan fichero en cwd)
        # Asumimos que workdir: temp_dir
        try:
            installer.install(temp_dir)
        except Exception as e:
            # Limpieza temp y lanzar error 500
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise e

        # 4) Copiar carpeta generada a cache_dir
        cache_path = self.cache_repo.compute_path(cache_key)
        # Carpeta destino: <cache_dir>/objects/..../<hash>.<manager>/node_modules (o vendor)
        final_output = cache_path / installer.output_folder_name
        final_output.parent.mkdir(parents=True, exist_ok=True)
        # Copiar recursivamente temp_dir/node_modules → final_output
        shutil.copytree(temp_dir / installer.output_folder_name, final_output)

        # 5) Generar metadata
        file_list = self.zip_util.list_all_files(final_output)
        checksums = self.zip_util.compute_checksums(final_output)
        self.zip_util.write_metadata(cache_path, request_dto.hash, request_dto.manager, file_list, checksums)

        # 6) Comprimir cache
        zip_path = cache_path / f"{request_dto.hash}.zip"
        self.zip_util.compress_folder(final_output, zip_path)

        # 7) Persistir cache_obj en repo
        cache_obj = CacheObject(cache_path.parent.parent.parent, request_dto.hash, request_dto.manager)
        self.cache_repo.save(cache_obj)

        # 8) Limpieza de carpeta temporal
        shutil.rmtree(temp_dir, ignore_errors=True)

        download_url = f"{base_download_url}/download/{request_dto.hash}.zip"
        return CacheResponseDTO(download_url=download_url, cache_hit=False)

# ---------------------------------------
# INTERFACES / ENTRYPOINT: Servidor FastAPI
# ---------------------------------------
def create_app(cache_dir: Path, is_public: bool, api_keys: List[str], base_download_url: str) -> FastAPI:
    app = FastAPI()
    cache_repo = FileSystemCacheRepository(cache_dir)
    installer_factory = InstallerFactory()
    zip_util = ZipUtil()
    validator = ApiKeyValidator(api_keys) if not is_public else None
    handler = HandleCacheRequest(cache_repo, installer_factory, zip_util)

    # Ruta para generar o recuperar cache
    @app.post("/v1/cache", response_model=CacheResponseDTO)
    async def cache_endpoint(request: Request):
        # API Key
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
        supported = ["npm", "composer"]
        if dto.manager not in supported:
            raise HTTPException(status_code=400, detail=f"Manager no soportado: {dto.manager}")

        # Llamar caso de uso
        try:
            response_dto = handler.execute(dto, base_download_url)
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=f"Error al generar dependencias: {e}")
        return JSONResponse(status_code=200, content=response_dto.dict())

    # Ruta para descargar ZIP
    @app.get("/download/{hash}.zip")
    async def download_endpoint(hash: str):
        # Notar que no se valida API key aquí: el usuario ya la tuvo que pasar al crear
        # Podría implementarse control adicional (TTL, tokens únicos, etc.)
        # Construir ruta en disco
        # Para deducir manager, podríamos examinar subdirectorios: simplificación: 
        # Intentar buscar zip en ambos managers
        for manager in ["npm", "composer"]:
            # Reconstruir ruta de forma análoga
            h0_2 = hash[0:2]
            h2_4 = hash[2:4]
            cache_path = cache_dir / "objects" / h0_2 / h2_4
            folder = cache_path / f"{hash}.{manager}"
            zip_path = folder / f"{hash}.zip"
            if zip_path.is_file():
                return FileResponse(zip_path, filename=f"{hash}.zip", media_type="application/zip")
        raise HTTPException(status_code=404, detail="ZIP no encontrado")

    return app

def parse_args():
    parser = argparse.ArgumentParser(description="Servidor DepCacheProxy")
    parser.add_argument("port", type=int, help="Puerto HTTP donde escuchará (ej. 8080)")
    parser.add_argument("--cache_dir", type=str, required=True, help="Directorio base de cache")
    parser.add_argument("--is_public", action="store_true", default=False, help="Si se especifica, servidor público (sin API key)")
    parser.add_argument("--api-keys", type=str, required=False, help="Lista separada por comas de API keys válidas")
    return parser.parse_args()

def main():
    args = parse_args()
    port = args.port
    cache_dir = Path(args.cache_dir)
    is_public = args.is_public
    api_keys = []
    if not is_public:
        if not args.api_keys:
            print("ERROR: Debe proporcionar --api-keys cuando no es público.")
            sys.exit(1)
        api_keys = [k.strip() for k in args.api_keys.split(",") if k.strip()]
    # Verificar cache_dir es escribible
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"ERROR: No se puede crear/acceder a cache_dir '{cache_dir}': {e}")
        sys.exit(1)

    # Construir base_download_url (sin trailing slash)
    base_download_url = f"http://localhost:{port}"
    # Crear app FastAPI
    app = create_app(cache_dir, is_public, api_keys, base_download_url)
    # Ejecutar con Uvicorn
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
```

#### Comentarios de Pseudocódigo Servidor

1. **Estructura DDD**

   * División en `domain/` (entidades: `DependencySet`, `CacheObject`; repositorio: `ICacheRepository`), `application/` (`HandleCacheRequest`), `infrastructure/` (`FileSystemCacheRepository`, `NpmInstaller`, `ComposerInstaller`, `ZipUtil`, `ApiKeyValidator`) y `interfaces/` (`create_app`, endpoints).

2. **Validación de API Key**

   * Se hace al inicio de `cache_endpoint`. Si falla, se lanza `HTTPException(401)`.

3. **Instalación de dependencias**

   * `InstallerFactory` elige el `DependencyInstaller` adecuado basándose en `manager`.
   * Cada `DependencyInstaller` implementa `install(work_dir)` y lanza excepción en caso de fallo.

4. **Persistencia en FileSystem**

   * `FileSystemCacheRepository` guarda la estructura tal como la crea el caso de uso.
   * El método `get(cache_key)` construye un `CacheObject` temporal y llama `exists()`.

5. **Generación de Metadatos y ZIP**

   * `ZipUtil.list_all_files()` obtiene lista recursiva de archivos en la carpeta de dependencias.
   * `ZipUtil.compute_checksums()` calcula checksum SHA256 de cada archivo.
   * `ZipUtil.write_metadata()` escribe el fichero `.hash` con `ruta;tamaño;checksum`.
   * `ZipUtil.compress_folder()` genera el ZIP que luego será servido por `FileResponse`.

6. **Rutas HTTP**

   * `POST /v1/cache`: recibe JSON y retorna JSON con URL y estado de cache (hit/miss).
   * `GET /download/{hash}.zip`: busca en ambos gestores (`npm`, `composer`) el ZIP y lo retorna.

7. **Errores y Excepciones**

   * Si `manager` no soportado → `400 Bad Request`.
   * Si error al instalar dependencias → `500 Internal Server Error`.
   * Si ZIP no existe al intentar descargar → `404 Not Found`.

8. **Concurrencia**

   * FastAPI + Uvicorn permiten concurrencia asíncrona.
   * Múltiples peticiones `POST /v1/cache` para el mismo hash concurrentemente podrían causar “race condition” al copiar carpetas.

     * Se recomienda implementar un mecanismo de **locking** (p. ej. fichero `.lock` o uso de `asyncio.Lock`) por `cache_key` para asegurar que solo un proceso genera el mismo hash a la vez; los demás esperan.

---

## 9. API HTTP y Esquema de Rutas

### 9.1 Rutas Principales

| Método | Ruta                   | Descripción                                                 | Request Body                 | Respuestas                                                                                                                          |
| ------ | ---------------------- | ----------------------------------------------------------- | ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| POST   | `/v1/cache`            | Solicita cache de dependencias: hit/miss y URL de descarga. | JSON (ver `CacheRequestDTO`) | `200 OK` → `{ download_url: str, cache_hit: bool }` <br> `400 Bad Request` <br> `401 Unauthorized` <br> `500 Internal Server Error` |
| GET    | `/download/{hash}.zip` | Descarga el ZIP generado para el hash proporcionado.        | Ninguno                      | `200 OK` → ZIP <br> `404 Not Found`                                                                                                 |

### 9.2 Esquema de Request y Response

#### 9.2.1 `CacheRequestDTO`

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

  * `manager` (string, obligatorio): identificador de gestor de dependencias (`npm`, `composer`, etc.).
  * `hash` (string, obligatorio): hash SHA256 calculado por el cliente.
  * `files` (map\<string, string>, obligatorio): diccionario de nombre de fichero → contenido codificado en Base64.
  * `versions` (map\<string, string>, opcional): claves/valores de versiones. Ej. `{ "node": "14.20.0", "npm": "6.14.13" }` para NPM; `{ "php": "8.1.0" }` para Composer.

#### 9.2.2 `CacheResponseDTO`

```jsonc
{
  "download_url": "http://server:8080/download/ab12cd34ef56... .zip",
  "cache_hit": true
}
```

* **Campos**:

  * `download_url` (string, obligatorio): URL absoluta para descargar el ZIP.
  * `cache_hit` (boolean, obligatorio): indica si fue “hit” (cache existente) o “miss” (se generó).

---

## 10. Escenarios de Uso y Casos de Prueba

A continuación se describen distintos escenarios de uso, con inputs esperados y validaciones.

### 10.1 Escenario 1: Cache hit en NPM (Servidor público)

1. **Cliente invoca**:

   ```bash
   dep_cache_proxy_client http://localhost:8080 npm --files=package.json,package.lock
   ```
2. **Cliente**:

   * Calcula hash (p. ej. `ff0033aa...`).
   * Envía `POST /v1/cache` con payload (sin Authorization, porque servidor es público).
3. **Servidor**:

   * `is_public = True` → No valida key.
   * `manager="npm"` soportado.
   * `cache_key="ff0033aa....npm"`.
   * `cache_repo.get("ff0033aa....npm")` → devuelve `CacheObject` porque existe.
   * Responde con `200 OK` y JSON:

     ```jsonc
     { "download_url": "http://localhost:8080/download/ff0033aa... .zip", "cache_hit": true }
     ```
4. **Cliente**:

   * Descarga ZIP y lo extrae en `./node_modules/`.
   * Termina con éxito.

**Pruebas**:

* Verificar que `download_url` apunte a un ZIP que realmente existe y es un ZIP válido.
* Confirmar que carpeta `node_modules/` coincide con versión esperada.

---

### 10.2 Escenario 2: Cache miss en Composer (Servidor con API key)

1. **Servidor** arrancado con:

   ```bash
   dep_cache_proxy_server 8080 --cache_dir=./cache --api-keys=KEY1,KEY2
   ```
2. **Cliente invoca**:

   ```bash
   dep_cache_proxy_client http://localhost:8080 composer --apikey=KEY1 --files=composer.json,composer.lock --php-version=8.1.0
   ```
3. **Cliente**:

   * Calcula hash (p. ej. `aa11bb22...`).
   * Envía `POST /v1/cache` con cabecera `Authorization: Bearer KEY1` y payload.
4. **Servidor**:

   * Valida API key `KEY1` → OK.
   * `manager="composer"`, hash no existe en cache.
   * Crea `temp_dir="tmp/aa11bb22...".`
   * Escribe `composer.json` + `composer.lock` en temp.
   * Ejecuta `composer install --no-dev --prefer-dist` en temp.

     * Resultado: `temp/vendor/` con dependencias.
   * Copia `temp/vendor/` a `cache/objects/aa/11/aa11bb22... .composer/vendor/`.
   * Calcula lista de archivos y checksums.
   * Escribe `cache/objects/aa/11/aa11bb22... .composer/aa11bb22... .composer.hash`.
   * Comprime a `cache/objects/aa/11/aa11bb22... .composer/aa11bb22... .zip`.
   * Limpia `temp_dir`.
   * Retorna `200 OK` con `{"download_url":"http://localhost:8080/download/aa11bb22... .zip", "cache_hit": false}`.
5. **Cliente**:

   * Descarga ZIP y descomprime en `./vendor/`.
   * Termina con éxito.

**Pruebas**:

* Verificar estructura en `cache/objects/aa/11/aa11bb22... .composer/`.
* Confirmar que `composer install` se ejecuta correctamente en contenedor/servidor.
* Confirmar que `cache_hit` pasa a `true` en siguiente invocación con mismos ficheros.

---

### 10.3 Escenario 3: Petición con API key inválida

1. **Cliente invoca**:

   ```bash
   dep_cache_proxy_client http://localhost:8080 npm --apikey=INVALID --files=package.json,package.lock
   ```
2. **Servidor**:

   * Recibe `Authorization: Bearer INVALID`.
   * `validator.validate("INVALID")` → `False`.
   * Retorna `401 Unauthorized` con JSON:

     ```jsonc
     { "detail": "API Key inválida" }
     ```
3. **Cliente**:

   * Detecta `resp.status_code == 401` y sale con código de error tras indicar mensaje en consola.

---

### 10.4 Escenario 4: Manager no soportado

1. **Cliente invoca**:

   ```bash
   dep_cache_proxy_client http://localhost:8080 pip --files=requirements.txt,requirements.lock
   ```
2. **Cliente**:

   * `manager="pip"` no está en `supported=["npm","composer"]`.
   * Imprime: `ERROR: Gestor 'pip' no soportado. Opciones: npm, composer` y sale.

*Opcionalmente*, si movemos la validación al servidor:

* Servidor recibiría `POST` y devolvería `400 Bad Request` con detalle “Manager no soportado: pip”.

---

## 11. Notas de Seguridad, Escalabilidad y Errores Comunes

### 11.1 Seguridad

1. **Validación de Inputs**

   * El campo `manager` debe compararse contra una lista blanca (whitelist) de gestores permitidos.
   * Los nombres de archivos (`package.json`, etc.) se asumen seguros; de todos modos, no se debe permitir rutas relativas con `../`.
   * **No ejecutar scripts potencialmente maliciosos**:

     * En NPM, se usa `--ignore-scripts` para evitar que se ejecuten `preinstall`/`postinstall`.
     * En Composer, usar `--no-scripts` para evitar hooks.

2. **Inyección de Comandos**

   * Cuando se genera el comando `npm ci` o `composer install`, no concatenar strings de forma insegura.
   * Usar lista de argumentos en `subprocess.run([...])`.

3. **API Key**

   * Guardar las keys en memoria (o en un almacén seguro).
   * Comparar de forma constante para evitar “timing attacks”.
   * No incluir `--api-keys` en logs.

4. **Entrega de ZIP**

   * Servir archivos solo desde `cache/objects`. Evitar rutas arbitrarias.
   * Evitar que el cliente descargue cualquier otro archivo en el servidor (no exponer rutas del sistema de archivos).

5. **HTTPS**

   * El servidor **no** soporta HTTPS nativamente. Debe usarse un proxy inverso (Nginx, Traefik) que ofrezca TLS/SSL.

### 11.2 Escalabilidad y Concurrencia

1. **Servir múltiples peticiones concurrentes**

   * FastAPI + Uvicorn (configurado con múltiples workers) permite concurrencia.
   * Evitar condiciones de carrera:

     * **Lock por hash**: Si dos clientes piden simultáneamente el mismo `hash`, ambos entran en el bloque “cache miss”. El primero genera la cache, el segundo trata de generar a la vez → posible corrupción.
     * Solución:

       * Usar un lock a nivel de sistema de archivos. Ejemplo (Linux): `flock` en un archivo `<cache_path>.lock`.
       * O usar una tabla simple en memoria: `locks = {}` con `asyncio.Lock` para ese hash.

2. **Tamaño de Cache**

   * Configurar políticas de retención:

     * Máximo de N entradas.
     * Expiración basado en tiempo (ej. borrar cachés > 30 días sin uso).
     * Eliminar manual (`delete(cache_key)`).

3. **Uso de S3 u Otros**

   * En lugar de `FileSystemCacheRepository`, podría construirse `S3CacheRepository`, donde los objetos (carpetas y ZIP) se almacenan en buckets S3.
   * Mantener metadata localmente (RDS) o en DynamoDB, apuntando a URLs de S3.

### 11.3 Errores Comunes y Cómo Manejarlos

1. **Hash no coincide entre cliente y servidor**

   * Asegurarse de que el algoritmo de hash sea idéntico.
   * Validar que se está ordenando adecuadamente la lista de archivos y las claves de `versions`.

2. **Falla en `npm ci` o `composer install`**

   * Verificar que en el servidor existe la versión correcta de Node/NPM/PHP/Composer.
   * Revisar logs (`stdout` y `stderr`) para detectar errores de compatibilidad.
   * El servidor debería reportar el error exacto al cliente (código 500 con detalle).

3. **Permisos de Directorios**

   * `cache_dir` debe ser escribible por el proceso.
   * Si el servidor corre en modo “sin permisos de root”, asegurarse de que el usuario tenga acceso a `cache_dir`.

4. **Limpieza Inadecuada de Carpetas Temporales**

   * Si el proceso de instalación falla, debe borrarse la carpeta temporal (`temp_dir`) para evitar acumular basura.
   * Utilizar `shutil.rmtree(temp_dir, ignore_errors=True)` en bloque `finally`.

5. **El ZIP supera el máximo permitido**

   * Algunos proxies o clientes HTTP limitan el tamaño de respuesta.
   * Configurar chunked transfer o resumable downloads (fuera del alcance de la primera versión).

---

## 12. Conclusiones

El proyecto **DepCacheProxy** (`dep_cache_proxy`) ofrece una solución genérica y escalable para cachear y servir dependencias de gestores como NPM o Composer, acelerando pipelines de construcción y mitigando problemas de red inestable. Al seguir principios DDD y SOLID, se logra una arquitectura modular, mantenible y extensible:

* **Dominio**: Entidades `DependencySet` y `CacheObject`, repositorio `ICacheRepository`.
* **Aplicación**: Caso de uso `HandleCacheRequest` orquesta la lógica de validación de cache, generación de dependencias y compresión.
* **Infraestructura**: `FileSystemCacheRepository`, `NpmInstaller`, `ComposerInstaller`, `ZipUtil`, `ApiKeyValidator`.
* **Interfaces**: FastAPI para servidor (`POST /v1/cache`, `GET /download/{hash}.zip`), cliente CLI con `requests` y `argparse`.

El pseudocódigo provisto puede servir como base directa para implementar la librería en Python. Se recomiendan pruebas exhaustivas, integración continua (CI) y despliegue con contenedores Docker, montando el volumen de `cache_dir` y configurando un proxy inverso para TLS.