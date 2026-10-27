"""One-time patch #10: bank-style amount input (starts at 0.00; every digit you type pushes the value up
from the sen: 1 -> 0.01, 12 -> 0.12, 125 -> 1.25, 12500 -> 125.00; Backspace pushes it back down).
Used for: receipt total, manual amount, transaction add/edit, budget amount.
Run once from the project folder:   python patch_v10.py"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def edit(path, fn):
    p = ROOT / path
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def swap(s, old, new):
    assert old in s, "anchor not found: " + old[:80]
    return s.replace(old, new, 1)


# ============================================================ the input component (plain HTML/JS, no build step)
comp = ROOT / "components" / "money_input"
comp.mkdir(parents=True, exist_ok=True)
(comp / "index.html").write_text(r'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body { margin: 0; padding: 0; background: transparent; }
  body { font-family: "Source Sans Pro", "Source Sans 3", -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }
  #label { font-size: 14px; line-height: 20px; color: rgb(49, 51, 63); margin-bottom: 4px; }
  #box { display: flex; align-items: center; box-sizing: border-box; height: 40px; padding: 0 12px;
         background: rgb(240, 242, 246); border: 1px solid transparent; border-radius: 8px; }
  #box.focus { border-color: rgb(255, 75, 75); }
  #box.disabled { opacity: .5; }
  #prefix { color: rgba(49, 51, 63, 0.6); font-size: 16px; margin-right: 8px; user-select: none; }
  #amt { flex: 1; min-width: 0; border: 0; outline: 0; background: transparent; font: inherit; font-size: 16px;
         color: rgb(49, 51, 63); text-align: right; }
</style>
</head>
<body>
<div id="label"></div>
<div id="box"><span id="prefix">RM</span><input id="amt" type="text" inputmode="numeric" autocomplete="off"></div>
<script>
  var MAX = 99999999999;                       // 999,999,999.99
  var cents = 0, initArg = null, committed = null, timer = null;
  var input = document.getElementById("amt"), box = document.getElementById("box"), labelEl = document.getElementById("label");

  function send(type, data) { window.parent.postMessage(Object.assign({isStreamlitMessage: true, type: type}, data), "*"); }
  function fmt(c) { return (c / 100).toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2}); }
  function show() { input.value = fmt(cents); }
  function caretEnd() { var n = input.value.length; try { input.setSelectionRange(n, n); } catch (e) {} }
  function allSelected() { return input.value.length > 0 && input.selectionStart === 0 && input.selectionEnd === input.value.length; }
  function commit() {
    clearTimeout(timer);
    if (committed !== cents) { committed = cents; send("streamlit:setComponentValue", {value: cents / 100, dataType: "json"}); }
  }
  function schedule() { clearTimeout(timer); timer = setTimeout(commit, 600); }   // value reaches Python shortly after you stop typing

  // Digits never depend on the caret position: every digit is appended to the amount (bank style).
  input.addEventListener("beforeinput", function (e) {
    var t = e.inputType;
    if (t === "insertText" || t === "insertFromDrop") {
      e.preventDefault();
      if (allSelected()) cents = 0;                      // typing over a selected amount starts a fresh one
      var ds = (e.data || "").replace(/\D/g, "");
      for (var i = 0; i < ds.length; i++) cents = Math.min(cents * 10 + parseInt(ds[i], 10), MAX);
      show(); caretEnd(); schedule();
    } else if (t.indexOf("delete") === 0) {
      e.preventDefault();
      cents = (allSelected() || t === "deleteByCut") ? 0 : Math.floor(cents / 10);
      show(); caretEnd(); schedule();
    }
  });
  // fallback for input methods that cannot be cancelled (e.g. some Android keyboards)
  input.addEventListener("input", function () {
    var d = input.value.replace(/\D/g, "").slice(0, 11);
    cents = d ? Math.min(parseInt(d, 10), MAX) : 0;
    show(); caretEnd(); schedule();
  });
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); commit(); }
    if (e.key === "Escape") { cents = 0; show(); schedule(); }
  });
  input.addEventListener("paste", function (e) {
    e.preventDefault();
    var txt = (e.clipboardData || window.clipboardData).getData("text").replace(/[^0-9.]/g, "");
    if (!txt) return;
    cents = Math.min(txt.indexOf(".") >= 0 ? Math.round(parseFloat(txt) * 100) : parseInt(txt, 10) * 100, MAX) || 0;
    show(); caretEnd(); schedule();
  });
  // clicking anywhere in the box focuses the field and selects the amount (typing then starts from 0.0x)
  box.addEventListener("mousedown", function (e) { if (e.target !== input) setTimeout(function () { input.focus(); input.select(); }, 0); });
  input.addEventListener("focus", function () { box.classList.add("focus"); setTimeout(function () { input.select(); }, 0); });
  input.addEventListener("click", function () { input.select(); });
  input.addEventListener("mouseup", function (e) { e.preventDefault(); });
  input.addEventListener("blur", function () { box.classList.remove("focus"); commit(); });

  window.addEventListener("message", function (e) {
    if (!e.data || e.data.type !== "streamlit:render") return;
    var a = e.data.args || {};
    labelEl.textContent = a.label || "";
    labelEl.style.display = a.label ? "block" : "none";
    input.disabled = !!a.disabled;
    box.classList.toggle("disabled", !!a.disabled);
    if (initArg !== a.value) {                 // only (re)initialise when Python passes a NEW starting value
      initArg = a.value;
      cents = Math.round((Number(a.value) || 0) * 100);
      committed = cents;
      show();
    }
    send("streamlit:setFrameHeight", {height: a.label ? 68 : 44});
  });
  send("streamlit:componentReady", {apiVersion: 1});
</script>
</body>
</html>
''', encoding="utf-8")
print("created components/money_input/index.html")


# ============================================================ utils/ui.py: Python wrapper
def f_ui(s):
    if "def money_input" in s:
        return s
    s = swap(s, "import streamlit as st\n",
             "from pathlib import Path\n\nimport streamlit as st\nimport streamlit.components.v1 as components\n")
    s += '''

# ---------------------------------------------------------------- bank-style amount input
_MONEY_DIR = Path(__file__).resolve().parent.parent / "components" / "money_input"
_money_component = (components.declare_component("money_input", path=str(_MONEY_DIR))
                    if (_MONEY_DIR / "index.html").exists() else None)


def money_input(label, value=0.0, key=None, disabled=False):
    """Amount input that works like a bank app: starts at 0.00 and each digit pushes the value up from the sen
    (1 -> 0.01, 12 -> 0.12, 125 -> 1.25). Returns a float in RM with 2 decimals.
    The value is sent to Python when you press Enter or leave the field.
    `value` is only the STARTING amount (use a new `key` to start over). Falls back to st.number_input
    if the component folder is missing."""
    value = round(float(value or 0.0), 2)
    if _money_component is None:
        return float(st.number_input(label, min_value=0.0, value=value, step=0.10, format="%.2f", key=key))
    out = _money_component(label=label, value=value, disabled=disabled, key=key, default=value)
    try:
        return round(max(float(out), 0.0), 2)
    except (TypeError, ValueError):
        return value
'''
    return s


edit("utils/ui.py", f_ui)


# ============================================================ pages/2_Receipts.py
def f_receipts(s):
    if "ui.money_input" in s:
        return s
    s = swap(s, '        amount = c2.number_input(t("Total amount (RM)"), min_value=0.0, value=float(res["amount"]), step=0.10,\n'
                '                                 format="%.2f", key=f"cf_a_{k}")\n',
            '        with c2:\n'
            '            amount = ui.money_input(t("Total amount (RM)"), value=float(res["amount"]), key=f"cf_a_{k}")\n')
    s = swap(s, '    amount = c2.number_input(t("Amount (RM)"), min_value=0.0, value=0.0, step=0.10, format="%.2f", key=f"man_a_{n}")\n',
            '    with c2:\n'
            '        amount = ui.money_input(t("Amount (RM)"), value=0.0, key=f"man_a_{n}")\n')
    return s


edit("pages/2_Receipts.py", f_receipts)


# ============================================================ pages/3_Transactions.py
def f_tx(s):
    if "ui.money_input" in s:
        return s
    s = swap(s, '        a = c2.number_input(t("Amount (RM)"), min_value=0.0, step=0.10, format="%.2f", key="add_a")\n',
            '        add_n = st.session_state.setdefault("add_tx_n", 0)          # new key after every save = empty field\n'
            '        with c2:\n'
            '            a = ui.money_input(t("Amount (RM)"), value=0.0, key=f"add_a_{add_n}")\n')
    s = swap(s, '            st.success(t("Transaction saved."))\n            st.rerun()\n',
            '            st.success(t("Transaction saved."))\n'
            '            st.session_state["add_tx_n"] = add_n + 1\n'
            '            st.rerun()\n')
    s = swap(s, '        a = c2.number_input(t("Amount (RM)"), min_value=0.0, value=float(r["amount"]), step=0.10, format="%.2f")\n',
            '        with c2:\n'
            '            a = ui.money_input(t("Amount (RM)"), value=float(r["amount"]), key=f"edit_a_{r[\'id\']}")\n')
    return s


edit("pages/3_Transactions.py", f_tx)


# ============================================================ pages/5_Budget_Goals.py
def f_budget(s):
    if "ui.money_input" in s:
        return s
    s = swap(s, '        amt = c2.number_input(t("Monthly budget (RM)"), min_value=0.0, step=10.0, format="%.2f")\n',
            '        bud_n = st.session_state.setdefault("bud_n", 0)\n'
            '        with c2:\n'
            '            amt = ui.money_input(t("Monthly budget (RM)"), value=0.0, key=f"bud_a_{bud_n}")\n')
    s = swap(s, '            st.success(t("Budget goal saved."))\n            st.rerun()\n',
            '            st.success(t("Budget goal saved."))\n'
            '            st.session_state["bud_n"] = bud_n + 1\n'
            '            st.rerun()\n')
    s = swap(s, '                new_amt = e1.number_input(t("Adjust amount"), min_value=0.01, value=float(b["budget"]), step=10.0,\n'
                '                                          key=f"ba_{b[\'budget_id\']}", label_visibility="collapsed")\n',
            '                with e1:\n'
            '                    new_amt = ui.money_input("", value=float(b["budget"]), key=f"ba_{b[\'budget_id\']}")\n')
    s = swap(s, '                    db.update_budget(b["budget_id"], uid, new_amt)\n                    st.rerun()\n',
            '                    if new_amt > 0:\n'
            '                        db.update_budget(b["budget_id"], uid, new_amt)\n'
            '                    st.rerun()\n')
    return s


edit("pages/5_Budget_Goals.py", f_budget)
print("Done. Restart Streamlit.")