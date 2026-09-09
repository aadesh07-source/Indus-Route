"""Vector knowledge base (ChromaDB) for statutory RAG — optional layer.

The assistant's general-regulatory questions are answered by retrieving the
most relevant statute snippets from a persistent ChromaDB collection seeded
from app/rules/regulatory_kb.json plus every sector rule table. This mirrors
the reference architecture: chat UI -> SSE -> application context + vector
store -> Gemini (streaming).

GRACEFUL DEGRADATION (project convention): if chromadb or its embedding
model is unavailable, every function here degrades and the chat engine falls
back to the deterministic rule-table RAG in ai_service. Nothing here can
crash the API or the chat.
"""
import json
from pathlib import Path

from .. import config

COLLECTION_NAME = "maharashtra_regulations"

_state = {"collection": None, "error": None}


def _kb_file() -> Path:
    return Path(__file__).resolve().parents[1] / "rules" / "regulatory_kb.json"


def available() -> bool:
    try:
        import chromadb  # noqa: F401
        return True
    except Exception:
        return False


def _get_collection():
    if _state["collection"] is not None:
        return _state["collection"]
    import chromadb
    client = chromadb.PersistentClient(path=str(config.DATA_DIR / "chroma_db"))
    _state["collection"] = client.get_or_create_collection(
        name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
    return _state["collection"]


def _iter_docs():
    """Yield statute docs + sector rule-table approval docs for ingestion."""
    try:
        data = json.loads(_kb_file().read_text(encoding="utf-8"))
        for d in data.get("documents", []):
            yield {"id": d["id"], "title": d.get("title", d["id"]),
                   "source": d.get("source", ""), "text": d.get("text", "")}
    except Exception:
        pass
    # Ingest sector rule tables so the vector store also covers platform rules.
    rules_dir = _kb_file().parent
    for jf in sorted(rules_dir.glob("*.json")):
        if jf.name in ("regulatory_kb.json", "document_checks.json"):
            continue
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            sector = data.get("sector", jf.stem)
            for ap in data.get("approvals", []):
                req = ap.get("required_documents") or []
                doc_txt = ", ".join(d if isinstance(d, str)
                                    else str(d.get("type", "")) for d in req)
                rid = ap.get("id") or ap.get("code")
                if not rid:
                    continue
                yield {
                    "id": "rule_{}".format(rid),
                    "title": "{} ({})".format(ap.get("name", ""), ap.get("code", "")),
                    "source": ap.get("department", "Sector rule table"),
                    "text": ("Approval '{}' (code {}) applies to the {} sector, "
                             "administered by {}. {}. Statutory SLA: {} days. "
                             "Parallel group: {}. Required documents: {}.").format(
                        ap.get("name", ""), ap.get("code", ""), sector,
                        ap.get("department", "concerned authority"),
                        ap.get("description", ""), ap.get("sla_days", "N/A"),
                        ap.get("parallel_group", "N/A"), doc_txt or "as notified"),
                }
        except Exception:
            continue


def seed(force: bool = False) -> dict:
    """Ingest the knowledge base. Safe to call repeatedly (idempotent)."""
    if not available():
        return {"seeded": False, "reason": "chromadb not installed"}
    try:
        col = _get_collection()
        docs = list(_iter_docs())
        if force and col.count():
            col.delete(ids=col.get()["ids"])
        existing = set(col.get()["ids"]) if col.count() else set()
        new = [d for d in docs if d["id"] not in existing]
        if new:
            col.add(
                ids=[d["id"] for d in new],
                documents=["{}. {}".format(d["title"], d["text"]) for d in new],
                metadatas=[{"title": d["title"], "source": d["source"]} for d in new])
        return {"seeded": True, "total": col.count(), "added": len(new)}
    except Exception as exc:  # embedding model download failure, disk, etc.
        _state["error"] = str(exc)
        return {"seeded": False, "reason": str(exc)[:200]}


def retrieve(query: str, n: int = 3) -> list:
    """Top-n statute snippets. Returns [] on any failure (caller falls back)."""
    if not available() or not (query or "").strip():
        return []
    try:
        col = _get_collection()
        total = col.count()
        if total == 0:
            return []
        res = col.query(query_texts=[query], n_results=min(n, total))
        out = []
        ids = res.get("ids") or [[]]
        docs = (res.get("documents") or [[]])[0] or []
        metas = (res.get("metadatas") or [[]])[0] or []
        dists = (res.get("distances") or [[]])[0] or []
        for i, doc_id in enumerate(ids[0]):
            meta = metas[i] if i < len(metas) else {}
            out.append({
                "id": doc_id,
                "title": (meta or {}).get("title", doc_id),
                "source": (meta or {}).get("source", ""),
                "text": docs[i] if i < len(docs) else "",
                "distance": dists[i] if i < len(dists) else None,
            })
        return out
    except Exception:
        return []


def status() -> dict:
    """Reported via /health so judges can see the RAG layer's mode."""
    if not available():
        return {"available": False,
                "reason": "chromadb not installed (keyword RAG fallback active)"}
    try:
        col = _get_collection()
        return {"available": True, "documents": col.count(),
                "collection": COLLECTION_NAME}
    except Exception as exc:
        return {"available": False, "reason": str(exc)[:120]}