"""
Tests de la barriere A.6 du serveur 3 (guard.py + mcp-noc-ai) :
  - consentement humain obligatoire avant chaque appel d'outil ;
  - fail-safe : refus si le client ne sait pas confirmer ;
  - journal d'audit alimente ;
  - sortie d'outil marquee non fiable (untrusted).

Ces tests pilotent le serveur MCP en memoire (pas de transport) : les
outils appeles agissent sur les donnees statiques du laboratoire.
"""

from __future__ import annotations

import asyncio
import json

from fastmcp import Client
from fastmcp.client.elicitation import ElicitResult

import guard
from server import mcp

TOOL = "correlate_alarms"


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
            return await client.call_tool(TOOL, {}, raise_on_error=False)

    result = _run(scenario())

    assert result.is_error is not True
    assert result.structured_content["untrusted"] is True
    assert result.meta["untrusted"] is True
    assert len(demande) == 1
    assert TOOL in demande[0]

    statuses = [entry["status"] for entry in _audit_lines(audit)]
    assert "EXECUTION_AUTORISEE" in statuses
    assert "EXECUTION_TERMINEE" in statuses


def test_consentement_elicitation_refuse(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "CONSENT_MODE", "elicitation")
    audit = tmp_path / "audit.log"
    monkeypatch.setattr(guard, "AUDIT_LOG_PATH", audit)

    async def scenario():
        async with Client(mcp, elicitation_handler=_refuser) as client:
            return await client.call_tool(TOOL, {}, raise_on_error=False)

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
            return await client.call_tool(TOOL, {}, raise_on_error=False)

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
            return await client.call_tool(TOOL, {}, raise_on_error=False)

    result = _run(scenario())

    assert result.is_error is not True
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
            return await client.call_tool(TOOL, {}, raise_on_error=False)

    result = _run(scenario())

    assert result.is_error is True
    statuses = [entry["status"] for entry in _audit_lines(audit)]
    assert "CONSENT_REFUSE" in statuses


def test_audit_une_execution_par_appel(tmp_path, monkeypatch):
    """Chaque execution laisse exactement une trace AUTORISEE + TERMINEE."""
    monkeypatch.setattr(guard, "CONSENT_MODE", "dry_run")
    audit = tmp_path / "audit.log"
    monkeypatch.setattr(guard, "AUDIT_LOG_PATH", audit)

    async def scenario():
        async with Client(mcp) as client:
            await client.call_tool(TOOL, {})
            await client.call_tool("detect_anomalies", {})

    _run(scenario())

    entrees = _audit_lines(audit)
    autorisees = [e for e in entrees if e["status"] == "EXECUTION_AUTORISEE"]
    terminees = [e for e in entrees if e["status"] == "EXECUTION_TERMINEE"]
    assert len(autorisees) == 2
    assert len(terminees) == 2
