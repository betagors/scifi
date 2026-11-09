---
name: submission
description: Academic paper submission packaging suite. Generates editorial cover letters, research highlights with venue character validation, standalone unblinded title pages for review fairness, and reproducible anonymous code ZIP archives.
---

# Submission: Academic Paper Packaging & Editorial Suite

The `submission` skill prepares and packages all mandatory pre-submission artifacts for academic journal and conference submissions across Elsevier, IEEE, Springer Nature, ACM, and double-blind venues:
1. **Editorial Cover Letters**: Compiles professional letters addressed to the Editor-in-Chief highlighting paper significance, publisher-specific declarations (e.g. IEEE conference extension clauses, Elsevier novelty statements), and reviewer nominations.
2. **Research Highlights**: Validates and formats 3–5 bullet points against strict publisher character ceilings (such as Elsevier's rigid 85-character ceiling per bullet).
3. **Standalone Title Pages**: Generates unblinded metadata files (`title_page.tex` / `.md`) with author affiliations, correspondence, funding, and CRediT taxonomy, allowing the main manuscript to remain strictly blinded for review fairness.
4. **Reproducible Anonymous Code ZIP**: Bundles and scrubs source code of git history, local paths (`C:\Users\...` or `/home/...`), secrets, and author identities into a verified `anonymous_code.zip`.
5. **Submission Bundle**: Runs all 4 generators in a single command (`sf submission bundle`), producing a complete `dist/submission/` directory with `submission_manifest.json`.

---

## When to Use

- Generating formal submission cover letters for journal Editor-in-Chief review.
- Auditing bulleted research highlights against venue character limits (Elsevier 85 characters, IEEE 100 characters).
- Creating unblinded title pages for double-blind submissions to ensure review fairness.
- Packaging anonymized code repositories for conference peer review (NeurIPS, ICML, CVPR, ICLR).
- Bundling an entire submission package before final portal upload.

---

## CLI Usage

```bash
# Generate tailored editorial cover letter
sf submission letter --target main.tex --journal "Pattern Recognition" --venue elsevier

# Validate research highlights against Elsevier's 85-character ceiling
sf submission highlights --target main.tex --venue elsevier

# Generate unblinded title page with CRediT statement
sf submission title-page --target main.tex --venue elsevier --funding "NSF Award #12345"

# Package reproducible anonymous code zip archive
sf submission pack-code ./code --authors "Alice Smith, Bob Jones"

# Generate complete submission bundle in one command
sf submission bundle --target main.tex --journal "IEEE TPAMI" --venue ieee
```

---

## FastMCP Tools

- `scifi_generate_cover_letter`
- `scifi_generate_highlights`
- `scifi_generate_title_page`
- `scifi_package_anonymous_code`
- `scifi_prepare_submission_bundle`
