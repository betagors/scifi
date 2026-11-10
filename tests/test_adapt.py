# tests/test_adapt.py
from pathlib import Path
from scifi.adapt import adapt_project

def test_adapt_migrates_flat_repo_safely(tmp_path):
    flat_repo = tmp_path / "legacy_repo"
    flat_repo.mkdir()
    (flat_repo / "paper.tex").write_text(r"\documentclass{article}\begin{document}Hello\end{document}", encoding="utf-8")
    (flat_repo / "refs.bib").write_text("@article{Zhang2020,\n title={UAV Caching}\n}", encoding="utf-8")
    (flat_repo / "train.py").write_text("print('training')", encoding="utf-8")
    (flat_repo / "data.csv").write_text("x,y\n1,2", encoding="utf-8")
    
    res = adapt_project(flat_repo, venue="ieee", collection="UAV", dry_run=False)
    assert res["status"] == "SUCCESS"
    assert (flat_repo / "paper" / "main.tex").is_file()
    assert (flat_repo / "paper" / "references.bib").is_file()
    assert (flat_repo / "code" / "src" / "train.py").is_file()
    assert (flat_repo / "code" / "data" / "data.csv").is_file()
    assert (flat_repo / ".scifi" / "config.toml").is_file()

def test_adapt_dry_run_leaves_files_untouched(tmp_path):
    flat_repo = tmp_path / "dry_run_repo"
    flat_repo.mkdir()
    (flat_repo / "paper.tex").write_text(r"\documentclass{article}", encoding="utf-8")
    (flat_repo / "train.py").write_text("print('training')", encoding="utf-8")
    
    res = adapt_project(flat_repo, venue="ieee", collection="UAV", dry_run=True)
    assert res["status"] == "DRY_RUN"
    assert (flat_repo / "paper.tex").is_file()
    assert (flat_repo / "train.py").is_file()
    assert not (flat_repo / "paper").exists()


def test_adapt_preserves_existing_paper_bib_and_parses_citations(tmp_path):
    repo = tmp_path / "semi_structured_repo"
    repo.mkdir()
    paper_dir = repo / "paper"
    paper_dir.mkdir()
    (paper_dir / "main.tex").write_text(r"\documentclass{article}\title{UAV Trajectory}\begin{document}Hello\end{document}", encoding="utf-8")
    (paper_dir / "references.bib").write_text("@article{Zhang2020,\n title={UAV Caching},\n doi={10.1109/TVT.2020.1}\n}", encoding="utf-8")
    (repo / "scifi.toml").write_text("[manuscript]\ntarget_venue = 'ieee'\ndouble_blind = false\n", encoding="utf-8")

    res = adapt_project(repo, venue="ieee", dry_run=False)
    assert res["status"] == "SUCCESS"
    assert res["citations_found"] == 1
    config_content = (repo / ".scifi" / "config.toml").read_text(encoding="utf-8")
    assert 'title = "UAV Trajectory"' in config_content
    assert "double_blind = false" in config_content

