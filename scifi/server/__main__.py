"""
Entry point for running FastMCP server via `python -m scifi.server`.
"""

from __future__ import annotations

from scifi.server import mcp

if __name__ == "__main__":
    mcp.run()
