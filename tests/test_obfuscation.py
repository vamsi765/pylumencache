"""The capture tool must not leak real ids, free text, MACs or the Prefix Topic."""
import pytest
from conftest import load_tool

pytest.importorskip("paho.mqtt.client")
Obfuscator = load_tool("lumencache_capture").Obfuscator

PREFIX = "platform:na/example/abc123"


@pytest.fixture
def obf():
    return Obfuscator(PREFIX)


def test_hsn_and_sys_get_stable_fakes(obf):
    a = obf.payload({"hsn": "REAL-1", "sys": "SYS-REAL"})
    b = obf.payload({"hsn": "REAL-1"})
    assert a == {"hsn": "HSN0001", "sys": "SYS0001"}
    assert b == {"hsn": "HSN0001"}


def test_different_values_get_different_fakes(obf):
    out = obf.payload([{"hsn": "A"}, {"hsn": "B"}])
    assert [m["hsn"] for m in out] == ["HSN0001", "HSN0002"]


def test_socket_suffix_is_kept_and_shares_the_pdm_fake(obf):
    out = obf.payload([{"hsn": "PDM-1"}, {"hsn": "PDM-1_S3"}])
    assert [m["hsn"] for m in out] == ["HSN0001", "HSN0001_S3"]


def test_real_id_inside_free_text_is_replaced(obf):
    obf.payload({"hsn": "PDM-1"})
    assert obf.payload("seen PDM-1 on the bus") == "seen HSN0001 on the bus"


def test_meta_free_text_is_blanked_but_device_names_stay(obf):
    msg = {"sys_info": {"name": "Smith House", "phone": "555-0100", "note": ""},
           "devs": {"name": "Kitchen"}}
    out = obf.payload({"meta": msg})["meta"]
    assert out["sys_info"] == {"name": "", "phone": "", "note": ""}
    assert out["devs"] == {"name": "Kitchen"}


def test_free_text_outside_meta_is_untouched(obf):
    assert obf.payload({"sys_info": {"name": "Keep"}}) == {"sys_info": {"name": "Keep"}}


@pytest.mark.parametrize("mac", ["AA:BB:CC:DD:EE:FF", "aa-bb-cc-dd-ee-ff"])
def test_mac_addresses_are_masked(obf, mac):
    out = obf.payload({"note": f"adapter {mac} up"})
    assert mac.lower() not in str(out).lower()
    assert "02:00:00:00:00:01" in out["note"]


def test_same_mac_gets_the_same_mask(obf):
    a = obf.payload("AA:BB:CC:DD:EE:FF")
    b = obf.payload("aa:bb:cc:dd:ee:ff")
    assert a == b


def test_prefix_is_replaced_in_text(obf):
    assert obf.payload(f"{PREFIX}/status") == "<prefix>/status"


def test_non_string_values_pass_through(obf):
    assert obf.payload({"e": 57, "bri": 50.5, "on": [1, None, True]}) == {"e": 57, "bri": 50.5, "on": [1, None, True]}
