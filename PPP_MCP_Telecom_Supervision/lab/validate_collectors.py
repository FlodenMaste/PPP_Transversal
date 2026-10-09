#!/usr/bin/env python3
"""
Validation des collecteurs CONTRE LE LABO REEL (mode COLLECTOR_MODE=real).

A lancer depuis la racine du depot, le labo Containerlab etant deploye et les
services d'acquisition de l'hote demarres (relais syslog udp/1514 + nfcapd
udp/9995) :

    docker build -t mcp-noc-frr:local lab/containerlab
    docker build -t mcp-noc-term:local -f lab/containerlab/Dockerfile.term lab/containerlab
    cd lab/containerlab && sudo containerlab deploy -t topology.clab.yml && cd ../..
    sudo scripts/lab_services.sh            # relais syslog + nfcapd
    ./venv/bin/python lab/validate_collectors.py

Chaque collecteur est appele une fois en mode "real" ; le script affiche le
statut, la source et un extrait de donnees. Les collecteurs qui dependent de
binaires systeme absents (tshark) ou d'un service non expose par le labo
FRR (NETCONF) sont signales comme NON DISPONIBLE - c'est attendu, pas une
regression.

Cibles (IPs de management statiques, cf. lab/containerlab/topology.clab.yml) :
    r1 = 172.20.20.11   r2 = 172.20.20.12   r3 = 172.20.20.13
"""

import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from collector import config  # noqa: E402

R1, R2, R3 = "172.20.20.11", "172.20.20.12", "172.20.20.13"


def _brief(response: dict, max_len: int = 220) -> str:
    if response["status"] == "ok":
        try:
            data = json.dumps(response["data"], ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            data = str(response["data"])
    else:
        data = str(response["error"])
    return data[:max_len] + ("..." if len(data) > max_len else "")


def run(label: str, func, *args, **kwargs) -> bool:
    """Appelle un collecteur en mode reel et affiche le resultat."""
    try:
        response = func(*args, mode="real", **kwargs)
    except Exception as exc:  # noqa: BLE001 - un collecteur ne doit pas planter le script
        print(f"[ECHEC]   {label:<28} exception : {type(exc).__name__}: {exc}")
        return False

    ok = response["status"] == "ok"
    tag = "[OK]     " if ok else "[ERREUR] "
    simulated = " (SIMULE !)" if response["simulated"] else ""
    print(f"{tag} {label:<28}{simulated}")
    print(f"          source={response['source']} device={response['device']}")
    print(f"          {_brief(response)}")
    return ok


def main() -> int:
    print("=" * 78)
    print(f"  Mode COLLECTOR_MODE = {config.COLLECTOR_MODE}")
    print("  Cibles du labo : " + f"r1={R1} r2={R2} r3={R3}")
    print("=" * 78)

    from collector.cli.cli_collector import get_bgp_peers, get_ospf_neighbors
    from collector.netconf.netconf_collector import netconf_get
    from collector.netflow.netflow_collector import analyze_netflow
    from collector.ping.ping_collector import ping_host, traceroute
    from collector.snmp.snmp_collector import get_interface_stats, snmp_get, snmp_walk
    from collector.syslog.syslog_collector import get_recent_syslog

    results: list[tuple[str, bool]] = []

    print("\n--- SNMP (SNMPv3 authPriv, lecture seule) ---")
    results.append(("snmp_get sysDescr r1", run("snmp_get r1", snmp_get, R1, "1.3.6.1.2.1.1.1.0")))
    results.append(("snmp_walk system r1", run("snmp_walk r1", snmp_walk, R1, "1.3.6.1.2.1.1")))
    results.append(("get_interface_stats r1", run("get_interface_stats r1", get_interface_stats, R1)))
    results.append(("snmp_get sysDescr r2", run("snmp_get r2", snmp_get, R2, "1.3.6.1.2.1.1.1.0")))

    print("\n--- Connectivite (ping / traceroute depuis l'hote) ---")
    results.append(("ping_host r1", run("ping_host r1", ping_host, R1)))
    results.append(("ping_host r3", run("ping_host r3", ping_host, R3)))
    results.append(("traceroute r3", run("traceroute r3", traceroute, R3)))

    print("\n--- CLI via SSH (netmiko, liste blanche 'show') ---")
    results.append(("get_bgp_peers r1", run("get_bgp_peers r1", get_bgp_peers, R1)))
    results.append(("get_ospf_neighbors r1", run("get_ospf_neighbors r1", get_ospf_neighbors, R1)))

    print("\n--- Syslog (relais udp/1514 -> /var/log/network_syslog.log) ---")
    results.append(("get_recent_syslog", run("get_recent_syslog", get_recent_syslog, limit=5)))
    results.append(("get_recent_syslog r1", run("get_recent_syslog r1", get_recent_syslog, "r1", 5)))

    print("\n--- NetFlow (softflowd -> nfcapd udp/9995 -> /var/netflow) ---")
    results.append(("analyze_netflow r1", run("analyze_netflow r1", analyze_netflow, R1, top_n=5)))

    print("\n--- Services non exposes par le labo FRR (attendu en erreur) ---")
    results.append(("netconf_get r1 (non dispo)", run("netconf_get r1", netconf_get, R1)))

    print("\n--- Collecteurs dependent de binaires systeme ---")
    for name, binary in (("nfdump (netflow)", shutil.which("nfdump")), ("tshark (pcap)", shutil.which("tshark"))):
        status = f"present : {binary}" if binary else "ABSENT -> apt install nfdump / tshark"
        print(f"[INFO]    {name:<28} {status}")

    print("\n" + "=" * 78)
    ok = sum(1 for _, passed in results if passed)
    print(f"  Resultat : {ok}/{len(results)} collecteurs repondent en mode reel")
    print("  (netconf_get est attendu en erreur : le labo FRR n'expose pas NETCONF)")
    print("=" * 78)
    return 0 if ok >= len(results) - 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
