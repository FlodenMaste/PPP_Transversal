"""
Collecteur NetFlow - outil MCP cible : analyze_netflow.

Le calcul statistique brut est délégué à nfdump (outil
déterministe), jamais au LLM - le rôle de l'IA (bloc 4) se
limite à interpréter le résultat structuré qu'on lui fournit ici.

Pré-requis pour le mode réel :
    nfdump installé sur la machine et fichiers de flux
    disponibles dans NETFLOW_DATA_DIR.
"""

import subprocess
from typing import Any

from collector import config
from collector.common.schema import make_error_response, make_response
from collector.common.utils import (
    fixtures_dir,
    load_json_fixture,
    logger,
    resolve_device_key,
    unknown_device_message,
)

FIXTURES = fixtures_dir(__file__)


def _real_analyze_netflow(device_ip: str, window: str, top_n: int) -> dict[str, Any]:
    """Exécute nfdump en subprocess et parse la sortie.

    `window` est un filtre temporel nfdump (ex: "-t 2026/09/14.10:00:00-2026/09/14.10:05:00").
    On utilise ici -s record/bytes (tri par volume) et -n top_n pour les
    top talkers, au format CSV (-o csv). Les colonnes sont résolues par
    leur en-tête (sa/da/pr/ipkt/ibyt/opkt/obyt) : les index fixes ne
    sont pas stables entre versions de nfdump.
    """
    cmd = [
        config.NFDUMP_BIN,
        "-R", config.NETFLOW_DATA_DIR,
        "-s", "record/bytes",
        "-n", str(top_n),
        "-o", "csv",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)

    top_talkers: list[dict[str, Any]] = []
    header: list[str] | None = None
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("ts,"):
            header = line.split(",")
            continue
        if header is None:
            continue
        fields = line.split(",")
        if len(fields) != len(header):
            continue  # lignes de synthèse nfdump ("Summary", bilan, ...)
        row = dict(zip(header, fields))
        try:
            packets = int(row.get("ipkt", "0") or 0) + int(row.get("opkt", "0") or 0)
            nbytes = int(row.get("ibyt", "0") or 0) + int(row.get("obyt", "0") or 0)
        except ValueError:
            continue
        top_talkers.append(
            {
                "src_ip": row.get("sa", ""),
                "dst_ip": row.get("da", ""),
                "protocol": row.get("pr", ""),
                "src_port": int(row["sp"]) if row.get("sp", "").isdigit() else None,
                "dst_port": int(row["dp"]) if row.get("dp", "").isdigit() else None,
                "bytes": nbytes,
                "packets": packets,
            }
        )
        if len(top_talkers) >= top_n:
            break

    return {"window": window, "top_talkers": top_talkers, "raw_stdout": result.stdout}


def analyze_netflow(device_ip: str, window: str = "last_5_minutes", top_n: int = 10, mode: str | None = None) -> dict[str, Any]:
    """Retourne un résumé des flux (top talkers, volumes) pour un équipement."""
    simulated = config.is_simulated(mode)
    try:
        if simulated:
            table = load_json_fixture(FIXTURES / "netflow_sample.json")
            device_data = table.get(resolve_device_key(device_ip))
            if device_data is None:
                return make_error_response(
                        "netflow", device_ip,
                        unknown_device_message(device_ip, "de flux NetFlow"),
                        simulated=True,
                    )
            return make_response("netflow", device_ip, device_data, simulated=True)

        data = _real_analyze_netflow(device_ip, window, top_n)
        return make_response("netflow", device_ip, data, simulated=False)

    except subprocess.CalledProcessError as exc:
        logger.error("analyze_netflow (nfdump) failed for %s: %s", device_ip, exc.stderr)
        return make_error_response("netflow", device_ip, f"nfdump error: {exc.stderr}", simulated=simulated)
    except Exception as exc:  # noqa: BLE001
        logger.error("analyze_netflow failed for %s: %s", device_ip, exc)
        return make_error_response("netflow", device_ip, str(exc), simulated=simulated)
