"""
Collecteur NETCONF du serveur 2 (cahier B.4 / B.6).

- Les identifiants ne sont JAMAIS un argument d'outil : ils sont lus dans
  le .env (NETCONF_USERNAME / NETCONF_PASSWORD), jamais versionne.
- Cible bornee a l'inventaire du laboratoire (tools/targets.py).
- Verification de la cle d'hote activee par defaut ; elle ne peut etre
  desactivee que explicitement (NETCONF_HOSTKEY_VERIFY=false), cas du
  labo Containerlab ou les cles changent a chaque redeloiement.
"""

from __future__ import annotations

import os

from ncclient import manager

from tools.targets import target_error


def _credentials() -> tuple[str, str]:
    username = os.environ.get("NETCONF_USERNAME", "").strip()
    password = os.environ.get("NETCONF_PASSWORD", "").strip()
    if not username or not password:
        raise ValueError(
            "Variables d'environnement obligatoires absentes : "
            "NETCONF_USERNAME / NETCONF_PASSWORD (aucun secret en argument d'outil)"
        )
    return username, password


def netconf_get(
    host: str,
    port: int = 830,
    filter_xml: str = "<filter type='subtree'></filter>",
) -> dict:
    """Operation NETCONF <get-config> en lecture seule."""
    refused = target_error(host)
    if refused:
        return refused

    try:
        username, password = _credentials()
    except ValueError as exc:
        return {"status": "error", "host": host, "error": str(exc)}

    verify = os.environ.get("NETCONF_HOSTKEY_VERIFY", "true").strip().lower() != "false"
    known_hosts = os.environ.get("NETCONF_KNOWN_HOSTS", "").strip()

    options: dict = {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "hostkey_verify": verify,
        "allow_agent": False,
        "look_for_keys": False,
        "timeout": 10,
    }
    if verify and known_hosts:
        options["userknownhostsfile"] = known_hosts

    try:
        with manager.connect(**options) as connection:
            response = connection.get(filter_xml)

            return {
                "status": "success",
                "host": host,
                "port": port,
                "data": response.data_xml,
            }

    except Exception as exc:
        hint = ""
        if "UnknownHost" in type(exc).__name__ or "host key" in str(exc).lower():
            hint = (
                " (cle d'hote inconnue : renseigner NETCONF_KNOWN_HOSTS, "
                "ou NETCONF_HOSTKEY_VERIFY=false dans le labo uniquement)"
            )
        return {
            "status": "error",
            "host": host,
            "port": port,
            "error": str(exc) + hint,
        }
