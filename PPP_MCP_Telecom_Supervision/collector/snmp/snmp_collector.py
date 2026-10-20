"""
Collecteur SNMP - outils MCP cibles : snmp_get, snmp_walk, get_interface_stats.

En lecture seule uniquement (GET/WALK), jamais de SET. Utilise
pysnmp en mode réel ; en mode simulé, lit des fixtures JSON.

Mode réel : SNMPv3 niveau authPriv uniquement (authentification +
chiffrement), avec un compte lecture seule. SNMPv1/v2c (community) n'est
volontairement pas supporté. Les identifiants viennent de
l'environnement (voir config.get_snmpv3_credentials) ; s'ils manquent,
aucune requête n'est envoyée.

Pré-requis pour le mode réel :
    pip install pysnmp

pysnmp >= 6 expose uniquement l'API asyncio (pysnmp.hlapi.v3arch.asyncio) :
les fonctions réelles sont donc async et exécutées via _run_async(), qui
retombe sur asyncio.run() hors d'une boucle d'événements.
"""

import asyncio
import re
from typing import Any

from collector import config
from collector.common.schema import make_error_response, make_response
from collector.common.utils import (
    fixtures_dir,
    load_json_fixture,
    logger,
    resolve_device_key,
    sanitize_untrusted_text,
    unknown_device_message,
)

FIXTURES = fixtures_dir(__file__)

_OID_RE = re.compile(r"^\d+(\.\d+){0,127}$")
_AUTH_PROTOCOLS = ("SHA", "SHA256")
_PRIV_PROTOCOLS = ("AES", "AES256")


def _run_async(coro):
    """Exécute une coroutine synchrone.

    asyncio.run() échoue si on est déjà dans une boucle d'événements (le
    serveur MCP appelle les collecteurs depuis sa propre boucle) : dans ce
    cas, la coroutine part dans un thread dédié avec sa propre boucle.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _validate_oid(oid: str) -> str:
    """Accepte uniquement un OID numérique pointé (ex: 1.3.6.1.2.1.1.1.0)."""
    if not isinstance(oid, str) or not _OID_RE.match(oid.strip(".")):
        raise ValueError("OID invalide : attendu un OID numérique pointé (ex: 1.3.6.1.2.1.1.1.0)")
    return oid.strip(".")


def _build_usm_user():
    """Construit l'utilisateur SNMPv3 authPriv (SHA/SHA256 + AES/AES256).

    Les identifiants sont lus AVANT d'importer pysnmp : s'ils manquent,
    ConfigError est levée sans qu'aucune requête ne parte.
    """
    credentials = config.get_snmpv3_credentials()
    if config.SNMPV3_AUTH_PROTOCOL not in _AUTH_PROTOCOLS:
        raise config.ConfigError(f"SNMPV3_AUTH_PROTOCOL doit valoir l'une des valeurs : {_AUTH_PROTOCOLS}")
    if config.SNMPV3_PRIV_PROTOCOL not in _PRIV_PROTOCOLS:
        raise config.ConfigError(f"SNMPV3_PRIV_PROTOCOL doit valoir l'une des valeurs : {_PRIV_PROTOCOLS}")

    from pysnmp.hlapi.v3arch.asyncio import (
        UsmUserData,
        usmAesCfb128Protocol,
        usmAesCfb256Protocol,
        usmHMAC192SHA256AuthProtocol,
        usmHMACSHAAuthProtocol,
    )

    auth_protocol = {"SHA": usmHMACSHAAuthProtocol, "SHA256": usmHMAC192SHA256AuthProtocol}[
        config.SNMPV3_AUTH_PROTOCOL
    ]
    priv_protocol = {"AES": usmAesCfb128Protocol, "AES256": usmAesCfb256Protocol}[config.SNMPV3_PRIV_PROTOCOL]
    return UsmUserData(
        credentials["user"],
        authKey=credentials["auth_key"],
        privKey=credentials["priv_key"],
        authProtocol=auth_protocol,
        privProtocol=priv_protocol,
    )


async def _transport(device_ip: str):
    from pysnmp.hlapi.v3arch.asyncio import UdpTransportTarget

    return await UdpTransportTarget.create(
        (device_ip, config.SNMP_PORT),
        timeout=config.SNMP_TIMEOUT,
        retries=config.SNMP_RETRIES,
    )


async def _real_snmp_get(device_ip: str, oid: str) -> str:
    """Exécute un GET SNMPv3 (authPriv) réel via pysnmp (asyncio)."""
    usm_user = _build_usm_user()  # ConfigError si identifiants absents

    from pysnmp.hlapi.v3arch.asyncio import (
        ContextData,
        ObjectIdentity,
        ObjectType,
        SnmpEngine,
        get_cmd,
    )

    error_indication, error_status, error_index, var_binds = await get_cmd(
        SnmpEngine(),
        usm_user,
        await _transport(device_ip),
        ContextData(),
        ObjectType(ObjectIdentity(oid)),
    )

    if error_indication:
        raise RuntimeError(str(error_indication))
    if error_status:
        raise RuntimeError(f"{error_status.prettyPrint()} at {error_index}")

    name, value = var_binds[0]
    return str(value)


async def _real_snmp_walk(device_ip: str, oid: str) -> dict[str, str]:
    """Exécute un WALK SNMPv3 (authPriv) réel via pysnmp (asyncio).

    Le nombre d'entrées est plafonné à SNMP_WALK_MAX_ENTRIES pour ne pas
    saturer la mémoire sur une branche large ou un agent défaillant.
    """
    usm_user = _build_usm_user()

    from pysnmp.hlapi.v3arch.asyncio import (
        ContextData,
        ObjectIdentity,
        ObjectType,
        SnmpEngine,
        walk_cmd,
    )

    results: dict[str, str] = {}
    root = oid.strip(".")
    async for error_indication, error_status, error_index, var_binds in walk_cmd(
        SnmpEngine(),
        usm_user,
        await _transport(device_ip),
        ContextData(),
        ObjectType(ObjectIdentity(oid)),
    ):
        if error_indication:
            raise RuntimeError(str(error_indication))
        if error_status:
            raise RuntimeError(f"{error_status.prettyPrint()} at {error_index}")
        for name, value in var_binds:
            # Arret des que le GETNEXT sort de la branche demandee :
            # sans ce controle, le walk continuerait dans les branches voisines.
            if not str(name).startswith(root + "."):
                return results
            results[str(name)] = str(value)
            if len(results) >= config.SNMP_WALK_MAX_ENTRIES:
                logger.warning(
                    "snmp_walk sur %s plafonné à %d entrées (SNMP_WALK_MAX_ENTRIES)",
                    device_ip,
                    config.SNMP_WALK_MAX_ENTRIES,
                )
                return results
    return results


def snmp_get(device_ip: str, oid: str, mode: str | None = None) -> dict[str, Any]:
    """Récupère la valeur d'un OID unique sur un équipement.

    En mode simulé, cherche l'OID dans snmp_walk_system.json.
    """
    simulated = config.is_simulated(mode)
    try:
        if simulated:
            table = load_json_fixture(FIXTURES / "snmp_walk_system.json")
            device_data = table.get(resolve_device_key(device_ip), {})
            if oid not in device_data:
                return make_error_response("snmp", device_ip, f"OID {oid} introuvable dans les fixtures", simulated=True)
            return make_response("snmp", device_ip, {"oid": oid, "value": device_data[oid]}, simulated=True)

        value = _run_async(_real_snmp_get(device_ip, oid))
        return make_response("snmp", device_ip, {"oid": oid, "value": value}, simulated=False)

    except Exception as exc:  # noqa: BLE001 - on isole toute erreur réseau/protocole
        logger.error("snmp_get failed for %s / %s: %s", device_ip, oid, exc)
        return make_error_response("snmp", device_ip, str(exc), simulated=simulated)


def snmp_walk(device_ip: str, oid: str, mode: str | None = None) -> dict[str, Any]:
    """Parcourt une branche SNMP à partir d'un OID racine."""
    simulated = config.is_simulated(mode)
    try:
        if simulated:
            table = load_json_fixture(FIXTURES / "snmp_walk_system.json")
            device_data = table.get(resolve_device_key(device_ip), {})
            return make_response("snmp", device_ip, {"root_oid": oid, "entries": device_data}, simulated=True)

        entries = _run_async(_real_snmp_walk(device_ip, oid))
        return make_response("snmp", device_ip, {"root_oid": oid, "entries": entries}, simulated=False)

    except Exception as exc:  # noqa: BLE001
        logger.error("snmp_walk failed for %s / %s: %s", device_ip, oid, exc)
        return make_error_response("snmp", device_ip, str(exc), simulated=simulated)


def get_interface_stats(device_ip: str, interface: str | None = None, mode: str | None = None) -> dict[str, Any]:
    """Récupère les statistiques d'interface(s) d'un équipement.

    Outil MCP cible : get_interface_stats. Si `interface` est
    fourni, ne retourne que cette interface ; sinon, toutes les
    interfaces connues.
    """
    simulated = config.is_simulated(mode)
    try:
        if simulated:
            table = load_json_fixture(FIXTURES / "interface_stats.json")
            device_data = table.get(resolve_device_key(device_ip))
            if device_data is None:
                return make_error_response(
                    "snmp", device_ip,
                    unknown_device_message(device_ip, "d'interfaces (SNMP)"),
                    simulated=True,
                )
            if interface:
                if interface not in device_data:
                    return make_error_response("snmp", device_ip, f"Interface {interface} introuvable", simulated=True)
                return make_response("snmp", device_ip, {interface: device_data[interface]}, simulated=True)
            return make_response("snmp", device_ip, device_data, simulated=True)

        # Mode réel : combine plusieurs OIDs de la table ifTable (walk ciblé)
        entries = _run_async(_real_snmp_walk(device_ip, "1.3.6.1.2.1.2.2.1"))
        return make_response("snmp", device_ip, {"raw_iftable": entries}, simulated=False)

    except Exception as exc:  # noqa: BLE001
        logger.error("get_interface_stats failed for %s: %s", device_ip, exc)
        return make_error_response("snmp", device_ip, str(exc), simulated=simulated)