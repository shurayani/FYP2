"""One-time cleanup: removes decorative emoji/icons from the interface so it looks more professional.
Run once from the project folder:   python clean_emoji.py
(Status dots for Online/Offline are kept.)"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = [ROOT / "app.py", ROOT / "utils" / "ui.py", ROOT / "utils" / "i18n.py", *sorted((ROOT / "pages").glob("*.py"))]
KEEP = set("🟢🔴🟠")
EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\U0001F1E6-\U0001F1FF\uFE0F\u200d]+ ?")


def strip_line(line: str) -> str:
    if "page_icon" in line:                      # keep the browser-tab icon
        return line
    line = line.replace('"⚠️"', '"Yes"')           # the anomaly column needs a visible marker
    line = re.sub(r',\s*icon=("[^"]*"|\'[^\']*\')', "", line)   # st.page_link / st.Page icons
    def repl(m):
        kept = "".join(c for c in m.group(0) if c in KEEP)
        return (kept + " ") if kept else ""
    return EMOJI.sub(repl, line)


for f in FILES:
    if not f.exists():
        continue
    old = f.read_text(encoding="utf-8")
    new = "\n".join(strip_line(l) for l in old.split("\n"))
    if new != old:
        f.write_text(new, encoding="utf-8")
        print("cleaned", f.relative_to(ROOT))
print("Done. Restart Streamlit.")