# Serveur 3 — Analyse IA du NOC (10 outils)

Serveur MCP d'analyse : corrélation d'alarmes multi-sources, cause racine
(RCA) et génération de rapports d'incident, ancrés dans les ressources
documentaires (topologie, inventaire, runbooks).

- **Framework** : FastMCP 3.x (`fastmcp>=3.0,<4.0`), Python 3.12 (exigence A.4)
- **Transport** : stdio (démonstration via MCP Inspector)
- **Aucun secret** : les données sont des fichiers JSON locaux dans `data/`.

## Outils (10)

| Outil | Rôle |
|---|---|
| `correlate_alarms` | regroupe les alarmes proches dans le temps et dans le réseau |
| `analyze_root_cause` | cause racine documentée par les sorties réelles |
| `generate_incident_report` | rapport d'incident construit à partir d'un runbook |
| `detect_anomalies` | interprétation d'alertes pré-calculées (seuils déterministes) |
| `formuler_hypothese` | hypothèse de cause racine demandée au LLM (primitive `sampling`, refus possible) |
| `get_interface_stats`, `get_bgp_peers`, `get_ospf_neighbors`, `ping_host`, `qos_stats` | lectures de contexte |

## Resources (3)

`noc://topology` · `noc://inventory` · `noc://runbooks`

## Prompts (2)

`qualifier_incident` · `resume_journalier`

## Données (`data/`)

`topology.json`, `inventory.json`, `runbooks.json`, `sample_alarms.json`,
`sample_syslog.json`, `simulated_metrics.json`.

## Démarrage

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python server.py             # stdio, "Command" de MCP Inspector
```

## Conformité

- **B.7** : `detect_anomalies` ne confie aucun calcul statistique au LLM —
  les seuils sont codés en dur, le modèle ne fait qu'interpréter.
- **B.7 / B.8** : les conclusions sont appuyées sur des sorties réelles et
  sur les runbooks ; tout rapport porte le statut
  `EN_ATTENTE_DE_VALIDATION_HUMAINE`.
- **B.6** : aucun outil n'écrit sur le réseau.
