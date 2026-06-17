"""
Tests completos para los endpoints de clientes y archivos.

Flujos cubiertos (según lo discutido):
  - GET  /api/app/clients
  - GET  /api/app/clients/{slug}/files
  - GET  /api/app/files
  - POST /api/app/clients/{slug}/files  (subida de archivo)
  - POST /api/app/files                 (crear carpeta)
  - PATCH /api/app/files/{id}           (renombrar / mover)
  - DELETE /api/app/files/{id}          (borrar archivo o carpeta)
  - GET  /api/app/files/{id}/content    (descargar archivo)
"""
import uuid

import pytest

from tests.conftest import fake_file, make_folder, upload_pdf


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/app/clients
# ═══════════════════════════════════════════════════════════════════════════════

class TestListClients:
    def test_sin_datos_devuelve_lista_vacia(self, client):
        r = client.get("/api/app/clients")
        assert r.status_code == 200
        assert r.json() == []

    def test_devuelve_los_tres_clientes_seeded(self, client, seeded_clients):
        r = client.get("/api/app/clients")
        assert r.status_code == 200
        assert len(r.json()) == 3

    def test_slugs_correctos(self, client, seeded_clients):
        slugs = {c["slug"] for c in client.get("/api/app/clients").json()}
        assert slugs == {"mendoza-asociados", "garcia-vargas-s-a", "ruiz-hernandez"}

    def test_shape_del_cliente(self, client, seeded_clients):
        data = client.get("/api/app/clients").json()
        mendoza = next(c for c in data if c["slug"] == "mendoza-asociados")
        assert mendoza["name"] == "Mendoza & Asociados"
        assert mendoza["color"] == "#3b82f6"
        assert "Arrendamiento" in mendoza["areas"]
        assert "id" in mendoza


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/app/clients/{slug}/files
# ═══════════════════════════════════════════════════════════════════════════════

class TestListClientFiles:
    def test_slug_desconocido_devuelve_404(self, client, seeded_clients):
        r = client.get("/api/app/clients/no-existe/files")
        assert r.status_code == 404

    def test_cliente_sin_archivos_devuelve_lista_vacia(self, client, seeded_clients):
        r = client.get("/api/app/clients/mendoza-asociados/files")
        assert r.status_code == 200
        assert r.json() == []

    def test_solo_devuelve_archivos_del_cliente(self, client, seeded_clients):
        upload_pdf(client, slug="mendoza-asociados")
        upload_pdf(client, slug="garcia-vargas-s-a")

        r = client.get("/api/app/clients/mendoza-asociados/files")
        assert len(r.json()) == 1

    def test_filtro_type_file(self, client, seeded_clients):
        upload_pdf(client)
        make_folder(client)

        items = client.get("/api/app/clients/mendoza-asociados/files?type=file").json()
        assert len(items) == 1
        assert all(i["type"] == "file" for i in items)

    def test_filtro_type_folder(self, client, seeded_clients):
        upload_pdf(client)
        make_folder(client)

        items = client.get("/api/app/clients/mendoza-asociados/files?type=folder").json()
        assert len(items) == 1
        assert all(i["type"] == "folder" for i in items)


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/app/files
# ═══════════════════════════════════════════════════════════════════════════════

class TestListFiles:
    def test_sin_datos_devuelve_lista_vacia(self, client, seeded_clients):
        r = client.get("/api/app/files")
        assert r.status_code == 200
        assert r.json() == []

    def test_devuelve_archivos_de_todo_el_despacho(self, client, seeded_clients):
        upload_pdf(client, slug="mendoza-asociados")
        upload_pdf(client, slug="garcia-vargas-s-a")

        r = client.get("/api/app/files")
        assert len(r.json()) == 2

    def test_filtro_por_client_slug(self, client, seeded_clients):
        upload_pdf(client, slug="mendoza-asociados")
        upload_pdf(client, slug="garcia-vargas-s-a")

        items = client.get("/api/app/files?clientSlug=mendoza-asociados").json()
        assert len(items) == 1

    def test_filtro_slug_desconocido_devuelve_404(self, client, seeded_clients):
        r = client.get("/api/app/files?clientSlug=no-existe")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# POST /api/app/clients/{slug}/files  (subida de archivo)
# ═══════════════════════════════════════════════════════════════════════════════

class TestUploadFile:
    def test_pdf_devuelve_201(self, client, seeded_clients):
        r = upload_pdf(client)
        assert r.status_code == 201

    def test_docx_devuelve_201(self, client, seeded_clients):
        r = client.post(
            "/api/app/clients/mendoza-asociados/files",
            files=fake_file("contrato.docx"),
        )
        assert r.status_code == 201

    def test_extension_no_permitida_devuelve_415(self, client, seeded_clients):
        r = client.post(
            "/api/app/clients/mendoza-asociados/files",
            files=fake_file("notas.txt"),
        )
        assert r.status_code == 415

    def test_cliente_desconocido_devuelve_404(self, client, seeded_clients):
        r = client.post(
            "/api/app/clients/no-existe/files",
            files=fake_file("doc.pdf"),
        )
        assert r.status_code == 404

    def test_crea_archivo_fisico_en_disco(self, client, seeded_clients, tmp_path):
        upload_pdf(client)
        assert len(list(tmp_path.rglob("*.pdf"))) == 1

    def test_shape_de_respuesta(self, client, seeded_clients):
        r = upload_pdf(client, filename="mi_doc.pdf")
        data = r.json()
        assert data["name"] == "mi_doc.pdf"
        assert data["type"] == "file"
        assert data["mimeType"] == "application/pdf"
        assert data["size"] > 0
        assert data["id"] is not None
        assert data["parentId"] is None

    def test_mime_type_docx(self, client, seeded_clients):
        r = client.post(
            "/api/app/clients/mendoza-asociados/files",
            files=fake_file("contrato.docx"),
        )
        assert "wordprocessingml" in r.json()["mimeType"]

    def test_subir_dentro_de_carpeta(self, client, seeded_clients):
        folder_id = make_folder(client).json()["id"]
        r = upload_pdf(client, parent_id=folder_id)
        assert r.status_code == 201
        assert r.json()["parentId"] == folder_id

    def test_subir_en_carpeta_de_otro_cliente_devuelve_400(self, client, seeded_clients):
        folder_id = make_folder(client, client_slug="garcia-vargas-s-a").json()["id"]
        r = upload_pdf(client, slug="mendoza-asociados", parent_id=folder_id)
        assert r.status_code == 400

    def test_archivo_como_padre_devuelve_400(self, client, seeded_clients):
        file_id = upload_pdf(client).json()["id"]
        r = upload_pdf(client, filename="doc2.pdf", parent_id=file_id)
        assert r.status_code == 400

    def test_padre_inexistente_devuelve_404(self, client, seeded_clients):
        r = client.post(
            "/api/app/clients/mendoza-asociados/files",
            files=fake_file("doc.pdf"),
            data={"parent_id": str(uuid.uuid4())},
        )
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# POST /api/app/files  (crear carpeta)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCreateFolder:
    def test_crear_carpeta_devuelve_201(self, client, seeded_clients):
        r = make_folder(client)
        assert r.status_code == 201

    def test_shape_de_carpeta(self, client, seeded_clients):
        r = make_folder(client, name="Demandas")
        data = r.json()
        assert data["name"] == "Demandas"
        assert data["type"] == "folder"
        assert data["size"] is None
        assert data["id"] is not None

    def test_carpeta_anidada(self, client, seeded_clients):
        parent_id = make_folder(client, name="Contratos").json()["id"]
        r = make_folder(client, name="Arrendamiento", parent_id=parent_id)
        assert r.status_code == 201
        assert r.json()["parentId"] == parent_id

    def test_archivo_como_padre_devuelve_400(self, client, seeded_clients):
        file_id = upload_pdf(client).json()["id"]
        r = client.post("/api/app/files", json={
            "name": "Carpeta",
            "clientSlug": "mendoza-asociados",
            "parentId": file_id,
        })
        assert r.status_code == 400

    def test_padre_inexistente_devuelve_404(self, client, seeded_clients):
        r = client.post("/api/app/files", json={
            "name": "Carpeta",
            "parentId": str(uuid.uuid4()),
        })
        assert r.status_code == 404

    def test_carpeta_sin_cliente(self, client, seeded_clients):
        r = client.post("/api/app/files", json={"name": "General"})
        assert r.status_code == 201
        assert r.json()["clientId"] is None

    def test_carpeta_anidada_infiere_cliente_del_padre(self, client, seeded_clients):
        parent = make_folder(client, name="Contratos").json()
        r = client.post("/api/app/files", json={
            "name": "Arrendamiento",
            "parentId": parent["id"],
        })
        assert r.status_code == 201
        assert r.json()["clientId"] == parent["clientId"]

    def test_carpeta_con_cliente_distinto_al_padre_devuelve_400(self, client, seeded_clients):
        parent = make_folder(client, name="Contratos", client_slug="mendoza-asociados").json()
        r = client.post("/api/app/files", json={
            "name": "Fiscal",
            "clientSlug": "garcia-vargas-s-a",
            "parentId": parent["id"],
        })
        assert r.status_code == 400

    def test_carpeta_con_cliente_desconocido_devuelve_404(self, client, seeded_clients):
        r = client.post("/api/app/files", json={
            "name": "Carpeta",
            "clientSlug": "no-existe",
        })
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# PATCH /api/app/files/{id}
# ═══════════════════════════════════════════════════════════════════════════════

class TestUpdateFile:
    def test_renombrar_archivo(self, client, seeded_clients):
        file_id = upload_pdf(client).json()["id"]
        r = client.patch(f"/api/app/files/{file_id}", json={"name": "nuevo.pdf"})
        assert r.status_code == 200
        assert r.json()["name"] == "nuevo.pdf"

    def test_renombrar_carpeta(self, client, seeded_clients):
        folder_id = make_folder(client, "Contratos").json()["id"]
        r = client.patch(f"/api/app/files/{folder_id}", json={"name": "Convenios"})
        assert r.status_code == 200
        assert r.json()["name"] == "Convenios"

    def test_mover_archivo_a_carpeta(self, client, seeded_clients):
        file_id = upload_pdf(client).json()["id"]
        folder_id = make_folder(client).json()["id"]
        r = client.patch(f"/api/app/files/{file_id}", json={"parentId": folder_id})
        assert r.status_code == 200
        assert r.json()["parentId"] == folder_id

    def test_mover_archivo_a_raiz_del_despacho(self, client, seeded_clients):
        folder_id = make_folder(client).json()["id"]
        file_id = upload_pdf(client, parent_id=folder_id).json()["id"]
        r = client.patch(f"/api/app/files/{file_id}", json={"parentId": None})
        assert r.status_code == 200
        assert r.json()["parentId"] is None
        assert r.json()["clientId"] is None

    def test_mover_archivo_a_raiz_de_otro_cliente(self, client, seeded_clients):
        file_id = upload_pdf(client, slug="mendoza-asociados").json()["id"]
        target_client_id = next(c.id for c in seeded_clients if c.slug == "garcia-vargas-s-a")
        r = client.patch(f"/api/app/files/{file_id}", json={
            "parentId": None,
            "clientSlug": "garcia-vargas-s-a",
        })
        assert r.status_code == 200
        assert r.json()["parentId"] is None
        assert r.json()["clientId"] == str(target_client_id)

    def test_mover_archivo_a_carpeta_de_otro_cliente_reasigna_cliente(self, client, seeded_clients):
        file_id = upload_pdf(client, slug="mendoza-asociados").json()["id"]
        target_folder = make_folder(client, client_slug="garcia-vargas-s-a").json()
        r = client.patch(f"/api/app/files/{file_id}", json={"parentId": target_folder["id"]})
        assert r.status_code == 200
        assert r.json()["parentId"] == target_folder["id"]
        assert r.json()["clientId"] == target_folder["clientId"]

    def test_mover_carpeta_a_otro_cliente_reasigna_descendientes(self, client, seeded_clients):
        folder = make_folder(client, name="Contratos", client_slug="mendoza-asociados").json()
        file_id = upload_pdf(client, slug="mendoza-asociados", parent_id=folder["id"]).json()["id"]
        target = make_folder(client, name="Fiscal", client_slug="garcia-vargas-s-a").json()

        r = client.patch(f"/api/app/files/{folder['id']}", json={"parentId": target["id"]})
        assert r.status_code == 200
        assert r.json()["clientId"] == target["clientId"]

        moved_file = next(item for item in client.get("/api/app/files").json() if item["id"] == file_id)
        assert moved_file["clientId"] == target["clientId"]

    def test_no_permite_mover_carpeta_a_su_descendiente(self, client, seeded_clients):
        parent_id = make_folder(client, name="Contratos").json()["id"]
        child_id = make_folder(client, name="Sub", parent_id=parent_id).json()["id"]
        r = client.patch(f"/api/app/files/{parent_id}", json={"parentId": child_id})
        assert r.status_code == 400

    def test_mover_a_carpeta_inexistente_devuelve_404(self, client, seeded_clients):
        file_id = upload_pdf(client).json()["id"]
        r = client.patch(f"/api/app/files/{file_id}", json={"parentId": str(uuid.uuid4())})
        assert r.status_code == 404

    def test_mover_con_archivo_como_padre_devuelve_400(self, client, seeded_clients):
        file1_id = upload_pdf(client, filename="a.pdf").json()["id"]
        file2_id = upload_pdf(client, filename="b.pdf").json()["id"]
        r = client.patch(f"/api/app/files/{file1_id}", json={"parentId": file2_id})
        assert r.status_code == 400

    def test_id_inexistente_devuelve_404(self, client, seeded_clients):
        r = client.patch(f"/api/app/files/{uuid.uuid4()}", json={"name": "x.pdf"})
        assert r.status_code == 404

    def test_patch_parcial_no_sobreescribe_otros_campos(self, client, seeded_clients):
        folder_id = make_folder(client).json()["id"]
        file_id = upload_pdf(client, parent_id=folder_id).json()["id"]

        # solo renombramos, parentId no viene en el body
        r = client.patch(f"/api/app/files/{file_id}", json={"name": "renombrado.pdf"})
        data = r.json()
        assert data["name"] == "renombrado.pdf"
        assert data["parentId"] == folder_id  # no se perdió


# ═══════════════════════════════════════════════════════════════════════════════
# DELETE /api/app/files/{id}
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeleteFile:
    def test_borrar_archivo_devuelve_204(self, client, seeded_clients):
        file_id = upload_pdf(client).json()["id"]
        r = client.delete(f"/api/app/files/{file_id}")
        assert r.status_code == 204

    def test_borrar_archivo_lo_elimina_de_la_bd(self, client, seeded_clients):
        file_id = upload_pdf(client).json()["id"]
        client.delete(f"/api/app/files/{file_id}")
        ids = {f["id"] for f in client.get("/api/app/files").json()}
        assert file_id not in ids

    def test_borrar_archivo_elimina_binario_del_disco(self, client, seeded_clients, tmp_path):
        file_id = upload_pdf(client).json()["id"]
        assert len(list(tmp_path.rglob("*.pdf"))) == 1
        client.delete(f"/api/app/files/{file_id}")
        assert len(list(tmp_path.rglob("*.pdf"))) == 0

    def test_borrar_carpeta_vacia_devuelve_204(self, client, seeded_clients):
        folder_id = make_folder(client).json()["id"]
        r = client.delete(f"/api/app/files/{folder_id}")
        assert r.status_code == 204

    def test_borrar_carpeta_con_archivo_elimina_binario(self, client, seeded_clients, tmp_path):
        folder_id = make_folder(client).json()["id"]
        upload_pdf(client, parent_id=folder_id)
        assert len(list(tmp_path.rglob("*.pdf"))) == 1

        client.delete(f"/api/app/files/{folder_id}")
        assert len(list(tmp_path.rglob("*.pdf"))) == 0

    def test_borrar_carpeta_anidada_elimina_todos_los_binarios(self, client, seeded_clients, tmp_path):
        """
        Contratos/
          doc1.pdf
          Arrendamiento/
            doc2.pdf
        Borrar Contratos debe eliminar ambos PDFs del disco.
        """
        folder_id = make_folder(client, "Contratos").json()["id"]
        sub_id = make_folder(client, "Arrendamiento", parent_id=folder_id).json()["id"]
        upload_pdf(client, filename="doc1.pdf", parent_id=folder_id)
        upload_pdf(client, filename="doc2.pdf", parent_id=sub_id)

        assert len(list(tmp_path.rglob("*.pdf"))) == 2
        client.delete(f"/api/app/files/{folder_id}")
        assert len(list(tmp_path.rglob("*.pdf"))) == 0

    def test_borrar_carpeta_anidada_elimina_filas_en_cascade(self, client, seeded_clients):
        folder_id = make_folder(client, "Contratos").json()["id"]
        sub_id = make_folder(client, "Sub", parent_id=folder_id).json()["id"]
        file_id = upload_pdf(client, parent_id=sub_id).json()["id"]

        client.delete(f"/api/app/files/{folder_id}")

        all_ids = {f["id"] for f in client.get("/api/app/files").json()}
        assert folder_id not in all_ids
        assert sub_id not in all_ids
        assert file_id not in all_ids

    def test_id_inexistente_devuelve_404(self, client, seeded_clients):
        r = client.delete(f"/api/app/files/{uuid.uuid4()}")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/app/files/{id}/content  (descarga)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDownloadFile:
    def test_descarga_pdf(self, client, seeded_clients):
        file_id = upload_pdf(client, filename="doc.pdf").json()["id"]
        r = client.get(f"/api/app/files/{file_id}/content")
        assert r.status_code == 200
        assert "application/pdf" in r.headers["content-type"]

    def test_descarga_docx(self, client, seeded_clients):
        file_id = client.post(
            "/api/app/clients/mendoza-asociados/files",
            files=fake_file("contrato.docx"),
        ).json()["id"]
        r = client.get(f"/api/app/files/{file_id}/content")
        assert r.status_code == 200
        assert "wordprocessingml" in r.headers["content-type"]

    def test_descarga_devuelve_contenido_correcto(self, client, seeded_clients):
        contenido = b"este es el contenido real del pdf"
        file_id = client.post(
            "/api/app/clients/mendoza-asociados/files",
            files={"file": ("real.pdf", contenido, "application/octet-stream")},
        ).json()["id"]
        r = client.get(f"/api/app/files/{file_id}/content")
        assert r.content == contenido

    def test_descarga_con_nombre_correcto(self, client, seeded_clients):
        file_id = upload_pdf(client, filename="mi_contrato.pdf").json()["id"]
        r = client.get(f"/api/app/files/{file_id}/content")
        assert "mi_contrato.pdf" in r.headers.get("content-disposition", "")

    def test_carpeta_devuelve_400(self, client, seeded_clients):
        folder_id = make_folder(client).json()["id"]
        r = client.get(f"/api/app/files/{folder_id}/content")
        assert r.status_code == 400

    def test_id_inexistente_devuelve_404(self, client, seeded_clients):
        r = client.get(f"/api/app/files/{uuid.uuid4()}/content")
        assert r.status_code == 404
