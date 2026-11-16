"""
Zenodo Subcommand Handler (`sf zenodo`).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scifi.config import set_global_config_value
from scifi.zenodo import ZenodoDepositClient


def _print_json(data: object) -> None:
    print(json.dumps(data, indent=2, default=str))


def _client_from_args(args: argparse.Namespace) -> ZenodoDepositClient:
    return ZenodoDepositClient(sandbox=bool(getattr(args, "sandbox", False)))


def cmd_zenodo(args: argparse.Namespace) -> int:
    """Manage Zenodo account authentication, depositions, DOIs, and submission uploads (`sf zenodo`)."""
    action = getattr(args, "zenodo_action", None) or "status"
    as_json = bool(getattr(args, "json", False))

    if action == "login":
        token = getattr(args, "token", None)
        if not token:
            print("[ERROR] Provide --token <ZENODO_TOKEN>.", file=sys.stderr)
            return 1
        cfg_path = set_global_config_value("zenodo_token", token)
        client = ZenodoDepositClient(token=token, sandbox=bool(getattr(args, "sandbox", False)))
        status = (
            client.status()
            if not getattr(args, "no_verify", False)
            else {
                "configured": True,
                "connected": None,
                "sandbox": bool(getattr(args, "sandbox", False)),
            }
        )
        status["config_path"] = str(cfg_path)
        if as_json:
            _print_json(status)
        else:
            print(f"[OK] Saved Zenodo token to {cfg_path}")
            if status.get("connected") is True:
                print(f"  -> Verified connection to {status.get('api_base')}")
            elif status.get("connected") is False:
                print(f"  [WARNING] Token saved, but verification failed: {status.get('error')}", file=sys.stderr)
        return 0 if status.get("connected") is not False else 1

    client = _client_from_args(args)

    if action == "status":
        st = client.status()
        if as_json:
            _print_json(st)
        else:
            state = (
                "CONNECTED"
                if st["connected"]
                else ("CONFIGURED (UNVERIFIED)" if st["configured"] else "NOT CONFIGURED")
            )
            print(f"Zenodo Status: {state}")
            print(f"  API Base: {st['api_base']}")
            if st.get("error"):
                print(f"  Note: {st['error']}")
        return 0 if st.get("connected") else 1

    try:
        if action == "list":
            deps = client.list_depositions(
                status=getattr(args, "status", None),
                size=getattr(args, "limit", 20),
                query=getattr(args, "query", None),
            )
            if as_json:
                _print_json([d.to_dict() for d in deps])
            else:
                if not deps:
                    print("No Zenodo depositions found.")
                for d in deps:
                    doi = d.doi or d.prereserved_doi or "no-doi"
                    print(f"  [{d.id}] ({d.state}) {d.title} — DOI: {doi} ({len(d.files)} files)")
            return 0

        if action == "show":
            dep = client.get_deposition(args.deposition_id)
            if as_json:
                _print_json(dep.to_dict())
            else:
                print(f"Deposition {dep.id}: {dep.title}")
                print(f"  State: {dep.state} | Submitted: {dep.submitted}")
                print(f"  DOI: {dep.doi or dep.prereserved_doi or 'none'}")
                if dep.html_url:
                    print(f"  URL: {dep.html_url}")
                for f in dep.files:
                    print(f"    - {f.filename} ({f.filesize} bytes)")
            return 0

        if action == "create":
            keywords = [k.strip() for k in (getattr(args, "keywords", "") or "").split(",") if k.strip()]
            dep = client.create_deposition(
                title=getattr(args, "title", None),
                upload_type=getattr(args, "upload_type", "software") or "software",
                description=getattr(args, "description", None),
                creators=getattr(args, "creators", None),
                keywords=keywords or None,
                license_id=getattr(args, "license", None),
                prereserve_doi=not bool(getattr(args, "no_reserve_doi", False)),
            )
            if as_json:
                _print_json(dep.to_dict())
            else:
                print(f"[OK] Created Zenodo draft deposition {dep.id}: {dep.title}")
                if dep.prereserved_doi:
                    print(f"  Reserved DOI: {dep.prereserved_doi}")
                if dep.html_url:
                    print(f"  URL: {dep.html_url}")
            return 0

        if action == "update":
            meta: dict[str, object] = {}
            if getattr(args, "title", None):
                meta["title"] = args.title
            if getattr(args, "description", None):
                meta["description"] = args.description
            if getattr(args, "license", None):
                meta["license"] = args.license
            if getattr(args, "keywords", None):
                meta["keywords"] = [k.strip() for k in args.keywords.split(",") if k.strip()]
            if not meta:
                print("[ERROR] Provide at least one metadata field to update.", file=sys.stderr)
                return 1
            dep = client.update_metadata(args.deposition_id, meta)
            if as_json:
                _print_json(dep.to_dict())
            else:
                print(f"[OK] Updated deposition {dep.id}: {dep.title}")
            return 0

        if action == "upload":
            uploaded = []
            for fp in args.files:
                zf = client.upload_file(args.deposition_id, fp)
                uploaded.append(zf.to_dict())
            if as_json:
                _print_json({"deposition_id": args.deposition_id, "uploaded": uploaded})
            else:
                for u in uploaded:
                    print(f"[OK] Uploaded {u['filename']} ({u['filesize']} bytes) to deposition {args.deposition_id}")
            return 0

        if action == "reserve-doi":
            res = client.reserve_doi(args.deposition_id)
            if as_json:
                _print_json(res)
            else:
                print(
                    f"[OK] Deposition {res['deposition_id']} reserved DOI: {res.get('prereserved_doi') or res.get('doi')}"
                )
            return 0

        if action == "publish":
            if not getattr(args, "yes", False):
                print(
                    "[ERROR] Publishing a Zenodo deposition mints a permanent DOI and cannot be undone. "
                    "Re-run with --yes to confirm.",
                    file=sys.stderr,
                )
                return 1
            dep = client.publish(args.deposition_id)
            if as_json:
                _print_json(dep.to_dict())
            else:
                print(f"[OK] Published deposition {dep.id} — DOI: {dep.doi}")
            return 0

        if action == "push-submission":
            files_to_push: list[Path] = []
            if getattr(args, "files", None):
                files_to_push.extend(Path(p) for p in args.files)
            else:
                bundle_dir = Path(getattr(args, "bundle_dir", None) or "submission_bundle")
                if bundle_dir.is_dir():
                    for cand in sorted(bundle_dir.iterdir()):
                        if cand.is_file() and cand.suffix.lower() in {".zip", ".pdf", ".tex", ".md"}:
                            files_to_push.append(cand)
                if not files_to_push:
                    from scifi.submission import package_anonymous_code

                    code_res = package_anonymous_code(code_dir=getattr(args, "code_dir", "."))
                    if code_res.zip_path:
                        files_to_push.append(Path(code_res.zip_path))

            if not files_to_push:
                print("[ERROR] No submission artifacts found or packaged to upload.", file=sys.stderr)
                return 1

            keywords = [k.strip() for k in (getattr(args, "keywords", "") or "").split(",") if k.strip()]
            push_res = client.push_submission_artifacts(
                files=files_to_push,
                deposition_id=getattr(args, "deposition_id", None),
                title=getattr(args, "title", None),
                description=getattr(args, "description", None),
                creators=getattr(args, "creators", None),
                upload_type=getattr(args, "upload_type", "software") or "software",
                keywords=keywords or None,
                license_id=getattr(args, "license", None),
                publish=bool(getattr(args, "publish", False)),
            )
            if as_json:
                _print_json(push_res.to_dict())
            else:
                print(
                    f"[OK] Pushed {len(push_res.uploaded_files)} file(s) to Zenodo deposition {push_res.deposition_id}"
                )
                if push_res.prereserved_doi:
                    print(f"  Reserved DOI: {push_res.prereserved_doi}")
                if push_res.doi:
                    print(f"  Published DOI: {push_res.doi}")
                if push_res.html_url:
                    print(f"  URL: {push_res.html_url}")
            return 0

    except Exception as exc:
        if as_json:
            _print_json({"error": str(exc)})
        else:
            print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(f"[ERROR] Unknown zenodo action: {action}", file=sys.stderr)
    return 1
