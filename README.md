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
├── mcp-noc-ai/                    Serveur 3 : analyse IA (10 outils, corrélation, RCA)
├── docs/
│     ├── Rapport_...pdf           Rapport technique (59 pages)
│     ├── Architecture.md          Revue d'architecture : C4, ADR, flux, risques
│     ├── Mise_en_oeuvre.md        Partie II : scénarios S0→S9 + résultats observés
│     ├── scenarios_resultats.json Résultats machine de la campagne (29 appels)
│     ├── campagne_scenarios.txt   Journal brut de la campagne S0→S7
│     ├── Dimensionnement_TCO.md   Hypothèses, formules, mesures, TCO (B.10)
│     └── schemas/                 Schémas JSON des outils des 4 serveurs (A.7)
└── scripts/                       Export des schémas JSON (régénérable),
                                   campagne de scénarios, Inspector (4 serveurs),
                                   relais syslog, services labo, mesures (B.10)
```

## Livrables (A.7 / B.8)

| Livrable | Où |
|---|---|
| Dépôt GitHub public | ce dépôt |
| `Dockerfile` | `PPP_MCP_Telecom_Supervision/Dockerfile` |
| `docker-compose.yml` | `PPP_MCP_Telecom_Supervision/docker-compose.yml` (+ Keycloak : `mcp-noc-telecom/docker-compose.yml`) |
| Schémas JSON des outils | `docs/schemas/*.json` (35 outils, régénérables via `scripts/run_all.sh`) |
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

# images labo : routeurs (FRR+snmp+sshd+softflowd) et terminaux (snmpwalk+softflowd)
docker build -t mcp-noc-frr:local  lab/containerlab
docker build -t mcp-noc-term:local -f lab/containerlab/Dockerfile.term lab/containerlab

sudo containerlab deploy -t lab/containerlab/topology.clab.yml
docker ps --format '{{.Names}} {{.Status}}' | grep mcp-noc-lab   # 5 conteneurs UP

# services d'acquisition de l'hôte : relais syslog udp/1514 + nfcapd udp/9995
sudo scripts/lab_services.sh

# (mode réel) collecteurs testés contre le labo : 13/13 OK, dont NETCONF sur r1:830
cp .env.example .env && ./venv/bin/python lab/validate_collectors.py
```

Détails, télémétrie et injection de panne pour la démo live :
`PPP_MCP_Telecom_Supervision/lab/README.md`.

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
./venv/bin/python -m server.main            # CONSENT_MODE=elicitation par défaut (A.6)
                                             # CONSENT_MODE=dry_run : tests automatises uniquement

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
# le serveur 1 tourne en dry_run faute d'IHM de confirmation côté Inspector :
# sans consentement, le garde A.6 refuse tout appel (fail-safe) — c'est le
# comportement voulu en production (CONSENT_MODE=elicitation).
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
docker compose run --rm tests   # 37 tests dans l'image
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
| 1 — unitaires (socle) | `cd PPP_MCP_Telecom_Supervision && ./venv/bin/python -m pytest collector/tests mcp_server/tests -q` | 52 passed |
| 1 — unitaires (serveur 2) | `cd noc-mcp-server && ./venv/bin/python -m pytest tests -q` | 7 passed |
| 1 — unitaires (serveur 3) | `cd mcp-noc-ai && ./venv/bin/python -m pytest tests -q` | 14 passed |
| 5 — sécurité A.6 | `cd mcp-noc-telecom/server && ./venv/bin/python -m pytest -q` | 30 passed (Keycloak actif) |
| 3 — bout en bout | `cd mcp-noc-telecom/server && CONSENT_MODE=dry_run ./venv/bin/python test_mcp.py` | RBAC, consentement, audit |
| 3 — consentement réel + PKCE | `cd mcp-noc-telecom/server && ./venv/bin/python test_elicitation_http.py` | 1 elicitation reçue, sysDescr réel |
| 3 — outils vus par l'hôte | `cd noc-mcp-server && ./venv/bin/python test_client_roots.py` | 9 outils, 4 resources, 1 prompt |
| 4 — collecteurs réels (labo) | `cd PPP_MCP_Telecom_Supervision && ./venv/bin/python lab/validate_collectors.py` | 13/13 (NETCONF sur r1:830 compris) |
| 3 — campagne de scénarios | `./PPP_MCP_Telecom_Supervision/venv/bin/python scripts/run_scenarios.py --json docs/scenarios_resultats.json` | 29 appels, 18 outils, 18 consentements, code 0 |
| 4 — mesures de dimensionnement (B.10) | `scripts/measure_dimensionnement.sh` | volumes syslog/NetFlow, RSS, hôte |
| 5 — socle dans le conteneur | `cd PPP_MCP_Telecom_Supervision && docker compose run --rm tests` | 37 passed |

Niveaux 2 et 4 (intégration réelle, coupure de lien) : voir le rapport,
partie III — méthodologie de tests.

## Conformité au cahier des charges

| Réf. | Exigence | État |
|---|---|---|
| A.1 / A.2 | Fondements MCP, primitives (tools, resources, prompts, elicitation, roots, logging) | ✅ |
| A.3 | stdio + Streamable HTTP, spec 2025-11-25, HTTP+SSE déprécié | ✅ |
| A.4 | FastMCP 3.x, `@mcp.tool()`, Python 3.12 | ✅ (`fastmcp>=3.0,<4.0` sur les 4 dépôts) |
| A.5 | Démonstration via MCP Inspector | ✅ (4 instances, `scripts/inspector.sh`) |
| A.6 | RBAC Keycloak, OAuth 2.1 + PKCE, anti-passthrough, consentement, audit | ✅ (30 tests) |
| A.7 | Dépôt public, Dockerfile, docker-compose, schémas JSON, Inspector, rapport PDF | ✅ (hors support PPT) |
| B.2 | Laboratoire Containerlab (5 nœuds, panne injectable) | ✅ |
| B.4 | pysnmp, ncclient, netmiko, napalm, nfdump, tshark | ✅ |
| B.5 | ≥ 8 outils MCP + resources (topologie, inventaire, IPAM, runbooks) | ✅ (13 + 10 + 9 + 3 outils ; 19 outils exploités en scénarios S0→S9) |
| B.6 | Lecture seule, comptes minimaux, secrets, sorties non fiables, plafonds PCAP | ✅ |
| B.7 | `detect_anomalies` sans calcul confié au LLM, RCA documentée | ✅ |
| B.8 | Serveur opérationnel + documentation de repro + démo live | ✅ (rapport partie III) |
| B.10 | Dimensionnement & Rigueur (formules, sources) + TCO réel | ✅ (`docs/Dimensionnement_TCO.md`, mesures `scripts/measure_dimensionnement.sh`) |

## Sécurité en un paragraphe

Aucun outil exposé ne modifie une configuration réseau : les accès CLI sont
bridés à une liste blanche de commandes `show`, les comptes du labo sont en
lecture seule (SNMPv3 `rouser … priv` avec vue `limited`, SSH `frrvty`), les
secrets vivent dans `.env` (jamais versionné), chaque sortie d'outil est
marquée `untrusted`, et côté serveur 1 chaque appel exige un jeton Keycloak
valide (JWKS/RS256) + le rôle RBAC + une confirmation humaine par élicitation,
le tout tracé dans `audit.log`.

## Indépendance des serveurs (contrôlée le 20/10/2026)

Chaque serveur a son propre `requirements.txt` et son propre venv. Les dépendances
réellement déclarées, relues un à un :

| Serveur | Dépendances | Accès réseau |
|---|---|---|
| socle `mcp_server.server` | FastMCP 3.4.8 + collecteurs (pysnmp, ncclient, netmiko, napalm, nfdump, tshark) | en-process |
| `mcp-noc-telecom` (sécurité A.6) | `fastmcp`, `pyjwt`, `python-dotenv` | **aucune librairie** : `snmpwalk` passe par `docker exec clab-mcp-noc-lab-client` |
| `noc-mcp-server` (collecte) | FastMCP 3.4.8 + ~80 paquets épinglés (`pysnmp`, `ncclient`, `paramiko`, …) | en-process |
| `mcp-noc-ai` (analyse) | `fastmcp` + `pytest` **uniquement** | **aucun accès réseau** : analyse sur données déjà collectées |

Toutes les versions convergeaient déjà vers FastMCP 3.4.8 : il n'existe aucune
divergence vers une 4.x. `mcp-noc-ai` étant indépendant de toute stack réseau, le choix
de son framework reste ouvert (voir `docs/Architecture.md`, ADR-07).

## Documentation

- `docs/Architecture.md` — revue d'architecture : vues C4, ADR justifiés (ADR-01 → ADR-08), flux détaillés, dépendances réelles des 4 serveurs, risques W1–W12
- `docs/Mise_en_oeuvre.md` — Partie II : mise en œuvre par **scénarios S0→S9** avec les résultats observés (campagne, élicitation, panne) et synthèse de 19 outils exploités
- `docs/Rapport_PPP_MCP_Telecom_Supervision.pdf` — rapport complet (architectures, commandes, campagne de tests, glossaire)
- `docs/scenarios_resultats.json` + `docs/campagne_scenarios.txt` — résultats machine et journal de la campagne
- `docs/Dimensionnement_TCO.md` — dimensionnement chiffré (hypothèses, formules F1–F8, mesures labo, recoupements de sources) et TCO 3 ans
- `PPP_MCP_Telecom_Supervision/docs/architecture.md` — architecture et répartition des blocs
- `PPP_MCP_Telecom_Supervision/docs/collector.md` — backend de collecte (modes, format de sortie unifié, sécurité)
- `docs/schemas/` — schémas JSON des outils MCP
