---
description: Audit manuscripts for uncredited methods, attribution gaps, and informal web plagiarism
argument-hint: "[path/to/paper.tex | 'paragraph text']"
---

Audit manuscripts, draft sections, or paragraphs for attribution integrity using the `argus` skill:

- **Uncredited Scientific Methods:** Detect named algorithms, architectures, loss functions, and techniques (e.g. *LoRA*, *AdamW*, *InfoNCE*, *DBSCAN*) lacking citations. Retrieve canonical papers via OpenAlex/Crossref and insert `\cite{...}` tags.
- **Informal Web & Blog Plagiarism:** Identify passages adapted from tutorials, blogs, or Medium posts. Either trace to root academic literature or reformulate into publication-grade academic prose via the `human` skill.
- **Common Knowledge Filtering:** Automatically suppress false alarms on universal concepts (e.g. *gradient descent*, *Fourier transform*, *backpropagation*).
- **Self-Citation & Preprint Alignment:** Prevent false flags on author preprints or previous papers using `--author-whitelist` or `--preprint-doi`.

Target: $ARGUMENTS
