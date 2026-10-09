import os

from dotenv import load_dotenv

load_dotenv()

# --- Authentification locale (mode "local", hors Keycloak) ---------------
JWT_SECRET = os.getenv("JWT_SECRET", "change-moi-avant-la-demo")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", "60"))

# --- Hierarchie RBAC (A.6 : RBAC adossse aux jetons JWT) -----------------
ROLE_HIERARCHY = ["operateur", "superviseur", "administrateur"]


def role_satisfies(user_role: str, required_role: str) -> bool:
    if user_role not in ROLE_HIERARCHY or required_role not in ROLE_HIERARCHY:
        return False
    return ROLE_HIERARCHY.index(user_role) >= ROLE_HIERARCHY.index(required_role)


# --- A.6 : Keycloak (OIDC) + OAuth 2.1 / PKCE -----------------------------
# AUTH_MODE=keycloak : les jetons sont emis et verifies par Keycloak (JWKS, RS256)
# AUTH_MODE=local    : mode autonome sans Keycloak (demos/tests hors ligne)
AUTH_MODE = os.getenv("AUTH_MODE", "keycloak").strip().lower()

# URL du realm Keycloak (issuer OIDC + JWKS derives de cette URL)
KEYCLOAK_REALM_URL = os.getenv(
    "KEYCLOAK_REALM_URL", "http://localhost:18080/realms/mcp-noc"
).rstrip("/")

# URL publique du serveur MCP (declaree dans les metadonnees OAuth - RFC 9728)
MCP_BASE_URL = os.getenv("MCP_BASE_URL", "http://localhost:8001").rstrip("/")

# --- Transport -------------------------------------------------------------
# stdio  : demos rapides et tests automatises (MCP Inspector en stdio)
# http   : Streamable HTTP, transport exigible pour OAuth 2.1 + PKCE (A.6)
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio").strip().lower()
MCP_HTTP_HOST = os.getenv("MCP_HTTP_HOST", "127.0.0.1")
MCP_HTTP_PORT = int(os.getenv("MCP_HTTP_PORT", "8001"))

# --- Consentement humain obligatoire (A.6) --------------------------------
# elicitation : demande dans l'IHM du client MCP (reponse du survivellant)
# terminal    : confirmation en clavier sur le serveur (demos en console)
# dry_run     : simulation journalisee (tests automatises uniquement)
# deny        : refus systematique (test negatif)
CONSENT_MODE = os.getenv("CONSENT_MODE", "elicitation").strip().lower()


# --- Secrets du laboratoire (B.6 : surchargeables par variables .env) ----
SNMP_USER = os.getenv("SNMP_USER", "mcpreadonly")
SNMP_AUTH_PASS = os.getenv("SNMP_AUTH_PASS", "AuthPass2026!")
SNMP_PRIV_PASS = os.getenv("SNMP_PRIV_PASS", "PrivPass2026!")
