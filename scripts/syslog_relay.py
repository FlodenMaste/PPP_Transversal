#!/usr/bin/env python3
"""
Relais syslog du laboratoire (telemetrie B.3).

Les routeurs FRR exportent leur journalisation vers l'hote via busybox
`syslogd -L -R 172.20.20.1:1514` (cf. lab/containerlab/topology.clab.yml) ;
ce relais ecoute le port UDP 1514, normalise chaque datagramme au format
attendu par le collecteur du socle et l'append dans SYSLOG_FILE_PATH
(/var/log/network_syslog.log par defaut).

Normalisation (busybox n'envoie ni nom d'hote ni balise %FAC-SEV-MNEMONIC) :

    brut  : <30>Oct  9 08:10:01 bgpd[145]: message...
    ecrit : <30>Oct  9 08:10:01 r1 %DAEMON-6-bgpd: message...

soit <PRI><timestamp> <hostname> %<facility>-<severity>-<mnemonic>: <message>,
format regex _SYSLOG_LINE_RE de collector/syslog/syslog_collector.py.
Les lignes deja conformes sont recopies telles quelles.

Usage :
    python3 scripts/syslog_relay.py
    SYSLOG_HOSTS="10.0.0.1=r1,10.0.0.2=r2" python3 scripts/syslog_relay.py --port 1514
"""

from __future__ import annotations

import argparse
import os
import re
import socketserver
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_OUTPUT = "/var/log/network_syslog.log"

# IP d'expedition -> nom d'hote (labo containerlab par defaut).
DEFAULT_HOSTS = {
    "172.20.20.11": "r1",
    "172.20.20.12": "r2",
    "172.20.20.13": "r3",
    "172.20.20.14": "client",
    "172.20.20.15": "server",
}

_FACILITY_NAMES = {
    0: "kern",
    2: "mail",
    3: "daemon",
    4: "auth",
    10: "authpriv",
    16: "local0",
    17: "local1",
    18: "local2",
    20: "local4",
    23: "local7",
}

# <PRI><timestamp> deja au format attendu
_LINE_RE = re.compile(r"^<(?P<pri>\d+)>(?P<ts>\w+\s+\d+\s+\d+:\d+:\d+)\s+(?P<rest>.*)$")
# busybox : "bgpd[145]: suite" ou "bgpd: suite"
_TAG_RE = re.compile(r"^(?P<tag>[A-Za-z_][\w.-]*)(?:\[(?P<pid>\d+)\])?:\s*(?P<msg>.*)$")


def parse_hosts(raw: str | None) -> dict[str, str]:
    """\"ip=nom,ip=nom\" -> {ip: nom} ; repli sur la table du labo."""
    if not raw:
        return dict(DEFAULT_HOSTS)
    table: dict[str, str] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            continue
        ip, name = item.split("=", 1)
        ip, name = ip.strip(), name.strip()
        if ip and name:
            table[ip] = name
    return table or dict(DEFAULT_HOSTS)


def normalize(line: str, source_ip: str, hosts: dict[str, str]) -> str:
    """Rewrite un datagramme busybox au format du collecteur du socle."""
    match = _LINE_RE.match(line)
    if not match:
        return line
    pri = int(match.group("pri"))
    ts = match.group("ts")
    rest = match.group("rest").strip()
    hostname = hosts.get(source_ip, source_ip)

    # Deja normalisee (hostname + %FAC-SEV-MNEMONIC:) : conserve telle quelle.
    if re.match(r"^\S+\s+%\w+-\d+-[\w-]+:\s", rest):
        return line

    facility = pri // 8
    severity = pri % 8
    fac_name = _FACILITY_NAMES.get(facility, f"local{facility % 8}" if facility >= 16 else "daemon")

    tag_match = _TAG_RE.match(rest)
    if tag_match:
        mnemonic = tag_match.group("tag").split(".")[0]
        message = tag_match.group("msg")
    else:
        mnemonic = "msg"
        message = rest
    mnemonic = re.sub(r"[^A-Za-z0-9_]", "-", mnemonic) or "msg"

    return f"<{pri}>{ts} {hostname} %{fac_name.upper()}-{severity}-{mnemonic}: {message}"


class SyslogHandler(socketserver.BaseRequestHandler):
    """Normalise puis ecrit le datagramme UDP recu dans le fichier de telemetrie."""

    def handle(self) -> None:
        data, _sock = self.request
        if not data:
            return
        line = data.decode("utf-8", errors="replace").rstrip("\n")
        if not line:
            return
        source_ip = self.client_address[0]
        line = normalize(line, source_ip, self.server.hosts)  # type: ignore[attr-defined]
        try:
            with open(self.server.output_path, "a", encoding="utf-8") as handle:  # type: ignore[attr-defined]
                handle.write(line + "\n")
        except OSError as exc:
            print(f"[syslog-relay] ecriture impossible : {exc}", file=sys.stderr)
            return
        if self.server.verbose:  # type: ignore[attr-defined]
            source = f"{source_ip}:{self.client_address[1]}"
            print(
                f"[{datetime.now(timezone.utc).isoformat()}] {source} -> {line[:160]}",
                file=sys.stderr,
            )


class SyslogServer(socketserver.UDPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0", help="adresse d'ecoute (defaut : toutes)")
    parser.add_argument("--port", type=int, default=1514, help="port UDP (defaut : 1514)")
    parser.add_argument(
        "--output",
        default=os.environ.get("SYSLOG_FILE_PATH", DEFAULT_OUTPUT),
        help=f"fichier de destination (defaut : SYSLOG_FILE_PATH ou {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--hosts",
        default=os.environ.get("SYSLOG_HOSTS"),
        help='table ip=nom (defaut : SYSLOG_HOSTS ou labo containerlab)',
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="trace chaque message")
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.touch(exist_ok=True)

    hosts = parse_hosts(args.hosts)
    server = SyslogServer((args.host, args.port), SyslogHandler)
    server.output_path = str(output)
    server.verbose = args.verbose
    server.hosts = hosts
    print(
        f"[syslog-relay] ecoute udp/{args.host}:{args.port} -> {output} "
        f"({len(hosts)} hotes connus)",
        file=sys.stderr,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
