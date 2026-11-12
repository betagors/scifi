# tests/test_scaffold.py
from scifi.scaffold import scaffold_project


def test_scaffold_creates_standard_two_pillar_layout(tmp_path):
    proj_dir = tmp_path / "test_research"
    res = scaffold_project(target_dir=proj_dir, title="Provably Robust UAV Networks", venue="ieee", collection="UAV")
    assert res["status"] == "SUCCESS"
    assert (proj_dir / ".scifi" / "config.toml").is_file()
    assert (proj_dir / "paper" / "main.tex").is_file()
    assert (proj_dir / "paper" / "macros.tex").is_file()
    assert (proj_dir / "paper" / "references.bib").is_file()
    assert (proj_dir / "paper" / "sections" / "01_abstract.tex").is_file()
    assert (proj_dir / "paper" / "sections" / "02_introduction.tex").is_file()
    assert (proj_dir / "code" / "src").is_dir()
    assert (proj_dir / "code" / "pyproject.toml").is_file()

    # Check config contents
    config_text = (proj_dir / ".scifi" / "config.toml").read_text(encoding="utf-8")
    assert 'title = "Provably Robust UAV Networks"' in config_text
    assert 'active_venue = "ieee"' in config_text
    assert 'collection = "UAV"' in config_text


def test_scaffold_handles_existing_directory_safely(tmp_path):
    proj_dir = tmp_path / "existing_research"
    proj_dir.mkdir()
    (proj_dir / "custom.txt").write_text("user data", encoding="utf-8")

    res = scaffold_project(target_dir=proj_dir, title="Existing Study", venue="neurips")
    assert res["status"] == "SUCCESS"
    assert (proj_dir / "custom.txt").is_file()
    assert (proj_dir / "paper" / "main.tex").is_file()
