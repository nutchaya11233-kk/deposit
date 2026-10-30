"""Console logger แบบมีสี — ใช้ร่วมกันทั้งระบบ"""
from datetime import datetime

_RESET = "\033[0m"
_LEVELS = {
    "INFO":    ("\033[96m", "·"),
    "OK":      ("\033[92m", "✓"),
    "WARN":    ("\033[93m", "!"),
    "ERROR":   ("\033[91m", "✗"),
}


def log(level: str, message: str) -> None:
    color, mark = _LEVELS.get(level, (_RESET, " "))
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{color}{ts} {mark} {message}{_RESET}", flush=True)
