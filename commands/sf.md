---
description: Run SciFi Scientific Research & Academic Writing Toolkit (citations, academic prose, math proofs)
argument-hint: "[verify|audit|humanize|derive|compile] [target or arguments]"
---

Run the SciFi scientific research and academic writing toolkit on the target:

1. **Citation & Literature Audit (`alex` / `verify` / `audit`)**: If the user provided a DOI, arXiv/PubMed link, or `.bib` file, verify against Crossref, OpenAlex, arXiv, and DataCite. Report retractions, metadata discrepancies, and clean BibTeX/APA entries.
2. **Academic Prose Humanizer (`human`)**: If the user provided a section of text or asked to humanize/de-AI writing, rewrite into rigorous, objective academic prose following the Master Academic Humanizer protocol. Remove AI hallmarks, em dashes, and fluff while enforcing epistemic hedging and formal tone.
3. **Mathematical Derivation Verifier (`turing`)**: If the user provided mathematical equations or LaTeX derivations, use SymPy to verify symbolic derivations, physical unit consistency, matrix dimensions, limits, convexity, or notation consistency.
4. **LaTeX Compilation (`compile`)**: Compile LaTeX manuscript using `scifi compile` or `scifi_compile_latex` and report errors.
5. **Attribution & Plagiarism (`argus`)**: Scan text or LaTeX for uncredited methods and auto-inject citations.

Arguments: $ARGUMENTS
