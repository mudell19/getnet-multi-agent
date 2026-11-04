"""Block-level text extraction that keeps tables, product cards and FAQ questions.

It removes page chrome and text repeated across pages instead of using main-content detection,
which drops product cards and FAQ entries on these sites.
"""
from collections import Counter
from dataclasses import dataclass

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

REMOVED_TAGS = ["script", "style", "nav", "header", "footer", "noscript", "svg", "form", "iframe", "select", "template"]
INLINE_TAGS = {"a", "span", "strong", "em", "b", "i", "u", "small", "sup", "sub", "br", "font", "abbr", "code", "mark", "label", "img"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
REPETITION_THRESHOLD = 0.30
MIN_PAGES_FOR_REPETITION = 5
MAX_QUESTION_CHARS = 200


@dataclass(frozen=True)
class Block:
    kind: str  # heading, question, text or row
    text: str


def _clean(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _text_block(text: str) -> Block | None:
    cleaned = _clean(text)
    if not cleaned:
        return None
    if cleaned.endswith("?") and len(cleaned) <= MAX_QUESTION_CHARS and "\n" not in cleaned:
        return Block("question", cleaned)
    return Block("text", cleaned)


def _has_block_child(tag: Tag) -> bool:
    return any(isinstance(d, Tag) and d.name not in INLINE_TAGS for d in tag.descendants)


def _walk(element: Tag, blocks: list[Block]) -> None:
    buffer: list[str] = []

    def flush() -> None:
        block = _text_block("".join(buffer))
        buffer.clear()
        if block and (not blocks or blocks[-1] != block):
            blocks.append(block)

    for child in element.children:
        if isinstance(child, NavigableString):
            if type(child) is NavigableString:
                buffer.append(str(child))
        elif not isinstance(child, Tag):
            continue
        elif child.name == "br":
            buffer.append("\n")
        elif child.name in HEADING_TAGS:
            flush()
            text = " ".join(child.get_text(" ").split())
            if text:
                blocks.append(Block("heading", text))
        elif child.name == "table":
            flush()
            for row in child.find_all("tr"):
                cells = [" ".join(c.get_text(" ").split()) for c in row.find_all(["th", "td"])]
                if any(cells):
                    blocks.append(Block("row", " | ".join(cells)))
        elif child.name in INLINE_TAGS and not _has_block_child(child):
            if child.name == "a" and child.get_text(strip=True).endswith("?"):
                flush()
                buffer.append(child.get_text(" "))
                flush()
            else:
                for br in child.find_all("br"):
                    br.replace_with("\n")
                buffer.append(child.get_text(" "))
        else:
            flush()
            _walk(child, blocks)
    flush()


def extract_blocks(html: str) -> list[Block]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(REMOVED_TAGS):
        tag.decompose()
    blocks: list[Block] = []
    if soup.body:
        _walk(soup.body, blocks)
    return blocks


def strip_repeated(pages: list[list[Block]]) -> list[list[Block]]:
    """Drops text found in 30% or more of the pages. Call once per host."""
    if len(pages) < MIN_PAGES_FOR_REPETITION:
        return pages
    counts = Counter(text for page in pages for text in {b.text for b in page})
    limit = REPETITION_THRESHOLD * len(pages)
    return [[b for b in page if counts[b.text] < limit] for page in pages]


