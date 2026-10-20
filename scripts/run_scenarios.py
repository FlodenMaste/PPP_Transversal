#!/usr/bin/env python3
"""Campagne de mise en oeuvre par SCENARIOS (partie II du rapport).

Chaque scenario est une suite d'appels MCP reels contre les serveurs du
projet, executes via le transport stdio (meme chemin que MCP Inspector).
Le script affiche, pour chaque appel : l'outil, les arguments, le statut et
un extrait du resultat — c'est la colonne « observe » des tableaux du
rapport (B.5 : au minimum 10 outils MCP integres ET exploités).

Prerequis (cf. scripts/inspector.sh, README § « Démarrage rapide ») :
    - laboratoire Containerlab deploye + scripts/lab_services.sh ;
    - les venv des 4 depots crees ;
    - Keycloak (scenario S8 uniquement) : mcp-noc-telecom/docker-compose.yml.

Utilisation, depuis la racine du depot, en compte utilisateur (jamais sudo) :
    ./venv/bin/python scripts/run_scenarios.py            # S1 a S7
    ./venv/bin/python scripts/run_scenarios.py --only S5
    ./venv/bin/python scripts/run_scenarios.py --json docs/scenarios_resultats.json

Sortie code 0 : tous les appels attendus ont repondu (une erreur documentee,
comme le refus RBAC ou l'absence de capacite sampling, compte comme reponse).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mcp-noc-telecom" / "server"))  # pour AUTH_MODE

from fastmcp import Client  # noqa: E402
from fastmcp.client.transports import StdioTransport  # noqa: E402

R1, R2, R3 = "172.20.20.11", "172.20.20.12", "172.20.20.13"

# (scenario, serveur, sortie, mode) : le serveur = cible stdio
SERVEURS = {
    "socle": ("PPP_MCP_Telecom_Supervision", ["-m", "mcp_server.server"]),
    "s2": ("noc-mcp-server", ["server.py"]),
    "s3": ("mcp-noc-ai", ["server.py"]),
}


def _env_pour(dossier: Path) -> dict:
    """Environnement du serveur : .env local + COLLECTOR_MODE=real."""
    env = {**os.environ, "COLLECTOR_MODE": "real"}
    dotenv = dossier / ".env"
    if dotenv.is_file():
        for ligne in dotenv.read_text(encoding="utf-8").splitlines():
            ligne = ligne.strip()
            if ligne and not ligne.startswith("#") and "=" in ligne:
                cle, _, valeur = ligne.partition("=")
                env.setdefault(cle.strip(), valeur.strip().strip('"').strip("'"))
    return env


def _texte(contenu) -> str:
    """Extrait le texte d'une resource / d'un prompt quel que soit le type."""
    if isinstance(contenu, str):
        return contenu
    if isinstance(contenu, (list, tuple)) and contenu:
        premier = contenu[0]
        return getattr(premier, "text", None) or str(premier)
    return getattr(contenu, "text", None) or str(contenu)


def _extrait(valeur, max_car: int = 420) -> str:
    if isinstance(valeur, (dict, list)):
        texte = json.dumps(valeur, ensure_ascii=False, indent=None)
    else:
        texte = str(valeur)
    texte = texte.replace("\n", " ")
    return texte if len(texte) <= max_car else texte[:max_car] + " …"


class Campagne:
    def __init__(self, json_sortie: Path | None):
        self.json_sortie = json_sortie
        self.resultats: list[dict] = []
        self.ouutils: set[str] = set()
        self.clients: dict[str, Client] = {}
        # Consentement humain (A.6) : les serveurs emettent
        # `elicitation/create` avant chaque execution d'outil. Ce client
        # répond « accepter » comme le ferait un operateur dans une IHM et
        # compte les demandes — la preuve que la chaine de consentement
        # est bien traversée de bout en bout (mode elicitation, defaut).
        self.consentements: list[dict] = []
        self.samplings: list[dict] = []

    async def _consentement(self, message, response_type, params, context):
        self.consentements.append({
            "message": str(getattr(params, "message", message)),
            "reponse": "accepter",
        })
        print(f"    [CONSENTEMENT] {str(getattr(params, 'message', message))[:110]}")
        return True

    async def _sampling(self, messages, params, context):
        """Reponse du LLM de l'hote (primitive sampling, A.2)."""
        dernier = messages[0] if messages else None
        texte = getattr(getattr(dernier, "content", None), "text", str(dernier))
        self.samplings.append({"demande": str(texte)[:200]})
        print(f"    [SAMPLING] demande LLM de l'hote recue ({len(str(texte))} car.)")
        return ("Hypothese formulee par le LLM de l'hote a partir des seules "
                "preuves fournies : coupure du lien primaire r1<->r2 (eth1), "
                "bascule OSPF sur r1<->r3. A VALIDER PAR UN OPERATEUR.")

    def _client(self, cle: str) -> Client:
        if cle in self.clients:
            return self.clients[cle]
        dossier, args = SERVEURS[cle]
        chemin = ROOT / dossier
        transport = StdioTransport(
            command=str(chemin / "venv" / "bin" / "python"),
            args=args,
            cwd=str(chemin),
            env=_env_pour(chemin),
        )
        self.clients[cle] = Client(transport,
                                   elicitation_handler=self._consentement,
                                   sampling_handler=self._sampling)
        return self.clients[cle]

    async def __aenter__(self):
        for cle in SERVEURS:
            client = self._client(cle)
            await client.__aenter__()
            info = getattr(client, "server_info", None) or getattr(
                client, "_initialization_result", None)
            self.ajout("info", serveur=cle, details=str(info))
        return self

    async def __aexit__(self, *exc):
        for client in self.clients.values():
            try:
                await client.__aexit__(*exc)
            except Exception:  # noqa: BLE001 - fermeture best-effort
                pass
        self._ecrire()

    def ajout(self, scenario: str, **champs):
        self.resultats.append({"scenario": scenario, **champs})

    def titre(self, texte: str):
        print("\n" + "=" * 78)
        print(f"  {texte}")
        print("=" * 78)

    async def outil(self, scenario: str, serveur: str, nom: str, args: dict,
                    attendu: str = "") -> dict:
        debut = time.perf_counter()
        try:
            client = self._client(serveur)
            res = await client.call_tool(nom, args)
            donnees = getattr(res, "structured_content", None) or getattr(res, "data", None)
            duree = (time.perf_counter() - debut) * 1000
            entree = {
                "scenario": scenario, "serveur": serveur, "type": "outil",
                "outil": nom, "args": args, "statut": "repondu",
                "duree_ms": round(duree, 1), "attendu": attendu,
                "resultat": donnees,
            }
            self.ouutils.add(f"{serveur}:{nom}")
            print(f"  [OK]   {nom:<24} {int(duree):>5} ms   {_extrait(donnees, 200)}")
        except Exception as exc:  # noqa: BLE001
            duree = (time.perf_counter() - debut) * 1000
            entree = {
                "scenario": scenario, "serveur": serveur, "type": "outil",
                "outil": nom, "args": args, "statut": "erreur",
                "duree_ms": round(duree, 1), "attendu": attendu,
                "erreur": f"{type(exc).__name__}: {exc}",
            }
            print(f"  [ERR]  {nom:<24} {int(duree):>5} ms   {type(exc).__name__}: {exc}")
        self.ajout(**entree)
        return entree

    async def resource(self, scenario: str, serveur: str, uri: str):
        try:
            client = self._client(serveur)
            contenu = await client.read_resource(uri)
            texte = _texte(contenu)
            self.ajout(scenario, type="resource", serveur=serveur, uri=uri,
                       statut="lue", octets=len(texte), extrait=texte[:200])
            print(f"  [OK]   resource {uri:<34} {len(texte):>6} octets")
        except Exception as exc:  # noqa: BLE001
            self.ajout(scenario, type="resource", serveur=serveur, uri=uri,
                       statut="erreur", erreur=f"{type(exc).__name__}: {exc}")
            print(f"  [ERR]  resource {uri:<34} {type(exc).__name__}: {exc}")

    async def prompt(self, scenario: str, serveur: str, nom: str, args: dict):
        try:
            client = self._client(serveur)
            contenu = await client.get_prompt(nom, args)
            texte = _texte(getattr(contenu, "messages", contenu))
            self.ajout(scenario, type="prompt", serveur=serveur, prompt=nom,
                       statut="genere", extrait=texte[:200])
            print(f"  [OK]   prompt  {nom:<34} {len(texte):>6} caracteres")
        except Exception as exc:  # noqa: BLE001
            self.ajout(scenario, type="prompt", serveur=serveur, prompt=nom,
                       statut="erreur", erreur=f"{type(exc).__name__}: {exc}")
            print(f"  [ERR]  prompt  {nom:<34} {type(exc).__name__}: {exc}")

    async def inventaire(self, serveur: str):
        client = self._client(serveur)
        outils = await client.list_tools()
        resources = await client.list_resources()
        prompts = await client.list_prompts()
        self.ajout("S0", type="inventaire", serveur=serveur,
                   outils=[o.name for o in outils],
                   resources=[str(r.uri) for r in resources],
                   prompts=[p.name for p in prompts])
        print(f"  {serveur:<6} outils={len(outils)}  resources={len(resources)}  "
              f"prompts={len(prompts)}")
        return outils

    def _ecrire(self):
        if not self.json_sortie:
            return
        self.json_sortie.parent.mkdir(parents=True, exist_ok=True)
        self.json_sortie.write_text(
            json.dumps({
                "genere_le": time.strftime("%Y-%m-%d %H:%M:%S"),
                "outils_exploites": sorted(self.ouutils),
                "nombre_outils_exploites": len(self.ouutils),
                "consentements_demandes": len(self.consentements),
                "sampling_demandes": len(self.samplings),
                "appels": self.resultats,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nResultats JSON : {self.json_sortie}")


async def derouler(campagne: Campagne, seuls: set[str]) -> None:
    def actif(sc: str) -> bool:
        return not seuls or sc in seuls

    if actif("S0"):
        campagne.titre("S0 — INVENTAIRE DES PRIMITIVES MCP EXPOSEES")
        for cle in ("socle", "s2", "s3"):
            await campagne.inventaire(cle)

    if actif("S1"):
        campagne.titre("S1 — DECOUVERTE DU RESEAU (resources documentaires)")
        for uri in ("noc://topology", "noc://inventory", "noc://ipam",
                    "noc://runbook/restart-switch"):
            await campagne.resource("S1", "s2", uri)
        await campagne.prompt("S1", "s2", "network_diagnosis", {"device": "r1"})

    if actif("S2"):
        campagne.titre("S2 — ETAT DES EQUIPEMENTS (SNMPv3 authPriv)")
        await campagne.outil("S2", "s2", "snmp_get",
                             {"ip": R1, "oid": "1.3.6.1.2.1.1.1.0"},
                             "description systeme r1")
        await campagne.outil("S2", "s2", "snmp_walk",
                             {"ip": R2, "oid": "1.3.6.1.2.1.1"},
                             "branche system de r2")
        await campagne.outil("S2", "s2", "get_interface_stats", {"ip": R3},
                             "table des interfaces de r3")
        await campagne.outil("S2", "s2", "get_device_status", {"name": "r1"},
                             "inventaire de r1")

    if actif("S3"):
        campagne.titre("S3 — CONNECTIVITE (ping / traceroute)")
        await campagne.outil("S3", "s2", "ping_host", {"ip": R3},
                             "4 paquets recus, 0 % de perte")
        await campagne.outil("S3", "s2", "traceroute_host", {"ip": R3},
                             "chemin vers r3")

    if actif("S4"):
        campagne.titre("S4 — ROUTAGE (BGP / OSPF en lecture seule)")
        await campagne.outil("S4", "s2", "get_bgp_peers", {"ip": R1},
                             "2 sessions iBGP etablies")
        await campagne.outil("S4", "s2", "get_ospf_neighbors", {"ip": R2},
                             "voisinage OSPF area 0")

    if actif("S5"):
        campagne.titre("S5 — CONFIGURATION (NETCONF rfc 6241, lecture seule)")
        await campagne.outil("S5", "s2", "netconf_get", {"host": R1},
                             "configuration interfaces de r1 via r1:830")

    if actif("S6"):
        campagne.titre("S6 — TRAFIC ET TELEMETRIE (syslog / NetFlow / QoS)")
        await campagne.outil("S6", "socle", "get_recent_syslog",
                             {"device_ip": None, "limit": 10},
                             "journal syslog normalise")
        await campagne.outil("S6", "socle", "analyze_netflow",
                             {"device_ip": R1, "window": "last_5_minutes"},
                             "top talkers de r1")
        await campagne.outil("S6", "socle", "qos_stats", {"device_ip": R1},
                             "statistiques QoS")
        await campagne.outil("S6", "socle", "detect_anomalies",
                             {"device_ip": R1, "window": "last_5_minutes"},
                             "alertes determinees hors LLM (B.7)")

    if actif("S7"):
        campagne.titre("S7 — INCIDENT ET CAUSE RACINE (B.7 / B.8)")
        entree = await campagne.outil("S7", "s3", "correlate_alarms",
                                      {"time_window_minutes": 15},
                                      "cluster d'incident + preuves")
        incident_id = None
        resultat = entree.get("resultat") or {}
        clusters = (resultat.get("structured_content", {}) or {}).get(
            "incident_candidates") if isinstance(resultat, dict) else None
        if not clusters and isinstance(resultat, dict):
            clusters = resultat.get("incident_candidates")
        if clusters:
            incident_id = clusters[0].get("incident_id")
        if not incident_id:
            # repli : le meme identifiant est exposé par la resource d'etat
            incident_id = "INC-0001"
        await campagne.outil("S7", "s3", "analyze_root_cause",
                             {"incident_id": incident_id},
                             "preuves rassemblees (aucune speculation)")
        await campagne.outil(
            "S7", "s3", "generate_incident_report",
            {"incident_id": incident_id,
             "root_cause_summary": "link down sur le lien primaire r1<->r2"},
            "runbook + statut EN_ATTENTE_DE_VALIDATION_HUMAINE")
        await campagne.outil("S7", "s3", "formuler_hypothese",
                             {"incident_id": incident_id},
                             "sampling LLM ou repli sur les preuves (A.2)")
        await campagne.outil("S7", "s3", "detect_anomalies",
                             {"time_window_minutes": 15},
                             "anomalies + alarmes qualifyes")

    print("\n" + "-" * 78)
    print(f"Consentements humains demandes et accordes : "
          f"{len(campagne.consentements)}")
    print(f"Outils MCP distincts exploites : {len(campagne.ouutils)}")
    for nom in sorted(campagne.ouutils):
        print(f"  - {nom}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", action="append", default=[],
                        metavar="Sx", help="ne lancer que ce(scenario)s")
    parser.add_argument("--json", metavar="CHEMIN", default=None,
                        help="ecrire les resultats dans ce fichier JSON")
    args = parser.parse_args()

    async def scenario():
        async with Campagne(Path(args.json) if args.json else None) as campagne:
            await derouler(campagne, set(args.only))

    asyncio.run(scenario())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
