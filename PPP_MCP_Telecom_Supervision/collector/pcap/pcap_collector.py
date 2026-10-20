"""
Collecteur PCAP - outil MCP cible : capture_pcap.

Contrainte de sécurité du cahier des charges : la capture doit
être strictement bridée en durée et en volume, pour éviter la
capture accidentelle de données sensibles et l'engorgement du
réseau. Les plafonds PCAP_MAX_DURATION_SECONDS et
PCAP_MAX_PACKETS (config.py) ne sont jamais dépassés, même si
l'appelant en demande plus.

Pré-requis pour le mode réel :
    tshark installé sur la machine (paquet wireshark-common /
    tshark), et droits suffisants pour capturer (cap_net_raw ou
    root selon l'OS).

La capture n'est jamais lancée à l'aveugle : l'identifiant
d'équipement est d'abord résolu en conteneur du lab, l'interface
demandée est vérifiée dans ce conteneur, puis traduite en
l'interface côté hôte qui lui fait face. Chaque étape échoue avec
un message explicite plutôt qu'avec une trace tshark.
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from collector import config
from collector.common.schema import make_error_response, make_response
from collector.common.utils import (
    fixtures_dir,
    load_json_fixture,
    logger,
    resolve_device_key,
    unknown_device_message,
)

FIXTURES = fixtures_dir(__file__)

_CLAB_TOPOLOGY_CACHE: dict[str, Any] | None = None


def _clamp(value: int, maximum: int) -> int:
    return min(value, maximum)


# Garde empruntee a la version B : empeche toute injection de sequence
# (« ../ ») dans le nom du fichier de capture (B.6).
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")


def _capture_output_file(node: str, interface: str) -> str:
    """Construit le chemin du fichier de capture en eliminant toute
    injection de sequence qui permettrait d'ecrire hors de PCAP_OUTPUT_DIR."""
    for label, value in (("device", node), ("interface", interface)):
        if not value or not _SAFE_NAME.match(value):
            raise ValueError(
                f"Nom de capture invalide ({label}={value!r}) : "
                "seuls [A-Za-z0-9_.:-] sont admis, sans '..'"
            )

    base = Path(config.PCAP_OUTPUT_DIR).resolve()
    base.mkdir(parents=True, exist_ok=True)
    target = (base / f"{node}_{interface}.pcap").resolve()
    if target.parent != base:
        raise ValueError(f"Chemin de capture hors de {base}")
    return str(target)


def _clab_topology() -> dict[str, Any]:
    """topology-data.json du lab Containerlab (statique, mis en cache).

    Sert uniquement à obtenir le nom du lab, dont dépend le nom des
    conteneurs : clab-<lab>-<noeud>. Renvoie un dictionnaire vide si le
    fichier est absent ou illisible : la résolution échouera alors avec un
    message explicite plutôt que de lancer une capture au hasard.
    """
    global _CLAB_TOPOLOGY_CACHE
    if _CLAB_TOPOLOGY_CACHE is None:
        root = Path(__file__).resolve().parents[2] / "lab" / "containerlab"
        data: dict[str, Any] = {}

        # 1) artefact genere par containerlab au deploiement
        matches = sorted(root.glob("*/topology-data.json"))
        if matches:
            try:
                data = json.loads(matches[0].read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("topologie containerlab illisible (%s)", exc)

        # 2) repli : topology.clab.yml statique. L'artefact ci-dessus n'existe
        #    que pour le lab actuellement deploye (dans l'arbre qui a servi a le
        #    lancer) ; sans lui, la lecture d'un arbre vierge echouerait a tort.
        if not data.get("name"):
            yaml_path = root / "topology.clab.yml"
            if yaml_path.is_file():
                try:
                    import yaml

                    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
                except Exception as exc:  # noqa: BLE001
                    logger.warning("topology.clab.yml illisible (%s)", exc)

        _CLAB_TOPOLOGY_CACHE = data
    return _CLAB_TOPOLOGY_CACHE


def _container_for(device_ip: str) -> tuple[str, str]:
    """Nom du conteneur et du noeud de lab pour une IP de gestion donnée.

    Le préfixe vient du nom du lab lu dans topology-data.json ; on ne le
    durcit pas dans le code.
    """
    node = resolve_device_key(device_ip).lower()
    lab = _clab_topology().get("name")
    if not lab:
        raise ValueError(
            "topologie containerlab introuvable : impossible de rattacher "
            f"{device_ip} a un conteneur, capture annulee"
        )
    return f"clab-{lab}-{node}", node


def _docker(container: str, argv: list[str]) -> str:
    """Exécute `docker exec <container> ...` et renvoie stdout (stripé).

    Tout échec (conteneur absent/arrêté, commande refusée) lève ValueError
    avec la sortie docker : c'est une erreur de cadrage, à restituer telle
    quelle, et non un échec de tshark à décrire comme tel.
    """
    result = subprocess.run(
        ["docker", "exec", container, *argv],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        raise ValueError(
            f"docker exec {container} a echoue : "
            f"{detail[0] if detail else 'aucune sortie'}"
        )
    return result.stdout.strip()


def _resolve_host_iface(container: str, interface: str) -> str:
    """Interface côté hôte qui fait face à `interface` dans le conteneur.

    L'endroit exact d'où il faut capturer : le peer veth côté hôte. Sans
    cette traduction, on capture sur une interface de l'hôte qui n'a aucun
    rapport avec l'équipement ciblé (c'est le cas du défaut "eth0", qui
    n'existe pas sur l'hôte).
    """
    known = set(_docker(container, ["ls", "/sys/class/net/"]).split())
    if interface not in known:
        available = ", ".join(sorted(known - {"lo"})) or "aucune"
        raise ValueError(
            f"interface {interface!r} inexistante sur {container} "
            f"(disponibles : {available})"
        )

    iflink = _docker(container, ["cat", f"/sys/class/net/{interface}/iflink"])
    if not iflink.isdigit():
        raise ValueError(f"pair hote de {interface} indeterminable (iflink={iflink!r})")

    for entry in sorted(Path("/sys/class/net").iterdir()):
        try:
            if (entry / "ifindex").read_text().strip() == iflink:
                return entry.name
        except OSError:
            continue

    # Les interfaces de lien (eth1..eth3) sont reliées directement a un
    # autre conteneur : leur pair ne vit pas dans l'espace de noms de
    # l'hote, aucune capture hote n'est donc possible dessus.
    raise ValueError(
        f"aucun pair cote hote pour {interface} de {container} : seules les "
        "interfaces reliées au réseau de gestion sont capturables depuis "
        "l'hôte (essayez eth0)"
    )


def _capture_error(device_ip: str, stderr: str, simulated: bool) -> dict[str, Any]:
    """Traduit l'échec de tshark en message exploitable.

    Trois causes distinctes, qu'il ne faut pas confondre : le droit de
    capture manquant sur dumpcap, le répertoire de sortie non inscriptible,
    et tout le reste. Sans ce filtre, l'appelant ne reçoit qu'une trace
    brute — ou pire, un remède qui ne traite pas la cause réelle.
    """
    lowered = stderr.lower()

    # 1. Droit de capture : seuls les marqueurs propres à dumpcap comptent.
    #    "Permission denied" tout seul ne suffit pas : il survient aussi
    #    quand c'est le fichier de sortie qui n'est pas inscriptible.
    if any(marker in lowered for marker in ("dumpcap", "cap_net_raw", "cap_net_admin", "capture privileges")):
        return make_error_response(
            "pcap",
            device_ip,
            "droit de capture absent : dumpcap n'a pas CAP_NET_RAW "
            "(sudo setcap cap_net_raw,cap_net_admin=ep /usr/bin/dumpcap)",
            simulated=simulated,
        )

    # 2. Sortie non inscriptible : PCAP_OUTPUT_DIR existe mais n'appartient
    #    pas à l'utilisateur qui lance le serveur.
    if "could not be opened" in lowered or ("permission denied" in lowered and config.PCAP_OUTPUT_DIR.lower() in lowered):
        return make_error_response(
            "pcap",
            device_ip,
            f"repertoire de sortie non inscriptible : {config.PCAP_OUTPUT_DIR} "
            "(verifier ses droits ou PCAP_OUTPUT_DIR)",
            simulated=simulated,
        )

    return make_error_response("pcap", device_ip, f"tshark error: {stderr}", simulated=simulated)


def _real_capture_pcap(device_ip: str, interface: str, duration_seconds: int, max_packets: int, capture_filter: str | None) -> dict[str, Any]:
    """Lance une capture tshark bridée en durée et en nombre de paquets.

    Toute erreur de cadrage (équipement inconnu, interface absente, pair
    hôte introuvable, droits insuffisants) est levée avec un message
    explicite et interceptée par capture_pcap().
    """
    container, node = _container_for(device_ip)
    host_iface = _resolve_host_iface(container, interface)

    output_file = _capture_output_file(node, interface)

    cmd = [
        "tshark",
        "-i", host_iface,
        "-a", f"duration:{duration_seconds}",
        "-c", str(max_packets),
        "-w", output_file,
    ]
    if capture_filter:
        cmd.extend(["-f", capture_filter])

    run = subprocess.run(cmd, capture_output=True, text=True, timeout=duration_seconds + 15, check=False)
    if run.returncode != 0:
        raise RuntimeError(run.stderr.strip() or f"tshark exit {run.returncode}")

    # Résumé rapide via tshark -r (comptage par protocole)
    summary = subprocess.run(
        ["tshark", "-r", output_file, "-q", "-z", "io,phs"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if summary.returncode != 0:
        raise RuntimeError(summary.stderr.strip() or "lecture du fichier pcap impossible")

    return {
        "device": node,
        "interface": interface,
        "host_interface": host_iface,
        "duration_seconds": duration_seconds,
        "max_packets": max_packets,
        "file_path": output_file,
        "protocol_summary_raw": summary.stdout,
    }


def capture_pcap(
    device_ip: str,
    interface: str = "eth0",
    duration_seconds: int = 10,
    max_packets: int = 200,
    capture_filter: str | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    """Capture un échantillon de trafic, borné en durée et en volume.

    Les valeurs demandées sont systématiquement plafonnées par
    PCAP_MAX_DURATION_SECONDS et PCAP_MAX_PACKETS - un appelant
    ne peut jamais dépasser ces limites, même en le demandant
    explicitement.
    """
    simulated = config.is_simulated(mode)

    safe_duration = _clamp(duration_seconds, config.PCAP_MAX_DURATION_SECONDS)
    safe_packets = _clamp(max_packets, config.PCAP_MAX_PACKETS)

    try:
        # Garde B.6 : valide les noms avant toute resolution. Sans elle,
        # un nom malveillant descend jusqu'a docker/tshark et ressort en
        # « docker exec a echoue », alors que le motif reel est un nom
        # de capture invalide.
        for label, value in (("device", device_ip), ("interface", interface)):
            if not value or not _SAFE_NAME.match(value):
                raise ValueError(
                    f"Nom de capture invalide ({label}={value!r}) : "
                    "seuls [A-Za-z0-9_.:-] sont admis, sans '..'"
                )

        if simulated:
            table = load_json_fixture(FIXTURES / "capture_summary.json")
            device_data = table.get(resolve_device_key(device_ip))
            if device_data is None:
                return make_error_response(
                    "pcap", device_ip,
                    unknown_device_message(device_ip, "de capture (tshark)"),
                    simulated=True,
                )
            return make_response("pcap", device_ip, device_data, simulated=True)

        data = _real_capture_pcap(device_ip, interface, safe_duration, safe_packets, capture_filter)
        return make_response("pcap", device_ip, data, simulated=False)

    except ValueError as exc:
        # Cadrage invalide : équipement inconnu, interface absente du
        # conteneur, ou interface sans pair côté hôte. Message tel quel.
        logger.error("capture_pcap refused for %s: %s", device_ip, exc)
        return make_error_response("pcap", device_ip, str(exc), simulated=simulated)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        # Échec de tshark lui-même (droits insuffisants, binaire absent...).
        detail = getattr(exc, "stderr", None) or str(exc)
        logger.error("capture_pcap failed for %s: %s", device_ip, detail)
        return _capture_error(device_ip, str(detail), simulated)
    except Exception as exc:  # noqa: BLE001
        logger.error("capture_pcap failed for %s: %s", device_ip, exc)
        return make_error_response("pcap", device_ip, str(exc), simulated=simulated)
