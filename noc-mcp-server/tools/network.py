"""
Tests de connectivité du serveur 2 (cahier B.5).

Les cibles sont bornees a l'inventaire du laboratoire (B.6 : le serveur
ne sert pas de relais vers n'importe quelle adresse).
"""

import subprocess

from tools.targets import target_error


def ping_host(ip: str) -> dict:
    """Teste si une adresse IP est joignable."""

    refused = target_error(ip)
    if refused:
        return refused

    try:
        result = subprocess.run(
            ["ping", "-c", "4", "-W", "2", ip],
            capture_output=True,
            text=True,
            timeout=15,
        )

        return {
            "status": "success" if result.returncode == 0 else "failed",
            "host": ip,
            "reachable": result.returncode == 0,
            "output": result.stdout or result.stderr,
        }

    except Exception as exc:
        return {
            "status": "error",
            "host": ip,
            "error": str(exc),
        }


def traceroute_host(ip: str) -> dict:
    """Effectue un traceroute vers une adresse IP."""

    refused = target_error(ip)
    if refused:
        return refused

    try:
        result = subprocess.run(
            ["traceroute", "-m", "12", ip],
            capture_output=True,
            text=True,
            timeout=30,
        )

        return {
            "status": "success" if result.returncode == 0 else "failed",
            "host": ip,
            "output": result.stdout or result.stderr,
        }

    except Exception as exc:
        return {
            "status": "error",
            "host": ip,
            "error": str(exc),
        }
