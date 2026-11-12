# Web UI Cockpit

SciFi includes a lightweight browser-based research cockpit (`sf ui`) powered by a built-in HTTP server.

---

## Launching the Cockpit

To start the Web UI cockpit:

```bash
uv run sf ui
```

By default, the server listens on `http://127.0.0.1:8000`. You can customize the port or host:

```bash
uv run sf ui --host 0.0.0.0 --port 8080
```

---

## Cockpit Views & Capabilities

### 1. Literature Lineage Graph
- Interactive visual exploration of citation networks (foundational prior work and frontier developments).
- Visual node coloring by publication year, venue tier, and open-access accessibility.
- Instant node inspection showing extracted abstracts, benchmark leader scores, and methodology notes.

### 2. Research Projects Hub
- Multi-workspace project registry showing paper counts, open-access distributions, and active drafts.
- Automatic synchronization with local `.scifi/literature_manifest.json` workspace files.

### 3. Author Reprint Desk
- Central tracking dashboard for paywalled articles and author reprint requests.
- One-click `mailto:` generation populated with standard polite academic reprint requests.
- Direct drag-and-drop PDF ingestion to transition requests to `RECEIVED` and store copies in the content-addressed store.
