#!/usr/bin/env bash
###############################################################################
# Installation du serveur MCP "noc-ai-diagnostics"
# Projet PPP - EC2LT - Groupe 3
#
# Ce script reprend, DANS L'ORDRE, toutes les commandes executees pour
# installer et tester le serveur MCP de diagnostic NOC sur une VM
# Ubuntu 26.04.1 LTS (Python 3.14 natif).
#
# Usage : a lire et executer etape par etape (ou "bash installer_serveur_mcp_noc.sh")
# Prerequis : VM Ubuntu 26.04 LTS, acces root ou sudo, connexion internet.
###############################################################################

set -e  # arrete le script au premier echec

echo ">>> ETAPE 0 - Verification de l'environnement"
python3 --version
apt update


echo ">>> ETAPE 1 - Installation des outils de base"
apt install -y python3-pip python3-venv git


echo ">>> ETAPE 2 - Creation de l'arborescence du projet"
mkdir -p ~/mcp-noc-ai/data
cd ~/mcp-noc-ai


echo ">>> ETAPE 3 - Creation et activation de l'environnement virtuel"
python3 -m venv venv
source venv/bin/activate
python3 --version   # doit afficher Python 3.14.x


echo ">>> ETAPE 4 - Creation des fichiers de donnees (data/)"

cat > data/topology.json << 'EOF'
{
  "nodes": ["R1", "R2", "R3", "SW1", "SW2"],
  "links": [
    {"source": "R1", "target": "R2", "type": "fiber"},
    {"source": "R2", "target": "R3", "type": "fiber"},
    {"source": "R1", "target": "SW1", "type": "ethernet"},
    {"source": "R2", "target": "SW2", "type": "ethernet"}
  ]
}
EOF

cat > data/inventory.json << 'EOF'
{
  "devices": [
    {"name": "R1", "role": "router", "vendor": "FRRouting", "mgmt_ip": "10.0.0.1"},
    {"name": "R2", "role": "router", "vendor": "FRRouting", "mgmt_ip": "10.0.0.2"},
    {"name": "R3", "role": "router", "vendor": "FRRouting", "mgmt_ip": "10.0.0.3"},
    {"name": "SW1", "role": "switch", "vendor": "SR Linux", "mgmt_ip": "10.0.0.11"},
    {"name": "SW2", "role": "switch", "vendor": "SR Linux", "mgmt_ip": "10.0.0.12"}
  ]
}
EOF

cat > data/runbooks.json << 'EOF'
{
  "runbooks": [
    {
      "id": "RB-BGP-FLAP",
      "title": "Instabilite de session BGP (flapping)",
      "tags": ["bgp", "flap", "session bgp", "voisin bgp"],
      "steps": [
        "1. Verifier l'etat de la session avec get_bgp_peers.",
        "2. Verifier la stabilite du lien physique sous-jacent (get_interface_stats).",
        "3. Verifier les timers BGP (hold-time / keepalive).",
        "4. Si la cause est un lien instable, escalader vers l'equipe transmission.",
        "5. Documenter l'incident avant toute action corrective."
      ]
    },
    {
      "id": "RB-LINK-DOWN",
      "title": "Coupure de lien",
      "tags": ["link down", "interface down", "coupure", "lien"],
      "steps": [
        "1. Confirmer la coupure via get_interface_stats sur les deux extremites.",
        "2. Verifier s'il existe un chemin de secours dans la topologie.",
        "3. Notifier l'equipe terrain si la coupure est physique.",
        "4. Suivre la procedure de bascule si un lien de secours existe.",
        "5. Documenter l'incident avant toute action corrective."
      ]
    }
  ]
}
EOF

cat > data/sample_syslog.json << 'EOF'
[
  {"timestamp": "2026-09-15T10:00:12", "device": "R1", "message": "%LINK-3-UPDOWN: Interface GigabitEthernet0/1, changed state to down"},
  {"timestamp": "2026-09-15T10:00:14", "device": "R2", "message": "%BGP-5-ADJCHANGE: neighbor 10.0.0.1 Down BGP Notification sent"},
  {"timestamp": "2026-09-15T10:00:20", "device": "SW1", "message": "%LINEPROTO-5-UPDOWN: Line protocol on Interface Vlan1, changed state to down"},
  {"timestamp": "2026-09-15T09:40:00", "device": "R3", "message": "%SYS-5-CONFIG_I: Configured from console by admin"}
]
EOF

cat > data/sample_alarms.json << 'EOF'
[
  {"timestamp": "2026-09-15T10:00:15", "device": "R1", "severity": "critical", "message": "Interface GigabitEthernet0/1 down"},
  {"timestamp": "2026-09-15T10:00:18", "device": "R2", "severity": "major", "message": "BGP peer 10.0.0.1 state changed to Idle"},
  {"timestamp": "2026-09-15T09:41:00", "device": "R3", "severity": "info", "message": "Configuration change detected"}
]
EOF

cat > data/simulated_metrics.json << 'EOF'
{
  "interfaces": {
    "R1": [
      {"name": "GigabitEthernet0/0", "peer": "R2", "status": "up", "in_octets": 1928374650, "out_octets": 1823746500, "in_errors": 0, "out_errors": 0},
      {"name": "GigabitEthernet0/1", "peer": "SW1", "status": "down", "in_octets": 293847, "out_octets": 281039, "in_errors": 42, "out_errors": 17, "last_change": "2026-09-15T10:00:12"}
    ],
    "R2": [
      {"name": "GigabitEthernet0/0", "peer": "R1", "status": "up", "in_octets": 1823746500, "out_octets": 1928374650, "in_errors": 0, "out_errors": 0},
      {"name": "GigabitEthernet0/1", "peer": "R3", "status": "up", "in_octets": 2384756102, "out_octets": 2298374610, "in_errors": 0, "out_errors": 0},
      {"name": "GigabitEthernet0/2", "peer": "SW2", "status": "up", "in_octets": 938475610, "out_octets": 902837465, "in_errors": 0, "out_errors": 0}
    ],
    "R3": [
      {"name": "GigabitEthernet0/0", "peer": "R2", "status": "up", "in_octets": 2298374610, "out_octets": 2384756102, "in_errors": 0, "out_errors": 0}
    ],
    "SW1": [
      {"name": "eth0/1", "peer": "R1", "status": "down", "in_octets": 281039, "out_octets": 293847, "in_errors": 12, "out_errors": 8, "last_change": "2026-09-15T10:00:20"}
    ],
    "SW2": [
      {"name": "eth0/1", "peer": "R2", "status": "up", "in_octets": 902837465, "out_octets": 938475610, "in_errors": 0, "out_errors": 0}
    ]
  },
  "bgp_peers": {
    "R1": [
      {"neighbor_ip": "10.0.0.2", "neighbor_device": "R2", "remote_as": 65002, "state": "Established", "uptime": "05:12:03"}
    ],
    "R2": [
      {"neighbor_ip": "10.0.0.1", "neighbor_device": "R1", "remote_as": 65001, "state": "Idle", "uptime": "00:00:00", "last_event": "2026-09-15T10:00:14"},
      {"neighbor_ip": "10.0.0.3", "neighbor_device": "R3", "remote_as": 65003, "state": "Established", "uptime": "05:12:03"}
    ],
    "R3": [
      {"neighbor_ip": "10.0.0.2", "neighbor_device": "R2", "remote_as": 65002, "state": "Established", "uptime": "05:12:03"}
    ]
  },
  "ospf_neighbors": {
    "R1": [
      {"neighbor_id": "2.2.2.2", "neighbor_device": "R2", "state": "FULL", "interface": "GigabitEthernet0/0"}
    ],
    "R2": [
      {"neighbor_id": "1.1.1.1", "neighbor_device": "R1", "state": "FULL", "interface": "GigabitEthernet0/0"},
      {"neighbor_id": "3.3.3.3", "neighbor_device": "R3", "state": "FULL", "interface": "GigabitEthernet0/1"}
    ],
    "R3": [
      {"neighbor_id": "2.2.2.2", "neighbor_device": "R2", "state": "FULL", "interface": "GigabitEthernet0/0"}
    ]
  },
  "qos_stats": {
    "R1": [
      {"interface": "GigabitEthernet0/0", "drop_rate_pct": 0.01, "avg_latency_ms": 2.3, "jitter_ms": 0.4}
    ],
    "R2": [
      {"interface": "GigabitEthernet0/1", "drop_rate_pct": 0.02, "avg_latency_ms": 3.1, "jitter_ms": 0.6}
    ]
  }
}
EOF

echo "Fichiers data/ crees."


echo ">>> ETAPE 5 - Installation de FastMCP"

cat > requirements.txt << 'EOF'
fastmcp>=3.0.0
EOF

pip install --upgrade pip
pip install -r requirements.txt
pip show fastmcp


echo ">>> ETAPE 6 - Creation du serveur MCP (server.py)"

cat > server.py << 'EOF'
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
    """
    syslogs = _load_json("sample_syslog.json")
    alarms = _load_json("sample_alarms.json")
    topology = _load_json("topology.json")

    ref = datetime.fromisoformat(reference_time) if reference_time else datetime.now()

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
    Interprete des anomalies pre-calculees (erreurs d'interface, sessions
    BGP down, alarmes critiques) sans effectuer de calcul statistique
    elle-meme : le calcul est fait en amont, cet outil qualifie et
    priorise les alertes existantes.
    """
    metrics = _load_json("simulated_metrics.json")
    alarms = _load_json("sample_alarms.json")
    ref = datetime.fromisoformat(reference_time) if reference_time else datetime.now()

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
EOF

echo "server.py cree."


echo ">>> ETAPE 7 - Verification et premier lancement du serveur"
python3 -m py_compile server.py && echo "server.py OK, pas d'erreur de syntaxe"
# python3 server.py    # (decommenter pour lancer le serveur ; Ctrl+C pour l'arreter)


echo ">>> ETAPE 8 - Installation de Node.js (necessaire pour MCP Inspector)"
curl -fsSL https://deb.nodesource.com/setup_lts.x | bash -
apt install -y nodejs
node --version


echo ">>> ETAPE 9 - Lancement de MCP Inspector pour tester le serveur"
echo "Commande a executer manuellement (interface web interactive) :"
echo "    npx @modelcontextprotocol/inspector python3 server.py"
echo ""
echo "Ouvrir ensuite l'URL affichee (http://127.0.0.1:6274?MCP_INSPECTOR_API_TOKEN=...)"
echo "dans un navigateur de la VM, activer la connexion au serveur 'python3',"
echo "puis tester les Resources et les Tools depuis les onglets correspondants."

echo ""
echo ">>> INSTALLATION TERMINEE"
echo "Pour relancer le serveur plus tard :"
echo "    cd ~/mcp-noc-ai && source venv/bin/activate && python3 server.py"
