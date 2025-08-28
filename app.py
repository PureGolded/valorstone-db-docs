from __future__ import annotations
from flask import Flask, render_template, request, redirect, url_for, make_response, jsonify, abort
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple
import json
import os
import uuid
import time
import re

# -----------------------------
# Models
# -----------------------------

def gen_id() -> str:
    return uuid.uuid4().hex[:8]

@dataclass
class Link:
    id: str
    from_type: str  # 'table' | 'column'
    from_id: str
    to_type: str
    to_id: str
    note: str = ""

@dataclass
class ForeignRef:
    table_id: str
    column_id: str
    note: str = ""

@dataclass
class Column:
    id: str
    name: str
    datatype: str = "TEXT"
    is_primary: bool = False
    is_nullable: bool = True
    default: Optional[str] = None
    note: str = ""
    foreign_ref: Optional[ForeignRef] = None
    order: int = 0

@dataclass
class Table:
    id: str
    name: str
    note: str = ""
    columns: Dict[str, Column] = field(default_factory=dict)

@dataclass
class Database:
    id: str
    name: str
    note: str = ""
    tables: Dict[str, Table] = field(default_factory=dict)
    links: Dict[str, Link] = field(default_factory=dict)
    diagram: dict = field(default_factory=dict)

# -----------------------------
# Documents & Sharing
# -----------------------------

@dataclass
class DocNote:
    id: str
    start_line: int
    end_line: int
    text: str
    author: str = ""
    created_at: float = field(default_factory=lambda: time.time())

@dataclass
class Document:
    id: str
    name: str
    parent_id: Optional[str] = None  # folder id
    content: str = ""
    notes: Dict[str, DocNote] = field(default_factory=dict)
    updated_at: float = field(default_factory=lambda: time.time())

@dataclass
class DocFolder:
    id: str
    name: str
    parent_id: Optional[str] = None

@dataclass
class DocShare:
    id: str  # token
    pin: str
    kind: str  # 'doc' | 'folder'
    target_id: str  # doc_id or folder_id
    created_at: float = field(default_factory=lambda: time.time())

# -----------------------------
# Storage layer (per PIN)
# -----------------------------

DATA_DIR = os.path.join(os.path.dirname(__file__), ".pin_data")
PIN_COOKIE = "vibe_pin"
SHARES_PATH = os.path.join(DATA_DIR, "shares.json")

os.makedirs(DATA_DIR, exist_ok=True)


def pin_path(pin: str) -> str:
    return os.path.join(DATA_DIR, f"{pin}.json")


def load_state(pin: str) -> Dict[str, Database]:
    path = pin_path(pin)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            dbs: Dict[str, Database] = {}
            for db_id, db_data in raw.items():
                # skip non-database keys
                if db_id in ("documents", "doc_folders"):
                    continue
                if not isinstance(db_data, dict) or "id" not in db_data or "name" not in db_data or "tables" not in db_data:
                    continue
                tables = {}
                for t_id, t in db_data.get("tables", {}).items():
                    cols: Dict[str, Column] = {}
                    idx = 0
                    for c_id, c in t.get("columns", {}).items():
                        fr = None
                        if isinstance(c.get("foreign_ref"), dict):
                            try:
                                fr = ForeignRef(**c["foreign_ref"])
                            except Exception:
                                fr = None
                        col = Column(
                            id=c["id"],
                            name=c["name"],
                            datatype=c.get("datatype", "TEXT"),
                            is_primary=bool(c.get("is_primary", False)),
                            is_nullable=bool(c.get("is_nullable", True)),
                            default=c.get("default"),
                            note=c.get("note", ""),
                            foreign_ref=fr,
                            order=int(c.get("order", idx)),
                        )
                        cols[c_id] = col
                        idx += 1
                    tables[t_id] = Table(id=t["id"], name=t["name"], note=t.get("note", ""), columns=cols)
                links = {l_id: Link(**l) for l_id, l in db_data.get("links", {}).items()}
                diagram = db_data.get("diagram", {}) or {}
                dbs[db_id] = Database(id=db_data["id"], name=db_data["name"], note=db_data.get("note", ""), tables=tables, links=links, diagram=diagram)
            return dbs
        except Exception:
            return {}
    return {}


def save_state(pin: str, dbs: Dict[str, Database]) -> None:
    path = pin_path(pin)
    # preserve documents and folders
    preserved_docs = {}
    preserved_folders = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
                preserved_docs = raw.get("documents", {}) or {}
                preserved_folders = raw.get("doc_folders", {}) or {}
        except Exception:
            preserved_docs, preserved_folders = {}, {}
    serializable = {}
    for db_id, db in dbs.items():
        serializable[db_id] = {
            "id": db.id,
            "name": db.name,
            "note": db.note,
            "tables": {
                t_id: {
                    "id": t.id,
                    "name": t.name,
                    "note": t.note,
                    "columns": {c_id: asdict(c) for c_id, c in t.columns.items()},
                }
                for t_id, t in db.tables.items()
            },
            "links": {l_id: asdict(l) for l_id, l in db.links.items()},
            "diagram": db.diagram,
        }
    if preserved_folders:
        serializable["doc_folders"] = preserved_folders
    if preserved_docs:
        serializable["documents"] = preserved_docs
    with open(path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2)


def load_docs(pin: str) -> Tuple[Dict[str, DocFolder], Dict[str, Document]]:
    path = pin_path(pin)
    if not os.path.exists(path):
        return {}, {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        folders: Dict[str, DocFolder] = {}
        documents: Dict[str, Document] = {}
        for fid, fdata in raw.get("doc_folders", {}).items():
            folders[fid] = DocFolder(id=fdata["id"], name=fdata["name"], parent_id=fdata.get("parent_id"))
        for did, ddata in raw.get("documents", {}).items():
            notes: Dict[str, DocNote] = {}
            for nid, ndata in ddata.get("notes", {}).items():
                try:
                    notes[nid] = DocNote(
                        id=ndata["id"],
                        start_line=int(ndata.get("start_line", 1)),
                        end_line=int(ndata.get("end_line", ndata.get("start_line", 1))),
                        text=ndata.get("text", ""),
                        author=ndata.get("author", ""),
                        created_at=float(ndata.get("created_at", time.time())),
                    )
                except Exception:
                    continue
            documents[did] = Document(
                id=ddata["id"],
                name=ddata["name"],
                parent_id=ddata.get("parent_id"),
                content=ddata.get("content", ""),
                notes=notes,
                updated_at=float(ddata.get("updated_at", time.time())),
            )
        return folders, documents
    except Exception:
        return {}, {}


def save_docs(pin: str, folders: Dict[str, DocFolder], documents: Dict[str, Document]) -> None:
    path = pin_path(pin)
    raw = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            raw = {}
    raw["doc_folders"] = {fid: asdict(f) for fid, f in folders.items()}
    raw["documents"] = {did: {
        "id": d.id,
        "name": d.name,
        "parent_id": d.parent_id,
        "content": d.content,
        "notes": {nid: asdict(n) for nid, n in d.notes.items()},
        "updated_at": d.updated_at,
    } for did, d in documents.items()}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)


def load_shares() -> Dict[str, DocShare]:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(SHARES_PATH):
        return {}
    try:
        with open(SHARES_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        shares: Dict[str, DocShare] = {}
        for token, s in raw.items():
            shares[token] = DocShare(id=s["id"], pin=s["pin"], kind=s["kind"], target_id=s["target_id"], created_at=s.get("created_at", time.time()))
        return shares
    except Exception:
        return {}


def save_shares(shares: Dict[str, DocShare]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    serializable = {token: asdict(s) for token, s in shares.items()}
    with open(SHARES_PATH, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2)


def slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9\-_.]", "", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")

# -----------------------------
# Flask app
# -----------------------------

app = Flask(__name__)


def get_pin() -> Optional[str]:
    return request.cookies.get(PIN_COOKIE)


def get_state_or_init(pin: str) -> Dict[str, Database]:
    return load_state(pin)


@app.route("/", methods=["GET", "POST"])
def index():
    pin = get_pin()
    if request.method == "POST":
        pin = request.form.get("pin", "").strip()
        if not pin:
            abort(400, "PIN required")
        resp = make_response(redirect(url_for("workspace")))
        resp.set_cookie(PIN_COOKIE, pin, max_age=60 * 60 * 24 * 7)  # 7 days
        return resp

    return render_template("index.html", pin=pin)


@app.route("/workspace")
def workspace():
    pin = get_pin()
    if not pin:
        return redirect(url_for("index"))
    dbs = get_state_or_init(pin)
    folders, documents = load_docs(pin)
    return render_template("workspace.html", pin=pin, dbs=dbs, folders=folders, documents=documents)

# --------- Databases ----------

@app.post("/api/databases")
def create_database():
    pin = get_pin()
    if not pin:
        abort(401)
    dbs = get_state_or_init(pin)
    name = request.json.get("name", "New Database").strip() or "New Database"
    db_id = gen_id()
    dbs[db_id] = Database(id=db_id, name=name)
    save_state(pin, dbs)
    return jsonify({"ok": True, "database": asdict(dbs[db_id])})


@app.delete("/api/databases/<db_id>")
def delete_database(db_id: str):
    pin = get_pin()
    if not pin:
        abort(401)
    dbs = get_state_or_init(pin)
    if db_id in dbs:
        dbs.pop(db_id)
        save_state(pin, dbs)
        return jsonify({"ok": True})
    abort(404)


@app.patch("/api/databases/<db_id>")
def update_database(db_id: str):
    pin = get_pin()
    if not pin:
        abort(401)
    dbs = get_state_or_init(pin)
    db = dbs.get(db_id)
    if not db:
        abort(404)
    data = request.json or {}
    if "name" in data:
        db.name = data["name"].strip() or db.name
    if "note" in data:
        db.note = data["note"]
    if "diagram" in data and isinstance(data["diagram"], dict):
        # Minimal sanitation: ensure it's a dict of simple types
        db.diagram = data["diagram"]
    save_state(pin, dbs)
    return jsonify({"ok": True, "database": asdict(db)})

# --------- Docs: Browse Pages ---------

@app.get("/docs")
def docs_home():
    pin = get_pin()
    if not pin:
        return redirect(url_for("index"))
    folders, documents = load_docs(pin)
    return render_template("docs.html", pin=pin, folders=folders, documents=documents, current_folder=None, share=None, can_edit=True, is_shared=False)


@app.get("/docs/f/<folder_id>")
def docs_folder(folder_id: str):
    pin = get_pin()
    if not pin:
        return redirect(url_for("index"))
    folders, documents = load_docs(pin)
    if folder_id not in folders:
        abort(404)
    return render_template("docs.html", pin=pin, folders=folders, documents=documents, current_folder=folder_id, share=None, can_edit=True, is_shared=False)


@app.get("/docs/d/<doc_id>")
def docs_doc_editor(doc_id: str):
    pin = get_pin()
    if not pin:
        return redirect(url_for("index"))
    folders, documents = load_docs(pin)
    doc = documents.get(doc_id)
    if not doc:
        abort(404)
    # editor mode
    return render_template("document.html", doc=doc, folders=folders, can_edit=True, share=None, is_shared=False)

# --------- Docs: API CRUD ---------

@app.post("/api/docs/folders")
def api_create_folder():
    pin = get_pin()
    if not pin:
        abort(401)
    folders, documents = load_docs(pin)
    data = request.json or {}
    name = (data.get("name") or "New Folder").strip() or "New Folder"
    parent_id = data.get("parent_id") or None
    if parent_id and parent_id not in folders:
        abort(400)
    fid = gen_id()
    folders[fid] = DocFolder(id=fid, name=name, parent_id=parent_id)
    save_docs(pin, folders, documents)
    return jsonify({"ok": True, "folder": asdict(folders[fid])})


@app.patch("/api/docs/folders/<fid>")
def api_update_folder(fid: str):
    pin = get_pin()
    if not pin:
        abort(401)
    folders, documents = load_docs(pin)
    f = folders.get(fid)
    if not f:
        abort(404)
    data = request.json or {}
    if "name" in data:
        f.name = data["name"].strip() or f.name
    if "parent_id" in data:
        pid = data.get("parent_id")
        if pid and pid not in folders:
            abort(400)
        f.parent_id = pid
    save_docs(pin, folders, documents)
    return jsonify({"ok": True, "folder": asdict(f)})


@app.delete("/api/docs/folders/<fid>")
def api_delete_folder(fid: str):
    pin = get_pin()
    if not pin:
        abort(401)
    folders, documents = load_docs(pin)
    if fid not in folders:
        abort(404)
    # prevent delete if contains items
    if any(d.parent_id == fid for d in documents.values()) or any(f.parent_id == fid for f in folders.values() if f.id != fid):
        abort(400, "Folder not empty")
    folders.pop(fid)
    save_docs(pin, folders, documents)
    return jsonify({"ok": True})


@app.post("/api/docs")
def api_create_doc():
    pin = get_pin()
    if not pin:
        abort(401)
    folders, documents = load_docs(pin)
    data = request.json or {}
    name = (data.get("name") or "Untitled").strip() or "Untitled"
    parent_id = data.get("parent_id") or None
    if parent_id and parent_id not in folders:
        abort(400)
    did = gen_id()
    content = data.get("content") or f"# {name}\n\nStart writing...\n"
    documents[did] = Document(id=did, name=name, parent_id=parent_id, content=content)
    save_docs(pin, folders, documents)
    return jsonify({"ok": True, "document": asdict(documents[did])})


@app.get("/api/docs/<doc_id>")
def api_get_doc(doc_id: str):
    pin = get_pin()
    if not pin:
        abort(401)
    folders, documents = load_docs(pin)
    d = documents.get(doc_id)
    if not d:
        abort(404)
    return jsonify({"ok": True, "document": asdict(d)})


@app.patch("/api/docs/<doc_id>")
def api_update_doc(doc_id: str):
    pin = get_pin()
    if not pin:
        abort(401)
    folders, documents = load_docs(pin)
    d = documents.get(doc_id)
    if not d:
        abort(404)
    data = request.json or {}
    touched = False
    if "name" in data:
        d.name = data["name"].strip() or d.name
        touched = True
    if "parent_id" in data:
        pid = data.get("parent_id")
        if pid and pid not in folders:
            abort(400)
        d.parent_id = pid
        touched = True
    if "content" in data:
        d.content = data["content"]
        touched = True
    if touched:
        d.updated_at = time.time()
    save_docs(pin, folders, documents)
    return jsonify({"ok": True, "document": asdict(d)})


@app.delete("/api/docs/<doc_id>")
def api_delete_doc(doc_id: str):
    pin = get_pin()
    if not pin:
        abort(401)
    folders, documents = load_docs(pin)
    if doc_id not in documents:
        abort(404)
    documents.pop(doc_id)
    save_docs(pin, folders, documents)
    return jsonify({"ok": True})


@app.get("/api/docs/<doc_id>/notes")
def api_get_notes(doc_id: str):
    pin = get_pin()
    if not pin:
        abort(401)
    folders, documents = load_docs(pin)
    d = documents.get(doc_id)
    if not d:
        abort(404)
    return jsonify({"ok": True, "notes": {nid: asdict(n) for nid, n in d.notes.items()}})


@app.post("/api/docs/<doc_id>/notes")
def api_add_note(doc_id: str):
    pin = get_pin()
    if not pin:
        abort(401)
    folders, documents = load_docs(pin)
    d = documents.get(doc_id)
    if not d:
        abort(404)
    data = request.json or {}
    try:
        start_line = int(data.get("start_line", 1))
        end_line = int(data.get("end_line", start_line))
    except Exception:
        abort(400)
    text = (data.get("text") or "").strip()
    if not text:
        abort(400)
    author = (data.get("author") or "").strip()
    nid = gen_id()
    d.notes[nid] = DocNote(id=nid, start_line=start_line, end_line=end_line, text=text, author=author)
    d.updated_at = time.time()
    save_docs(pin, folders, documents)
    return jsonify({"ok": True, "note": asdict(d.notes[nid])})


@app.delete("/api/docs/<doc_id>/notes/<nid>")
def api_delete_note(doc_id: str, nid: str):
    pin = get_pin()
    if not pin:
        abort(401)
    folders, documents = load_docs(pin)
    d = documents.get(doc_id)
    if not d:
        abort(404)
    if nid in d.notes:
        d.notes.pop(nid)
        d.updated_at = time.time()
        save_docs(pin, folders, documents)
        return jsonify({"ok": True})
    abort(404)


# --------- Sharing ---------

@app.post("/api/docs/<doc_id>/share")
def api_share_doc(doc_id: str):
    pin = get_pin()
    if not pin:
        abort(401)
    folders, documents = load_docs(pin)
    if doc_id not in documents:
        abort(404)
    shares = load_shares()
    token = gen_id()
    shares[token] = DocShare(id=token, pin=pin, kind='doc', target_id=doc_id)
    save_shares(shares)
    return jsonify({"ok": True, "token": token, "url": url_for('shared_doc', token=token, _external=True)})


@app.post("/api/docs/folders/<fid>/share")
def api_share_folder(fid: str):
    pin = get_pin()
    if not pin:
        abort(401)
    folders, documents = load_docs(pin)
    if fid not in folders:
        abort(404)
    shares = load_shares()
    token = gen_id()
    shares[token] = DocShare(id=token, pin=pin, kind='folder', target_id=fid)
    save_shares(shares)
    return jsonify({"ok": True, "token": token, "url": url_for('shared_folder', token=token, _external=True)})


def _shared_context(token: str) -> Tuple[DocShare, Dict[str, DocFolder], Dict[str, Document]]:
    shares = load_shares()
    s = shares.get(token)
    if not s:
        abort(404)
    folders, documents = load_docs(s.pin)
    return s, folders, documents


@app.get("/s/d/<token>")
def shared_doc(token: str):
    s, folders, documents = _shared_context(token)
    if s.kind != 'doc':
        abort(404)
    doc = documents.get(s.target_id)
    if not doc:
        abort(404)
    # read-only unless cookie matches pin
    can_edit = (get_pin() == s.pin)
    return render_template("document.html", doc=doc, folders=folders, can_edit=can_edit, share=asdict(s), is_shared=True)


@app.get("/s/f/<token>")
def shared_folder(token: str):
    s, folders, documents = _shared_context(token)
    if s.kind != 'folder':
        abort(404)
    root = folders.get(s.target_id)
    if not root:
        abort(404)
    can_edit = (get_pin() == s.pin)
    return render_template("docs.html", pin=None, folders=folders, documents=documents, current_folder=root.id, share=asdict(s), can_edit=can_edit, is_shared=True)


@app.get("/s/f/<token>/d/<doc_id>")
def shared_folder_doc(token: str, doc_id: str):
    s, folders, documents = _shared_context(token)
    if s.kind != 'folder':
        abort(404)
    doc = documents.get(doc_id)
    if not doc:
        abort(404)
    # ensure doc is within subtree of shared folder
    subtree = set()
    root = s.target_id
    pending = [root]
    while pending:
        x = pending.pop()
        subtree.add(x)
        for fid, f in folders.items():
            if f.parent_id == x and fid not in subtree:
                pending.append(fid)
    if doc.parent_id not in subtree and doc.parent_id != root:
        abort(403)
    can_edit = (get_pin() == s.pin)
    return render_template("document.html", doc=doc, folders=folders, can_edit=can_edit, share=asdict(s), is_shared=True)


@app.get("/s/f/<token>/f/<folder_id>")
def shared_folder_sub(token: str, folder_id: str):
    s, folders, documents = _shared_context(token)
    if s.kind != 'folder':
        abort(404)
    # ensure folder is within subtree of shared root
    subtree = set()
    root = s.target_id
    pending = [root]
    while pending:
        x = pending.pop()
        subtree.add(x)
        for fid, f in folders.items():
            if f.parent_id == x and fid not in subtree:
                pending.append(fid)
    if folder_id not in subtree and folder_id != root:
        abort(403)
    can_edit = (get_pin() == s.pin)
    return render_template("docs.html", pin=None, folders=folders, documents=documents, current_folder=folder_id, share=asdict(s), can_edit=can_edit, is_shared=True)


@app.post("/api/shared/d/<token>/<doc_id>/notes")
def api_shared_add_note(token: str, doc_id: str):
    # Readers can add notes via share token
    s, folders, documents = _shared_context(token)
    if s.kind not in ('doc','folder'):
        abort(404)
    d = documents.get(doc_id)
    if not d:
        abort(404)
    # If folder share, ensure doc is within subtree
    if s.kind == 'folder':
        subtree = set()
        root = s.target_id
        pending = [root]
        while pending:
            x = pending.pop()
            subtree.add(x)
            for fid, f in folders.items():
                if f.parent_id == x and fid not in subtree:
                    pending.append(fid)
        if d.parent_id not in subtree and d.parent_id != root:
            abort(403)
    data = request.json or {}
    try:
        start_line = int(data.get("start_line", 1))
        end_line = int(data.get("end_line", start_line))
    except Exception:
        abort(400)
    text = (data.get("text") or "").strip()
    if not text:
        abort(400)
    author = (data.get("author") or "").strip()
    nid = gen_id()
    d.notes[nid] = DocNote(id=nid, start_line=start_line, end_line=end_line, text=text, author=author)
    # Save to the pin that owns this share
    save_docs(s.pin, folders, documents)
    return jsonify({"ok": True, "note": asdict(d.notes[nid])})


@app.get("/api/shared/resolve/<token>/doc/<doc_id>")
def api_shared_resolve_doc(token: str, doc_id: str):
    s, folders, documents = _shared_context(token)
    d = documents.get(doc_id)
    if not d:
        abort(404)
    allowed = True
    url = None
    if s.kind == 'folder':
        subtree = set()
        root = s.target_id
        pending = [root]
        while pending:
            x = pending.pop()
            subtree.add(x)
            for fid, f in folders.items():
                if f.parent_id == x and fid not in subtree:
                    pending.append(fid)
        allowed = (d.parent_id in subtree) or (d.parent_id == root)
        if allowed:
            url = url_for('shared_folder_doc', token=token, doc_id=doc_id)
    else:
        # doc share: only that doc is allowed
        allowed = (s.kind == 'doc' and s.target_id == doc_id)
        if allowed:
            url = url_for('shared_doc', token=token)
    return jsonify({"ok": True, "allowed": allowed, "url": url})


# --------- Search API (docs + database items) ---------

@app.get("/api/search")
def api_search():
    pin = get_pin()
    if not pin:
        abort(401)
    q = (request.args.get('q') or '').strip().lower()
    folders, documents = load_docs(pin)
    dbs = get_state_or_init(pin)
    results = []
    for d in documents.values():
        if q in d.name.lower() or (q and q in d.content.lower()):
            results.append({"type":"doc","id":d.id,"name":d.name, "parent_id": d.parent_id})
        for line in d.content.splitlines():
            if line.startswith('#'):
                heading = line.lstrip('#').strip()
                if heading and (q in heading.lower()):
                    results.append({"type":"heading","doc_id":d.id,"heading":heading, "doc_name": d.name, "parent_id": d.parent_id})
    for db_id, db in dbs.items():
        db_slug = slugify(db.name)
        if q in db_slug:
            results.append({"type":"database","db_id":db_id,"name":db.name,"slug":db_slug})
        for t_id, t in db.tables.items():
            t_slug = slugify(t.name)
            if q in t_slug:
                results.append({"type":"table","db_id":db_id,"table_id":t_id,"name":t.name,"slug":t_slug})
            for c_id, c in t.columns.items():
                c_slug = slugify(c.name)
                label = f"{t_slug}.{c_slug}"
                if q in c_slug or q in label:
                    results.append({"type":"column","db_id":db_id,"table_id":t_id,"column_id":c_id,"name":c.name,"slug":c_slug,"label":label})
    return jsonify({"ok": True, "results": results[:50]})


# --------- Docs listing APIs (minimal) ---------

@app.get("/api/docs/state")
def api_docs_state():
    pin = get_pin()
    if not pin:
        abort(401)
    folders, documents = load_docs(pin)
    # minimal state, no content
    mf = {fid: {"id": f.id, "name": f.name, "parent_id": f.parent_id} for fid, f in folders.items()}
    md = {did: {"id": d.id, "name": d.name, "parent_id": d.parent_id, "updated_at": d.updated_at} for did, d in documents.items()}
    return jsonify({"ok": True, "folders": mf, "documents": md})


@app.get("/api/shared/f/<token>/state")
def api_shared_docs_state(token: str):
    s, folders, documents = _shared_context(token)
    if s.kind != 'folder':
        abort(404)
    # build subtree folder ids
    subtree = set()
    root = s.target_id
    pending = [root]
    while pending:
        x = pending.pop()
        subtree.add(x)
        for fid, f in folders.items():
            if f.parent_id == x and fid not in subtree:
                pending.append(fid)
    # include only folders in subtree and docs under them
    mf = {fid: {"id": folders[fid].id, "name": folders[fid].name, "parent_id": folders[fid].parent_id} for fid in subtree if fid in folders}
    md = {}
    for did, d in documents.items():
        if d.parent_id in subtree or d.parent_id == root:
            md[did] = {"id": d.id, "name": d.name, "parent_id": d.parent_id, "updated_at": d.updated_at}
    return jsonify({"ok": True, "folders": mf, "documents": md, "root": root})

# --------- Tables ----------

@app.post("/api/databases/<db_id>/tables")
def create_table(db_id: str):
    pin = get_pin()
    if not pin:
        abort(401)
    dbs = get_state_or_init(pin)
    db = dbs.get(db_id)
    if not db:
        abort(404)
    name = request.json.get("name", "New Table").strip() or "New Table"
    t_id = gen_id()
    db.tables[t_id] = Table(id=t_id, name=name)
    save_state(pin, dbs)
    return jsonify({"ok": True, "table": asdict(db.tables[t_id])})


@app.delete("/api/databases/<db_id>/tables/<t_id>")
def delete_table(db_id: str, t_id: str):
    pin = get_pin()
    if not pin:
        abort(401)
    dbs = get_state_or_init(pin)
    db = dbs.get(db_id)
    if not db:
        abort(404)
    if t_id in db.tables:
        # remove links that reference this table or its columns
        to_remove = [l_id for l_id, l in db.links.items() if (l.from_type == 'table' and l.from_id == t_id) or (l.to_type == 'table' and l.to_id == t_id)]
        for l_id in to_remove:
            db.links.pop(l_id, None)
        # remove columns links
        col_ids = list(db.tables[t_id].columns.keys())
        to_remove2 = [l_id for l_id, l in db.links.items() if (l.from_type == 'column' and l.from_id in col_ids) or (l.to_type == 'column' and l.to_id in col_ids)]
        for l_id in to_remove2:
            db.links.pop(l_id, None)
        db.tables.pop(t_id)
        save_state(pin, dbs)
        return jsonify({"ok": True})
    abort(404)


@app.patch("/api/databases/<db_id>/tables/<t_id>")
def update_table(db_id: str, t_id: str):
    pin = get_pin()
    if not pin:
        abort(401)
    dbs = get_state_or_init(pin)
    db = dbs.get(db_id)
    if not db:
        abort(404)
    t = db.tables.get(t_id)
    if not t:
        abort(404)
    data = request.json or {}
    if "name" in data:
        t.name = data["name"].strip() or t.name
    if "note" in data:
        t.note = data["note"]
    save_state(pin, dbs)
    return jsonify({"ok": True, "table": asdict(t)})

# --------- Columns ----------

@app.post("/api/databases/<db_id>/tables/<t_id>/columns")
def create_column(db_id: str, t_id: str):
    pin = get_pin()
    if not pin:
        abort(401)
    dbs = get_state_or_init(pin)
    db = dbs.get(db_id)
    if not db:
        abort(404)
    t = db.tables.get(t_id)
    if not t:
        abort(404)
    data = request.json or {}
    name = (data.get("name") or "column").strip() or "column"
    c_id = gen_id()
    fr = None
    if isinstance(data.get("foreign_ref"), dict):
        fr_raw = data["foreign_ref"]
        # validate minimal fields
        if fr_raw.get("table_id") and fr_raw.get("column_id"):
            fr = ForeignRef(
                table_id=fr_raw["table_id"],
                column_id=fr_raw["column_id"],
                note=fr_raw.get("note", ""),
            )
    # compute next order so newest appears at the bottom
    next_order = 0
    if t.columns:
        try:
            next_order = max((getattr(col, "order", 0) for col in t.columns.values()), default=-1) + 1
        except Exception:
            next_order = len(t.columns)

    col = Column(
        id=c_id,
        name=name,
        datatype=data.get("datatype", "TEXT"),
        is_primary=bool(data.get("is_primary", False)),
        is_nullable=bool(data.get("is_nullable", True)),
        default=data.get("default"),
        note=data.get("note", ""),
        foreign_ref=fr,
        order=next_order,
    )
    t.columns[c_id] = col
    save_state(pin, dbs)
    return jsonify({"ok": True, "column": asdict(col)})


@app.delete("/api/databases/<db_id>/tables/<t_id>/columns/<c_id>")
def delete_column(db_id: str, t_id: str, c_id: str):
    pin = get_pin()
    if not pin:
        abort(401)
    dbs = get_state_or_init(pin)
    db = dbs.get(db_id)
    if not db:
        abort(404)
    t = db.tables.get(t_id)
    if not t:
        abort(404)
    if c_id in t.columns:
        # remove links referencing this column
        to_remove = [l_id for l_id, l in db.links.items() if (l.from_type == 'column' and l.from_id == c_id) or (l.to_type == 'column' and l.to_id == c_id)]
        for l_id in to_remove:
            db.links.pop(l_id, None)
        t.columns.pop(c_id)
        save_state(pin, dbs)
        return jsonify({"ok": True})
    abort(404)


@app.patch("/api/databases/<db_id>/tables/<t_id>/columns/<c_id>")
def update_column(db_id: str, t_id: str, c_id: str):
    pin = get_pin()
    if not pin:
        abort(401)
    dbs = get_state_or_init(pin)
    db = dbs.get(db_id)
    if not db:
        abort(404)
    t = db.tables.get(t_id)
    if not t:
        abort(404)
    col = t.columns.get(c_id)
    if not col:
        abort(404)
    data = request.json or {}
    if "name" in data:
        col.name = data["name"].strip() or col.name
    if "datatype" in data:
        col.datatype = data["datatype"]
    if "is_primary" in data:
        col.is_primary = bool(data["is_primary"])  # allow toggle
    if "is_nullable" in data:
        col.is_nullable = bool(data["is_nullable"])  # allow toggle
    if "default" in data:
        col.default = data["default"]
    if "note" in data:
        col.note = data["note"]
    if "foreign_ref" in data:
        fr_raw = data["foreign_ref"]
        if fr_raw is None:
            col.foreign_ref = None
        elif isinstance(fr_raw, dict) and fr_raw.get("table_id") and fr_raw.get("column_id"):
            col.foreign_ref = ForeignRef(
                table_id=fr_raw["table_id"],
                column_id=fr_raw["column_id"],
                note=fr_raw.get("note", ""),
            )
    if "order" in data:
        try:
            new_order = int(data["order"])
            col.order = new_order
        except Exception:
            pass
    save_state(pin, dbs)
    return jsonify({"ok": True, "column": asdict(col)})

# --------- Duplicate Database ----------

@app.post("/api/databases/<db_id>/duplicate")
def duplicate_database(db_id: str):
    pin = get_pin()
    if not pin:
        abort(401)
    dbs = get_state_or_init(pin)
    src = dbs.get(db_id)
    if not src:
        abort(404)

    # New database id and structure
    new_db_id = gen_id()
    new_db = Database(id=new_db_id, name=f"{src.name} (copy)", note=src.note)

    # Build id maps
    table_id_map: Dict[str, str] = {}
    col_id_map: Dict[str, str] = {}

    # First pass: create tables and columns with new ids, but defer foreign_ref
    pending_refs: List[tuple[str, str, ForeignRef]] = []  # (t_id_new, c_id_new, old_foreign_ref)
    for t_old_id, t in src.tables.items():
        t_new_id = gen_id()
        table_id_map[t_old_id] = t_new_id
        new_table = Table(id=t_new_id, name=t.name, note=t.note)
        new_db.tables[t_new_id] = new_table
        for c_old_id, c in t.columns.items():
            c_new_id = gen_id()
            col_id_map[c_old_id] = c_new_id
            new_col = Column(
                id=c_new_id,
                name=c.name,
                datatype=c.datatype,
                is_primary=c.is_primary,
                is_nullable=c.is_nullable,
                default=c.default,
                note=c.note,
                foreign_ref=None,
            )
            new_table.columns[c_new_id] = new_col
            if c.foreign_ref:
                pending_refs.append((t_new_id, c_new_id, c.foreign_ref))

    # Resolve foreign refs
    for t_new_id, c_new_id, fr in pending_refs:
        mapped_t = table_id_map.get(fr.table_id)
        mapped_c = col_id_map.get(fr.column_id)
        if mapped_t and mapped_c:
            new_db.tables[t_new_id].columns[c_new_id].foreign_ref = ForeignRef(
                table_id=mapped_t,
                column_id=mapped_c,
                note=fr.note,
            )

    # Remap links too (if any exist)
    for l_id, l in src.links.items():
        new_l_id = gen_id()
        from_id_new = l.from_id
        to_id_new = l.to_id
        if l.from_type == 'table':
            from_id_new = table_id_map.get(l.from_id, l.from_id)
        elif l.from_type == 'column':
            from_id_new = col_id_map.get(l.from_id, l.from_id)
        if l.to_type == 'table':
            to_id_new = table_id_map.get(l.to_id, l.to_id)
        elif l.to_type == 'column':
            to_id_new = col_id_map.get(l.to_id, l.to_id)
        new_db.links[new_l_id] = Link(
            id=new_l_id,
            from_type=l.from_type,
            from_id=from_id_new,
            to_type=l.to_type,
            to_id=to_id_new,
            note=l.note,
        )

    dbs[new_db_id] = new_db
    save_state(pin, dbs)
    return jsonify({"ok": True, "database": asdict(new_db)})

# --------- Links ----------

@app.post("/api/databases/<db_id>/links")
def create_link(db_id: str):
    pin = get_pin()
    if not pin:
        abort(401)
    dbs = get_state_or_init(pin)
    db = dbs.get(db_id)
    if not db:
        abort(404)
    data = request.json or {}
    link = Link(
        id=gen_id(),
        from_type=data.get("from_type", "table"),
        from_id=data.get("from_id"),
        to_type=data.get("to_type", "table"),
        to_id=data.get("to_id"),
        note=data.get("note", ""),
    )
    if not link.from_id or not link.to_id:
        abort(400, "Missing link endpoints")
    db.links[link.id] = link
    save_state(pin, dbs)
    return jsonify({"ok": True, "link": asdict(link)})


@app.patch("/api/databases/<db_id>/links/<l_id>")
def update_link(db_id: str, l_id: str):
    pin = get_pin()
    if not pin:
        abort(401)
    dbs = get_state_or_init(pin)
    db = dbs.get(db_id)
    if not db:
        abort(404)
    link = db.links.get(l_id)
    if not link:
        abort(404)
    data = request.json or {}
    if "note" in data:
        link.note = data["note"]
    save_state(pin, dbs)
    return jsonify({"ok": True, "link": asdict(link)})


@app.delete("/api/databases/<db_id>/links/<l_id>")
def delete_link(db_id: str, l_id: str):
    pin = get_pin()
    if not pin:
        abort(401)
    dbs = get_state_or_init(pin)
    db = dbs.get(db_id)
    if not db:
        abort(404)
    if l_id in db.links:
        db.links.pop(l_id)
        save_state(pin, dbs)
        return jsonify({"ok": True})
    abort(404)


# --------- Simple API to fetch state ----------

@app.get("/api/state")
def get_state():
    pin = get_pin()
    if not pin:
        abort(401)
    dbs = get_state_or_init(pin)
    payload = {db_id: asdict(db) for db_id, db in dbs.items()}
    return jsonify(payload)


# --------- Pages per database ----------

@app.get("/db/<db_id>")
def db_page(db_id: str):
    pin = get_pin()
    if not pin:
        return redirect(url_for("index"))
    dbs = get_state_or_init(pin)
    db = dbs.get(db_id)
    if not db:
        abort(404)
    return render_template("database.html", db=db, db_id=db_id)


# -----------------------------
# Run
# -----------------------------

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
