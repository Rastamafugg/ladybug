"""Purpose inventory. Recommendations never change a gate's authority."""
import ast
import html
from pathlib import Path
import re

from .core import digest


def inventory(root):
    rows = []
    catalogue_path = Path(root) / "wiki/internal/tooling/testing.html"
    catalogue = catalogue_path.read_text(encoding="utf-8") if catalogue_path.exists() else ""
    existing = {name: html.unescape(re.sub(r"<[^>]+>", "", body)).strip()
                for name, body in re.findall(r"<li><code>(verify[^<]+\.py)</code>(.*?)</li>", catalogue, re.S)}
    for path in sorted((Path(root) / "scripts").glob("verify*.py")):
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        flags = []
        if "fragment not in" in source or ".index(\"\\n" in source or "required_source" in source:
            flags.append("lexical-source-contract")
        if 'ROOT / "build"' in source or "ROOT/'build'" in source:
            flags.append("fixed-artifact-root")
        if "monitor" in source.lower():
            flags.append("monitor-reference-needs-transport-review")
        if "socket" in source or "subprocess" in source:
            flags.append("owns-transport-or-processes")
        if "runtime" in path.stem or "natural" in path.stem:
            recurrence = "relevant-runtime-changes; retain separate natural/manual acceptance"
        elif "source_documentation" in path.stem:
            recurrence = "source/interface/documentation changes; result separate from ROM construction"
        elif "overflow" in path.stem:
            recurrence = "packing/checker changes for synthetic controls; real capacity every build"
        else:
            recurrence = "relevant-input-or-checker changes; review existing approved card"
        rows.append({"file": path.relative_to(root).as_posix(), "sha256": digest(path),
                     "purpose": ast.get_docstring(tree) or "UNDOCUMENTED: manual purpose review required",
                     "existing_catalogue": existing.get(path.name, "missing from prior catalogue; purpose requires review"),
                     "recommendation": recurrence, "review_flags": flags,
                     "migration": "legacy; no gate retired or newly authorized"})
    return {"schema": 1, "method": "AST module purpose plus explicitly heuristic coupling flags",
            "authority": "inventory only; consult approved test cards", "verifiers": rows,
            "special_controls": [{"name": "PROFILE-FIT", "recurrence": "checker/limit/fixture changes or absent valid qualification evidence", "purpose": "qualify the size checker, not every game build"}]}
