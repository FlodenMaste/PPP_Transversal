"""
Tests des primitives MCP du socle (cahier A.2) :
  - Prompts preconfigures consultables par l'hote ;
  - Completions automatiques (CompleteRequest) ;
  - Roots : lecture de runbook bornee aux racines declarees ;
  - Logging : notifications de niveau envoyees au client ;
  - Capability `completions` annoncee par le serveur.
"""

from __future__ import annotations

import asyncio
import logging

from fastmcp import Client
from mcp import types as mcp_types

from mcp_server.server import mcp


def _run(coro):
    return asyncio.run(coro)


async def _prompts():
    async with Client(mcp) as client:
        return await client.list_prompts()


def test_prompts_preconfigures():
    prompts = _run(_prompts())
    noms = {p.name for p in prompts}
    assert {"triage_incident", "collecte_diagnostic", "rapport_quotidien"} <= noms
    triage = next(p for p in prompts if p.name == "triage_incident")
    assert triage.arguments and triage.arguments[0].name == "equipement"


def test_prompt_genere_du_contenu():
    async def scenario():
        async with Client(mcp) as client:
            return await client.get_prompt("triage_incident", {"equipement": "r2"})

    result = _run(scenario())
    texte = result.messages[0].content.text
    assert "r2" in texte
    assert "untrusted" in texte


def test_completion_argument_de_prompt():
    async def scenario():
        async with Client(mcp) as client:
            return await client.complete(
                mcp_types.PromptReference(type="ref/prompt", name="triage_incident"),
                {"name": "equipement", "value": "r"},
            )

    completion = _run(scenario())
    assert "r1" in completion.values and "r2" in completion.values


def test_completion_argument_de_template_de_resource():
    async def scenario():
        async with Client(mcp) as client:
            return await client.complete(
                mcp_types.ResourceTemplateReference(
                    type="ref/resource", uri="mcp://socle/runbook/{name}"
                ),
                {"name": "name", "value": "b"},
            )

    completion = _run(scenario())
    assert completion.values == ["bgp_flap"]


def test_runbook_lisible_sans_racines_de_l_hote():
    async def scenario():
        async with Client(mcp) as client:
            return await client.read_resource("mcp://socle/runbook/bgp_flap")

    contenu = _run(scenario())[0].text
    assert "BGP" in contenu


def test_runbook_dans_les_racines_de_l_hote():
    racine = "file:///home/floden/PPP_Transversal"

    async def scenario():
        async with Client(mcp, roots=[racine]) as client:
            return await client.read_resource("mcp://socle/runbook/bgp_flap")

    contenu = _run(scenario())[0].text
    assert "BGP" in contenu


def test_runbook_hors_des_racines_refuse():
    """Une racine hors depot => la lecture du runbook est refusee."""

    async def scenario():
        async with Client(mcp, roots=["file:///tmp"]) as client:
            return await client.read_resource("mcp://socle/runbook/bgp_flap")

    try:
        _run(scenario())
    except Exception as exc:  # McpError enrobe la PermissionError serveur
        assert "racines" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("lecture hors racines non refusee")


def test_logging_notifications_recues_par_le_client(caplog):
    """La lecture de runbook emet une notification de niveau INFO (A.2)."""
    caplog.set_level(logging.INFO)

    async def scenario():
        async with Client(mcp) as client:
            return await client.read_resource("mcp://socle/runbook/bgp_flap")

    _run(scenario())

    assert any("runbook bgp_flap lu" in record.getMessage() for record in caplog.records)
