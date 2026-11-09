---
name: hypatia
description: Literature synthesis, competitive benchmarking, and delta-novelty matrix generation. Extracts technical formulations, mathematical assumptions, and stated limitations from open-access PDFs and related works to build robust Related Work taxonomies and gap analyses.
---

# Hypatia: Literature Synthesis & Competitive Benchmarking

The `hypatia` skill enables deep literature synthesis, competitive benchmarking, and delta-novelty matrix generation. It retrieves open-access scientific PDFs (via arXiv, Unpaywall, OpenAlex) and extracts key technical sections (Abstract, System Model/Methodology, Limitations & Conclusions) so that AI agents can construct gap analyses grounded directly in literature text.

## When to Use
- Comparing a draft against competing baseline papers.
- Fetching and parsing open-access research papers via DOI or arXiv identifier.
- Ingesting local PDF papers to extract deep mathematical assumptions and limitations.
- Synthesizing related works into thematic taxonomies rather than shallow chronological summaries.
- Building a multi-variable Delta-Novelty Matrix for Introduction and Related Work sections.
- Extracting exact mathematical assumptions, system models, and stated limitations directly from baseline PDFs.

---

## Native MCP Tools

Invoke the native SciFi MCP tools directly:

### 1. `scifi_fetch_paper_pdf`
Download an open-access research PDF by DOI or arXiv ID.

```json
{
  "identifier": "1706.03762",
  "output_dir": "workspace/papers",
  "email": "researcher@university.edu"
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `identifier` | string | Yes | DOI (e.g. `"10.1109/TWC.2023.3291234"`) or arXiv ID (e.g. `"1706.03762"` or `"2301.12345"`) |
| `output_dir` | string | No | Destination directory for downloaded PDF (default: `"workspace"`) |
| `email` | string | No | Contact email for polite OpenAlex/Unpaywall registry requests |

### 2. `scifi_extract_pdf_text`
Extract structured technical sections from a scientific PDF.

```json
{
  "pdf_path": "workspace/papers/1706.03762.pdf",
  "max_pages": 20,
  "max_section_length": 15000
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `pdf_path` | string | Yes | Absolute or relative path to the PDF file |
| `max_pages` | integer | No | Maximum number of pages to parse (default: 20) |
| `max_section_length` | integer | No | Maximum character length per section (default: 15000, 0 for unlimited) |

Returns structured sections:
- `abstract`: Primary problem statement and contribution summary.
- `system_model_or_method`: Mathematical formulation, state equations, and algorithms.
- `limitations_and_conclusion`: Stated bounds, trade-offs, and open challenges.
- `raw_sample`: Initial extracted excerpt for fast inspection.

### 3. `scifi_map_literature` with Full-Text Gap Mining
Crawl lineage while automatically resolving full-text PDFs (locally or via OA) to mine grounded research gaps.

```json
{
  "query": "1706.03762",
  "depth": 2,
  "max_papers": 25,
  "extract_fulltext": true,
  "pdf_dir": "workspace/papers",
  "auto_fetch_pdf": true
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `query` | string | Yes | Seed paper title, DOI, or arXiv ID |
| `depth` | integer | No | Traversal hops (default: 2) |
| `max_papers` | integer | No | Maximum papers to discover (default: 25) |
| `extract_fulltext` | boolean | No | Enable full-text section gap mining (default: true) |
| `pdf_dir` | string | No | Local directory with downloaded PDFs to match against |
| `auto_fetch_pdf` | boolean | No | Automatically download OA PDFs via arXiv/Unpaywall |

---

## CLI Usage

Run full-text grounded literature reviews directly from the terminal:

```bash
# Report with local PDF matching and auto open-access PDF downloading
sf literature report "10.1109/TWC.2023.3291234" --pdf-dir workspace/papers --auto-fetch-pdf

# Interactive map with full-text section extraction
sf literature map "2301.12345" --pdf-dir workspace/papers --open
```

---

## Analytical Playbooks

### 1. Delta-Novelty Matrix Formulation
When contrasting the proposed paper with a baseline, never settle for superficial summaries. Construct a concrete technical delta table:

| Evaluation Dimension | Baseline Work [Ref] | Proposed Approach | Exact Technical Delta |
|---|---|---|---|
| **Theoretical Paradigm** | Heuristic scheduling | Potential Game | Replaces ad-hoc rules with equilibrium guarantees |
| **State Coupling / Mobility** | 2D static placement | 3D continuous trajectory | Extends feasibility to full kinematic state space |
| **Scalability / Complexity** | $O(N^2)$ per iteration | $O(1)$ asymptotic (MFG) | Eliminates curse of dimensionality via statistical distribution |
| **Information Constraints** | Centralised global CSI | Local partial state | Practical under realistic channel-estimation constraints |
| **Objective Function** | Throughput maximisation | Age-of-Information + energy | Jointly captures freshness and sustainability trade-offs |

*Rule:* Populate every cell directly from extracted paper sections—never from assumptions.

### 2. Gap-to-Contribution Narrative
Structure Related Work narratives into three precise transitions:

1. **Thematic Grouping:**
   > *"Recent advances in [Topic] broadly fall into two categories: [Category A], which ..., and [Category B], which ..."*
2. **The Limitation Bridge:**
   > *"While [A] addresses parameter $\alpha$, it fundamentally relies on assumption $\beta$, which breaks down when $\gamma \to \infty$ because ..."*
3. **The Proposed Resolution:**
   > *"In contrast, our proposed formulation bypasses this bottleneck by establishing [formal claim], thereby [direct benefit]."*

---

## Status Codes & Agent Actions

| Status Code | Meaning | Agent Action |
|---|---|---|
| `SUCCESS` (fetch) | PDF successfully downloaded | Proceed to `scifi_extract_pdf_text`. |
| `NO_OA_PDF` | Paper indexed but no open-access PDF URL found | Prompt user for local PDF copy or alternative DOI/arXiv ID. |
| `NOT_FOUND` | Identifier not recognized by registries | Check format (`10.xxxx/...` or `YYMM.NNNNN`) with `scifi_verify_citation`. |
| `DOWNLOAD_FAILED` | Remote server rejected stream | Retry or ask user for local copy. |
| `SUCCESS` (extract) | Sections parsed successfully | Extract mathematical model, construct Delta-Novelty Matrix. |
| `ERROR` | Corrupted PDF or parse exception | Inform user; fallback to raw text or abstract review. |
