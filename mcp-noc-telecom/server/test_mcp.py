"""
Test de bout en bout du serveur MCP via un client stdio.

Lance le serveur, liste les outils, puis appelle chacun d'entre eux :
  - jeton delivre par Keycloak (AUTH_MODE=keycloak, defaut) ou jeton
    local (AUTH_MODE=local) ;
  - chaque appel declenche une demande de consentement humain
    (elicitation) : repondre "oui" pour continuer.

Usage :
    python test_mcp.py
    CONSENT_MODE=dry_run python test_mcp.py    # sans confirmation
    AUTH_MODE=local python test_mcp.py         # sans Keycloak
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from fastmcp import Client
from fastmcp.client.elicitation import ElicitResult
from fastmcp.client.transports import StdioTransport

SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))

from server.config import AUTH_MODE
from server.security.auth import fetch_keycloak_token, generate_token

# Utilisateurs du realm mcp-noc (voir security/keycloak/realm-mcp.json)
KEYCLOAK_USERS = {
    "operateur": ("operateur", "Operateur2026!"),
    "hors_rbac": ("invite", "Invite2026!"),
}


async def make_token(role: str = "operateur") -> str:
    if AUTH_MODE == "keycloak":
        user, password = KEYCLOAK_USERS.get(
            role if role in KEYCLOAK_USERS else "operateur",
            KEYCLOAK_USERS["operateur"] if role == "operateur" else ("invite", "Invite2026!"),
        )
        if role == "role_inexistant":
            user, password = KEYCLOAK_USERS["hors_rbac"]
        return await fetch_keycloak_token(user, password)
    if role == "role_inexistant":
        return generate_token("intrus", "role_inexistant")
    return generate_token(f"test-{role}", role)


async def consentement(message, response_type, params, context):
    """Consentement humain : demande affichee dans le terminal."""
    print("\n[CONSENTEMENT HUMAIN REQUIS]")
    print(message)
    if os.getenv("AUTO_CONSENT") == "1":
        return True
    reponse = input("Confirmer l'execution ? (oui/non) : ").strip().lower()
    if reponse in ("oui", "o", "yes", "y"):
        return True
    return ElicitResult(action="decline")


def show(titre: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {titre}")
    print("=" * 70)


async def main() -> None:
    transport = StdioTransport(
        command=str(SERVER_DIR / "venv" / "bin" / "python"),
        args=["-m", "server.main"],
        cwd=str(SERVER_DIR),
        # Le SDK MCP ne transmet qu'une liste blanche d variables
        # d'environnement : on transmet explicitement AUTH_MODE,
        # CONSENT_MODE, KEYCLOAK_REALM_URL, etc.
        env={**os.environ},
    )

    async with Client(transport, elicitation_handler=consentement) as client:
        show("CONTEXTE")
        print(f"AUTH_MODE={AUTH_MODE}  CONSENT_MODE={os.getenv('CONSENT_MODE', 'elicitation')}")

        show("INVENTAIRE DES OUTILS")
        token = await make_token("operateur")
        for tool in await client.list_tools():
            schema = tool.inputSchema if hasattr(tool, "inputSchema") else tool.input_schema
            required = schema.get("required", [])
            print(f"- {tool.name}  (requis : {', '.join(required) or 'aucun'})")

        show("OUTIL 1 : get_syslog_message (scenario normal)")
        result = await client.call_tool(
            "get_syslog_message", {"token": token, "scenario": "normal"}
        )
        print(result.content[0].text)

        show("OUTIL 2 : get_syslog_message (scenario piege / injection)")
        result = await client.call_tool(
            "get_syslog_message", {"token": token, "scenario": "piege"}
        )
        print(result.content[0].text)

        show("OUTIL 3 : snmp_get (requiert le labo Containerlab)")
        result = await client.call_tool("snmp_get", {"token": token, "router": "r1"})
        print(result.content[0].text)

        show("OUTIL 4 : role hors RBAC (refus attendu)")
        bad_token = await make_token("role_inexistant")
        try:
            result = await client.call_tool(
                "snmp_get", {"token": bad_token, "router": "r1"}
            )
            print(f"isError={result.isError} -> {result.content[0].text}")
        except Exception as exc:
            print(f"ACCES REFUSE (attendu) : {type(exc).__name__}: {exc}")

        show("OUTIL 5 : appel sans jeton (refus attendu)")
        try:
            result = await client.call_tool("snmp_get", {"router": "r1"})
            print(f"isError={result.isError} -> {result.content[0].text}")
        except Exception as exc:
            print(f"ACCES REFUSE (attendu) : {type(exc).__name__}: {exc}")

        show("JOURNAL D'AUDIT (6 dernieres entrees)")
        audit = SERVER_DIR / "audit.log"
        if audit.exists():
            for line in audit.read_text(encoding="utf-8").splitlines()[-6:]:
                entry = json.loads(line)
                print(f"{entry['status']:<28} {entry['user']:<16} {entry['tool']}")

    print("\nTest termine.")


if __name__ == "__main__":
    asyncio.run(main())
