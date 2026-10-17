"""Original scenario interface, available only inside the mandatory safe worker."""
from pathlib import Path
import sys
PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE))
from safety.runtime import require_active
from safety.config import HEADERS, normalized
_job = require_active()
REPOSITORY = Path(_job['repo'])
ROOT = Path(_job['output'])
HTML = normalized((REPOSITORY/'index.html').read_bytes()).decode('utf-8')
TEST_HEADERS = HEADERS


async def launch_browser(p):
    require_active()
    return await p.chromium.launch(headless=True, chromium_sandbox=True)
