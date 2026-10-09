"""
Serveur MCP - Outils de diagnostic IA pour le NOC
Groupe 3 - EC2LT - PPP MCP Telecom Supervision
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastmcp import FastMCP

DATA_DIR = Path(__file__).parent / "data"
mcp = FastMCP("noc-ai-diagnostics")


def _load_json(filename: str):
    path = DATA_DIR / filename
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


_INCIDENTS: dict[str, dict] = {}


@mcp.resource("noc://topology")
def get_topology() -> dict:
    """Topologie du reseau (noeuds + liens) au format JSON."""
    return _load_json("topology.json")


@mcp.resource("noc://inventory")
def get_inventory() -> dict:
    """Inventaire des equipements du reseau."""
    return _load_json("inventory.json")


@mcp.resource("noc://runbooks")
def get_runbooks() -> dict:
    """Procedures officielles de resolution d'incidents (runbooks)."""
    return _load_json("runbooks.json")


def _within_window(ts: str, ref: datetime, minutes: int) -> bool:
    event_time = datetime.fromisoformat(ts)
    return abs((event_time - ref).total_seconds()) <= minutes * 60


def _default_reference(*datasets: list[dict]) -> datetime:
    """Sans reference_time, centre la fenetre sur le dernier evenement present
    dans les donnees du labo (sinon les fichiers statiques sortiraient
    immediatement de la fenetre glissante)."""
    stamps = [
        datetime.fromisoformat(event["timestamp"])
        for dataset in datasets
        for event in dataset
    ]
    return max(stamps) if stamps else datetime.now()


def _neighbors_of(device: str, topology: dict) -> set:
    neighbors = set()
    for link in topology.get("links", []):
        if link["source"] == device:
            neighbors.add(link["target"])
        elif link["target"] == device:
            neighbors.add(link["source"])
    return neighbors


@mcp.tool()
def correlate_alarms(time_window_minutes: int = 15, reference_time: Optional[str] = None) -> dict:
    """
    Regroupe les Syslogs et les alarmes SNMP survenus dans une fenetre de temps
    donnee en incidents candidats, en se basant sur la proximite topologique.
    Sans reference_time, la fenetre est centree sur le dernier evenement des donnees.
    """
    syslogs = _load_json("sample_syslog.json")
    alarms = _load_json("sample_alarms.json")
    topology = _load_json("topology.json")

    ref = datetime.fromisoformat(reference_time) if reference_time else _default_reference(syslogs, alarms)

    events = []
    for s in syslogs:
        events.append({"type": "syslog", **s})
    for a in alarms:
        events.append({"type": "alarm", **a})

    events = [e for e in events if _within_window(e["timestamp"], ref, time_window_minutes)]

    clusters: list = []
    used = set()
    for i, e in enumerate(events):
        if i in used:
            continue
        device = e["device"]
        group = [e]
        used.add(i)
        related_devices = {device} | _neighbors_of(device, topology)
        for j, other in enumerate(events):
            if j in used or j == i:
                continue
            if other["device"] in related_devices:
                group.append(other)
                used.add(j)
        devices_involved = sorted({g["device"] for g in group})
        clusters.append({
            "incident_id": f"INC-{uuid.uuid4().hex[:8]}",
            "devices_involved": devices_involved,
            "event_count": len(group),
            "events": group,
        })

    for c in clusters:
        _INCIDENTS[c["incident_id"]] = c

    return {
        "reference_time": ref.isoformat(),
        "time_window_minutes": time_window_minutes,
        "incident_candidates": clusters,
        "note": "Regroupement deterministe (temps + topologie). Qualifie chaque incident avant de le traiter comme reel.",
    }


@mcp.tool()
def analyze_root_cause(incident_id: str) -> dict:
    """
    Rassemble les preuves techniques pour un incident (topologie locale,
    inventaire, evenements bruts). Ne formule aucune hypothese elle-meme.
    """
    incident = _INCIDENTS.get(incident_id)
    if incident is None:
        return {"error": f"incident {incident_id} introuvable. Appelle d'abord correlate_alarms."}

    topology = _load_json("topology.json")
    inventory = _load_json("inventory.json")

    devices = incident["devices_involved"]
    local_links = [
        link for link in topology.get("links", [])
        if link["source"] in devices or link["target"] in devices
    ]
    device_inventory = [d for d in inventory.get("devices", []) if d["name"] in devices]

    return {
        "incident_id": incident_id,
        "devices_involved": devices,
        "events": incident["events"],
        "local_topology": {"nodes": devices, "links": local_links},
        "device_inventory": device_inventory,
        "instructions_for_llm": (
            "A partir de ces preuves UNIQUEMENT, propose une hypothese de cause racine. "
            "Structure : symptome observe -> equipements impliques -> cause probable -> "
            "preuve exacte citee. Si insuffisant, dis-le plutot que de speculer."
        ),
    }


@mcp.tool()
def generate_incident_report(incident_id: str, root_cause_summary: str) -> dict:
    """
    Cherche le runbook pertinent et assemble un rapport structure, en
    attente de validation humaine.
    """
    incident = _INCIDENTS.get(incident_id)
    if incident is None:
        return {"error": f"incident {incident_id} introuvable."}

    runbooks = _load_json("runbooks.json").get("runbooks", [])
    root_cause_lower = root_cause_summary.lower()

    matched_runbook = None
    for rb in runbooks:
        if any(tag.lower() in root_cause_lower for tag in rb.get("tags", [])):
            matched_runbook = rb
            break

    chronologie = sorted(incident["events"], key=lambda e: e["timestamp"])

    return {
        "incident_id": incident_id,
        "generated_at": datetime.now().isoformat(),
        "summary": f"Incident impliquant {', '.join(incident['devices_involved'])}.",
        "chronology": [
            {"timestamp": e["timestamp"], "device": e["device"], "message": e.get("message", "")}
            for e in chronologie
        ],
        "root_cause": root_cause_summary,
        "matched_runbook": matched_runbook if matched_runbook else "Aucun runbook correspondant trouve.",
        "recommended_action": (
            matched_runbook["steps"] if matched_runbook else
            "Aucune action automatique : remonter a un ingenieur NOC."
        ),
        "validation_status": "EN_ATTENTE_DE_VALIDATION_HUMAINE",
    }


@mcp.tool()
def get_interface_stats(device: str) -> dict:
    """
    Retourne les statistiques des interfaces d'un equipement (etat,
    compteurs, erreurs). Lecture seule, aucune modification possible.
    """
    metrics = _load_json("simulated_metrics.json")
    interfaces = metrics.get("interfaces", {}).get(device)
    if interfaces is None:
        return {"error": f"equipement '{device}' introuvable dans les metriques."}
    return {"device": device, "interfaces": interfaces}


@mcp.tool()
def get_bgp_peers(device: str) -> dict:
    """
    Retourne l'etat des sessions BGP (voisins, AS distant, etat,
    uptime) d'un equipement donne. Lecture seule.
    """
    metrics = _load_json("simulated_metrics.json")
    peers = metrics.get("bgp_peers", {}).get(device)
    if peers is None:
        return {"error": f"equipement '{device}' introuvable ou pas de session BGP."}
    return {"device": device, "bgp_peers": peers}


@mcp.tool()
def get_ospf_neighbors(device: str) -> dict:
    """
    Retourne le voisinage OSPF (neighbor ID, etat, interface) d'un
    equipement donne. Lecture seule.
    """
    metrics = _load_json("simulated_metrics.json")
    neighbors = metrics.get("ospf_neighbors", {}).get(device)
    if neighbors is None:
        return {"error": f"equipement '{device}' introuvable ou pas de voisinage OSPF."}
    return {"device": device, "ospf_neighbors": neighbors}


@mcp.tool()
def ping_host(device: str, target: str) -> dict:
    """
    Simule un test de connectivite (ping) depuis un equipement vers
    une cible. Se base sur l'etat des interfaces pour determiner le
    resultat. Lecture seule, aucune configuration modifiee.
    """
    metrics = _load_json("simulated_metrics.json")
    interfaces = metrics.get("interfaces", {}).get(device, [])
    for iface in interfaces:
        if iface.get("peer") == target:
            reachable = iface.get("status") == "up"
            return {
                "source": device,
                "target": target,
                "reachable": reachable,
                "packet_loss_pct": 0 if reachable else 100,
                "avg_rtt_ms": 1.2 if reachable else None,
            }
    return {
        "source": device,
        "target": target,
        "reachable": False,
        "note": "Aucun lien direct connu vers cette cible dans la topologie simulee.",
    }


@mcp.tool()
def qos_stats(device: str) -> dict:
    """
    Retourne les statistiques de qualite de service (taux de perte,
    latence, gigue) des interfaces d'un equipement. Lecture seule.
    """
    metrics = _load_json("simulated_metrics.json")
    stats = metrics.get("qos_stats", {}).get(device)
    if stats is None:
        return {"error": f"pas de statistiques QoS disponibles pour '{device}'."}
    return {"device": device, "qos_stats": stats}


@mcp.tool()
def detect_anomalies(time_window_minutes: int = 15, reference_time: Optional[str] = None) -> dict:
    """
    Interprete des anomalies     pre-calculees (erreurs d'interface, sessions
    BGP down, alarmes critiques) sans effectuer de calcul statistique
    elle-meme : le calcul est fait en amont, cet outil qualifie et
    priorise les alertes existantes.
    Sans reference_time, la fenetre est centree sur la derniere alarme disponible.
    """
    metrics = _load_json("simulated_metrics.json")
    alarms = _load_json("sample_alarms.json")
    ref = datetime.fromisoformat(reference_time) if reference_time else _default_reference(alarms)


    anomalies = []

    for device, interfaces in metrics.get("interfaces", {}).items():
        for iface in interfaces:
            if iface.get("status") == "down" or iface.get("in_errors", 0) > 10:
                anomalies.append({
                    "device": device,
                    "type": "interface",
                    "detail": iface,
                    "severity": "critical" if iface.get("status") == "down" else "warning",
                })

    for device, peers in metrics.get("bgp_peers", {}).items():
        for peer in peers:
            if peer.get("state") != "Established":
                anomalies.append({
                    "device": device,
                    "type": "bgp",
                    "detail": peer,
                    "severity": "critical",
                })

    recent_alarms = [a for a in alarms if _within_window(a["timestamp"], ref, time_window_minutes)]

    return {
        "reference_time": ref.isoformat(),
        "time_window_minutes": time_window_minutes,
        "anomalies_detected": anomalies,
        "recent_alarms_in_window": recent_alarms,
        "note": "Anomalies pre-qualifiees a partir de seuils deterministes (etat down, erreurs, sessions non etablies). Aucune inference statistique n'est effectuee par le modele.",
    }


if __name__ == "__main__":
    mcp.run()
