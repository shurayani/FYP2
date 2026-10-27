"""Start IPECS so you can open it on your PHONE (patch #13).

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
