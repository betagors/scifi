# tests/test_env.py
from scifi.env import auto_detect_zotero_dir, diagnose_environment, ensure_uv


def test_auto_detect_zotero_dir_default(monkeypatch, tmp_path):
    fake_zotero = tmp_path / "Zotero"
    fake_zotero.mkdir()
    (fake_zotero / "zotero.sqlite").touch()
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    detected = auto_detect_zotero_dir()
    assert detected == fake_zotero


def test_auto_detect_zotero_dir_missing(monkeypatch, tmp_path):
    empty_home = tmp_path / "empty_home"
    empty_home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(empty_home))
    monkeypatch.setenv("HOME", str(empty_home))
    detected = auto_detect_zotero_dir()
    # If not in default location, should return None
    assert detected is None


def test_ensure_uv():
    uv_info = ensure_uv()
    assert isinstance(uv_info, dict)
    assert "available" in uv_info
    assert "executable" in uv_info


def test_diagnose_environment_health():
    diag = diagnose_environment(auto_fix=False)
    assert "python" in diag
    assert "zotero" in diag
    assert "uv" in diag
    assert "latex" in diag
    assert diag["python"]["version"] is not None
