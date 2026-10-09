"""Syslogs du labo en direct (NOC_SYSLOG_FILE) dans correlate_alarms."""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastmcp import Client

import guard
from server import mcp

_LIVE_LINE = "<38>Oct  9 08:16:12 r1 %AUTH-6-sshd: Failed password for noc from 172.20.20.1 port 60638 ssh2"
_BOGUS_LINE = "celle-ci ne matche pas le format du socle"


def test_correlate_integre_les_syslogs_du_labo(monkeypatch, tmp_path):
    monkeypatch.setattr(guard, "CONSENT_MODE", "dry_run")
    monkeypatch.setattr(guard, "AUDIT_LOG_PATH", tmp_path / "audit.log")

    logfile = tmp_path / "network_syslog.log"
    logfile.write_text(_LIVE_LINE + "\n" + _BOGUS_LINE + "\n", encoding="utf-8")
    monkeypatch.setenv("NOC_SYSLOG_FILE", str(logfile))

    async def scenario():
        async with Client(mcp) as client:
            return await client.call_tool("correlate_alarms", {})

    result = asyncio.run(scenario())
    data = result.structured_content

    assert data["live_syslog_events"] == 1
    live = [
        event
        for cluster in data["incident_candidates"]
        for event in cluster["events"]
        if event.get("source") == "labo"
    ]
    assert live, "l'evenement syslog du labo doit apparaitre dans un cluster"
    assert live[0]["device"] == "r1"
    assert "Failed password" in live[0]["message"]
    assert live[0]["timestamp"].startswith(f"{datetime.now().year}-10-09")


def test_sans_variable_pas_devenement_labo(monkeypatch, tmp_path):
    monkeypatch.setattr(guard, "CONSENT_MODE", "dry_run")
    monkeypatch.setattr(guard, "AUDIT_LOG_PATH", tmp_path / "audit.log")
    monkeypatch.delenv("NOC_SYSLOG_FILE", raising=False)

    async def scenario():
        async with Client(mcp) as client:
            return await client.call_tool("correlate_alarms", {})

    result = asyncio.run(scenario())
    assert result.structured_content["live_syslog_events"] == 0
