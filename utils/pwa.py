"""Installable app (Progressive Web App) support - patch #13.

* register_routes(): Streamlit only serves its own files, but an installable app needs /manifest.json, /sw.js and
  the icons at the ROOT of the site. This adds those few routes to the web server Streamlit is already running
  (a Tornado application) - nothing else is changed. Uses Streamlit internals, so if a future Streamlit version
  works differently it returns False and the card falls back to 'Add to Home screen' instructions.
* install_box(): the 'Install IPECS app' card shown on the login page (components/pwa_install/index.html).
"""
import gc
import re
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from utils.i18n import t

ROOT = Path(__file__).resolve().parent.parent
PWA_DIR = ROOT / "pwa"
_COMP_DIR = ROOT / "components" / "pwa_install"

_FILES = {                                     # the ONLY files served (no other path can be requested)
    "manifest.json": "application/manifest+json",
    "sw.js": "application/javascript; charset=utf-8",
    "offline.html": "text/html; charset=utf-8",
    "icon-192.png": "image/png",
    "icon-512.png": "image/png",
    "apple-touch-icon.png": "image/png",
}

_component = (components.declare_component("pwa_install", path=str(_COMP_DIR))
              if (_COMP_DIR / "index.html").exists() else None)
_routes_ok = False


def register_routes() -> bool:
    """Serve the PWA files at the site root. Safe to call on every rerun (only the first call does the work)."""
    global _routes_ok
    if _routes_ok:
        return True
    try:
        import tornado.web
    except ImportError:
        return False

    class PwaFileHandler(tornado.web.RequestHandler):
        def get(self, name):
            path = PWA_DIR / name
            if name not in _FILES or not path.is_file():
                raise tornado.web.HTTPError(404)
            self.set_header("Content-Type", _FILES[name])
            self.set_header("Cache-Control", "no-cache")
            if name == "sw.js":
                self.set_header("Service-Worker-Allowed", "/")
            self.write(path.read_bytes())

    pattern = r"/(" + "|".join(re.escape(n) for n in _FILES) + r")"
    found = False
    try:
        for obj in gc.get_objects():                       # find the web server Streamlit created
            try:
                if not isinstance(obj, tornado.web.Application):
                    continue
            except Exception:
                continue
            found = True
            if not getattr(obj, "_ipecs_pwa_routes", False):
                obj.add_handlers(r".*", [(pattern, PwaFileHandler)])    # checked BEFORE Streamlit's own routes
                obj._ipecs_pwa_routes = True
    except Exception:
        return False
    _routes_ok = found
    return found


def install_box():
    """'Install IPECS app' card. Hidden automatically when IPECS is already running as the installed app."""
    routes = register_routes()
    if _component is None:
        return
    strings = {
        "title": t("Use IPECS like an app"),
        "text": t("Install it on your phone: it opens full-screen, with its own icon on the home screen."),
        "button": t("Install IPECS app"),
        "installing": t("Installing..."),
        "installed_title": t("IPECS is installed"),
        "installed_text": t("Open it from your home screen."),
        "ios_steps": t("In Safari, tap the Share button (the square with an arrow), then choose 'Add to Home Screen' and tap 'Add'."),
        "menu_steps": t("Open the browser menu (the three dots) and choose 'Install app' or 'Add to Home screen'."),
        "http_steps": t("This link is not secure (http://), so the phone can only add a shortcut: open the browser menu (the three dots) and choose 'Add to Home screen'. For the full app, open the https:// link shown by start_phone.py --tunnel."),
        "cancelled": t("Installation was cancelled. You can press the button again."),
    }
    _component(routes=routes, dark=bool(st.session_state.get("dark_mode")), s=strings, key="pwa_install", default=None)
