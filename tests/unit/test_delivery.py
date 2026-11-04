"""Delivery requirements. The Docker requirements are proven by running the container; these checks
guard the configuration between those runs."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_R60_env_example_lists_every_variable_and_holds_no_secret():
    example = (ROOT / ".env.example").read_text()
    source = "".join(p.read_text() for p in (ROOT / "src").rglob("*.py"))
    used = set(re.findall(r'(?:_required\(|environ\.get\()"([A-Z_]+)"', source)) - {"DATA_DIR", "APP_REV"}
    for name in used:
        assert re.search(rf"^{name}=", example, re.M), name
    assert re.search(r"^GEMINI_API_KEY=your-api-key-here$", example, re.M)


def test_R60_real_env_file_is_ignored_by_git_and_docker():
    assert ".env" in (ROOT / ".gitignore").read_text().splitlines()
    assert ".env" in (ROOT / ".dockerignore").read_text().splitlines()
    tracked = subprocess.run(["git", "ls-files", ".env"], cwd=ROOT, capture_output=True, text=True).stdout
    assert tracked == ""


def test_R61_compose_and_dockerfile_define_volume_health_and_locked_install():
    compose = (ROOT / "docker-compose.yml").read_text()
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "app_data:/app/data" in compose and "env_file: .env" in compose and "max-size" in compose
    assert "HEALTHCHECK" in dockerfile and "/health" in dockerfile
    assert "uv sync --frozen" in dockerfile and "@sha256:" in dockerfile


def test_R62_readme_covers_every_required_section():
    readme = (ROOT / "README.md").read_text().lower()
    for text in (
        "docs/agent-workflow.png",
        "## build, configure and run",
        "## testing strategy",
        "## orchestration architecture",
        "## design choices",
        "## message workflow",
        "## rag pipeline",
        "### ingestion",
        "### storage",
        "### retrieval",
        "### generation",
        "## how llm tools are used",
        "## evaluation and observability",
        "dashboards",
        "alerts",
        "## known limits",
        "without authentication",
        "no conversation memory",
        "paid-tier",
    ):
        assert text in readme, text
