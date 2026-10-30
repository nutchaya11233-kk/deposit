"""
จุดเริ่มของระบบตอน dev

    py -3 run.py

production ใช้ serve.py แทน
"""
import sys

from server.bootstrap import prepare
from server.config import WEB_HOST, WEB_PORT
from server.logger import log


def main() -> int:
    if not prepare():
        return 1

    from server.app import create_app
    app = create_app()

    log("OK", f"เปิดหน้าเว็บที่ http://{WEB_HOST}:{WEB_PORT}")
    app.run(host=WEB_HOST, port=WEB_PORT, debug=False, use_reloader=False, threaded=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("INFO", "ปิดระบบแล้ว")
        sys.exit(0)
