"""Module 9: Sync Management - online/offline state, last sync, pending changes, conflicts, Sync Now."""
import pandas as pd
import streamlit as st

from src import db_manager as db, sync_manager
from utils import ui
from utils.i18n import t

user = ui.require_login()
uid = user["id"]
st.title(f"{t('Sync Status')}")

s = sync_manager.status(uid)
k = st.columns(4)
k[0].metric(t("Connection"), ("🟢 " + t("Online")) if s["online"] else ("🔴 " + t("Offline")))
k[1].metric(t("Last sync"), ui.local_time(s["last_sync"]) if s["last_sync"] else t("Never"))
k[2].metric(t("Pending changes"), s["pending"])
k[3].metric(t("Conflicts"), s["conflict_count"])

if not s["configured"]:
    st.warning(t("Supabase is not configured. IPECS works fully offline; add SUPABASE_URL and SUPABASE_KEY to .env to enable synchronisation."))

if st.button(t("Sync Now"), type="primary", disabled=not s["configured"]):
    with st.spinner(t("Synchronising...")):
        st.session_state["last_sync_result"] = sync_manager.sync_now(uid)
    st.rerun()

res = st.session_state.get("last_sync_result")
if res:
    (st.success if res["ok"] else st.warning)(res["message"])
    for c in res["conflicts"]:
        st.warning(t("Conflict on {tbl} record {rid}: the {kept} version was kept (last-write-wins).",
                     tbl=c["table"], rid=c["record_id"][:8], kept=t(c["kept"])))

st.subheader(t("Conflicts and the version kept"))
if not s["conflicts"]:
    st.caption(t("No conflicts."))
else:
    st.dataframe(pd.DataFrame({t("Table"): [c["table_name"] for c in s["conflicts"]],
                               t("Record"): [c["record_id"][:8] for c in s["conflicts"]],
                               t("Kept version"): [t(c["kept"]) if c["kept"] else "—" for c in s["conflicts"]],
                               t("Local time"): [ui.local_time(c["local_updated_at"]) for c in s["conflicts"]],
                               t("Remote time"): [ui.local_time(c["remote_updated_at"]) for c in s["conflicts"]]}),
                 width="stretch", hide_index=True)

st.subheader(t("Record sync status"))
entries = db.get_sync_entries(uid)
if not entries:
    st.caption(t("No records tracked yet."))
else:
    f = st.selectbox(t("Filter"), [t("All"), "pending", "synced", "conflict"])
    shown = [e for e in entries if f == t("All") or e["sync_status"] == f]
    st.dataframe(pd.DataFrame({t("Table"): [e["table_name"] for e in shown],
                               t("Record"): [e["record_id"][:8] for e in shown],
                               t("Operation"): [e["operation"] for e in shown],
                               t("Status"): [e["sync_status"] for e in shown],
                               t("Local change"): [ui.local_time(e["local_updated_at"]) for e in shown],
                               t("Synced at"): [ui.local_time(e["synced_at"]) for e in shown]}),
                 width="stretch", hide_index=True)
st.caption(t("Sync runs automatically once when you log in (if configured and online) and whenever you press Sync Now."))
