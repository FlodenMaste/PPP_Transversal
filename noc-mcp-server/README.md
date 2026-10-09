# Serveur 2 — Outils réseau temps réel (9 outils)

Serveur MCP d'outils de supervision réseau, conçu pour être branché sur le
laboratoire Containerlab du projet (SNMPv3 + SSH en lecture seule).

- **Framework** : FastMCP 3.x (`fastmcp>=3.0,<4.0`), Python 3.12 (exigence A.4)
- **Transport** : stdio (démonstration via MCP Inspector)

## Outils (9)

| Outil | Rôle |
|---|---|
| `ping_host` | accessibilité ICMP |
| `traceroute_host` | chemin IP vers un hôte |
| `snmp_get` / `snmp_walk` | SNMPv3 authPriv (lecture seule) |
| `get_interface_stats` | métriques d'interfaces |
| `get_bgp_peers` | état des voisins BGP |
| `get_ospf_neighbors` | voisinage OSPF |
| `netconf_get` | extraction de configuration YANG (lecture seule) |
| `get_device_status` | état synthétique d'un équipement |

## Resources (4)

`noc://topology` · `noc://inventory` · `noc://ipam` · `noc://runbook/restart-switch`

## Prompts (3)

`network_diagnosis` — prompt structuré de diagnostic réseau.
`performance_review` — revue de performance d'un segment.
`change_verification` — vérification d'un changement réseau.

## Démarrage

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # secrets du labo (jamais versionnés)
python test_client_roots.py   # liste outils / resources / prompt
```

### Via MCP Inspector

```bash
python server.py              # mode stdio, "Command" de l'Inspecteur
```

### Secrets

Les identifiants SNMPv3 et SSH du laboratoire sont lus depuis `.env`
(`.env.example` fournit la structure). Ce sont des comptes de
**démonstration en lecture seule** : ne jamais les réutiliser ailleurs.
Les valeurs du labo se trouvent dans
`../PPP_MCP_Telecom_Supervision/lab/containerlab/topology.clab.yml`.

## Sécurité

Aucun outil ne modifie une configuration réseau : les accès CLI passent par
des commandes `show` uniquement (liste blanche côté collecteur du socle),
et les comptes du labo sont limités à la lecture (`rouser … priv` en SNMPv3,
groupe `frrvty` en SSH).
