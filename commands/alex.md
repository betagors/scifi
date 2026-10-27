---
description: Verify academic citations, validate DOIs, check retractions, and audit .bib files
argument-hint: "[DOI|URL|path/to/references.bib]"
---

Verify academic citations and literature references using the `alex` skill:

- If given a DOI or URL (arXiv, PubMed, publisher link): query Crossref, OpenAlex, arXiv, and DataCite. Report retracted status, expression of concern, errata, and author/title/year fidelity. Provide formatted BibTeX and APA 7th edition outputs.
- If given a `.bib` file: audit every entry, detect missing DOIs, flag retractions, identify discrepancies, and output a structured markdown audit report and sanitized BibTeX file.
- If given a paper title: search authoritative registries and return verified records.

Target: $ARGUMENTS
