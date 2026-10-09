#!/bin/bash
# Injection de pannes dans le laboratoire mcp-noc-lab (bloc 1).
#
# Scenarios de demonstration (B.8 du cahier des charges) :
#   ./inject_bgp_flap.sh status     -> etat OSPF/BGP/routes sur r1
#   ./inject_bgp_flap.sh link_down  -> coupure du lien PRIMAIRE r1 <-> r2
#   ./inject_bgp_flap.sh link_up    -> retablissement du lien primaire
#   ./inject_bgp_flap.sh bgp_down   -> remise a zero de la session iBGP r1-r2
#   ./inject_bgp_flap.sh bgp_up     -> retablissement de la session iBGP
#
# La coupure est faite par `shutdown` en mode config (et non `ip link down`) :
# FRR genere alors immediatement les messages %OSPF AdjChg sur LES DEUX bouts,
# que syslogd -R forwarde au relais de l'hote (udp/1514) pour la correlation
# IA. La commande n'est ecrite QUE dans le running-config : frr.conf (bind
# monte sur le depot) n'est pas modifie tant que personne ne fait `write file`
# (lecture seule, cf. B.6). link_up retire le `shutdown` et retablit l'etat.
set -e

LAB_R1=clab-mcp-noc-lab-r1
LAB_R2=clab-mcp-noc-lab-r2
LAB_R3=clab-mcp-noc-lab-r3
ACTION="${1:-status}"

set_link() {   # set_link <container> <up|down>
  local node="$1" state="$2" cmd="no shutdown"
  [ "$state" = down ] && cmd="shutdown"
  docker exec "$node" vtysh -c "conf t" -c "interface eth1" -c "$cmd" \
    >/dev/null 2>&1 || true
}

case "$ACTION" in
  status)
    echo "=== OSPF sur R1 ==="
    docker exec "$LAB_R1" vtysh -c "show ip ospf neighbor" 2>/dev/null | grep -v "^% Can't open"
    echo
    echo "=== BGP sur R1 ==="
    docker exec "$LAB_R1" vtysh -c "show ip bgp summary" 2>/dev/null | grep -v "^% Can't open"
    echo
    echo "=== Route vers le LAN serveur (192.168.3.0/24) ==="
    docker exec "$LAB_R1" vtysh -c "show ip route 192.168.3.0/24" 2>/dev/null | grep -v "^% Can't open"
    ;;
  link_down)
    echo "[PANNE] Coupure du lien primaire R1 <-> R2 (eth1, shutdown OSPF)"
    set_link "$LAB_R1" down
    set_link "$LAB_R2" down
    echo "Evenements syslog AdjChg immediats sur r1 et r2 (relais udp/1514)."
    echo "Le trafic bascule sur le lien de secours R1 <-> R3 (coût OSPF 100)."
    echo "L'etat de la panne : ./inject_bgp_flap.sh status"
    ;;
  link_up)
    echo "[RECUP] Retablissement du lien primaire R1 <-> R2"
    set_link "$LAB_R1" up
    set_link "$LAB_R2" up
    ;;
  bgp_down)
    echo "[PANNE] Remise a zero de la session iBGP R1 <-> R2 (flapping)"
    docker exec "$LAB_R2" vtysh -c "clear ip bgp 1.1.1.1 soft" >/dev/null 2>&1 || true
    docker exec "$LAB_R2" vtysh -c "clear ip bgp 1.1.1.1" >/dev/null
    echo "Session remise a zero (messages %ADJCHANGE envoyes au relais syslog)."
    echo "Etat : ./inject_bgp_flap.sh status"
    ;;
  bgp_up)
    echo "[RECUP] Le routage OSPF permet la reconnexion iBGP en quelques secondes."
    sleep 3
    docker exec "$LAB_R1" vtysh -c "show ip bgp summary" 2>/dev/null | grep -v "^% Can't open"
    ;;
  *)
    echo "Usage: $0 [status|link_down|link_up|bgp_down|bgp_up]"
    exit 1
    ;;
esac
