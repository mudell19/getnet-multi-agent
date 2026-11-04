"""Persistent vector store in cosine space, where similarity = 1 - distance."""
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from getnet_multi_agent.rag.chunker import Chunk

COLLECTION = "knowledge_base"
BUILDING = "knowledge_base_building"
ADD_BATCH = 500


def _to_chunk(chunk_id: str, document: str, meta: dict) -> Chunk:
    return Chunk(chunk_id, meta["url"], meta["title"], meta["origin"], meta["heading"], document)


class KnowledgeStore:
    def __init__(self, path: Path):
        path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(path), settings=ChromaSettings(anonymized_telemetry=False)
        )
        self._drop(BUILDING)  # A leftover build means an earlier ingestion was interrupted.

    def _drop(self, name: str) -> None:
        if name in {c.name for c in self.client.list_collections()}:
            self.client.delete_collection(name)

    def count(self) -> int:
        if COLLECTION not in {c.name for c in self.client.list_collections()}:
            return 0
        return self.client.get_collection(COLLECTION).count()

    def replace(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Builds aside and swaps, so a failed run never damages the current knowledge base."""
        self._drop(BUILDING)
        building = self.client.create_collection(BUILDING, configuration={"hnsw": {"space": "cosine"}})
        for i in range(0, len(chunks), ADD_BATCH):
            batch = chunks[i : i + ADD_BATCH]
            building.add(
                ids=[c.id for c in batch],
                embeddings=vectors[i : i + ADD_BATCH],
                documents=[c.text for c in batch],
                metadatas=[
                    {"url": c.url, "title": c.title, "origin": c.origin, "heading": c.heading}
                    for c in batch
                ],
            )
        self._drop(COLLECTION)
        building.modify(name=COLLECTION)

    def query(self, vector: list[float], k: int) -> list[tuple[Chunk, float]]:
        result = self.client.get_collection(COLLECTION).query(
            query_embeddings=[vector], n_results=k, include=["documents", "metadatas", "distances"]
        )
        return [
            (_to_chunk(i, d, m), 1.0 - distance)
            for i, d, m, distance in zip(
                result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0]
            )
        ]

    def all_chunks(self) -> list[Chunk]:
        data = self.client.get_collection(COLLECTION).get(include=["documents", "metadatas"])
        return [_to_chunk(i, d, m) for i, d, m in zip(data["ids"], data["documents"], data["metadatas"])]
