import re

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"ignore\s+tes\s+instructions?\s+pr[ée]c[ée]dentes?",
    r"disregard\s+(all\s+)?(previous|prior|above)",
    r"you\s+are\s+now\s+",
    r"tu\s+es\s+maintenant\s+",
    r"new\s+instructions?\s*:",
    r"nouvelles?\s+instructions?\s*:",
    r"system\s*:",
    r"assistant\s*:",
    r"act\s+as\s+",
    r"<\|.*?\|>",
    r"###\s*(system|instruction)",
    r"forget\s+(everything|all)",
    r"oublie\s+(tout|tes\s+instructions)",
    r"execute\s+the\s+following\s+command",
    r"ex[ée]cute\s+la\s+commande\s+suivante",
]

COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

MAX_OUTPUT_LENGTH = 2000


def sanitize_untrusted_output(raw_text: str, source: str = "inconnu") -> dict:
    """
    Analyse un texte provenant d'une source non fiable (equipement reseau,
    log, banniere SNMP...) et le neutralise si des tentatives d'injection
    de prompt sont detectees. Retourne un dict structure, jamais le texte
    brut directement utilisable comme instruction par le LLM.
    """
    flags = []
    sanitized = raw_text

    for pattern in COMPILED_PATTERNS:
        matches = pattern.findall(raw_text)
        if matches:
            flags.append(pattern.pattern)
            sanitized = pattern.sub("[CONTENU_SUSPECT_NEUTRALISE]", sanitized)

    truncated = False
    if len(sanitized) > MAX_OUTPUT_LENGTH:
        sanitized = sanitized[:MAX_OUTPUT_LENGTH] + "...[TRONQUE]"
        truncated = True

    return {
        "source": source,
        "is_flagged": len(flags) > 0,
        "flags_detected": flags,
        "truncated": truncated,
        "sanitized_text": sanitized,
        "original_length": len(raw_text),
    }
