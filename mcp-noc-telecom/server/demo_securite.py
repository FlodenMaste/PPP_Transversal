"""
Script de demonstration complet de la couche securite du serveur MCP
(cahier des charges A.6) - a executer devant le jury.

  1. RBAC : acces REFUSE pour un role hors hierarchie
  2. RBAC : acces AUTORISE pour un role suffisant
  3. Consentement humain obligatoire (confirmation clavier ici ;
     en session MCP, la meme demande passe par l'elicitation)
  4. Neutralisation d'une injection de prompt (sorties non fiables)
  5. Journal d'audit qui trace l'ensemble

Usage :
    python demo_securite.py                    # demande de confirmer au clavier
    CONSENT_MODE=dry_run python demo_securite.py   # sans confirmation (demo rapide)

En AUTH_MODE=keycloak (defaut), les jetons sont delivres par Keycloak.
"""

import asyncio

from server.config import AUTH_MODE
from server.security.auth import (
    AccessDeniedError,
    fetch_keycloak_token,
    generate_token,
)

# Utilisateurs Keycloak du realm mcp-noc (security/keycloak/realm-mcp.json)
KEYCLOAK_USERS = {
    "operateur": ("operateur", "Operateur2026!"),
    "superviseur": ("superviseur", "Superviseur2026!"),
    "administrateur": ("administrateur", "Administrateur2026!"),
    "invite": ("invite", "Invite2026!"),  # role hors RBAC : doit etre refuse
}
LOCAL_ROLES = {"operateur", "superviseur", "administrateur", "invite"}


async def jeton(pour: str) -> str:
    """Jeton Keycloak (defaut) ou jeton local HS256 si AUTH_MODE=local."""
    if AUTH_MODE == "keycloak":
        user, password = KEYCLOAK_USERS[pour]
        return await fetch_keycloak_token(user, password)
    role = pour if pour in LOCAL_ROLES else "role_inexistant"
    return generate_token(f"demo-{pour}", role)


def separateur(titre: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {titre}")
    print("=" * 70)


async def main() -> None:
    from server.tools.demo_attack import get_syslog_message
    from server.tools.supervision import snmp_get

    print(f"Mode d'authentification : AUTH_MODE={AUTH_MODE}")

    separateur("DEMO 1 : RBAC - acces REFUSE (role hors hierarchie)")
    print("Un utilisateur sans role MCP tente d'appeler un outil protege...")
    try:
        await snmp_get(router="r1", token=await jeton("invite"))
        print("-> ECHEC : l'acces aurait du etre refuse")
    except AccessDeniedError as e:
        print(f"-> ACCES REFUSE (comme attendu) : {e}")

    separateur("DEMO 2 : RBAC - acces AUTORISE (role operateur) + consentement")
    token = await jeton("operateur")
    print("Confirmation humaine demandee avant execution (saisir : oui)")
    result = await snmp_get(router="r1", token=token)
    print(f"-> Acces autorise. Succes : {result['success']}")

    separateur("DEMO 3 : Syslog normal, aucune alerte")
    result = await get_syslog_message(scenario="normal", token=token)
    print(f"Message : {result['message_neutralise']}")
    print(f"-> Injection detectee : {result['injection_detectee']}")

    separateur("DEMO 4 : Syslog PIEGE - tentative d'injection de prompt")
    print("Un equipement compromis tente d'injecter des instructions cachees...")
    result = await get_syslog_message(scenario="piege", token=token)
    print(f"Message NEUTRALISE : {result['message_neutralise']}")
    print(f"-> Injection detectee : {result['injection_detectee']}")
    print(f"-> Nombre de patterns suspects bloques : {result['nombre_patterns_suspects']}")

    separateur("DEMO 5 : Journal d'audit de cette session (dernieres lignes)")
    from pathlib import Path

    audit = Path(__file__).resolve().parent / "audit.log"
    with open(audit, encoding="utf-8") as f:
        for ligne in f.readlines()[-5:]:
            print(ligne.strip())

    print("\n" + "=" * 70)
    print("  FIN DE LA DEMONSTRATION")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
