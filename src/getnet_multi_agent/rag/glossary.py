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


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


_PATTERNS = [
    re.compile(r"\b(" + "|".join(re.escape(fold(term)) for term in group) + r")\b")
    for group in ALIAS_GROUPS
]


def matched_groups(text: str) -> list[int]:
    folded = fold(text)
    return [i for i, pattern in enumerate(_PATTERNS) if pattern.search(folded)]


def expansion_terms(groups: list[int]) -> list[str]:
    return [term for i in groups for term in ALIAS_GROUPS[i]]


def group_hits(text: str, groups: list[int]) -> int:
    folded = fold(text)
    return sum(1 for i in groups if _PATTERNS[i].search(folded))
