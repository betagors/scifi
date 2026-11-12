# FastMCP Tools Reference

SciFi provides 46 FastMCP tools for AI coding assistants. All tools are registered on the FastMCP server instance (`mcp`) and organized into modular domain routers.

---

## Tool Categories

### 1. Literature & Citations (Alex & Argus)
| Tool Name | Parameters | Description |
|---|---|---|
| `scifi_verify_citation` | `identifier`, `claimed_title`, `claimed_author`, `claimed_year`, `claimed_venue` | Verify citation against Crossref/OpenAlex/arXiv with caching and retraction checking |
| `scifi_audit_bib` | `bib_path`, `output_bib` | Audit an entire `.bib` bibliography file and optionally generate sanitized entries |
| `scifi_search_literature` | `query`, `limit` | Search academic registries for canonical literature and seminal works |
| `scifi_audit_attribution` | `tex_path`, `bib_path`, `autofix` | Scan LaTeX manuscripts for uncredited methods, algorithms, and attribution gaps |

### 2. Mathematics & Theoretical Rigor (Turing & Gauss)
| Tool Name | Parameters | Description |
|---|---|---|
| `scifi_verify_derivative` | `expression`, `variable`, `claimed_derivative` | Verify symbolic derivative using SymPy |
| `scifi_verify_derivation_step` | `lhs`, `rhs`, `assumptions` | Verify symbolic equivalence between two mathematical expressions |
| `scifi_check_units` | `expression`, `check_mode` | Check dimensional homogeneity across additive terms and equation equalities |
| `scifi_check_matrix_shapes` | `expression`, `shapes` | Verify matrix products and tensor contraction dimensions |
| `scifi_check_limits` | `expression`, `variable`, `point`, `claimed`, `direction` | Verify analytical asymptotic limits ($x \to 0$, $x \to \infty$) |
| `scifi_check_convexity` | `expression`, `variables`, `claimed` | Check convexity/concavity via positive semi-definite Hessian inspection |
| `scifi_check_notation` | `tex_path`, `sections` | Audit LaTeX source for mathematical symbol overloading and collisions |
| `scifi_verify_curve` | `formula_latex`, `var_name`, `sim_data_path`, `x_vals`, `y_vals`, `rtol` | Verify theoretical closed-form expressions against numerical simulation datasets |
| `scifi_audit_statistics` | `samples`, `confidence` | Audit sample sizes ($N \ge 30$), confidence intervals, and statistical significance |

### 3. Unified Manuscript Readiness & Typography
| Tool Name | Parameters | Description |
|---|---|---|
| `scifi_compile_latex` | `entrypoint`, `engine`, `clean` | Autonomously compile LaTeX manuscripts with log diagnostic parsing |
| `scifi_audit_claims` | `file_path` | Scan manuscript text for unsupported assertions and absolute claims |
| `scifi_audit_manuscript` | `tex_path`, `bib_path`, `venue`, `double_blind`, `compile_pdf` | Execute the full 6-stage pre-submission manuscript readiness audit |
| `scifi_evaluate_title_abstract` | `tex_path`, `title`, `abstract`, `keywords` | Shannon 100-point triage, 5-beat abstract balance, and keyword expansion |
| `scifi_generate_latex_table` | `data_json`, `caption`, `label`, `column_alignments`, `booktabs` | Generate publication-grade LaTeX `booktabs` tables |
| `scifi_check_venue_compliance` | `tex_path`, `venue` | Audit manuscript against publisher margin, font, and double-blind rules |
| `scifi_audit_human` | `tex_path`, `mode`, `apply_autofix`, `max_burstiness_threshold` | Detect and eradicate synthetic AI writing clichés and LaTeX markup fingerprints |
| `scifi_audit_figures` | `tex_path`, `figures_dir`, `min_dpi`, `check_subfigures` | Audit figures for print resolution ($\ge 300\text{ DPI}$), vector formats, and colorblind safety |
| `scifi_trim_budget` | `tex_path`, `bib_path`, `max_pages`, `target_lines` | Layout micro-trimming assistant to reclaim vertical page lines without `\vspace` hacks |
| `scifi_audit_proofs` | `tex_path`, `appendix_path` | Euclid theorem-proof sentinel detecting orphan theorems and broken appendix proofs |
| `scifi_audit_reproducibility` | `tex_path`, `code_dir`, `venue` | Bacon conference reproducibility auditor for seeds, error bars, and compute hardware |
| `scifi_format_rebuttal` | `comments_path_or_text`, `author_actions`, `target_venue`, `output_md` | Scaffold disciplined 4-beat point-by-point reviewer rebuttal responses |
| `scifi_diff_manuscript` | `old_tex_path`, `new_tex_path`, `generate_pdf`, `output_tex` | Generate word-level revision diffs via latexdiff with visual markup |

### 4. Literature Intelligence & Central Knowledge Hub
| Tool Name | Parameters | Description |
|---|---|---|
| `scifi_fetch_paper_pdf` | `identifier`, `output_dir`, `email` | Retrieve open-access paper PDFs by DOI or arXiv ID from arXiv, Unpaywall, OpenAlex |
| `scifi_extract_pdf_text` | `pdf_path`, `max_pages`, `max_section_length` | Extract structured section text from scientific PDFs for synthesis and gap analysis |
| `scifi_map_literature` | `query`, `depth`, `max_papers`, `graph_id`, `output_dir` | Build interactive literature lineage graphs from seed papers |
| `scifi_query_sota_benchmarks` | `query`, `benchmark_name` | Query benchmark taxonomies, empirical metrics, and current SOTA leaders |
| `scifi_query_store` | `query_sql` | Execute strictly read-only SQL SELECT queries against the literature knowledge store |
| `scifi_export_bibtex` | `graph_id`, `output_path` | Export verified BibTeX entries for all papers in a literature graph session |
| `scifi_list_projects` | *(none)* | List all registered research project workspaces in the central knowledge store |
| `scifi_get_project_summary` | `project_name_or_path` | Retrieve paper counts, OA percentages, and pending reprint requests |
| `scifi_draft_reprint_request` | `identifier`, `project_name` | Generate an academic-standard author reprint request and mailto link |
| `scifi_list_pending_reprints` | `project_name` | List pending reprint requests awaiting author responses |
| `scifi_ingest_paper_pdf` | `identifier`, `pdf_path`, `project_name` | Ingest an acquired paper PDF into the content-addressed central store |

### 5. Academic Paper Submission Suite
| Tool Name | Parameters | Description |
|---|---|---|
| `scifi_generate_highlights` | `bullets`, `venue`, `manuscript_path`, `output_path` | Validate highlights against publisher character limits ($\le 85$ chars for Elsevier) |
| `scifi_generate_title_page` | `title`, `authors`, `venue`, `funding`, `conflicts`, `output_path` | Generate unblinded standalone title pages for double-blind review fairness |
| `scifi_generate_cover_letter` | `manuscript_title`, `journal_name`, `venue`, `issn`, `editor_name`, `authors` | Generate editorial cover letters in Markdown and LaTeX format |
| `scifi_package_anonymous_code` | `code_dir`, `output_zip_path`, `author_names` | Package code directories into anonymous ZIPs with git histories and user paths scrubbed |
| `scifi_prepare_submission_bundle` | `target_dir_or_tex`, `journal_name`, `venue`, `authors`, `code_dir` | Generate all four submission artifacts and packaging manifest in one shot |

### 6. Local Zotero SQLite Integration
| Tool Name | Parameters | Description |
|---|---|---|
| `scifi_zotero_status` | *(none)* | Check local Zotero library, data directory detection, and port 23119 server |
| `scifi_zotero_get_collection_papers` | `collection` | Retrieve papers belonging to a Zotero collection with local PDF paths |
| `scifi_zotero_get_annotations` | `item_key` | Retrieve user PDF highlights, notes, and comments for a Zotero paper |
| `scifi_zotero_push_audit_note` | `item_key`, `audit_data` | Non-destructively stage or push SciFi audit cards as child notes in Zotero |
