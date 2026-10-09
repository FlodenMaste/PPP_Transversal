"""
Point d'entree du serveur MCP "mcp-noc-telecom" (groupe 3, A.6).

Deux modes de transport :
  - MCP_TRANSPORT=stdio : lance par MCP Inspector en "Command",
    demo rapide et tests automatises ;
  - MCP_TRANSPORT=http  : Streamable HTTP, transport exigible pour
    OAuth 2.1 + PKCE (A.6). Le serveur expose alors les metadonnees
    de ressource protegee (RFC 9728) qui pointent vers Keycloak
    (issuer OIDC), et valide chaque requete via le JWKS (RS256).

En AUTH_MODE=keycloak (defaut), un fournisseur Keycloak est attache
au serveur : aucun outil ne s'execute sans jeton valide + role RBAC +
consentement humain explicite.
"""

from fastmcp import FastMCP

from server.config import (
    AUTH_MODE,
    KEYCLOAK_REALM_URL,
    MCP_BASE_URL,
    MCP_HTTP_HOST,
    MCP_HTTP_PORT,
    MCP_TRANSPORT,
)


def build_auth_provider():
    """Fournisseur OIDC Keycloak (OAuth 2.1 + PKCE cote client)."""
    if AUTH_MODE != "keycloak":
        return None

    from fastmcp.server.auth.providers.keycloak import KeycloakAuthProvider

    return KeycloakAuthProvider(
        realm_url=KEYCLOAK_REALM_URL,
        base_url=MCP_BASE_URL,
        required_scopes=[],  # le RBAC se fait sur les rôles (realm_access.roles)
    )


mcp = FastMCP(
    "mcp-noc-telecom",
    instructions=(
        "Serveur MCP de supervision NOC (groupe 3). Toutes les actions "
        "sont journalisees ; chaque appel d'outil demande une confirmation "
        "explicite (pas d'autorisation permanente)."
    ),
    auth=build_auth_provider(),
)

from server.tools.demo_attack import get_syslog_message
from server.tools.supervision import snmp_get, snmp_get_secure

mcp.tool()(snmp_get)
mcp.tool()(snmp_get_secure)
mcp.tool()(get_syslog_message)


if __name__ == "__main__":
    if MCP_TRANSPORT == "http":
        mcp.run(
            transport="http",
            host=MCP_HTTP_HOST,
            port=MCP_HTTP_PORT,
        )
    else:
        mcp.run(transport="stdio")
