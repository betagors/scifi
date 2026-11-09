"""Theorem-Proof and Appendix Completeness Sentinel (euclid)."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from scifi.latex.project import resolve_latex_project
from scifi.proofs.models import (
    ProofAuditResult,
    ProofIssueCategory,
    TheoremProofRecord,
)

RE_ENV_START = re.compile(
    r"\\begin\{(theorem|lemma|proposition|corollary)\}\s*(?:\[(.*?)\])?",
    re.IGNORECASE,
)
RE_LABEL = re.compile(r"\\label\s*\{\s*([^}]+?)\s*\}")
RE_REF = re.compile(r"\\ref\s*\{\s*([^}]+?)\s*\}")
RE_ALL_LABELS = re.compile(r"\\label\s*\{\s*([^}]+?)\s*\}")


def audit_latex_proofs(tex_path: Path | str) -> ProofAuditResult:
    """Audit LaTeX manuscript for orphan theorems and verify appendix proof pointers."""
    target_path = Path(tex_path)
    if target_path.exists():
        try:
            proj = resolve_latex_project(target_path)
            full_text = proj.merged_text
        except Exception:
            full_text = target_path.read_text(encoding="utf-8", errors="replace")
    else:
        full_text = str(tex_path)

    # Strip comments
    clean_lines = [re.sub(r"(?<!\\)%.*$", "", line) for line in full_text.splitlines()]
    clean_text = "\n".join(clean_lines)

    # Collect all defined labels in the manuscript
    all_defined_labels = set(RE_ALL_LABELS.findall(clean_text))

    theorems: list[TheoremProofRecord] = []
    issues: list[dict[str, Any]] = []

    # Find theorem environments
    env_matches = list(RE_ENV_START.finditer(clean_text))

    for idx, em in enumerate(env_matches):
        env_type = em.group(1).lower()
        title = em.group(2) or ""
        start_pos = em.start()

        # Find matching \end{env_type}
        end_env_pattern = rf"\\end\{{{env_type}\}}"
        end_m = re.search(end_env_pattern, clean_text[em.end() :], re.IGNORECASE)
        if not end_m:
            continue
        env_body_end = em.end() + end_m.end()
        env_body = clean_text[start_pos:env_body_end]

        label_m = RE_LABEL.search(env_body)
        thm_label = label_m.group(1) if label_m else f"{env_type}_{idx+1}"

        # Determine span of trailing prose (up to next theorem or next \section)
        next_env_pos = env_matches[idx + 1].start() if idx + 1 < len(env_matches) else len(clean_text)
        next_sec_m = re.search(r"\\(?:section|chapter)\b", clean_text[env_body_end:next_env_pos])
        trailing_end = env_body_end + (next_sec_m.start() if next_sec_m else (next_env_pos - env_body_end))
        trailing_prose = clean_text[env_body_end:trailing_end]

        combined_scope = env_body + "\n" + trailing_prose

        # 1. Check for inline proof
        has_inline_proof = bool(re.search(r"\\begin\{proof\}", trailing_prose[:1000], re.IGNORECASE))

        # 2. Check for appendix reference in trailing prose
        ref_appendix_label = None
        appendix_verified = False

        app_ref_pattern = re.compile(
            r"(?:proof|detailed|derivation|argument|deferred|left to).*?(?:appendix|section|supp)\s*~?\\ref\{([^}]+)\}",
            re.IGNORECASE | re.DOTALL,
        )
        app_m = app_ref_pattern.search(trailing_prose)
        if app_m:
            ref_appendix_label = app_m.group(1).strip()
            if ref_appendix_label in all_defined_labels:
                appendix_verified = True
            else:
                issues.append({
                    "category": ProofIssueCategory.UNRESOLVED_APPENDIX_PROOF.value,
                    "severity": "CRITICAL",
                    "theorem": thm_label,
                    "message": f"{env_type.capitalize()} '{thm_label}' defers proof to label '{ref_appendix_label}', but this label is not defined in any loaded LaTeX file.",
                    "recommendation": f"Add \\label{{{ref_appendix_label}}} in the appendix or update the pointer to a valid appendix label.",
                })

        record = TheoremProofRecord(
            env_type=env_type,
            label=thm_label,
            name_or_title=title,
            has_inline_proof=has_inline_proof,
            referenced_appendix_label=ref_appendix_label,
            appendix_verified=appendix_verified,
        )
        theorems.append(record)

        if not has_inline_proof and not appendix_verified and not ref_appendix_label:
            issues.append({
                "category": ProofIssueCategory.ORPHAN_THEOREM.value,
                "severity": "CRITICAL",
                "theorem": thm_label,
                "message": f"Orphan {env_type.capitalize()} '{thm_label}': Stated without an inline \\begin{{proof}} or an explicit cross-reference to an appendix proof.",
                "recommendation": "Provide an inline proof or explicitly specify 'The proof is deferred to Appendix~\\ref{...}'.",
            })

    orphan_count = sum(1 for t in theorems if not t.has_inline_proof and not t.appendix_verified)

    return ProofAuditResult(
        status="SUCCESS",
        total_theorems=len(theorems),
        orphan_theorems=orphan_count,
        theorems=theorems,
        issues=issues,
    )
