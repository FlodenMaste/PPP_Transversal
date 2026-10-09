# Runbook — Instabilité de session BGP (RB-BGP-FLAP)

## Objectif

Qualifier un flapping de session BGP et identifier la cause racine,
sans intervenir sur la configuration.

## Étapes

1. Vérifier l'état de la session avec `get_bgp_peers` (état Active/Idle
   vs Established, compteurs de préfixes).
2. Vérifier la stabilité du lien physique sous-jacent avec
   `get_interface_stats` (erreurs, changes d'état).
3. Corréler avec les événements proches : `get_recent_syslog` sur les
   routeurs concernés.
4. Vérifier les timers BGP (hold-time / keepalive) si la session est
   régulièrement réinitialisée.
5. Si la cause est un lien instable, escalader vers l'équipe
   transmission.
6. Documenter l'incident avant toute action corrective.

## Sécurité (B.6)

- Lecture seule : aucun outil exposé ne modifie une configuration.
- Les sorties (`untrusted`) servent de preuves à la décision humaine.
- Toute remédiation est soumise à validation humaine avant application.
