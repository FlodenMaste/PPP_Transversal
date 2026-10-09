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


def _security(
    username: str = "",
    auth_key: str = "",
    priv_key: str = "",
    community: str = "public",
):
    """Retourne le mode de securite SNMP.

    SNMPv3 authPriv si un utilisateur est fourni (argument ou .env),
    sinon SNMPv2c avec la community fournie.
    """
    username = username or os.environ.get("SNMPV3_USER", "")

    if not username:
        from pysnmp.hlapi.v3arch.asyncio import CommunityData

        return CommunityData(community or os.environ.get("SNMP_COMMUNITY", "public"), mpModel=1)

    from pysnmp.hlapi.v3arch.asyncio import (
        UsmUserData,
        usmAesCfb128Protocol,
        usmAesCfb256Protocol,
        usmHMAC192SHA256AuthProtocol,
        usmHMACSHAAuthProtocol,
    )

    auth_key = auth_key or os.environ.get("SNMPV3_AUTH_KEY", "")
    priv_key = priv_key or os.environ.get("SNMPV3_PRIV_KEY", "")

    auth_protocol = {
        "SHA": usmHMACSHAAuthProtocol,
        "SHA256": usmHMAC192SHA256AuthProtocol,
    }.get(os.environ.get("SNMPV3_AUTH_PROTOCOL", "SHA"), usmHMACSHAAuthProtocol)

    priv_protocol = {
        "AES": usmAesCfb128Protocol,
        "AES256": usmAesCfb256Protocol,
    }.get(os.environ.get("SNMPV3_PRIV_PROTOCOL", "AES"), usmAesCfb128Protocol)

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


def snmp_get(
    ip: str,
    oid: str,
    community: str = "public",
    username: str = "",
    auth_key: str = "",
    priv_key: str = "",
    port: int = 161,
) -> dict:

    try:
        return asyncio.run(
            _snmp_get(ip, oid, _security(username, auth_key, priv_key, community), port)
        )

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


def snmp_walk(
    ip: str,
    oid: str,
    community: str = "public",
    username: str = "",
    auth_key: str = "",
    priv_key: str = "",
    port: int = 161,
) -> dict:

    try:
        return asyncio.run(
            _snmp_walk(ip, oid, _security(username, auth_key, priv_key, community), port)
        )

    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
        }


def get_interface_stats(
    ip: str,
    community: str = "public",
    username: str = "",
    auth_key: str = "",
    priv_key: str = "",
    port: int = 161,
) -> dict:

    return snmp_walk(
        ip,
        "1.3.6.1.2.1.2.2.1",
        community,
        username,
        auth_key,
        priv_key,
        port,
    )
