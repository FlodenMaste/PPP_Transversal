# Laboratoire réseau (bloc 1) — Containerlab + FRRouting

Réseau émulé local, 5 nœuds, **aucun matériel** : routes OSPF area 0 + iBGP
AS65000, panne injectable, télémétrie (SNMPv3, SSH, syslog, NetFlow) lue par
les collecteurs du socle en mode `COLLECTOR_MODE=real`.

```
                r2 (172.20.20.12)
               / \              10.0.12.0/30  r1↔r2 (primaire)
   r1 --------   -------- r3    10.0.23.0/30  r2↔r3 (transit)
172.20.20.11  \ /               10.0.13.0/30  r1↔r3 (secours)
               X
              / \
   client ----   ---- server     LAN client 192.168.1.0/24  (r1 eth3)
172.20.20.14                     LAN serveur 192.168.3.0/24 (r3 eth3)
                 172.20.20.15
```

* **Plan de management** (`172.20.20.0/24`, bridge Docker `clab-*`) : cibles
  statiques des collecteurs **depuis l'hôte** (SNMP, SSH, ping, syslog).
* **Plan de données** (veth point-à-point) : OSPF/iBGP ; joignable **depuis
  les conteneurs uniquement**. ⚠ Les LAN `192.168.1.0/24` et `192.168.3.0/24`
  peuvent chevaucher le LAN de la machine hôte : pour un test depuis l'hôte,
  utiliser les IPs de management, pas les IPs de LAN.

## Fichiers

| Fichier | Rôle |
|---|---|
| `containerlab/topology.clab.yml` | topologie + commandes de démarrage (sshd, snmpd, syslogd, softflowd) |
| `containerlab/configs/r{1,2,3}/frr.conf` | OSPF + iBGP (`log syslog informational`) |
| `containerlab/configs/r{1,2,3}/snmpd.conf` | SNMPv3 `createUser mcpreadonly` (SHA/AES), vue `limited`, `rouser … priv` |
| `containerlab/Dockerfile` | image routeur `mcp-noc-frr:local` (FRR + net-snmp + openssh + softflowd) |
| `containerlab/Dockerfile.term` | image terminal `mcp-noc-term:local` (snmpwalk + softflowd) |
| `fault-injection/*.sh` | coupure de lien / flap BGP déterministes (démo live) |
| `validate_collectors.py` | validation des 13 collecteurs **en mode réel** contre le labo |

## Déploiement

```bash
# 1. images (une fois) - les paquets sont dedans : aucun apk au démarrage
docker build -t mcp-noc-frr:local  lab/containerlab
docker build -t mcp-noc-term:local -f lab/containerlab/Dockerfile.term lab/containerlab

# 2. labo (5 conteneurs, liens data + management)
sudo containerlab deploy -t lab/containerlab/topology.clab.yml

# 3. services d'acquisition sur l'hôte (idempotent)
sudo scripts/lab_services.sh          # relais syslog udp/1514 + nfcapd udp/9995
scripts/lab_services.sh status
```

À l'initialisation chaque routeur lance : `syslogd -L -R 172.20.20.1:1514`,
`softflowd -i eth1 -n 172.20.20.1:9995 -v 9`, `sshd`, `snmpd` (le compte SSH
`noc` / `LabPass2026!` est membre de `frrvty` = `vtysh` en lecture seule).

## Télémétrie

| Canal | Chaîne | Lecture par le socle |
|---|---|---|
| SNMPv3 authPriv | `snmpd` (r1..r3) → pysnmp depuis l'hôte | `snmp_get`, `snmp_walk`, `get_interface_stats` |
| CLI show | `ssh noc@172.20.20.x` → netmiko → `vtysh -c "show …"` (liste blanche) | `get_bgp_peers`, `get_ospf_neighbors` |
| Syslog | `syslogd -R` (routeurs) → udp/1514 → `scripts/syslog_relay.py` (normalisation `<PRI> ts host %FAC-SEV-MNEM:`) → `/var/log/network_syslog.log` | `get_recent_syslog` |
| NetFlow v9 | `softflowd -i eth1` (5 nœuds) → udp/9995 → `nfcapd` → `/var/netflow` (rotation 60 s) | `analyze_netflow` (nfdump) |
| Connectivité | ping / traceroute depuis l'hôte | `ping_host`, `traceroute` |
| NETCONF | non exposé par FRR 8.5 → retour d'erreur explicite en mode réel | `netconf_get` (attendu en erreur, documenté) |

## Validation

```bash
cd PPP_MCP_Telecom_Supervision
cp .env.example .env          # COLLECTOR_MODE=real + cles SNMPv3/CLI du labo
./venv/bin/python lab/validate_collectors.py
```

Attendu : **13/13 collecteurs OK en mode réel** — `netconf_get` interroge
`r1:830` (sous-système RFC 6241 du labo, base 1.0, lecture seule).

Puis injection de panne pour la démonstration live :

```bash
sudo lab/fault-injection/inject_bgp_flap.sh status    # etat OSPF/BGP/routes
sudo lab/fault-injection/inject_bgp_flap.sh link_down # coupure lien primaire r1<->r2
#   -> messages %OSPF AdjChg immediats sur r1 ET r2 (running-config only,
#      frr.conf non modifie) relayes en ~1 s dans /var/log/network_syslog.log
NOC_SYSLOG_FILE=/var/log/network_syslog.log \
  mcp-noc-ai/venv/bin/python -c "…"   # correlate_alarms integre le labo
sudo lab/fault-injection/inject_bgp_flap.sh link_up   # retablissement (~1 min)
sudo lab/fault-injection/inject_bgp_flap.sh bgp_down  # flap iBGP -> %ADJCHANGE
```

`log-adjacency-changes` (OSPF) et `bgp log-neighbor-changes` sont actifs dans
`configs/r*/frr.conf` : sans eux, FRR ne journalise pas les changements
d'adjacence et la corrélation IA n'a rien à corrélé.
