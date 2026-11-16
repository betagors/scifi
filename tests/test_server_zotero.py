# tests/test_server_zotero.py
from scifi.server import (
    scifi_zotero_push_audit_note,
    scifi_zotero_search,
    scifi_zotero_status,
)


def test_server_zotero_status_tool():
    status = scifi_zotero_status()
    assert isinstance(status, dict)
    assert "status" in status
    assert "detected" in status


def test_server_zotero_push_audit_note_offline(tmp_path, monkeypatch):
    queue_file = tmp_path / "zotero_write_queue.json"
    monkeypatch.setattr(
        "scifi.literature.zotero.writer.ZoteroLocalWriter.__init__",
        lambda self, *args, **kwargs: (
            setattr(self, "stage_file", queue_file)
            or setattr(self, "base_url", "http://127.0.0.1:23999/api/users/0")
            or setattr(self, "host", "127.0.0.1")
            or setattr(self, "port", 23999)
            or setattr(self, "api_key", None)
        ),
    )
    res = scifi_zotero_push_audit_note(
        item_key="TESTKEY",
        audit_data={
            "contribution": "Test Study",
            "assumptions_flagged": ["Assumption 1"],
            "benchmarks_extracted": [{"metric": "acc", "value": "95%"}],
            "math_verified": True,
            "retraction_status": "OK",
        },
    )
    assert isinstance(res, dict)
    assert res.get("status") == "STAGED"
    assert queue_file.is_file()
    import json

    staged = json.loads(queue_file.read_text(encoding="utf-8"))
    staged_types = [item["type"] for item in staged]
    assert "audit_note" in staged_types
    assert "tags" in staged_types


def test_server_zotero_search_tool(tmp_path, monkeypatch):
    from pathlib import Path

    from scifi.literature.zotero.models import ZoteroItem

    monkeypatch.setattr(
        "scifi.server.routers.zotero.ZoteroLocalReader.__init__",
        lambda self, *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "scifi.server.routers.zotero.ZoteroLocalReader.search_items",
        lambda self, query="", collection=None, has_pdf=None, limit=20: [
            ZoteroItem(
                item_id=1,
                key="ABC123",
                title="UAV Charging Optimization",
                authors=["Zhang, Wei"],
                year=2025,
                doi="10.1109/TEST.2025.1",
                abstract="A" * 500,
                pdf_path=Path("/tmp/uav.pdf"),
                tags=["UAV"],
            )
        ],
    )
    res = scifi_zotero_search(query="charging")
    assert len(res) == 1
    assert res[0]["key"] == "ABC123"
    assert res[0]["has_pdf"] is True
    assert res[0]["abstract_snippet"].endswith("...")
    assert len(res[0]["abstract_snippet"]) == 403


def test_multi_project_zotero_discovery_and_sync(tmp_path, monkeypatch):
    from scifi.literature.zotero.sync import (
        MultiProjectZoteroSyncer,
        discover_zotero_projects,
        register_zotero_project,
    )

    cfg_file = tmp_path / "global_config.json"
    monkeypatch.setenv("SCIFI_CONFIG_PATH", str(cfg_file))
    # Ensure LiteratureStore fallback doesn't pick up real user DB
    monkeypatch.setattr("scifi.server.app.DEFAULT_CENTRAL_STORE_PATH", tmp_path / "nonexistent.db")

    proj_a = tmp_path / "proj_a"
    (proj_a / ".scifi").mkdir(parents=True)
    (proj_a / ".scifi" / "config.toml").write_text(
        '[zotero]\nenabled = true\nauto_sync = true\ncollection = "UAV"\n',
        encoding="utf-8",
    )

    proj_b = tmp_path / "proj_b"
    (proj_b / ".scifi").mkdir(parents=True)
    (proj_b / ".scifi" / "config.toml").write_text(
        '[zotero]\nenabled = true\nauto_sync = false\ncollection = "Disabled"\n',
        encoding="utf-8",
    )

    register_zotero_project(proj_a)
    register_zotero_project(proj_b)

    discovered = discover_zotero_projects()
    assert proj_a.resolve() in discovered
    assert proj_b.resolve() not in discovered

    called_roots = []
    monkeypatch.setattr(
        "scifi.literature.zotero.sync.ZoteroAutoSyncer.sync_if_needed",
        lambda self, force=False: called_roots.append(self.root) or {"collection": "UAV", "bib_added": 1},
    )

    multi = MultiProjectZoteroSyncer()
    results = multi.sync_all_if_needed(force=True)
    assert len(results) == 1
    assert called_roots == [proj_a.resolve()]
    assert results[0]["project_root"] == str(proj_a.resolve())


def test_server_zotero_status_with_project_dir_and_live_collections(tmp_path, monkeypatch):
    from scifi.literature.zotero.models import ZoteroCollection

    proj = tmp_path / "project-beta"
    (proj / ".scifi").mkdir(parents=True)
    (proj / "paper").mkdir(parents=True)
    (proj / ".scifi" / "config.toml").write_text(
        '[zotero]\nenabled = true\nauto_sync = false\ncollection = "project-beta"\nsync_bib = "references.bib"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr("scifi.server.routers.zotero.auto_detect_zotero_dir", lambda: tmp_path)
    monkeypatch.setattr("scifi.server.routers.zotero.is_zotero_port_open", lambda: True)
    monkeypatch.setattr("scifi.server.routers.zotero.ZoteroLocalReader.__init__", lambda self, *a, **kw: None)
    monkeypatch.setattr(
        "scifi.server.routers.zotero.ZoteroLocalReader.get_collections",
        lambda self: [ZoteroCollection(collection_id=1, name="ExistingCol")],
    )
    monkeypatch.setattr(
        "scifi.server.routers.zotero.ZoteroLocalWriter.list_collections_live",
        lambda self: [
            {"key": "KEY1", "name": "ExistingCol"},
            {"key": "HLIBUWUL", "name": "project-beta"},
        ],
    )
    monkeypatch.setattr("scifi.server.app.DEFAULT_CENTRAL_STORE_PATH", tmp_path / "nonexistent.db")
    monkeypatch.setenv("SCIFI_CONFIG_PATH", str(tmp_path / "global_config.json"))

    status = scifi_zotero_status(project_dir=str(proj))
    assert status["configured_collection"] == "project-beta"
    assert status["project_root"] == str(proj.resolve())
    assert status["bib_path"] == str((proj / "paper" / "references.bib").resolve())
    names = {c["name"]: c for c in status["collections"]}
    assert "project-beta" in names
    assert names["project-beta"]["key"] == "HLIBUWUL"
    assert names["ExistingCol"]["key"] == "KEY1"


def test_server_zotero_sync_with_project_dir_persists_empty_collection(tmp_path, monkeypatch):
    from scifi.server import scifi_zotero_sync

    proj = tmp_path / "project-beta"
    (proj / ".scifi").mkdir(parents=True)
    (proj / "paper").mkdir(parents=True)
    (proj / "paper" / "references.bib").write_text("", encoding="utf-8")
    (proj / ".scifi" / "config.toml").write_text(
        '[zotero]\nenabled = true\nauto_sync = true\ncollection = ""\nsync_bib = "references.bib"\n',
        encoding="utf-8",
    )

    monkeypatch.setenv("SCIFI_CONFIG_PATH", str(tmp_path / "global_config.json"))
    monkeypatch.setattr(
        "scifi.server.routers.zotero.sync_zotero_project",
        lambda root=None, collection=None: {
            "status": "SUCCESS",
            "collection": collection,
            "bib_path": str(((root or tmp_path) / "paper" / "references.bib").resolve()),
        },
    )

    res = scifi_zotero_sync(collection="project-beta", project_dir=str(proj))
    assert res["status"] == "SUCCESS"
    assert res["bib_path"] == str((proj / "paper" / "references.bib").resolve())
    assert 'collection = "project-beta"' in (proj / ".scifi" / "config.toml").read_text(encoding="utf-8")
