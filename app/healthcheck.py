import urllib.request, sys, os
try:
    port = os.environ.get("APP_PORT", "3000")
    urllib.request.urlopen("http://localhost:" + port + "/healthz", timeout=4)
    sys.exit(0)
except Exception:
    sys.exit(1)
