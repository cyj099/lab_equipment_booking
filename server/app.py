# -*- coding: utf-8 -*-
"""移动端 Flask 后端：复用现有控制器，提供 H5 可用的 REST API。

运行：python server/app.py  （局域网手机访问 http://<本机IP>:5000）
"""

import os
import secrets
import sys
from functools import wraps

# 直接运行 python server/app.py 时，sys.path[0] 是 server/，需补上项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, render_template, request

from controller.appointment_controller import AppointmentController
from controller.device_controller import DeviceController
from controller.message_controller import MessageController
from controller.notice_controller import NoticeController
from controller.sign_controller import SignController
from controller.user_controller import UserController
from controller.waitlist_controller import WaitlistController
from db.init_db import init_db
from utils.ai_recommend import recommend_slots
from utils.time_util import parse_dt, to_db_str

_TOKENS: dict = {}  # token -> uid（单进程内存态，演示用）


def create_app(db_path: str | None = None) -> Flask:
    init_db(db_path)
    app = Flask(__name__)

    uc = UserController(db_path)
    dc = DeviceController(db_path)
    ac = AppointmentController(db_path)
    nc = NoticeController(db_path)
    mc = MessageController(db_path)
    sc = SignController(db_path)
    wc = WaitlistController(db_path)

    def current_user() -> dict | None:
        token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
        uid = _TOKENS.get(token)
        return uc.dao.get_by_id(uid) if uid else None

    def login_required(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if current_user() is None:
                return jsonify({"ok": False, "msg": "未登录或登录已过期"}), 401
            return f(*args, **kwargs)
        return wrapper

    def err(msg, code=400):
        return jsonify({"ok": False, "msg": msg}), code

    def ok(data=None, **extra):
        body = {"ok": True}
        if data is not None:
            body["data"] = data
        body.update(extra)
        return jsonify(body)

    # ---------- 页面 ----------
    @app.get("/")
    def index():
        return render_template("index.html")

    # ---------- 认证 ----------
    @app.post("/api/login")
    def login():
        body = request.get_json(silent=True) or {}
        user, msg = uc.login(body.get("username", ""), body.get("password", ""))
        if not user:
            return err(msg, 401)
        token = secrets.token_hex(16)
        _TOKENS[token] = user["uid"]
        # 仅回传客户端需要的字段，避免 password_hash 等敏感字段泄露（Issue #7）
        safe_user = {
            key: user[key]
            for key in ("uid", "username", "real_name", "role", "status", "phone",
                        "blacklist_count", "credit_score", "create_time")
            if key in user
        }
        return ok({"token": token, "user": safe_user})

    @app.post("/api/register")
    def register():
        body = request.get_json(silent=True) or {}
        okk, msg = uc.register(body.get("username", ""), body.get("password", ""),
                               body.get("real_name", ""), body.get("phone", ""))
        return ok({"msg": msg}) if okk else err(msg)

    @app.post("/api/logout")
    @login_required
    def logout():
        token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
        _TOKENS.pop(token, None)
        return ok()

    # ---------- 设备 ----------
    @app.get("/api/devices")
    @login_required
    def devices():
        return ok(dc.list_devices(keyword=request.args.get("kw", ""),
                                  campus_id=request.args.get("campus_id", type=int)))

    # ---------- AI 推荐 ----------
    @app.get("/api/recommend")
    @login_required
    def recommend():
        did = request.args.get("did", type=int)
        day_arg = request.args.get("day", "")
        duration = request.args.get("duration", 2, type=float)
        day = parse_dt(day_arg)
        if day is None and day_arg:
            from datetime import datetime as _dt
            try:
                day = _dt.strptime(day_arg, "%Y-%m-%d")
            except ValueError:
                day = None
        if not did or not day:
            return err("缺少 did 或 day")
        booked = [(parse_dt(s), parse_dt(e)) for s, e in ac.dao.get_valid_time_range_by_device(did)]
        booked = [(s, e) for s, e in booked if s and e]
        slots = recommend_slots(booked, day, duration)
        return ok([[to_db_str(s), to_db_str(e)] for s, e in slots])

    # ---------- 预约 ----------
    @app.get("/api/appointments")
    @login_required
    def my_appointments():
        return ok(ac.list_by_user(current_user()["uid"]))

    @app.post("/api/appointments")
    @login_required
    def submit():
        body = request.get_json(silent=True) or {}
        start, end = parse_dt(body.get("start", "")), parse_dt(body.get("end", ""))
        if not start or not end:
            return err("时间格式错误")
        okk, msg = ac.submit_appointment(
            current_user()["uid"], body.get("did"), start, end,
            appointment_type=body.get("type", "instant"),
            tutor_uid=body.get("tutor_uid"))
        return ok({"msg": msg}) if okk else err(msg)

    @app.post("/api/appointments/<int:aid>/cancel")
    @login_required
    def cancel(aid):
        okk, msg = ac.cancel(aid, current_user())
        return ok({"msg": msg}) if okk else err(msg)

    @app.get("/api/recommend_slots")
    @login_required
    def recommend_slots_alias():
        return recommend()

    # ---------- 候补 ----------
    @app.get("/api/waitlist")
    @login_required
    def waitlist():
        return ok(wc.list_by_user(current_user()["uid"]))

    @app.post("/api/waitlist")
    @login_required
    def join_waitlist():
        body = request.get_json(silent=True) or {}
        start, end = parse_dt(body.get("start", "")), parse_dt(body.get("end", ""))
        if not start or not end:
            return err("时间格式错误")
        okk, msg = wc.join(current_user()["uid"], body.get("did"), start, end)
        return ok({"msg": msg}) if okk else err(msg)

    # ---------- 签到 ----------
    @app.post("/api/sign")
    @login_required
    def sign():
        body = request.get_json(silent=True) or {}
        okk, msg = sc.sign_in(current_user()["uid"], body.get("aid"),
                              body.get("method", "manual"))
        return ok({"msg": msg}) if okk else err(msg)

    # ---------- 公告 / 消息 ----------
    @app.get("/api/notices")
    @login_required
    def notices():
        return ok(nc.list_notices())

    @app.get("/api/messages")
    @login_required
    def messages():
        return ok(mc.list_by_user(current_user()["uid"]))

    @app.post("/api/messages/read_all")
    @login_required
    def read_all():
        mc.mark_all_read(current_user()["uid"])
        return ok()

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
