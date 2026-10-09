# Dimensionnement & TCO

Document de calcul (critère **B.10 — Dimensionnement & Rigueur, 30 %**) : hypothèses,
formules, mesures de terrain, résultats par scénario et coût total de possession (TCO).
Toutes les mesures sont **reproductibles** via `scripts/measure_dimensionnement.sh`
(labo déployé, services actifs).

- Date des mesures : **09/10/2026**, fenêtre 07:50 → 09:12 (82 min).
- Date des sources tarifaires : **09/10/2026** (voir §10).
- Toutes les unités sont explicites ; les valeurs intermédiaires ne sont pas arrondies.

---

## 1. Objet et méthode

Le dimensionnement répond à trois questions : **combien de données** (syslog + NetFlow),
**quelle machine** (CPU, RAM, stockage) et **quel coût** (TCO 3 ans), pour trois cibles :

| Scénario | Périmètre | Usage |
|---|---|---|
| **S0 — Labo** | 5 nœuds containerlab (3 routeurs FRR, 1 client, 1 serveur) | Démonstration réelle de ce dépôt |
| **S1 — PME** | 50 équipements supervisés (site unique) | Cible « petit déploiement » |
| **S2 — Entreprise** | 500 équipements supervisés | Cible « déploiement étendu » |
| S3 — Datacenter / bord opérateur | débit de flux seul | Ordre de grandeur (formules seules) |

Méthode : (i) mesurer le labo, (ii) calibrer les constantes sur des sources publiées et
vérifiables, (iii) appliquer des formules fermées, (iv) recouper les résultats entre eux,
(v) chiffrer le TCO avec des prix sourcés. Les hypothèses non mesurables sont signalées
comme telles (§9).

---

## 2. Hypothèses de travail

| Hypothèse | Valeur | Justification |
|---|---|---|
| Durée de rétention | **30 jours** | Usage NOC type (investigation sur 1 mois) |
| Longueur d'un événement syslog `L` | **810 B** (retenu), plancher 118,5 B | Dérivé de l'estimateur Cisco : 4,3 GB/j ÷ (61 EPS × 86 400 s) = **816 B** ; 1,4 GB/j ÷ (20 × 86 400) = **810 B** (§5) |
| Taille d'un enregistrement NetFlow `R` | **489 B/flux** sur disque (retenu, prudence) | Mesuré sur le labo (nfdump brut) ; fourchette littérature 100 B (paquet) → 400–490 B (journal) → 500–600 B (indexé) (§5) |
| Facteur de compression `k` | **1** (brut) ou **1/2,8** (compressé) | Internet2/Abilene : compression mesurée ≈ 2,8:1 |
| EPS routeur/switch | **0,05 EPS** moyen (≈ 4 320 événements/jour) | Événements d'adjacence, interfaces, traps — régime permanent du labo mesuré à 0,036 EPS |
| EPS serveur | **0,5 EPS** | Authentifications, services, systèmes |
| EPS pare-feu | **61 EPS** | Cisco : 1010 à 60 % de charge ≈ 61 EPS (événements de connexion) |
| Débit de flux `F` (PME) | **500 à 2 000 flux/s** | ntop : Small/Medium Business |
| Débit de flux `F` (entreprise) | **5 000 à 20 000 flux/s** | ntop : Large Enterprise Core |
| Débit de flux `F` (DC) | **50 000 à 200 000 flux/s** | ntop : Large Data Center / ISP Edge |
| Taux horaire d'ingénierie | **289 €/jour** | §8.2 (calcul détaillé) |
| Électricité (labo) | **60 W moyens**, **0,1318 €/kWh HT** | Hypothèse machine (non mesurable, §9) ; tarif EDF non résidentiel ≤ 36 kVA au 01/08/2026 |

### Mix d'équipements retenus

| Scénario | Routeurs/switchs (0,05 EPS) | Serveurs (0,5 EPS) | Pare-feux (61 EPS) | **EPS total** |
|---|---|---|---|---|
| S1 — PME 50 | 40 | 8 | 2 | 40×0,05 + 8×0,5 + 2×61 = **128 EPS** |
| S2 — Entreprise 500 | 400 | 80 | 20 | **1 280 EPS** |

> Les pare-feux dominent le calcul (2 équipements sur 50 = 95 % du volume syslog) :
> c'est le comportement réel constaté par Cisco (« Connection events make up the vast
> majority of all events »), d'où l'intérêt de filtrer les événements de trafic.

---

## 3. Mesures de terrain (labo S0)

Rejouer : `scripts/measure_dimensionnement.sh`.

| Grandeur | Mesure | Commande |
|---|---|---|
| Syslog : volume moyen | 176 lignes / 20 853 octets → **118,5 B/ligne** | `wc -l -c /var/log/network_syslog.log` |
| Syslog : EPS mesuré | 176 événements / 4 920 s = **0,036 EPS** | idem + fenêtre |
| NetFlow : volume utile | 114 flux / 42 736 B → **374,9 B/flux** | `nfdump -r /var/netflow \| tail -4` |
| NetFlow : volume sur disque | 55 714 B / 114 flux → **488,7 B/flux** (83 fichiers) | `du -sb /var/netflow` |
| NetFlow : débit d'export | 114 flux / 4 920 s = **0,0232 flux/s** → **90,6 bit/s** | idem |
| NetFlow : débit de traitement nfdump | **7 520 flux/s** (échantillon de 114 flux : indicatif, pas un benchmark) | `flows/second` de nfdump |
| RAM routeurs FRR | **25,8 – 26,2 MiB** (r1 26,17 / r2 25,84 / r3 26,03) | `docker stats --no-stream` |
| RAM client / serveur labo | 624 KiB / 792 KiB | idem |
| CPU routeurs | ≤ **0,12 %** | idem |
| RAM relais syslog | **14,0 MiB** | `ps -eo rss,args` |
| RAM nfcapd (×2 : 2055 hôte + 9995 labo) | **2,5 MiB** chacun | idem |
| RAM serveurs MCP (4) | 76,8 + 81,2 + 95,8 + 71,8 = **325,6 MiB** | `ps -eo rss,args` (serveur démarré) |
| Hôte de démonstration | **15,96 GiB** RAM (≈ 3 GiB utilisés), load 3,04, disque 50 G **88 %** (5,8 G libres) | `free -h`, `uptime`, `df -h /` |
| Collectes réelles | **12/13** collecteurs répondent (NETCONF absent du labo FRR, attendu) | `lab/validate_collectors.py` |

Ordre de grandeur labo : à l'état de repos le labo génère **0,036 EPS** et **0,023 flux/s**,
soit ≈ **0,37 MB/jour** de syslog (avec `L` mesuré) et ≈ **1 MB/jour** de NetFlow :
un poste unique suffit largement.

---

## 4. Formules de dimensionnement

Toutes les formules sont en unités SI (octets, bits, secondes), 1 jour = 86 400 s.

| Réf. | Formule | Résultat |
|---|---|---|
| **F1** | `V_syslog(j) = EPS × 86 400 × L` | volume syslog en octets/jour |
| **F2** | `P_syslog = EPS × L × 8` | débit réseau syslog en bit/s |
| **F3** | `P_export = F × R × 8` | bande passante d'export NetFlow en bit/s (**ntop**) |
| **F4** | `V_netflow(j) = F × 86 400 × R` | volume NetFlow en octets/jour |
| **F5** | `S(T) = (V_syslog + V_netflow) × T × k` | stockage sur `T` jours ; `k = 1` brut, `1/2,8` compressé |
| **F6** | `RAM = Σ RSS(mesurés) × 1,3` | RAM avec 30 % de marge |
| **F7** | `Débit d'écriture = (V_syslog + V_netflow) / 86 400` | I/O disque moyen en octets/s |
| **F8** | `TCO = CAPEX + Σ années (hébergement + énergie + main-d'œuvre)` | coût total sur la durée |

---

## 5. Calibration des constantes et recoupements

Chaque constante est soit **mesurée**, soit **dérivée d'une source**, et **recoupée** par une
source indépendante.

### 5.1 Longueur d'événement `L`

| Point de mesure / source | `L` |
|---|---|
| **Mesuré** — relais du labo (lignes FRR normalisées) | 118,5 B |
| **Dérivé Cisco** — 61 EPS → 4,3 GB/j : `4,3e9 / (61 × 86 400)` | **816 B** |
| **Dérivé Cisco** — 20 EPS → 1,4 GB/j : `1,4e9 / (20 × 86 400)` | **810 B** |
| **Retenu** (prudent) | **810 B** |

**Recoupement** : avec `L = 810 B`, l'estimateur Cisco 2 106 EPS donne
`2 106 × 86 400 × 810 = 147 GB/jour`, et le nombre d'événements `2 106 × 86 400 = 181 958 400`
est **exactement** celui publié par Cisco → la calibration est cohérente.
Écart labo ↔ Cisco : ×6,8 (message FRR court vs événement firewall structuré) : on dimensionne
sur la borne haute et on montre le plancher mesuré (sensibilité en §6.1).

### 5.2 Taille d'enregistrement NetFlow `R`

| Source | `R` | Observe |
|---|---|---|
| **Mesuré** — labo, nfdump brut sur disque | **488,7 B** | retenu (prudent) |
| **Mesuré** — labo, charge utile nfdump | 374,9 B | utile hors en-têtes de fichiers |
| Internet2/Abilene (2010), NetFlow v5 | 48 B | format fixe, sans templates |
| ntop — exemple de calcul | 100 B (jusqu'à 150 B avec L7) | enregistrement moyen « typique » |
| Netdata (2026) — journal brut | ≈ 400 B (340 B faible cardinalité, **490 B** forte cardinalité) | **recoupe notre mesure** |
| Elastic / ElastiFlow — record indexé Elasticsearch | 500–600 B | indexation incluse |
| ntopng — base de flux interne | 11 B | stockage propriétaire compressé |

**Recoupements chiffrés** :
- Netdata : `1 000 flux/s × 86 400 × 400 B = 34,6 GB/j` → ≈ **35 GB/j** publié ✓ ;
  et « ~490 bytes/flow on high-cardinality traffic » = notre mesure **488,7 B** ✓.
- PacketMentor : `50 000 flux/s → ~430 GB/j` ⇒ `430e9 / (50 000 × 86 400) ≈ 99,5 B`
  (soit `R = 100 B`, le format paquet) : l'écart ×5 avec notre valeur s'explique par le
  stockage brut fichier par fichier vs enregistrement compact — d'où le couple
  **489 B (brut) / 100 B (paquet)** utilisé en sensibilité.
- Abilene : `750e6 flux/j × 48 B = 36 GB` ≈ **35 GB** publié ✓ ;
  `750e6 / 86 400 × 48 × 8 = 3,33 Mbit/s` ≈ **3,4 Mbit/s** publié ✓.

### 5.3 Formule de bande passante d'export (ntop)

`P_export = F × R × 8`. Avec `R = 100 B` la formule reproduit **exactement** la table ntop :
500 flux/s → 0,4 Mbit/s ; 2 000 → 1,6 Mbit/s ; 5 000 → 4 Mbit/s ; 20 000 → 16 Mbit/s ;
50 000 → 40 Mbit/s ✓. Avec notre `R = 489 B` (prudent), les valeurs sont ×4,9.

---

## 6. Résultats

### 6.1 Syslog (F1) — sensibilité sur `L`

| Scénario | EPS | `L = 118,5 B` (mesuré labo) | **`L = 810 B` (retenu)** | 30 j (`L = 810 B`) |
|---|---|---|---|---|
| S0 Labo (mesuré) | 0,036 | 0,37 MB/j | 2,5 MB/j | 75 MB |
| S1 PME 50 | 128 | 1,31 GB/j | **9,0 GB/j** | **269 GB** |
| S2 Entreprise 500 | 1 280 | 13,1 GB/j | **89,6 GB/j** | **2 687 GB** |

Vérification F2 (débit réseau) : `128 × 810 × 8 = 830 kbit/s` → négligeable sur un lien ≥ 100 Mbit/s.

### 6.2 NetFlow (F3, F4) — sensibilité sur `F` et `R`

`R = 488,7 B` (brut retenu), rétention 30 j.

| Scénario | `F` (flux/s) | `P_export` (F3) | `V_netflow`/j (F4) | 30 j brut | 30 j compressé (÷2,8) |
|---|---|---|---|---|---|
| S0 Labo (mesuré) | 0,0232 | 0,09 kbit/s | 0,98 MB | 29 MB | 10 MB |
| S1 PME (ntop min) | 500 | **1,95 Mbit/s** | **21,1 GB** | **633 GB** | 226 GB |
| S1 PME (ntop max) | 2 000 | 7,8 Mbit/s | 84,4 GB | 2 532 GB | 904 GB |
| S2 Ent. (ntop min) | 5 000 | 19,5 Mbit/s | 211 GB | 6,33 TB | 2,26 TB |
| S2 Ent. (ntop max) | 20 000 | 78,2 Mbit/s | 845 GB | 25,3 TB | 9,05 TB |
| S3 DC (ntop min) | 50 000 | 195 Mbit/s | 2,11 TB | 63,3 TB | 22,6 TB |

Avec `R = 100 B` (borne basse, format paquet) : 500 flux/s → 4,3 GB/j et 30 j → 130 GB.

### 6.3 Stockage combiné (F5) et I/O (F7) — scénario PME retenu

`S(30 j) = (9,0 + 21,1) GB/j × 30 = 903 GB` en **brut** ; avec compression du NetFlow
÷2,8 seulement : `269 + 226 = 495 GB`. En `R = 100 B` : `269 + 130 = 399 GB`.

`Débit d'écriture = (9,0 + 21,1) × 1e9 / 86 400 ≈ 0,35 Mo/s` → **très faible** : aucun goulot
d'I/O attendu sur NVMe (Netdata : 50 000 flux/s nécessitent déjà du NVMe, soit ~1,7 TB/j —
80× notre cas PME). Côté labo : `(2,5 MB + 0,98 MB) / 86 400 ≈ 40 octets/s`.

### 6.4 CPU et RAM (F6)

| Besoin (scénario PME retenu) | Justification |
|---|---|
| Ingestion NetFlow 500 flux/s | ≪ 7 520 flux/s mesurés (nfdump) et ≪ 50 000–100 000 flux/s par agent (Netdata) ; ≪ 80–102 Kfps (ntop/nProbe) |
| Ingestion syslog 128 EPS (830 kbit/s) | négligeable (un relais Python fait 14 MiB de RSS) |
| Écriture disque 0,35 Mo/s | négligeable |
| RAM applicative mesurée | 4 serveurs MCP 325,6 MiB + relais 14 MiB + nfcapd 5 MiB = **345 MiB** |
| OS + marge 30 % (F6) | 345 MiB × 1,3 ≈ 0,45 GiB → **8 GiB retenus** (marge ×4) |
| Routeurs du labo (référence) | 26 MiB et ≤0,12 % de CPU par nœud FRR complet (FRR + snmpd + sshd + softflowd + syslogd) |

**Plateforme retenue (S1 PME)** : 4 vCPU / 8 GiB / 1 To NVMe suffisent par calcul.
Le TCO §8 retient néanmoins l'offre **OVH ADVANCE-1** (6 vCPU / 32 GiB / 2 × 960 Go NVMe,
159,99 € HT/mois) : offre la mieux sourcée, offre aussi la redondance de stockage
(RAID logiciel) et la marge de croissance — surcoût assumé.

---

## 7. Dimensionnement par scénario (synthèse)

| | S0 Labo (réel) | S1 PME 50 | S2 Entreprise 500 |
|---|---|---|---|
| EPS retenu | 0,036 (mesuré) | 128 | 1 280 |
| Syslog / jour (`L=810 B`) | 2,5 MB | 9,0 GB | 89,6 GB |
| NetFlow / jour (`R=489 B`) | 0,98 MB (0,023 flux/s) | 21,1 GB (500 flux/s) | 211 GB (5 000 flux/s) |
| Export NetFlow | 0,09 kbit/s | 1,95 Mbit/s | 19,5 Mbit/s |
| Stockage 30 j (brut) | ≈ 104 MB | **903 GB** | 9,02 TB |
| Écriture moyenne | ≈ 0,01 Mo/s | 0,35 Mo/s | 3,5 Mo/s |
| CPU / RAM | hôte existant (16 GiB, ≈3 GiB occupés) | 4 vCPU / 8 GiB (mesuré : 0,35 GiB applicatif) | 8 vCPU / 16 GiB, + agent NetFlow par site |
| Remarque | disque hôte à 88 % : rotation à activer | 903 GB > 2 × 960 Go utiles : **compresser (÷2,8 → 495 GB)** ou étendre le stockage | **distribution** : un agent de collecte par site (enveloppe 50–100 Kflux/s par agent) |

---

## 8. TCO (coût réel calculé)

### 8.1 Prix et paramètres sourcés

| Paramètre | Valeur | Source (§10) |
|---|---|---|
| Serveur ADVANCE-1 (Gen 2026, 6 vCPU, 32 Go, 2×960 Go NVMe) | **159,99 € HT/mois** (depuis le 11/08/2026) | OVHcloud |
| Électricité non résidentielle ≤ 36 kVA | **13,18 c€/kWh HT** (abonnement 6 kVA : 168,60 €/an HT) | EDF Tarif Bleu, grille au 01/08/2026 |
| Salaire brut annuel médian ingénieur réseau (France, 2026) | **45 000 €** | fiche-paie.fr |
| Cotisations patronales | **39,81 %** du brut (somme des taux URSSAF), **réduction générale nulle au-delà de 1,6 SMIC** (1,6 × 1 867,02 €/mois au 01/06/2026 ≈ **35 850 €/an**) → coefficient **×1,40** (45 000 € > 35 850 €) | URSSAF |
| Jours ouvrés | 218/an | convention |
| Licences logicielles | **0 €** — FRR, containerlab, nfdump/softflowd, FastMCP, Python : open source | dépôt |

### 8.2 Main-d'œuvre (F8)

```
Coût employeur = 45 000 € × 1,40 = 63 000 €/an
Jour ouvré     = 63 000 / 218     = 289 €/jour   (soit 38,30 €/h sur 1 645 h)
```

### 8.3 TCO du labo de démonstration (S0, 3 ans)

| Poste | Calcul | Montant |
|---|---|---|
| CAPEX | matériel déjà existant (poste 16 GiB) | **0 €** |
| Énergie | 60 W × 8 760 h = 526 kWh/an × 0,1318 € | 69,3 €/an → **208 €** (3 ans) |
| Main-d'œuvre | mise en place 3 j + 0,5 j/an = 4,5 j × 289 € | **1 301 €** |
| Licences | open source | 0 € |
| **Total 3 ans** | | **1 509 € HT** (≈ 42 €/mois) |

### 8.4 TCO d'un déploiement PME (S1, 3 ans)

| Poste | Calcul | Montant |
|---|---|---|
| Hébergement | 159,99 €/mois × 36 | **5 759,64 €** |
| Stockage | 2 × 960 Go NVMe inclus (903 GB/30 j bruts → 495 GB compressés) | 0 € |
| Énergie | incluse dans l'offre hébergeur | 0 € |
| Main-d'œuvre déploiement | 10 j × 289 € | 2 890 € |
| Main-d'œuvre exploitation | 0,5 j/mois = 6 j/an → 18 j × 289 € | 5 202 € |
| Licences | open source | 0 € |
| **Total 3 ans** | | **13 852 € HT** |
| **Coût mensuel équivalent** | 13 852 / 36 | **385 €/mois** |

### 8.5 TCO entreprise (S2, ordre de grandeur, 3 ans)

Même formule avec 2 nœuds redondés (HA) et une exploitation plus lourde :

```
Hébergement : 2 × 159,99 € × 36              = 11 519 €
Main-d'œuvre : (20 j déploiement + 1 j/mois)  = 56 j × 289 € = 16 184 €
Stockage 30 j : 9,02 TB brut (2,26 TB compressé) → capacité hors offre ADVANCE-1 :
                disque additionnel ou stockage objet À SOURCER
Total 3 ans (hors stockage étendu)            ≈ 27 703 € HT  (≈ 770 €/mois)
```

**Ce que le TCO ne couvre pas** (volontairement assumé, non sourcé) : licences
d'outils propriétaires (non retenus), sauvegardes externes, connectivité, poste
d'exploitation dédié, projets de migration.

---

## 9. Limites et points de vigilance

1. **Mesures courtes** : 82 minutes de NetFlow, 176 événements syslog, échantillon de 114 flux
   pour le débit nfdump (7 520 flux/s = ordre de grandeur, pas un benchmark). Les constantes
   `L` et `R` sont donc **recoupées par la littérature** (§5) plutôt que déduites seules.
2. **Énergie non mesurable** : les compteurs RAPL de l'hôte ne s'incrémentent pas sous
   l'hyperviseur → hypothèse **60 W** à confirmer par un wattmètre.
3. **Disque du labo à 88 %** (50 Go, 5,8 Go libres) : la rétention longue n'est pas tenable
   sur l'hôte tel quel — activer rotation/compression (§7).
4. **NETCONF absent** du labo FRR (12/13 collecteurs) : pas d'impact sur les volumes, mais
   la colonne NETCONF du dimensionnement reste à instruire sur un équipement qui l'expose.
5. **Main-d'œuvre = hypothèse** : pas de relevé de temps dans le dépôt (historique git réduit
   à 3 commits) → hypothèse explicite de 289 €/j, à ajuster selon le profil réel.
6. **Prix volatils** : OVHcloud a révisé ses tarifs au 11/08/2026 (+52 % sur l'ADVANCE-1) et
   procède à des révisions trimestrielles ; le tarif EDF est révisé le 1er février et le
   1er août → **réévaluer le TCO à la souscription**.
7. **Bornes de sensibilité** : sur le scénario PME le stockage 30 j varie de **399 GB**
   (`R = 100 B`, `L = 810 B`) à **903 GB** (`R = 489 B`) — retenir la borne haute,
   prévoir la compression.

---

## 10. Sources

Accès le **09/10/2026**, sauf mention contraire.

1. **Cisco — Logging Best Practices (Secure Firewall 7.6)** — 61 EPS → 4,3 GB/jour ;
   20 EPS → 1,4 GB/jour ; 2 106 EPS = 181 958 400 événements/jour ; méthodologie
   `EPS = événements / 86 400`. https://secure.cisco.com/secure-firewall/v7.6/docs/logging-best-practices (publié 2024-07-26)
2. **Cisco — Firewall Performance Estimator** (outil en ligne, base des exemples). https://ngfwpe.cisco.com/ftd-logging-estimator
3. **ntop — How much bandwidth does NetFlow take during export ?** — formule
   `Bandwidth (bps) = Flows per Second × Bytes per Flow Record × 8` ; table SMB 500–2 000 flux/s
   → 400 kbit/s–1,6 Mbit/s, entreprise 5 000–20 000 → 4–16 Mbit/s, DC 50 000–200 000 → 40–160+ Mbit/s. https://www.ntop.org/faq/how-much-bandwidth-does-netflow-take-during-export/
4. **ntop — NetFlow Collection Performance using ntopng and nProbe** — ~10 Mbit/s ≈ 12 000 flux/s ; 102 Kflux/s sans perte (4 interfaces). https://www.ntop.org/netflow-collection-performance-using-ntopng-and-nprobe/
5. **ntop — ntopng Disk Requirements** — 11 octets/flux en base propriétaire. https://www.ntop.org/ntopng-disk-requirements-for-timeseries-and-flows/
6. **Netdata — Sizing and Capacity Planning (Network Flows, 2026)** — journal brut ≈ 400 B/flux
   (340 B faible cardinalité, **490 B** forte cardinalité) ; 1 000 flux/s ≈ 35 GB/j ;
   enveloppe **50 000–100 000 flux/s par agent**. https://learn.netdata.cloud/docs/network-performance-monitoring/network-flows/sizing-and-capacity-planning
7. **PacketMentor — NetFlow (2026)** — 50–100 octets/record ; 50 000 flux/s ≈ 5 Mo/s ≈ 430 GB/j ;
   paliers de rétention (7–14 j chaud, 30–90 j tiède, 1 an+ froid). https://packetmentor.com/topics/netflow/
8. **Elastic / ElastiFlow — Tune for indexing speed** — record NetFlow indexé 500–600 B ;
   ingestion 350 000 records/s sur cluster 5 nœuds. https://discuss.elastic.co/t/tune-for-indexing-speed/318873
9. **Internet2 / Abilene — Network Flow Analysis (2010)** — 700–800 M flux/jour, 48 B/record
   → ~35 GB et ~3,4 Mbit/s, compression mesurée **2,8:1**. https://www.slideshare.net/slideshow/network-flow-analysis-3984307/
10. **EDF — Tarif Bleu non résidentiel ≤ 36 kVA**, grille au 01/08/2026 : 13,18 c€/kWh HT,
    abonnement 6 kVA 168,60 €/an HT. https://www.edf.fr/sites/entreprise/files/2026-07/Fiche_descriptive_tarif_bleu_non_residentiel_inf36kVA.pdf
11. **OVHcloud — Dedicated servers pricing update H2 2026** (publié 2026-08-17) : ADVANCE-1
    Gen 2026 = 159,99 € HT/mois à compter du 11/08/2026 (avant : 104,99 €). https://blog.ovhcloud.com/en/posts/dedicated-servers-pricing-update-h2-2026/ ; catalogue : https://www.ovhcloud.com/fr/bare-metal/dedicated-server-france/
12. **fiche-paie.fr — Ingénieur réseau (2026)** : médian 3 750 € brut/mois = **45 000 €/an**. https://fiche-paie.fr/metier/ingenieur-reseau
13. **URSSAF — Réduction générale des cotisations patronales** : taux employeur cumulés
    0,3981 (maladie 13,00 % + vieillesse 10,66 % + familiales 5,25 % + AT/MP 0,49 % +
    Agirc-Arrco 6,01 % + chômage 4,00 % + Fnal 0,10 % + CSA 0,30 %), réduction nulle au-delà
    de 1,6 SMIC. https://www.urssaf.fr/accueil/employeur/beneficier-exonerations/reduction-generale-cotisation.html ; simulateur : https://www.urssaf.fr/accueil/outils-documentation/simulateurs/cotisations-employeur.html
14. **Cahier des charges PPP** — B.10 Évaluation (Dimensionnement & Rigueur : 30 %,
    « Justesse des calculs, des formules et des sources » ; Finition/GitHub/TCO : 15 %,
    « coût réel calculé »).
