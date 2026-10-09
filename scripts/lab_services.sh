#!/usr/bin/env bash
# Services d'acquisition de l'hote pour le laboratoire NOC (telemetrie B.3).
#
#   1. relais syslog  : udp/1514 -> /var/log/network_syslog.log (normalise,
#                       cf. scripts/syslog_relay.py) - lu par le collecteur
#                       syslog du socle en mode reel ;
#   2. collecteur NetFlow : nfcapd ecoute udp/9995 et ecrit /var/netflow
#                       (rotation 60 s) - lu par analyze_netflow (nfdump).
#
# Les routeurs/terminaux exportent via respectivement busybox `syslogd -R`
# et `softflowd` (cf. lab/containerlab/topology.clab.yml).
#
# Utilisation :
#   sudo scripts/lab_services.sh          # demarre ce qui manque
#   sudo scripts/lab_services.sh stop     # arrete les deux services
#   sudo scripts/lab_services.sh status   # etat
#
# Idempotent : re-execution sans effet si les services tournent deja.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RELAY_LOG="${RELAY_LOG:-/var/log/syslog_relay.out}"
NETFLOW_DIR="${NETFLOW_DATA_DIR:-/var/netflow}"
NETFLOW_PORT="${NETFLOW_PORT:-9995}"
SYSLOG_PORT="${SYSLOG_PORT:-1514}"

relay_running() { pgrep -f "python3? .*syslog_relay\.py" >/dev/null 2>&1; }
nfcapd_running() { pgrep -f "nfcapd .*-p ${NETFLOW_PORT}" >/dev/null 2>&1; }

start_relay() {
  if relay_running; then
    echo "[lab-services] relais syslog deja actif"
    return 0
  fi
  # setsid : survit au timeout du shell appelant (nohup seul ne suffit pas)
  setsid python3 "$ROOT/scripts/syslog_relay.py" --port "$SYSLOG_PORT" \
    </dev/null >>"$RELAY_LOG" 2>&1 &
  sleep 1
  relay_running && echo "[lab-services] relais syslog udp/$SYSLOG_PORT -> /var/log/network_syslog.log" \
    || { echo "[lab-services] ECHEC relais syslog (voir $RELAY_LOG)" >&2; return 1; }
}

start_nfcapd() {
  if nfcapd_running; then
    echo "[lab-services] nfcapd deja actif"
    return 0
  fi
  mkdir -p "$NETFLOW_DIR"
  nfcapd -D -p "$NETFLOW_PORT" -w "$NETFLOW_DIR" \
    -P "/var/run/nfcapd.${NETFLOW_PORT}.pid" -t 60
  sleep 1
  nfcapd_running && echo "[lab-services] nfcapd udp/$NETFLOW_PORT -> $NETFLOW_DIR (rotation 60 s)" \
    || { echo "[lab-services] ECHEC nfcapd" >&2; return 1; }
}

stop_all() {
  pkill -f "syslog_relay\.py" 2>/dev/null || true
  [ -f "/var/run/nfcapd.${NETFLOW_PORT}.pid" ] && kill "$(cat "/var/run/nfcapd.${NETFLOW_PORT}.pid")" 2>/dev/null || true
  echo "[lab-services] arret demande"
}

status() {
  relay_running && echo "[lab-services] relais syslog : ACTIF" || echo "[lab-services] relais syslog : arrête"
  nfcapd_running && echo "[lab-services] nfcapd : ACTIF" || echo "[lab-services] nfcapd : arrêt"
  if [ -d "$NETFLOW_DIR" ]; then
    echo "[lab-services] fichiers de flux : $(ls "$NETFLOW_DIR" | wc -l)"
  fi
}

case "${1:-start}" in
  start) start_relay; start_nfcapd ;;
  stop) stop_all ;;
  status) status ;;
  *) echo "usage: $0 [start|stop|status]" >&2; exit 2 ;;
esac
