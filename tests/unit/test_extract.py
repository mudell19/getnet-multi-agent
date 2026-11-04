from getnet_multi_agent.rag.chunker import chunk_blocks
from getnet_multi_agent.rag.extract import Block, extract_blocks, strip_repeated

PAGE = """<html><head><title>T</title><style>.a{}</style><script>var x=1</script></head><body>
<header>HEADER TEXT</header><nav>NAV TEXT</nav>
<div class="card"><h3>Get Smart</h3><p>The POS to make your business grow.</p><ul><li>Android system</li></ul></div>
<table><tr><th>Plan</th><th>Rate</th></tr><tr><td>Get Clássica</td><td>R$ 79,90</td></tr></table>
<div class="faq"><h2>Algar</h2>
<a class="q" href="#">Como insiro o Chip na minha máquina?</a>
<div class="modal"><div class="title">Como insiro o Chip na minha máquina?</div>
<div class="txt"><p>Siga os passos:<br />– Abra a tampa<br />– Insira o chip em SIM1</p></div></div>
<a class="q" href="#">O que é o Chip Algar?</a>
<div class="modal"><div class="title">O que é o Chip Algar?</div><div class="txt"><p>É um chip multioperadora de rede.</p></div></div>
</div><footer>FOOTER TEXT</footer></body></html>"""


def test_R25_strips_page_chrome_and_scripts():
    text = " ".join(b.text for b in extract_blocks(PAGE))
    for removed in ("HEADER TEXT", "NAV TEXT", "FOOTER TEXT", "var x", ".a{}"):
        assert removed not in text


def test_R25_preserves_tables_product_cards_and_faq_questions():
    blocks = extract_blocks(PAGE)
    assert Block("row", "Get Clássica | R$ 79,90") in blocks
    assert Block("heading", "Get Smart") in blocks
    assert Block("text", "Android system") in blocks
    assert Block("question", "O que é o Chip Algar?") in blocks


def test_R25_strips_text_repeated_in_30_percent_of_pages():
    common = Block("text", "Baixe o app")
    pages = [[common, Block("text", f"page {i}")] for i in range(3)]
    pages += [[Block("text", f"other {i}")] for i in range(7)]
    result = strip_repeated(pages)
    assert all(common not in page for page in result)
    assert Block("text", "page 0") in result[0]


def test_R25_keeps_text_below_the_repetition_threshold():
    rare = Block("text", "rare")
    pages = [[rare]] * 2 + [[Block("text", f"o{i}")] for i in range(8)]
    assert rare in strip_repeated(pages)[0]


def test_R26_chunks_by_heading_and_faq_question():
    chunks = chunk_blocks(extract_blocks(PAGE), "https://x/", "T", "brazil_site")
    headings = [c.heading for c in chunks]
    assert "Get Smart" in headings
    assert "Como insiro o Chip na minha máquina?" in headings
    assert "O que é o Chip Algar?" in headings


def test_R26_each_faq_question_stays_with_its_own_answer():
    chunks = chunk_blocks(extract_blocks(PAGE), "https://x/", "T", "brazil_site")
    chip = next(c for c in chunks if c.heading.startswith("Como insiro"))
    assert "SIM1" in chip.text and "multioperadora" not in chip.text
    other = next(c for c in chunks if c.heading.startswith("O que é"))
    assert "multioperadora" in other.text and "SIM1" not in other.text


def test_R26_oversized_sections_split_at_block_boundaries_keeping_heading():
    blocks = [Block("heading", "H")] + [Block("text", "x" * 1000 + str(i)) for i in range(7)]
    chunks = chunk_blocks(blocks, "u", "T", "brazil_site")
    assert len(chunks) >= 2 and all(c.heading == "H" for c in chunks)
    assert all(c.text.count("x" * 1000) <= 4 for c in chunks)
