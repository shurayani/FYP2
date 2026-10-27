"""One-time patch #13: use IPECS on a PHONE and INSTALL it like an app (Progressive Web App).
  * the login page gets an 'Install IPECS app' card:
      - Android / Chrome / Edge (https link) : one tap -> the phone's own install dialog -> IPECS icon on the home screen
      - iPhone / iPad                        : Apple does not allow an install button, so the card shows the
                                               2 steps (Share -> Add to Home Screen)
      - plain http:// link                   : the card explains how to add a shortcut instead
    once installed, IPECS opens full-screen with its own icon; the card hides itself inside the installed app
  * new files : pwa/ (manifest, service worker, offline page, icons), components/pwa_install/index.html,
                utils/pwa.py, start_phone.py
  * changed   : pages/1_Account.py (card on the login page), utils/i18n.py (BM strings), README.md

IMPORTANT - phones only allow a real install from a SECURE (https://) link. IPECS runs on your computer, so:
    python start_phone.py            same Wi-Fi only, http://192.168.x.x:8501 -> works in the phone browser,
                                     but can only be added as a shortcut (not a full install)
    python start_phone.py --tunnel   secure https://....trycloudflare.com link -> full install, works on any network
                                     (needs the free 'cloudflared' program, see README section 'Use IPECS on your phone')
Your computer must stay on with IPECS running while the phone uses it - the data stays on your computer.

Run once from the project folder:   python patch_v13.py      (needs opencv-python, already in requirements.txt)"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def edit(path, fn):
    p = ROOT / path
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def swap(s, old, new):
    assert old in s, "anchor not found: " + old[:80]
    return s.replace(old, new, 1)


def write_new(path, text):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    print("wrote", path)


# ============================================================ pwa/manifest.json
manifest = {
    "id": "/",
    "name": "IPECS - Expense Tracker",
    "short_name": "IPECS",
    "description": "Intelligent Personal Expense Categorization System",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "background_color": "#ffffff",
    "theme_color": "#2E74B5",
    "icons": [
        {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ],
}
write_new("pwa/manifest.json", json.dumps(manifest, indent=2) + "\n")

# ============================================================ pwa/sw.js (service worker)
write_new("pwa/sw.js", r'''// IPECS service worker - makes the app installable.
// IPECS needs a live connection to the computer it runs on, so pages are NOT cached for offline use.
// Only a small "cannot reach IPECS" page is kept, shown when that computer is off or out of reach.
const CACHE = "ipecs-pwa-v1";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((c) => c.add("/offline.html"))
      .catch(() => {})
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.mode !== "navigate") return;      // data, images and the live connection go straight to the network
  event.respondWith(
    fetch(event.request).catch(() =>
      caches.match("/offline.html").then((r) => r || new Response("IPECS is not reachable.", {status: 503}))
    )
  );
});
''')

# ============================================================ pwa/offline.html
write_new("pwa/offline.html", r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#2E74B5">
<title>IPECS - not reachable</title>
<style>
  body { margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
         font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif; background: #f4f9fe; color: #1f3b57; }
  .card { max-width: 340px; margin: 24px; padding: 24px; background: #fff; border: 1px solid #cfe2f5;
          border-radius: 14px; text-align: center; }
  img { width: 72px; height: 72px; border-radius: 16px; }
  h1 { font-size: 20px; margin: 14px 0 8px; }
  p { font-size: 14px; line-height: 1.5; margin: 0 0 10px; }
  .ms { color: #5b7690; }
  button { margin-top: 8px; width: 100%; height: 44px; border: 0; border-radius: 8px; background: #2E74B5;
           color: #fff; font-size: 15px; font-weight: 600; }
</style>
</head>
<body>
<div class="card">
  <img src="/icon-192.png" alt="">
  <h1>Cannot reach IPECS</h1>
  <p>IPECS runs on your computer. Make sure the computer is on, IPECS (start_phone.py) is running and you have
     internet, then try again.</p>
  <p class="ms">Tidak dapat mencapai IPECS. Pastikan komputer dihidupkan, IPECS sedang berjalan dan anda
     mempunyai internet, kemudian cuba lagi.</p>
  <button onclick="location.reload()">Try again / Cuba lagi</button>
</div>
</body>
</html>
''')

# ============================================================ pwa icons (drawn with OpenCV: white receipt on IPECS blue)
import cv2            # noqa: E402  (opencv-python is already a requirement)
import numpy as np    # noqa: E402

BLUE, WHITE, LINE, DARK = (181, 116, 46), (255, 255, 255), (233, 215, 190), (121, 78, 31)   # BGR
img = np.zeros((512, 512, 3), np.uint8)
img[:] = BLUE                                              # full-bleed background -> also valid as a 'maskable' icon
left, right, top, bottom, tooth = 166, 346, 104, 392, 20
pts = [(left, top), (right, top), (right, bottom)]
x, down = right, False
while x > left:                                            # zig-zag torn edge at the bottom of the receipt
    x = max(left, x - 18)
    pts.append((x, bottom - (0 if down else tooth)))
    down = not down
pts.append((left, bottom))
cv2.fillPoly(img, [np.array(pts, np.int32)], WHITE, lineType=cv2.LINE_AA)
for y, x2 in ((152, 316), (186, 290), (220, 316), (254, 270)):
    cv2.line(img, (196, y), (x2, y), LINE, 12, cv2.LINE_AA)
cv2.line(img, (196, 296), (316, 296), DARK, 6, cv2.LINE_AA)
cv2.putText(img, "RM", (204, 352), cv2.FONT_HERSHEY_DUPLEX, 1.55, DARK, 4, cv2.LINE_AA)
for name, size in (("icon-512.png", 512), ("icon-192.png", 192), ("apple-touch-icon.png", 180)):
    out = img if size == 512 else cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".png", out)                   # imencode + write_bytes: safe for non-ASCII folder names
    assert ok, "could not create " + name
    (ROOT / "pwa" / name).write_bytes(buf.tobytes())
    print("wrote pwa/" + name)

# ============================================================ components/pwa_install/index.html (install card)
write_new("components/pwa_install/index.html", r'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body { margin: 0; padding: 0; background: transparent; }
  body { font-family: "Source Sans Pro", "Source Sans 3", -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }
  #card { display: none; box-sizing: border-box; padding: 12px 14px; border: 1px solid #cfe2f5; border-radius: 12px;
          background: #f4f9fe; color: #1f3b57; }
  body.dark #card { background: #1b2734; border-color: #2c4a66; color: #e6eef6; }
  #head { display: flex; align-items: center; gap: 12px; }
  #icon { width: 40px; height: 40px; border-radius: 10px; flex: none; }
  #title { font-weight: 650; font-size: 15px; line-height: 1.3; }
  #text { font-size: 13px; line-height: 1.4; opacity: .85; }
  #btn { display: none; margin-top: 10px; width: 100%; height: 42px; border: 0; border-radius: 8px; background: #2E74B5;
         color: #fff; font: inherit; font-size: 15px; font-weight: 600; cursor: pointer; }
  #btn:disabled { opacity: .6; cursor: default; }
  #steps { display: none; margin-top: 10px; padding: 10px 12px; border-radius: 8px; font-size: 13px; line-height: 1.5;
           background: #e6f1fc; }
  body.dark #steps { background: #22374b; }
</style>
</head>
<body>
<div id="card">
  <div id="head"><img id="icon" alt=""><div><div id="title"></div><div id="text"></div></div></div>
  <button id="btn" type="button"></button>
  <div id="steps"></div>
</div>
<script>
  // Streamlit custom component (same protocol as components/money_input). It runs in an iframe from the same
  // origin, so it can add the manifest to the main page and catch the browser's install prompt there.
  var S = {}, routes = false, started = false, lastHeight = -1, stepsText = "", busy = false;
  var P = null, D = null;
  try { P = window.parent; D = P.document; } catch (e) { P = null; D = null; }
  var card = document.getElementById("card"), btn = document.getElementById("btn"), steps = document.getElementById("steps");

  function send(type, data) { window.parent.postMessage(Object.assign({isStreamlitMessage: true, type: type}, data), "*"); }
  function fitHeight() {
    var h = card.style.display === "none" ? 0 : Math.ceil(card.getBoundingClientRect().height) + 2;
    if (h !== lastHeight) { lastHeight = h; send("streamlit:setFrameHeight", {height: h}); }
  }
  function addHead(tag, attrs) {
    if (!D || D.getElementById(attrs.id)) return;
    var el = D.createElement(tag);
    for (var k in attrs) el.setAttribute(k, attrs[k]);
    D.head.appendChild(el);
  }

  function state() {                    // shared with later re-renders through the main window
    if (!P) return {prompt: null, installed: false};
    if (!P.__ipecsPwa) {
      var st = P.__ipecsPwa = {prompt: null, installed: false, sw: false};
      P.addEventListener("beforeinstallprompt", function (e) { e.preventDefault(); st.prompt = e; });
      P.addEventListener("appinstalled", function () { st.installed = true; st.prompt = null; });
    }
    return P.__ipecsPwa;
  }

  function setupPage() {                // listener first, then the manifest (the prompt fires after the manifest is read)
    var st = state();
    if (!D) return;
    addHead("meta", {id: "ipecs-theme", name: "theme-color", content: "#2E74B5"});
    addHead("meta", {id: "ipecs-mobile-capable", name: "mobile-web-app-capable", content: "yes"});
    addHead("meta", {id: "ipecs-apple-capable", name: "apple-mobile-web-app-capable", content: "yes"});
    addHead("meta", {id: "ipecs-apple-title", name: "apple-mobile-web-app-title", content: "IPECS"});
    addHead("meta", {id: "ipecs-apple-bar", name: "apple-mobile-web-app-status-bar-style", content: "default"});
    if (!routes) return;
    addHead("link", {id: "ipecs-manifest", rel: "manifest", href: "/manifest.json"});
    addHead("link", {id: "ipecs-touch-icon", rel: "apple-touch-icon", href: "/apple-touch-icon.png"});
    if (!st.sw && P.isSecureContext && "serviceWorker" in P.navigator) {
      st.sw = true;
      P.navigator.serviceWorker.register("/sw.js", {scope: "/"}).catch(function () {});
    }
  }

  function env() {
    var nav = P ? P.navigator : navigator, win = P || window;
    var ios = /iphone|ipad|ipod/i.test(nav.userAgent) || (nav.platform === "MacIntel" && nav.maxTouchPoints > 1);
    var standalone = false;
    try { standalone = win.matchMedia("(display-mode: standalone)").matches || nav.standalone === true; } catch (e) {}
    return {ios: ios, standalone: standalone, secure: !!win.isSecureContext};
  }

  function render() {
    var st = state(), e = env();
    if (e.standalone) { card.style.display = "none"; fitHeight(); return; }   // already running as the installed app
    card.style.display = "block";
    document.getElementById("title").textContent = st.installed ? S.installed_title : S.title;
    document.getElementById("text").textContent = st.installed ? S.installed_text : S.text;
    btn.style.display = st.installed ? "none" : "block";
    btn.disabled = busy;
    btn.textContent = busy ? S.installing : S.button;
    if (st.prompt) stepsText = "";
    else if (e.ios) stepsText = S.ios_steps;
    else if (!e.secure) stepsText = S.http_steps;
    else stepsText = S.menu_steps;
    if (st.installed || st.prompt) steps.style.display = "none";
    fitHeight();
  }

  btn.addEventListener("click", function () {
    var st = state();
    if (st.prompt && !busy) {                       // Chrome / Edge / Samsung Internet: the phone's own install dialog
      var p = st.prompt;
      busy = true; render();
      p.prompt();
      p.userChoice.then(function (choice) {
        st.prompt = null;                           // a prompt can only be shown once
        if (choice && choice.outcome === "accepted") st.installed = true;
        else { steps.textContent = S.cancelled; steps.style.display = "block"; }
      }).catch(function () { st.prompt = null; }).then(function () { busy = false; render(); });
      return;
    }
    steps.textContent = stepsText;                  // iPhone, http:// links or browsers without an install prompt
    steps.style.display = "block";
    fitHeight();
  });

  window.addEventListener("message", function (e) {
    if (!e.data || e.data.type !== "streamlit:render") return;
    var a = e.data.args || {};
    S = a.s || {};
    routes = !!a.routes;
    document.body.classList.toggle("dark", !!a.dark);
    document.getElementById("icon").src = routes ? "/icon-192.png" : "";
    document.getElementById("icon").style.display = routes ? "block" : "none";
    if (!started) {
      started = true;
      setupPage();
      setInterval(render, 700);                     // the install prompt can arrive a little after the page loads
    }
    render();
  });
  send("streamlit:componentReady", {apiVersion: 1});
</script>
</body>
</html>
''')

# ============================================================ utils/pwa.py
write_new("utils/pwa.py", r'''"""Installable app (Progressive Web App) support - patch #13.

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
''')

# ============================================================ start_phone.py (launcher)
write_new("start_phone.py", r'''"""Start IPECS so you can open it on your PHONE (patch #13).

    python start_phone.py            same Wi-Fi: prints http://<this computer>:8501 - open it in the phone browser.
                                     Works, but phones only add a SHORTCUT from an http:// link.
    python start_phone.py --tunnel   also creates a secure https://....trycloudflare.com link with the free
                                     'cloudflared' program -> the phone can INSTALL IPECS as an app, from any network.

Keep this window open while you use IPECS on the phone. Press Ctrl+C to stop."""
import argparse
import re
import shutil
import socket
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def lan_ip():
    """This computer's address on the Wi-Fi network (no data is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def banner(lines):
    width = max(len(x) for x in lines) + 4
    print("\n" + "=" * width)
    for x in lines:
        print("  " + x)
    print("=" * width + "\n", flush=True)


def show_qr(url):
    try:
        import qrcode                      # optional: pip install qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.print_ascii(invert=True)
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(description="Start IPECS for phone access.")
    ap.add_argument("--tunnel", action="store_true", help="create a secure https link with cloudflared (needed to install the app)")
    ap.add_argument("--port", type=int, default=8501)
    args = ap.parse_args()

    try:
        sys.path.insert(0, str(ROOT))
        from utils.config import ADMIN_PASSWORD
        if ADMIN_PASSWORD == "admin123":
            print("WARNING: the admin password is still 'admin123'. Other people can now reach IPECS - "
                  "set ADMIN_PASSWORD in .env first.\n")
    except Exception:
        pass

    cloudflared = shutil.which("cloudflared") if args.tunnel else None
    if args.tunnel and not cloudflared:
        print("cloudflared was not found. Install it first (see README, 'Use IPECS on your phone'), "
              "or run without --tunnel for same-Wi-Fi access.")
        sys.exit(1)

    st = subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
                           "--server.address", "0.0.0.0", "--server.port", str(args.port),
                           "--server.headless", "true"], cwd=str(ROOT))
    local = f"http://{lan_ip()}:{args.port}"
    banner(["IPECS is running.",
            f"On this computer : http://localhost:{args.port}",
            f"Phone, same Wi-Fi: {local}   (browser only - shortcut, not a full install)",
            "If the phone cannot open it, allow Python through the computer's firewall (private networks)."])

    procs = [st]
    if cloudflared:
        tun = subprocess.Popen([cloudflared, "tunnel", "--no-autoupdate", "--url", f"http://localhost:{args.port}"],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                               errors="replace")
        procs.append(tun)

        def watch():
            shown = False
            for line in tun.stdout:
                m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
                if m and not shown:
                    shown = True
                    banner(["SECURE LINK FOR THE PHONE (install the app from here):", m.group(0),
                            "Open it in Chrome (Android) or Safari (iPhone), then use 'Install IPECS app' on the login page.",
                            "The link changes every time you start the tunnel; an installed app needs the same link,",
                            "so for daily use keep this window running (or set up a named Cloudflare tunnel)."])
                    show_qr(m.group(0))
        threading.Thread(target=watch, daemon=True).start()
        print("Starting the secure tunnel (takes a few seconds)...", flush=True)

    try:
        st.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()


if __name__ == "__main__":
    main()
''')


# ============================================================ pages/1_Account.py: card on the login page
def f_account(s):
    if "pwa.install_box()" in s:
        return s
    s = swap(s, "from utils import ui\n", "from utils import pwa, ui\n")
    return swap(s, '    st.caption(t("Intelligent Personal Expense Categorization System"))\n',
                '    st.caption(t("Intelligent Personal Expense Categorization System"))\n'
                '    pwa.install_box()                     # \'Install IPECS app\' (patch #13)\n')


edit("pages/1_Account.py", f_account)
print("1_Account.py ok")


# ============================================================ utils/i18n.py
def f_i18n(s):
    if "Install IPECS app" in s:
        return s
    return s + """

MS.update({
    "Use IPECS like an app": "Guna IPECS seperti aplikasi",
    "Install it on your phone: it opens full-screen, with its own icon on the home screen.":
        "Pasang pada telefon anda: ia dibuka skrin penuh, dengan ikon sendiri di skrin utama.",
    "Install IPECS app": "Pasang aplikasi IPECS",
    "Installing...": "Sedang memasang...",
    "IPECS is installed": "IPECS telah dipasang",
    "Open it from your home screen.": "Buka dari skrin utama anda.",
    "In Safari, tap the Share button (the square with an arrow), then choose 'Add to Home Screen' and tap 'Add'.":
        "Dalam Safari, ketik butang Kongsi (petak dengan anak panah), kemudian pilih 'Tambah ke Skrin Utama' dan ketik 'Tambah'.",
    "Open the browser menu (the three dots) and choose 'Install app' or 'Add to Home screen'.":
        "Buka menu pelayar (tiga titik) dan pilih 'Pasang aplikasi' atau 'Tambah ke skrin Utama'.",
    "This link is not secure (http://), so the phone can only add a shortcut: open the browser menu (the three dots) and choose 'Add to Home screen'. For the full app, open the https:// link shown by start_phone.py --tunnel.":
        "Pautan ini tidak selamat (http://), jadi telefon hanya boleh menambah pintasan: buka menu pelayar (tiga titik) dan pilih 'Tambah ke skrin Utama'. Untuk aplikasi penuh, buka pautan https:// yang dipaparkan oleh start_phone.py --tunnel.",
    "Installation was cancelled. You can press the button again.":
        "Pemasangan dibatalkan. Anda boleh tekan butang sekali lagi.",
})
"""


edit("utils/i18n.py", f_i18n)
print("i18n.py ok")


# ============================================================ README.md
def f_readme(s):
    if "Use IPECS on your phone" in s:
        return s
    return s.rstrip("\n") + """

## Use IPECS on your phone (patch #13)
IPECS keeps running on your computer; the phone opens it in the browser and can install it as an app.
* **Same Wi-Fi:** `python start_phone.py` -> open the printed `http://192.168.x.x:8501` link on the phone.
  Phones only allow a *shortcut* from an `http://` link (browser menu -> Add to Home screen).
* **Install as an app (any network):** install the free [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
  (Windows: `winget install --id Cloudflare.cloudflared`, macOS: `brew install cloudflared`), then run
  `python start_phone.py --tunnel` and open the printed `https://....trycloudflare.com` link on the phone.
  Press **Install IPECS app** on the login page (iPhone: Share -> Add to Home Screen).
* Keep the computer on and `start_phone.py` running while you use the phone. A quick-tunnel link changes each
  time it starts; anyone with the link can reach the login page, so change `ADMIN_PASSWORD` in `.env` first.
"""


edit("README.md", f_readme)
print("README.md ok")
print("Done. Stop Streamlit, then start it with:  python start_phone.py --tunnel   (or without --tunnel for same Wi-Fi)")
