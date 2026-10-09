# Image des routeurs du laboratoire NOC (bloc 1).
#
# Base FRRouting + outils de telemetrie et d'acces a distance utilises
# par les collecteurs du socle (B.5) :
#   - net-snmp / net-snmp-tools : agent SNMPv3 en lecture seule (snmpd) ;
#   - openssh                   : sshd pour le compte « noc » (vtysh
#                                 en lecture seule, membre du groupe frrvty) ;
#   - softflowd                 : exporteur NetFlow (UDP/9995 vers l'hote).
#
# Construction (une fois, hors ligne ensuite) :
#   docker build -t mcp-noc-frr:local lab/containerlab
FROM frrouting/frr:latest

RUN apk add --no-cache net-snmp net-snmp-tools openssh softflowd
