---
name: alex
description: Verify academic citations via DOI, web links (arXiv, PubMed, OpenAlex, publisher URLs), or audit entire .bib files against authoritative registries (Crossref, OpenAlex, arXiv, DataCite). Detects retracted papers, errata, publisher notices, title/author/year discrepancies, and generates standardized BibTeX and APA citations.
---

# Alex: Academic Literature & Citation Verifier

The `alex` skill validates scientific references and literature citations against global bibliographic registries (Crossref, OpenAlex, arXiv, and DataCite). It provides verification for individual links/DOIs and batch auditing for `.bib` bibliographies.

## Core Capabilities

1. **Identifier & Link Resolution**:
   - DOIs: `10.1038/s41586-020-2649-2`, `https://doi.org/...`
   - arXiv: `https://arxiv.org/abs/1706.03762`, `arXiv:1706.03762`, or bare ID
   - PubMed: `https://pubmed.ncbi.nlm.nih.gov/12345678/` or `PMID:12345678`
   - Publisher & Web URLs: Follows HTTP redirects, parses Highwire / Dublin Core `<meta>` tags (`citation_doi`, `citation_title`, `dc.identifier`).
2. **Retraction & Errata Screening**:
   - Queries Crossref Crossmark updates and OpenAlex's retraction index.
   - Immediately alerts if a cited work has been retracted, withdrawn, or has published corrections.
3. **Discrepancy & Typo Auditing**:
   - Compares user/BibTeX claimed title, first author, year, and venue against official registry data.
   - Detects halluncinated citations, incorrect years (e.g. preprint vs journal publication), and severe title mismatches.
4. **Standardized Citation Formatting**:
   - Produces clean BibTeX entries with predictable citekeys (`[FirstAuthor][Year][TitleWord]`).
   - Generates APA 7th edition formatted text citations.
5. **Full `.bib` File Auditing & Sanitization**:
   - Audits every entry in a `.bib` file.
   - Fills in missing DOIs by searching official registries by title.
   - Exports a sanitized `.bib` file with retraction warnings embedded as comments.

---

## Command-Line Usage

Run via Python in the repository virtual environment:

### 1. Verify a Single DOI or Link

```bash
uv run scifi verify 10.1038/s41586-020-2649-2
```

Outputs a rich markdown summary card containing verification status, metadata, citation count, APA citation, and BibTeX.

#### With Claimed Discrepancy Checking
```bash
uv run scifi verify 10.1038/s41586-020-2649-2 \
  --claimed-title "Array programming in NumPy" \
  --claimed-year 2019 \
  --claimed-author "Harris"
```

#### Alternate Output Formats (`markdown`, `bibtex`, `apa`, `json`, `text`)
```bash
uv run scifi verify https://arxiv.org/abs/1706.03762 --format bibtex
uv run scifi verify 10.1038/s41586-020-2649-2 --format apa
uv run scifi verify 10.1016/S0140-6736(97)11096-0 --format json
```

### 2. Audit a BibTeX File

Audit all entries in a `.bib` file and output a comprehensive Markdown report:

```bash
uv run scifi audit references.bib --output-report audit_report.md --output-bib clean_references.bib
```

### 3. Search Official Registries by Title

```bash
uv run scifi search "Attention is all you need" --verify
```

---

## Python API Usage

```python
from scifi.citation_verifier import verify_citation, audit_bib_file

# Verify a DOI or URL
result = verify_citation("10.1038/s41586-020-2649-2")
print(result.status)          # VerificationStatus.VERIFIED or RETRACTED
print(result.is_retracted)     # False
print(result.to_bibtex())      # Standard BibTeX
print(result.to_apa())         # APA 7th Edition

# Audit a .bib file
report = audit_bib_file("my_paper.bib")
print(f"Total: {report.total_entries}, Retracted: {report.retracted_count}")
print(report.summary_markdown())
```

---

## Verification Status Codes

- 🟢 **VERIFIED**: Active, peer-reviewed, or preprint work found and verified in registry.
- 🚨 **RETRACTED**: Work was formally retracted by the publisher or authors.
- ⚠️ **ERRATA_EXISTS**: Formal correction or expression of concern published.
- 🟠 **MISMATCH**: Citation exists but title/author/year deviates significantly from claimed reference.
- ❌ **UNRESOLVED**: Could not locate DOI or link in registries.
