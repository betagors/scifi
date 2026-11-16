# SciFi Academic & Scientific Writing Rules

Always-on invariants for SciFi. Detailed rubrics live in `skills/<name>/SKILL.md` and `@scholar`, `@argus`, `@scribe`, `@theorist`, `@auditor`, `@shannon`.

## 1. Citation & Bibliographic Integrity
- **Zero Hallucination:** Never fabricate citations, DOIs, authors, venues, or dates.
- **Zotero-First & Verification:** Check Zotero (`scifi_zotero_status`, `scifi_zotero_search`, `scifi_zotero_get_annotations`) before remote searches; verify `.bib` entries and retractions via `alex` (`scifi_verify_citation`, `scifi_audit_bib`).
- **Attribution:** Credit named methods to primary literature via `argus` (`@argus`).

## 2. Academic Prose & LaTeX Source Humanization
- **Orwell Academic Prose & Stylometry Protocol:** Use `orwell` (`@scribe`, `sf orwell`, `scifi_audit_orwell`) to strip AI clichés, em dashes, and synthetic LaTeX, calibrate voice, and run `sf orwell verify-edit`.
- **LaTeX & Acronyms:** Define non-universal acronyms once in abstract and body; use `\newcommand`, prose `where`, and `$W_{\mathrm{loss}}$`.

## 3. Mathematical & Theoretical Rigor
- **Symbolic & Simulation Rigor:** Verify derivatives, steps, units, shapes, limits, and convexity via `turing` (`@theorist`); validate curves via `gauss` without conflating fits with uncertified constants; report bottleneck complexity and solver.

## 4. Adversarial Peer Review & Methodology
- **Falsification & Baselines:** Surface unstated assumptions and separate oracle bounds from heuristics via `popper` (`@auditor`); cite recent SOTA (`hypatia`), caveat cross-paper runtimes, and explain invariant columns.

## 5. LaTeX Typesetting & Compilation
- **Clean Build:** Keep notation uniform and compile via `compiler` (`scifi_compile_latex`) with zero undefined refs.

## 6. Title, Abstract & Academic SEO Optimization
- **5-Beat Abstracts & SEO:** Use `shannon` (`@shannon`) to front-load keyphrases (<65 chars), write 150–220 word 5-beat abstracts, keep keyword overlap <35%, and verify Triage Score.

## 7. Visual & Scientific Figure Accessibility
- **Figures:** Enforce vector plots, $\ge 300\text{ DPI}$ rasters, body discussion for every `(a)`/`(b)`/`(c)`, and colorblind-safe palettes via `da-vinci` (`scifi_audit_figures`).

## 8. Page Budget & Typographic Micro-Trimming
- **No Squeeze Hacks:** Never use negative `\vspace` or margin hacks; prune widow lines and condense venues via `layout` (`scifi_trim_budget`).

## 9. Theorem–Proof & Appendix Completeness
- **Zero Orphan Claims:** Every theorem, lemma, and proposition requires an inline proof or verified appendix pointer with full hypotheses via `euclid` (`scifi_audit_proofs`).

## 10. Conference Reproducibility & Open Science
- **Reproducibility:** Disclose seeds, separated variance sources, tolerances, and compute, and scrub URLs for double-blind review via `bacon` (`scifi_audit_reproducibility`).

## 11. Author Rebuttal & Point-by-Point Revisions
- **4-Beat Rebuttal:** Structure responses in 4 beats and generate section diffs via `rebuttal` (`scifi_format_rebuttal`, `scifi_diff_manuscript`).

## 12. Academic Paper Packaging & Submission Suite
- **Submission Bundles:** Generate cover letters, character-checked highlights, unblinded title pages, and anonymous code ZIPs via `submission` (`scifi_prepare_submission_bundle`).

## 13. Token-Efficient Dataset Inspection & Reading
- **Inspect Schema First:** Never `read_file` or `cat` raw datasets (`.csv`, `.tsv`, `.jsonl`, `.json` >32 KB, `.parquet`, `.feather`, `.sqlite`, `.db`, `.xlsx`, `.h5`, `.npz`); run `scifi_datasets_inspect` (`sf datasets inspect`) first.

## 14. File Size & Modularity
- Keep source and test files under ~300 lines; split cleanly before adding major logic.

## 15. Editing Efficiency
- Batch non-contiguous edits to one file into a single multi-chunk diff.
