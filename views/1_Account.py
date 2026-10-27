"""Module 1: User Account Management - register, login, logout, profile, password, deactivation."""
import streamlit as st

from src import auth, db_manager as db
from utils import pwa, ui
from utils.i18n import t

user = st.session_state.get("user")

# ------------------------------------------------------------------ not logged in: login / register
if not user:
    st.title("IPECS")
    st.caption(t("Intelligent Personal Expense Categorization System"))
    pwa.install_box()                     # 'Install IPECS app' (patch #13)
    tab_login, tab_reg, tab_admin = st.tabs([t("User Login"), t("Register"), t("Admin Login")])
    with tab_login:
        with st.form("login_form"):
            u = st.text_input(t("Username"))
            p = st.text_input(t("Password"), type="password")
            ok = st.form_submit_button(t("Log in"), type="primary")
        if ok:
            res, msg = auth.login(u, p)
            if res and res["role"] == "admin":
                st.error(t("This is an administrator account. Please use the Admin Login tab."))
            elif res:
                st.session_state["user"] = res
                st.session_state["_auto_synced"] = False
                st.session_state["_goto_dashboard"] = True
                st.rerun()
            else:
                st.error(t(msg))
    with tab_admin:
        st.caption(t("Administrator access only."))
        with st.form("admin_login_form"):
            au = st.text_input(t("Username"), key="adm_user")
            ap = st.text_input(t("Password"), type="password", key="adm_pw")
            aok = st.form_submit_button(t("Log in as administrator"), type="primary")
        if aok:
            res, msg = auth.login(au, ap)
            if res and res["role"] == "admin":
                st.session_state["user"] = res
                st.session_state["_auto_synced"] = False
                st.session_state["_goto_dashboard"] = True
                st.rerun()
            elif res:
                st.error(t("This account is not an administrator."))
            else:
                st.error(t(msg))
    with tab_reg:
        with st.form("register_form"):
            ru = st.text_input(t("Username"), key="reg_user")
            re_ = st.text_input(t("Email"), key="reg_email")
            rp = st.text_input(t("Password"), type="password", key="reg_pw")
            rc = st.text_input(t("Confirm password"), type="password", key="reg_pw2")
            sub = st.form_submit_button(t("Create account"), type="primary")
        if sub:
            ok, msg = auth.register(ru, re_, rp, rc)
            (st.success if ok else st.error)(t(msg))
    st.stop()

# ------------------------------------------------------------------ logged in
st.title(f"{t('Account')}")
fresh = db.get_user(user["id"])
tab_profile, tab_pw, tab_settings = st.tabs([t("Profile"), t("Change password"), t("Settings")])

with tab_profile:
    with st.form("profile_form"):
        new_name = st.text_input(t("Username"), value=fresh["username"])
        new_email = st.text_input(t("Email"), value=fresh["email"])
        save = st.form_submit_button(t("Save profile"), type="primary")
    if save:
        ok, msg = auth.update_profile(user["id"], new_name, new_email)
        if ok:
            st.session_state["user"].update(username=new_name.strip(), email=new_email.strip().lower())
            st.success(t(msg))
            st.rerun()
        else:
            st.error(t(msg))
    st.caption(f"{t('Role')}: {fresh['role']} · {t('Member since')}: {ui.local_time(fresh['created_at'], False)}")

with tab_pw:
    if user["role"] == "admin":
        st.caption(t("The administrator password is configured through the ADMIN_PASSWORD setting, but you can also change it here."))
    with st.form("pw_form"):
        cur = st.text_input(t("Current password"), type="password")
        new = st.text_input(t("New password"), type="password")
        conf = st.text_input(t("Confirm new password"), type="password")
        go = st.form_submit_button(t("Change password"), type="primary")
    if go:
        ok, msg = auth.change_password(user["id"], cur, new, conf)
        (st.success if ok else st.error)(t(msg))

with tab_settings:
    st.subheader(t("Application preferences"))
    st.write(t("The interface language can be changed from the sidebar (English / Bahasa Malaysia)."))
    if user["role"] != "admin":
        st.subheader(t("Data management"))
        n_tx = len(db.get_transactions(user["id"]))
        n_rc = len(db.get_receipts(user["id"]))
        st.write(t("You have {tx} transaction(s) and {rc} receipt(s) stored.", tx=n_tx, rc=n_rc))
        st.caption(t("Export your transactions from the Transactions page."))
        st.subheader(t("System information"))
        st.caption("IPECS · SQLite local database · Streamlit")
        st.subheader(t("Deactivate account"))
        st.warning(t("Deactivating your account will prevent you from logging in. Contact the administrator to reactivate it."))
        confirm = st.checkbox(t("I understand and want to deactivate my account"))
        if st.button(t("Deactivate my account"), disabled=not confirm):
            auth.deactivate_account(user["id"])
            lang = st.session_state.get("lang", "en")
            st.session_state.clear()
            st.session_state["lang"] = lang
            st.rerun()
    if st.button(t("Log out"), key="logout_account"):
        lang = st.session_state.get("lang", "en")
        st.session_state.clear()
        st.session_state["lang"] = lang
        st.rerun()
