"""
Tests de la barriere A.6 du serveur 2 (guard.py + noc-mcp-server) :
  - consentement humain obligatoire avant chaque appel d'outil ;
  - fail-safe : refus si le client ne sait pas confirmer ;
  - journal d'audit alimente ;
  - sortie d'outil marquee non fiable (untrusted) ;
  - cibles bornees a l'inventaire (B.6).

Ces tests pilotent le serveur MCP en memoire (pas de transport) et ne
generent aucun trafic reseau : le mode par defaut des tests est dry_run
ou les cibles refusent avant toute execution.
"""

from __future__ import annotations

import asyncio
import json

from fastmcp import Client
from fastmcp.client.elicitation import ElicitResult

import guard
from server import mcp


def _run(coro):
    return asyncio.run(coro)


def _audit_lines(path):
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


async def _refuser(message, response_type, params, context):
    return ElicitResult(action="decline")


def test_consentement_elicitation_accepte(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "CONSENT_MODE", "elicitation")
    audit = tmp_path / "audit.log"
    monkeypatch.setattr(guard, "AUDIT_LOG_PATH", audit)
    demande = []

    async def handler(message, response_type, params, context):
        demande.append(message)
        return {"value": True}

    async def scenario():
        async with Client(mcp, elicitation_handler=handler) as client:
            return await client.call_tool(
                "get_device_status", {"name": "r1"}, raise_on_error=False
            )

    result = _run(scenario())

    assert result.is_error is not True
    assert result.structured_content["status"] == "found"
    assert result.structured_content["untrusted"] is True
    assert result.meta["untrusted"] is True
    assert len(demande) == 1
    assert "get_device_status" in demande[0]

    statuses = [entry["status"] for entry in _audit_lines(audit)]
    assert "EXECUTION_AUTORISEE" in statuses
    assert "EXECUTION_TERMINEE" in statuses


def test_consentement_elicitation_refuse(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "CONSENT_MODE", "elicitation")
    audit = tmp_path / "audit.log"
    monkeypatch.setattr(guard, "AUDIT_LOG_PATH", audit)

    async def scenario():
        async with Client(mcp, elicitation_handler=_refuser) as client:
            return await client.call_tool(
                "get_device_status", {"name": "r1"}, raise_on_error=False
            )

    result = _run(scenario())

    assert result.is_error is True
    assert "refuse" in json.dumps(result.structured_content).lower()
    statuses = [entry["status"] for entry in _audit_lines(audit)]
    assert "REFUSEE_HUMAIN" in statuses
    assert "EXECUTION_AUTORISEE" not in statuses


def test_fail_safe_client_sans_elicitation(tmp_path, monkeypatch):
    """Aucun canal de confirmation => rien n'est execute."""
    monkeypatch.setattr(guard, "CONSENT_MODE", "elicitation")
    audit = tmp_path / "audit.log"
    monkeypatch.setattr(guard, "AUDIT_LOG_PATH", audit)

    async def scenario():
        async with Client(mcp) as client:
            return await client.call_tool(
                "get_device_status", {"name": "r1"}, raise_on_error=False
            )

    result = _run(scenario())

    assert result.is_error is True
    statuses = [entry["status"] for entry in _audit_lines(audit)]
    assert "CONSENT_REFUSE" in statuses
    assert "EXECUTION_AUTORISEE" not in statuses


def test_mode_dry_run_reserve_aux_tests(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "CONSENT_MODE", "dry_run")
    audit = tmp_path / "audit.log"
    monkeypatch.setattr(guard, "AUDIT_LOG_PATH", audit)

    async def scenario():
        async with Client(mcp) as client:
            return await client.call_tool(
                "get_device_status", {"name": "r1"}, raise_on_error=False
            )

    result = _run(scenario())

    assert result.structured_content["status"] == "found"
    assert result.structured_content["untrusted"] is True
    statuses = [entry["status"] for entry in _audit_lines(audit)]
    assert "CONSENT_DRY_RUN" in statuses
    assert "EXECUTION_AUTORISEE" in statuses


def test_mode_deny_refuse_tout(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "CONSENT_MODE", "deny")
    audit = tmp_path / "audit.log"
    monkeypatch.setattr(guard, "AUDIT_LOG_PATH", audit)

    async def scenario():
        async with Client(mcp) as client:
            return await client.call_tool(
                "get_device_status", {"name": "r1"}, raise_on_error=False
            )

    result = _run(scenario())

    assert result.is_error is True
    statuses = [entry["status"] for entry in _audit_lines(audit)]
    assert "CONSENT_REFUSE" in statuses


def test_cible_hors_inventaire_refusee(tmp_path, monkeypatch):
    """B.6 : le serveur n'est pas un relais vers n'importe quelle adresse."""
    monkeypatch.setattr(guard, "CONSENT_MODE", "dry_run")
    audit = tmp_path / "audit.log"
    monkeypatch.setattr(guard, "AUDIT_LOG_PATH", audit)

    async def scenario():
        async with Client(mcp) as client:
            return await client.call_tool(
                "ping_host", {"ip": "8.8.8.8"}, raise_on_error=False
            )

    result = _run(scenario())

    assert "hors inventaire" in json.dumps(result.structured_content)
    assert result.structured_content["status"] == "error"


def test_secret_plus_jamais_argument_doutil(tmp_path, monkeypatch):
    """A.6 : aucun outil n'exige de secret en argument (snmp/netconf/ssh)."""
    async def scenario():
        tools = await mcp.list_tools()
        return {t.name: t.parameters for t in tools}

    schemas = _run(scenario())
    secrets = {"password", "community", "auth_key", "priv_key", "username"}
    for name, schema in schemas.items():
        props = set((schema or {}).get("properties", {}))
        interdits = props & secrets
        assert not interdits, f"{name} expose {interdits} en argument"
