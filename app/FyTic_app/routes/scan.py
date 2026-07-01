from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.db import get_db
from app.FyTic_app.auth import AuthUser, require_org
from app.FyTic_app.ai import ai_scan, compute_progress, extract_text_from_bytes, extract_variables

router = APIRouter(tags=["scan"])


@router.post("/scan/process", response_model=dict)
async def process_scan(
    file: UploadFile = File(...),
    user: AuthUser = Depends(require_org),
) -> dict:
    data = await file.read()
    filename = file.filename or "document"
    raw_text = extract_text_from_bytes(filename, data)
    if not raw_text.strip():
        raise HTTPException(422, "Could not extract text from file")
    result = ai_scan(raw_text, filename)
    return {
        "filename": filename,
        "markdown": result.get("markdown", raw_text),
        "analysis": result.get("analysis", {"sections": []}),
    }


@router.get("/search", response_model=dict)
def search(
    q: str = Query(..., min_length=1),
    client_id: str | None = Query(default=None),
    user: AuthUser = Depends(require_org),
) -> dict:
    db = get_db()
    q_lower = q.lower()

    # Search contracts (documents)
    doc_q = (
        db.table("contracts")
        .select("id,title,template_id,client_id,status,created_at,type,variables,signatures,content")
        .eq("org_id", user.org_id)
        .is_("deleted_at", "null")
        .ilike("title", f"%{q}%")
    )
    if client_id:
        doc_q = doc_q.eq("client_id", client_id)
    doc_rows = doc_q.limit(20).execute()

    # Search templates (user-scope)
    tpl_rows = (
        db.table("templates")
        .select("id,name,group_name,source,content,variables,signatories")
        .eq("org_id", user.org_id)
        .is_("deleted_at", "null")
        .ilike("name", f"%{q}%")
        .limit(20)
        .execute()
    )

    # Build client name map for docs
    client_ids = list({r["client_id"] for r in doc_rows.data if r.get("client_id")})
    clients_map: dict = {}
    if client_ids:
        c_rows = db.table("clients").select("id,name,initials,accent_color").in_("id", client_ids).execute()
        clients_map = {c["id"]: c for c in c_rows.data}

    documents = []
    for r in doc_rows.data:
        content = r.get("content") or []
        variables = r.get("variables") or {}
        signatures = r.get("signatures") or {}
        detected = extract_variables(content) if content else list(variables.keys())
        progress = compute_progress(detected, variables, [], signatures)
        c = clients_map.get(r.get("client_id", ""), {})
        documents.append({
            "id": r["id"],
            "templateId": r.get("template_id"),
            "clientId": r.get("client_id"),
            "clientName": c.get("name"),
            "clientInitials": c.get("initials"),
            "clientAccentColor": c.get("accent_color"),
            "title": r.get("title", ""),
            "type": r.get("type", "contract"),
            "status": r.get("status", "draft"),
            "createdAt": r.get("created_at", ""),
            "progress": progress,
        })

    templates = [
        {
            "id": t["id"],
            "name": t.get("name", ""),
            "group": t.get("group_name"),
            "source": t.get("source", "user"),
            "content": t.get("content") or [],
            "signatories": t.get("signatories") or [],
            "detected_variables": t.get("variables") or [],
        }
        for t in tpl_rows.data
    ]

    return {"documents": documents, "templates": templates}
