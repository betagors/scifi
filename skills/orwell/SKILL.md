---
name: orwell
description: >-
  Orwell Academic Prose & LaTeX Stylometry Engine. Eradicates bloated diction, AI-isms, em dashes,
  and synthetic LaTeX source fingerprints; calibrates guarded voice profiles (presets, exemplar papers,
  or personal corpus) into scifi.toml; and enforces edit-invariant verification on numbers, equations,
  and citation/reference keys.
---

# Orwell: Academic Prose Craft, Voice Calibration & Edit-Invariant Guard

Audit and refine academic prose and `.tex` source markup while preserving the author's calibrated voice and verifying that no factual or symbolic anchors change.

## Step 1: Run Programmatic Forensic Audit First

Before manually editing `.tex` files, run `scifi_audit_orwell` (MCP) or `uv run sf orwell <path>` (CLI) to detect exact `file:line` flags across all 8 dimensions:
1. **List Environments**: `\item \textbf{...}:` clones ($R_{\mathrm{IB}} \ge 0.80$, item length $\mathrm{CV} < 0.15$).
2. **Document Preamble**: Unused or kitchen-sink packages, saturated `linkcolor=blue, citecolor=blue`.
3. **Tabular Markup**: Unweighted specs (`cccc`, `lcccc`) lacking `tabular*`/`tabularx`/`p{...}`/`\makecell`.
4. **Macro Abstraction**: $\mu_{\mathrm{macro}} \to 0$ when canonical math expansions (`\mathbb`, `\mathcal`, `\mathbf`) repeat $\ge 8$ times without `\newcommand` / `\DeclareMathOperator`.
5. **Math Syntax**: In-equation `\text{where }`, `$k$-th`, trapped punctuation (`$x.$`), un-scoped subscripts (`$W_{loss}$` -> `$W_{\mathrm{loss}}$`), unspaced differentials (`\,dx`).
6. **Prose Stylometry**: Kobak et al. excess AI words, em-dashes (`—`, `---`), and low sentence burstiness ($B_{\mathrm{length}} < 0.28$).
7. **Presentation & Reviewer Flags**:
   - *Compound Method Naming & `\texttt`*: Over-engineered multi-segment names (`Lya-BiMAPPO-MaxSNR`) and monospace method names in prose. Prefer one concise method name and descriptive baseline/ablation labels (e.g., `L-MAPPO with equal CPU allocation`).
   - *Abstract Overload & Boldness*: Word count ($>220$/$250$), inline math ($>6$), big-O expressions ($\ge 2$), numeric result density ($>8$), and explicit `\textbf`/`\bfseries` inside the abstract. Note: `\documentclass[journal]{IEEEtran}` sets abstract text in bold by template design—do not override class typography.
   - *Inline Math Density*: Paragraphs with $\ge 12$ inline math segments and math/word ratio $> 0.12$, or sentences defining $\ge 4$ symbols inline. Never remove equations to look less synthetic; move substantial definitions into displayed equations.
   - *Heading & Contribution Complexity*: Section/theorem/contribution titles $>7$–$8$ words, chaining $\ge 3$ results, or embedding `\ref`/theorem lists.
   - *Absolutist Adjectives*: High density ($>6/1\text{k}$ words) or placement in titles/abstract of *exact, explicit, unconditional, analytical, assumption-free, strictly, zero-duality-gap, rigorous, provable, guarantee, certify, deterministic, closed-form*.
   - *Transition Repetition*: Repeated sentence openers (*Furthermore, Moreover, Consequently, Additionally, Conversely, Notably, Crucially, Rather than*, `To <verb>,`).
   - *Font Pairing*: Times-compatible body text (`IEEEtran`, `times`, `newtxtext`) paired with Computer Modern math; test `\usepackage{newtxtext,newtxmath}` after `amsmath`.
   - *Repeated Sentences*: Exact duplicate sentences of $\ge 8$ words.
8. **Abbreviation Hygiene**: First-occurrence definitions in both abstract and main text, one-/two-use abbreviations, invented/blended algorithm acronyms (`Lya-BiMAPPO`), compound variant labels (`Safe-Pure-MAPPO`), and sentence-level abbreviation overload ($\ge 4$ acronyms in one sentence).

**Target:** Human Authenticity Score $\ge 80/100$ (`AUTHENTIC_HUMAN_BASELINE`).

> [!NOTE]
> **Confounder Guardrail:** Non-native English (ESL) phrasebanks can depress $B_{\mathrm{length}}$, and conference templates (IEEE/ACM/Springer) often supply default preambles. Corroborate stylometric flags with source-level metrics ($\mu_{\mathrm{macro}}$, $R_{\mathrm{IB}}$, $\rho_{\mathrm{math\_text}}$).

---

## Step 2: Prose & Register Rules (Manual Rewrite Pass)

1. **Strip AI Tropes & Significance Inflation**: Remove *delve, pivotal, intricate, crucial, notably, underscores, showcasing, tapestry, testament, beacon, groundbreaking, seamless, realm, multifaceted, meticulous*, and filler openers (*"It is crucial/worth noting that..."*, *"marks a paradigm shift"*). Remove redundant `\subsection` wrap-up paragraphs and pre-equation transitions (*"Moreover,"*, *"Crucially,"*).
2. **Punctuation & Cadence**: Replace em-dashes (`—`, `---`) with commas, colons, or parentheses. Enforce sentence-length burstiness ($B_{\mathrm{length}} > 0.55$) by alternating concise empirical assertions (8–12 words) with multi-clause analytical sentences (28–42 words). Break uniform 3-part paragraphs ($\sigma_{\mathrm{para}} > 45$ words).
3. **Objectivity & Voice**: Use impersonal passive voice for methodology/experiments where appropriate (*"The ablation study was conducted..."*), epistemic hedging (*may, appears to, suggests, indicates*), Latinate verbs over phrasal verbs (*investigate* vs *look into*), and precise quantification over vague adjectives (*substantial, marginal*). Keep terminology consistent (no synonym hopping).
4. **Abbreviation & Acronym Cleanup Policy**:
   - **Preserve standard scientific abbreviations** (e.g., `UAV`, `MEC`, `MAPPO`, `PPO`, `KKT`, `CBF`, `QCQP`, `CTDE`, `LoS`, `SNR`), defining each at first occurrence in the **abstract** and again at first occurrence in the **main text**.
   - **Simplify invented algorithm acronyms**: Replace artificially constructed blends (e.g., `Lya-BiMAPPO`) with readable names in prose (e.g., *Lyapunov-guided MAPPO*) and a short label (`L-MAPPO`) only where needed in figures/tables.
   - **Standardize compound variant labels**: Replace hyphenated ablation/baseline stacks (`Penalty-BiMAPPO`, `Safe-Pure-MAPPO`, `Lya-BiMAPPO-MaxSNR`) with descriptive experimental labels (*MAPPO (penalty-based)*, *MAPPO (safety-filtered)*, *Proposed method (Max-SNR association)*).
   - **Remove one-/two-use abbreviations**: Do not introduce abbreviations for concepts used only once or twice; keep their full names.
   - **Avoid abbreviation overload**: Do not stack 4+ abbreviations in a single sentence when spelling out secondary concepts in ordinary prose is clearer. If adding a Nomenclature section (only when template/page budget permits), separate **abbreviations** from **mathematical notation**.

---

## Step 3: LaTeX Source Refactoring Rules

- **Lists**: Convert routine `\item \textbf{Title}: Clause.` blocks to prose or vary item lead-ins and lengths ($\mathrm{CV} > 0.40$).
- **Display Math**: End equations with `,` or `.` and move `where ...` definitions into body prose (`\noindent where ...`).
- **Inline Math & Subscripts**: Write `$i$th` instead of `$i$-th`; move trailing punctuation outside `$...$`; scope multi-letter subscripts (`$W_{\mathrm{loss}}$`, `$\mathcal{L}_{\mathrm{reg}}$`); insert `\,` before differentials (`\int f(x)\,dx`) and `\!` at multi-integrals/expectations.
- **Macros & Tables**: Define semantic macros (`\newcommand{\R}{\mathbb{R}}`, `\DeclareMathOperator{\argmax}{arg\,max}`) and manage table widths explicitly (`tabularx`, `p{...}`, `\cmidrule(lr){...}`).

---

## Step 4: Voice Calibration & Edit-Invariant Guard

- **Calibrate Voice (`sf orwell calibrate` / `scifi_calibrate_orwell`)**:
  - Zero-corpus preset: `uv run sf orwell calibrate --preset {terse-systems|formal-theory|narrative-science|balanced}`
  - Exemplar papers: `uv run sf orwell calibrate --exemplar <exemplar_dir>`
  - Personal corpus (clamped against flat burstiness / AI tropes): `uv run sf orwell calibrate <past_papers_dir>`
  - Hybrid (keep your macros, use preset cadence): `uv run sf orwell calibrate <past_papers_dir> --notation-only --blend-preset terse-systems`
- **Verify Edit Invariants (`sf orwell verify-edit` / `scifi_verify_edit_invariants`)**:
  - After any prose rewrite, run `uv run sf orwell verify-edit <before> <after>` to confirm zero altered numbers, math expressions, or `\cite{}`/`\ref{}`/`\label{}` keys.

## Output Rule
When asked to rewrite text directly, output **only** the revised text without conversational filler unless an audit report was requested.
