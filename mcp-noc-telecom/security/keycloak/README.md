# Socle de sécurité — Keycloak (A.6)

Ce dossier contient la configuration d'identité du projet **A.6 « Sécurité
commune »** : RBAC adossé à des jetons JWT gérés par **Keycloak (OIDC)**,
complété par **OAuth 2.1 avec PKCE** côté client (MCP Inspector).

## Démarrage

```bash
# à la racine du dépôt
docker compose up -d          # publie Keycloak sur http://localhost:18080

# vérifications
curl -s http://localhost:18080/realms/mcp-noc/.well-known/openid-configuration | head
```

L'import du realm (`realm-mcp.json`) est automatique au premier démarrage.
Keycloak démarre en **mode dev** avec une base H2 éphémère : pour repartir de
zéro, `docker compose down -v && docker compose up -d --force-recreate`.

> Le port **8080 est déjà occupé** par un autre conteneur de la machine :
> Keycloak est donc publié sur le port **18080** (et 19000 pour son endpoint
> de santé). `KEYCLOAK_REALM_URL` et `MCP_BASE_URL` sont dans `server/.env`.

## Realm `mcp-noc`

| Élément | Valeur |
|---|---|
| Issuer OIDC | `http://localhost:18080/realms/mcp-noc` |
| JWKS | `.../protocol/openid-connect/certs` (RS256) |
| Durée de vie du jeton | 300 s |
| Rôles (hiérarchie RBAC) | `operateur` < `superviseur` < `administrateur` |
| Rôle hors hiérarchie | `invite` (sert à démontrer un **refus** RBAC) |
| Client OAuth public | `mcp-cli` (authorization code + PKCE S256, ROPC désactivé) |
| Client automatisation/tests | `mcp-cli-ropc` (grant mot de passe réservé aux scripts stdio, désactivable hors labo) |

### Utilisateurs

| Utilisateur | Mot de passe | Rôle |
|---|---|---|
| `operateur` | `Operateur2026!` | operateur (droits minimaux, lecture seule) |
| `superviseur` | `Superviseur2026!` | superviseur |
| `administrateur` | `Administrateur2026!` | administrateur |
| `invite` | `Invite2026!` | **aucun rôle MCP** → tous les outils refusés |

Ces identifiants sont ceux du **laboratoire** (comme les secrets SNMPv3) et
sont destinés à la démonstration ; en production, ils viennent d'un coffre de
secrets et le realm est protégé par TLS.

## Chaîne d'authentification

1. **MCP Inspector (HTTP)** ouvre le parcours `authorization_code` + **PKCE
   S256** : le serveur MCP expose les métadonnées de ressource protégée
   (`/.well-known/oauth-protected-resource/mcp`, RFC 9728) qui pointent vers
   ce realm Keycloak.
2. Keycloak délivre le jeton d'accès (RS256, `realm_access.roles`).
3. Le serveur MCP **valide chaque requête** (JWKS + issuer) via
   `KeycloakAuthProvider` — sans ce jeton : `401`.
4. Le rôle est ensuite vérifié dans la hiérarchie RBAC (décorateur
   `@require_role`), puis le **consentement humain explicite** est demandé
   (primitive MCP `elicitation`).

**Token passthrough** : sur transport HTTP, un jeton transmis *en argument
d'outil* est **refusé** (`TOKEN_PASSTHROUGH_REFUSE` dans `audit.log`) : le
jeton de session OAuth 2.1 ne quitte jamais l'en-tête `Authorization`.

## Dynamic Client Registration (DCR)

L'enregistrement anonyme de clients est **refusé par Keycloak** (policy
*Trusted Hosts*) : les clients doivent être déclarés à l'avance. C'est ici un
choix assumé de posture de sécurité ; MCP Inspector se configure donc avec le
`client_id` **`mcp-cli`** (client public, PKCE S256) et l'option *Dynamic
client registration* désactivée.

## Tests associés

```bash
cd server
./venv/bin/pytest test_a6_security.py -v      # 28 tests (RBAC, JWKS, consentement, HTTP, PKCE)
```
