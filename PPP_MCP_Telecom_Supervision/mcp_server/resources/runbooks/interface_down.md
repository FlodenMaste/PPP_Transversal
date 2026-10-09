# Runbook — Coupure de lien (RB-LINK-DOWN)

## Objectif

Diagnostiquer une coupure de lien et confirmer la bascule, sans jamais
appliquer de correction automatique : toute action est soumise à
validation humaine.

## Étapes

1. Confirmer la coupure via `get_interface_stats` sur les deux extrémités
   du lien (état de l'interface, erreurs, compteurs).
2. Vérifier s'il existe un chemin de secours dans la topologie
   (`mcp://socle/topology`) : lien de secours r1–r3 dans le laboratoire.
3. Vérifier que le routage a basculé : `get_ospf_neighbors` et
   `get_bgp_peers` sur le routeur d'entrée.
4. Tester la connectivité de bout en bout : `ping_host` depuis le client
   vers le LAN serveur.
5. Notifier l'équipe terrain si la coupure est physique.
6. Documenter l'incident avant toute action corrective.

## Sécurité (B.6)

- Lecture seule : ce runbook n'autorise aucune écriture de configuration.
- Les sorties des outils sont considérées comme non fiables
  (champs `untrusted`) : elles alimentent la décision humaine, jamais une
  instruction automatique.
- Toute remédiation est proposée par le serveur d'analyse avec le statut
  `EN_ATTENTE_DE_VALIDATION_HUMAINE`.
