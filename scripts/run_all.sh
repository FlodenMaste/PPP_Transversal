#!/usr/bin/env bash
# Regenere les schemas JSON des outils des 4 serveurs (exigence A.7).
# Chaque serveur est charge avec son propre venv (versions FastMCP distinctes).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/docs/schemas"
mkdir -p "$OUT"

(cd "$ROOT/PPP_MCP_Telecom_Supervision" \
  && ./venv/bin/python "$ROOT/scripts/export_schemas.py" mcp_server.server mcp-noc-socle "$OUT/mcp-noc-socle.json")

(cd "$ROOT/mcp-noc-telecom/server" \
  && ./venv/bin/python "$ROOT/scripts/export_schemas.py" server.main mcp-noc-telecom "$OUT/mcp-noc-telecom.json")

(cd "$ROOT/noc-mcp-server" \
  && ./venv/bin/python "$ROOT/scripts/export_schemas.py" server noc-mcp-server "$OUT/noc-mcp-server.json")

(cd "$ROOT/mcp-noc-ai" \
  && ./venv/bin/python "$ROOT/scripts/export_schemas.py" server mcp-noc-ai "$OUT/mcp-noc-ai.json")

echo "Schemas regeneres dans $OUT"
