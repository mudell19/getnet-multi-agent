"""Alias groups, because users write in English while the main source is in Portuguese."""
import re
import unicodedata

ALIAS_GROUPS: tuple[tuple[str, ...], ...] = (
    ("get clássica", "get classica", "get classic"),
    ("get smart",),
    ("link de pagamento", "payment link"),
    ("antecipação", "antecipação de vendas", "antecipar", "receivables advance"),
    ("crediário", "parcelas", "parcela", "installments", "installment"),
    # Added for scenarios S4 and S5, which have no product alias of their own.
    ("pix",),
    ("conta bancária", "bank account", "conta de recebimento", "get conta"),
    ("internet", "connect", "connection", "connectivity", "conexão", "conectividade", "chip", "teste de comunicação"),
)

# These trigger a group from a question, but match too much marketing text to rank chunks.
QUERY_ONLY_TERMS = {"connect", "connection", "connectivity"}


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _pattern(terms) -> re.Pattern:
    return re.compile(r"\b(" + "|".join(re.escape(fold(term)) for term in terms) + r")\b")


_QUERY_PATTERNS = [_pattern(group) for group in ALIAS_GROUPS]
_CHUNK_PATTERNS = [_pattern(t for t in group if t not in QUERY_ONLY_TERMS) for group in ALIAS_GROUPS]


def matched_groups(text: str) -> list[int]:
    folded = fold(text)
    return [i for i, pattern in enumerate(_QUERY_PATTERNS) if pattern.search(folded)]


def expansion_terms(groups: list[int]) -> list[str]:
    return [term for i in groups for term in ALIAS_GROUPS[i]]


def group_hits(text: str, groups: list[int]) -> int:
    folded = fold(text)
    return sum(1 for i in groups if _CHUNK_PATTERNS[i].search(folded))


def is_exact_term(text: str, groups: list[int]) -> bool:
    """True when the whole text is an alias, such as a product card titled "Get Classic"."""
    folded = fold(text).strip()
    return any(_CHUNK_PATTERNS[i].fullmatch(folded) for i in groups)
