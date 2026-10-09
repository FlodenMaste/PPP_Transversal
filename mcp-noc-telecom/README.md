# mcp-noc-telecom — serveur MCP de supervision NOC (groupe 3)

Serveur MCP **FastMCP** qui sécurise l'accès aux outils de supervision
(SNMPv3 lecture seule, Syslog) d'un laboratoire Containerlab, conforme à la
partie **A.6 « Sécurité commune »** du cahier des charges :

- **RBAC** adossé à des **jetons JWT gérés par Keycloak (OIDC)** — validation
  côté serveur via **JWKS (RS256) + issuer** ;
- **OAuth 2.1 avec PKCE (S256)** sur transport Streamable HTTP (parcours
  `authorization_code` utilisé par MCP Inspector) ;
- **token passthrough interdit** : un jeton transmis en argument d'outil est
  refusé et journalisé (`TOKEN_PASSTHROUGH_REFUSE`) ;
- **consentement humain explicite à chaque exécution d'outil** via la
  primitive MCP `elicitation` — aucune option « toujours autoriser » ;
- **sorties d'outils traitées comme non fiables** (neutralisation des tentatives
  d'injection de prompt, cf. cas Sygnia) ;
- **journal d'audit** de toutes les actions (`server/audit.log`), secrets
  redigés automatiquement.

## Arborescence

```
.
├── docker-compose.yml            # Keycloak (OIDC) pour A.6
├── security/keycloak/            # realm mcp-noc (rôles, utilisateurs, client)
│   ├── realm-mcp.json
│   └── README.md
├── lab/                          # laboratoire Containerlab (5 nœuds, FRR)
└── server/
    ├── server/
    │   ├── main.py               # FastMCP + KeycloakAuthProvider + transports
    │   ├── config.py             # mode d'auth, transport, consentement
    │   ├── security/
    │   │   ├── auth.py           # RBAC, JWKS/issuer, anti-passthrough
    │   │   ├── consent.py        # consentement humain (éllicitation)
    │   │   ├── audit_log.py      # journal + redaction des secrets
    │   │   └── sanitizer.py      # neutralisation des sorties non fiables
    │   └── tools/                # snmp_get, snmp_get_secure, get_syslog_message
    ├── test_a6_security.py       # 28 tests d'acceptation A.6
    ├── test_mcp.py               # test de bout en bout (stdio)
    ├── demo_securite.py          # démonstration 5 étapes (jury)
    └── requirements.txt
```

## Démarrage

```bash
# 1) laboratoire (racine du dépôt PPP)
containerlab deploy -t lab/topology.clab.yml --reconfigure

# 2) Keycloak (OIDC) - port 18080 (8080 occupé sur la machine)
docker compose up -d
curl -s http://localhost:18080/realms/mcp-noc/.well-known/openid-configuration | head -3

# 3) serveur MCP
cd server && python -m venv venv && ./venv/bin/pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
./venv/bin/python -m server.main                        # stdio (MCP Inspector > Command)
MCP_TRANSPORT=http ./venv/bin/python -m server.main     # HTTP : OAuth 2.1 + PKCE
```

## Tests

```bash
cd server
./venv/bin/pytest test_a6_security.py -v    # A.6 : RBAC, JWKS, consentement, HTTP, PKCE
CONSENT_MODE=dry_run ./venv/bin/python test_mcp.py      # bout en bout (stdio)
CONSENT_MODE=dry_run ./venv/bin/python demo_securite.py # démonstration
```

## Connexion depuis MCP Inspector (HTTP + OAuth 2.1/PKCE)

1. `MCP_TRANSPORT=http MCP_HTTP_PORT=8001 ./venv/bin/python -m server.main`
2. Inspector : transport **HTTP**, URL `http://localhost:8001/mcp`, onglet
   **Authorization** → *Dynamic client registration* désactivé,
   `client_id = mcp-cli` (client public), PKCE S256 (valeur par défaut).
3. Connexion : `operateur` / `Operateur2026!` — la demande de consentement
   s'affiche ensuite à chaque appel d'outil.

Voir `security/keycloak/README.md` pour le détail du realm et des comptes.
