"""
Acces CLI des routeurs FRR via SSH (cahier B.5 / B.6).

- Lecture seule stricte : les commandes envoyees sont figees
  (« show ... »), aucun argument utilisateur n'atteint le shell.
- Compte membre du groupe frrvty (vtysh en lecture seule).
- Cible bornee a l'inventaire du laboratoire.
- Verification de la cle d'hote :
    SSH_KNOWN_HOSTS=<fichier>  -> verification stricte (defaut si present)
    SSH_HOSTKEY_POLICY=strict  -> cle inconnue = refus (sans fichier)
    SSH_HOSTKEY_POLICY=accept-new -> cle enregistree a la premiere connexion
                                     (labo : les cles changent a chaque
                                     redeloiement), comportement documente.
"""

from __future__ import annotations

import json
import os
import shlex
from pathlib import Path

import paramiko

from tools.targets import target_error

DEFAULT_KNOWN_HOSTS = Path(__file__).resolve().parent.parent / "resources" / "known_hosts"


def _load_host_keys(path: Path) -> paramiko.HostKeys | None:
    if not path.is_file():
        return None
    keys = paramiko.HostKeys()
    try:
        keys.load(str(path))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Fichier known_hosts illisible ({path}) : {exc}") from exc
    return keys


class _CheckingPolicy(paramiko.MissingHostKeyPolicy):
    """Enregistre la cle si accept-new, refuse sinon (jamais AutoAdd silencieux)."""

    def __init__(self, client: paramiko.SSHClient, save_to: Path | None):
        self._client = client
        self._save_to = save_to

    def missing_host_key(self, client, hostname, key):
        policy = os.environ.get("SSH_HOSTKEY_POLICY", "accept-new").strip().lower()
        if policy != "accept-new":
            raise paramiko.SSHException(
                f"Cle d'hote inconnue pour {hostname} (SSH_HOSTKEY_POLICY={policy})"
            )
        client.get_host_keys().add(hostname, key.get_name(), key)
        if self._save_to is not None:
            try:
                self._save_to.parent.mkdir(parents=True, exist_ok=True)
                with self._save_to.open("a", encoding="utf-8") as handle:
                    handle.write(f"{hostname} {key.get_name()} {key.get_base64()}\n")
            except OSError:
                pass  # l'enregistrement best-effort n'empeche pas la connexion


def _ssh_client(hostname: str) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    known = os.environ.get("SSH_KNOWN_HOSTS", "").strip()
    known_path = Path(known) if known else DEFAULT_KNOWN_HOSTS

    host_keys = _load_host_keys(known_path)
    if host_keys is not None:
        client.set_host_keys(str(known_path))
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
    else:
        # Pas de fichier de reference : cle acceptee a la premiere connexion
        # puis memorisee (comportement « accept-new »), jamais ignorée.
        save_to = known_path if os.environ.get("SSH_KNOWN_HOSTS") else None
        client.set_missing_host_key_policy(_CheckingPolicy(client, save_to))
    return client


def _vtysh(ip: str, command: str) -> dict:
    """Execute une commande vtysh figee sur un equipement via SSH (lecture seule).

    Les identifiants sont lus dans le .env du serveur (ROUTER_SSH_USER /
    ROUTER_SSH_PASS). Le compte utilise est membre du groupe frrvty :
    vtysh est donc strictement en lecture seule.
    """
    refused = target_error(ip)
    if refused:
        return refused

    username = os.environ.get("ROUTER_SSH_USER", "noc")
    password = os.environ.get("ROUTER_SSH_PASS", "")
    port = int(os.environ.get("ROUTER_SSH_PORT", "22"))

    if not password:
        return {
            "status": "error",
            "error": "ROUTER_SSH_PASS manquant : renseigner le .env du serveur",
        }

    client = _ssh_client(ip)
    return_code = -1

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
