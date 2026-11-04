"""S0 tests: AC-26, AC-86 (part), AC-88, AC-116, AC-118, AC-121."""

import json
import pathlib
import shutil
import socket
import ssl
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "gates"))

import g1  # noqa: E402
import g2  # noqa: E402

IGNORE = shutil.ignore_patterns(
    ".git", ".venv", ".run", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"
)


@pytest.fixture
def copy(tmp_path: pathlib.Path) -> pathlib.Path:
    dest = tmp_path / "repo"
    shutil.copytree(ROOT, dest, ignore=IGNORE)
    return dest


def test_ac26_demo_config_has_no_production() -> None:
    assert g1.check_production(ROOT) == []


def test_ac26_production_in_fixture_is_found(copy: pathlib.Path) -> None:
    f = copy / "contracts/fixtures/gpay-handler-test.json"
    f.write_text(f.read_text().replace('"TEST"', '"PRODUCTION"', 1))
    assert any("PRODUCTION" in e for e in g1.check_production(copy))


def test_ac26_handler_fixture_is_test() -> None:
    cfg = json.loads((ROOT / "contracts/fixtures/gpay-handler-test.json").read_text())
    assert cfg["config"]["environment"] == "TEST"


def test_ac86_pinned_schemas_are_draft_2020_12() -> None:
    assert g2.check_draft(ROOT) == []


def test_ac88_manifest_agrees() -> None:
    assert g2.check_hashes(ROOT) == []


def test_ac88_one_changed_byte_fails(copy: pathlib.Path) -> None:
    f = copy / "contracts/ucp-schemas/shopping/checkout.json"
    b = bytearray(f.read_bytes())
    b[-2] = ord(" ") if b[-2] != ord(" ") else ord("\t")
    f.write_bytes(bytes(b))
    errs = g2.check_hashes(copy)
    assert errs and "checkout.json" in errs[0]


def test_ac116_missing_report_fails(tmp_path: pathlib.Path) -> None:
    (tmp_path / "G1.json").write_text(json.dumps({"gate": "G1", "status": "PASS"}))
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools/gates/summary.py"), str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 1
    assert "MISSING REPORT" in (tmp_path / "summary.md").read_text()


def test_ac116_m1_is_not_run(tmp_path: pathlib.Path) -> None:
    for g in ("G1", "G2", "G3", "G4"):
        (tmp_path / f"{g}.json").write_text(json.dumps({"gate": g, "status": "PASS"}))
    subprocess.run(
        [sys.executable, str(ROOT / "tools/gates/summary.py"), str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert "| M1 (M-01 live TEST sheet) | NOT RUN |" in (tmp_path / "summary.md").read_text()


def test_ac118_pins_agree() -> None:
    assert g1.check_pins(ROOT) == []


def test_ac118_wrong_commit_fails(copy: pathlib.Path) -> None:
    (copy / "docs").mkdir(exist_ok=True)
    (copy / "docs/x.md").write_text(
        "https://github.com/Universal-Commerce-Protocol/ucp/blob/"
        "0000000000000000000000000000000000000000/README.md\n"
    )
    assert any("not the pin" in e for e in g1.check_pins(copy))


def test_ac118_latest_url_fails(copy: pathlib.Path) -> None:
    (copy / "docs").mkdir(exist_ok=True)
    (copy / "docs/y.md").write_text("https://ucp.dev/" + "latest/schemas/ucp.json\n")
    assert any("alias is not pinned" in e for e in g1.check_pins(copy))


def _handshake(port: int, version: ssl.TLSVersion) -> str:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.minimum_version = version
    ctx.maximum_version = version
    with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
        with ctx.wrap_socket(s, server_hostname="localhost") as t:
            return str(t.version())


@pytest.mark.parametrize("port", [8443, 9443])
def test_ac121_tls12_is_refused(port: int) -> None:
    with pytest.raises(ssl.SSLError):
        _handshake(port, ssl.TLSVersion.TLSv1_2)


@pytest.mark.parametrize("port", [8443, 9443])
def test_ac121_tls13_connects(port: int) -> None:
    assert _handshake(port, ssl.TLSVersion.TLSv1_3) == "TLSv1.3"
