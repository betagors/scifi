"""
Submission Suite Subcommand Handler (`sf submission`).
"""

from __future__ import annotations

import argparse
import json
import sys


def cmd_submission(args: argparse.Namespace) -> int:
    """Academic paper submission suite (`sf submission`)."""
    action = getattr(args, "submission_action", None)
    if action == "letter":
        from scifi.submission import generate_cover_letter

        res = generate_cover_letter(
            journal_name=getattr(args, "journal", "Target Journal") or "Target Journal",
            venue=getattr(args, "venue", "general") or "general",
            issn=getattr(args, "issn", None),
            editor_name=getattr(args, "editor", None),
            authors=getattr(args, "authors", None),
            figure_path=getattr(args, "figure", None),
            prior_doi=getattr(args, "prior_doi", None),
            manuscript_path=getattr(args, "target", None),
            output_path=getattr(args, "output", None),
        )
        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2))
        else:
            print(res.markdown_text)
            if res.output_path:
                print(f"[OK] Cover letter saved to {res.output_path}")
        return 0

    elif action == "highlights":
        from scifi.submission import generate_highlights

        bullets_arg = getattr(args, "bullets", None)
        res_hl = generate_highlights(
            bullets=bullets_arg,
            venue=getattr(args, "venue", "general") or "general",
            manuscript_path=getattr(args, "target", None),
            output_path=getattr(args, "output", None),
        )
        if getattr(args, "json", False):
            print(json.dumps(res_hl.to_dict(), indent=2))
        else:
            print(res_hl.markdown_text)
            if not res_hl.all_valid:
                for h in res_hl.highlights:
                    if not h.is_valid:
                        print(f"  [WARNING] {h.issue}", file=sys.stderr)
            if getattr(args, "output", None):
                print(f"[OK] Highlights saved to {args.output}")
        return 0 if res_hl.all_valid else 1

    elif action == "title-page":
        from scifi.submission import generate_title_page

        res_tp = generate_title_page(
            venue=getattr(args, "venue", "general") or "general",
            authors=getattr(args, "authors", None),
            manuscript_path=getattr(args, "target", None),
            funding=getattr(args, "funding", None),
            conflicts=getattr(args, "conflicts", None),
            output_path=getattr(args, "output", None),
        )
        if getattr(args, "json", False):
            print(json.dumps(res_tp.to_dict(), indent=2))
        else:
            print(res_tp.markdown_text)
            if res_tp.output_path:
                print(f"[OK] Title page saved to {res_tp.output_path}")
        return 0

    elif action == "pack-code":
        from scifi.submission import package_anonymous_code

        authors = [a.strip() for a in (getattr(args, "authors", "") or "").split(",") if a.strip()]
        res_code = package_anonymous_code(
            code_dir=getattr(args, "code_dir", "."),
            output_zip_path=getattr(args, "output", None),
            author_names=authors,
        )
        if getattr(args, "json", False):
            print(json.dumps(res_code.to_dict(), indent=2))
        else:
            print(res_code.audit_report)
            if res_code.zip_path:
                print(f"[OK] Anonymous code archive created at: {res_code.zip_path}")
        return 0 if res_code.audit_passed else 1

    elif action == "bundle":
        from scifi.submission import prepare_submission_bundle

        res_bundle = prepare_submission_bundle(
            target_dir_or_tex=getattr(args, "target", "."),
            journal_name=getattr(args, "journal", None),
            venue=getattr(args, "venue", "general") or "general",
            issn=getattr(args, "issn", None),
            authors=getattr(args, "authors", None),
            code_dir=getattr(args, "code_dir", None),
            no_code=getattr(args, "no_code", False),
            figure_path=getattr(args, "figure", None),
            prior_doi=getattr(args, "prior_doi", None),
            funding=getattr(args, "funding", None),
            conflicts=getattr(args, "conflicts", None),
            editor_name=getattr(args, "editor", None),
            output_dir=getattr(args, "output", None),
        )
        if getattr(args, "json", False):
            print(json.dumps(res_bundle.to_dict(), indent=2))
        else:
            print(f"# Submission Bundle Generated [{res_bundle.venue.upper()}]")
            print(f"- Output directory: `{res_bundle.output_dir}`")
            print(f"- Cover letter: `{res_bundle.cover_letter_path}`")
            print(f"- Highlights: `{res_bundle.highlights_path}`")
            print(f"- Title page: `{res_bundle.title_page_path}`")
            if res_bundle.code_zip_path:
                print(f"- Anonymous code zip: `{res_bundle.code_zip_path}`")
            print(f"- Manifest: `{res_bundle.manifest_path}`")
        return 0

    else:
        print("[ERROR] Specify a submission action: letter, highlights, title-page, pack-code, bundle", file=sys.stderr)
        return 1
