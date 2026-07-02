from __future__ import annotations

from pydantic import BaseModel


# ─── Me ──────────────────────────────────────────────────────────────────────

class MeResponse(BaseModel):
    id: str
    email: str
    fullName: str | None = None
    firmName: str | None = None
    teamSize: str | None = None
    organization: str | None = None
    role: str
    position: str | None = None
    practiceArea: str | None = None
    phone: str | None = None
    loginMethod: str | None = None
    dateCreated: str
    referralCode: str | None = None
    referredBy: str | None = None
    surveyCompleted: bool = False
    tokensUsed: int = 0
    tokenLimit: int | None = None


class MePatch(BaseModel):
    fullName: str | None = None
    firmName: str | None = None
    teamSize: str | None = None
    position: str | None = None
    practiceArea: str | None = None
    phone: str | None = None


# ─── Clients ─────────────────────────────────────────────────────────────────

class ClientListItem(BaseModel):
    id: str
    name: str
    rfc: str | None = None
    initials: str | None = None
    accentColor: str = "#6366f1"
    email: str | None = None
    contact: str | None = None
    caseDescription: str | None = None
    document_count: int = 0


class ClientDetail(ClientListItem):
    address: str | None = None
    tags: list[str] = []
    documents: list[DocumentListItem] = []


class ClientCreate(BaseModel):
    name: str
    rfc: str | None = None
    address: str | None = None
    contact: str | None = None
    email: str | None = None
    initials: str | None = None
    accentColor: str = "#6366f1"
    caseDescription: str | None = None
    tags: list[str] = []


class ClientPatch(BaseModel):
    name: str | None = None
    rfc: str | None = None
    address: str | None = None
    contact: str | None = None
    email: str | None = None
    initials: str | None = None
    accentColor: str | None = None
    caseDescription: str | None = None
    tags: list[str] | None = None


# ─── Documents (contracts table) ─────────────────────────────────────────────

class DocumentProgress(BaseModel):
    total_vars: int
    filled_vars: int
    percent: int
    missing: list[str]
    total_sigs: int
    filled_sigs: int


class DocumentListItem(BaseModel):
    id: str
    templateId: str | None = None
    clientId: str | None = None
    clientName: str | None = None
    clientInitials: str | None = None
    clientAccentColor: str | None = None
    title: str
    type: str = "contract"
    status: str = "draft"
    createdAt: str
    progress: DocumentProgress


class DocumentFull(BaseModel):
    id: str
    templateId: str | None = None
    clientId: str | None = None
    clientName: str | None = None
    title: str
    type: str
    status: str
    createdAt: str
    variables: dict = {}
    signatures: dict = {}


class TemplateInfo(BaseModel):
    id: str
    name: str
    signatories: list[Signatory] = []
    raw_content: list[str] = []


class DocumentDetailResponse(BaseModel):
    document: DocumentFull
    template: TemplateInfo | None = None
    rendered_content: list[str] = []
    progress: DocumentProgress


class DocumentCreate(BaseModel):
    clientId: str | None = None
    templateId: str | None = None
    title: str
    type: str = "contract"
    variables: dict = {}


class DocumentPatch(BaseModel):
    title: str | None = None
    status: str | None = None
    client_id: str | None = None
    doc_type: str | None = None


class VariablesPatch(BaseModel):
    variables: dict[str, str]


class SignaturePost(BaseModel):
    signatory_key: str
    signature_data: str


class ShareRequest(BaseModel):
    method: str
    email: str | None = None
    message: str | None = None


class CopyAsTemplateRequest(BaseModel):
    name: str
    group: str | None = None


# ─── Templates ───────────────────────────────────────────────────────────────

class Signatory(BaseModel):
    key: str
    label: str
    nameVar: str | None = None


class FyticTemplate(BaseModel):
    id: str
    name: str
    signatories: list[Signatory] = []
    content: list[str] = []
    group: str | None = None
    source: str = "fytic"


class UserTemplate(BaseModel):
    id: str
    name: str
    group: str | None = None
    content: list[str] = []
    signatories: list[Signatory] = []
    detected_variables: list[str] = []
    source: str = "user"


class TemplateImportResult(UserTemplate):
    suggested_name: str | None = None
    risk_clauses: list[str] = []


class TemplatePatch(BaseModel):
    name: str | None = None
    group: str | None = None


class TemplateGroupCreate(BaseModel):
    name: str


class TemplateGroupRename(BaseModel):
    new_name: str


# ─── Org members ─────────────────────────────────────────────────────────────

class OrgMember(BaseModel):
    id: str
    orgId: str | None = None
    email: str
    fullName: str | None = None
    role: str
    position: str | None = None
    status: str
    avatarInitials: str | None = None
    createdAt: str
    updatedAt: str | None = None


class MemberInvite(BaseModel):
    email: str
    full_name: str | None = None
    role: str = "member"
    position: str | None = None


class MemberPatch(BaseModel):
    full_name: str | None = None
    role: str | None = None
    position: str | None = None
    status: str | None = None


# ─── Org items / sections ────────────────────────────────────────────────────

class OrgItem(BaseModel):
    id: str
    parentId: str
    sectionId: str = "general"
    kind: str
    name: str
    icon: str | None = None
    color: str | None = None
    rfc: str | None = None
    createdAt: str


class OrgItemCreate(BaseModel):
    parentId: str = "root"
    sectionId: str | None = None
    kind: str
    name: str
    icon: str | None = None
    color: str | None = None
    rfc: str | None = None


class OrgItemPatch(BaseModel):
    name: str | None = None
    sectionId: str | None = None
    color: str | None = None
    parentId: str | None = None


class OrgSection(BaseModel):
    id: str
    parentId: str = "root"
    name: str
    isDefault: bool = False


class OrgSectionCreate(BaseModel):
    parentId: str = "root"
    name: str


class OrgSectionPatch(BaseModel):
    name: str


# ─── Library ─────────────────────────────────────────────────────────────────

class LibraryItem(BaseModel):
    id: str
    parentId: str
    sectionId: str = "general"
    kind: str
    name: str
    fileType: str | None = None
    size: int | None = None
    downloadUrl: str | None = None
    createdAt: str


class LibraryItemCreate(BaseModel):
    parentId: str = "root"
    sectionId: str | None = None
    name: str


class LibraryItemPatch(BaseModel):
    name: str | None = None
    sectionId: str | None = None
    parentId: str | None = None


class LibrarySection(BaseModel):
    id: str
    parentId: str = "root"
    name: str
    isDefault: bool = False


class LibrarySectionCreate(BaseModel):
    parentId: str = "root"
    name: str


class LibrarySectionPatch(BaseModel):
    name: str


# ─── Law DB ──────────────────────────────────────────────────────────────────

class LawDoc(BaseModel):
    id: str
    name: str
    scope: str
    state: str | None = None
    year: int | None = None
    vigente: bool = True
    hasNewReforms: bool = False
    url: str | None = None
    pdfLink: str | None = None
    otherLink: str | None = None
    publishDate: str | None = None
    lastUpdate: str | None = None


class LawGroup(BaseModel):
    name: str
    docs: list[LawDoc]


# ─── Scan / Search ───────────────────────────────────────────────────────────

class AnalysisSection(BaseModel):
    type: str
    title: str
    items: list[str]


class ScanResult(BaseModel):
    filename: str
    markdown: str
    analysis: dict


class SummarizeResult(BaseModel):
    summary: str
    key_points: list[str]
    word_count: int


class AnalyzeResult(BaseModel):
    sections: list[AnalysisSection]


# Fix forward refs
ClientDetail.model_rebuild()
DocumentDetailResponse.model_rebuild()
TemplateInfo.model_rebuild()
