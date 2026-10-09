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
# Les commandes envoyees aux equipements sont limitees a des operations de
# mise en lien / de remise a zero : aucune modification de configuration
# permanente n'est ecrite sur les routeurs (lecture seule, cf. B.6).
set -e

LAB_R1=clab-mcp-noc-lab-r1
LAB_R2=clab-mcp-noc-lab-r2
LAB_R3=clab-mcp-noc-lab-r3
ACTION="${1:-status}"

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
    echo "[PANNE] Coupure du lien primaire R1 <-> R2 (eth1)"
    docker exec "$LAB_R1" ip link set eth1 down
    docker exec "$LAB_R2" ip link set eth1 down
    echo "Le trafic bascule sur le lien de secours R1 <-> R3 (coût OSPF 100)."
    echo "L'etat de la panne : ./inject_bgp_flap.sh status"
    ;;
  link_up)
    echo "[RECUP] Retablissement du lien primaire R1 <-> R2"
    docker exec "$LAB_R1" ip link set eth1 up
    docker exec "$LAB_R2" ip link set eth1 up
    ;;
  bgp_down)
    echo "[PANNE] Remise a zero de la session iBGP R1 <-> R2 (flapping)"
    docker exec "$LAB_R2" vtysh -c "clear ip bgp 1.1.1.1 soft" >/dev/null 2>&1 || true
    docker exec "$LAB_R2" vtysh -c "clear ip bgp 1.1.1.1" >/dev/null
    echo "Session remise a zero. Etat : ./inject_bgp_flap.sh status"
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
