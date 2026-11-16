"""
Tests for SciFi Dataset Manager, Default Datasets Folder, Kaggle Integration,
and Additional Providers (Hugging Face, Zenodo, Direct URL).
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scifi.cli import main as cli_main
from scifi.config import get_datasets_dir, set_global_config_value
from scifi.datasets import (
    DatasetManager,
    DatasetManifestStore,
    DirectURLDownloader,
    HuggingFaceClient,
    KaggleAuthError,
    KaggleClient,
    ZenodoClient,
    resolve_kaggle_credentials,
    safe_extract_archive,
)
from scifi.server.routers.datasets import (
    scifi_datasets_dir,
    scifi_datasets_list,
    scifi_kaggle_status,
)


def _make_zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


class _FakeResponse:
    def __init__(self, status_code: int = 200, json_data=None, content: bytes = b"", text: str = ""):
        self.status_code = status_code
        self._json = json_data
        self.content = content
        self.text = text or (json.dumps(json_data) if json_data is not None else "")

    def json(self):
        return self._json

    def iter_content(self, chunk_size: int = 8192):
        for i in range(0, len(self.content), chunk_size):
            yield self.content[i : i + chunk_size]

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


# ----------------------------------------------------------------------
# Default datasets_dir resolution
# ----------------------------------------------------------------------


def test_datasets_dir_resolution_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    global_cfg = tmp_path / "global_config.json"
    monkeypatch.setenv("SCIFI_CONFIG_PATH", str(global_cfg))
    monkeypatch.delenv("SCIFI_DATASETS_DIR", raising=False)

    # 1. Global config
    global_ds = tmp_path / "global_datasets"
    set_global_config_value("datasets_dir", str(global_ds), config_path=global_cfg)
    assert get_datasets_dir(workspace_dir=tmp_path, global_config_path=global_cfg) == global_ds.resolve()

    # 2. Env var overrides global config
    env_ds = tmp_path / "env_datasets"
    monkeypatch.setenv("SCIFI_DATASETS_DIR", str(env_ds))
    assert get_datasets_dir(workspace_dir=tmp_path, global_config_path=global_cfg) == env_ds.resolve()

    # 3. scifi.toml [datasets] dir overrides env var
    toml_ds = tmp_path / "project_datasets"
    (tmp_path / "scifi.toml").write_text(f'[datasets]\ndir = "{toml_ds.as_posix()}"\n', encoding="utf-8")
    assert get_datasets_dir(workspace_dir=tmp_path, global_config_path=global_cfg) == toml_ds.resolve()

    # 4. Explicit override wins over everything
    explicit_ds = tmp_path / "explicit_datasets"
    assert (
        get_datasets_dir(workspace_dir=tmp_path, override=explicit_ds, global_config_path=global_cfg)
        == explicit_ds.resolve()
    )


# ----------------------------------------------------------------------
# Manifest Store & Safe Extraction
# ----------------------------------------------------------------------


def test_safe_extract_archive_blocks_zip_slip(tmp_path: Path):
    bad_zip = tmp_path / "evil.zip"
    bad_zip.write_bytes(_make_zip_bytes({"../evil.txt": b"boom"}))
    with pytest.raises(ValueError, match="Unsafe archive member path"):
        safe_extract_archive(bad_zip, tmp_path / "out")


def test_manifest_store_lifecycle(tmp_path: Path):
    ds_root = tmp_path / "datasets"
    data_dir = ds_root / "kaggle" / "owner__iris"
    data_dir.mkdir(parents=True)
    (data_dir / "iris.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    store = DatasetManifestStore(ds_root)
    rec = store.register("kaggle", "owner/iris", data_dir, title="Iris")
    assert rec.provider == "kaggle"
    assert rec.files == ["iris.csv"]
    assert rec.total_bytes > 0

    listed = store.list_local()
    assert len(listed) == 1
    assert listed[0].identifier == "owner/iris"

    assert store.remove("owner/iris", delete_files=True) is True
    assert store.list_local() == []
    assert not data_dir.exists()


# ----------------------------------------------------------------------
# Kaggle Credentials & Client
# ----------------------------------------------------------------------


def test_kaggle_credential_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    monkeypatch.delenv("KAGGLE_USERNAME", raising=False)
    monkeypatch.delenv("KAGGLE_KEY", raising=False)

    # 1. kaggle.json
    kdir = tmp_path / ".kaggle"
    kdir.mkdir()
    (kdir / "kaggle.json").write_text(json.dumps({"username": "alice", "key": "secret123"}), encoding="utf-8")
    monkeypatch.setenv("KAGGLE_CONFIG_DIR", str(kdir))
    creds = resolve_kaggle_credentials(workspace_dir=tmp_path)
    assert creds["mode"] == "basic"
    assert creds["username"] == "alice"

    # 2. Env token overrides kaggle.json
    monkeypatch.setenv("KAGGLE_API_TOKEN", "tok_xyz")
    creds2 = resolve_kaggle_credentials(workspace_dir=tmp_path)
    assert creds2["mode"] == "bearer"
    assert creds2["token"] == "tok_xyz"


def test_kaggle_client_requires_auth_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    monkeypatch.delenv("KAGGLE_USERNAME", raising=False)
    monkeypatch.delenv("KAGGLE_KEY", raising=False)
    monkeypatch.setenv("KAGGLE_CONFIG_DIR", str(tmp_path / "no_kaggle"))
    monkeypatch.setenv("SCIFI_CONFIG_PATH", str(tmp_path / "no_cfg.json"))

    client = KaggleClient(workspace_dir=tmp_path)
    assert client.is_authenticated is False
    with pytest.raises(KaggleAuthError):
        client.search_datasets("titanic")


def test_kaggle_datasets_competitions_and_kernels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SCIFI_DATASETS_DIR", str(tmp_path / "ds"))
    session = MagicMock()
    zip_bytes = _make_zip_bytes({"train.csv": b"id,y\n1,0\n"})

    def fake_request(method, url, **kwargs):
        if url.endswith("/datasets/list"):
            return _FakeResponse(
                200,
                json_data=[{"ref": "uciml/iris", "title": "Iris Species", "totalBytes": 1024, "downloadCount": 500}],
            )
        if url.endswith("/datasets/download/uciml/iris"):
            return _FakeResponse(200, content=zip_bytes)
        if url.endswith("/competitions/list"):
            return _FakeResponse(200, json_data=[{"ref": "titanic", "title": "Titanic", "reward": "Knowledge"}])
        if url.endswith("/competitions/data/download-all/titanic"):
            return _FakeResponse(200, content=zip_bytes)
        if url.endswith("/competitions/submissions/url/10/1") or "/competitions/submissions/url/" in url:
            return _FakeResponse(200, json_data={"createUrl": "https://upload.example/blob", "token": "blob_tok"})
        if url.endswith("/competitions/submissions/submit/titanic"):
            return _FakeResponse(200, json_data={"message": "Successfully submitted to Titanic"})
        if url.endswith("/kernels/pull"):
            return _FakeResponse(
                200,
                json_data={
                    "blob": {"source": "print('hello kaggle')\n", "language": "python", "kernelType": "script"},
                    "metadata": {"title": "Hello Kernel", "language": "python", "kernelType": "script"},
                },
            )
        if url.endswith("/kernels/push"):
            return _FakeResponse(200, json_data={"ref": "alice/hello-kernel", "versionNumber": 1})
        if url.endswith("/kernels/status"):
            return _FakeResponse(200, json_data={"status": "complete"})
        if url.endswith("/kernels/output"):
            return _FakeResponse(200, json_data={"log": "Done!", "files": []})
        return _FakeResponse(200, json_data={})

    session.request.side_effect = fake_request
    session.put.return_value = _FakeResponse(200)

    client = KaggleClient(username="alice", key="k123", workspace_dir=tmp_path, session=session)

    # Datasets
    ds = client.search_datasets("iris")
    assert len(ds) == 1 and ds[0].identifier == "uciml/iris"
    dl = client.download_dataset("uciml/iris")
    assert "train.csv" in dl.files
    assert Path(dl.local_path).parent.parent == (tmp_path / "ds").resolve()

    # Competitions
    comps = client.list_competitions(search="titanic")
    assert len(comps) == 1 and comps[0].ref == "titanic"
    comp_dl = client.download_competition("titanic")
    assert "train.csv" in comp_dl.files

    sub_file = tmp_path / "sub.csv"
    sub_file.write_text("id,y\n1,1\n", encoding="utf-8")
    sub_res = client.submit_competition("titanic", sub_file, message="test")
    assert "Successfully submitted" in sub_res["message"]

    # Kernels
    pulled = client.pull_kernel("alice/hello-kernel")
    assert Path(pulled["metadata_file"]).is_file()
    pushed = client.push_kernel(pulled["local_dir"])
    assert pushed["versionNumber"] == 1
    assert client.kernel_status("alice/hello-kernel")["status"] == "complete"
    out = client.kernel_output("alice/hello-kernel")
    assert "kernel.log" in out["files"]


# ----------------------------------------------------------------------
# Other Providers & Unified DatasetManager
# ----------------------------------------------------------------------


def test_huggingface_zenodo_url_and_manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SCIFI_DATASETS_DIR", str(tmp_path / "ds_home"))
    session = MagicMock()

    def fake_get(url, **kwargs):
        if "huggingface.co/api/datasets/imdb/tree" in url:
            return _FakeResponse(200, json_data=[{"type": "file", "path": "data.csv", "size": 12}])
        if "huggingface.co/api/datasets" in url:
            return _FakeResponse(200, json_data=[{"id": "imdb", "downloads": 1000, "likes": 50}])
        if "huggingface.co/datasets/imdb/resolve/" in url:
            return _FakeResponse(200, content=b"text,label\nhi,1\n")
        if "zenodo.org/api/records/12345" in url:
            return _FakeResponse(
                200,
                json_data={
                    "id": 12345,
                    "metadata": {"title": "Physics Dataset"},
                    "files": [{"key": "obs.csv", "size": 9, "links": {"self": "https://zenodo.org/files/obs.csv"}}],
                },
            )
        if "zenodo.org/files/obs.csv" in url:
            return _FakeResponse(200, content=b"x,y\n1,2\n")
        if "example.org/sample.zip" in url:
            return _FakeResponse(200, content=_make_zip_bytes({"sample.txt": b"ok"}))
        return _FakeResponse(200, json_data={})

    session.get.side_effect = fake_get

    mgr = DatasetManager(datasets_dir=tmp_path / "ds_home")
    mgr.huggingface = HuggingFaceClient(workspace_dir=tmp_path, session=session)
    mgr.zenodo = ZenodoClient(workspace_dir=tmp_path, session=session)
    mgr.url_downloader = DirectURLDownloader(workspace_dir=tmp_path, session=session)

    hf_res = mgr.download("hf", "imdb")
    assert hf_res.provider == "huggingface"
    assert "data.csv" in hf_res.files

    zen_res = mgr.download("zenodo", "10.5281/zenodo.12345")
    assert zen_res.provider == "zenodo"
    assert "obs.csv" in zen_res.files

    url_res = mgr.download("auto", "https://example.org/sample.zip")
    assert url_res.provider == "url"
    assert "sample.txt" in url_res.files

    local = mgr.list_local()
    assert len(local) == 3


# ----------------------------------------------------------------------
# CLI & MCP Tools
# ----------------------------------------------------------------------


def test_cli_and_mcp_datasets_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    cfg_path = tmp_path / "cfg.json"
    monkeypatch.setenv("SCIFI_CONFIG_PATH", str(cfg_path))
    monkeypatch.delenv("SCIFI_DATASETS_DIR", raising=False)

    target = tmp_path / "my_datasets"
    rc = cli_main(["datasets", "dir", "--set", str(target)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Default datasets directory set to" in out

    mcp_dir = scifi_datasets_dir()
    assert Path(mcp_dir["datasets_dir"]) == target.resolve()

    mcp_list = scifi_datasets_list()
    assert mcp_list["count"] == 0

    kg_st = scifi_kaggle_status()
    assert "authenticated" in kg_st
    assert Path(kg_st["default_datasets_dir"]) == target.resolve()


def test_kaggle_downloads_auto_recovery_and_login(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake_home = tmp_path / "home"
    (fake_home / "Downloads").mkdir(parents=True)
    (fake_home / "Downloads" / "kaggle.json").write_text(
        json.dumps({"username": "bob", "key": "bob_key_99"}), encoding="utf-8"
    )
    monkeypatch.delenv("KAGGLE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    monkeypatch.delenv("KAGGLE_USERNAME", raising=False)
    monkeypatch.delenv("KAGGLE_KEY", raising=False)
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    creds = resolve_kaggle_credentials(workspace_dir=tmp_path)
    assert creds["mode"] == "basic"
    assert creds["username"] == "bob"
    assert str(creds["source"]).startswith("recovered_from_downloads:")
    assert (fake_home / ".kaggle" / "kaggle.json").is_file()

    # Test sf kaggle login --from-file --no-verify
    src_json = tmp_path / "new_kaggle.json"
    src_json.write_text(json.dumps({"username": "carol", "key": "carol_key"}), encoding="utf-8")
    rc = cli_main(["kaggle", "login", "--from-file", str(src_json), "--no-verify"])
    assert rc == 0
    saved = json.loads((fake_home / ".kaggle" / "kaggle.json").read_text(encoding="utf-8"))
    assert saved["username"] == "carol"


def test_http_retry_and_part_cleanup(tmp_path: Path):
    from scifi.datasets.http import request_with_retry, stream_to_file

    session = MagicMock()
    session.request.side_effect = [
        _FakeResponse(429, text="rate limited"),
        _FakeResponse(200, json_data={"ok": True}),
    ]
    resp = request_with_retry(session, "GET", "https://example.org/api", backoff_base=0.001)
    assert resp.status_code == 200
    assert session.request.call_count == 2

    # Failing stream cleans up .part file
    bad_resp = MagicMock()

    def _boom(**kwargs):
        yield b"partial"
        raise RuntimeError("network drop")

    bad_resp.iter_content.side_effect = _boom
    target = tmp_path / "out.bin"
    with pytest.raises(RuntimeError, match="network drop"):
        stream_to_file(bad_resp, target)
    assert not target.exists()
    assert not (tmp_path / "out.bin.part").exists()


def test_doctor_env_includes_datasets_and_kaggle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from scifi.env import diagnose_environment

    ds_dir = tmp_path / "doctor_ds"
    monkeypatch.setenv("SCIFI_DATASETS_DIR", str(ds_dir))
    diag = diagnose_environment(auto_fix=True)
    assert diag["datasets"]["default_dir"] == str(ds_dir.resolve())
    assert diag["datasets"]["exists"] is True
    assert "kaggle" in diag
    assert diag["kaggle"]["status"] in ("HEALTHY", "MISSING_CREDENTIALS")


# ----------------------------------------------------------------------
# Token-Efficient Dataset Inspection & Bounded Outputs
# ----------------------------------------------------------------------


def test_inspect_csv_bounds_rows_columns_and_long_cells(tmp_path: Path):
    from scifi.datasets import inspect_dataset

    csv_path = tmp_path / "train.csv"
    long_text = "x" * 500
    rows = ["id,score,notes,empty_col"]
    for i in range(100):
        rows.append(f"{i},{i * 0.5},{long_text},")
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    info = inspect_dataset(csv_path, max_rows=3, max_chars=40, max_columns=3)
    assert info["kind"] == "file"
    assert info["format"] == "csv"
    assert info["row_count"] == 100
    assert info["row_count_estimated"] is False
    assert info["column_count"] == 4
    assert info["omitted_columns"] == 1
    assert len(info["columns"]) == 3
    assert info["columns"][0]["type"] == "int"
    assert info["columns"][1]["type"] == "float"
    assert len(info["sample_rows"]) == 3
    assert len(info["sample_rows"][0]["notes"]) < 70
    assert "[500 chars]" in info["sample_rows"][0]["notes"]


def test_inspect_jsonl_json_and_large_json_skip(tmp_path: Path):
    from scifi.datasets import inspect_dataset

    jsonl_path = tmp_path / "samples.jsonl"
    records = [json.dumps({"id": i, "tags": list(range(20)), "text": "y" * 200}) for i in range(25)]
    jsonl_path.write_text("\n".join(records) + "\n", encoding="utf-8")

    jl_info = inspect_dataset(jsonl_path, max_rows=2, max_chars=30)
    assert jl_info["format"] == "jsonl"
    assert jl_info["row_count"] == 25
    assert len(jl_info["sample_rows"]) == 2
    assert "... [+15 more]" in jl_info["sample_rows"][0]["tags"]

    big_json = tmp_path / "huge.json"
    big_json.write_bytes(b'{"data": [' + b'"abcdefghij",' * 220_000 + b'"end"]}')
    bj_info = inspect_dataset(big_json)
    assert bj_info["format"] == "json"
    assert bj_info["large_file_skipped_full_parse"] is True
    assert "prefix_preview" in bj_info


def test_inspect_sqlite_and_directory_with_many_files(tmp_path: Path):
    import sqlite3

    from scifi.datasets import inspect_dataset

    db_path = tmp_path / "exp.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE runs (id INTEGER, loss REAL, note TEXT)")
    for i in range(15):
        conn.execute("INSERT INTO runs VALUES (?, ?, ?)", (i, 0.1 * i, "z" * 150))
    conn.commit()
    conn.close()

    db_info = inspect_dataset(db_path, max_rows=2, max_chars=30)
    assert db_info["format"] == "sqlite"
    assert db_info["table_count"] == 1
    assert db_info["tables"][0]["row_count"] == 15
    assert len(db_info["tables"][0]["sample_rows"]) == 2
    assert "[150 chars]" in db_info["tables"][0]["sample_rows"][0]["note"]

    ds_dir = tmp_path / "img_dataset"
    (ds_dir / "images").mkdir(parents=True)
    for i in range(30):
        (ds_dir / "images" / f"img_{i:03d}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (ds_dir / "labels.csv").write_text("file,label\nimg_000.png,cat\nimg_001.png,dog\n", encoding="utf-8")

    dir_info = inspect_dataset(ds_dir, max_files=5, max_rows=2)
    assert dir_info["kind"] == "directory"
    assert dir_info["total_files"] == 31
    assert len(dir_info["files_preview"]) == 5
    assert dir_info["omitted_files"] == 26
    assert dir_info["primary_file"] == "labels.csv"
    assert dir_info["primary_file_inspection"]["row_count"] == 2


def test_mcp_list_search_and_cli_inspect_are_token_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    from scifi.datasets import DatasetInfo
    from scifi.server.routers.datasets import scifi_datasets_inspect, scifi_datasets_search

    ds_root = tmp_path / "datasets"
    data_dir = ds_root / "kaggle" / "owner__manyfiles"
    data_dir.mkdir(parents=True)
    for i in range(25):
        (data_dir / f"part_{i:02d}.txt").write_text(f"row {i}\n", encoding="utf-8")
    (data_dir / "main.csv").write_text("a,b\n1,2\n3,4\n", encoding="utf-8")

    store = DatasetManifestStore(ds_root)
    store.register("kaggle", "owner/manyfiles", data_dir, title="Many Files")

    monkeypatch.setenv("SCIFI_DATASETS_DIR", str(ds_root))
    listed = scifi_datasets_list(max_files=5)
    assert listed["count"] == 1
    entry = listed["datasets"][0]
    assert entry["file_count"] == 26
    assert len(entry["files_preview"]) == 5
    assert entry["omitted_files"] == 21
    assert "files" not in entry

    # Inspect by tracked identifier via MCP tool
    inspected = scifi_datasets_inspect("owner/manyfiles", max_files=5, max_rows=2)
    assert inspected["kind"] == "directory"
    assert inspected["primary_file"] == "main.csv"
    assert inspected["primary_file_inspection"]["row_count"] == 2

    # Inspect via CLI --json
    rc = cli_main(["datasets", "inspect", "owner/manyfiles", "--max-files", "5", "--json"])
    assert rc == 0
    cli_out = json.loads(capsys.readouterr().out)
    assert cli_out["total_files"] == 26
    assert len(cli_out["files_preview"]) == 5

    # Search truncates long descriptions
    monkeypatch.setattr(
        DatasetManager,
        "search",
        lambda self, query, provider="all", limit=15: {
            "query": query,
            "provider": provider,
            "count": 1,
            "results": [
                DatasetInfo(
                    provider="kaggle",
                    identifier="owner/long",
                    title="Long Desc",
                    description="D" * 1000,
                ).to_dict()
            ],
            "errors": {},
        },
    )
    search_res = scifi_datasets_search("long")
    assert len(search_res["results"][0]["description"]) < 270
    assert "[1000 chars]" in search_res["results"][0]["description"]
