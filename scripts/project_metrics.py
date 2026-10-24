"""Write docs/project_metrics.md: size of the codebase, datasets, tests and chart library — all measured.

Usage:
    python scripts/project_metrics.py [--pytest]   # --pytest also runs the test suite and records the result
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def count_lines(paths) -> int:
    return sum(len(p.read_text(encoding="utf-8").splitlines()) for p in paths)


def functions_in(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n.name for n in tree.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")]


def main() -> None:
    py = [p for p in ROOT.rglob("*.py") if ".venv" not in p.parts and "__pycache__" not in p.parts]
    groups = {
        "src/data": list((ROOT / "src" / "data").glob("*.py")),
        "src/analysis": list((ROOT / "src" / "analysis").glob("*.py")),
        "src/visualization": list((ROOT / "src" / "visualization").glob("*.py")),
        "src/ui + utils": list((ROOT / "src" / "ui").glob("*.py")) + list((ROOT / "src" / "utils").glob("*.py")),
        "pages + app.py": list((ROOT / "pages").glob("*.py")) + [ROOT / "app.py"],
        "scripts": list((ROOT / "scripts").glob("*.py")),
        "tests": list((ROOT / "tests").glob("*.py")),
    }
    chart_fns = [f for f in functions_in(ROOT / "src/visualization/charts.py")
                 if f not in ("binned_relationship",)] + functions_in(ROOT / "src/visualization/maps.py")
    test_fns = sum(len([f for f in functions_in(p) if f.startswith("test_")]) for p in groups["tests"])
    manifest = json.loads((ROOT / "data/processed/pipeline_manifest.json").read_text())
    L = ["# Project metrics", "",
         f"_Measured {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `scripts/project_metrics.py`._", "",
         "## Code", "", "| Area | Files | Lines |", "|---|---|---|"]
    for k, files in groups.items():
        L.append(f"| {k} | {len(files)} | {count_lines(files):,} |")
    L += [f"| **Total Python** | {len(py)} | {count_lines(py):,} |", "",
          "## Visualisation library", "",
          f"- {len(chart_fns)} chart functions ({len(functions_in(ROOT / 'src/visualization/maps.py'))} geographic): "
          + ", ".join(f"`{f}`" for f in chart_fns), f"- {len(list((ROOT / 'pages').glob('*.py')))} dashboard pages", "",
          "## Data (from pipeline_manifest.json)", ""]
    for name, o in manifest["outputs"].items():
        L.append(f"- `{name}`: " + ", ".join(f"{k} = {v:,}" if isinstance(v, int) else f"{k} = {v}" for k, v in o.items()))
    L += ["", "## Tests", "", f"- {test_fns} test functions in {len(groups['tests'])} files "
          "(parametrised cases expand this number when run)."]
    if "--pytest" in sys.argv:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, capture_output=True, text=True)
        last = [l for l in r.stdout.strip().splitlines() if l.strip()][-1]
        L.append(f"- Last full run: `{last}`")
    (ROOT / "docs" / "project_metrics.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
