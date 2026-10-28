"""One-time patch #27:
  1. Transactions > History: the selected transaction STAYS selected after you move an item (or save changes),
     so you can move several items of the same receipt one after another. If the transaction disappears
     (its last item was moved), the transaction the item went to is selected instead.
  2. Dashboard cards (receipt, budget, alerts, transactions, forecast) and the profile card: the WHOLE card is
     clickable, not only its words.
  3. Login page: the install card becomes one green 'Install IPECS app' button with a download icon, placed under
     the login form (no title or explanation; on iPhone the steps still appear after a tap).
Run once from the project folder:   python patch_v27.py      then commit + push + Reboot app."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def edit(path, fn):
    p = ROOT / path
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def swap(s, old, new):
    assert old in s, "anchor not found: " + old[:80]
    return s.replace(old, new, 1)


# ============================================================ 1. keep the selected transaction
def f_tx(s):
    if 'st.session_state["tx_pick"]' in s:
        return s
    s = swap(s, '''        r = by_id[st.selectbox(t("Select a transaction"), list(by_id.keys()), format_func=_tx_label)]
''', '''        ids = list(by_id.keys())
        keep = st.session_state.get("tx_pick")             # stays on the same transaction after a move or a save
        r = by_id[st.selectbox(t("Select a transaction"), ids, index=ids.index(keep) if keep in ids else 0,
                               format_func=_tx_label)]
        st.session_state["tx_pick"] = r["id"]
''')
    s = swap(s, '''                db.move_item(uid, it_id, cats[new_cat])
''', '''                db.move_item(uid, it_id, cats[new_cat])
                still = db.get_row("transactions", r["id"])
                st.session_state["tx_pick"] = (r["id"] if still and not still["is_deleted"]
                                               else db.get_row("transaction_items", it_id)["transaction_id"])
''')
    return s


edit("views/3_Transactions.py", f_tx)
print("3_Transactions.py ok")


# ============================================================ 2. whole card clickable
CSS = '''
/* ---------- the whole card is the link (patch #27): Streamlit sizes a page link to its words, so stretch it */
[class*="st-key-dlink"] [data-testid="stElementContainer"]:has([data-testid="stPageLink"]),
.st-key-profilebox [data-testid="stElementContainer"]:has([data-testid="stPageLink"]) {
    position:absolute !important; inset:0 !important; width:100% !important; height:100% !important;
    max-width:none !important; min-width:0 !important; margin:0 !important; z-index:5; }
[class*="st-key-dlink"] [data-testid="stPageLink"], [class*="st-key-dlink"] [data-testid="stPageLink"] div,
.st-key-profilebox [data-testid="stPageLink"], .st-key-profilebox [data-testid="stPageLink"] div {
    position:static !important; }
[class*="st-key-dlink"] [data-testid="stPageLink-NavLink"], .st-key-profilebox [data-testid="stPageLink-NavLink"] {
    position:absolute !important; inset:0 !important; width:100% !important; height:100% !important;
    margin:0 !important; padding:0 !important; opacity:0; cursor:pointer; }
'''


def f_app(s):
    if "the whole card is the link" in s:
        return s
    s = swap(s, "</style>\n\"\"\"\n", CSS + "</style>\n\"\"\"\n")
    for line in ('            st.page_link("views/6_Reports.py", label=t("Open reports"))\n',
                 '            st.page_link("views/5_Budget_Goals.py", label=t("Open budget goals"))\n',
                 '                    st.page_link("views/7_Anomaly_Alerts.py", label=t("View all alerts"))\n',
                 '                    st.page_link("views/3_Transactions.py", label=t("All transactions"))\n',
                 '                    st.page_link("views/8_Forecast.py", label=t("Open forecasts"))\n'):
        s = swap(s, line, line.replace("))\n", '), width="stretch")\n'))
    return s


edit("app.py", f_app)
print("app.py ok")


# ============================================================ 3. install button under the login form
def f_account(s):
    if "# install button (patch #27)" in s:
        return s
    s = swap(s, "    pwa.install_box()                     # 'Install IPECS app' (patch #13)\n", "")
    return swap(s, "            (st.success if ok else st.error)(t(msg))\n    st.stop()\n",
                "            (st.success if ok else st.error)(t(msg))\n"
                "    st.write(\"\")\n"
                "    pwa.install_box()                     # install button (patch #27)\n"
                "    st.stop()\n")


edit("views/1_Account.py", f_account)


def f_card(s):
    if "DL_ICON" in s:
        return s
    s = swap(s, '''  #card { display: none; box-sizing: border-box; padding: 12px 14px; border: 1px solid #D3DCDA; border-radius: 12px;
          background: #FFFFFF; color: #16253D; }''', '''  #card { display: none; box-sizing: border-box; padding: 2px 0; color: #16253D; }''')
    s = swap(s, "body.dark #card { background: #1b2734; border-color: #2c4a66; color: #e6eef6; }",
             "body.dark #card { color: #e6eef6; }")
    s = swap(s, "#head { display: flex; align-items: center; gap: 12px; }", "#head { display: none; }")
    s = swap(s, "#btn { display: none; margin-top: 10px; width: 100%; height: 42px;",
             "#btn { display: none; align-items: center; justify-content: center; gap: 8px; margin: 0; width: 100%; height: 44px;")
    s = swap(s, "  function send(type, data)", '''  var DL_ICON = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
                'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
                '<path d="M12 4v11"/><path d="M7 10l5 5 5-5"/><path d="M5 20h14"/></svg>';
  function esc(x) { var d = document.createElement("div"); d.textContent = x || ""; return d.innerHTML; }
  function send(type, data)''')
    s = swap(s, "if (e.standalone) { card.style.display = \"none\"; fitHeight(); return; }",
             "if (e.standalone || st.installed) { card.style.display = \"none\"; fitHeight(); return; }")
    s = swap(s, 'btn.style.display = st.installed ? "none" : "block";', 'btn.style.display = "flex";')
    s = swap(s, "btn.textContent = busy ? S.installing : S.button;",
             'btn.innerHTML = DL_ICON + "<span>" + esc(busy ? S.installing : S.button) + "</span>";')
    return s


edit("components/pwa_install/index.html", f_card)
print("login page + install button ok")
print("Done. Commit + push, then Reboot app (and restart Streamlit on the laptop).")