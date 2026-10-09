import json
import os
import shlex

import paramiko


def _vtysh(ip: str, command: str) -> dict:
    """Execute une commande vtysh sur un equipement via SSH (lecture seule).

    Les identifiants sont lus dans le .env du serveur (ROUTER_SSH_USER /
    ROUTER_SSH_PASS). Le compte utilise est membre du groupe frrvty :
    vtysh est donc strictement en lecture seule.
    """
    username = os.environ.get("ROUTER_SSH_USER", "noc")
    password = os.environ.get("ROUTER_SSH_PASS", "")
    port = int(os.environ.get("ROUTER_SSH_PORT", "22"))

    if not password:
        return {
            "status": "error",
            "error": "ROUTER_SSH_PASS manquant : renseigner le .env du serveur",
        }

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            ip,
            port=port,
            username=username,
            password=password,
            timeout=10,
            banner_timeout=10,
            auth_timeout=10,
            allow_agent=False,
            look_for_keys=False,
        )

        _, stdout, stderr = client.exec_command(
            "vtysh -c {}".format(shlex.quote(command)),
            timeout=15,
        )

        output = stdout.read().decode("utf-8", errors="replace").strip()
        error = stderr.read().decode("utf-8", errors="replace").strip()
        return_code = stdout.channel.recv_exit_status()

    except Exception as exc:
        return {
            "status": "error",
            "host": ip,
            "error": str(exc),
        }

    finally:
        client.close()

    if return_code != 0:
        return {
            "status": "error",
            "host": ip,
            "error": error or output or f"code {return_code}",
        }

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        data = output

    return {
        "status": "success",
        "host": ip,
        "data": data,
    }


def get_bgp_peers(ip: str) -> dict:
    """Récupère les voisins BGP depuis FRRouting (via SSH)."""

    return _vtysh(ip, "show bgp summary json")


def get_ospf_neighbors(ip: str) -> dict:
    """Récupère les voisins OSPF depuis FRRouting (via SSH)."""

    return _vtysh(ip, "show ip ospf neighbor json")
