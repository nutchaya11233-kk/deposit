"""
รันบน production ด้วย waitress แทน Flask dev server

    py -3 serve.py

⚠️ frps ถามเว็บนี้ทุกครั้งที่ frpc login — เว็บล่ม = frpc ตัวใหม่ต่อไม่ได้
   (ตัวที่ต่ออยู่แล้วไม่หลุด)
"""
import sys

from waitress import serve

from server.bootstrap import prepare
from server.config import WEB_HOST, WEB_PORT
from server.logger import log


def main() -> int:
    if not prepare():
        return 1

    from server.app import create_app
    app = create_app()

    log("OK", f"waitress รับงานที่ http://{WEB_HOST}:{WEB_PORT}")
    serve(app, host=WEB_HOST, port=WEB_PORT, threads=6, ident="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
