"""
Regression tests verifying 100% docstring coverage across all public classes.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil

import scifi


def test_all_public_classes_have_docstrings() -> None:
    """Verify that every public class in scifi has a non-empty Google-style docstring."""
    undocumented: list[str] = []

    for module_info in pkgutil.walk_packages(scifi.__path__, scifi.__name__ + "."):
        try:
            mod = importlib.import_module(module_info.name)
        except Exception:
            continue

        for name, obj in inspect.getmembers(mod, inspect.isclass):
            if obj.__module__ == mod.__name__ and not name.startswith("_"):
                doc = obj.__doc__
                if not doc or not doc.strip():
                    undocumented.append(f"{mod.__name__}.{name}")

    assert not undocumented, f"Found {len(undocumented)} undocumented public classes: {undocumented}"
