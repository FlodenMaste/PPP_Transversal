# Runbook — Problème sur un switch

## Objectif

Diagnostiquer un switch qui semble indisponible avant toute intervention.

## Étape 1 — Vérification Ping

Tester l'adresse IP du switch.

## Étape 2 — Traceroute

Effectuer un traceroute pour identifier une éventuelle rupture du chemin.

## Étape 3 — SNMP

Vérifier si le service SNMP répond.

## Étape 4 — Interfaces

Consulter l'état et les statistiques des interfaces.

## Étape 5 — Routage

Vérifier BGP ou OSPF si l'équipement participe au routage.

## Étape 6 — NETCONF

Utiliser NETCONF GET si disponible afin de consulter l'état de l'équipement.

## Étape 7 — Analyse

Comparer les résultats avec l'inventaire, la topologie et l'IPAM.

## Sécurité

Le serveur MCP ne doit pas redémarrer automatiquement un équipement réel.

Toute opération destructive doit nécessiter une intervention humaine autorisé
