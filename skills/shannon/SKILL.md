---
name: shannon
description: Use when drafting, engineering, or optimizing academic manuscript titles, 5-beat cognitive abstracts, or keyword strategies for journal and conference submission. Applies academic SEO visibility tricks, dual-audience accessibility checks, and empirical search engine validation.
---

# Shannon — Academic Title, Abstract & Keyword Optimization Engine

The `shannon` skill provides an automated, publication-tested protocol to engineer manuscript titles, 5-beat dual-audience abstracts, and non-redundant indexing keywords. It bridges expert scientific rigor with broad accessibility, while applying academic search engine optimization (SEO) techniques to maximize citation velocity and indexing discovery across Google Scholar, Scopus, IEEE Xplore, and Web of Science.

---

## 1. Information Extraction & Context Framing

Before generating titles or abstracts, extract the following 5 parameters from the author's research notes, manuscript draft, or experimental logs:

1. **Practical Real-World Problem (Lay/Interdisciplinary Context):** Why does this problem matter to a broader scientific or engineering audience? Avoid starting with insular subfield jargon.
2. **Specific Technical Bottleneck:** Exactly why do existing methods, algorithms, or frameworks fail or hit a performance limit?
3. **Core Algorithmic / Architectural Innovation:** What is the proposed mechanism, mathematical formulation, or system design?
4. **Quantified Experimental Benchmarks:** Exact numerical improvements (% gains, dB, latency reduction, error bounds) evaluated against modern competitive baselines.
5. **Target Publisher & Venue:** IEEE, Elsevier, Springer Nature, ACM, NeurIPS, etc. (determines controlled vocabulary standards and formatting expectations).

---

## 2. Title Generation Matrix & Academic SEO Tricks

Generate **three distinct structural angles**, each adhering strictly to empirical academic SEO guidelines:

### Academic SEO "Tricks & Hacks" for Titles:
- **Trick 1: Front-Loading Keyphrase (<65 Characters):** Place the primary search keyphrase in the first 65 characters of the title. Google Scholar, ScienceDirect, and browser tab titles truncate after 60–65 characters.
- **Trick 2: Citation Sweet-Spot Length (10–14 Words / 70–110 Characters):** Bibliometric studies demonstrate that papers with 10–14 word titles achieve statistically higher citation velocity than very brief (<8 words) or overly verbose (>16 words) titles.
- **Trick 3: Acronym Guard:** Never lead with an obscure project or algorithm acronym (e.g., *"Q-FEDX for..."*). Searchers and indexing algorithms do not query unpublished acronyms. Always anchor with universal domain keywords (*"Adaptive Federated Optimization via Q-FEDX for..."*).
- **Trick 4: No Punctuation Clutter:** Do not end titles with a period. Avoid question marks or cute slogans.

### The 3 Structural Angles:
1. **Angle A (Declarative / Finding-First):**
   `"[Primary Finding / Quantified Gain] via [Novel Mechanism] for [Application]"`
   *Example:* *"Decentralized Beamforming via Riemannian Optimization for Dynamic Satellite Constellations"*
2. **Angle B (Descriptive / Method-First):**
   `"[Novel Mechanism]: [Methodology] for [Application] under [Constraint]"`
   *Example:* *"Riemannian Manifold Synchronization: An Adaptive Beamforming Framework under Severe Doppler Shift"*
3. **Angle C (Problem-Oriented / Challenge-First):**
   `"[Problem Challenge] in [Domain]: A [Mechanism] Approach"`
   *Example:* *"Doppler Shift Mitigation in Low Earth Orbit Clusters: A Manifold Optimization Approach"*

---

## 3. 5-Beat Dual-Audience Abstract Drafting

The abstract must satisfy two distinct readers simultaneously:
- **The Non-Technical / Interdisciplinary Reader (or Generalist Editor):** Needs to understand the motivation, intuition, and practical significance without cognitive exhaustion.
- **The Expert Peer Reviewer:** Scrutinizes technical bottlenecks, mathematical specificity, and quantified benchmark baselines.

### Structure (Strictly 150–220 Words):
- **Beat 1: Context & Lay-Accessible Problem Hook (1–2 sentences):**
  Ground the domain in concrete physical or operational reality. Keep sentences under 30 words. No unanchored equations ($O(N)$), nested clauses, or hyper-niche jargon.
- **Beat 2: Specific Technical Bottleneck (1 sentence):**
  Use explicit contrastive discourse markers (*"However, existing schemes remain limited by..."*, *"A key bottleneck lies in..."*). Pinpoint the exact theoretical or empirical breakdown.
- **Beat 3: Proposed Method / Mechanism (2–3 sentences):**
  Introduce the core architectural or mathematical formulation using concrete technical nouns (*"algorithm"*, *"framework"*, *"manifold"*, *"formulation"*, *"optimization"*).
- **Beat 4: Quantified Experimental Findings (2 sentences):**
  Provide hard numerical evidence: percentages, error bounds, and standard units (`%`, `dB`, `ms`, `FLOPS`, `fps`, `accuracy`, `speedup`) compared against specific named baselines.
- **Beat 5: Practical Impact & Theoretical Implication (1 sentence):**
  State the broader system-level or cross-disciplinary significance (*"These results provide a scalable foundation for real-time constellation routing under dynamic orbital conditions"*).

### Academic SEO "Rule of Three" Keyphrase Anchoring:
Ensure the primary search keyphrase appears naturally **three times** throughout the abstract:
1. Once in **Beat 1** (problem context).
2. Once in **Beat 3** (method description).
3. Once in **Beat 5** (practical implication).

### Style Invariants:
- **Zero em dashes (—):** Replace with parentheses, standard commas, or discrete sentences.
- **Zero AI clichés:** Eliminate *delve*, *pivotal*, *testament*, *tapestry*, *seamless*, *groundbreaking*, *crucial*, *vital*.
- **No run-on sentences:** Keep all sentences $\le 35$ words.
- **No first-person singular pronouns:** Use objective academic passive voice or discipline-standard active plural.

---

## 4. Metadata Vocabulary Expansion (Keywords)

Do not waste keyword metadata slots by duplicating words already present in the chosen title. Search engines (Scopus, Web of Science, Google Scholar) index both title and keywords:
- **Non-Redundancy Rule:** Ensure author keywords share $<35\%$ word overlap with the title.
- **Vocabulary Broadening:** Allocate 5–7 keywords across:
  - 2 Controlled Thesaurus terms (IEEE Thesaurus, Inspec, MeSH, ACM Computing Classification).
  - 2 Application / Domain context terms (e.g., *"satellite communications"*, *"edge computing"*).
  - 2 Methodological / Algorithmic terms (e.g., *"stochastic approximation"*, *"differential privacy"*).

---

## 5. Verification & Scorecard Audit

Execute the Shannon empirical validation script to audit the manuscript title, abstract, and keywords:

```bash
uv run python skills/shannon/scripts/test_keywords.py \
  --title "<Selected Title>" \
  --abstract "<Draft Abstract>" \
  --keywords "<k1, k2, k3, k4, k5>" \
  [--target-venue ieee|elsevier|springer] \
  [--live]
```

### Verification Criteria:
- **Reviewer Triage Score:** Must achieve $\ge 85 / 100$ points.
- **Academic SEO:** Keyphrase confirmed in first 65 chars; sweet-spot length (10–14 words); 3-beat keyphrase anchoring active.
- **Dual-Audience Accessibility:** Zero run-on sentences ($>35$ words); lead sentence accessible to non-specialists.
- **Keyword Redundancy:** Overlap with title $<35\%$.
- **Title Collision:** When run with `--live`, title collision risk must be `LOW RISK` or `MODERATE OVERLAP` ($<0.85$).
