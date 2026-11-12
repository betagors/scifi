import threading
import urllib.request
from pathlib import Path

from scifi.literature.store import LiteratureStore
from scifi.web.server import (
    SciFiWebServer,
    find_available_port,
    get_default_static_dir,
)


def test_frontend_assets_present():
    static_dir = get_default_static_dir()
    index_file = static_dir / "index.html"
    app_js = static_dir / "app.js"
    styles_css = static_dir / "styles.css"

    assert index_file.exists(), f"Missing {index_file}"
    assert app_js.exists(), f"Missing {app_js}"
    assert styles_css.exists(), f"Missing {styles_css}"

    content = index_file.read_text(encoding="utf-8")
    assert "SciFi Research Cockpit" in content
    assert "network-container" in content
    assert "reprints-table" in content
    assert "projects-dropdown" in content
    assert "paper-drawer" in content
    assert "session-selector" in content

    # Verify CDN script dependencies in index.html
    assert "vis-network" in content
    assert "tailwindcss" in content

    # Verify styles.css
    css_content = styles_css.read_text(encoding="utf-8")
    assert "#network-container" in css_content
    assert "#paper-drawer" in css_content

    # Verify app.js core routines
    js_content = app_js.read_text(encoding="utf-8")
    assert "fetchProjects" in js_content
    assert "vis.Network" in js_content
    assert "updateReprintEmail" in js_content
    assert "submitIngestPdf" in js_content


def test_frontend_assets_served_by_web_server(tmp_path: Path):
    db_file = tmp_path / "cockpit.db"
    store = LiteratureStore(db_file)
    static_dir = get_default_static_dir()

    port = find_available_port(start_port=8960)
    server = SciFiWebServer(
        store=store,
        host="127.0.0.1",
        port=port,
        static_dir=static_dir,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        # GET / -> index.html
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as resp:
            assert resp.status == 200
            assert "text/html" in resp.headers.get("Content-Type", "")
            body = resp.read().decode("utf-8")
            assert "SciFi Research Cockpit" in body
            assert 'id="network-container"' in body
            assert 'id="reprints-table"' in body
            assert 'id="projects-dropdown"' in body
            assert 'id="paper-drawer"' in body
            assert 'id="session-selector"' in body

        # GET /app.js
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/app.js") as resp:
            assert resp.status == 200
            assert "javascript" in resp.headers.get("Content-Type", "")
            js_body = resp.read().decode("utf-8")
            assert "fetchProjects" in js_body
            assert "vis.Network" in js_body
            assert "updateReprintEmail" in js_body

        # GET /styles.css
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/styles.css") as resp:
            assert resp.status == 200
            assert "text/css" in resp.headers.get("Content-Type", "")
            css_body = resp.read().decode("utf-8")
            assert len(css_body) > 0
            assert "#network-container" in css_body
    finally:
        server.shutdown()
        server.server_close()
