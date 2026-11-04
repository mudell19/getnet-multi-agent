"""Ingestion pipeline and the refresh command: python -m getnet_multi_agent.rag.ingest --refresh"""
import argparse
from collections import defaultdict
from urllib.parse import urlsplit

from getnet_multi_agent.config import Settings, load_settings
from getnet_multi_agent.llm import LLMClient
from getnet_multi_agent.logging_setup import log_event
from getnet_multi_agent.rag.chunker import Chunk, chunk_blocks
from getnet_multi_agent.rag.crawler import Crawler, Page
from getnet_multi_agent.rag.extract import extract_blocks, strip_repeated
from getnet_multi_agent.rag.store import KnowledgeStore


def build_chunks(pages: list[Page]) -> list[Chunk]:
    by_host: dict[str, list[Page]] = defaultdict(list)
    for page in pages:
        by_host[urlsplit(page.final_url).hostname].append(page)
    chunks: list[Chunk] = []
    for host_pages in by_host.values():
        cleaned = strip_repeated([extract_blocks(p.html) for p in host_pages])
        for page, blocks in zip(host_pages, cleaned):
            chunks.extend(chunk_blocks(blocks, page.final_url, page.title, page.origin))
    return chunks


def ingest(settings: Settings, llm: LLMClient, store: KnowledgeStore, refresh: bool = False, crawler=None) -> int:
    crawler = crawler or Crawler(settings.data_dir / "crawl_cache", settings.rag_max_pages, refresh=refresh)
    result = crawler.crawl()
    chunks = build_chunks(result.pages)
    if not chunks:
        log_event("ingest_empty", stopped_hosts=result.stopped_hosts)
        return 0
    vectors = llm.embed(None, "ingestion", [c.text for c in chunks])
    store.replace(chunks, vectors)
    log_event("ingest_complete", pages=len(result.pages), chunks=len(chunks), stopped_hosts=result.stopped_hosts)
    return len(chunks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the knowledge base. Stop the service first.")
    parser.add_argument("--refresh", action="store_true", help="refetch cached URLs")
    args = parser.parse_args()
    settings = load_settings()
    store = KnowledgeStore(settings.data_dir / "chroma")
    ingest(settings, LLMClient(settings), store, refresh=args.refresh)


if __name__ == "__main__":
    main()
