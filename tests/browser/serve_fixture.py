"""Start the synthetic fixture with a trusted loopback host-theme origin."""
import sys
from pathlib import Path

from streamlit.web import bootstrap
from streamlit.web.server import routes

port = int(sys.argv[1]) if len(sys.argv) > 1 else 8591
# Cloud origins are built in. Loopback is trusted only by this QA launcher,
# before host-config is served; application code never modifies the allowlist.
routes._DEFAULT_ALLOWED_MESSAGE_ORIGINS.extend([
    f"http://localhost:{port}", f"http://127.0.0.1:{port}",
])
options = {
    "server.port": port, "server.headless": True, "browser.gatherUsageStats": False,
}
bootstrap.load_config_options(flag_options=options)
bootstrap.run(str(Path(__file__).with_name("fixture_app.py")), False, [], options)
