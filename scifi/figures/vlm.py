"""Multimodal VLM visual inspection engine for rendered figures and compiled PDF pages."""

from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

import requests

_DEFAULT_MODELS: dict[str, str] = {
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4o",
    "anthropic": "claude-3-5-sonnet-latest",
    "openai_compatible": "gpt-4o",
}

_FIGURE_PROMPT = """You are a senior scientific figure and publication design reviewer.
Inspect the attached rendered figure(s) and/or figure-bearing PDF page(s) for visual defects that static LaTeX parsing cannot detect:
1. Overlapping or colliding axis tick labels, axis titles, data labels, or annotations.
2. Cut-off or clipped legends, titles, axis labels, or plot edges.
3. Illegible or excessively small font sizes, or low-contrast text/lines.
4. Subfigure ((a), (b), (c)) misalignment, inconsistent sizing, or overlapping panels.
5. Colorblind-ambiguous curve/bar encodings lacking secondary cues (markers, line styles, hatching).
6. Figures overflowing column/page margins or colliding with captions/body text.
7. Inconsistent, invented, or compound algorithm/variant labels in legends or diagrams (e.g., stale hyphenated blends like Lya-BiMAPPO or Safe-Pure-MAPPO that contradict standardized prose/table labels, or unexplained ad-hoc acronyms).

Return ONLY a JSON array of defect objects (empty array [] if no defects are found). Each object must have:
- "category": one of ["LABEL_READABILITY", "LABEL_CONSISTENCY", "CLIPPED_CONTENT", "OVERLAPPING_ELEMENTS", "SUBFIGURE_LAYOUT", "COLORBLIND_RISK", "MARGIN_OVERFLOW", "VISUAL_DEFECT"]
- "severity": one of ["INFO", "WARNING", "CRITICAL"]
- "target": short identifier of the figure or page (e.g. "fig:loss" or "Page 3")
- "message": concise description of the exact visual defect observed
- "recommendation": concrete fix to resolve the visual defect
"""

_LAYOUT_PROMPT = """You are a senior academic typesetting and page-budget reviewer.
Inspect the attached rendered compiled PDF page(s) for visual layout, pagination, and whitespace defects that static LaTeX parsing cannot detect:
1. Awkward page-break whitespace or large empty vertical gaps at the bottom of pages or columns.
2. Orphan/widow headings or isolated single-line trailing paragraphs at page/column boundaries.
3. Float/table/figure placement issues (e.g., floats pushed far away, excessive whitespace around floats, or a sparsely populated trailing final page).
4. Margin overflows, overfull text/equations bleeding into margins or column gutters, or colliding text/tables.
5. Excessively loose table/figure padding that could be legitimately tightened to save vertical lines.

Return ONLY a JSON array of layout finding objects (empty array [] if no defects are found). Each object must have:
- "category": one of ["PAGE_BREAK_WHITESPACE", "ORPHAN_HEADING", "FLOAT_PLACEMENT", "MARGIN_OVERFLOW", "WIDOW_LINE", "TRAILING_PAGE_SLACK"]
- "severity": one of ["INFO", "WARNING", "CRITICAL"]
- "page": integer page number if known, else null
- "target": short target label (e.g. "Page 4" or "Page 8 (bottom)")
- "message": concise description of the layout/whitespace defect observed
- "recommendation": concrete typographic fix (without negative \\vspace hacks)
- "potential_savings_lines": integer estimate of vertical lines recoverable (0 if purely visual fix)
"""


def resolve_vlm_config(
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Resolve VLM provider, model, API key, and endpoint from arguments or environment."""
    eff_provider = (provider or os.environ.get("SCIFI_VLM_PROVIDER") or "").strip().lower()
    eff_base_url = (base_url or os.environ.get("SCIFI_VLM_BASE_URL") or "").strip()

    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    generic_key = api_key or os.environ.get("SCIFI_VLM_API_KEY")

    if not eff_provider:
        if gemini_key:
            eff_provider = "gemini"
        elif openai_key:
            eff_provider = "openai"
        elif anthropic_key:
            eff_provider = "anthropic"
        elif eff_base_url or generic_key:
            eff_provider = "openai_compatible"

    key_map = {
        "gemini": generic_key or gemini_key,
        "openai": generic_key or openai_key,
        "anthropic": generic_key or anthropic_key,
        "openai_compatible": generic_key or openai_key,
    }
    eff_key = key_map.get(eff_provider, generic_key)
    eff_model = model or os.environ.get("SCIFI_VLM_MODEL") or _DEFAULT_MODELS.get(eff_provider, "gemini-2.5-flash")

    if not eff_provider or not eff_key:
        return {
            "available": False,
            "provider": eff_provider or None,
            "model": eff_model,
            "api_key": None,
            "base_url": eff_base_url or None,
            "hint": (
                "No VLM API key configured. Set GEMINI_API_KEY, OPENAI_API_KEY, "
                "ANTHROPIC_API_KEY, or SCIFI_VLM_API_KEY to enable visual VLM inspection."
            ),
        }

    return {
        "available": True,
        "provider": eff_provider,
        "model": eff_model,
        "api_key": eff_key,
        "base_url": eff_base_url or None,
    }


def _strip_json_fences(raw_text: str) -> str:
    """Strip markdown code fences around JSON payloads if present."""
    text = raw_text.strip()
    fence_match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()
    return text


def _parse_findings_json(raw_text: str) -> list[dict[str, Any]]:
    """Parse VLM JSON array response, tolerating surrounding prose or fences."""
    cleaned = _strip_json_fences(raw_text)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
        if isinstance(parsed, dict) and isinstance(parsed.get("findings"), list):
            return [item for item in parsed["findings"] if isinstance(item, dict)]
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, list):
                    return [item for item in parsed if isinstance(item, dict)]
            except json.JSONDecodeError:
                pass
    return []


def _encode_image_b64(image_path: Path) -> tuple[str, str]:
    """Read image bytes and return (base64_str, mime_type)."""
    suffix = image_path.suffix.lower()
    mime = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"
    b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return b64, mime


def _call_gemini(
    prompt: str,
    encoded_images: list[dict[str, str]],
    model: str,
    api_key: str,
    timeout: int,
) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    parts: list[dict[str, Any]] = [{"text": prompt}]
    for img in encoded_images:
        parts.append({"text": f"Image: {img['label']}"})
        parts.append({"inline_data": {"mime_type": img["mime"], "data": img["b64"]}})

    payload: dict[str, Any] = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
    }
    resp = requests.post(url, params={"key": api_key}, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        return "[]"
    text_parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in text_parts if isinstance(p, dict))


def _call_openai(
    prompt: str,
    encoded_images: list[dict[str, str]],
    model: str,
    api_key: str,
    base_url: str | None,
    timeout: int,
) -> str:
    endpoint = (base_url.rstrip("/") if base_url else "https://api.openai.com/v1") + "/chat/completions"
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for img in encoded_images:
        content.append({"type": "text", "text": f"Image: {img['label']}"})
        content.append({"type": "image_url", "image_url": {"url": f"data:{img['mime']};base64,{img['b64']}"}})

    payload: dict[str, Any] = {
        "model": model,
        "temperature": 0.1,
        "messages": [{"role": "user", "content": content}],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        return "[]"
    return str(choices[0].get("message", {}).get("content") or "[]")


def _call_anthropic(
    prompt: str,
    encoded_images: list[dict[str, str]],
    model: str,
    api_key: str,
    timeout: int,
) -> str:
    url = "https://api.anthropic.com/v1/messages"
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for img in encoded_images:
        content.append({"type": "text", "text": f"Image: {img['label']}"})
        content.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": img["mime"], "data": img["b64"]},
            }
        )

    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": 2048,
        "temperature": 0.1,
        "messages": [{"role": "user", "content": content}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    blocks = data.get("content") or []
    return "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")


def inspect_images_with_vlm(
    images: list[dict[str, Any]],
    mode: str = "figure",
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    max_images: int = 8,
    timeout: int = 60,
) -> dict[str, Any]:
    """
    Run multimodal VLM visual inspection on rendered figure or PDF page PNGs.

    Args:
        images: List of preview dicts containing at least `image_path` (and optional `figure_ref`, `page`, `kind`).
        mode: Inspection mode, either `"figure"` (da-vinci) or `"layout"` (sf trim).
        provider: Optional VLM provider (`gemini`, `openai`, `anthropic`, `openai_compatible`).
        model: Optional model identifier override.
        api_key: Optional API key override.
        base_url: Optional OpenAI-compatible base URL override.
        max_images: Maximum number of images to send in the inspection batch.
        timeout: HTTP timeout in seconds.

    Returns:
        Dict with `status`, `provider`, `model`, `images_inspected`, `findings`, and optional `hint`/`error_message`.
    """
    cfg = resolve_vlm_config(provider=provider, model=model, api_key=api_key, base_url=base_url)
    if not cfg["available"]:
        return {
            "status": "SKIPPED_NO_API_KEY",
            "provider": cfg.get("provider"),
            "model": cfg.get("model"),
            "images_inspected": 0,
            "findings": [],
            "hint": cfg.get("hint"),
        }

    encoded_images: list[dict[str, str]] = []
    for item in images[:max_images]:
        raw_path = item.get("image_path")
        if not raw_path:
            continue
        p = Path(raw_path)
        if not p.is_file():
            continue
        b64, mime = _encode_image_b64(p)
        if item.get("figure_ref"):
            label = f"{item['figure_ref']} ({p.name})"
        elif item.get("page") is not None:
            label = f"Compiled PDF Page {item['page']} ({p.name})"
        else:
            label = p.name
        encoded_images.append({"label": label, "b64": b64, "mime": mime})

    if not encoded_images:
        return {
            "status": "SKIPPED_NO_IMAGES",
            "provider": cfg["provider"],
            "model": cfg["model"],
            "images_inspected": 0,
            "findings": [],
        }

    prompt = _LAYOUT_PROMPT if mode == "layout" else _FIGURE_PROMPT
    eff_provider = cfg["provider"]
    eff_model = cfg["model"]
    eff_key = cfg["api_key"]

    try:
        if eff_provider == "gemini":
            raw_reply = _call_gemini(prompt, encoded_images, eff_model, eff_key, timeout)
        elif eff_provider == "anthropic":
            raw_reply = _call_anthropic(prompt, encoded_images, eff_model, eff_key, timeout)
        elif eff_provider in ("openai", "openai_compatible"):
            raw_reply = _call_openai(prompt, encoded_images, eff_model, eff_key, cfg.get("base_url"), timeout)
        else:
            return {
                "status": "ERROR",
                "provider": eff_provider,
                "model": eff_model,
                "images_inspected": len(encoded_images),
                "findings": [],
                "error_message": f"Unsupported VLM provider: {eff_provider}",
            }

        findings = _parse_findings_json(raw_reply)
        return {
            "status": "SUCCESS",
            "provider": eff_provider,
            "model": eff_model,
            "images_inspected": len(encoded_images),
            "findings_count": len(findings),
            "findings": findings,
        }
    except Exception as exc:
        return {
            "status": "ERROR",
            "provider": eff_provider,
            "model": eff_model,
            "images_inspected": len(encoded_images),
            "findings": [],
            "error_message": str(exc),
        }
