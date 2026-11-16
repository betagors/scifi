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

import json
import os
import tempfile
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CONFIG_SCHEMA_VERSION = 1
DEFAULT_USER_AGENT_BASE = "SciFi-Toolkit/1.0 (https://github.com/Betagors/scifi"
DEFAULT_FALLBACK_EMAIL = "scifi-toolkit@gmail.com"
DEFAULT_DATASETS_DIR = Path.home() / ".scifi" / "datasets"


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
    latex_bin_dir: str | None = None
    latex_engine: str | None = None
    datasets_dir: str | None = None
    kaggle_username: str | None = None
    kaggle_key: str | None = None
    hf_token: str | None = None
    zenodo_token: str | None = None
    orwell_voice: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_global_config_path() -> Path:
    """Return path to global user config (~/.scifi/config.json or SCIFI_CONFIG_PATH)."""
    env_override = os.environ.get("SCIFI_CONFIG_PATH")
    if env_override:
        return Path(env_override)
    return Path.home() / ".scifi" / "config.json"


def migrate_global_config(data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """
    Upgrade a global config dictionary to CONFIG_SCHEMA_VERSION.
    Returns (migrated_dict, changed).
    """
    migrated = dict(data)
    changed = False

    # Normalize any legacy hyphenated keys to snake_case
    for key in list(migrated.keys()):
        if "-" in key:
            norm = key.replace("-", "_")
            if norm not in migrated:
                migrated[norm] = migrated.pop(key)
                changed = True

    raw_ver = migrated.get("config_version")
    if not isinstance(raw_ver, int) or raw_ver < CONFIG_SCHEMA_VERSION:
        migrated["config_version"] = CONFIG_SCHEMA_VERSION
        changed = True

    return migrated, changed


def migrate_global_config_file(config_path: Path | str | None = None) -> bool:
    """Persist any pending global config migration if the file exists. Returns True if updated."""
    path = Path(config_path) if config_path else get_global_config_path()
    if not path.is_file():
        return False
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return False
    except Exception:
        return False
    migrated, changed = migrate_global_config(raw)
    if changed:
        save_global_config(migrated, path)
    return changed


def load_global_config(config_path: Path | str | None = None) -> dict[str, Any]:
    """Load global configuration dictionary from ~/.scifi/config.json."""
    path = Path(config_path) if config_path else get_global_config_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        migrated, _ = migrate_global_config(data)
        return migrated
    except Exception:
        return {}


def save_global_config(data: dict[str, Any], config_path: Path | str | None = None) -> Path:
    """Persist global configuration dictionary atomically to ~/.scifi/config.json."""
    path = Path(config_path) if config_path else get_global_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    payload["config_version"] = CONFIG_SCHEMA_VERSION
    formatted = json.dumps(payload, indent=2) + "\n"
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tf:
            tf.write(formatted)
            temp_name = tf.name
        os.replace(temp_name, path)
    except Exception:
        if temp_name and os.path.exists(temp_name):
            try:
                os.remove(temp_name)
            except OSError:
                pass
        raise
    return path


def set_global_config_value(
    key: str,
    value: Any,
    config_path: Path | str | None = None,
) -> Path:
    """Set a single key in ~/.scifi/config.json."""
    valid_keys = {
        "email",
        "s2_api_key",
        "default_venue",
        "author_whitelist",
        "zotero_local_api_key",
        "zotero_projects",
        "latex_bin_dir",
        "latex_engine",
        "datasets_dir",
        "kaggle_username",
        "kaggle_key",
        "hf_token",
        "zenodo_token",
    }
    norm_key = key.strip().lower().replace("-", "_")
    if norm_key not in valid_keys:
        raise ValueError(f"Unsupported config key '{key}'. Valid keys: {', '.join(sorted(valid_keys))}")

    data = load_global_config(config_path)
    if norm_key in ("author_whitelist", "zotero_projects"):
        if isinstance(value, str):
            data[norm_key] = [v.strip() for v in value.split(",") if v.strip()]
        elif isinstance(value, list):
            data[norm_key] = [str(v).strip() for v in value if str(v).strip()]
        else:
            data[norm_key] = []
    else:
        data[norm_key] = str(value).strip() if value is not None else None

    return save_global_config(data, config_path)


def _normalize_dot_scifi_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize .scifi/config.toml (2-pillar schema) into scifi.toml-compatible sections."""
    out: dict[str, Any] = dict(raw)
    proj = raw.get("project") if isinstance(raw.get("project"), dict) else {}
    ms = dict(raw.get("manuscript")) if isinstance(raw.get("manuscript"), dict) else {}

    paper_dir = str(ms.get("paper_dir", "")).strip().strip("/\\")
    if "main_tex" not in ms and "main_entrypoint" in ms:
        ep = str(ms["main_entrypoint"]).strip()
        ms["main_tex"] = f"{paper_dir}/{ep}" if paper_dir else ep
    if "bib_file" in ms and paper_dir and not ("/" in str(ms["bib_file"]) or "\\" in str(ms["bib_file"])):
        ms["bib_file"] = f"{paper_dir}/{ms['bib_file']}"
    if "target_venue" not in ms and "active_venue" in proj:
        ms["target_venue"] = proj["active_venue"]
    if "double_blind" not in ms and "double_blind" in proj:
        ms["double_blind"] = proj["double_blind"]
    if ms:
        out["manuscript"] = ms
    return out


def load_workspace_toml(workspace_dir: Path | str | None = None) -> dict[str, Any]:
    """Load local project configuration from .scifi/config.toml and/or scifi.toml."""
    base = Path(workspace_dir) if workspace_dir else Path.cwd()
    if base.is_file():
        base = base.parent

    merged: dict[str, Any] = {}
    dot_toml = base / ".scifi" / "config.toml"
    if dot_toml.is_file():
        try:
            merged = _normalize_dot_scifi_config(tomllib.loads(dot_toml.read_text(encoding="utf-8")))
        except Exception:
            pass

    toml_path = base / "scifi.toml"
    if toml_path.is_file():
        try:
            root_data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
            for sec, val in root_data.items():
                if isinstance(val, dict) and isinstance(merged.get(sec), dict):
                    merged[sec] = {**merged[sec], **val}
                else:
                    merged[sec] = val
        except Exception:
            pass

    return merged


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
    latex_sec = toml_data.get("latex", {}) if isinstance(toml_data.get("latex"), dict) else {}
    datasets_sec = toml_data.get("datasets", {}) if isinstance(toml_data.get("datasets"), dict) else {}
    orwell_sec = toml_data.get("orwell", {}) if isinstance(toml_data.get("orwell"), dict) else {}
    orwell_voice = dict(orwell_sec.get("voice", {})) if isinstance(orwell_sec.get("voice"), dict) else {}

    email = api_sec.get("email") or os.environ.get("SCIFI_EMAIL") or global_data.get("email")
    s2_api_key = api_sec.get("s2_api_key") or os.environ.get("S2_API_KEY") or global_data.get("s2_api_key")
    default_venue = global_data.get("default_venue")
    target_venue = manuscript_sec.get("target_venue") or default_venue
    latex_bin_dir = (
        latex_sec.get("bin_dir") or os.environ.get("SCIFI_LATEX_BIN_DIR") or global_data.get("latex_bin_dir")
    )
    latex_engine = latex_sec.get("engine") or os.environ.get("SCIFI_LATEX_ENGINE") or global_data.get("latex_engine")
    datasets_dir = (
        datasets_sec.get("dir")
        or os.environ.get("SCIFI_DATASETS_DIR")
        or global_data.get("datasets_dir")
        or str(DEFAULT_DATASETS_DIR)
    )
    kaggle_username = (
        api_sec.get("kaggle_username") or os.environ.get("KAGGLE_USERNAME") or global_data.get("kaggle_username")
    )
    kaggle_key = api_sec.get("kaggle_key") or os.environ.get("KAGGLE_KEY") or global_data.get("kaggle_key")
    hf_token = api_sec.get("hf_token") or os.environ.get("HF_TOKEN") or global_data.get("hf_token")
    zenodo_token = api_sec.get("zenodo_token") or os.environ.get("ZENODO_TOKEN") or global_data.get("zenodo_token")

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
        latex_bin_dir=latex_bin_dir,
        latex_engine=latex_engine,
        datasets_dir=datasets_dir,
        kaggle_username=kaggle_username,
        kaggle_key=kaggle_key,
        hf_token=hf_token,
        zenodo_token=zenodo_token,
        orwell_voice=orwell_voice,
    )


def get_datasets_dir(
    workspace_dir: Path | str | None = None,
    override: Path | str | None = None,
    global_config_path: Path | str | None = None,
) -> Path:
    """Resolve the default datasets directory, expanding user home (~)."""
    if override is not None and str(override).strip():
        return Path(override).expanduser().resolve()
    cfg = resolve_config(workspace_dir=workspace_dir, global_config_path=global_config_path)
    raw = cfg.datasets_dir or str(DEFAULT_DATASETS_DIR)
    return Path(raw).expanduser().resolve()


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


def _format_toml_value(val: Any) -> str:
    """Serialize a Python primitive or flat list/dict for scifi.toml."""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        escaped = val.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(val, list):
        items = ", ".join(_format_toml_value(v) for v in val)
        return f"[{items}]"
    return _format_toml_value(str(val))


def save_orwell_voice_toml(
    voice_profile: dict[str, Any],
    toml_path: Path | str | None = None,
) -> Path:
    """
    Write or update the [orwell.voice] (and optional [orwell.voice.macros]) section
    in scifi.toml without clobbering existing [manuscript], [api], or [latex] sections.
    """
    path = Path(toml_path) if toml_path else Path.cwd() / "scifi.toml"
    if path.is_dir():
        path = path / "scifi.toml"

    existing_text = path.read_text(encoding="utf-8") if path.is_file() else ""
    # Strip any existing [orwell.voice] and [orwell.voice.macros] blocks
    cleaned_lines: list[str] = []
    skip_section = False
    for line in existing_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            sec_name = stripped[1:-1].strip()
            if sec_name in ("orwell.voice", "orwell.voice.macros"):
                skip_section = True
                continue
            skip_section = False
        if not skip_section:
            cleaned_lines.append(line)

    while cleaned_lines and not cleaned_lines[-1].strip():
        cleaned_lines.pop()

    macros = voice_profile.get("macro_conventions", {})
    scalar_keys = [
        "source",
        "preset",
        "sentence_length_mean",
        "sentence_length_cv_min",
        "sentence_length_cv_target",
        "passive_ratio_target",
        "preferred_transitions",
    ]

    orwell_lines = ["[orwell.voice]"]
    for k in scalar_keys:
        if k in voice_profile and voice_profile[k] is not None:
            orwell_lines.append(f"{k} = {_format_toml_value(voice_profile[k])}")

    if isinstance(macros, dict) and macros:
        orwell_lines.append("")
        orwell_lines.append("[orwell.voice.macros]")
        for macro_name, expansion in sorted(macros.items()):
            orwell_lines.append(f"{_format_toml_value(str(macro_name))} = {_format_toml_value(str(expansion))}")

    new_parts: list[str] = []
    if cleaned_lines:
        new_parts.append("\n".join(cleaned_lines))
    new_parts.append("\n".join(orwell_lines))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(new_parts) + "\n", encoding="utf-8")
    return path


_KNOWN_SECTIONS: dict[str, set[str]] = {
    "manuscript": {
        "main_tex",
        "bib_file",
        "target_venue",
        "double_blind",
        "author_whitelist",
        "preprint_doi",
    },
    "api": {"email", "s2_api_key"},
    "latex": {"bin_dir", "engine"},
    "orwell": {"voice"},
}


def validate_workspace_config(workspace_dir: Path | str | None = None) -> dict[str, Any]:
    """Validate scifi.toml structure, key types, and referenced project files.

    Args:
        workspace_dir: Workspace directory containing ``scifi.toml`` (defaults to cwd).

    Returns:
        Dictionary with ``valid``, ``toml_found``, ``toml_path``, ``errors``, and ``warnings``.
    """
    base = Path(workspace_dir) if workspace_dir else Path.cwd()
    toml_path = base / "scifi.toml"
    errors: list[str] = []
    warnings: list[str] = []

    if not toml_path.is_file():
        return {
            "valid": True,
            "toml_found": False,
            "toml_path": None,
            "errors": [],
            "warnings": [],
        }

    try:
        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "valid": False,
            "toml_found": True,
            "toml_path": str(toml_path),
            "errors": [f"Invalid TOML syntax in {toml_path.name}: {exc}"],
            "warnings": [],
        }

    for section, value in data.items():
        if section not in _KNOWN_SECTIONS:
            warnings.append(f"Unknown section [{section}] in scifi.toml.")
            continue
        if not isinstance(value, dict):
            errors.append(f"Section [{section}] must be a TOML table.")
            continue
        known_keys = _KNOWN_SECTIONS[section]
        for key in value:
            if key not in known_keys:
                warnings.append(f"Unknown key '{section}.{key}' in scifi.toml.")

    manuscript = data.get("manuscript")
    if isinstance(manuscript, dict):
        if "double_blind" in manuscript and not isinstance(manuscript["double_blind"], bool):
            errors.append("'manuscript.double_blind' must be a boolean.")
        if "author_whitelist" in manuscript:
            wl = manuscript["author_whitelist"]
            if not isinstance(wl, list) or not all(isinstance(item, str) for item in wl):
                errors.append("'manuscript.author_whitelist' must be a list of strings.")
        for key in ("main_tex", "bib_file", "target_venue", "preprint_doi"):
            if key in manuscript and not isinstance(manuscript[key], str):
                errors.append(f"'manuscript.{key}' must be a string.")
        if isinstance(manuscript.get("main_tex"), str) and not (base / manuscript["main_tex"]).exists():
            warnings.append(f"Configured main_tex '{manuscript['main_tex']}' does not exist in {base}.")
        if isinstance(manuscript.get("bib_file"), str) and not (base / manuscript["bib_file"]).exists():
            warnings.append(f"Configured bib_file '{manuscript['bib_file']}' does not exist in {base}.")

    api = data.get("api")
    if isinstance(api, dict):
        for key in ("email", "s2_api_key"):
            if key in api and not isinstance(api[key], str):
                errors.append(f"'api.{key}' must be a string.")

    latex = data.get("latex")
    if isinstance(latex, dict):
        for key in ("bin_dir", "engine"):
            if key in latex and not isinstance(latex[key], str):
                errors.append(f"'latex.{key}' must be a string.")

    orwell = data.get("orwell")
    if isinstance(orwell, dict) and "voice" in orwell:
        voice = orwell["voice"]
        if not isinstance(voice, dict):
            errors.append("'orwell.voice' must be a TOML table.")
        else:
            for num_key in (
                "sentence_length_mean",
                "sentence_length_cv_min",
                "sentence_length_cv_target",
                "passive_ratio_target",
            ):
                if num_key in voice and not isinstance(voice[num_key], (int, float)):
                    errors.append(f"'orwell.voice.{num_key}' must be numeric.")

    return {
        "valid": len(errors) == 0,
        "toml_found": True,
        "toml_path": str(toml_path),
        "errors": errors,
        "warnings": warnings,
    }
