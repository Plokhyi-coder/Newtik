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

# Whisper defaults (used from stage 3 onward, kept here so config stays in one place)
WHISPER_MODEL = "large-v3"
WHISPER_DEVICE = "auto"          # "auto" | "cuda" | "cpu"
WHISPER_COMPUTE_TYPE_CUDA = "float16"
WHISPER_COMPUTE_TYPE_CPU = "int8"

# Transfer-to-phone defaults
TRANSFER_PORT = 8765
TRANSFER_SESSION_TIMEOUT_SEC = 30 * 60

HOST = "127.0.0.1"
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
