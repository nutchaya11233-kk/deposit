"""
Flask app — เสิร์ฟ API ที่ /api และหน้าเว็บ (ไฟล์ static ที่ build มาแล้ว) ที่ /

⚠️ เสิร์ฟทั้งสองอย่างจากโปรเซสเดียว ตั้งใจให้เป็นแบบนั้น — VPS มี RAM 512MB
   ถ้าแยก Node ออกไปเสิร์ฟหน้าเว็บอีกตัวจะกินอีก 150-250MB โดยไม่ได้อะไรกลับมา
   (หน้านี้อยู่หลัง login ไม่ต้องการ SEO ไม่ต้องการ SSR)
   ผลพลอยได้คือเป็น same-origin จึงไม่ต้องตั้ง CORS และ cookie ทำงานตรง ๆ
"""
from __future__ import annotations

import os
from datetime import timedelta

from flask import Flask, jsonify, send_from_directory

from server.api import bp as api_bp
from server.config import COOKIE_SECURE, SECRET_IS_EPHEMERAL, SECRET_KEY
from server.frp_plugin import bp as frp_plugin_bp
from server.logger import log

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config.update(
        SECRET_KEY=SECRET_KEY,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=COOKIE_SECURE,
        PERMANENT_SESSION_LIFETIME=timedelta(days=7),
        JSON_SORT_KEYS=False,
        MAX_CONTENT_LENGTH=1 * 1024 * 1024,
    )

    if SECRET_IS_EPHEMERAL:
        log("WARN", "ยังไม่ได้ตั้ง SECRET_KEY ใน .env — ทุกคนจะหลุด login ทุกครั้งที่รีสตาร์ต")

    app.register_blueprint(api_bp)
    app.register_blueprint(frp_plugin_bp)

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True})

    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def spa(path: str):
        """
        เสิร์ฟหน้าเว็บ — เส้นทางที่ไม่ใช่ไฟล์จริง ให้ตกไปที่ index.html

        ⚠️ จำเป็นเพราะหน้าเว็บเป็น SPA ที่จัดการ URL เอง ถ้าไม่ทำแบบนี้
           ผู้ใช้ที่กด refresh อยู่หน้า /accounts จะเจอ 404
        """
        if not os.path.isdir(STATIC_DIR):
            return (
                "<h1>ยังไม่ได้ build หน้าเว็บ</h1>"
                "<p>รัน <code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code> ก่อน</p>",
                503,
            )
        if path and os.path.isfile(os.path.join(STATIC_DIR, path)):
            return send_from_directory(STATIC_DIR, path)
        return send_from_directory(STATIC_DIR, "index.html")

    return app
