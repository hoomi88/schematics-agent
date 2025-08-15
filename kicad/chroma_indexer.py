from __future__ import annotations
from pathlib import Path
from typing import List, Dict
from kicad.library import _candidate_symbol_dirs, _list_symbol_files
from tools.chroma_client import ChromaClient
import hashlib


def _make_id(lib: str, path: Path) -> str:
    h = hashlib.sha1(str(path).encode("utf-8")).hexdigest()
    return f"{lib}|{h}"


def build_symbol_documents() -> List[Dict[str, str]]:
    docs: List[Dict[str, str]] = []
    seen_ids: set[str] = set()
    for root in _candidate_symbol_dirs():
        for fpath in _list_symbol_files(root):
            lib = fpath.stem
            doc_id = _make_id(lib, fpath)
            if doc_id in seen_ids:
                continue
            seen_ids.add(doc_id)
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            docs.append({
                "id": doc_id,
                "document": text,
                "lib": lib,
                "path": str(fpath),
            })
    return docs


def populate_chroma(persist_dir: str = ".chroma", collection: str = "kicad_symbols") -> None:
    client = ChromaClient(persist_dir=persist_dir)
    try:
        client.delete_collection(collection)
    except Exception:
        pass
    docs = build_symbol_documents()
    if not docs:
        return
    ids = [d["id"] for d in docs]
    documents = [d["document"] for d in docs]
    metadatas = [{"lib": d["lib"], "path": d["path"]} for d in docs]
    client.add(collection, ids=ids, documents=documents, metadatas=metadatas)


if __name__ == "__main__":
    populate_chroma()
    print("Chroma populated with KiCad symbol libraries.")
