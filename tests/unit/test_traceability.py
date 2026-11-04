import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_R_ids_covered_every_requirement_has_a_named_test():
    spec = (ROOT / "specs/001-multi-agent-support/spec.md").read_text()
    ids = re.findall(r"^- \*\*(R\d+)\*\*:", spec, re.M)
    assert len(ids) == 62
    source = "".join(p.read_text() for p in (ROOT / "tests").rglob("test_*.py"))
    names = re.findall(r"def (test_\w+)", source)
    missing = [i for i in ids if not any(re.search(rf"_{i}(_|$)", name) for name in names)]
    assert missing == []
