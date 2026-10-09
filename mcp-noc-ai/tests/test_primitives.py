"""
Tests des primitives MCP du serveur 3 (cahier A.2) :
  - Prompts preconfigures ;
  - Sampling : demande de completion au LLM de l'hote, avec repli propre
    quand l'hote ne supporte pas la primitive ;
  - Completions automatiques sur l'argument incident_id.
"""

from __future__ import annotations

import asyncio
import json

from fastmcp import Client
from mcp import types as mcp_types

import guard
from server import mcp


def _run(coro):
    return asyncio.run(coro)


def _incident_id():
    """Declenche la correlation puis renvoie un identifiant d'incident."""

    async def scenario():
        async with Client(mcp) as client:
            result = await client.call_tool("correlate_alarms", {})
            clusters = result.structured_content["incident_candidates"]
            return clusters[0]["incident_id"]

    return _run(scenario())


def test_prompts_preconfigures():
    async def scenario():
        async with Client(mcp) as client:
            return await client.list_prompts()

    noms = {p.name for p in _run(scenario())}
    assert {"qualifier_incident", "resume_journalier"} <= noms


def test_prompt_qualifier_incident_genere_du_contenu():
    async def scenario():
        async with Client(mcp) as client:
            return await client.get_prompt("qualifier_incident", {"incident_id": "INC-1"})

    result = _run(scenario())
    texte = result.messages[0].content.text
    assert "INC-1" in texte
    assert "formuler_hypothese" in texte


def test_completion_incident_id_connu(monkeypatch, tmp_path):
    monkeypatch.setattr(guard, "CONSENT_MODE", "dry_run")
    monkeypatch.setattr(guard, "AUDIT_LOG_PATH", tmp_path / "audit.log")
    incident_id = _incident_id()

    async def scenario():
        async with Client(mcp) as client:
            return await client.complete(
                mcp_types.PromptReference(type="ref/prompt", name="qualifier_incident"),
                {"name": "incident_id", "value": incident_id[:6]},
            )

    completion = _run(scenario())
    assert incident_id in completion.values


def test_sampling_hypothese_formulee_par_l_hote(monkeypatch, tmp_path):
    monkeypatch.setattr(guard, "CONSENT_MODE", "dry_run")
    monkeypatch.setattr(guard, "AUDIT_LOG_PATH", tmp_path / "audit.log")
    incident_id = _incident_id()

    async def sampling_handler(messages, params, context):
        assert "hypothese" in messages[0].content.text.lower()
        return "Hypothese de test : coupure du lien r1-r2."

    async def scenario():
        async with Client(mcp, sampling_handler=sampling_handler) as client:
            return await client.call_tool(
                "formuler_hypothese", {"incident_id": incident_id}
            )

    result = _run(scenario())
    assert result.structured_content["status"] == "ok"
    assert "coupure du lien" in result.structured_content["hypothese"]
    assert "certitude" in result.structured_content["note"]
    assert result.structured_content["untrusted"] is True


def test_sampling_sans_capacite_hote_repli_sur_les_preuves(monkeypatch, tmp_path):
    monkeypatch.setattr(guard, "CONSENT_MODE", "dry_run")
    monkeypatch.setattr(guard, "AUDIT_LOG_PATH", tmp_path / "audit.log")
    incident_id = _incident_id()

    async def scenario():
        async with Client(mcp) as client:  # aucun handler sampling
            return await client.call_tool(
                "formuler_hypothese", {"incident_id": incident_id}
            )

    result = _run(scenario())
    assert result.structured_content["status"] == "sampling_indisponible"
    assert "devices_involved" in json.dumps(result.structured_content["preuves"])


def test_formuler_hypothese_incident_inconnu(monkeypatch, tmp_path):
    monkeypatch.setattr(guard, "CONSENT_MODE", "dry_run")
    monkeypatch.setattr(guard, "AUDIT_LOG_PATH", tmp_path / "audit.log")

    async def scenario():
        async with Client(mcp) as client:
            return await client.call_tool(
                "formuler_hypothese", {"incident_id": "INC-0000"}
            )

    result = _run(scenario())
    assert "introuvable" in result.structured_content["error"]
