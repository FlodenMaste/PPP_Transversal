from collector import config
from collector.common.schema import validate_response
from collector.pcap.pcap_collector import _clamp, capture_pcap


def test_capture_pcap_simulated_ok():
    response = capture_pcap("R1", mode="simulated")
    assert validate_response(response)
    assert response["data"]["packet_count"] == 342


def test_clamp_never_exceeds_configured_max():
    assert _clamp(9999, config.PCAP_MAX_DURATION_SECONDS) == config.PCAP_MAX_DURATION_SECONDS
    assert _clamp(1, config.PCAP_MAX_DURATION_SECONDS) == 1


def test_capture_pcap_rejet_sequence_traversale():
    """B.6 : aucun chemin de capture ne peut sortir de PCAP_OUTPUT_DIR."""
    response = capture_pcap("../../etc/cron.d/evil", mode="real")
    assert response["status"] == "error"
    assert "invalide" in response["error"]


def test_capture_pcap_rejet_interface_malveillante():
    response = capture_pcap("172.20.20.11", interface="../eth0", mode="real")
    assert response["status"] == "error"
    assert "invalide" in response["error"]


def test_capture_output_file_dans_le_repertoire_autorise(tmp_path, monkeypatch):
    from collector.pcap import pcap_collector

    monkeypatch.setattr(config, "PCAP_OUTPUT_DIR", str(tmp_path))
    chemin = pcap_collector._capture_output_file("172.20.20.11", "eth0")
    assert chemin.startswith(str(tmp_path.resolve()))
    assert chemin.endswith("172.20.20.11_eth0.pcap")
