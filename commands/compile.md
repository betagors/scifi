---
description: Compile a LaTeX manuscript and diagnose build errors
argument-hint: "<path/to/main.tex>"
---

Execute the `compiler` skill on `$ARGUMENTS` (defaults to `main.tex` in the workspace root).

Steps the agent follows:
1. Run `scifi compile $ARGUMENTS` or call the `scifi_compile_latex` MCP tool with `{"entrypoint": "$ARGUMENTS"}`.
2. If `status == "SUCCESS"`: report the `pdf_path` and list any non-fatal warnings (undefined refs, missing cites, layout hbox counts).
3. If `status == "FAILED"`: read `errors[]`, navigate to the exact `file:line`, diagnose the syntax issue, fix it in place, and recompile.
4. If `status == "ENGINE_MISSING"`: execute the `action_required.install_command` returned by the tool, then retry.
5. After a successful build, cross-check `undefined_citations` against the `.bib` file if one is present.
