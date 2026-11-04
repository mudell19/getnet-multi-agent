"""Combines vector top-k with lexical matching over the alias glossary."""
from dataclasses import dataclass

from getnet_multi_agent.llm import LLMClient, RequestContext
from getnet_multi_agent.rag.chunker import Chunk
from getnet_multi_agent.rag.glossary import expansion_terms, group_hits, matched_groups
from getnet_multi_agent.rag.store import KnowledgeStore


@dataclass
class Retrieved:
    chunk: Chunk
    similarity: float | None
    match: str  # vector, lexical or both


class Retriever:
    def __init__(self, store: KnowledgeStore, llm: LLMClient, top_k: int, min_similarity: float):
        self.store = store
        self.llm = llm
        self.top_k = top_k
        self.min_similarity = min_similarity
        self._chunks: list[Chunk] | None = None

    def _lexical(self, groups: list[int]) -> list[Chunk]:
        if self._chunks is None:
            self._chunks = self.store.all_chunks()
        scored = []
        for chunk in self._chunks:
            hits = group_hits(chunk.text, groups)
            if hits:
                # More alias groups first, then matches in the heading, then shorter sections.
                scored.append((-hits, -group_hits(chunk.heading, groups), len(chunk.text), chunk.id, chunk))
        scored.sort(key=lambda item: item[:4])
        return [item[4] for item in scored]

    def retrieve(self, ctx: RequestContext, query: str) -> list[Retrieved]:
        """Returns qualifying chunks only: similarity at the threshold, or a glossary match."""
        if self.store.count() == 0:
            return []
        groups = matched_groups(query)
        expanded = " ".join([query, *expansion_terms(groups)])
        vector = self.llm.embed(ctx, "knowledge", [expanded])[0]
        hits = self.store.query(vector, self.top_k)
        similarity = {chunk.id: score for chunk, score in hits}

        selected: dict[str, Retrieved] = {}
        lexical_slots = (self.top_k + 1) // 2 if groups else 0
        for chunk in self._lexical(groups)[:lexical_slots] if groups else []:
            score = similarity.get(chunk.id)
            selected[chunk.id] = Retrieved(chunk, score, "both" if score is not None else "lexical")
        for chunk, score in hits:
            if len(selected) >= self.top_k:
                break
            if score >= self.min_similarity and chunk.id not in selected:
                selected[chunk.id] = Retrieved(chunk, score, "vector")
        return list(selected.values())
