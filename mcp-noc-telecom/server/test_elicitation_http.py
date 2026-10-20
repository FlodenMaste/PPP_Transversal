"""Bout en bout de la chaine de consentement (A.6) cote client HTTP.

Sequence completee par ce script, dans cet ordre :
  1. parcours OAuth 2.1 + PKCE S256 (client public « mcp-cli », redirection
     vers /callback) pour obtenir un jeton operateur dans Keycloak ;
  2. connexion au serveur MCP en Streamable HTTP avec le jeton ;
  3. tools/list ;
  4. tools/call `snmp_get` : le serveur envoie `elicitation/create`, le
     client repond « accepter » et l'outil s'execute reellement (sysDescr
     de r1 retourne par SNMPv3).

C'est la demonstration du consentement humain explicite, distincte du
mode « terminal » et du mode « dry_run » (tests automatises).

Pourquoi ce script existe : MCP Inspector 2.9 (transport Streamable HTTP)
ne transmet jamais la demande d'elicitation a son IHM ; l'appel d'outil
ressemble alors a un blocage. Le serveur le borne par CONSENT_ELICIT_TIMEOUT
(45 s par defaut) et REFUSE le consentement avec un message explicite au lieu
de rester suspendu. Ce script utilise le client officiel FastMCP, qui sait
repondre a `elicitation/create` : la chaine completee y est donc verifiable.

Usage :
    ./venv/bin/python -u test_elicitation_http.py [url_mcp]
    # serveur requis : MCP_TRANSPORT=http ./venv/bin/python -m server.main
Sortie : code 0 si consentement recu, outil execute et resultat non vide.
"""
import asyncio
import base64
import hashlib
import html
import re
import secrets
import sys

import httpx
from fastmcp import Client
from fastmcp.client.elicitation import ElicitResult
from fastmcp.client.transports import StreamableHttpTransport

REALM = "http://localhost:18080/realms/mcp-noc"
MCP = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001/mcp"
CALLBACK = MCP.rsplit("/mcp", 1)[0] + "/callback"

ELICIT_SEEN = []


def _b64u(octets: bytes) -> str:
    return base64.urlsafe_b64encode(octets).rstrip(b"=").decode()


def _login(user: str, mot_de_passe: str) -> str:
    """Parcours authorization_code + PKCE S256 (sans navigateur)."""
    verifier = _b64u(secrets.token_bytes(64))
    challenge = _b64u(hashlib.sha256(verifier.encode()).digest())
    state = _b64u(secrets.token_bytes(16))

    http = httpx.Client(timeout=20, follow_redirects=False)
    page = http.get(
        f"{REALM}/protocol/openid-connect/auth",
        params={
            "client_id": "mcp-cli",
            "redirect_uri": CALLBACK,
            "response_type": "code",
            "scope": "openid profile email roles",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
    )
    cookies = "; ".join(f"{c.name}={c.value}" for c in http.cookies.jar)
    action = html.unescape(
        re.search(r'<form[^>]*action="([^"]+)"', page.text).group(1)
    )
    suivant = httpx.post(
        action, timeout=20, follow_redirects=False, headers={"Cookie": cookies},
        data={"username": user, "password": mot_de_passe, "credentialId": ""},
    )
    code = re.search(r"[?&]code=([^&]+)", suivant.headers["location"]).group(1)
    jeton = httpx.post(
        f"{REALM}/protocol/openid-connect/token", timeout=20,
        data={"grant_type": "authorization_code", "client_id": "mcp-cli",
              "code": code, "redirect_uri": CALLBACK, "code_verifier": verifier},
    )
    jeton.raise_for_status()
    return jeton.json()["access_token"]


async def _on_elicitation(message, response_type, params, context):
    ELICIT_SEEN.append(message)
    print(f"  [ELICITATION RECUE] {message.splitlines()[0]}", flush=True)
    return ElicitResult(action="accept", content={"value": True})


async def main() -> int:
    jeton = _login("operateur", "Operateur2026!")
    print("[1] OAuth 2.1 + PKCE S256 -> jeton operateur", flush=True)

    transport = StreamableHttpTransport(
        url=MCP, headers={"Authorization": f"Bearer {jeton}"}
    )
    async with Client(transport, elicitation_handler=_on_elicitation) as client:
        info = client.initialize_result
        serveur = getattr(info, "serverInfo", None)
        print(f"[2] connecte a {serveur.name} v{serveur.version}", flush=True)

        outils = await client.list_tools()
        print(f"[3] tools/list -> {len(outils)} outils", flush=True)

        print("[4] tools/call snmp_get (consentement humain requis)...", flush=True)
        resultat = await client.call_tool(
            "snmp_get", {"router": "r1", "oid": ".1.3.6.1.2.1.1.1.0"}
        )
        texte = resultat.content[0].text if resultat.content else ""
        erreur = getattr(resultat, "isError", False)
        print(f"[5] RESULTAT -> isError={erreur}", flush=True)
        print(f"    {texte[:500]}", flush=True)

    ok = bool(texte) and not erreur and len(ELICIT_SEEN) == 1
    print(
        f"[6] demandes d'elicitation recues : {len(ELICIT_SEEN)} "
        f"-> {'OK' if ok else 'ECHEC'}",
        flush=True,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
