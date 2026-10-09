#!/usr/bin/env python3
"""
Exporte les schemas JSON Schema des outils MCP (exigence A.7).

Chaque serveur est importe avec SON propre environnement virtuel, puis ses
outils sont serialises en JSON Schema (inputSchema / outputSchema).

Usage (depuis la racine du depot ou le sous-dossier du serveur) :

    ./venv/bin/python scripts/export_schemas.py <module> <nom_sortie> <sortie.json>

Exemples :
    (cd PPP_MCP_Telecom_Supervision && ../venv/... )  ->  voir scripts/run_all.sh
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def export(module_ref: str, server_name: str, output: Path) -> int:
    sys.path.insert(0, str(Path.cwd()))
    module = importlib.import_module(module_ref)
    mcp = getattr(module, "mcp", None)
    if mcp is None:
        raise SystemExit(f"{module_ref} : attribut 'mcp' introuvable")

    tools = asyncio.run(mcp.list_tools())
    payload = {
        "server": server_name,
        "framework": "fastmcp",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tool_count": len(tools),
        "tools": [
            {
                "name": t.name,
                "description": (t.description or "").strip(),
                "inputSchema": t.parameters,
                "outputSchema": getattr(t, "output_schema", None),
            }
            for t in sorted(tools, key=lambda x: x.name)
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{server_name}: {len(tools)} outils -> {output}")
    return len(tools)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    export(sys.argv[1], sys.argv[2], Path(sys.argv[3]))
