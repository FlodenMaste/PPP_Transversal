import json
import logging
from datetime import datetime, timezone
from pathlib import Path

AUDIT_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "audit.log"

# Cles jamais journalisees (B.6 : les secrets ne quittent jamais le process)
SENSITIVE_KEYS = {
    "token",
    "password",
    "passwd",
    "secret",
    "authorization",
    "access_token",
    "refresh_token",
    "jwt",
    "auth_key",
    "priv_key",
}

logger = logging.getLogger("mcp_audit")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.FileHandler(AUDIT_LOG_PATH, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


def _scrub(value, key: str = ""):
    """Retire les secrets et les objets non serialisables d'un parametre."""
    if key.lower() in SENSITIVE_KEYS:
        return "***REDAIGNE***"
    if isinstance(value, dict):
        return {k: _scrub(v, k) for k, v in value.items() if k.lower() != "ctx"}
    if isinstance(value, (list, tuple)):
        return [_scrub(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return f"<{type(value).__name__}>"


def log_action(user: str, tool: str, params: dict, status: str, detail: str = ""):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user": user,
        "tool": tool,
        "params": _scrub(params or {}),
        "status": status,
        "detail": detail,
    }
    logger.info(json.dumps(entry, ensure_ascii=False, default=str))
