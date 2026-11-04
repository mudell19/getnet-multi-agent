"""Chunks by heading and by FAQ question, never by fixed windows."""
import hashlib
from dataclasses import dataclass

from getnet_multi_agent.rag.extract import Block

MAX_BODY_CHARS = 3000
MIN_BODY_CHARS = 15


@dataclass(frozen=True)
class Chunk:
    id: str
    url: str
    title: str
    origin: str
    heading: str
    text: str


def chunk_blocks(blocks: list[Block], url: str, title: str, origin: str) -> list[Chunk]:
    sections: list[tuple[str, list[str]]] = []
    heading = ""
    question = ""
    body: list[str] = []

    def close() -> None:
        nonlocal body
        content = "\n".join(body)
        if len(content) >= MIN_BODY_CHARS:
            sections.append((question or heading, list(body)))
        body = []

    for block in blocks:
        if block.kind == "heading":
            # Consecutive headings stay together, such as a product name and its subtitle.
            joined = f"{heading} - {block.text}" if heading and not body and not question else block.text
            close()
            heading, question = joined, ""
        elif block.kind == "question":
            if block.text == question and not body:
                continue
            close()
            question = block.text
        else:
            body.append(block.text)
            # Oversized sections split at a block boundary and keep their heading.
            if sum(len(b) for b in body) > MAX_BODY_CHARS:
                close()
    close()

    chunks = []
    for index, (section_heading, section_body) in enumerate(sections):
        text = "\n".join(p for p in (title, section_heading, *section_body) if p)
        digest = hashlib.sha256(f"{url}#{index}".encode()).hexdigest()[:32]
        chunks.append(Chunk(digest, url, title, origin, section_heading, text))
    return chunks
