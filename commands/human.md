---
description: Audit and rewrite AI text or LaTeX source code into rigorous, authentic human-authored academic prose
argument-hint: "[text or path/to/draft.tex]"
---

Audit and rewrite the target text or LaTeX manuscript using the `human` skill protocol (`sf human`):

1. **Eradicate AI Prose Hallmarks (Kobak et al. Markers)**: Strip high-displacement synthetic vocabulary (*delve*, *pivotal*, *intricate*, *crucial*, *notably*, *underscores*, *showcasing*, *tapestry*, *testament*), formulaic pre-equation scaffolding (*"Moreover,"*, *"Crucially,"*, *"It is worth noting that"*), and redundant `\subsection` summary wrap-ups.
2. **Eliminate Synthetic LaTeX Source Fingerprints**:
   - De-template `\item \textbf{...}:` list clones ($R_{\mathrm{IB}} < 0.80$) and increase item length variance ($\mathrm{CV} > 0.40$).
   - Extract conversational English (`\text{where }`, `\quad \text{such that}`) out of display equations into body text (`\noindent where ...`).
   - Scope multi-letter textual subscripts in upright font (`$W_{\mathrm{loss}}$` instead of `$W_{loss}$`), move trailing punctuation outside `$...$`, and add thin spaces (`\,`) before differentials (`\,dx`).
   - Introduce authorial `\newcommand` macro abstractions ($\mu_{\mathrm{macro}} > 0$), prune uninvoked preamble packages, and tune tabular column geometry.
3. **Remove Em Dashes & Enforce High Burstiness ($B_{\mathrm{length}} > 0.55$)**: Never use em dashes (`—` or `---`); vary sentence lengths between concise empirical assertions (8–12 words) and complex analytical clauses (28–40 words).
4. **Enforce Scholarly Register**: Apply formal passive constructions where appropriate, disciplined epistemic hedging (*"indicates"*, *"suggests"*, *"under assumption $\mathcal{A}$"*), and SVOCA clarity.

Target text/file: $ARGUMENTS
