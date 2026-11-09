# SciFi Academic & Scientific Writing Rules

These rules are active whenever the SciFi plugin is enabled to enforce academic standards across literature verification, mathematical rigor, peer review readiness, and LaTeX manuscript typesetting.

## 1. Citation & Bibliographic Integrity
- **Zero Hallucination:** Never fabricate or guess academic citations, DOIs, author names, venues, or publication dates.
- **Mandatory Verification:** Use the `alex` skill to cross-reference DOIs, literature links, and `.bib` entries against authoritative registries (Crossref, OpenAlex, arXiv, DataCite).
- **Attribution & Plagiarism Audit:** Use the `argus` skill to detect uncredited algorithms, models, and techniques, audit attribution gaps, and triage scientific literature from informal web articles.
- **Retraction & Errata Vigilance:** Actively flag retracted papers, publisher expressions of concern, or errata when auditing bibliographies.
- **Standard Formatting:** Output verified entries with consistent BibTeX keys (`[Author][Year][Word]`) or APA 7th edition formatting.

## 2. Academic Prose & LaTeX Source Humanization
- **Master Academic Humanizer Protocol:** Use the `human` skill (`sf human` / `scifi_audit_human`) to eradicate synthetic AI writing hallmarks, buzzwords, marketing fluff, and autoregressive LaTeX markup fingerprints.
- **Eliminate AI Tropes (Kobak et al. Markers):** Strip characteristic synthetic vocabulary (*delve*, *pivotal*, *intricate*, *crucial*, *notably*, *underscores*, *showcasing*, *testament*, *tapestry*, *beacon*, *groundbreaking*, *it is crucial to note*) and formulaic pre-equation transitions.
- **Punctuation & Burstiness Standards:** Avoid conversational em dashes (`—` or `---`); replace with parentheses, commas, or discrete clauses. Enforce high sentence-length burstiness ($B_{\mathrm{length}} > 0.55$) by alternating concise empirical assertions with multi-clause analytical sentences.
- **LaTeX Source-Code Ergonomics:** Avoid `\item \textbf{...}:` list clones ($R_{\mathrm{IB}} < 0.80$, item length $\mathrm{CV} > 0.40$); define reusable semantic macros ($\mu_{\mathrm{macro}} > 0$) instead of repeating raw canonical expansions; place `where ...` explanations in body prose rather than inside display equations ($\rho_{\mathrm{math\_text}} = 0$); scope multi-letter subscripts in upright font (`$W_{\mathrm{loss}}$`); and insert thin spaces (`\,`) before differentials.
- **Scholarly Register:** Enforce disciplined academic voice: passive constructions where standard in scientific disciplines, epistemic hedging (*results indicate*, *under assumption $\mathcal{A}$*), and precise quantitative descriptions.

## 3. Mathematical & Theoretical Rigor
- **Symbolic Verification First:** Before asserting mathematical proofs, gradients, or optimality conditions in manuscript text, verify them symbolically via the `turing` skill (SymPy).
- **Dimensional Homogeneity:** Verify that all additive terms and equation equalities maintain consistent physical units (pint/SymPy).
- **Matrix & Tensor Shapes:** Verify that matrix products, vector inner/outer products, and tensor contractions have strictly compatible shapes.
- **Asymptotic & Boundary Conditions:** Check analytical limits ($x \to 0$, $N \to \infty$) and convexity properties (positive semi-definite Hessian).
- **Theoretical vs. Numerical Alignment:** Verify that closed-form analytical equations match empirical numerical simulations using the `gauss` skill.

## 4. Adversarial Peer Review & Methodology
- **Unstated Assumptions:** Uncover and explicitly document hidden physical or computational assumptions in System Models (e.g., ideal feedback, negligible delay, infinite compute) using the `popper` skill.
- **Fair Baselines:** Validate that experimental comparisons evaluate against modern state of the art rather than outdated or weak baselines.
- **Failure Modes & Sensitivity:** Document boundary conditions and scenarios where proposed methods degrade or fail.

## 5. LaTeX Typesetting & Compilation
- **Notation Consistency:** Maintain uniform symbol definitions and formatting across all sections and equation environments.
- **Clean Compilation:** Use the `compiler` skill to run `latexmk` or `pdflatex`, locate build errors by file and line number, and resolve missing packages or undefined references.

## 6. Title, Abstract & Academic SEO Optimization
- **Keyphrase Front-Loading:** Always place the primary domain search keyphrase within the first 65 characters of the title to avoid search snippet truncation.
- **Citation Sweet-Spot Length:** Target title lengths of 10–14 words (70–110 characters) correlated with higher citation discovery.
- **5-Beat Dual-Audience Abstracts:** Structure abstracts strictly into 150–220 words balancing an accessible lead hook for non-technical/interdisciplinary readers with quantified empirical metrics for expert reviewers.
- **Rule of Three Keyphrase Anchoring:** Anchor primary search keyphrases across context (Beat 1), methodology (Beat 3), and conclusion (Beat 5).
- **Metadata Vocabulary Expansion:** Ensure author keywords share <35% word overlap with the title, broadening the paper's searchable footprint across indexing databases.
- **Empirical Validation:** Use the `shannon` skill (`test_keywords.py`) to verify the 100-point Reviewer Triage Score and search engine collision safety.
