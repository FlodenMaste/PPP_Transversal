"""
Consentement humain obligatoire pour toute execution d'outil (A.6).

Exigences du cahier des charges (partie A.6) :
  - « Chaque execution d'outil requiert le consentement explicite de
    l'utilisateur, les annotations de type destructiveHint n'etant pas
    considerees comme des barrieres suffisantes. »
  - (B.4) l'option d'autorisation permanente (« always allow ») est
    bannie : la confirmation est donc redemandee a chaque appel.

Trois canaux de confirmation sont pris en charge :
  1. elicitation : primitive MCP `elicitation/create`, la demande
     s'affiche dans l'IHM du client (Inspector) - canal officiel ;
  2. terminal    : confirmation clavier sur le serveur (demos en
     console, appels directs hors MCP) ;
  3. dry_run     : simulation journalisee, reservee aux tests
     automatises (jamais pour une demonstration reellement sensible).

Sans aucun canal disponible, le consentement est REFUSE (par defaut :
on n'execute rien).
"""

import sys

from server.config import CONSENT_MODE
from server.security.audit_log import log_action


class ConsentRefusedError(Exception):
    """Levaluateur humain a refuse, ou aucun canal de confirmation n'existe."""


_MESSAGE = (
    "CONSENTEMENT HUMAIN REQUIS\n"
    "Outil : {tool}\n"
    "Utilisateur : {user}\n"
    "Action : {action}\n"
    "Confirmez-vous l'execution ? (aucune autorisation permanente)"
)


def require_human_consent(
    action_description: str,
    user: str,
    tool: str,
    dry_run: bool = False,
) -> bool:
    """
    Confirmation en clavier sur le serveur (canal « terminal »).

    Ne propose JAMAIS d'option « toujours autoriser » (always allow),
    conformement au cahier des charges. En mode dry_run=True, simule la
    demande sans bloquer (tests automatises) et journalise la simulation.
    """
    if dry_run:
        log_action(
            user=user,
            tool=tool,
            params={"action": action_description},
            status="CONSENT_DRY_RUN",
            detail="Simulation sans execution reelle (tests uniquement)",
        )
        return True

    message = _MESSAGE.format(tool=tool, user=user, action=action_description)
    print(f"\n[VALIDATION HUMAINE REQUISE]\n{message}")
    response = input("Confirmer cette action ? (oui/non) : ").strip().lower()
    approved = response in ("oui", "o", "yes", "y")

    log_action(
        user=user,
        tool=tool,
        params={"action": action_description},
        status="VALIDEE_HUMAIN" if approved else "REFUSEE_HUMAIN",
        detail=f"Reponse operateur (canal terminal) : '{response}'",
    )

    if not approved:
        raise ConsentRefusedError(
            f"Action refusee par l'utilisateur : {action_description}"
        )

    return True


async def ensure_human_consent(
    *,
    user: str,
    tool: str,
    action: str,
    ctx=None,
    mode: str | None = None,
) -> None:
    """
    Consentement explicite OBLIGATOIRE avant chaque execution d'outil (A.6).

    Choix du canal :
      - CONSENT_MODE=elicitation (defaut) : demande via le client MCP
        (primitive elicitation). Si le client ne fournit pas de contexte
        (appel direct en console) et que le serveur tourne dans un
        terminal, bascule sur la confirmation clavier. Sans aucun canal,
        le consentement est refuse.
      - CONSENT_MODE=terminal : toujours la confirmation clavier.
      - CONSENT_MODE=dry_run  : simulation journalisee (tests).
      - CONSENT_MODE=deny     : refus systematique (test negatif).

    Lève ConsentRefusedError si l'utilisateur refuse ou si aucun canal
    de confirmation n'est disponible.
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

    # --- Canal 1 : elicitation MCP (IHM du client) ------------------------
    if ctx is not None and mode == "elicitation":
        try:
            from fastmcp.server.elicitation import AcceptedElicitation

            result = await ctx.elicit(
                message=_MESSAGE.format(tool=tool, user=user, action=action),
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
        raise ConsentRefusedError(
            f"Execution refusee par l'utilisateur : {action}"
        )

    # --- Canal 2 : confirmation clavier sur le serveur --------------------
    if mode == "terminal" or (mode == "elicitation" and sys.stdin.isatty()):
        require_human_consent(action, user, tool)
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
