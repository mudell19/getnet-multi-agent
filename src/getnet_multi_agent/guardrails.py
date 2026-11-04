"""Deterministic guardrails. They run before routing and before any LLM or log sees the text."""
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

Language = Literal["en", "pt"]

CARD_CANDIDATE = re.compile(r"(?<!\d)\d(?:[ .-]?\d){12,18}(?!\d)")
CPF_FORMATTED = re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)")
CPF_BARE = re.compile(r"(?<!\d)\d{11}(?!\d)")
CARD_MASK = "[CARD MASKED]"
CPF_MASK = "[CPF MASKED]"

INJECTION_PATTERNS = [
    re.compile(p)
    for p in (
        # English
        r"\b(ignore|disregard|forget|override)\b.{0,40}\b(instructions?|prompts?|rules?)\b",
        r"\b(system|developer) (prompt|message|instructions?)\b",
        r"\b(reveal|show|print|repeat|leak)\b.{0,30}\b(prompt|instructions?)\b",
        r"\byou are now\b",
        r"\b(jailbreak|developer mode|dan mode)\b",
        r"\bpretend (to be|you are)\b",
        # Portuguese (accents removed before matching)
        r"\b(ignore|ignora|desconsidere|esqueca|esquece)\b.{0,40}\b(instrucoes|instrucao|prompts?|regras?)\b",
        r"\b(prompt|mensagem|instrucoes) do (sistema|desenvolvedor)\b",
        r"\b(revele|mostre|imprima|repita)\b.{0,30}\b(prompt|instrucoes)\b",
        r"\bvoce agora e\b",
        r"\bmodo (desenvolvedor|sem restricoes)\b",
        r"\bfinja (ser|que)\b",
    )
]

PT_WORDS = set(
    "o a os as um uma de do da dos das em no na nos nas para por com que como quando qual quais "
    "minha meu minhas meus nao sim e voce voces preciso quero posso tem ter esta estou ontem hoje "
    "vendas maquina maquininha dinheiro cartao ola obrigado".split()
)
EN_WORDS = set(
    "the a an of in on for with what how when which my me i you your is are do does did can will "
    "not yes and need want have has this that yesterday today sales machine money card hello "
    "thanks please all ignore previous instructions from to".split()
)

REFUSALS = {
    "en": "I'm sorry, but I can't help with that request. I can help with Getnet products and "
    "services, your receivables and card machine, or general factual questions.",
    "pt": "Sinto muito, mas não posso ajudar com esse pedido. Posso ajudar com produtos e serviços "
    "da Getnet, seus recebíveis e sua maquininha, ou com perguntas factuais gerais.",
}
LENGTH_REFUSALS = {
    "en": "I'm sorry, but your message is too long. Please send a shorter message, up to {limit} "
    "characters.",
    "pt": "Sinto muito, mas sua mensagem é muito longa. Envie uma mensagem mais curta, de até "
    "{limit} caracteres.",
}


@dataclass
class GuardrailResult:
    masked_message: str
    language: Language
    refusal: str | None = None
    refusal_reason: str | None = None


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def luhn_valid(digits: str) -> bool:
    total = 0
    for i, char in enumerate(reversed(digits)):
        value = int(char)
        if i % 2 == 1:
            value = value * 2 - 9 if value > 4 else value * 2
        total += value
    return total % 10 == 0


def cpf_valid(digits: str) -> bool:
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    for size in (9, 10):
        total = sum(int(digits[i]) * (size + 1 - i) for i in range(size))
        if (total * 10 % 11) % 10 != int(digits[size]):
            return False
    return True


def mask_sensitive(text: str) -> str:
    def mask_card(match: re.Match) -> str:
        digits = re.sub(r"\D", "", match.group())
        return CARD_MASK if luhn_valid(digits) else match.group()

    text = CPF_FORMATTED.sub(CPF_MASK, text)
    text = CARD_CANDIDATE.sub(mask_card, text)
    return CPF_BARE.sub(lambda m: CPF_MASK if cpf_valid(m.group()) else m.group(), text)


def has_injection(text: str) -> bool:
    normalized = _normalize(text)
    return any(pattern.search(normalized) for pattern in INJECTION_PATTERNS)


def detect_language(text: str) -> Language:
    """Used when no Router language is available. Falls back to Portuguese."""
    words = re.findall(r"[a-z']+", _normalize(text))
    pt_score = sum(w in PT_WORDS for w in words)
    en_score = sum(w in EN_WORDS for w in words)
    return "en" if en_score > pt_score else "pt"


def run_guardrails(message: str, max_chars: int) -> GuardrailResult:
    masked = mask_sensitive(message)
    language = detect_language(masked)
    if len(message) > max_chars:
        return GuardrailResult(
            masked, language, LENGTH_REFUSALS[language].format(limit=max_chars), "message_too_long"
        )
    if has_injection(masked):
        return GuardrailResult(masked, language, REFUSALS[language], "prompt_injection")
    return GuardrailResult(masked, language)
