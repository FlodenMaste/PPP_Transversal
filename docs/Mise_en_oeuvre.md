# Partie II — Mise en œuvre par scénarios (résultats observés)

> Ce document est la **Partie II** du rapport PPP : la mise en œuvre est présentée sous
> forme de **scénarios exécutés**, avec pour chacun la commande et le **résultat réellement
> observé** le 20 octobre 2026 dans le laboratoire du dépôt.
>
> Revue d'architecture et ADR associés : `docs/Architecture.md`.
> Journal brut de la campagne : `docs/campagne_scenarios.txt`.
> Résultats machine : `docs/scenarios_resultats.json` (29 appels).

---

## 0. Environnement et reproduction

| Élément | Valeur observée |
|---|---|
| Dépôt | `PPP_Transversal/` (référentiel unique) |
| Framework MCP | **FastMCP 3.4.8** dans les 4 venv (`fastmcp>=3.0,<4.0`) |
| Laboratoire | Containerlab : `r1`, `r2`, `r3` (FRR, images `mcp-noc-frr:local`) + `client` + `server` (`mcp-noc-term:local`), gestion 172.20.20.0/24 |
| Télémétrie | relais syslog udp/1514 + nfcapd udp/9995 (`scripts/lab_services.sh`) |
| Identité | Keycloak `http://localhost:18080/realms/mcp-noc` (clients `mcp-cli` PKCE, `mcp-cli-ropc`) |
| Prérequis | `containerlab deploy --reconfigure`, `sudo scripts/lab_services.sh`, `.env` local par serveur |

**Chaîne d'exécution** (depuis la racine du dépôt, en compte utilisateur) :

```bash
sudo PPP_MCP_Telecom_Supervision/venv/bin/python \
     PPP_MCP_Telecom_Supervision/lab/validate_collectors.py   # contrôle du labo
./PPP_MCP_Telecom_Supervision/venv/bin/python scripts/run_scenarios.py \
     --json docs/scenarios_resultats.json                      # campagne S0→S7
```

> **Note d'exploitation** : le laboratoire a dû être redéployé après redémarrage de la
> machine (sshd/NETCONF/SNMP disparus). C'est le comportement attendu d'un labo
> Containerlab : tout état vivant (`shutdown` en running-config, sessions BGP) est perdu.

---

## S0 — Inventaire des primitives MCP exposées

| Serveur | Commande | **Observé** |
|---|---|---|
| socle | `tools/list`, `resources/list`, `prompts/list` | **13 outils** / 3 ressources / 3 prompts |
| serveur 2 (`noc-mcp-server`) | idem | **9 outils** / 4 ressources / 3 prompts |
| serveur 3 (`mcp-noc-ai`) | idem | **10 outils** / 3 ressources / 2 prompts |
| serveur 1 (`mcp-noc-telecom`) | idem (stdio + HTTP) | **3 outils** / 1 ressource / 1 prompt |

**Total : 35 outils, 11 ressources, 9 prompts** sur 4 processus FastMCP 3.4.8.
Les listes complètes (noms, descriptions, schémas d'arguments) sont dans
`docs/schemas/*.json`, générés depuis `tools/list`.

---

## S1 — Découverte du réseau (ressources documentaires)

L'agent n'interroge pas encore le réseau : il se documente. Quatre ressources lues sur le
serveur 2 + génération d'un prompt de diagnostic.

| Ressource | **Observé** |
|---|---|
| `noc://topology` | 2 044 octets — nœuds `r1` (172.20.20.11, loopback 1.1.1.1), `r2`, `r3`, `client`, `server` |
| `noc://inventory` | 1 418 octets — `r1`, type `router`, vendor `FRRouting`, localisation `NOC-LAB` |
| `noc://ipam` | 1 549 octets — `172.20.20.0/24` (management SNMP+SSH), sous-réseaux de service |
| `noc://runbook/restart-switch` | 860 octets — runbook en 2 étapes (ping, puis isolation) |
| Prompt `network_diagnosis` | généré : « Tu es un ingénieur NOC chargé de diagnostiquer … l'équipement r1 » |

---

## S2 — État des équipements (SNMPv3 authPriv)

| Outil (serveur) | Arguments | **Observé** | Durée |
|---|---|---|---|
| `snmp_get` (s2) | `ip=172.20.20.11, oid=1.3.6.1.2.1.1.1.0` | `Linux r1 7.0.0-38-generic #38~24.04.4-Ubuntu … x86_64` | 387 ms |
| `snmp_walk` (s2) | `ip=172.20.20.12, oid=1.3.6.1.2.1.1` | branche système de r2 : sysDescr + sysObjectID `1.3.6.1.4.1.8072.3.2.10` (net-snmp) | 655 ms |
| `get_interface_stats` (s2) | `ip=172.20.20.13` | table IF-MIB de r3 (indexes 1, 2, 27, 32 …) | 1 143 ms |
| `get_device_status` (s2) | `name=r1` | `{"name":"r1","type":"router","ip":"172.20.20.11","vendor":"FRRouting","role":"edge …"}` | 31 ms |

Les réponses SNMP sont marquées `"untrusted": true` : les valeurs sont du texte externe,
jamais interprétées comme des instructions (garde anti prompt-injection, ADR-08).

---

## S3 — Connectivité

| Outil | Arguments | **Observé** |
|---|---|---|
| `ping_host` | `ip=172.20.20.13` | `reachable: true`, `icmp_seq=1 … time=0.064 ms`, 4 réponses, 0 % de perte |
| `traceroute_host` | `ip=172.20.20.13` | 1 saut : `clab-mcp-noc-lab-r3 (172.20.20.13)` — client et serveur sont séparés par r1 puis r3 |

---

## S4 — Routage (lecture seule)

| Outil | Arguments | **Observé** |
|---|---|---|
| `get_bgp_peers` | `ip=172.20.20.11` | AS 65000, router-id 1.1.1.1, **2 pairs iBGP**, RIB 17 entrées, préfixes échangés avec 2.2.2.2 et 3.3.3.3 |
| `get_ospf_neighbors` | `ip=172.20.20.12` | voisin `3.3.3.3`, état `Full/DR`, `converged: Full`, uptime ≈ 1 796 s |

**Contrôle de recette à utiliser** (le rapport initial employait une commande inadaptée) :

```bash
docker exec clab-mcp-noc-lab-r1 vtysh -c "show ip ospf neighbor" | grep -c Full   # attendu : 2
docker exec clab-mcp-noc-lab-r1 vtysh -c "show ip bgp summary" \
  | awk 'NR>8 && $10 ~ /^[0-9]+$/ {print $1, $10}'                                # pairs + préfixes reçus
```

> `show ip bgp summary` n'affiche **pas** « Established » : la colonne
> `State/PfxRcd` porte le **nombre de préfixes reçus** une fois la session établie
> (ici `2.2.2.2 … 4` et `3.3.3.3 … 5`). Toute recette qui greppait « Established »
> échouait à tort.

---

## S5 — Configuration (NETCONF RFC 6241, lecture seule)

| Outil | Arguments | **Observé** |
|---|---|---|
| `netconf_get` | `host=172.20.20.11` (port 830) | `<?xml version="1.0"…><frr-configuration xmlns="urn:lab:frr:netconf:1.0"><system><hostname>r1</hostname>…` |

Correctif d'exploitation apporté : `noc-mcp-server/.env` ne définissait pas
`NETCONF_USERNAME` / `NETCONF_PASSWORD` → le serveur refusait de démarrer (« aucun secret
en argument d'outil », B.6). Le `.env` local et le `.env.example` (placeholders) ont été
complétés ; le serveur démarre désormais et NETCONF répond en 622 ms.

---

## S6 — Trafic et télémétrie

| Outil (socle) | Arguments | **Observé** |
|---|---|---|
| `get_recent_syslog` | `limit=10` | entrées normalisées (`facility=AUTH`, `mnemonic=sshd`, `Accepted password for noc from 172.20.20.1 …`) — flux **réel** du relais udp/1514 |
| `analyze_netflow` | `device=172.20.20.11, window=last_5_minutes` | top talkers : `2.2.2.2 → 1.1.1.1` TCP/179 (iBGP), 8 831 octets / 130 paquets — flux **réel** du nfcapd udp/9995 |
| `qos_stats` | `device=172.20.20.11` | file 2 : 544 paquets, 0 drop ; file 26 : 397 paquets, 0 drop |
| `detect_anomalies` | `window=last_5_minutes` | `anomaly_count: 0`, seuils affichés (`top_talker_ratio 0.8`, `min_packets 1000`) — **détection déterministe hors LLM** (B.7) |

---

## S7 — Incident et cause racine (B.7 / B.8)

Chaîne complète sur le serveur 3, à partir des événements d'incident :

| Outil (s3) | **Observé** |
|---|---|
| `correlate_alarms` | candidat `INC-6c3a8d9d`, 2 équipements (`r1`, `r2`), **16 événements** groupés sur 15 min |
| `detect_anomalies` | `eth1` r1 ↔ r2 `status: down`, compteurs `in_octets 938 475 610` / `out_octets 902 837 465` |
| `analyze_root_cause` | chronologie : `%LINK-3-UPDOWN: Interface eth1, changed state to down` (r1 et r2) — **preuves rassemblées, aucune spéculation** |
| `formuler_hypothese` | **sampling** : « coupure du lien primaire r1<->r2 (eth1), bascule OSPF sur r1<->r3. **A VALIDER PAR UN OPERATEUR** » |
| `generate_incident_report` | rapport structuré (chronologie + résumé), statut **`EN_ATTENTE_DE_VALIDATION_HUMAINE`** |

Point saillant : l'hypothèse n'est **pas** appliquée ; elle est rendue au client sous
réserve de validation humaine, conformément à B.8 et à l'ADR-08.

---

## S8 — Sécurité : consentement, RBAC, injection, audit

Exécuté contre le **serveur 1** (`mcp-noc-telecom`), qui porte le modèle de conformité A.6.

### 8.1 Consentement réel + OAuth 2.1 PKCE (hors navigateur)

`python test_elicitation_http.py` (serveur 1 en Streamable HTTP :8001) :

```
[1] OAuth 2.1 + PKCE S256 -> jeton operateur
[2] connecte a mcp-noc-telecom v3.4.8
[3] tools/list -> 3 outils
[4] tools/call snmp_get (consentement humain requis)...
  [ELICITATION RECUE] CONSENTEMENT HUMAIN REQUIS
[5] RESULTAT -> isError=False
    {"success":true,"router":"r1","oid":".1.3.6.1.2.1.1.1.0",
     "raw_output":"SNMPv2-MIB::sysDescr.0 = STRING: Linux r1 7.0.0-38-generic …"}
[6] demandes d'elicitation recues : 1 -> OK
```

Contrôles complémentaires sur le même port : `GET /.well-known/oauth-protected-resource/mcp`
→ RFC 9728, issuer Keycloak ; requête **sans** jeton → **401**.

> Réalisation observée : le serveur 1 ne lie pas SNMP lui-même — il exécute
> `docker exec clab-mcp-noc-lab-client snmpwalk -v3 -l authPriv …` (3 dépendances au
> total : `fastmcp`, `pyjwt`, `python-dotenv`). Le `sysDescr` ci-dessus provient donc
> réellement du conteneur `client` du laboratoire interrogant r1.

### 8.2 RBAC, refus et journal d'audit

`python test_mcp.py` + `python demo_securite.py` :

| Contrôle | **Observé** |
|---|---|
| Rôle hors hiérarchie (`invite`) | refus : « Roles ['invite'] hors RBAC (['operateur','superviseur','administrateur']) » |
| Jeton absent | refus : « Jeton manquant : authentification requise » |
| Injection de prompt (flux syslog piégé) | **3 patterns neutralisés**, statut `ALERTE_INJECTION_NEUTRALISEE` dans l'audit |
| Journal d'audit | 98+ entrées JSONL : `user`, `tool`, `params`, `status`, `detail` |

### 8.3 Suites de tests automatisées (103 tests)

| Suite | Porte | Résultat |
|---|---|---|
| socle `pytest` | primitives, collecteurs, formatage | **52 passed** (4,9 s) |
| serveur 2 `pytest` | outils de collecte | **7 passed** (4,8 s) |
| serveur 3 `pytest` | corrélation / analyse | **14 passed** (4,7 s) |
| serveur 1 `pytest test_a6_security.py` | auth, RBAC, consentement, sanitizer, audit | **30 passed** (12,1 s) |
| **Total** | | **103 passed, 0 échec** |

> Les 30 tests du serveur 1 (et non 28) constituent la preuve A.6 ; c'est le chiffre à
> retenir dans le rapport.

---

## S9 — Robustesse : injection de panne et guérison

Scénario B.8 exécuté avec `lab/fault-injection/inject_bgp_flap.sh` (coupure par
`shutdown` de l'interface, uniquement en running-config).

| Étape | Commande | **Observé** |
|---|---|---|
| 1. Nominal | `inject_bgp_flap.sh status` | OSPF r1 : **2 voisins Full** ; BGP r1 : 2 pairs, préfixes reçus `4` (r2) et `5` (r3) |
| 2. Panne | `inject_bgp_flap.sh link_down` | lien r1↔r2 coupé ; `%OSPF AdjChg` émis des deux côtés vers le relais syslog |
| 3. Pendant la panne | `status` | OSPF r1 : **1 seul voisin** (`3.3.3.3`) ; route vers le LAN serveur via **eth2 (cost 100)** |
| 4. Supervision pendant la panne | `run_scenarios.py --only S4 --only S3` | **4 appels OK** : `ping_host`, `traceroute_host`, `get_bgp_peers`, `get_ospf_neighbors` — la plateforme répond et **montre** l'état dégradé (RIB 15 entrées au lieu de 17) |
| 5. Guérison | `inject_bgp_flap.sh link_up` | OSPF r1 : **2 voisins Full** (après 45 s de reconvergence) ; BGP : 2 pairs, `4` et `5` préfixes |
| 6. Retour au nominal | `show ip route 3.3.3.3` | `Known via "ospf", metric 20, best … via eth1` — **le chemin primaire est redevenu actif**, eth2 (cost 100) repassant en secours |

Conclusion du scénario : la coupure est détectable **par les outils MCP** (les nombres
d'entités changent réellement), la supervision ne s'arrête pas, et la topologie revient
à son état initial sans intervention manuelle sur les outils MCP (la restauration est un
acte d'exploitation, jamais une action IA — ADR-06).

---

## Synthèse : outils MCP intégrés et exploités

Exigence B.5 : **au minimum 10 outils MCP intégrés et exploités**. Sur la campagne et les
scénarios de sécurité, **21 exécutions d'outils** portant sur **19 outils distincts** ont
été observées sur **3 des 4 processus** du dépôt.

| # | Outil | Serveur | Scénario | Résultat observé (extrait) |
|---|---|---|---|---|
| 1 | `snmp_get` | serveur 2 | S2 / S8 | sysDescr de r1 : `Linux r1 7.0.0-38-generic …` |
| 2 | `snmp_walk` | serveur 2 | S2 | branche `1.3.6.1.2.1.1` de r2 (net-snmp) |
| 3 | `get_interface_stats` | serveur 2 | S2 | table IF-MIB de r3 |
| 4 | `get_device_status` | serveur 2 | S2 | fiche r1 (FRRouting, role edge) |
| 5 | `ping_host` | serveur 2 | S3 | `reachable: true`, 0 % de perte |
| 6 | `traceroute_host` | serveur 2 | S3 | 1 saut jusqu'à r3 |
| 7 | `get_bgp_peers` | serveur 2 | S4 | AS 65000, 2 pairs iBGP |
| 8 | `get_ospf_neighbors` | serveur 2 | S4 | `Full/DR` avec 3.3.3.3 |
| 9 | `netconf_get` | serveur 2 | S5 | `<frr-configuration>…` sur r1:830 |
| 10 | `get_recent_syslog` | socle | S6 | entrées AUTH/sshd réelles |
| 11 | `analyze_netflow` | socle | S6 | top talker BGP (TCP/179) |
| 12 | `qos_stats` | socle | S6 | 0 drop, 544 paquets (file 2) |
| 13 | `detect_anomalies` | socle | S6 | `anomaly_count: 0` (seuils visibles) |
| 14 | `correlate_alarms` | serveur 3 | S7 | `INC-6c3a8d9d`, 16 événements |
| 15 | `detect_anomalies` | serveur 3 | S7 | `eth1 … down` entre r1 et r2 |
| 16 | `analyze_root_cause` | serveur 3 | S7 | `%LINK-3-UPDOWN … eth1` (preuves) |
| 17 | `formuler_hypothese` | serveur 3 | S7 | hypothèse **sampling** + validation humaine |
| 18 | `generate_incident_report` | serveur 3 | S7 | rapport, statut `EN_ATTENTE_DE_VALIDATION_HUMAINE` |
| 19 | `get_ospf_neighbors` | serveur 3 | S7 | voisinage r2 dans la corrélation |
| 20 | `snmp_get` | **serveur 1** | S8 | elicitation reçue + sysDescr réel |
| 21 | `get_syslog_message` / `snmp_get_secure` | **serveur 1** | S8 | refus RBAC, injection neutralisée, audit (suite A.6) |

**Répartition par serveur** : socle 4 · serveur 2 9 · serveur 3 6 · serveur 1 2.
**Aucun échec** : 0 erreur sur les 29 appels de la campagne (sortie code 0).

---

## Synthèse transverse

| Indicateur | Valeur observée |
|---|---|
| Collecteurs opérationnels | **13 / 13** (`validate_collectors.py`, sortie code 0) |
| Outils MCP exploités | **21 exécutions / 19 outils distincts** |
| Consentements humains demandés et accordés | **18** (campagne) + 1 elicitation réelle (S8) |
| Appels de *sampling* | **1** (`formuler_hypothese`) |
| Tests automatisés | **103 passed / 0 échec** |
| Journal d'audit | 98+ entrées, y compris refus et alertes d'injection |
| Disponibilité pendant une panne | 4 appels réussis pendant la coupure r1↔r2 |

---

## Limites et corrections apportées à l'existant

1. **NETCONF non renseigné** dans `noc-mcp-server/.env` → corrigé (S5).
2. **Consentement en simulation par défaut** (`CONSENT_MODE=dry_run`) dans le `.env` du
   serveur 1 → ramené à `elicitation` ; la simulation reste possible par variable
   d'environnement explicite (Inspector, tests).
3. **Contrôle BGP inopérant** (recherche de « Established ») → remplacé par un test
   numérique sur `State/PfxRcd` (S4).
4. **Chiffres à corriger dans le rapport** : 30 tests A.6 (et non 28) ; FastMCP 3.4.8
   partout (il n'existe aucune divergence vers 4.x) ; le jeton automatisé s'obtient avec
   `client_id=mcp-cli-ropc` (ROPC), `mcp-cli` servant au flux PKCE.
5. **Topologie réelle** : la route du LAN serveur est apprise **uniquement** par r3 (iBGP
   sans route-reflector) ; le lien r1↔r2 porte le détour primaire vers r3 via OSPF
   (metric 20 contre 100 sur le lien direct). La redondance est donc réelle sur le
   **chemin**, partielle sur la **distribution iBGP** (voir `docs/Architecture.md`, W3).
