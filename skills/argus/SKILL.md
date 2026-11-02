---
name: argus
description: Sentinel for academic attribution, uncredited methods, and plagiarism detection. Scans LaTeX manuscripts or text snippets for uncredited algorithms, models, and techniques, distinguishes canonical scientific literature from informal web/blog sources, generates verified BibTeX citations via OpenAlex/Crossref, and triggers academic reformulation via the human skill.
---

# Argus: Academic Attribution & Plagiarism Sentinel

**Argus** audits academic manuscripts, drafts, and text snippets to prevent unintentional plagiarism, uncredited methods, and improper citation practices.

Unlike commercial string-matching tools (e.g., iThenticate) that are blind to paraphrased concepts or uncredited algorithms, Argus semantically parses methods, verifies attribution proximity, and automatically triages issues into actionable resolutions via the native `scifi_audit_attribution` MCP tool.

---

## When to Use

1. **Auditing Drafts for Uncited Methods:** When a manuscript mentions algorithms, architectures, loss functions, or benchmarks (e.g., *LoRA*, *AdamW*, *Transformer*, *InfoNCE*, *DBSCAN*) without an accompanying citation.
2. **Checking Borrowed Paragraphs / Web Sources:** When text was adapted or copied from an online blog, tutorial, or Medium post, and needs to be either credited to primary literature or completely reformulated into original academic prose.
3. **Pre-Submission Plagiarism & Attribution Audit:** Full-manuscript integrity scan prior to journal or conference submission.
4. **Auto-Fixing Citation Gaps:** Automatically injecting missing `\cite{...}` tags into LaTeX files and appending standardized BibTeX entries to `references.bib`.

---

## Native MCP Tools

Invoke the native SciFi MCP tool directly:

### `scifi_audit_attribution`
Audit a LaTeX manuscript or text file for uncredited methods, algorithms, and plagiarism risks, with optional in-place auto-fixing.

```json
{
  "file_path": "path/to/paper.tex",
  "bib_path": "path/to/references.bib",
  "autofix": false,
  "enable_search": true
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `file_path` | string | Yes | Path to the LaTeX (`.tex`) or text file to audit |
| `bib_path` | string | No | Path to the `references.bib` file (defaults to `references.bib` in the manuscript directory) |
| `autofix` | boolean | No | If `true`, automatically injects `\cite{...}` in the LaTeX file and appends BibTeX to `bib_path` (default: `false`) |
| `enable_search` | boolean | No | Whether to query academic registries (OpenAlex/Crossref) for seminal papers (default: `true`) |

---

## Four-Way Attribution Triage

Argus classifies every flagged passage into one of four states:

| Classification | Meaning | Action Taken |
|---|---|---|
| **`CANONICAL_ACADEMIC`** | Technique or algorithm originating from peer-reviewed/preprint literature. | Queries OpenAlex/Crossref, retrieves canonical paper, formats verified BibTeX, and inserts `\cite{...}`. |
| **`COMMON_KNOWLEDGE`** | Foundational concepts (e.g., *gradient descent*, *Fourier transform*, *backpropagation*). | Suppresses false alarms to keep bibliography concise. |
| **`INFORMAL_WEB`** | Copied or adapted from blog posts, tutorials, or marketing text. | **Branch A:** Trace back to primary literature and cite that.<br>**Branch B:** Dispatches to [`human`](../human/SKILL.md) to rewrite into objective scholarly prose. |
| **`PREPRINT_ALIGNMENT`** | Text overlapping with the author's own preprint or thesis. | Identifies self-reference and advises explicit attribution to avoid self-plagiarism issues. |

---

## Remediation Workflow for Agents

When using Argus within an agent conversation or subagent:

1. **Step 1 — Run Audit:**
   Call `scifi_audit_attribution(file_path="paper.tex", bib_path="references.bib", autofix=False)`.

2. **Step 2 — Triage Findings:**
   - **For `CANONICAL_ACADEMIC` findings:**
     - Verify paper status with `scifi_verify_citation` via the [`alex`](../alex/SKILL.md) skill to confirm it is not retracted.
     - Call `scifi_audit_attribution` with `autofix=True` to insert `\cite{...}` into `paper.tex` and append verified BibTeX to `references.bib`.
   - **For `INFORMAL_WEB` findings:**
     - If the text explains a scientific concept: Search for the root academic paper using `scifi_search_literature` and cite it instead of citing a blog.
     - If the text is general exposition: Call the [`human`](../human/SKILL.md) skill to rewrite the passage from scratch following the Master Academic Humanizer protocol (eradicating AI tropes, blog tone, and conversational em dashes).
