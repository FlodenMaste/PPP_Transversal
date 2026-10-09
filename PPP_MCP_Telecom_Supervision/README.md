# MCP NOC Supervision - PPP Groupe 3 (EC2LT)

Assistant de diagnostic NOC basé sur un serveur MCP (FastMCP 3.x), déployé sur un
réseau émulé (Containerlab + FRRouting).

Ce dépôt contient le **socle** du projet : le laboratoire réseau (bloc 1), le
backend de collecte en lecture seule (bloc 2) et le serveur MCP qui expose ces
collecteurs en outils et resources (bloc 3).

## Structure

```
.
├── lab/                 # Bloc 1 : Containerlab, images labo, injection de pannes,
│                        #          relais syslog/NetFlow, validation en mode réel
├── collector/           # Bloc 2 : backend de collecte Python (SNMP, CLI, NETCONF,
│                        #          NetFlow, PCAP, Syslog, QoS, ping) - tests inclus
├── mcp_server/          # Bloc 3 : serveur FastMCP (13 outils + resources)
│   ├── server.py        #          outils MCP + resources topologie/inventaire/IPAM/runbooks
│   └── resources/       #          topologie, inventaire, IPAM, runbooks
├── docs/                # architecture.md, collector.md
├── Dockerfile           # image du serveur MCP (A.7)
├── docker-compose.yml   # serveur + tests (A.7)
└── requirements.txt     # pysnmp, ncclient, netmiko, napalm, fastmcp<4.0
```

Les blocs **sécurité (RBAC / Keycloak / consentement / audit)** et
**analyse IA (corrélation, RCA, rapports)** vivent dans les dépôts frères :

| Bloc | Dépôt |
|---|---|
| Sécurité A.6 (Keycloak, OAuth 2.1 + PKCE, audit) | `mcp-noc-telecom` (serveur 1) |
| Outils réseau temps réel (9 outils, SNMPv3 + SSH) | `noc-mcp-server` (serveur 2) |
| Analyse IA (corrélation, RCA, rapports) | `mcp-noc-ai` (serveur 3) |

Le détail de l'architecture complète est dans [docs/architecture.md](docs/architecture.md).

## Démarrage

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m pytest collector/tests mcp_server/tests -q   # 52 tests, aucun réseau requis
```

### Laboratoire (mode réel)

```bash
docker build -t mcp-noc-frr:local  lab/containerlab        # images labo
docker build -t mcp-noc-term:local -f lab/containerlab/Dockerfile.term lab/containerlab
sudo containerlab deploy -t lab/containerlab/topology.clab.yml
sudo ../scripts/lab_services.sh                            # relais syslog + nfcapd
python lab/validate_collectors.py                          # 12/13 collecteurs réels
```

Chaînes de télémétrie, IPs de management, injection de panne et démo live :
[lab/README.md](lab/README.md).

### Serveur MCP

```bash
# stdio (démonstration avec MCP Inspector : "Command" = python -m mcp_server.server)
python -m mcp_server.server

# Streamable HTTP (conteneur ou accès distant)
MCP_TRANSPORT=http MCP_HTTP_PORT=8000 python -m mcp_server.server
```

### Docker

```bash
docker compose up -d            # serveur MCP sur http://localhost:8000/mcp
docker compose run --rm tests   # suite de tests unitaires dans l'image
```

### Mode simulé vs mode réel

Par défaut (`COLLECTOR_MODE=simulated`), les outils répondent à partir des
fixtures versionnées : aucun accès réseau n'est nécessaire. En mode `real`,
ils interrogent le laboratoire Containerlab (réseau de management
`172.20.20.0/24`) — voir [docs/collector.md](docs/collector.md).

Documentation du collecteur (fonctions, mode simulé/réel, sécurité) : [docs/collector.md](docs/collector.md).

## Exigences couvertes

- **A.4** FastMCP 3.x (`fastmcp>=3.0,<4.0`), Python 3.12
- **A.7** Dockerfile + docker-compose.yml + schémas JSON des outils (`../docs/schemas/`)
- **B.2** laboratoire Containerlab : 5 nœuds, OSPF + iBGP, injection de pannes
- **B.4** pysnmp, ncclient, netmiko, napalm, nfdump, tshark
- **B.5** 13 outils en lecture seule, dont `analyze_netflow` et `capture_pcap`, plus les resources topologie / inventaire / IPAM / runbooks
- **B.6** lecture seule, comptes minimaux, plafonds PCAP, marqueurs `untrusted`
- **B.7** `detect_anomalies` : règles déterministes, aucun calcul confié au LLM
