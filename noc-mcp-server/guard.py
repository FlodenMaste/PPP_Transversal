"""
Barriere A.6 commune : consentement humain, journal d'audit, sorties
non fiables.

Exigences du cahier des charges (partie A.6) :
  - « Chaque execution d'outil requiert le consentement explicite de
    l'utilisateur, les annotations de type destructiveHint n'etant pas
    considerees comme des barrieres suffisantes. »
  - « ... toutes les actions alimentent un journal d'audit. »
  - « Les sorties d'outils sont traitees comme des entrees non fiables
    pour prevenir les injections indirectes. »

Le controle d'acces RBAC/JWT Keycloak (OIDC + OAuth 2.1/PKCE) est
implemente dans le depot mcp-noc-telecom (serveur 1) ; ce module apporte
aux trois autres serveurs les deux autres volets d'A.6 : consentement
systematique a chaque appel d'outil et journal d'audit horodate.

Modes de consentement (variable CONSENT_MODE) :
  elicitation : primitive MCP `elicitation/create` (defaut, canal officiel)
  terminal    : confirmation clavier sur le serveur (demonstration console)
  dry_run     : simulation journalisee, reservee aux tests automatises
  deny        : refus systematique (test negatif)

Sans aucun canal disponible, le consentement est REFUSE (fail-safe :
on n'execute rien). Il n'existe aucune autorisation permanente
(« always allow »), conformement au cahier.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import mcp.types as mt
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools.base import ToolResult

CONSENT_MODE = os.environ.get("CONSENT_MODE", "elicitation").strip().lower()
AUDIT_LOG_PATH = Path(
    os.environ.get("AUDIT_LOG_PATH", Path(__file__).resolve().parent / "audit.log")
)

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
    "community",
    "api_key",
}

_CONSENT_MESSAGE = (
    "CONSENTEMENT HUMAIN REQUIS\n"
    "Serveur : {server}\n"
    "Outil : {tool}\n"
    "Arguments : {action}\n"
    "Confirmez-vous l'execution ? (aucune autorisation permanente)"
)


class ConsentRefusedError(Exception):
    """L'humain a refuse, ou aucun canal de confirmation n'existe."""


def _scrub(value: Any, key: str = "") -> Any:
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


def log_action(user: str, tool: str, params: dict, status: str, detail: str = "") -> None:
    """Ecrit une ligne JSON dans le journal d'audit (jamais de secret)."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user": user,
        "tool": tool,
        "params": _scrub(params or {}),
        "status": status,
        "detail": detail,
    }
    try:
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except OSError:  # pragma: no cover - journal indisponible ne doit pas casser l'appel
        logging.getLogger("mcp_audit").exception("ecriture du journal d'audit impossible")


async def ensure_human_consent(
    *,
    user: str,
    tool: str,
    action: str,
    ctx: Any = None,
    server: str = "mcp-noc",
    mode: str | None = None,
) -> None:
    """
    Consentement explicite OBLIGATOIRE avant chaque execution d'outil (A.6).

    Lève ConsentRefusedError si l'utilisateur refuse ou si aucun canal de
    confirmation n'est disponible (fail-safe : rien n'est execute).
    """
    mode = (mode or CONSENT_MODE).strip().lower()

    if mode == "deny":
        log_action(
            user=user, tool=tool, params={"action": action},
            status="CONSENT_REFUSE", detail="CONSENT_MODE=deny (test negatif)",
        )
        raise ConsentRefusedError("Mode deny : toute execution est refusee.")

    if mode == "dry_run":
        log_action(
            user=user, tool=tool, params={"action": action},
            status="CONSENT_DRY_RUN",
            detail="Simulation de consentement (CONSENT_MODE=dry_run)",
        )
        return

    message = _CONSENT_MESSAGE.format(server=server, tool=tool, action=action)

    # --- Canal 1 : elicitation MCP (IHM du client) ------------------------
    if ctx is not None and mode == "elicitation":
        try:
            from fastmcp.server.elicitation import AcceptedElicitation

            result = await ctx.elicit(
                message=message,
                response_type=bool,
                response_title="Confirmer l'execution de l'outil",
            )
        except Exception as exc:
            log_action(
                user=user, tool=tool, params={"action": action},
                status="CONSENT_REFUSE",
                detail=f"Elicitation indisponible (client sans support) : {exc}",
            )
            raise ConsentRefusedError(
                "Consentement impossible : le client MCP ne sait pas "
                "confirmer l'execution (elicitation non prise en charge)."
            ) from exc

        if isinstance(result, AcceptedElicitation) and result.data is True:
            log_action(
                user=user, tool=tool, params={"action": action},
                status="VALIDEE_HUMAIN",
                detail="Confirmation explicite via elicitation MCP",
            )
            return

        log_action(
            user=user, tool=tool, params={"action": action},
            status="REFUSEE_HUMAIN",
            detail="Refus ou annulation via elicitation MCP",
        )
        raise ConsentRefusedError(f"Execution refusee par l'utilisateur : {action}")

    # --- Canal 2 : confirmation clavier sur le serveur --------------------
    if mode == "terminal" or (mode == "elicitation" and sys.stdin.isatty()):
        log_action(user=user, tool=tool, params={"action": action}, status="CONSENT_DEMANDE")
        print(f"\n[VALIDATION HUMAINE REQUISE]\n{message}")
        response = input("Confirmer cette action ? (oui/non) : ").strip().lower()
        approved = response in ("oui", "o", "yes", "y")
        log_action(
            user=user, tool=tool, params={"action": action},
            status="VALIDEE_HUMAIN" if approved else "REFUSEE_HUMAIN",
            detail=f"Reponse operateur (canal terminal) : '{response}'",
        )
        if not approved:
            raise ConsentRefusedError(f"Action refusee par l'utilisateur : {action}")
        return

    # --- Aucun canal : refus (on n'execute rien) --------------------------
    log_action(
        user=user, tool=tool, params={"action": action},
        status="CONSENT_REFUSE",
        detail=f"Aucun canal de consentement disponible (mode={mode})",
    )
    raise ConsentRefusedError(
        "Consentement humain impossible a obtenir : execution annulee."
    )


def mark_untrusted(result: ToolResult) -> ToolResult:
    """
    Marque une sortie d'outil comme non fiable (A.6 / B.6).

    Deux marqueurs : dans le payload structure (quand c'est un dictionnaire)
    et dans `meta` du resultat MCP, visible par tout client MCP.
    """
    structured = result.structured_content
    if isinstance(structured, dict) and "untrusted" not in structured:
        try:
            result.structured_content = {**structured, "untrusted": True}
            if isinstance(result.content, list) and len(result.content) == 1:
                block = result.content[0]
                if getattr(block, "type", None) == "text":
                    try:
                        payload = json.loads(block.text)
                        if isinstance(payload, dict) and "untrusted" not in payload:
                            block.text = json.dumps(
                                {**payload, "untrusted": True},
                                ensure_ascii=False,
                                default=str,
                            )
                    except (ValueError, TypeError):
                        pass
        except Exception:  # pragma: no cover - ne doit jamais casser la reponse
            pass

    meta = dict(result.meta or {})
    meta["untrusted"] = True
    meta["consent"] = "humain"
    result.meta = meta
    return result


async def _notify(ctx: Any, level: str, message: str) -> None:
    """Primitive logging MCP : notification de niveau envoyee au client.

    Un echec (client sans support, session fermee) ne doit jamais empecher
    l'appel d'outil : on logge localement en repli.
    """
    if ctx is None:
        return
    try:
        await getattr(ctx, level)(message)
    except Exception:  # pragma: no cover - notification best effort
        logging.getLogger("mcp_audit").debug("notification logging impossible")


class GuardMiddleware(Middleware):
    """
    Middleware A.6 applique a CHAQUE appel d'outil du serveur :
      1. consentement humain explicite (avant execution) ;
      2. ecriture au journal d'audit (demande, execution, resultat) ;
      3. notification de niveau au client (primitive logging, A.2) ;
      4. marquage de la sortie comme non fiable.
    """

    def __init__(self, server_name: str, user: str = "hote_mcp"):
        self.server_name = server_name
        self.user = user

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next,
    ) -> ToolResult:
        params = context.message
        tool = params.name
        arguments = dict(params.arguments or {})
        ctx = context.fastmcp_context
        action = json.dumps(_scrub(arguments), ensure_ascii=False, default=str)

        try:
            await ensure_human_consent(
                user=self.user,
                tool=tool,
                action=action,
                ctx=ctx,
                server=self.server_name,
            )
        except ConsentRefusedError as exc:
            log_action(
                user=self.user, tool=tool, params=arguments,
                status="EXECUTION_REFUSEE", detail=str(exc),
            )
            await _notify(
                ctx, "warning",
                f"{self.server_name} : execution de {tool} refusee ({exc})",
            )
            return ToolResult(
                content=[mt.TextContent(type="text", text=f"[CONSENTEMENT REFUSE] {exc}")],
                structured_content={"status": "refused", "tool": tool, "error": str(exc),
                                    "untrusted": True},
                is_error=True,
            )

        log_action(
            user=self.user, tool=tool, params=arguments,
            status="EXECUTION_AUTORISEE",
            detail=f"consentement={CONSENT_MODE}",
        )

        result = await call_next(context)
        result = mark_untrusted(result)
        log_action(
            user=self.user, tool=tool, params={},
            status="EXECUTION_ERREUR" if result.is_error else "EXECUTION_TERMINEE",
            detail=f"resultat_error={result.is_error}",
        )
        await _notify(
            ctx, "info",
            f"{self.server_name} : {tool} "
            f"{'en erreur' if result.is_error else 'execute'} (audit: "
            f"{'EXECUTION_ERREUR' if result.is_error else 'EXECUTION_TERMINEE'})",
        )
        return result
