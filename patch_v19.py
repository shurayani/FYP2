"""One-time patch #19: rename the folder  pages/  ->  views/   (fixes 'no such table: users' on Streamlit Cloud).

Why: Streamlit 1.66 treats a folder called 'pages' next to app.py as an old-style multipage app. A visitor who
opens a page link directly (e.g. .../Account, or a Home Screen icon saved on that page) then runs ONLY that page,
and app.py never runs - so the database is not created, the admin account does not exist and nothing is restored
from Supabase. IPECS already defines its pages itself with st.navigation in app.py, so the folder just needs a
different name. Every reference in app.py, utils/ui.py and README.md is updated. Nothing else changes.
Run once from the project folder:   python patch_v19.py"""
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OLD, NEW = ROOT / "pages", ROOT / "views"

# ---------------------------------------------------------------- move the page scripts
if OLD.exists():
    NEW.mkdir(exist_ok=True)
    for f in sorted(OLD.glob("*.py")):
        target = NEW / f.name
        assert not target.exists(), f"views/{f.name} already exists - stopping so nothing is overwritten"
        shutil.move(str(f), str(target))
        print(f"moved pages/{f.name} -> views/{f.name}")
    leftovers = [p for p in OLD.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    assert not leftovers, "pages/ still contains other files: " + ", ".join(str(p) for p in leftovers)
    shutil.rmtree(OLD)                       # only __pycache__ was left
    print("removed the empty pages/ folder")
else:
    print("pages/ folder already renamed")

# ---------------------------------------------------------------- update references
PATTERN = re.compile(r"\bpages/(\d+_[A-Za-z_]+\.py)")
for rel in ("app.py", "utils/ui.py", "README.md"):
    p = ROOT / rel
    s = p.read_text(encoding="utf-8")
    new, n = PATTERN.subn(r"views/\1", s)
    if n:
        p.write_text(new, encoding="utf-8")
    print(f"{rel}: {n} reference(s) updated")

missing = [m for m in PATTERN.findall((ROOT / "app.py").read_text(encoding="utf-8"))]
assert not missing, "app.py still refers to pages/"
for m in re.findall(r"views/(\d+_[A-Za-z_]+\.py)", (ROOT / "app.py").read_text(encoding="utf-8")):
    assert (NEW / m).exists(), "missing views/" + m
print("Done. Commit + push, then Reboot app on Streamlit Cloud.")