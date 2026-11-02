---
name: alex
description: Verify academic citations via DOI, web links (arXiv, PubMed, OpenAlex, publisher URLs), or audit entire .bib files against authoritative registries (Crossref, OpenAlex, arXiv, DataCite). Detects retracted papers, errata, publisher notices, title/author/year discrepancies, and generates standardized BibTeX and APA citations.
---

# Alex: Academic Literature & Citation Verifier

The `alex` skill validates scientific references and literature citations against authoritative global bibliographic registries (Crossref, OpenAlex, arXiv, and DataCite). It provides native MCP tools for verifying individual links/DOIs, searching academic literature, and batch-auditing `.bib` bibliographies.

## Core Capabilities

1. **Identifier & Link Resolution**: Resolves DOIs, arXiv URLs/IDs, PubMed links/PMIDs, and publisher URLs via official registries.
2. **Retraction & Errata Screening**: Queries Crossref Crossmark updates and OpenAlex retraction indices to alert if a work was retracted, withdrawn, or amended.
3. **Discrepancy Auditing**: Compares claimed author, title, publication year, and venue against official registry data to detect citation hallucination and drift.
4. **Standardized Citation Formatting**: Generates normalized BibTeX entries (`[Author][Year][Word]`) and APA 7th edition references.
5. **Batch `.bib` File Auditing & Sanitization**: Audits entire bibliographies, reports status counts, and exports sanitized clean `.bib` files.

---

## Native MCP Tools

Invoke the native SciFi MCP tools directly:

### 1. `scifi_verify_citation`
Verify a single publication reference, DOI, or URL.

```json
{
  "identifier": "10.1038/s41586-020-2649-2",
  "claimed_title": "Array programming in NumPy",
  "claimed_author": "Harris",
  "claimed_year": 2020,
  "claimed_venue": "Nature"
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `identifier` | string | Yes | DOI, arXiv URL/ID (`arxiv:1706.03762`), PubMed URL/PMID, or publisher URL |
| `claimed_title` | string | No | Author's claimed title in manuscript (for mismatch auditing) |
| `claimed_author` | string | No | Author's claimed primary author surname (for mismatch auditing) |
| `claimed_year` | integer | No | Author's claimed publication year (for mismatch auditing) |
| `claimed_venue` | string | No | Claimed publication journal or conference venue |

### 2. `scifi_audit_bib`
Audit an entire `.bib` bibliography file.

```json
{
  "bib_path": "path/to/references.bib",
  "output_bib": "path/to/clean_references.bib"
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `bib_path` | string | Yes | Path to the `.bib` file to audit |
| `output_bib` | string | No | Destination path to write sanitized clean BibTeX with warnings |

### 3. `scifi_search_literature`
Search OpenAlex and academic registries for canonical literature by title, keyword, or topic.

```json
{
  "query": "Attention Is All You Need",
  "limit": 5
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `query` | string | Yes | Title, author, or research topic search query |
| `limit` | integer | No | Maximum number of results (default: 5) |

---

## Status Codes & Interpretation

| Status Code | Meaning | Agent Action |
|---|---|---|
| 🟢 `VERIFIED` | Publication active and verified in official registry | Safe to cite. Use returned `cite_key` and `bibtex` or `apa`. |
| 🚨 `RETRACTED` | Paper was formally retracted or withdrawn | **Never cite silently.** Alert user immediately; excise claim or cite retraction context. |
| ⚠️ `ERRATA_EXISTS` | Publisher published errata or expression of concern | Check `errata_details`; alert user to review published correction. |
| 🟠 `MISMATCH` | Major discrepancy between claimed metadata and registry | Alert user to title/author/year discrepancy. Suggest corrected metadata. |
| ❌ `UNRESOLVED` | Identifier or URL not located in registries | Search via `scifi_search_literature` by title or request verified DOI from user. |

---

## Remediation Workflow for Agents

1. **Before writing or editing citations:** Call `scifi_verify_citation` for every paper referenced.
2. **When given a bibliography file:** Call `scifi_audit_bib` to generate a full discrepancy and retraction report before compiling.
3. **When identifying seminal papers:** Call `scifi_search_literature` to obtain the verified DOI and canonical BibTeX.
