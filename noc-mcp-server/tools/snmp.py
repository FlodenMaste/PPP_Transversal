"""
Collecteur SNMP du serveur 2 - SNMPv3 authPriv exclusif (cahier B.5 / B.6).

Conformément au cahier des charges, les comptes SNMP sont en lecture seule
et les secrets ne sont JAMAIS un argument d'outil (ils vivent dans le .env,
jamais versionné) : aucune rétrocompatibilité SNMPv2c « community=public ».
Les cibles sont bornées à l'inventaire du laboratoire (tools/targets.py).
"""

import asyncio
import os

from pysnmp.hlapi.v3arch.asyncio import (
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    get_cmd,
)

from tools.targets import target_error


class SnmpConfigError(Exception):
    """Compte SNMPv3 manquant dans l'environnement (jamais de repli)."""


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SnmpConfigError(
            f"Variable d'environnement obligatoire absente : {name} "
            "(compte SNMPv3 en lecture seule, cf. .env - aucun repli community)"
        )
    return value


def _security():
    """Compte SNMPv3 authPriv lu dans le .env (aucun secret en argument)."""
    from pysnmp.hlapi.v3arch.asyncio import (
        UsmUserData,
        usmAesCfb128Protocol,
        usmAesCfb256Protocol,
        usmHMAC192SHA256AuthProtocol,
        usmHMACSHAAuthProtocol,
    )

    username = _require_env("SNMPV3_USER")
    auth_key = _require_env("SNMPV3_AUTH_KEY")
    priv_key = _require_env("SNMPV3_PRIV_KEY")

    if len(auth_key) < 8 or len(priv_key) < 8:
        raise SnmpConfigError(
            "Les cles SNMPv3 doivent mesurer au moins 8 caracteres (USM)"
        )

    auth_protocol = {
        "SHA": usmHMACSHAAuthProtocol,
        "SHA256": usmHMAC192SHA256AuthProtocol,
    }.get(os.environ.get("SNMPV3_AUTH_PROTOCOL", "SHA").upper(), usmHMACSHAAuthProtocol)

    priv_protocol = {
        "AES": usmAesCfb128Protocol,
        "AES256": usmAesCfb256Protocol,
    }.get(os.environ.get("SNMPV3_PRIV_PROTOCOL", "AES").upper(), usmAesCfb128Protocol)

    return UsmUserData(
        username,
        authKey=auth_key,
        privKey=priv_key,
        authProtocol=auth_protocol,
        privProtocol=priv_protocol,
    )


async def _snmp_get(ip, oid, security, port):
    target = await UdpTransportTarget.create(
        (ip, port),
        timeout=2,
        retries=1,
    )

    error_indication, error_status, error_index, var_binds = await get_cmd(
        SnmpEngine(),
        security,
        target,
        ContextData(),
        ObjectType(ObjectIdentity(oid)),
    )

    if error_indication:
        return {"status": "error", "error": str(error_indication)}

    if error_status:
        return {
            "status": "error",
            "error": error_status.prettyPrint(),
        }

    values = {}

    for oid_value, value in var_binds:
        values[str(oid_value)] = str(value)

    return {
        "status": "success",
        "host": ip,
        "values": values,
    }


def snmp_get(ip: str, oid: str, port: int = 161) -> dict:
    """GET SNMPv3 (authPriv, lecture seule). Les secrets viennent du .env."""
    refused = target_error(ip)
    if refused:
        return refused

    try:
        return asyncio.run(_snmp_get(ip, oid, _security(), port))

    except SnmpConfigError as exc:
        return {"status": "error", "host": ip, "error": str(exc)}
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
        }


async def _snmp_walk(ip, oid, security, port):
    from pysnmp.hlapi.v3arch.asyncio import walk_cmd

    target = await UdpTransportTarget.create(
        (ip, port),
        timeout=2,
        retries=1,
    )

    results = []
    root = oid.strip(".")
    max_entries = int(os.environ.get("SNMP_WALK_MAX_ENTRIES", "500"))

    async for error_indication, error_status, error_index, var_binds in walk_cmd(
        SnmpEngine(),
        security,
        target,
        ContextData(),
        ObjectType(ObjectIdentity(oid)),
        lexicographicMode=False,
    ):

        if error_indication:
            return {
                "status": "error",
                "error": str(error_indication),
            }

        if error_status:
            return {
                "status": "error",
                "error": error_status.prettyPrint(),
            }

        for oid_value, value in var_binds:
            # Arret des que le GETNEXT sort de la branche demandee.
            if not str(oid_value).startswith(root + "."):
                return {
                    "status": "success",
                    "host": ip,
                    "results": results,
                }

            results.append(
                {
                    "oid": str(oid_value),
                    "value": str(value),
                }
            )

        # Plafond de securite : evite de vider une branche large ou un agent
        # qui repondrait en boucle.
        if len(results) >= max_entries:
            return {
                "status": "success",
                "host": ip,
                "results": results,
                "truncated": True,
            }

    return {
        "status": "success",
        "host": ip,
        "results": results,
    }


def snmp_walk(ip: str, oid: str, port: int = 161) -> dict:
    """WALK SNMPv3 (authPriv, lecture seule). Les secrets viennent du .env."""
    refused = target_error(ip)
    if refused:
        return refused

    try:
        return asyncio.run(_snmp_walk(ip, oid, _security(), port))

    except SnmpConfigError as exc:
        return {"status": "error", "host": ip, "error": str(exc)}
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
        }


def get_interface_stats(ip: str, port: int = 161) -> dict:
    """Statistiques d'interfaces (branche ifTable) en SNMPv3."""
    return snmp_walk(ip, "1.3.6.1.2.1.2.2.1", port)
