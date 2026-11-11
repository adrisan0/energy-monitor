"""Start a temporary Cloudflare Quick Tunnel for ONECTA OAuth callback."""
from __future__ import annotations

import re
import subprocess
import tempfile
import time
from pathlib import Path


LOG_DIR = Path(tempfile.gettempdir()) / "energy-home-daikin-tunnel"
LOG_DIR.mkdir(exist_ok=True)
FLAGS = (getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
         | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
         | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))


def main() -> int:
    tunnel_log = LOG_DIR / f"cloudflared-{int(time.time())}.log"
    with tunnel_log.open("ab") as output:
        tunnel = subprocess.Popen(
            ["cloudflared", "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:8765"],
            stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
            creationflags=FLAGS, close_fds=True,
        )
    (LOG_DIR / "pids.txt").write_text(f"tunnel={tunnel.pid}\n", encoding="ascii")

    url_pattern = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if tunnel.poll() is not None:
            print("cloudflared exited before creating a tunnel; inspect its log in the system temp directory.")
            return 1
        try:
            log = tunnel_log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            log = ""
        match = url_pattern.search(log)
        if match:
            print(f"TUNNEL_URL={match.group(0)}")
            print("Callback path: /oauth/daikin/callback")
            print("Register TUNNEL_URL + callback path in Daikin My Apps.")
            print("Then run scripts/oauth_callback.py; this script does not start a listener.")
            print(f"PIDS_FILE={LOG_DIR / 'pids.txt'}")
            return 0
        time.sleep(0.25)
    print("Timed out waiting for a Quick Tunnel URL; inspect its log in the system temp directory.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
