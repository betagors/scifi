"""
Embedded HTTP REST API server and secure static file dispatcher for SciFi Web Cockpit.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import socket
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

from scifi.literature.models import PaperRecord, ProjectRecord, ReprintRequestRecord
from scifi.literature.reprint import build_mailto_url, ingest_paper_copy
from scifi.literature.store import DEFAULT_CENTRAL_STORE_PATH, LiteratureStore
from scifi.literature.visualizer import OA_COLORS, determine_oa_status, format_node_label

logger = logging.getLogger("scifi.web.server")


def get_default_static_dir() -> Path:
    """Return the absolute path to the bundled web static assets directory."""
    return Path(__file__).resolve().parent / "static"


def find_available_port(
    start_port: int = 8080,
    max_attempts: int = 10,
    host: str = "127.0.0.1",
) -> int:
    """
    Find an available TCP port starting from start_port up to start_port + max_attempts - 1.
    """
    for offset in range(max_attempts):
        port = start_port + offset
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind((host, port))
                return port
        except OSError:
            continue
    raise OSError(
        f"No available port found in range {start_port}..{start_port + max_attempts - 1}"
    )


class SciFiRequestHandler(BaseHTTPRequestHandler):
    """
    Request handler serving SciFi Cockpit REST API endpoints and static assets.
    """

    server: SciFiWebServer

    def log_message(self, format: str, *args: Any) -> None:
        """Direct server log entries to logger instead of standard error."""
        logger.debug("%s - - [%s] %s", self.address_string(), self.log_date_time_string(), format % args)

    def do_OPTIONS(self) -> None:
        """Handle CORS pre-flight requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        """Route GET requests to API handlers or static file dispatcher."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        parts = [p for p in path.strip("/").split("/") if p]

        if parts and parts[0] == "api":
            self._route_api_get(parts[1:], query)
        else:
            self._handle_static_file(path)

    def do_POST(self) -> None:
        """Route POST requests to API action endpoints."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        parts = [p for p in path.strip("/").split("/") if p]

        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            content_length = 0

        if content_length > 15 * 1024 * 1024:
            self._send_error_json(413, "Payload Too Large: request body exceeds 15 MB limit.")
            return

        if content_length > 0:
            raw_body = self.rfile.read(content_length)
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as err:
                self._send_error_json(400, f"Malformed JSON body: {err}")
                return
        else:
            payload = {}

        if parts and parts[0] == "api":
            self._route_api_post(parts[1:], payload)
        else:
            self._send_error_json(404, f"API endpoint not found: {path}")

    # -------------------------------------------------------------------------
    # API Routing & Handlers
    # -------------------------------------------------------------------------

    def _route_api_get(self, parts: list[str], query: dict[str, list[str]]) -> None:
        if not parts:
            self._send_error_json(404, "API root not found")
            return

        if parts == ["projects"]:
            self._handle_get_projects()
        elif len(parts) == 2 and parts[0] == "projects":
            self._handle_get_project(parts[1])
        elif len(parts) == 3 and parts[0] == "projects" and parts[2] == "papers":
            self._handle_get_project_papers(parts[1])
        elif len(parts) == 3 and parts[0] == "projects" and parts[2] == "graph":
            self._handle_get_project_graph(parts[1], query)
        elif parts == ["reprints"]:
            self._handle_get_reprints(query)
        else:
            self._send_error_json(404, f"Unknown API endpoint: {'/'.join(parts)}")

    def _route_api_post(self, parts: list[str], payload: dict[str, Any]) -> None:
        if len(parts) == 2 and parts[0] == "reprints":
            self._handle_post_reprint(parts[1], payload)
        elif parts == ["papers", "ingest"]:
            self._handle_post_ingest(payload)
        else:
            self._send_error_json(404, f"Unknown API endpoint: {'/'.join(parts)}")

    def _handle_get_projects(self) -> None:
        """GET /api/projects: list all registered projects with paper counts."""
        projects = self.server.store.list_projects()
        res_projects = []
        for p in projects:
            papers = self.server.store.get_project_papers(p.id)
            res_projects.append(
                {
                    "id": p.id,
                    "name": p.name,
                    "workspace_path": p.workspace_path,
                    "description": p.description,
                    "created_at": p.created_at,
                    "updated_at": p.updated_at,
                    "paper_count": len(papers),
                }
            )
        self._send_json({"projects": res_projects})

    def _handle_get_project(self, project_id: str) -> None:
        """GET /api/projects/<id>: retrieve single project details."""
        proj = self.server.store.get_project(project_id)
        if not proj:
            self._send_error_json(404, f"Project '{project_id}' not found")
            return
        papers = self.server.store.get_project_papers(proj.id)
        self._send_json(
            {
                "project": {
                    "id": proj.id,
                    "name": proj.name,
                    "workspace_path": proj.workspace_path,
                    "description": proj.description,
                    "created_at": proj.created_at,
                    "updated_at": proj.updated_at,
                    "paper_count": len(papers),
                }
            }
        )

    def _handle_get_project_papers(self, project_id: str) -> None:
        """GET /api/projects/<id>/papers: list papers with OA status, PDF presence, and gap counts."""
        papers = self.server.store.get_project_papers(project_id)
        papers_res = []
        for p in papers:
            oa_status = determine_oa_status(p)
            is_oa = oa_status != "closed"

            has_pdf = False
            local_pdf: Optional[str] = None
            pdf_url: Optional[str] = None
            doi: Optional[str] = None

            for loc in p.locations or []:
                if loc.local_pdf_path:
                    local_pdf = str(loc.local_pdf_path)
                    has_pdf = True
                elif loc.is_accessible:
                    has_pdf = True
                if loc.pdf_url and not pdf_url:
                    pdf_url = loc.pdf_url

            for ident in p.identifiers or []:
                if ident.provider.lower() == "doi":
                    doi = ident.external_id
                    break
            if not doi and p.id.startswith("10."):
                doi = p.id

            gaps = self.server.store.get_paper_gaps(p.id)
            gap_count = len(gaps)

            authors_data = [
                {
                    "name": a.name if hasattr(a, "name") else str(a),
                    "email": getattr(a, "email", None),
                    "institution": getattr(a, "institution", None),
                }
                for a in (p.authors or [])
            ]

            papers_res.append(
                {
                    "id": p.id,
                    "title": p.title,
                    "year": p.year,
                    "publication_date": p.publication_date,
                    "citation_count": p.citation_count or 0,
                    "influential_citation_count": p.influential_citation_count or 0,
                    "recent_citation_growth": p.recent_citation_growth or 0.0,
                    "is_retracted": bool(p.is_retracted),
                    "abstract": p.abstract,
                    "venue_name": p.venue_name,
                    "venue_tier": p.venue_tier,
                    "authors": authors_data,
                    "doi": doi,
                    "pdf_url": pdf_url,
                    "is_oa": is_oa,
                    "oa_status": oa_status,
                    "has_pdf": has_pdf,
                    "local_pdf_path": local_pdf,
                    "gap_count": gap_count,
                }
            )

        self._send_json({"project_id": project_id, "papers": papers_res})

    def _handle_get_project_graph(
        self, project_id: str, query: dict[str, list[str]]
    ) -> None:
        """GET /api/projects/<id>/graph: nodes and edges for Vis.js."""
        session_id = query.get("session_id", [None])[0] or query.get(
            "graph_id", [None]
        )[0]

        if session_id:
            papers = self.server.store.get_graph_papers(session_id)
            if not papers:
                papers = self.server.store.get_project_papers(project_id)
            citations = self.server.store.get_graph_citations(session_id)
        else:
            papers = self.server.store.get_project_papers(project_id)
            citations = []

        paper_ids = {p.id for p in papers}

        if not citations and paper_ids:
            seen_edges: set[tuple[str, str]] = set()
            for p in papers:
                for c in self.server.store.get_paper_citations(p.id):
                    if c.target_paper_id in paper_ids:
                        edge_key = (c.source_paper_id, c.target_paper_id)
                        if edge_key not in seen_edges:
                            seen_edges.add(edge_key)
                            citations.append(c)

        nodes = []
        for p in papers:
            oa_status = determine_oa_status(p)
            is_oa = oa_status != "closed"
            color_bg = OA_COLORS.get(oa_status, "#64748b")
            label = format_node_label(p)
            title = f"{p.title} ({p.year or 'n.d.'})"

            nodes.append(
                {
                    "id": p.id,
                    "label": label,
                    "title": title,
                    "year": p.year,
                    "is_oa": is_oa,
                    "oa_status": oa_status,
                    "citation_count": p.citation_count or 0,
                    "influential_citation_count": p.influential_citation_count or 0,
                    "is_retracted": bool(p.is_retracted),
                    "shape": "box",
                    "margin": 10,
                    "color": {
                        "background": color_bg,
                        "border": color_bg,
                        "highlight": {"background": color_bg, "border": "#1e293b"},
                        "hover": {"background": color_bg, "border": "#3b82f6"},
                    },
                    "font": {"color": "#ffffff"},
                }
            )

        edges = []
        for c in citations:
            edges.append(
                {
                    "from": c.source_paper_id,
                    "to": c.target_paper_id,
                    "is_influential": bool(c.is_influential),
                    "arrows": "to",
                    "width": 2.5 if c.is_influential else 1.2,
                    "color": {
                        "color": "#3b82f6" if c.is_influential else "#94a3b8",
                        "highlight": "#1d4ed8",
                        "hover": "#2563eb",
                    },
                    "title": "Influential Citation" if c.is_influential else "Citation",
                }
            )

        self._send_json(
            {
                "project_id": project_id,
                "session_id": session_id,
                "nodes": nodes,
                "edges": edges,
            }
        )

    def _handle_get_reprints(self, query: dict[str, list[str]]) -> None:
        """GET /api/reprints: list reprint requests (support ?project_id=)."""
        project_id = query.get("project_id", [None])[0]
        status = query.get("status", [None])[0]
        if status and status.upper() == "REJECTED":
            status = "DECLINED"
        paper_id = query.get("paper_id", [None])[0]

        reprints = self.server.store.get_reprint_requests(
            project_id=project_id,
            status=status,
            paper_id=paper_id,
        )
        reprints_data = [
            {
                "id": r.id,
                "project_id": r.project_id,
                "paper_id": r.paper_id,
                "author_name": r.author_name,
                "author_email": r.author_email,
                "author_affiliation": r.author_affiliation,
                "status": r.status,
                "subject": r.subject,
                "body": r.body,
                "mailto_url": r.mailto_url,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in reprints
        ]
        self._send_json({"reprints": reprints_data})

    def _handle_post_reprint(self, reprint_id: str, payload: dict[str, Any]) -> None:
        """POST /api/reprints/<id>: update author_email or status."""
        existing = self.server.store.get_reprint_request(reprint_id)
        if not existing:
            self._send_error_json(404, f"Reprint request '{reprint_id}' not found")
            return

        new_email = payload.get("author_email")
        new_status = payload.get("status")
        if new_status and new_status.upper() == "REJECTED":
            new_status = "DECLINED"
        new_subject = payload.get("subject")
        new_body = payload.get("body")
        new_mailto = payload.get("mailto_url")

        # Auto-recompute mailto_url if email or text updated without explicit mailto_url
        if (
            new_email is not None or new_subject is not None or new_body is not None
        ) and "mailto_url" not in payload:
            effective_email = (
                new_email if new_email is not None else existing.author_email
            )
            effective_subj = (
                new_subject if new_subject is not None else existing.subject
            )
            effective_body = new_body if new_body is not None else existing.body
            new_mailto = build_mailto_url(effective_email, effective_subj, effective_body)

        updated = self.server.store.update_reprint_request(
            request_id=reprint_id,
            author_email=new_email,
            status=new_status,
            mailto_url=new_mailto,
            subject=new_subject,
            body=new_body,
        )

        if not updated:
            self._send_error_json(500, f"Failed to update reprint request '{reprint_id}'")
            return

        self._send_json(
            {
                "status": "SUCCESS",
                "reprint": {
                    "id": updated.id,
                    "project_id": updated.project_id,
                    "paper_id": updated.paper_id,
                    "author_name": updated.author_name,
                    "author_email": updated.author_email,
                    "author_affiliation": updated.author_affiliation,
                    "status": updated.status,
                    "subject": updated.subject,
                    "body": updated.body,
                    "mailto_url": updated.mailto_url,
                    "created_at": updated.created_at,
                    "updated_at": updated.updated_at,
                },
            }
        )

    def _handle_post_ingest(self, payload: dict[str, Any]) -> None:
        """POST /api/papers/ingest: ingest author PDF copy into store."""
        project_id = payload.get("project_id")
        paper_id = payload.get("paper_id")
        pdf_path = payload.get("pdf_path")
        storage_dir = payload.get("storage_dir")

        if not paper_id or not pdf_path:
            self._send_error_json(400, "Missing required fields 'paper_id' and 'pdf_path'")
            return

        try:
            result = ingest_paper_copy(
                store=self.server.store,
                project_id=project_id,
                paper_id=paper_id,
                pdf_path=pdf_path,
                storage_dir=storage_dir,
            )
            self._send_json(result)
        except FileNotFoundError as err:
            self._send_error_json(404, str(err))
        except Exception as err:
            self._send_error_json(400, str(err))

    # -------------------------------------------------------------------------
    # Static Assets & Security Guard
    # -------------------------------------------------------------------------

    def _handle_static_file(self, raw_path: str) -> None:
        """
        Serve static frontend assets with strict path traversal attack prevention.
        """
        unquoted = urllib.parse.unquote(raw_path).replace("\\", "/")
        rel_path = unquoted.lstrip("/")
        if rel_path.startswith("static/"):
            rel_path = rel_path[len("static/") :]
        if not rel_path or rel_path.endswith("/"):
            rel_path += "index.html"

        target_path = (self.server.static_dir / rel_path).resolve()

        # Path traversal guard: ensure candidate path is strictly within static_dir
        try:
            target_path.relative_to(self.server.static_dir)
        except ValueError:
            self._send_error_json(403, "Access Denied: Path traversal detected")
            return

        if not target_path.exists() or not target_path.is_file():
            self._send_error_json(404, f"Static asset not found: {raw_path}")
            return

        mime_type, _ = mimetypes.guess_type(str(target_path))
        if not mime_type:
            mime_type = "application/octet-stream"
        if mime_type.startswith("text/") or mime_type in (
            "application/javascript",
            "application/json",
        ):
            mime_type = f"{mime_type}; charset=utf-8"

        try:
            content = target_path.read_bytes()
        except OSError as err:
            self._send_error_json(500, f"Error reading asset: {err}")
            return

        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content)

    # -------------------------------------------------------------------------
    # JSON Response Helpers
    # -------------------------------------------------------------------------

    def _send_json(self, data: Any, status: int = 200) -> None:
        encoded = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(encoded)

    def _send_error_json(self, status: int, message: str) -> None:
        self._send_json({"error": message, "status": "ERROR"}, status=status)


class SciFiWebServer(ThreadingHTTPServer):
    """
    Embedded multi-threaded HTTP server providing REST API endpoints and
    secure static file serving for the SciFi literature research cockpit.
    """

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        store: Optional[LiteratureStore] = None,
        host: str = "127.0.0.1",
        port: int = 8080,
        static_dir: Optional[Path | str] = None,
        auto_fallback: bool = True,
        max_attempts: int = 10,
    ) -> None:
        self.host = host
        self.requested_port = port
        self.store = (
            store if store is not None else LiteratureStore(DEFAULT_CENTRAL_STORE_PATH)
        )
        self.static_dir = (
            Path(static_dir).resolve()
            if static_dir is not None
            else get_default_static_dir()
        )

        if auto_fallback:
            bound = False
            last_err: Optional[Exception] = None
            for offset in range(max_attempts):
                candidate_port = port + offset
                try:
                    super().__init__((host, candidate_port), SciFiRequestHandler)
                    bound = True
                    break
                except OSError as e:
                    last_err = e
                    continue
            if not bound:
                raise OSError(
                    f"Could not bind to any port in range {port}..{port + max_attempts - 1}: {last_err}"
                )
        else:
            super().__init__((host, port), SciFiRequestHandler)

        self.port = self.server_address[1]
