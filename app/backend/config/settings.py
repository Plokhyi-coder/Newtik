"""Central paths and defaults for the whole backend."""
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
STORAGE_DIR = APP_DIR / "storage"
DOWNLOADS_DIR = STORAGE_DIR / "downloads"
JOBS_DIR = STORAGE_DIR / "jobs"
LOGS_DIR = STORAGE_DIR / "logs"
CONFIG_DIR = APP_DIR / "backend" / "config"

for _d in (DOWNLOADS_DIR, JOBS_DIR, LOGS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

KEYWORDS_PATH = CONFIG_DIR / "keywords.json"
STYLE_PRESETS_PATH = CONFIG_DIR / "style_presets.json"

# Clip cutting defaults
DEFAULT_CLIP_LENGTH_SEC = 30
MIN_CLIP_LENGTH_SEC = 15
MAX_CLIP_LENGTH_SEC = 90
MIN_LAST_SEGMENT_SEC = 5  # segments shorter than this at the tail are dropped

# Whisper defaults (used from stage 3 onward, kept here so config stays in one place).
# "medium" (~1.5 GB) is the default: it downloads and loads much faster than
# large-v3 (~3 GB) with only a modest accuracy drop, and the first subtitle
# run otherwise silently blocks a job on that download with zero feedback -
# on a slow connection that can look exactly like the app hanging. Set this
# to "large-v3" for maximum accuracy if you have a fast connection and don't
# mind a longer one-time download.
WHISPER_MODEL = "medium"
WHISPER_DEVICE = "auto"          # "auto" | "cuda" | "cpu"
WHISPER_COMPUTE_TYPE_CUDA = "float16"
WHISPER_COMPUTE_TYPE_CPU = "int8"

# Transfer-to-phone defaults
TRANSFER_PORT = 8765
TRANSFER_SESSION_TIMEOUT_SEC = 30 * 60

HOST = "127.0.0.1"  # what the desktop window itself connects to (loopback)
BIND_HOST = "0.0.0.0"  # what uvicorn actually listens on, so phones on the same Wi-Fi can reach it
API_PORT = 8000

# Text overlay defaults
_FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf",           # Windows - priority platform
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux dev fallback
    "/System/Library/Fonts/Supplemental/Arial.ttf",          # macOS fallback
]


def find_default_font() -> str | None:
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


DEFAULT_FONT_PATH = find_default_font()
OVERLAY_FONT_SIZE = 48
