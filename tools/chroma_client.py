from __future__ import annotations
from typing import List, Dict, Any, Optional
import chromadb


class ChromaClient:
    def __init__(self, persist_dir: str = ".chroma"):
        self.client = chromadb.PersistentClient(path=persist_dir)

    def get_or_create(self, name: str, metadata: Optional[Dict[str, Any]] = None):
        safe_metadata = metadata if (metadata and len(metadata) > 0) else {"created_by": "schematic-agent", "collection": name}
        return self.client.get_or_create_collection(name=name, metadata=safe_metadata)

    def list_collections(self) -> List[str]:
        return [c.name for c in self.client.list_collections()]

    def delete_collection(self, name: str) -> None:
        self.client.delete_collection(name)

    def add(self, collection_name: str, ids: List[str], documents: List[str], metadatas: Optional[List[Dict[str, Any]]] = None) -> None:
        col = self.get_or_create(collection_name)
        col.add(ids=ids, documents=documents, metadatas=metadatas)

    def query(self, collection_name: str, text: str, n_results: int = 5) -> List[Dict[str, Any]]:
        col = self.get_or_create(collection_name)
        res = col.query(query_texts=[text], n_results=n_results)
        results: List[Dict[str, Any]] = []
        for i in range(len(res.get("ids", [[]])[0])):
            results.append({
                "id": res["ids"][0][i],
                "document": res["documents"][0][i],
                "metadata": res["metadatas"][0][i],
                "distance": res.get("distances", [[None]])[0][i],
            })
        return results
