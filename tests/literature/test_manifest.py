import json
from pathlib import Path
import pytest

from scifi.literature.store import LiteratureStore
from scifi.literature.models import (
    PaperRecord,
    CitationRecord,
    EvidenceRecord,
    PaperGapRecord,
    BenchmarkRecord,
    BenchmarkResultRecord,
    EvaluationMetricRecord,
)
from scifi.literature.manifest import export_manifest, import_manifest, sync_workspace


def test_manifest_export_and_import_roundtrip(tmp_path: Path):
    db1_path = tmp_path / "central1.db"
    store1 = LiteratureStore(db1_path)
    proj1 = store1.register_project("uav-research", str(tmp_path / "repo"))

    p1 = PaperRecord(id="10.1000/1", title="Paper 1", year=2021)
    p2 = PaperRecord(id="10.1000/2", title="Paper 2", year=2022)
    store1.upsert_paper(p1)
    store1.upsert_paper(p2)
    store1.link_paper_to_project(proj1.id, p1.id)
    store1.link_paper_to_project(proj1.id, p2.id)
    store1.add_citations([CitationRecord(source_paper_id=p2.id, target_paper_id=p1.id, is_influential=True)])

    manifest_file = tmp_path / "repo" / ".scifi" / "literature_manifest.json"
    exported_path = export_manifest(store1, proj1.id, manifest_file)
    assert manifest_file.exists()
    assert exported_path == manifest_file

    with open(manifest_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["project_name"] == "uav-research"
    assert data["papers_count"] == 2
    assert len(data["papers"]) == 2
    assert len(data["citations"]) == 1

    # Simulate fresh clone on machine 2
    db2_path = tmp_path / "central2.db"
    store2 = LiteratureStore(db2_path)
    proj2 = import_manifest(store2, manifest_file, str(tmp_path / "repo"))

    assert proj2.name == "uav-research"
    papers2 = store2.get_project_papers(proj2.id)
    assert len(papers2) == 2
    citations2 = store2.get_paper_citations(p2.id)
    assert len(citations2) == 1
    assert citations2[0].target_paper_id == p1.id


def test_sync_workspace_creates_manifest_and_bib(tmp_path: Path):
    repo_dir = tmp_path / "my_project"
    repo_dir.mkdir(parents=True, exist_ok=True)

    db_path = tmp_path / "central.db"
    store = LiteratureStore(db_path)
    proj = store.register_project("my-project", str(repo_dir))

    p = PaperRecord(id="10.1000/sync_test", title="Sync Test Paper", year=2023)
    store.upsert_paper(p)
    store.link_paper_to_project(proj.id, p.id)

    synced_proj = sync_workspace(store, repo_dir)
    assert synced_proj.id == proj.id

    manifest_file = repo_dir / ".scifi" / "literature_manifest.json"
    bib_file = repo_dir / ".scifi" / "references.bib"

    assert manifest_file.exists()
    assert bib_file.exists()

    bib_content = bib_file.read_text(encoding="utf-8")
    assert "@article{" in bib_content
    assert "Sync Test Paper" in bib_content


def test_sync_workspace_fresh_clone_rehydrates(tmp_path: Path):
    # Machine 1: export manifest
    repo_dir = tmp_path / "repo_clone"
    manifest_dir = repo_dir / ".scifi"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = manifest_dir / "literature_manifest.json"

    store1 = LiteratureStore(tmp_path / "central1.db")
    proj1 = store1.register_project("rehydrate-proj", str(repo_dir))
    paper = PaperRecord(id="10.1111/rehydrate", title="Rehydration Target", year=2024)
    store1.upsert_paper(paper)
    store1.link_paper_to_project(proj1.id, paper.id)
    export_manifest(store1, proj1.id, manifest_file)

    # Machine 2: brand new central store, only has git repo with manifest
    store2 = LiteratureStore(tmp_path / "central2.db")
    # Verify central store knows nothing about this project yet
    assert len(store2.list_projects()) == 0

    synced_proj = sync_workspace(store2, repo_dir)
    assert synced_proj.name == "rehydrate-proj"

    # Verify store2 was rehydrated
    papers = store2.get_project_papers(synced_proj.id)
    assert len(papers) == 1
    assert papers[0].id == "10.1111/rehydrate"
    assert papers[0].title == "Rehydration Target"

    # Verify bib file was generated
    bib_file = repo_dir / ".scifi" / "references.bib"
    assert bib_file.exists()
    assert "Rehydration Target" in bib_file.read_text(encoding="utf-8")


def test_manifest_roundtrip_with_gaps_and_benchmarks(tmp_path: Path):
    db1_path = tmp_path / "central1.db"
    store1 = LiteratureStore(db1_path)
    repo = tmp_path / "repo"
    proj = store1.register_project("eval-project", str(repo))

    paper = PaperRecord(id="10.2000/eval", title="Evaluation Study", year=2023)
    store1.upsert_paper(paper)
    store1.link_paper_to_project(proj.id, paper.id)

    # Add evidence and gap
    ev = EvidenceRecord(
        id="ev-100",
        paper_id=paper.id,
        evidence_type="limitation",
        extracted_text="Method fails in rain.",
        extraction_method="manual",
    )
    store1.save_evidence(ev)
    gap = PaperGapRecord(
        id="gap-100",
        paper_id=paper.id,
        gap_type="environmental",
        claim_summary="Rain failure limitation",
        primary_evidence_id=ev.id,
        verification_status="corroborated",
    )
    store1.save_paper_gap(gap)

    # Add benchmark and result
    bm = BenchmarkRecord(id="bm-100", name="DroneBench", domain="Robotics")
    store1.save_benchmark(bm)
    metric = EvaluationMetricRecord(id="met-100", name="mAP", goal="maximize")
    store1.save_evaluation_metric(metric)
    result = BenchmarkResultRecord(
        id="res-100",
        paper_id=paper.id,
        benchmark_id=bm.id,
        metric_id=metric.id,
        metric_value=0.925,
        is_sota=True,
    )
    store1.save_benchmark_result(result)

    manifest_file = repo / ".scifi" / "literature_manifest.json"
    export_manifest(store1, proj.id, manifest_file)

    # Machine 2 re-hydration
    store2 = LiteratureStore(tmp_path / "central2.db")
    proj2 = import_manifest(store2, manifest_file, str(repo))

    gaps2 = store2.get_paper_gaps(paper.id)
    assert len(gaps2) == 1
    assert gaps2[0].claim_summary == "Rain failure limitation"

    ev2 = store2.get_paper_evidence(paper.id)
    assert len(ev2) == 1
    assert ev2[0].extracted_text == "Method fails in rain."

    bench_results2 = store2.get_paper_benchmark_results(paper.id)
    assert len(bench_results2) == 1
    assert bench_results2[0].metric_value == pytest.approx(0.925)
    assert bench_results2[0].is_sota is True


def test_manifest_roundtrip_with_reprint_requests(tmp_path: Path):
    db1_path = tmp_path / "central1.db"
    store1 = LiteratureStore(db1_path)
    repo = tmp_path / "repo_reprints"
    proj = store1.register_project("reprint-proj", str(repo))

    p = PaperRecord(id="10.3000/paywalled", title="Paywalled Paper", year=2024)
    store1.upsert_paper(p)
    store1.link_paper_to_project(proj.id, p.id)

    req = store1.create_reprint_request(
        project_id=proj.id,
        paper_id=p.id,
        author_name="Dr. Author",
        author_email="author@example.edu",
        status="DRAFT_READY",
        subject="Reprint request for Paywalled Paper",
        body="Dear Dr. Author...",
    )

    manifest_file = repo / ".scifi" / "literature_manifest.json"
    export_manifest(store1, proj.id, manifest_file)

    # Machine 2 re-hydration
    store2 = LiteratureStore(tmp_path / "central2.db")
    proj2 = import_manifest(store2, manifest_file, str(repo))

    reprints2 = store2.get_reprint_requests(project_id=proj2.id)
    assert len(reprints2) == 1
    assert reprints2[0].paper_id == p.id
    assert reprints2[0].author_name == "Dr. Author"
    assert reprints2[0].author_email == "author@example.edu"
    assert reprints2[0].status == "DRAFT_READY"


def test_import_manifest_from_directory_path(tmp_path: Path):
    store1 = LiteratureStore(tmp_path / "central1.db")
    repo = tmp_path / "dir_repo"
    proj = store1.register_project("dir-proj", str(repo))

    paper = PaperRecord(id="10.4000/dir", title="Directory Paper", year=2022)
    store1.upsert_paper(paper)
    store1.link_paper_to_project(proj.id, paper.id)

    export_manifest(store1, proj.id, repo / ".scifi")

    # Import by passing workspace directory
    store2 = LiteratureStore(tmp_path / "central2.db")
    proj2 = import_manifest(store2, repo)
    assert proj2.name == "dir-proj"
    papers = store2.get_project_papers(proj2.id)
    assert len(papers) == 1
    assert papers[0].id == "10.4000/dir"


def test_sync_workspace_updates_root_references_bib_if_present(tmp_path: Path):
    repo = tmp_path / "repo_with_root_bib"
    repo.mkdir(parents=True, exist_ok=True)
    root_bib = repo / "references.bib"
    root_bib.write_text("% Old root bib\n", encoding="utf-8")

    store = LiteratureStore(tmp_path / "central.db")
    proj = store.register_project("root-bib-proj", str(repo))
    p = PaperRecord(id="10.5000/bib_update", title="Root Bib Paper", year=2023)
    store.upsert_paper(p)
    store.link_paper_to_project(proj.id, p.id)

    sync_workspace(store, repo)

    # Both .scifi/references.bib and root references.bib should be updated
    scifi_bib = repo / ".scifi" / "references.bib"
    assert scifi_bib.exists()
    assert "Root Bib Paper" in scifi_bib.read_text(encoding="utf-8")

    assert "Root Bib Paper" in root_bib.read_text(encoding="utf-8")


def test_export_manifest_invalid_project(tmp_path: Path):
    store = LiteratureStore(tmp_path / "central.db")
    with pytest.raises(ValueError, match="not found"):
        export_manifest(store, "non-existent-proj-id", tmp_path / "manifest.json")


def test_import_manifest_missing_file_raises(tmp_path: Path):
    store = LiteratureStore(tmp_path / "central.db")
    with pytest.raises(FileNotFoundError):
        import_manifest(store, tmp_path / "does_not_exist.json")
