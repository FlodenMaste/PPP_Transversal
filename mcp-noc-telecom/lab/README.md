# Laboratoire réseau émulé — MCP NOC Télécoms

Ce dossier contient la topologie réseau émulée via **Containerlab** + **FRRouting**,
qui sert de terrain de jeu pour le serveur MCP (outils SNMP, BGP, OSPF, NetFlow...).

## Adressage IP

| Lien | Réseau | R1 | R2 | R3 |
|---|---|---|---|---|
| R1-R2 | 10.0.12.0/30 | .1 | .2 | — |
| R2-R3 | 10.0.23.0/30 | — | .1 | .2 |
| R1-R3 (backup) | 10.0.13.0/30 | .1 | — | .2 |
| Loopback | — | 1.1.1.1/32 | 2.2.2.2/32 | 3.3.3.3/32 |
| LAN client | 192.168.1.0/24 | .1 (gw) | — | — |
| LAN serveur | 192.168.3.0/24 | — | — | .1 (gw) |

## Démarrage du labo

```bash
cd lab/
sudo clab deploy -t topology.clab.yml
```

**Attendre 10-15 secondes après le déploiement** avant de lancer des vérifications.

## Sécurité — SNMPv3 (conforme B.6 du cahier des charges)

Chaque routeur (r1, r2, r3) expose SNMP en version 3 uniquement :
- Authentification SHA, chiffrement AES (mode authPriv)
- Accès lecture seule uniquement
- Vue restreinte : système, interfaces, IP, OSPF, BGP

Identifiants de test :
- Utilisateur : mcpreadonly
- Mot de passe d'authentification : AuthPass2026!
- Mot de passe de chiffrement : PrivPass2026!

## Scénario de panne (pour la démo)

Le script fault-injection/inject_fault.sh permet de rejouer le scénario :

```bash
chmod +x fault-injection/inject_fault.sh
./fault-injection/inject_fault.sh status
./fault-injection/inject_fault.sh link_down
./fault-injection/inject_fault.sh status
./fault-injection/inject_fault.sh link_up
```

## Retour d'expérience — incidents rencontrés

| Incident | Cause | Solution |
|---|---|---|
| ip route add default échoue | Route par défaut déjà attribuée via eth0 par Containerlab | Utiliser ip route replace au lieu de ip route add |
| Ping vers 1.1.1.1 latence anormale | Collision avec l'adresse publique Cloudflare DNS | Ne jamais utiliser une adresse publique connue comme loopback |
| snmpd refuse de demarrer | Conflit entre snmpd.conf par defaut et personnalise | Ecraser directement /etc/snmp/snmpd.conf |
| apk add echoue avec erreur DNS | Resolveur DNS Docker incoherent apres redemarrage systeme | Redemarrer le service Docker |
| apk add echoue apres correction de route | Route par defaut pointant vers un routeur sans acces Internet | Placer apk add avant ip route replace dans le YAML |
| Interfaces disparues apres pause | Liens virtuels Containerlab ne survivent pas a une mise en veille | Toujours detruire le labo avant d'interrompre une session |
| Lien de secours utilise en permanence | OSPF preferait le chemin le plus court en nombre de sauts | Ajouter ip ospf cost 100 sur le lien de secours |

## Prochaines étapes

- [x] Deployer et valider OSPF + BGP
- [x] Securiser SNMP en SNMPv3
- [x] Valider le scenario de panne (aller et retour)
- [x] Forcer OSPF a preferer le chemin primaire
- [ ] Exporter la topologie en JSON pour les Resources MCP
- [ ] Ajouter la generation de Syslog
- [ ] Ajouter l'export NetFlow
