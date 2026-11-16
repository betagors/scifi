"""
FastMCP Server Package for SciFi.

Provides all FastMCP tools organized across domain-specific routers:
- Citations (`scifi.server.routers.citations`)
- Math (`scifi.server.routers.math`)
- Manuscript (`scifi.server.routers.manuscript`)
- Literature (`scifi.server.routers.literature`)
- Submission (`scifi.server.routers.submission`)
- Zotero (`scifi.server.routers.zotero`)
- Zenodo (`scifi.server.routers.zenodo`)
- Datasets & Kaggle (`scifi.server.routers.datasets`)
"""

from __future__ import annotations

import requests

from scifi.citation_verifier import audit_bib_file, generate_sanitized_bib, verify_citation
from scifi.latex import compile_latex
from scifi.literature import extract_pdf_text, fetch_paper_pdf
from scifi.literature.lineage import LineageCrawler
from scifi.literature.models import PaperRecord, ProjectRecord
from scifi.literature.reporter import save_markdown_report
from scifi.literature.store import DEFAULT_CENTRAL_STORE_PATH, LiteratureStore
from scifi.literature.visualizer import save_interactive_html
from scifi.server.app import (
    DEFAULT_KG_DB_PATH,
    DEFAULT_LITERATURE_DB_PATH,
    DEFAULT_USER_AGENT,
    _resolve_project,
    get_cache,
    get_knowledge_graph,
    get_literature_store,
    mcp,
)
from scifi.server.routers.citations import (
    scifi_audit_attribution,
    scifi_audit_bib,
    scifi_search_literature,
    scifi_verify_citation,
)
from scifi.server.routers.datasets import (
    scifi_datasets_dir,
    scifi_datasets_download,
    scifi_datasets_inspect,
    scifi_datasets_list,
    scifi_datasets_search,
    scifi_kaggle_competition_download,
    scifi_kaggle_competition_list,
    scifi_kaggle_competition_submit,
    scifi_kaggle_kernel_list,
    scifi_kaggle_kernel_output,
    scifi_kaggle_kernel_pull,
    scifi_kaggle_kernel_push,
    scifi_kaggle_kernel_status,
    scifi_kaggle_push_dataset,
    scifi_kaggle_status,
)
from scifi.server.routers.literature import (
    scifi_draft_reprint_request,
    scifi_export_bibtex,
    scifi_extract_pdf_text,
    scifi_fetch_openreview_gaps,
    scifi_fetch_paper_pdf,
    scifi_fetch_structured_paper,
    scifi_get_project_summary,
    scifi_ingest_paper_pdf,
    scifi_kg_delta_novelty,
    scifi_kg_find_contradictions,
    scifi_kg_query,
    scifi_kg_rebuild,
    scifi_kg_status,
    scifi_kg_trace_assumptions,
    scifi_kg_upsert_fact,
    scifi_list_pending_reprints,
    scifi_list_projects,
    scifi_map_literature,
    scifi_query_sota_benchmarks,
    scifi_query_store,
    scifi_synthesize_gaps,
)
from scifi.server.routers.manuscript import (
    scifi_audit_claims,
    scifi_audit_figures,
    scifi_audit_manuscript,
    scifi_audit_orwell,
    scifi_audit_proofs,
    scifi_audit_reproducibility,
    scifi_calibrate_orwell,
    scifi_check_venue_compliance,
    scifi_compile_latex,
    scifi_compiler_info,
    scifi_diff_manuscript,
    scifi_evaluate_title_abstract,
    scifi_format_rebuttal,
    scifi_generate_latex_table,
    scifi_render_pdf,
    scifi_trim_budget,
    scifi_verify_edit_invariants,
)
from scifi.server.routers.math import (
    scifi_audit_statistics,
    scifi_check_convexity,
    scifi_check_limits,
    scifi_check_matrix_shapes,
    scifi_check_notation,
    scifi_check_units,
    scifi_verify_curve,
    scifi_verify_derivation_step,
    scifi_verify_derivative,
)
from scifi.server.routers.submission import (
    scifi_generate_cover_letter,
    scifi_generate_highlights,
    scifi_generate_title_page,
    scifi_package_anonymous_code,
    scifi_prepare_submission_bundle,
)
from scifi.server.routers.zenodo import (
    scifi_zenodo_create_deposition,
    scifi_zenodo_get_deposition,
    scifi_zenodo_list_depositions,
    scifi_zenodo_publish_deposition,
    scifi_zenodo_push_submission,
    scifi_zenodo_reserve_doi,
    scifi_zenodo_status,
    scifi_zenodo_update_metadata,
    scifi_zenodo_upload_file,
)
from scifi.server.routers.zotero import (
    scifi_zotero_get_annotations,
    scifi_zotero_get_collection_papers,
    scifi_zotero_push_audit_note,
    scifi_zotero_search,
    scifi_zotero_status,
    scifi_zotero_sync,
)

__all__ = [
    # Core app & MCP server instance
    "mcp",
    "get_cache",
    "get_knowledge_graph",
    "get_literature_store",
    "_resolve_project",
    "DEFAULT_CENTRAL_STORE_PATH",
    "DEFAULT_KG_DB_PATH",
    "DEFAULT_LITERATURE_DB_PATH",
    "DEFAULT_USER_AGENT",
    # Re-exported for test mocks / backward compatibility
    "compile_latex",
    "fetch_paper_pdf",
    "extract_pdf_text",
    "verify_citation",
    "audit_bib_file",
    "generate_sanitized_bib",
    "requests",
    "LineageCrawler",
    "LiteratureStore",
    "ProjectRecord",
    "PaperRecord",
    "save_interactive_html",
    "save_markdown_report",
    # Citations tools
    "scifi_verify_citation",
    "scifi_audit_bib",
    "scifi_search_literature",
    "scifi_audit_attribution",
    # Math tools
    "scifi_verify_derivative",
    "scifi_verify_derivation_step",
    "scifi_check_units",
    "scifi_check_matrix_shapes",
    "scifi_check_limits",
    "scifi_check_convexity",
    "scifi_check_notation",
    "scifi_verify_curve",
    "scifi_audit_statistics",
    # Manuscript tools
    "scifi_compile_latex",
    "scifi_compiler_info",
    "scifi_render_pdf",
    "scifi_audit_claims",
    "scifi_audit_manuscript",
    "scifi_evaluate_title_abstract",
    "scifi_generate_latex_table",
    "scifi_check_venue_compliance",
    "scifi_audit_orwell",
    "scifi_calibrate_orwell",
    "scifi_verify_edit_invariants",
    "scifi_audit_figures",
    "scifi_trim_budget",
    "scifi_audit_proofs",
    "scifi_audit_reproducibility",
    "scifi_format_rebuttal",
    "scifi_diff_manuscript",
    # Literature tools
    "scifi_fetch_paper_pdf",
    "scifi_fetch_structured_paper",
    "scifi_fetch_openreview_gaps",
    "scifi_synthesize_gaps",
    "scifi_extract_pdf_text",
    "scifi_map_literature",
    "scifi_query_sota_benchmarks",
    "scifi_query_store",
    "scifi_export_bibtex",
    "scifi_list_projects",
    "scifi_get_project_summary",
    "scifi_draft_reprint_request",
    "scifi_list_pending_reprints",
    "scifi_ingest_paper_pdf",
    # Knowledge Graph tools
    "scifi_kg_status",
    "scifi_kg_rebuild",
    "scifi_kg_query",
    "scifi_kg_trace_assumptions",
    "scifi_kg_delta_novelty",
    "scifi_kg_find_contradictions",
    "scifi_kg_upsert_fact",
    # Submission tools
    "scifi_generate_highlights",
    "scifi_generate_title_page",
    "scifi_generate_cover_letter",
    "scifi_package_anonymous_code",
    "scifi_prepare_submission_bundle",
    # Zotero tools
    "scifi_zotero_status",
    "scifi_zotero_sync",
    "scifi_zotero_get_collection_papers",
    "scifi_zotero_search",
    "scifi_zotero_get_annotations",
    "scifi_zotero_push_audit_note",
    # Zenodo tools
    "scifi_zenodo_status",
    "scifi_zenodo_list_depositions",
    "scifi_zenodo_get_deposition",
    "scifi_zenodo_create_deposition",
    "scifi_zenodo_update_metadata",
    "scifi_zenodo_upload_file",
    "scifi_zenodo_reserve_doi",
    "scifi_zenodo_publish_deposition",
    "scifi_zenodo_push_submission",
    # Datasets & Kaggle tools
    "scifi_datasets_dir",
    "scifi_datasets_list",
    "scifi_datasets_inspect",
    "scifi_datasets_search",
    "scifi_datasets_download",
    "scifi_kaggle_status",
    "scifi_kaggle_push_dataset",
    "scifi_kaggle_competition_list",
    "scifi_kaggle_competition_download",
    "scifi_kaggle_competition_submit",
    "scifi_kaggle_kernel_list",
    "scifi_kaggle_kernel_pull",
    "scifi_kaggle_kernel_push",
    "scifi_kaggle_kernel_status",
    "scifi_kaggle_kernel_output",
]

import os as _os
import sys as _sys

if not _os.environ.get("PYTEST_CURRENT_TEST") and "pytest" not in _sys.modules:
    try:
        from scifi.literature.zotero.sync import start_background_sync as _start_zotero_bg_sync

        _start_zotero_bg_sync()
    except Exception:
        pass
