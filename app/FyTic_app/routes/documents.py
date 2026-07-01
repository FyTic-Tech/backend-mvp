from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.db import get_db
from app.FyTic_app.auth import AuthUser, require_admin, require_org, require_write
from app.FyTic_app.models import (
    CopyAsTemplateRequest, DocumentCreate, DocumentDetailResponse, DocumentFull,
    DocumentListItem, DocumentPatch, ShareRequest, SignaturePost, TemplateInfo,
    VariablesPatch,
)
from app.FyTic_app.ai import (
    ai_analyze, ai_summarize, compute_progress, export_docx, export_pdf,
    extract_variables, render_content,
)

router = APIRouter(tags=["documents"])


def _build_list_item(row: dict, clients_map: dict | None = None) -> DocumentListItem:
    variables: dict = row.get("variables") or {}
    signatures: dict = row.get("signatures") or {}
    content: list = row.get("content") or []
    detected = extract_variables(content) if content else list(variables.keys())
    signatories: list = []
    if row.get("template_id") and not content:
        pass
    progress = compute_progress(detected, variables, signatories, signatures)
    client_name: str | None = None
    client_initials: str | None = None
    client_color: str | None = None
    if clients_map and row.get("client_id"):
        c = clients_map.get(row["client_id"])
        if c:
            client_name = c.get("name")
            client_initials = c.get("initials")
            client_color = c.get("accent_color", "#6366f1")
    return DocumentListItem(
        id=row["id"],
        templateId=row.get("template_id"),
        clientId=row.get("client_id"),
        clientName=client_name,
        clientInitials=client_initials,
        clientAccentColor=client_color,
        title=row.get("title", ""),
        type=row.get("type", "contract"),
        status=row.get("status", "draft"),
        createdAt=row.get("created_at", ""),
        progress=progress,
    )


def _get_doc_or_404(db, doc_id: str, org_id: str, user_id: str | None = None) -> dict:
    q = (
        db.table("contracts")
        .select("*")
        .eq("id", doc_id)
        .eq("org_id", org_id)
        .is_("deleted_at", "null")
    )
    result = q.execute()
    if not result.data:
        raise HTTPException(404, "Document not found")
    row = result.data[0]
    # Enforce user-private doc access when user_id is provided
    if user_id and row.get("owner_scope") == "user" and row.get("created_by") != user_id:
        raise HTTPException(404, "Document not found")
    return row


@router.get("/documents", response_model=dict)
def list_documents(
    client_id: str | None = None,
    status: str | None = None,
    type: str | None = None,
    search: str | None = None,
    user: AuthUser = Depends(require_org),
) -> dict:
    db = get_db()

    def _build_q(scope: str):
        q = (
            db.table("contracts")
            .select("*")
            .eq("org_id", user.org_id)
            .eq("owner_scope", scope)
            .is_("deleted_at", "null")
        )
        if scope == "user":
            q = q.eq("created_by", user.user_id)
        if client_id:
            q = q.eq("client_id", client_id)
        if status:
            q = q.eq("status", status)
        if type:
            q = q.eq("type", type)
        return q.order("created_at", desc=True)

    org_rows = _build_q("org").execute()
    user_rows = _build_q("user").execute()
    all_data = (org_rows.data or []) + (user_rows.data or [])
    all_data.sort(key=lambda r: r.get("created_at", ""), reverse=True)

    # Build a clients lookup map for enrichment
    client_ids = list({r["client_id"] for r in all_data if r.get("client_id")})
    clients_map: dict = {}
    if client_ids:
        c_rows = (
            db.table("clients")
            .select("id,name,initials,accent_color")
            .in_("id", client_ids)
            .execute()
        )
        clients_map = {c["id"]: c for c in c_rows.data}

    documents = [_build_list_item(r, clients_map) for r in all_data]
    if search:
        q_lower = search.lower()
        documents = [
            d for d in documents
            if q_lower in d.title.lower()
            or (d.clientName and q_lower in d.clientName.lower())
        ]
    return {"documents": [d.model_dump() for d in documents], "total": len(documents)}


@router.post("/documents", status_code=201, response_model=dict)
def create_document(body: DocumentCreate, user: AuthUser = Depends(require_write)) -> dict:
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    content: list = []
    detected_vars: list = []
    template_data: dict | None = None

    if body.templateId:
        t = db.table("templates").select("*").eq("id", body.templateId).execute()
        if not t.data:
            raise HTTPException(404, "Template not found")
        template_data = t.data[0]
        content = template_data.get("content") or []
        detected_vars = template_data.get("variables") or extract_variables(content)

    # Initialize variables map from detected vars (all empty)
    variables = {v: body.variables.get(v, "") for v in detected_vars}
    variables.update(body.variables)

    record = {
        "org_id": user.org_id,
        "client_id": body.clientId,
        "template_id": body.templateId,
        "created_by": user.user_id,
        "owner_scope": "org",
        "title": body.title,
        "status": "draft",
        "type": body.type,
        "variables": variables,
        "signatures": {},
        "content": content,
        "created_at": now,
    }
    result = db.table("contracts").insert(record).select().execute()
    if not result.data:
        raise HTTPException(500, "Insert failed")
    row = result.data[0]
    return {"document": _build_list_item(row).model_dump()}


@router.get("/documents/{doc_id}", response_model=dict)
def get_document(doc_id: str, user: AuthUser = Depends(require_org)) -> dict:
    db = get_db()
    row = _get_doc_or_404(db, doc_id, user.org_id, user.user_id)
    template_info: TemplateInfo | None = None
    signatories: list = []
    if row.get("template_id"):
        t = db.table("templates").select("*").eq("id", row["template_id"]).execute()
        if t.data:
            td = t.data[0]
            signatories = td.get("signatories") or []
            template_info = TemplateInfo(
                id=td["id"],
                name=td.get("name", ""),
                signatories=signatories,
                raw_content=td.get("content") or [],
            )

    content = row.get("content") or (template_info.raw_content if template_info else [])
    variables = row.get("variables") or {}
    signatures = row.get("signatures") or {}
    detected = extract_variables(content)
    rendered = render_content(content, variables)
    progress = compute_progress(detected, variables, signatories, signatures)

    # Enrich with client name
    client_name: str | None = None
    if row.get("client_id"):
        c = db.table("clients").select("name").eq("id", row["client_id"]).execute()
        if c.data:
            client_name = c.data[0]["name"]

    doc_full = DocumentFull(
        id=row["id"],
        templateId=row.get("template_id"),
        clientId=row.get("client_id"),
        clientName=client_name,
        title=row.get("title", ""),
        type=row.get("type", "contract"),
        status=row.get("status", "draft"),
        createdAt=row.get("created_at", ""),
        variables=variables,
        signatures=signatures,
    )
    return {
        "document": doc_full.model_dump(),
        "template": template_info.model_dump() if template_info else None,
        "rendered_content": rendered,
        "progress": progress,
    }


@router.patch("/documents/{doc_id}", response_model=dict)
def update_document(
    doc_id: str, body: DocumentPatch, user: AuthUser = Depends(require_write)
) -> dict:
    db = get_db()
    _get_doc_or_404(db, doc_id, user.org_id, user.user_id)
    updates: dict = {}
    if body.title is not None:
        updates["title"] = body.title
    if body.status is not None:
        updates["status"] = body.status
    if body.client_id is not None:
        updates["client_id"] = body.client_id
    if body.doc_type is not None:
        updates["type"] = body.doc_type
    if updates:
        db.table("contracts").update(updates).eq("id", doc_id).execute()
    row = db.table("contracts").select("*").eq("id", doc_id).execute().data[0]
    return {"document": _build_list_item(row).model_dump()}


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: str, user: AuthUser = Depends(require_admin)) -> None:
    db = get_db()
    _get_doc_or_404(db, doc_id, user.org_id, user.user_id)
    db.table("contracts").update({"deleted_at": datetime.now(timezone.utc).isoformat()}).eq("id", doc_id).execute()


@router.patch("/documents/{doc_id}/variables", response_model=dict)
def update_variables(
    doc_id: str, body: VariablesPatch, user: AuthUser = Depends(require_write)
) -> dict:
    db = get_db()
    row = _get_doc_or_404(db, doc_id, user.org_id, user.user_id)
    current_vars: dict = row.get("variables") or {}
    current_vars.update(body.variables)
    db.table("contracts").update({"variables": current_vars}).eq("id", doc_id).execute()
    content = row.get("content") or []
    signatures = row.get("signatures") or {}
    signatories: list = []
    if row.get("template_id"):
        t = db.table("templates").select("signatories,variables").eq("id", row["template_id"]).execute()
        if t.data:
            signatories = t.data[0].get("signatories") or []
    detected = extract_variables(content) if content else list(current_vars.keys())
    progress = compute_progress(detected, current_vars, signatories, signatures)
    return {"variables": current_vars, "progress": progress}


@router.post("/documents/{doc_id}/signatures", response_model=dict)
def add_signature(
    doc_id: str, body: SignaturePost, user: AuthUser = Depends(require_write)
) -> dict:
    db = get_db()
    row = _get_doc_or_404(db, doc_id, user.org_id, user.user_id)
    sigs: dict = row.get("signatures") or {}
    sigs[body.signatory_key] = body.signature_data
    db.table("contracts").update({"signatures": sigs}).eq("id", doc_id).execute()
    return {"signatures": sigs}


@router.delete("/documents/{doc_id}/signatures/{key}", response_model=dict)
def delete_signature(
    doc_id: str, key: str, user: AuthUser = Depends(require_write)
) -> dict:
    db = get_db()
    row = _get_doc_or_404(db, doc_id, user.org_id, user.user_id)
    sigs: dict = row.get("signatures") or {}
    sigs.pop(key, None)
    db.table("contracts").update({"signatures": sigs}).eq("id", doc_id).execute()
    return {"signatures": sigs}


@router.post("/documents/{doc_id}/summarize", response_model=dict)
def summarize_document(doc_id: str, user: AuthUser = Depends(require_org)) -> dict:
    db = get_db()
    row = _get_doc_or_404(db, doc_id, user.org_id, user.user_id)
    content = row.get("content") or []
    variables = row.get("variables") or {}
    rendered = render_content(content, variables)
    return ai_summarize(rendered)


@router.post("/documents/{doc_id}/analyze", response_model=dict)
def analyze_document(doc_id: str, user: AuthUser = Depends(require_org)) -> dict:
    db = get_db()
    row = _get_doc_or_404(db, doc_id, user.org_id, user.user_id)
    content = row.get("content") or []
    variables = row.get("variables") or {}
    rendered = render_content(content, variables)
    return ai_analyze(rendered)


@router.post("/documents/{doc_id}/share")
def share_document(
    doc_id: str, body: ShareRequest, user: AuthUser = Depends(require_org)
):
    db = get_db()
    row = _get_doc_or_404(db, doc_id, user.org_id, user.user_id)
    content = row.get("content") or []
    variables = row.get("variables") or {}
    rendered = render_content(content, variables)
    title = row.get("title", "Documento")
    method = body.method

    if method == "md":
        return {"method": "md", "content": "\n\n".join(rendered)}
    if method == "link":
        link = f"https://app.fytic.tech/documents/{doc_id}/view"
        return {"method": "link", "url": link}
    if method == "docx":
        data = export_docx(title, rendered)
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{title}.docx"'},
        )
    if method == "pdf":
        data = export_pdf(title, rendered)
        return Response(
            content=data,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{title}.pdf"'},
        )
    if method == "email":
        if not body.email:
            raise HTTPException(400, "email required for method=email")
        # Resend integration pending; log intent for now
        return {"method": "email", "recipient": body.email}
    raise HTTPException(400, f"Unknown method: {method}")


@router.post("/documents/{doc_id}/copy-as-template", response_model=dict)
def copy_as_template(
    doc_id: str, body: CopyAsTemplateRequest, user: AuthUser = Depends(require_write)
) -> dict:
    db = get_db()
    row = _get_doc_or_404(db, doc_id, user.org_id, user.user_id)
    now = datetime.now(timezone.utc).isoformat()
    content = row.get("content") or []
    detected = extract_variables(content)
    record = {
        "org_id": user.org_id,
        "source": "user",
        "source_contract_id": doc_id,
        "name": body.name,
        "group_name": body.group or "",
        "content": content,
        "variables": detected,
        "signatories": [],
        "is_active": True,
        "created_by": user.user_id,
        "created_at": now,
    }
    result = db.table("templates").insert(record).select().execute()
    if not result.data:
        raise HTTPException(500, "Insert failed")
    t = result.data[0]
    return {
        "template": {
            "id": t["id"],
            "name": t["name"],
            "group": t.get("group_name"),
            "source": "user",
            "content": content,
            "signatories": [],
            "detected_variables": detected,
        }
    }
