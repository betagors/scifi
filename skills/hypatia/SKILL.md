---
name: hypatia
description: Literature synthesis, competitive benchmarking, and delta-novelty matrix generation. Extracts technical formulations, mathematical assumptions, and stated limitations from open-access PDFs and related works to build robust Related Work taxonomies and gap analyses.
compatibility: python3, requests, pypdf
---

## When to Use
- Comparing the user's paper draft against candidate baselines or competing papers.
- Downloading open-access reference papers via DOI or arXiv ID for full-text technical inspection.
- Building a multi-variable Delta-Novelty Matrix for the Introduction or Related Work sections.
- Synthesizing a list of 5–20 papers into orthogonal thematic taxonomies rather than chronological lists.

---

## Standard Tool Procedures

### 1. Fetching Full-Text Open-Access Papers

If the user provides a DOI, arXiv ID, or title of a reference paper to inspect:

```bash
uv run python skills/hypatia/scripts/fetch_oa_pdf.py \
    --id "<DOI_OR_ARXIV_ID>" \
    --out "workspace/baseline.pdf"
```

| Arg | Description |
|---|---|
| `--id` | DOI (e.g. `10.1109/TWC.2023.3291234`) or arXiv ID (e.g. `2301.12345` or `arxiv:2301.12345`) |
| `--out` | Destination path for the downloaded PDF (parent dirs created automatically) |
| `--email` | Email passed to Unpaywall API (default: `researcher@university.edu`) |

**Status codes:** `SUCCESS` · `NO_OA_PDF` · `NOT_FOUND` · `DOWNLOAD_FAILED` · `ERROR`

---

### 2. Extracting Core Technical Sections

Once a PDF is available (downloaded or provided locally):

```bash
uv run python skills/hypatia/scripts/extract_paper_text.py \
    --pdf "workspace/baseline.pdf"
```

Returns a JSON object with:
- `abstract` — first 2 000 chars of the abstract block
- `system_model_or_method` — problem formulation / system model section
- `limitations_and_conclusion` — conclusion and future-work section
- `raw_sample` — first 4 000 chars of the full extracted text

**Status codes:** `SUCCESS` · `ERROR`

---

### 3. Generating the Delta-Novelty Matrix

When comparing a paper against the current draft, **do not produce generic summaries**. Always construct a technical comparison matrix contrasting the following dimensions (adapt to the paper's domain):

| Evaluation Dimension | Baseline Work [Ref] | Proposed Approach | Exact Technical Delta |
|---|---|---|---|
| **Theoretical Paradigm** | Heuristic scheduling | Potential Game | Replaces ad-hoc rules with equilibrium guarantees |
| **State Coupling / Mobility** | 2D static placement | 3D continuous trajectory | Extends feasibility to full kinematic state space |
| **Scalability / Complexity** | $O(N^2)$ per iteration | $O(1)$ asymptotic (MFG) | Eliminates curse of dimensionality via statistical distribution |
| **Information Constraints** | Centralised global CSI | Local partial state | Practical under realistic channel-estimation constraints |
| **Objective Function** | Throughput maximisation | Age-of-Information + energy | Jointly captures freshness and sustainability trade-offs |

Populate every cell from the extracted sections — never fill cells from assumptions.

---

### 4. Drafting the Gap-to-Contribution Narrative

Produce draft-ready paragraphs structured as:

1. **Thematic Grouping:**
   > *"Recent advances in [Topic] broadly fall into two categories: [Category A], which ..., and [Category B], which ..."*

2. **The Limitation Bridge:**
   > *"While [A] addresses parameter $\alpha$, it fundamentally relies on assumption $\beta$, which breaks down when $\gamma \to \infty$ because ..."*

3. **The Proposed Resolution:**
   > *"In contrast, our proposed formulation bypasses this bottleneck by establishing [formal claim], thereby [direct benefit]."*

Always anchor each narrative bridge to a specific assumption or equation extracted from the PDF — cite equation numbers where available.

---

## Output Interpretation

| Status | Meaning | Agent Action |
|---|---|---|
| `SUCCESS` (fetch) | PDF downloaded | Proceed to extraction |
| `NO_OA_PDF` | Paper exists on Unpaywall but has no OA PDF link | Ask user for local PDF or alternative identifier |
| `NOT_FOUND` | Identifier not recognised | Verify DOI/arXiv ID and retry |
| `DOWNLOAD_FAILED` | OA host rejected the stream | Try alternative DOI or direct arXiv fallback |
| `SUCCESS` (extract) | Sections parsed | Build Delta-Novelty Matrix from returned JSON |
| `ERROR` | Parse or network failure | Surface `error` field to user with retry hint |
