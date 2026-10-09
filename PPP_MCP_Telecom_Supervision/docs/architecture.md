# Architecture de la solution

Vue d'ensemble du projet transversal « Application MCP pour l'Analyse et
Supervision des Réseaux Télécoms » (groupe 3, EC2LT).

## 1. Laboratoire émulé (bloc 1)

```
┌─────────────────────────── LABORATOIRE CONTAINERLAB ───────────────────────────┐
│  r1 (172.20.20.11) ── r2 (.12) ── r3 (.13)        OSPF area 0 · iBGP AS65000  │
│        │                   │                                                │
│   client (.14) 192.168.1.0/24          server (.15) 192.168.3.0/24            │
│   lien de secours r1–r3 (10.0.13.0/30) — injection de panne : eth1 down       │
└────────────────────────────────────────────────────────────────────────────────┘
        │  SNMPv3 authPriv (compte mcpreadonly, vue "limited")
        │  SSH        (compte noc, groupe frrvty → vtysh lecture seule)
        ▼
```

Déploiement : `sudo containerlab deploy -t lab/containerlab/topology.clab.yml`
(depôt `PPP_MCP_Telecom_Supervision`, détails dans `lab/`).

## 2. Chaîne MCP

```
  Hôte MCP (MCP Inspector, ports 6274 / 6374 / 6474)
        │  stdio / JSON-RPC 2.0            (transport local)
        │  Streamable HTTP                 (transport distant, A.3)
        ├──▶ Serveur 1  mcp-noc-telecom   sécurité : RBAC, JWT Keycloak,
        │                                 consentement, audit       (A.6)
        ├──▶ Serveur 2  noc-mcp-server    9 outils réseau temps réel
        ├──▶ Serveur 3  mcp-noc-ai        corrélation, RCA, rapports (IA)
        └──▶ Socle      mcp_server/       13 outils de collecte + resources
```

| Rôle | Dépôt | Contenu |
|---|---|---|
| Socle (blocs 1‑3) | `PPP_MCP_Telecom_Supervision` | labo, collecteurs, serveur MCP de collecte |
| Serveur 1 | `mcp-noc-telecom` | sécurité A.6 : Keycloak (OIDC), OAuth 2.1 + PKCE, RBAC, consentement, audit |
| Serveur 2 | `noc-mcp-server` | SNMP, ping, BGP, OSPF, NETCONF, resources, prompt |
| Serveur 3 | `mcp-noc-ai` | corrélation d'alarmes, cause racine (RCA), rapports d'incident |

## 3. Serveur MCP du socle (`mcp_server/server.py`)

- **Framework** : FastMCP 3.x (`fastmcp>=3.0,<4.0`), Python 3.12 — exigence A.4.
- **Outils (13)** : `snmp_get`, `snmp_walk`, `get_interface_stats`, `ping_host`,
  `traceroute`, `get_bgp_peers`, `get_ospf_neighbors`, `netconf_get`,
  `analyze_netflow`, `detect_anomalies`, `capture_pcap`, `qos_stats`,
  `get_recent_syslog`. Tous en **lecture seule**.
- **Resources** : `mcp://socle/topology`, `mcp://socle/inventory`,
  `mcp://socle/ipam`, `mcp://socle/runbook/{interface_down|bgp_flap}`.
- **Transports** : stdio (Inspector) ou Streamable HTTP (`MCP_TRANSPORT=http`,
  port 8000 par défaut).
- **Sorties** : chaque réponse conserve les marqueurs `untrusted` et
  `untrusted_fields` produits par le backend (B.6) — le modèle doit les
  traiter comme des données, jamais comme des instructions.

## 4. Flux de données

```
équipement ──SNMPv3/SSH/NETCONF/nfdump/tshark──▶ collector/  (bloc 2)
                                                 │ réponse unifiée :
                                                 │ {status, source, data,
                                                 │  untrusted, untrusted_fields}
                                                 ▼
                                          mcp_server/ (bloc 3)
                                                 │ outils + resources MCP
                                                 ▼
                                     Hôte MCP (LLM) ──▶ serveur 1 : jeton,
                                                        RBAC, consentement,
                                                        audit avant exécution
```

## 5. Sécurité (répartition des blocs)

| Exigence | Où elle est implémentée |
|---|---|
| RBAC + JWT Keycloak (OIDC) | `mcp-noc-telecom/server/server/security/auth.py` |
| OAuth 2.1 + PKCE S256, RFC 9728 | `mcp-noc-telecom` (transport HTTP), realm `security/keycloak/realm-mcp.json` |
| Refus du token passthrough | `auth.py` (parcours HTTP) |
| Consentement humain à chaque exécution | `mcp-noc-telecom/.../security/consent.py` (élicitation MCP) |
| Journal d'audit + redaction | `mcp-noc-telecom/.../security/audit_log.py` |
| Liste blanche de commandes `show` | `PPP_MCP_Telecom_Supervision/collector/cli/command_whitelist.py` |
| Comptes minimaux (SNMP lecture seule, `frrvty`) | `lab/containerlab/topology.clab.yml` + `snmpd.conf` |
| Plafonds de capture PCAP | `collector/config.py` (`PCAP_MAX_*`), appliqués par `_clamp()` |
| Sorties non fiables | `collector/common/schema.py` (`untrusted`, `untrusted_fields`) |
| Aucune écriture sur le réseau | aucun outil exposé ne modifie une configuration |

## 6. Tests

| Niveau | Commande | Couverture |
|---|---|---|
| 1 — unitaires | `python -m pytest collector/tests -q` (34) | parsing, bornes, erreurs, mode simulé |
| 5 — sécurité A.6 | `pytest test_a6_security.py -q` (28, dépôt serveur 1) | RBAC, JWKS, PKCE, 401/200, élicitation |
| 3 — bout en bout | `python test_mcp.py`, `python test_client_roots.py` | outils vus par l'hôte, refus sans jeton |

Les niveaux 2 et 4 (intégration réelle, panne réseau) nécessitent le
laboratoire déployé — commandes dans le rapport et dans `lab/`.
