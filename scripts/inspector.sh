#!/usr/bin/env bash
# Environnement de demonstration MCP Inspector (exigences A.5 et A.7).
#
# Lance un ou plusieurs serveurs MCP sous MCP Inspector (interface web) :
# chaque serveur a son propre onglet et son propre port.
#
# Usage :
#   scripts/inspector.sh                 # les 4 serveurs
#   scripts/inspector.sh serveur1        # un seul serveur
#   scripts/inspector.sh --dry-run       # affiche les commandes sans rien lancer
#
# Serveurs et ports :
#   serveur1 (securite A.6)  6274      socle (collecte, 13 outils)  6574
#   serveur2 (9 outils)      6374      serveur3 (analyse IA)        6474
#
# Le lanceur Inspector est resolu dans cet ordre :
#   1. $MCP_INSPECTOR (chemin explicite)
#   2. le cache npx local (~/.npm/_npx/.../mcp-inspector) : fonctionne hors ligne
#   3. npx --yes @modelcontextprotocol/inspector (necessite le reseau)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRY_RUN=0
TARGETS=()

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    serveur1|serveur2|serveur3|socle|all) TARGETS+=("$arg") ;;
    *) echo "Argument inconnu : $arg (attendu : socle|serveur1|serveur2|serveur3|all|--dry-run)" >&2; exit 2 ;;
  esac
done
if [[ ${#TARGETS[@]} -eq 0 ]]; then TARGETS=(all); fi

# --- resolution du lanceur MCP Inspector -------------------------------
resolve_insp() {
  if [[ -n "${MCP_INSPECTOR:-}" ]]; then echo "$MCP_INSPECTOR"; return; fi
  local cached
  cached="$(ls -1 "$HOME"/.npm/_npx/*/node_modules/.bin/mcp-inspector 2>/dev/null | head -n1 || true)"
  if [[ -n "$cached" && -x "$cached" ]]; then echo "$cached"; return; fi
  echo "npx --yes @modelcontextprotocol/inspector"
}
INSP="$(resolve_insp)"

# --- definition des serveurs ------------------------------------------
declare -a NAMES PORTS DIRS CMDS
add() { NAMES+=("$1"); PORTS+=("$2"); DIRS+=("$3"); CMDS+=("$4"); }

add serveur1 6274 "mcp-noc-telecom/server" "./venv/bin/python -m server.main"
add serveur2 6374 "noc-mcp-server"         "./venv/bin/python server.py"
add serveur3 6474 "mcp-noc-ai"             "./venv/bin/python server.py"
add socle    6574 "PPP_MCP_Telecom_Supervision" "./venv/bin/python -m mcp_server.server"

for i in "${!NAMES[@]}"; do
  sel=0
  for t in "${TARGETS[@]}"; do
    if [[ "$t" == "all" || "$t" == "${NAMES[$i]}" ]]; then sel=1; fi
  done
  if [[ $sel -eq 0 ]]; then continue; fi

  name="${NAMES[$i]}"; port="${PORTS[$i]}"; dir="${ROOT}/${DIRS[$i]}"; cmd="${CMDS[$i]}"
  log="/tmp/insp_${name}.log"
  venv_ok=1
  if [[ ! -x "${dir}/venv/bin/python" ]]; then venv_ok=0; fi

  if [[ $DRY_RUN -eq 1 ]]; then
    echo "[dry-run] cd ${DIRS[$i]} && CLIENT_PORT=$port MCP_SANDBOX_PORT=$((port+1)) $INSP $cmd"
    if [[ $venv_ok -eq 0 ]]; then
      echo "          ^ venv absent : cd ${DIRS[$i]} && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt"
    fi
    continue
  fi

  if [[ $venv_ok -eq 0 ]]; then
    echo "[!] $name : venv absent -> (cd ${DIRS[$i]} && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt)" >&2
    continue
  fi

  echo "[*] $name : lancement de l'Inspector sur le port $port (log: $log)"
  ( cd "$dir" && setsid env CLIENT_PORT="$port" MCP_SANDBOX_PORT="$((port+1))" \
      $INSP $cmd >"$log" 2>&1 </dev/null & )
done

if [[ $DRY_RUN -eq 1 ]]; then exit 0; fi

sleep 4
echo
for i in "${!NAMES[@]}"; do
  log="/tmp/insp_${NAMES[$i]}.log"
  if [[ ! -f "$log" ]]; then continue; fi
  url="$(grep -o "http://127.0.0.1:${PORTS[$i]}[^ ]*" "$log" | head -n1 || true)"
  if [[ -n "$url" ]]; then
    echo "  ${NAMES[$i]} (port ${PORTS[$i]}) : $url"
  else
    echo "  ${NAMES[$i]} : en attente de lancement, voir $log"
  fi
done
