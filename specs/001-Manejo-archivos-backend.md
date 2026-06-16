# 001 - Manejo de archivos en backend

## Resumen

Este documento describe la nueva implementacion del manejo de archivos en el backend FastAPI de FyTic.

El cambio principal observado en git es que el backend deja de depender de Supabase Storage para guardar los bytes crudos de los archivos y pasa a guardarlos en disco local, dentro de un directorio configurable por `UPLOAD_ROOT`.

Supabase sigue existiendo para la landing actual, pero el modulo SaaS de archivos usa:

- Postgres via SQLAlchemy para metadata de clientes y archivos.
- Alembic para migraciones.
- Disco local para PDFs/DOCX subidos.
- Endpoints FastAPI bajo `/api/app/*`.
- `FileResponse` para devolver el contenido del archivo.

La implementacion actual cubre manejo de clientes demo, arbol de archivos/carpetas, subida, listado, renombrado, movimiento, borrado y descarga.

## Archivos involucrados

Cambios modificados en archivos existentes:

- `.env.example`
- `.gitignore`
- `app/config.py`
- `main.py`
- `requirements.txt`

Archivos/carpetas nuevos relevantes:

- `app/database.py`
- `app/db_models.py`
- `app/app_clients/`
- `app/files/`
- `alembic/`
- `docker-compose.yml`
- `scripts/seed_demo.py`
- `tests/`

## Configuracion

### Variables de entorno nuevas

Definidas en `.env.example`:

```env
DATABASE_URL=postgresql+psycopg://fytic:fytic@localhost:5432/fytic_saas
UPLOAD_ROOT=var/uploads
DEMO_FIRM_ID=00000000-0000-0000-0000-000000000001
```

### `DATABASE_URL`

URL de conexion a la base Postgres usada por la capa SaaS.

La implementacion usa `psycopg` y SQLAlchemy:

```python
engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
```

### `UPLOAD_ROOT`

Directorio raiz donde se guardan los archivos subidos.

Valor por defecto:

```text
var/uploads
```

El backend crea este directorio al arrancar:

```python
Path(settings.upload_root).mkdir(parents=True, exist_ok=True)
```

El directorio `var/` esta ignorado por git para evitar commitear archivos subidos por usuarios.

### `DEMO_FIRM_ID`

ID fijo de despacho usado mientras no hay autenticacion real ni multi-tenant.

Todos los endpoints SaaS filtran por este `firm_id`.

## Dependencias nuevas

Agregadas a `requirements.txt`:

```txt
sqlalchemy>=2.0
alembic>=1.13
psycopg[binary]>=3.1
python-multipart>=0.0.9
```

Uso:

- `sqlalchemy`: ORM y sesiones contra Postgres.
- `alembic`: migraciones de esquema.
- `psycopg[binary]`: driver Postgres.
- `python-multipart`: soporte para `multipart/form-data` en subidas con `UploadFile`.

## Inicializacion del backend

En `main.py` se agregaron:

- Routers SaaS:
  - `app_clients_router` en `/api/app`
  - `files_router` en `/api/app`
- CORS con soporte para `PATCH` y `DELETE`.
- Creacion automatica de `UPLOAD_ROOT`.
- Check de conexion a Postgres SaaS durante startup.
- Check existente de Supabase para la landing.

Metodos permitidos por CORS:

```python
allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
```

## Base de datos

La metadata de SaaS vive en Postgres, no en Supabase Storage.

### Modelo `FirmClient`

Tabla:

```text
firm_clients
```

Representa clientes/casos del despacho dentro de la app SaaS.

Campos principales:

- `id`: UUID primario.
- `firm_id`: UUID del despacho demo.
- `slug`: identificador legible por URL.
- `name`: nombre del cliente.
- `color`: color del cliente en UI.
- `areas`: arreglo de categorias legales.
- `created_at`
- `updated_at`

Restriccion:

```text
unique(firm_id, slug)
```

### Modelo `FileRow`

Tabla:

```text
files
```

Representa carpetas y archivos en una sola tabla.

Campos principales:

- `id`: UUID primario.
- `firm_id`: UUID del despacho demo.
- `client_id`: FK opcional a `firm_clients.id`.
- `parent_id`: FK opcional a `files.id`.
- `name`: nombre visible en UI.
- `type`: `file` o `folder`.
- `storage_path`: ruta relativa bajo `UPLOAD_ROOT`.
- `mime_type`: MIME del archivo.
- `size`: tamano en bytes.
- `content_hash`: SHA-256 del contenido.
- `ingestion_status`: reservado para RAG.
- `ingestion_error`: reservado para RAG.
- `chunk_count`: reservado para RAG.
- `created_at`
- `updated_at`

Indice:

```text
ix_files_firm_client_parent(firm_id, client_id, parent_id)
```

Relaciones:

- `client_id -> firm_clients.id ON DELETE CASCADE`
- `parent_id -> files.id ON DELETE CASCADE`

## Migracion Alembic

La migracion inicial SaaS es:

```text
alembic/versions/a2aaf00efb12_saas_firm_clients_files.py
```

Crea:

- `firm_clients`
- `files`
- indice `ix_files_firm_client_parent`

## Almacenamiento local

La logica de disco vive en:

```text
app/files/storage.py
```

### Layout fisico

Los archivos se guardan bajo:

```text
UPLOAD_ROOT/<firm_id>/<client_id>/<file_id>.<ext>
```

Ejemplo:

```text
var/uploads/00000000-0000-0000-0000-000000000001/7f3.../8a2....pdf
```

En la base de datos solo se guarda la ruta relativa:

```text
<firm_id>/<client_id>/<file_id>.<ext>
```

Esto permite mover el `UPLOAD_ROOT` sin tener que reescribir las filas de `files`.

### Extensiones permitidas

Actualmente solo se aceptan:

```python
ALLOWED_EXT = {".pdf", ".docx"}
```

Si se sube otro tipo, el backend responde:

```text
415 Unsupported Media Type
```

### Resolucion segura de paths

La funcion `_resolve(storage_path)` compone la ruta final y valida que siga dentro de `UPLOAD_ROOT`:

```python
target = (UPLOAD_ROOT / storage_path).resolve()
if not target.is_relative_to(UPLOAD_ROOT):
    raise HTTPException(400, "invalid storage path")
```

Esto evita path traversal como `../../archivo`.

### Escritura del archivo

`save_upload(file, storage_path)`:

1. Valida extension.
2. Resuelve ruta segura bajo `UPLOAD_ROOT`.
3. Crea directorios padres.
4. Escribe en chunks de 1 MB.
5. Calcula `size`.
6. Calcula `content_hash` con SHA-256.
7. Devuelve `(size, content_hash)`.

### Borrado fisico

`delete_file(storage_path)`:

- Resuelve la ruta bajo `UPLOAD_ROOT`.
- Ejecuta `unlink(missing_ok=True)`.

El borrado no falla si el archivo ya no existe en disco.

## Endpoints implementados

Todos los endpoints nuevos viven bajo:

```text
/api/app
```

### Clientes

#### `GET /api/app/clients`

Lista los clientes del despacho demo.

Respuesta:

```json
[
  {
    "id": "uuid",
    "slug": "mendoza-asociados",
    "name": "Mendoza & Asociados",
    "color": "#3b82f6",
    "areas": ["Arrendamiento", "Civil", "Corporativo"]
  }
]
```

#### `GET /api/app/clients/{slug}/files`

Lista archivos y carpetas de un cliente.

Query opcional:

```text
?type=file
?type=folder
```

Errores:

- `404` si el `slug` no existe.

### Archivos

#### `GET /api/app/files`

Lista archivos y carpetas del despacho demo.

Query opcional:

```text
?clientSlug=mendoza-asociados
```

Errores:

- `404` si `clientSlug` no existe.

#### `POST /api/app/clients/{slug}/files`

Sube un archivo para un cliente.

Tipo:

```text
multipart/form-data
```

Campos:

- `file`: archivo PDF/DOCX.
- `parent_id`: carpeta destino opcional.

Flujo interno:

1. Resuelve el cliente por `slug`.
2. Toma la extension del filename.
3. Genera `file_id` UUID.
4. Construye `storage_path`.
5. Guarda el archivo fisico en disco.
6. Crea la fila `files`.
7. Devuelve un `FileItem`.

Errores:

- `404` si el cliente no existe.
- `404` si `parent_id` no existe.
- `400` si `parent_id` apunta a un archivo y no a una carpeta.
- `415` si la extension no es `.pdf` o `.docx`.

Nota: `ingestion_status` se crea como `pending`, pero la ingesta RAG todavia esta reservada/inactiva en esta implementacion.

#### `POST /api/app/files`

Crea una carpeta.

Body:

```json
{
  "name": "Contratos",
  "parentId": "uuid opcional",
  "clientSlug": "mendoza-asociados"
}
```

Comportamiento:

- Si `clientSlug` viene, la carpeta queda asociada a ese cliente.
- Si no viene, la carpeta queda a nivel despacho.
- `parentId` debe apuntar a una carpeta.

Errores:

- `404` si `clientSlug` no existe.
- `404` si `parentId` no existe.
- `400` si `parentId` apunta a un archivo.

#### `PATCH /api/app/files/{file_id}`

Renombra o mueve un archivo/carpeta.

Body:

```json
{
  "name": "nuevo-nombre.pdf",
  "parentId": "uuid carpeta destino"
}
```

Ambos campos son opcionales.

Comportamiento:

- Si viene `name`, actualiza el nombre visible.
- Si viene `parentId`, mueve el item bajo esa carpeta.
- No cambia el archivo fisico cuando se renombra; `storage_path` permanece estable.

Errores:

- `404` si `file_id` no existe.
- `404` si `parentId` no existe.
- `400` si `parentId` apunta a un archivo.

#### `DELETE /api/app/files/{file_id}`

Borra archivo o carpeta.

Comportamiento:

- Si es archivo, borra el binario local y la fila.
- Si es carpeta, recolecta recursivamente los `storage_path` de todos sus descendientes tipo `file`, borra esos binarios y despues borra la carpeta.
- La BD elimina filas descendientes por `ON DELETE CASCADE`.

Errores:

- `404` si `file_id` no existe.

#### `GET /api/app/files/{file_id}/content`

Descarga el contenido de un archivo.

Comportamiento:

1. Busca la fila `files`.
2. Valida que sea `type = "file"`.
3. Resuelve `UPLOAD_ROOT / storage_path`.
4. Verifica que exista en disco.
5. Devuelve `FileResponse` con `media_type` y `filename`.

Errores:

- `404` si `file_id` no existe.
- `400` si el item es una carpeta.
- `404` si la fila existe pero el archivo fisico no esta en disco.

## Shape de respuesta `FileItem`

La respuesta usada por frontend es:

```json
{
  "id": "uuid",
  "name": "Contrato.pdf",
  "type": "file",
  "parentId": null,
  "clientId": "uuid",
  "path": "/Contrato.pdf",
  "size": 12345,
  "modifiedAt": "2026-06-16T17:00:00",
  "mimeType": "application/pdf"
}
```

Para carpetas:

```json
{
  "id": "uuid",
  "name": "Contratos",
  "type": "folder",
  "parentId": null,
  "clientId": "uuid",
  "path": "/Contratos",
  "size": null,
  "modifiedAt": "2026-06-16T17:00:00",
  "mimeType": null
}
```

## Validaciones actuales

La implementacion valida:

- El cliente existe y pertenece a `DEMO_FIRM_ID`.
- El padre existe y pertenece a `DEMO_FIRM_ID`.
- El padre es carpeta, no archivo.
- La extension del upload es `.pdf` o `.docx`.
- La ruta resuelta queda dentro de `UPLOAD_ROOT`.
- El item existe antes de editar/borrar/descargar.
- Solo archivos se pueden descargar; carpetas devuelven `400`.

## Comportamiento de nombres

El nombre visible se guarda en `files.name`.

El nombre fisico en disco no usa el nombre original del usuario, sino:

```text
<file_id>.<ext>
```

Ventajas:

- Evita colisiones.
- Evita problemas con caracteres especiales.
- Permite renombrar sin mover archivos.
- Permite conservar `storage_path` estable para RAG.

## Borrado recursivo de carpetas

Antes de borrar una carpeta, el backend recorre sus descendientes para juntar los `storage_path` de los archivos.

Funcion:

```python
_collect_storage_paths(file_id, session)
```

Luego borra los binarios fisicos y finalmente borra la fila padre.

La cascada de Postgres se encarga de eliminar filas hijas.

## Seguridad

### Lo que ya esta cubierto

- No se expone `var/uploads` como carpeta publica.
- La descarga pasa por endpoint FastAPI.
- Se usa `FileResponse`, no links directos al filesystem.
- Se valida path traversal con `Path.resolve()` e `is_relative_to`.
- `var/` esta ignorado por git.
- Se restringen extensiones a PDF/DOCX.
- Todos los queries filtran por `DEMO_FIRM_ID`.

### Riesgos pendientes

- No hay autenticacion real todavia.
- No hay RLS por despacho todavia.
- El aislamiento multi-tenant depende de `DEMO_FIRM_ID`.
- No hay limite de tamano de archivo.
- La validacion actual se basa en extension; no verifica magic bytes.
- No hay antivirus ni sandboxing.
- No hay control de cuota por despacho.
- En despliegue cloud, el disco debe ser persistente o se perderan uploads.
- Si se corre con multiples replicas, el disco local no se comparte entre instancias.

## Consideraciones de despliegue

Esta decision funciona bien para desarrollo local y demo si el backend corre en una sola maquina.

Para produccion o staging real se debe confirmar:

- Que `UPLOAD_ROOT` apunte a un volumen persistente.
- Que el volumen sobreviva redeploys.
- Que no haya multiples replicas desincronizadas.
- Que exista estrategia de backup.
- Que las politicas de retencion/borrado sean claras.

Si el hosting no ofrece disco persistente, habria que revisar esta decision antes de produccion.

## Relacion con RAG

Los campos reservados para RAG ya existen en `files`:

- `ingestion_status`
- `ingestion_error`
- `chunk_count`
- `content_hash`
- `storage_path`

En esta implementacion, `ingestion_status` queda en `pending` al subir archivo.

La futura ingesta deberia resolver el archivo desde:

```text
UPLOAD_ROOT / files.storage_path
```

El contrato recomendado se mantiene:

```python
ingest_document(file_id, storage_path, client_id, firm_id)
delete_document_chunks(file_id)
```

Donde `storage_path` es una ruta relativa local, no una URL ni path de Supabase Storage.

## Datos demo

Script:

```text
scripts/seed_demo.py
```

Crea o actualiza tres clientes:

- `mendoza-asociados`
- `garcia-vargas-s-a`
- `ruiz-hernandez`

Usa upsert por:

```text
(firm_id, slug)
```

## Desarrollo local

Levantar Postgres:

```bash
docker compose up -d db
```

Aplicar migraciones:

```bash
alembic upgrade head
```

Seed demo:

```bash
python scripts/seed_demo.py
```

Arrancar backend:

```bash
python main.py
```

Docs:

```text
http://localhost:8000/docs
```

## Testing

Hay pruebas en:

```text
tests/test_api.py
tests/conftest.py
```

Flujos cubiertos:

- `GET /api/app/clients`
- `GET /api/app/clients/{slug}/files`
- `GET /api/app/files`
- `POST /api/app/clients/{slug}/files`
- `POST /api/app/files`
- `PATCH /api/app/files/{id}`
- `DELETE /api/app/files/{id}`
- `GET /api/app/files/{id}/content`

La suite verifica:

- Listado de clientes.
- Listado por cliente.
- Filtro por tipo (`file`/`folder`).
- Subida de PDF y DOCX.
- Rechazo de extensiones no permitidas.
- Creacion fisica del archivo en disco.
- Shape de respuesta.
- Subida dentro de carpeta.
- Rechazo de archivo como padre.
- Renombrado.
- Movimiento.
- Borrado de archivo.
- Borrado fisico del binario.
- Borrado de carpeta vacia.
- Borrado de carpeta con descendientes.
- Cascada de filas en BD.
- Descarga con MIME correcto.
- Descarga con nombre correcto.
- Rechazo de descarga de carpetas.

El fixture de tests redirige `UPLOAD_ROOT` a `tmp_path`, evitando tocar `var/uploads` real:

```python
monkeypatch.setattr(storage_mod, "UPLOAD_ROOT", tmp_path)
monkeypatch.setattr(router_mod, "UPLOAD_ROOT", tmp_path)
```

## Paso a paso para ejecutar tests

Ejecutar estos comandos desde la raiz del backend:

```bash
cd C:\Users\Gabriel\FyTic\backend-mvp
```

### 1. Levantar Postgres local

La suite usa Postgres real. Primero levanta el contenedor definido en `docker-compose.yml`:

```bash
docker compose up -d db
```

Verifica que el contenedor este corriendo:

```bash
docker ps --filter name=fytic_saas_db
```

### 2. Crear la base de datos de test

La app normal usa `fytic_saas`, pero los tests usan `fytic_test`.

Crear la base una sola vez:

```bash
docker exec fytic_saas_db psql -U fytic -d fytic_saas -c "CREATE DATABASE fytic_test;"
```

Si ya existe, Postgres devolvera un error indicando que la base ya fue creada. En ese caso puedes continuar.

### 3. Crear y activar entorno Python

Opcion con `venv`:

```bash
python -m venv .venv
.\.venv\Scripts\activate
```

Opcion con conda, si se esta usando el entorno del proyecto:

```bash
conda activate fytic
```

### 4. Instalar dependencias

Instala dependencias de runtime y de testing:

```bash
pip install -r requirements-dev.txt
```

`requirements-dev.txt` incluye `requirements.txt`, asi que no hace falta instalar ambos por separado.

### 5. Ejecutar la suite completa

```bash
pytest
```

### 6. Ejecutar solo tests de API de archivos/clientes

```bash
pytest tests/test_api.py
```

### 7. Ejecutar con salida detallada

```bash
pytest -v
```

### 8. Ejecutar un caso o clase especifica

Ejemplo, solo subida de archivos:

```bash
pytest tests/test_api.py::TestUploadFile -v
```

Ejemplo, solo descarga:

```bash
pytest tests/test_api.py::TestDownloadFile -v
```

### 9. Que esperar si todo esta bien

Los tests deben:

- Crear tablas temporales al inicio de la sesion.
- Truncar `files` y `firm_clients` entre tests.
- Redirigir uploads a un directorio temporal `tmp_path`.
- No escribir archivos reales en `var/uploads`.
- Validar que PDFs/DOCX se guardan y se eliminan correctamente.
- Validar que las respuestas HTTP tienen los codigos esperados.

### 10. Problemas comunes

Si aparece un error de conexion a Postgres:

```text
connection refused
```

Revisa que Docker este encendido y que el contenedor este arriba:

```bash
docker compose up -d db
```

Si aparece que `fytic_test` no existe:

```bash
docker exec fytic_saas_db psql -U fytic -d fytic_saas -c "CREATE DATABASE fytic_test;"
```

Si aparece que falta `pytest`:

```bash
pip install -r requirements-dev.txt
```

Si los tests fallan por tablas existentes o estado raro, reinicia la base de test:

```bash
docker exec fytic_saas_db psql -U fytic -d fytic_saas -c "DROP DATABASE IF EXISTS fytic_test;"
docker exec fytic_saas_db psql -U fytic -d fytic_saas -c "CREATE DATABASE fytic_test;"
```

## Checklist tecnico

- [x] Metadata de archivos en Postgres.
- [x] Archivos crudos en disco local.
- [x] Directorio local ignorado por git.
- [x] Subida multipart.
- [x] Validacion basica de extension.
- [x] Hash SHA-256.
- [x] Tamano en bytes.
- [x] Listado completo.
- [x] Listado por cliente.
- [x] Crear carpeta.
- [x] Renombrar.
- [x] Mover.
- [x] Borrar archivo fisico.
- [x] Borrar carpetas con descendientes.
- [x] Descargar con `FileResponse`.
- [x] Tests de endpoints principales.
- [ ] Auth real.
- [ ] RLS por despacho.
- [ ] Limite de tamano.
- [ ] Validacion de contenido real/magic bytes.
- [ ] Antivirus/sanitizacion.
- [ ] Jobs reales de ingesta RAG.
- [ ] Volumen persistente documentado para deploy.

## Decisiones importantes

1. El backend no guarda bytes crudos en Supabase Storage.
2. `storage_path` se conserva como abstraccion estable, pero ahora es una ruta relativa local.
3. Renombrar no mueve el archivo fisico.
4. Borrar carpeta implica borrar primero todos los binarios descendientes y luego la fila padre.
5. La descarga pasa siempre por FastAPI.
6. Las carpetas no tienen archivo fisico.
7. La implementacion actual esta pensada para demo/desarrollo local, no para multi-replica en produccion.
