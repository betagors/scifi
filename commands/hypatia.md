---
description: Synthesize literature, inspect full-text baselines, and construct novelty matrices
argument-hint: "[DOI|arXiv ID|topic|path/to/paper.pdf]"
---

Execute the `hypatia` skill on `$ARGUMENTS`.

- If given a **DOI or arXiv ID**: fetch the full-text open-access PDF via Unpaywall or arXiv, extract the mathematical problem formulation, system assumptions, and stated limitations, then construct a structured technical Delta-Novelty Matrix comparing it against the user's manuscript.
- If given a **local PDF path**: skip the fetch step and run extraction directly.
- If given a **topic or set of references**: synthesize them into a thematic taxonomy suitable for the Related Work section, grouping by paradigm rather than chronology.
- If given **two identifiers or paths** (e.g. `draft.tex baseline.pdf`): produce a side-by-side Delta-Novelty Matrix with gap-to-contribution narrative paragraphs ready to paste into the paper.
