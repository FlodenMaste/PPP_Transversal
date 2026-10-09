#!/usr/bin/env bash
# Mesures de terrain du labo -> entrees du calcul de dimensionnement
# (docs/Dimensionnement_TCO.md). A lancer depuis la racine du depot,
# labo depluye et services actifs (scripts/lab_services.sh start).
set -euo pipefail

echo "=== 1. Syslog (relais -> /var/log/network_syslog.log) ==="
SYSLOG=${NOC_SYSLOG_FILE:-/var/log/network_syslog.log}
if [ -f "$SYSLOG" ]; then
  wc -l -c "$SYSLOG" | awk '{
    printf "lignes=%s octets=%s octets/ligne=%.1f\n", $1, $2, $2/$1
  }'
else
  echo "absent: $SYSLOG"
fi

echo
echo "=== 2. NetFlow (softflowd -> nfcapd -> /var/netflow) ==="
NFDIR=${NETFLOW_DIR:-/var/netflow}
if [ -d "$NFDIR" ]; then
  du -sb "$NFDIR" | awk '{printf "octets sur disque=%s\n", $1}'
  echo "fichiers=$(ls "$NFDIR" | wc -l)"
  nfdump -r "$NFDIR" 2>/dev/null | tail -4 | grep -E "Summary|Time window"
  nfdump -r "$NFDIR" 2>/dev/null | grep -E "flows/second" | tail -1
else
  echo "absent: $NFDIR"
fi

echo
echo "=== 3. RSS des conteneurs labo (docker stats) ==="
docker stats --no-stream --format '{{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}' \
  | grep -E 'clab-mcp-noc-lab' | sort

echo
echo "=== 4. RSS des processus hote (relais, collectes) ==="
ps -eo rss,args | grep -E 'syslog_relay|nfcapd' | grep -v grep \
  | awk '{printf "%.1f MiB  %s\n", $1/1024, substr($0, index($0,$2))}'

echo
echo "=== 5. RSS des serveurs MCP (demarrer un serveur, relancer ce script) ==="
ps -eo rss,args | grep -E 'mcp_server\.server|server\.main|noc-mcp-server|venv/bin/python server\.py' \
  | grep -v grep | awk '{printf "%.1f MiB  %s\n", $1/1024, substr($0, index($0,$2))}'

echo
echo "=== 6. Hote ==="
free -h | awk '/^Mem:/ {printf "RAM totale=%s utilisee=%s disponibles=%s\n", $2, $3, $7}'
uptime | sed 's/^/ /'
df -h / | tail -1 | awk '{printf "disque %s utilise=%s libres=%s (%s)\n", $2, $3, $4, $5}'
