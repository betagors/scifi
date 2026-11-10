"""
scifi.config — Centralized Global & Workspace Configuration Manager.

Supports:
1. Global user configuration in ~/.scifi/config.json (or SCIFI_CONFIG_PATH env var):
   - email: Polite-pool email for Crossref, OpenAlex, and Unpaywall
   - s2_api_key: Semantic Scholar API key
   - default_venue: Default target venue/publisher (e.g., 'ieee', 'neurips', 'acm', 'nature')
   - author_whitelist: Default author names to whitelist against self-plagiarism flags
2. Project workspace configuration in scifi.toml:
   - [manuscript]
     main_tex = "main.tex"
     bib_file = "references.bib"
     target_venue = "ieee"
     double_blind = true
     author_whitelist = ["Jane Doe"]
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import tomllib
from typing import Any


DEFAULT_USER_AGENT_BASE = "SciFi-Toolkit/1.0 (https://github.com/Betagors/scifi"
DEFAULT_FALLBACK_EMAIL = "scifi-toolkit@gmail.com"


@dataclass
class ScifiConfig:
    """Resolved configuration combining global ~/.scifi/config.json and local scifi.toml."""

    email: str | None = None
    s2_api_key: str | None = None
    default_venue: str | None = None
    author_whitelist: list[str] = field(default_factory=list)
    main_tex: str = "main.tex"
    bib_file: str = "references.bib"
    target_venue: str | None = None
    double_blind: bool = False
    preprint_doi: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_global_config_path() -> Path:
    """Return path to global user config (~/.scifi/config.json or SCIFI_CONFIG_PATH)."""
    env_override = os.environ.get("SCIFI_CONFIG_PATH")
    if env_override:
        return Path(env_override)
    return Path.home() / ".scifi" / "config.json"


def load_global_config(config_path: Path | str | None = None) -> dict[str, Any]:
    """Load global configuration dictionary from ~/.scifi/config.json."""
    path = Path(config_path) if config_path else get_global_config_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_global_config(data: dict[str, Any], config_path: Path | str | None = None) -> Path:
    """Persist global configuration dictionary to ~/.scifi/config.json."""
    path = Path(config_path) if config_path else get_global_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def set_global_config_value(
    key: str,
    value: Any,
    config_path: Path | str | None = None,
) -> Path:
    """Set a single key in ~/.scifi/config.json."""
    valid_keys = {"email", "s2_api_key", "default_venue", "author_whitelist", "zotero_local_api_key"}
    norm_key = key.strip().lower().replace("-", "_")
    if norm_key not in valid_keys:
        raise ValueError(f"Unsupported config key '{key}'. Valid keys: {', '.join(sorted(valid_keys))}")

    data = load_global_config(config_path)
    if norm_key == "author_whitelist":
        if isinstance(value, str):
            data[norm_key] = [v.strip() for v in value.split(",") if v.strip()]
        elif isinstance(value, list):
            data[norm_key] = [str(v).strip() for v in value if str(v).strip()]
        else:
            data[norm_key] = []
    else:
        data[norm_key] = str(value).strip() if value is not None else None

    return save_global_config(data, config_path)


def load_workspace_toml(workspace_dir: Path | str | None = None) -> dict[str, Any]:
    """Load local project configuration from scifi.toml if present."""
    base = Path(workspace_dir) if workspace_dir else Path.cwd()
    if base.is_file():
        base = base.parent

    toml_path = base / "scifi.toml"
    if not toml_path.is_file():
        return {}
    try:
        return tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def resolve_config(
    workspace_dir: Path | str | None = None,
    global_config_path: Path | str | None = None,
) -> ScifiConfig:
    """
    Resolve effective ScifiConfig by merging:
    1. Defaults
    2. Global ~/.scifi/config.json
    3. Environment variables (SCIFI_EMAIL, S2_API_KEY)
    4. Project workspace scifi.toml
    """
    global_data = load_global_config(global_config_path)
    toml_data = load_workspace_toml(workspace_dir)
    manuscript_sec = toml_data.get("manuscript", {}) if isinstance(toml_data.get("manuscript"), dict) else {}
    api_sec = toml_data.get("api", {}) if isinstance(toml_data.get("api"), dict) else {}

    email = (
        api_sec.get("email")
        or os.environ.get("SCIFI_EMAIL")
        or global_data.get("email")
    )
    s2_api_key = (
        api_sec.get("s2_api_key")
        or os.environ.get("S2_API_KEY")
        or global_data.get("s2_api_key")
    )
    default_venue = global_data.get("default_venue")
    target_venue = manuscript_sec.get("target_venue") or default_venue

    whitelist: list[str] = []
    if isinstance(global_data.get("author_whitelist"), list):
        whitelist.extend(str(a) for a in global_data["author_whitelist"])
    if isinstance(manuscript_sec.get("author_whitelist"), list):
        for a in manuscript_sec["author_whitelist"]:
            if str(a) not in whitelist:
                whitelist.append(str(a))

    main_tex = str(manuscript_sec.get("main_tex", "main.tex"))
    bib_file = str(manuscript_sec.get("bib_file", "references.bib"))
    double_blind = bool(manuscript_sec.get("double_blind", False))
    preprint_doi = manuscript_sec.get("preprint_doi")

    return ScifiConfig(
        email=email,
        s2_api_key=s2_api_key,
        default_venue=default_venue,
        author_whitelist=whitelist,
        main_tex=main_tex,
        bib_file=bib_file,
        target_venue=target_venue,
        double_blind=double_blind,
        preprint_doi=preprint_doi,
    )


def get_polite_email(workspace_dir: Path | str | None = None) -> str:
    """Return configured polite-pool email or fallback."""
    cfg = resolve_config(workspace_dir=workspace_dir)
    return cfg.email or DEFAULT_FALLBACK_EMAIL


def get_user_agent(workspace_dir: Path | str | None = None) -> str:
    """Return HTTP User-Agent string with polite-pool mailto contact."""
    email = get_polite_email(workspace_dir=workspace_dir)
    return f"{DEFAULT_USER_AGENT_BASE}; mailto:{email})"


def generate_scifi_toml_template(
    main_tex: str = "main.tex",
    bib_file: str = "references.bib",
    target_venue: str = "ieee",
    double_blind: bool = True,
) -> str:
    """Generate a documented scifi.toml project configuration template."""
    db_str = "true" if double_blind else "false"
    return (
        "# SciFi Project Configuration (scifi.toml)\n"
        "# Used automatically by `sf doctor`, `sf venue`, `sf argus`, and `sf shannon`.\n\n"
        "[manuscript]\n"
        f'main_tex = "{main_tex}"\n'
        f'bib_file = "{bib_file}"\n'
        f'target_venue = "{target_venue}"\n'
        f"double_blind = {db_str}\n"
        "author_whitelist = []\n"
        '# preprint_doi = "10.48550/arXiv.XXXX.XXXXX"\n\n'
        "[api]\n"
        '# email = "researcher@university.edu"  # Polite pool for Crossref / OpenAlex / Unpaywall\n'
    )
