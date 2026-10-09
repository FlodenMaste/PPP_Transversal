# PPP Transversal — Application MCP pour l'Analyse et la Supervision des Réseaux Télécoms

Projet transversal **groupe 3** (EC2LT) : un serveur **MCP** (*Model Context
Protocol*) inséré entre un modèle de langage et les systèmes d'un centre
d'exploitation (NOC), pour construire « un NOC augmenté par l'IA » — en
**lecture seule**, sous **RBAC/Keycloak**, avec **consentement humain** et
**journal d'audit**.

Réseau émulé localement : **Containerlab + FRRouting** (5 nœuds, OSPF area 0,
iBGP AS65000, lien de secours, SNMPv3 authPriv, SSH en lecture seule),
injection de pannes déterministe, aucun équipement matériel.

## Structure du dépôt

```
PPP_Transversal/
├── PPP_MCP_Telecom_Supervision/   Socle : labo Containerlab, collecteurs (bloc 1-2),
│                                  serveur MCP de collecte 13 outils (bloc 3)
│     ├── lab/                     topology.clab.yml, configs, fault-injection
│     ├── collector/               SNMP, CLI, NETCONF, NetFlow, PCAP, Syslog, QoS, ping
│     ├── mcp_server/server.py     serveur FastMCP (outils + resources)
│     ├── Dockerfile               image du serveur MCP           (A.7)
│     └── docker-compose.yml       serveur + tests                (A.7)
├── mcp-noc-telecom/               Serveur 1 : sécurité A.6
│     └── server/                  RBAC, JWT Keycloak (OIDC), OAuth 2.1 + PKCE,
│                                  consentement par élicitation, audit
├── noc-mcp-server/                Serveur 2 : 9 outils réseau temps réel (SNMPv3, SSH)
├── mcp-noc-ai/                    Serveur 3 : analyse IA (corrélation, RCA, rapports)
├── docs/
│     ├── Rapport_...pdf           Rapport technique (79 pages)
│     └── schemas/                 Schémas JSON des outils des 4 serveurs (A.7)
└── scripts/                       Export des schémas JSON (régénérable)
```

## Livrables (A.7 / B.8)

| Livrable | Où |
|---|---|
| Dépôt GitHub public | ce dépôt |
| `Dockerfile` | `PPP_MCP_Telecom_Supervision/Dockerfile` |
| `docker-compose.yml` | `PPP_MCP_Telecom_Supervision/docker-compose.yml` (+ Keycloak : `mcp-noc-telecom/docker-compose.yml`) |
| Schémas JSON des outils | `docs/schemas/*.json` (34 outils, régénérables via `scripts/run_all.sh`) |
| Environnement de démonstration MCP Inspector | voir « Démarrage rapide » ci-dessous |
| Rapport PDF | `docs/Rapport_PPP_MCP_Telecom_Supervision.pdf` |
| Support de présentation (PowerPoint) | support de soutenance, hors dépôt |

## Démarrage rapide

### 0. Prérequis

```bash
python3 --version      # 3.12.x
docker --version       # 29.x
containerlab version   # 0.79.0
```

`sudo` sert uniquement à `containerlab` et `docker` — **jamais** à `python`,
`pip` ou `pytest` (sinon les fichiers appartiennent à root et les tests
échouent en compte utilisateur).

### 1. Laboratoire réseau

```bash
cd PPP_MCP_Telecom_Supervision
sudo containerlab deploy -t lab/containerlab/topology.clab.yml
docker ps --format '{{.Names}} {{.Status}}' | grep mcp-noc-lab   # 5 conteneurs UP
```

### 2. Keycloak (sécurité A.6)

```bash
cd mcp-noc-telecom
docker compose up -d        # realm mcp-noc importé, port 18080
```

### 3. Les serveurs MCP

```bash
# Socle (13 outils de collecte) — stdio
cd PPP_MCP_Telecom_Supervision && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python -m mcp_server.server

# Serveur 1 (sécurité) — stdio
cd ../mcp-noc-telecom/server && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
cp .env.example .env
CONSENT_MODE=dry_run ./venv/bin/python -m server.main

# Serveur 2 (9 outils réseau)
cd ../../noc-mcp-server && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
cp .env.example .env
./venv/bin/python server.py

# Serveur 3 (analyse IA)
cd ../mcp-noc-ai && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python server.py
```

### 4. Démonstration MCP Inspector (A.5)

```bash
# Option simple (4 serveurs, un onglet Inspector par serveur) :
scripts/inspector.sh                 # ou : scripts/inspector.sh --dry-run

# "Command" de l'Inspecteur, un onglet/terminal par serveur,
# chacun depuis la racine du dépôt (ports alignés sur scripts/inspector.sh) :
cd mcp-noc-telecom/server && CONSENT_MODE=dry_run ./venv/bin/python -m server.main   # 6274
cd noc-mcp-server && ./venv/bin/python server.py                                     # 6374
cd mcp-noc-ai && ./venv/bin/python server.py                                         # 6474
cd PPP_MCP_Telecom_Supervision && ./venv/bin/python -m mcp_server.server             # 6574
```

Les quatre interfaces répondent ensuite sur `http://127.0.0.1:{6274,6374,6474,6574}`.

### Docker (socle)

```bash
cd PPP_MCP_Telecom_Supervision
docker compose up -d            # serveur MCP en Streamable HTTP :8000
docker compose run --rm tests   # 34 tests dans l'image
```

## Tests

Commandes lancées **depuis la racine du dépôt**, avec les `venv` créés en
section 3. Le niveau A.6 exige en plus les dépendances de test et Keycloak :

```bash
cd mcp-noc-telecom/server && ./venv/bin/pip install -r requirements-dev.txt   # pytest, pytest-asyncio
docker compose -f mcp-noc-telecom/docker-compose.yml up -d                     # Keycloak, port 18080
```

| Niveau | Commande | Résultat |
|---|---|---|
| 1 — unitaires (socle) | `cd PPP_MCP_Telecom_Supervision && ./venv/bin/python -m pytest collector/tests -q` | 34 passed |
| 5 — sécurité A.6 | `cd mcp-noc-telecom/server && ./venv/bin/python -m pytest test_a6_security.py -q` | 28 passed |
| 3 — bout en bout | `cd mcp-noc-telecom/server && CONSENT_MODE=dry_run ./venv/bin/python test_mcp.py` | RBAC, consentement, audit |
| 3 — outils vus par l'hôte | `cd noc-mcp-server && ./venv/bin/python test_client_roots.py` | 9 outils, 4 resources, 1 prompt |
| 5 — socle dans le conteneur | `cd PPP_MCP_Telecom_Supervision && docker compose run --rm tests` | 34 passed |

Niveaux 2 et 4 (intégration réelle, coupure de lien) : voir le rapport,
partie III — méthodologie de tests.

## Conformité au cahier des charges

| Réf. | Exigence | État |
|---|---|---|
| A.1 / A.2 | Fondements MCP, primitives (tools, resources, prompts, elicitation, roots, logging) | ✅ |
| A.3 | stdio + Streamable HTTP, spec 2025-11-25, HTTP+SSE déprécié | ✅ |
| A.4 | FastMCP 3.x, `@mcp.tool()`, Python 3.12 | ✅ (`fastmcp>=3.0,<4.0` sur les 4 dépôts) |
| A.5 | Démonstration via MCP Inspector | ✅ (4 instances, `scripts/inspector.sh`) |
| A.6 | RBAC Keycloak, OAuth 2.1 + PKCE, anti-passthrough, consentement, audit | ✅ (28 tests) |
| A.7 | Dépôt public, Dockerfile, docker-compose, schémas JSON, Inspector, rapport PDF | ✅ (hors support PPT) |
| B.2 | Laboratoire Containerlab (5 nœuds, panne injectable) | ✅ |
| B.4 | pysnmp, ncclient, netmiko, napalm, nfdump, tshark | ✅ |
| B.5 | ≥ 8 outils MCP + resources (topologie, inventaire, IPAM, runbooks) | ✅ (13 + 9 + 9 + 3 outils) |
| B.6 | Lecture seule, comptes minimaux, secrets, sorties non fiables, plafonds PCAP | ✅ |
| B.7 | `detect_anomalies` sans calcul confié au LLM, RCA documentée | ✅ |
| B.8 | Serveur opérationnel + documentation de repro + démo live | ✅ (rapport partie III) |

## Sécurité en un paragraphe

Aucun outil exposé ne modifie une configuration réseau : les accès CLI sont
bridés à une liste blanche de commandes `show`, les comptes du labo sont en
lecture seule (SNMPv3 `rouser … priv` avec vue `limited`, SSH `frrvty`), les
secrets vivent dans `.env` (jamais versionné), chaque sortie d'outil est
marquée `untrusted`, et côté serveur 1 chaque appel exige un jeton Keycloak
valide (JWKS/RS256) + le rôle RBAC + une confirmation humaine par élicitation,
le tout tracé dans `audit.log`.

## Documentation

- `docs/Rapport_PPP_MCP_Telecom_Supervision.pdf` — rapport complet (architectures, commandes, campagne de tests, glossaire)
- `PPP_MCP_Telecom_Supervision/docs/architecture.md` — architecture et répartition des blocs
- `PPP_MCP_Telecom_Supervision/docs/collector.md` — backend de collecte (modes, format de sortie unifié, sécurité)
- `docs/schemas/` — schémas JSON des outils MCP
