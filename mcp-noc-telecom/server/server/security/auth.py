"""
Authentification et autorisation (RBAC) du serveur MCP - cahier A.6.

Deux sources de jetons JWT sont prises en charge :

  1. keycloak (defaut) : jetons emis par Keycloak (OIDC), verifies
     cote serveur contre le JWKS du realm (RS256 + issuer) - c'est
     l'exigence « RBAC adossé à des jetons JWT gérés par Keycloak (OIDC) ».
     Sur transport Streamable HTTP, le jeton OAuth 2.1 (+ PKCE) est
     porte par l'en-tete Authorization et valide par FastMCP avant meme
     d'atteindre l'outil : le serveur ne le retransmet jamais (A.6 :
     token passthrough interdit).

  2. local : jetons signes en HS256 avec JWT_SECRET, pour les
     demonstrations et tests hors ligne (sans Keycloak).

Dans les deux cas, le role effectif est le plus haut role de
ROLE_HIERARCHY present dans le jeton.
"""

import functools
import inspect
from datetime import datetime, timedelta, timezone

import jwt as pyjwt

from server.config import (
    AUTH_MODE,
    JWT_ALGORITHM,
    JWT_EXPIRATION_MINUTES,
    JWT_SECRET,
    KEYCLOAK_REALM_URL,
    ROLE_HIERARCHY,
    role_satisfies,
)
from server.security.audit_log import log_action
from server.security.consent import ensure_human_consent


class AccessDeniedError(Exception):
    """Jeton absent/invalide, ou role insuffisant."""


# ---------------------------------------------------------------------------
# 1. Verification locale (mode "local", HS256)
# ---------------------------------------------------------------------------
def verify_token(token: str) -> dict:
    try:
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except pyjwt.ExpiredSignatureError as exc:
        raise AccessDeniedError("Jeton expire. Veuillez en generer un nouveau.") from exc
    except pyjwt.InvalidTokenError as exc:
        raise AccessDeniedError("Jeton invalide ou signature incorrecte.") from exc

    if "user" not in payload or "role" not in payload:
        raise AccessDeniedError("Jeton mal forme (user/role manquant).")

    return payload


def generate_token(user: str, role: str, minutes: int | None = None) -> str:
    """Genere un jeton local HS256 (demo et tests hors Keycloak)."""
    payload = {
        "user": user,
        "role": role,
        "exp": datetime.now(timezone.utc)
        + timedelta(minutes=minutes or JWT_EXPIRATION_MINUTES),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


# ---------------------------------------------------------------------------
# 2. Verification Keycloak (OIDC : JWKS + issuer, RS256)
# ---------------------------------------------------------------------------
_keycloak_verifier = None


def get_keycloak_verifier():
    """Verificateur JWT cote serveur (cache) : JWKS + issuer du realm."""
    global _keycloak_verifier
    if _keycloak_verifier is None:
        from fastmcp.server.auth.providers.jwt import JWTVerifier

        _keycloak_verifier = JWTVerifier(
            jwks_uri=f"{KEYCLOAK_REALM_URL}/protocol/openid-connect/certs",
            issuer=KEYCLOAK_REALM_URL,
            algorithm="RS256",
        )
    return _keycloak_verifier


async def verify_keycloak_token(token: str) -> dict:
    """Verifie signature RS256 (JWKS), issuer et expiration du jeton Keycloak."""
    try:
        access = await get_keycloak_verifier().verify_token(token)
    except Exception as exc:  # noqa: BLE001 - toute erreur = jeton rejeté
        raise AccessDeniedError(
            f"Jeton Keycloak rejete (signature/issuer/expiration) : {exc}"
        ) from exc
    if access is None:
        raise AccessDeniedError("Jeton Keycloak invalide ou expire.")
    return dict(access.claims or {})


# ---------------------------------------------------------------------------
# 3. Resolution de l'identite (une seule porte d'entree pour les outils)
# ---------------------------------------------------------------------------
async def fetch_keycloak_token(
    username: str,
    password: str,
    client_id: str = "mcp-cli",
    scope: str = "openid profile email roles",
) -> str:
    """
    Recupere un jeton d'acces Keycloak (grant mot de passe, ROPC).

    Utilise par les tests et les demonstrations en mode stdio, ou aucun
    parcours navigateur n'est disponible. En demonstration interactive,
    le parcours recommande reste authorization code + PKCE dans
    MCP Inspector (A.6).
    """
    import httpx

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{KEYCLOAK_REALM_URL}/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": client_id,
                "username": username,
                "password": password,
                "scope": scope,
            },
        )
    if response.status_code != 200:
        raise AccessDeniedError(
            "Echec d'authentification Keycloak "
            f"({response.status_code}) : {response.text[:200]}"
        )
    return response.json()["access_token"]


def _roles_from_claims(claims: dict) -> list[str]:
    roles: set[str] = set()
    realm_access = claims.get("realm_access") or {}
    if isinstance(realm_access, dict):
        roles.update(realm_access.get("roles") or [])
    for key in ("roles", "role"):
        value = claims.get(key)
        if isinstance(value, str):
            roles.add(value)
        elif isinstance(value, (list, tuple)):
            roles.update(str(v) for v in value)
    return sorted(roles)


def _effective_role(roles: list[str]) -> str | None:
    """Plus haut role de la hierarchie present dans le jeton."""
    known = [r for r in roles if r in ROLE_HIERARCHY]
    if not known:
        return None
    return max(known, key=ROLE_HIERARCHY.index)


def _user_from_claims(claims: dict) -> str:
    return str(
        claims.get("preferred_username")
        or claims.get("user")
        or claims.get("sub")
        or "inconnu"
    )


def _current_oauth_claims():
    """Claims du jeton OAuth 2.1 valide par FastMCP (transport HTTP), sinon None."""
    try:
        from fastmcp.server.dependencies import get_access_token
    except Exception:  # pragma: no cover
        return None
    try:
        access = get_access_token()
    except Exception:  # hors contexte HTTP
        return None
    if access is None:
        return None
    return dict(access.claims or {})


async def resolve_identity(token: str | None, tool: str) -> dict:
    """
    Retourne {"user", "role", "roles", "source"} ou leve AccessDeniedError.

    - Transport HTTP + OAuth 2.1 : identite issue du jeton Bearer deja
      verifie par FastMCP/Keycloak. Un jeton transmis EN ARGUMENT D'OUTIL
      est alors refuse (« token passthrough » interdit par A.6).
    - Stdio (ou mode local) : jeton fourni en argument d'outil, verifie
      selon AUTH_MODE (JWKS Keycloak ou secret local HS256).
    """
    oauth_claims = _current_oauth_claims()

    if oauth_claims is not None:
        if token:
            log_action(
                user=_user_from_claims(oauth_claims),
                tool=tool,
                params={"token": token},
                status="TOKEN_PASSTHROUGH_REFUSE",
                detail=(
                    "Jeton fourni en argument d'outil alors que la requete "
                    "porte deja un jeton OAuth 2.1 : le transfert direct de "
                    "jetons est interdit (A.6)."
                ),
            )
            raise AccessDeniedError(
                "Token passthrough interdit : utilisez le jeton OAuth 2.1 "
                "de la session, pas un jeton en argument d'outil."
            )
        claims = oauth_claims
        source = "oauth2.1-pkce-keycloak"
    else:
        if not token:
            log_action(
                user="inconnu", tool=tool, params={}, status="REFUSE",
                detail="Jeton manquant pour cet appel d'outil.",
            )
            raise AccessDeniedError("Jeton manquant : authentification requise.")
        if AUTH_MODE == "keycloak":
            claims = await verify_keycloak_token(token)
            source = "keycloak-jwks"
        else:
            claims = verify_token(token)
            source = "local-hs256"

    roles = _roles_from_claims(claims)
    role = _effective_role(roles)
    user = _user_from_claims(claims)

    if role is None:
        detail = f"Roles {roles or 'absents'} hors RBAC ({ROLE_HIERARCHY})"
        log_action(
            user=user, tool=tool, params={}, status="REFUSE", detail=detail,
        )
        raise AccessDeniedError(f"Aucun role RBAC reconnu dans le jeton. {detail}")

    return {"user": user, "role": role, "roles": roles, "source": source}


# ---------------------------------------------------------------------------
# 4. Decorateur : authentication (RBAC) + consentement humain (A.6)
# ---------------------------------------------------------------------------
def require_role(required_role: str):
    """
    Protege un outil : identite validee (JWT), role suffisant (hierarchie),
    puis consentement explicite de l'utilisateur avant execution.
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(token: str | None = None, *args, **kwargs):
            tool = func.__name__

            # (a) identite + RBAC
            ident = await resolve_identity(token, tool=tool)
            if not role_satisfies(ident["role"], required_role):
                detail = (
                    f"Role '{ident['role']}' insuffisant "
                    f"(role '{required_role}' requis pour '{tool}')"
                )
                log_action(
                    user=ident["user"], tool=tool, params=kwargs,
                    status="REFUSE", detail=detail,
                )
                raise AccessDeniedError(detail)

            log_action(
                user=ident["user"], tool=tool, params=kwargs,
                status="AUTORISE",
                detail=(
                    f"role={ident['role']} (requis {required_role}), "
                    f"source={ident['source']}"
                ),
            )

            # (b) consentement explicite de l'utilisateur (A.6)
            action = f"Execution de l'outil '{tool}' avec {kwargs or 'aucun argument'}"
            await ensure_human_consent(
                user=ident["user"], tool=tool, action=action, ctx=kwargs.get("ctx"),
            )

            # (c) execution
            return await func(*args, **kwargs)

        # Signature exposee au client MCP : token en dernier, optionnel
        # (defaut "") en mode HTTP/OAuth (le jeton porte alors dans
        # l'en-tete Authorization de la requete).
        token_param = inspect.Parameter(
            "token",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=str,
            default="",
        )
        original_sig = inspect.signature(func)
        wrapper.__signature__ = original_sig.replace(
            parameters=[*original_sig.parameters.values(), token_param]
        )
        wrapper.__annotations__ = {
            **dict(getattr(func, "__annotations__", {})),
            "token": str,
        }
        wrapper.__doc__ = (
            (inspect.cleandoc(func.__doc__) + "\n\n" if func.__doc__ else "")
            + "Args:\n"
            "    token: Jeton JWT valide (Keycloak si AUTH_MODE=keycloak, sinon "
            f"secret local). Role requis : {required_role}. En transport HTTP "
            "(OAuth 2.1 + PKCE) laisser vide : le jeton porte dans l'en-tete "
            "Authorization ; un jeton en argument y est refuse (A.6).\n"
        )

        return wrapper

    return decorator
