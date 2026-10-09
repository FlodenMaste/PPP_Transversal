"""
Outils de supervision SNMPv3 (lecture seule) - cahier B.5/B.6.

Chaque outil est protege par @require_role (RBAC sur jeton JWT Keycloak)
et par le consentement humain obligatoire (A.6).
"""

import asyncio
import subprocess

from fastmcp.server.context import Context

from server.config import SNMP_AUTH_PASS, SNMP_PRIV_PASS, SNMP_USER
from server.security.audit_log import log_action
from server.security.auth import require_role
from server.security.sanitizer import sanitize_untrusted_output

KNOWN_ROUTERS = {
    "r1": "192.168.1.1",
    "r2": "2.2.2.2",
    "r3": "3.3.3.3",
}


def _snmp_walk(router: str, oid: str) -> dict:
    """Requete snmpwalk lancee depuis le conteneur client du laboratoire."""
    target_ip = KNOWN_ROUTERS[router]

    command = [
        "docker", "exec", "clab-mcp-noc-lab-client",
        "snmpwalk", "-v3", "-l", "authPriv",
        "-u", SNMP_USER,
        "-a", "SHA", "-A", SNMP_AUTH_PASS,
        "-x", "AES", "-X", SNMP_PRIV_PASS,
        target_ip, oid,
    ]

    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout : le routeur n'a pas repondu."}
    except FileNotFoundError as exc:
        return {
            "success": False,
            "error": f"Docker indisponible : {exc}. Le labo est-il deploye ?",
        }

    if result.returncode != 0:
        return {
            "success": False,
            "error": f"Echec de la requete SNMP : {result.stderr.strip()}",
        }

    return {
        "success": True,
        "router": router,
        "oid": oid,
        "raw_output": result.stdout.strip(),
    }


@require_role("operateur")
async def snmp_get(
    router: str, oid: str = ".1.3.6.1.2.1.1", ctx: Context = None
) -> dict:
    """
    Requete SNMPv3 (authPriv, lecture seule) sur un routeur du labo.

    La requete est executee depuis le conteneur client du laboratoire
    Containerlab, ce qui impose que le labo soit deploye au prealable.

    Args:
        router: Identifiant du routeur (r1, r2 ou r3).
        oid: OID de depart du walk SNMP (defaut : branche system).
        ctx: Contexte MCP (injection automatique, utilise pour le
            consentement humain via elicitation).
    """
    if router not in KNOWN_ROUTERS:
        return {
            "success": False,
            "error": f"Routeur inconnu : '{router}'. Valeurs possibles : {list(KNOWN_ROUTERS)}",
        }

    return await asyncio.to_thread(_snmp_walk, router, oid)


@require_role("operateur")
async def snmp_get_secure(
    router: str, oid: str = ".1.3.6.1.2.1.1", ctx: Context = None
) -> dict:
    """
    Identique a snmp_get, mais fait passer la sortie de l'equipement
    reseau (entree non fiable) par la couche de neutralisation avant
    de la retourner au LLM (A.6 : sorties d'outils non fiables).
    """
    raw_result = await snmp_get.__wrapped__(router, oid)

    if not raw_result.get("success"):
        return raw_result

    analysis = sanitize_untrusted_output(
        raw_result["raw_output"], source=f"snmp-{router}"
    )

    if analysis["is_flagged"]:
        log_action(
            user="systeme",
            tool="snmp_get_secure",
            params={"router": router},
            status="ALERTE_INJECTION_NEUTRALISEE",
            detail=f"Patterns detectes : {analysis['flags_detected']}",
        )

    return {
        "success": True,
        "router": router,
        "oid": oid,
        "output": analysis["sanitized_text"],
        "injection_detectee": analysis["is_flagged"],
    }
