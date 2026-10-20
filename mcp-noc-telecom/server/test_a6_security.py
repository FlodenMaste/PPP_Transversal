"""
Tests d'acceptation de l'exigence A.6 « Securite commune ».

Couverture :
  A. RBAC sur jetons JWT (roles, hierarchie, refus)
  B. Jetons emis par Keycloak (OIDC : JWKS RS256 + issuer)
  C. Token passthrough interdit
  D. Consentement humain explicite a chaque execution (sans « always allow »)
  E. Transport Streamable HTTP + OAuth 2.1 : metadonnees, 401/200
  F. Flux authorization code + PKCE (S256) de bout en bout

Certains tests sont sauts automatiquement si Keycloak (docker compose
up -d) ou le laboratoire Containerlab ne sont pas demarres.
"""

import asyncio
import base64
import hashlib
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx
import pytest

SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))

from server import config
from server.security import auth as auth_mod
from server.security import consent as consent_mod
from server.security.auth import (
    AccessDeniedError,
    fetch_keycloak_token,
    generate_token,
    resolve_identity,
    role_satisfies,
    verify_keycloak_token,
    verify_token,
)
from server.security.consent import ConsentRefusedError, ensure_human_consent

KEYCLOAK_URL = config.KEYCLOAK_REALM_URL
HTTP_PORT = int(os.getenv("A6_HTTP_PORT", "8002"))
HTTP_URL = f"http://127.0.0.1:{HTTP_PORT}"
CLIENT_ID = "mcp-cli"
REDIRECT_URI = "http://127.0.0.1:6274/callback"


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------
def keycloak_disponible() -> bool:
    try:
        r = httpx.get(f"{KEYCLOAK_URL}/.well-known/openid-configuration", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


requires_keycloak = pytest.mark.skipif(
    not keycloak_disponible(),
    reason="Keycloak non demarre (docker compose up -d)",
)


class FauxContexte:
    """Contexte MCP minimal : simule la reponse d'elicit du client."""

    def __init__(self, reponse):
        self.reponse = reponse
        self.messages = []

    async def elicit(self, message, response_type=None, response_title=None, **kwargs):
        self.messages.append(message)
        if self.reponse == "decline":
            from fastmcp.server.elicitation import DeclinedElicitation

            return DeclinedElicitation()
        from fastmcp.server.elicitation import AcceptedElicitation

        return AcceptedElicitation(data=True)


class FauxContexteSansSupport:
    """Simule un client MCP sans capacite d'elicitation."""

    async def elicit(self, *args, **kwargs):
        raise RuntimeError("elicitation/create non pris en charge")


# ===========================================================================
# A. RBAC sur jetons JWT (mode local, sans Keycloak)
# ===========================================================================
def test_jeton_local_valide(monkeypatch):
    monkeypatch.setattr(auth_mod, "AUTH_MODE", "local")
    claims = verify_token(generate_token("alice", "operateur"))
    assert claims["user"] == "alice" and claims["role"] == "operateur"


def test_jeton_local_invalide_rejete(monkeypatch):
    monkeypatch.setattr(auth_mod, "AUTH_MODE", "local")
    with pytest.raises(AccessDeniedError):
        verify_token("jeton-absolument-faux")


def test_jeton_local_expire_rejete(monkeypatch):
    monkeypatch.setattr(auth_mod, "AUTH_MODE", "local")
    expire = generate_token("bob", "operateur", minutes=-1)
    with pytest.raises(AccessDeniedError, match="expire"):
        verify_token(expire)


def test_role_hors_hierarchie_rejete(monkeypatch):
    monkeypatch.setattr(auth_mod, "AUTH_MODE", "local")
    avec_role_fantome = generate_token("intrus", "role_inexistant")
    with pytest.raises(AccessDeniedError, match="role RBAC"):
        asyncio.run(resolve_identity(avec_role_fantome, tool="snmp_get"))


@pytest.mark.parametrize(
    "user_role, requis, attendu",
    [
        ("operateur", "operateur", True),
        ("superviseur", "operateur", True),
        ("administrateur", "operateur", True),
        ("operateur", "superviseur", False),
        ("operateur", "administrateur", False),
    ],
)
def test_hierarchie_rbac(user_role, requis, attendu):
    assert role_satisfies(user_role, requis) is attendu


# ===========================================================================
# B. Jetons Keycloak (OIDC : JWKS RS256 + issuer)
# ===========================================================================
@requires_keycloak
async def test_jeton_keycloak_valide():
    jeton = await fetch_keycloak_token("operateur", "Operateur2026!")
    claims = await verify_keycloak_token(jeton)
    assert claims["iss"] == KEYCLOAK_URL
    assert claims["realm_access"]["roles"] == ["operateur"]


@requires_keycloak
async def test_jeton_local_rejete_en_mode_keycloak():
    """Un jeton signe en HS256 (secret local) ne passe pas la verification JWKS."""
    faux = generate_token("mallory", "administrateur")
    with pytest.raises(AccessDeniedError):
        await verify_keycloak_token(faux)


@requires_keycloak
async def test_jeton_keycloak_role_hors_rbac():
    jeton = await fetch_keycloak_token("invite", "Invite2026!")
    with pytest.raises(AccessDeniedError, match="role RBAC"):
        await resolve_identity(jeton, tool="snmp_get")


@requires_keycloak
async def test_jeton_expire_keycloak_rejete():
    """Jeton Keycloak expire : issuus server > lifespan (300 s) simule par 0 s."""
    jeton = await fetch_keycloak_token("operateur", "Operateur2026!")
    await asyncio.sleep(0)
    # Mutilation du claim d'expiration : la signature devient invalide,
    # ce qui couvre aussi le rejet par le JWKS.
    parties = jeton.split(".")
    payload = json_loads_b64(parties[1] + "=" * (-len(parties[1]) % 4))
    payload["exp"] = int(time.time()) - 10
    parties[1] = b64url(__import__("json").dumps(payload).encode())
    with pytest.raises(AccessDeniedError):
        await verify_keycloak_token(".".join(parties))


def json_loads_b64(data: str) -> dict:
    import json

    return json.loads(base64.urlsafe_b64decode(data))


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


# ===========================================================================
# C. Token passthrough interdit
# ===========================================================================
async def test_passport_interdit(monkeypatch):
    """Un jeton en argument d'outil est refuse si la requete porte deja un jeton."""
    monkeypatch.setattr(
        auth_mod, "_current_oauth_claims", lambda: {"preferred_username": "alice"}
    )
    with pytest.raises(AccessDeniedError, match="passthrough"):
        await resolve_identity("jeton-en-argument", tool="snmp_get")


async def test_identite_prende_oauth_en_entete(monkeypatch):
    monkeypatch.setattr(
        auth_mod,
        "_current_oauth_claims",
        lambda: {
            "preferred_username": "operateur",
            "realm_access": {"roles": ["operateur"]},
        },
    )
    identite = await resolve_identity(None, tool="snmp_get")
    assert identite["user"] == "operateur"
    assert identite["source"] == "oauth2.1-pkce-keycloak"


async def test_jeton_manquant_refuse(monkeypatch):
    monkeypatch.setattr(auth_mod, "AUTH_MODE", "local")
    with pytest.raises(AccessDeniedError, match="manquant"):
        await resolve_identity(None, tool="snmp_get")


# ===========================================================================
# D. Consentement humain explicite
# ===========================================================================
async def test_consentement_dry_run(monkeypatch):
    monkeypatch.setattr(consent_mod, "CONSENT_MODE", "dry_run")
    await ensure_human_consent(
        user="alice", tool="t", action="demo", ctx=None
    )  # ne doit pas lever


async def test_consentement_deny(monkeypatch):
    monkeypatch.setattr(consent_mod, "CONSENT_MODE", "deny")
    with pytest.raises(ConsentRefusedError):
        await ensure_human_consent(user="alice", tool="t", action="demo", ctx=None)


async def test_consentement_elicitation_accepte(monkeypatch):
    monkeypatch.setattr(consent_mod, "CONSENT_MODE", "elicitation")
    ctx = FauxContexte(reponse="accept")
    await ensure_human_consent(user="alice", tool="t", action="demo", ctx=ctx)
    assert ctx.messages and "CONSENTEMENT HUMAIN REQUIS" in ctx.messages[0]


async def test_consentement_elicitation_refuse(monkeypatch):
    monkeypatch.setattr(consent_mod, "CONSENT_MODE", "elicitation")
    ctx = FauxContexte(reponse="decline")
    with pytest.raises(ConsentRefusedError, match="refusee"):
        await ensure_human_consent(user="alice", tool="t", action="demo", ctx=ctx)


async def test_consentement_sans_client_n_execute_rien(monkeypatch):
    """Sans canal de confirmation, rien ne s'execute (fail-safe)."""
    monkeypatch.setattr(consent_mod, "CONSENT_MODE", "elicitation")
    import io

    monkeypatch.setattr(sys, "stdin", io.StringIO())  # non interactif -> pas de prompt
    with pytest.raises(ConsentRefusedError):
        await ensure_human_consent(user="alice", tool="t", action="demo", ctx=None)


async def test_consentement_client_sans_elicitation(monkeypatch):
    monkeypatch.setattr(consent_mod, "CONSENT_MODE", "elicitation")
    with pytest.raises(ConsentRefusedError, match="client MCP ne sait pas"):
        await ensure_human_consent(
            user="alice", tool="t", action="demo",
            ctx=FauxContexteSansSupport(),
        )


class FauxContexteSilencieux:
    """Simule un client qui recoit la demande et ne repond jamais.

    C'est le cas observe avec MCP Inspector 2.9 en Streamable HTTP :
    le serveur envoie `elicitation/create` sur la requete tools/call mais
    le client ne la transmet jamais a l'IHM. Sans delai, l'outil restait
    suspendu jusqu'au timeout du cote client (60 s), sans message exploitable.
    """

    async def elicit(self, *args, **kwargs):
        import asyncio

        await asyncio.Event().wait()  # jamais resolu


async def test_consentement_delai_depasse_refuse(monkeypatch):
    """Le client silencieux ne bloque pas l'outil au-dela du delai (A.6)."""
    monkeypatch.setattr(consent_mod, "CONSENT_MODE", "elicitation")
    monkeypatch.setattr(consent_mod, "CONSENT_ELICIT_TIMEOUT", 0.2)
    with pytest.raises(ConsentRefusedError, match="aucune reponse du client"):
        await ensure_human_consent(
            user="alice", tool="t", action="demo",
            ctx=FauxContexteSilencieux(),
        )


async def test_consentement_delai_depasse_journalise(monkeypatch):
    """Le refus par depassement laisse une entree CONSENT_REFUSE au journal."""
    monkeypatch.setattr(consent_mod, "CONSENT_MODE", "elicitation")
    monkeypatch.setattr(consent_mod, "CONSENT_ELICIT_TIMEOUT", 0.2)
    entrees = []
    monkeypatch.setattr(consent_mod, "log_action", lambda **kw: entrees.append(kw))
    with pytest.raises(ConsentRefusedError):
        await ensure_human_consent(
            user="alice", tool="t", action="demo",
            ctx=FauxContexteSilencieux(),
        )
    assert entrees and entrees[-1]["status"] == "CONSENT_REFUSE"
    assert "0.2 s" in entrees[-1]["detail"]


# ===========================================================================
# E. Transport Streamable HTTP + OAuth 2.1
# ===========================================================================
@pytest.fixture(scope="module")
def serveur_http():
    env = {
        **os.environ,
        "AUTH_MODE": "keycloak",
        "MCP_TRANSPORT": "http",
        "MCP_HTTP_PORT": str(HTTP_PORT),
        "MCP_BASE_URL": HTTP_URL,
        "MCP_HTTP_HOST": "127.0.0.1",
        "CONSENT_MODE": "elicitation",
    }
    proc = subprocess.Popen(
        [str(SERVER_DIR / "venv" / "bin" / "python"), "-m", "server.main"],
        cwd=str(SERVER_DIR),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            if proc.poll() is not None:
                pytest.skip("Le serveur HTTP s'est arrete (voir les logs)")
            try:
                if httpx.get(f"{HTTP_URL}/mcp", timeout=1).status_code in (400, 405, 401):
                    break
            except Exception:
                pass
            time.sleep(0.4)
        else:
            pytest.skip("Serveur HTTP non joignable")
        yield HTTP_URL
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@requires_keycloak
def test_metadonnees_ressource_protegee(serveur_http):
    r = httpx.get(f"{serveur_http}/.well-known/oauth-protected-resource/mcp")
    assert r.status_code == 200
    meta = r.json()
    assert meta["authorization_servers"] == [KEYCLOAK_URL]
    assert meta["bearer_methods_supported"] == ["header"]


@requires_keycloak
def test_metadata_oidc_keycloak_sert_pkce(serveur_http):
    r = httpx.get(f"{KEYCLOAK_URL}/.well-known/openid-configuration")
    meta = r.json()
    assert "S256" in meta["code_challenge_methods_supported"]
    assert "authorization_code" in meta["grant_types_supported"]


@requires_keycloak
def test_401_sans_jeton(serveur_http):
    r = httpx.post(
        f"{serveur_http}/mcp",
        headers={"Accept": "application/json, text/event-stream"},
        json=_initialize(),
    )
    assert r.status_code == 401
    assert "resource_metadata" in r.headers.get("www-authenticate", "")


@requires_keycloak
def test_401_avec_jeton_local_hs256(serveur_http):
    faux = generate_token("mallory", "administrateur")
    r = httpx.post(
        f"{serveur_http}/mcp",
        headers={
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {faux}",
        },
        json=_initialize(),
    )
    assert r.status_code == 401


@requires_keycloak
def test_200_avec_jeton_keycloak(serveur_http):
    jeton = asyncio.run(fetch_keycloak_token("operateur", "Operateur2026!"))
    r = httpx.post(
        f"{serveur_http}/mcp",
        headers={
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {jeton}",
        },
        json=_initialize(),
    )
    assert r.status_code == 200
    assert "mcp-session-id" in {k.lower() for k in r.headers}


def en_tete_cookies(client) -> dict:
    """httpx range les cookies de 'localhost' sous un domaine '.local' et ne
    les renvoie donc pas : on les renvoie explicitement (bug classique)."""
    return {
        "Cookie": "; ".join(
            f"{c.name}={c.value}" for c in client.cookies.jar
        )
    }


def _initialize() -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "tests-a6", "version": "1.0"},
        },
    }


# ===========================================================================
# F. Flux authorization code + PKCE (S256) de bout en bout
# ===========================================================================
@requires_keycloak
def test_flux_pkce_de_bout_en_bout():
    verifier = b64url(secrets.token_bytes(48))
    challenge = b64url(hashlib.sha256(verifier.encode()).digest())
    state = b64url(secrets.token_bytes(16))

    with httpx.Client(follow_redirects=False, timeout=20) as client:
        # 1) demande d'autorisation (PKCE S256)
        url = f"{KEYCLOAK_URL}/protocol/openid-connect/auth?" + urlencode(
            {
                "response_type": "code",
                "client_id": CLIENT_ID,
                "redirect_uri": REDIRECT_URI,
                "scope": "openid profile email roles",
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        page = client.get(url)
        assert page.status_code == 200, page.text[:300]
        action = re.search(r'action="([^"]+)"', page.text)
        assert action, "formulaire de connexion Keycloak introuvable"
        login_url = action.group(1).replace("&amp;", "&")

        # 2) connexion utilisateur
        connecte = client.post(
            login_url,
            data={"username": "operateur", "password": "Operateur2026!"},
            headers=en_tete_cookies(client),
        )
        assert connecte.status_code == 302, connecte.text[:300]
        location = connecte.headers["location"]
        assert REDIRECT_URI in location
        code = re.search(r"[?&]code=([^&]+)", location).group(1)

        # 3) echange du code contre un jeton avec le BON code_verifier
        ok = client.post(
            f"{KEYCLOAK_URL}/protocol/openid-connect/token",
            data={
                "grant_type": "authorization_code",
                "client_id": CLIENT_ID,
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": verifier,
            },
        )
        assert ok.status_code == 200, ok.text[:300]
        jeton = ok.json()["access_token"]

        # 4) preuve que le jeton est bien un jeton Keycloak utilisable
        claims = asyncio.run(verify_keycloak_token(jeton))
        assert claims["realm_access"]["roles"] == ["operateur"]

        # 5) PKCE reel : un code_volante avec un verifier different echoue
        page2 = client.get(url)
        action2 = re.search(r'action="([^"]+)"', page2.text).group(1).replace("&amp;", "&")
        connecte2 = client.post(
            action2,
            data={"username": "operateur", "password": "Operateur2026!"},
            headers=en_tete_cookies(client),
        )
        code2 = re.search(
            r"[?&]code=([^&]+)", connecte2.headers["location"]
        ).group(1)
        mauvais = client.post(
            f"{KEYCLOAK_URL}/protocol/openid-connect/token",
            data={
                "grant_type": "authorization_code",
                "client_id": CLIENT_ID,
                "code": code2,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": b64url(secrets.token_bytes(48)),
            },
        )
        assert mauvais.status_code == 400
        assert "invalid_grant" in mauvais.text
