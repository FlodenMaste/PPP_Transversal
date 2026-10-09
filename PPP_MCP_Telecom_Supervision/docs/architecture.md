# Architecture de la solution

Vue d'ensemble du projet transversal « Application MCP pour l'Analyse et
Supervision des Réseaux Télécoms » (groupe 3, EC2LT).

## 1. Laboratoire émulé (bloc 1)

```
┌─────────────────────────── LABORATOIRE CONTAINERLAB ───────────────────────────┐
│  r1 (172.20.20.11) ── r2 (.12) ── r3 (.13)        OSPF area 0 · iBGP AS65000  │
│        │                   │                                                │
│   client (.14) 192.168.1.0/24          server (.15) 192.168.3.0/24            │
│   lien de secours r1–r3 (10.0.13.0/30) — injection de panne : shutdown eth1   │
└────────────────────────────────────────────────────────────────────────────────┘
        │  SNMPv3 authPriv (compte mcpreadonly, vue "limited")
        │  SSH        (compte noc, groupe frrvty → vtysh lecture seule)
        │  Syslog     (syslogd -R → udp/1514 → relais hôte → fichier socle)
        │  NetFlow v9 (softflowd → udp/9995 → nfcapd → /var/netflow)
        ▼
```

Images labo construites localement (`lab/containerlab/Dockerfile[.term]`),
services d'acquisition de l'hôte : `scripts/lab_services.sh` ; validation en
mode réel : `lab/validate_collectors.py` (12/13, NETCONF non exposé par FRR).

Déploiement : `sudo containerlab deploy -t lab/containerlab/topology.clab.yml`
(depôt `PPP_MCP_Telecom_Supervision`, détails dans `lab/README.md`).

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
  `mcp://socle/ipam`, `mcp://socle/runbook/{interface_down|bgp_flap}`
  (la resource runbook exige une racine du client — primitive `roots`).
- **Prompts** : `triage_incident`, `collecte_diagnostic`, `rapport_quotidien` ;
  **completions** assistées sur l'argument `equipement` et sur `runbook/{name}`.
- **Transports** : stdio (Inspector) ou Streamable HTTP (`MCP_TRANSPORT=http`,
  port 8000 par défaut).
- **Sorties** : chaque réponse conserve les marqueurs `untrusted` et
  `untrusted_fields` produits par le backend (B.6) — le modèle doit les
  traiter comme des données, jamais comme des instructions.

## 4. Flux de données

```
équipement ──SNMPv3/SSH/NETCONF/nfdump/tshark──▶ collector/  (bloc 2)
     │                                          │ réponse unifiée :
     │ syslog (udp/1514, relais normalisé)      │ {status, source, data,
     │ NetFlow v9 (udp/9995, nfcapd)            │  untrusted, untrusted_fields}
     ▼                                          ▼
  /var/log/network_syslog.log · /var/netflow  ──▶  mcp_server/ (bloc 3)
                                                          │ outils + resources MCP
                                                          ▼
                                      Hôte MCP (LLM) ──▶ serveur 1 : jeton,
                                                         RBAC, consentement,
                                                         audit avant exécution
                                              └──▶ serveur 3 : corrélation avec
                                                   NOC_SYSLOG_FILE (labo en direct)
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
| 1 — unitaires (socle) | `python -m pytest collector/tests mcp_server/tests -q` (52) | parsing, bornes, erreurs, mode simulé, primitives MCP |
| 1 — unitaires (serveurs 2/3) | `pytest tests -q` dans `noc-mcp-server` (7) et `mcp-noc-ai` (14) | garde A.6, sampling, prompts, labo en direct |
| 5 — sécurité A.6 | `pytest -q` (28, dépôt serveur 1) | RBAC, JWKS, PKCE, 401/200, élicitation |
| 3 — bout en bout | `python test_mcp.py`, `python test_client_roots.py` | outils vus par l'hôte, refus sans jeton |
| 4 — collecteurs réels | `python lab/validate_collectors.py` (12/13, labo déployé) | SNMP, CLI, ping, syslog, NetFlow en mode réel |

Les niveaux 2 et 4 (intégration réelle, panne réseau) nécessitent le
laboratoire déployé — commandes dans le rapport et dans `lab/`.

## 7. Dimensionnement et TCO

Les hypothèses, formules et le coût total de possession sont chiffrés dans
`docs/Dimensionnement_TCO.md` (dépôt racine) et se recalculent à partir du
labo avec `scripts/measure_dimensionnement.sh`.

| Grandeur | Formule | Valeur mesurée (labo) | Retenue pour le dimensionnement |
|---|---|---|---|
| Volume syslog | `EPS × 86 400 × L` (F1) | 118,5 B/ligne, 0,036 EPS | `L = 810 B` (calibré sur l'estimateur Cisco) |
| Export NetFlow | `F × R × 8` (F3, ntop) | 488,7 B/flux, 0,023 flux/s | `R = 489 B/flux` (brut nfdump) |
| Stockage 30 j | `(V_syslog + V_netflow) × 30 × k` (F5) | ≈ 104 MB | 903 GB (PME 50) / 9,0 TB (entreprise 500) |
| RAM | `Σ RSS mesurés × 1,3` (F6) | 0,35 GiB applicatif (4 serveurs MCP + relais) | 8 GiB |
| TCO 3 ans | `CAPEX + hébergement + énergie + main-d'œuvre` (F8) | labo : 1 509 € HT | PME : 13 852 € HT (385 €/mois) |
