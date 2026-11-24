# -*- coding: utf-8 -*-
"""移动端 Flask API 集成测试（Flask test client + 临时数据库）。"""

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta

from server.app import create_app


def _db_str(dt):
    return dt.strftime("%Y-%m-%d %H:%M")


class TestMobileAPI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        self.app = create_app(self.db_path)
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _register_login(self):
        r = self.client.post("/api/register", json={
            "username": "mstu", "password": "123456",
            "real_name": "移动学生", "phone": "13900000000"})
        self.assertTrue(r.get_json()["ok"], r.get_json())
        r = self.client.post("/api/login", json={
            "username": "mstu", "password": "123456"})
        data = r.get_json()
        self.assertTrue(data["ok"], data)
        token = data["data"]["token"]
        self.h = {"Authorization": f"Bearer {token}"}
        return token

    def test_login_fail(self):
        r = self.client.post("/api/login", json={"username": "mstu", "password": "bad"})
        self.assertEqual(r.status_code, 401)

    def test_login_response_hides_password_hash(self):
        """登录响应不得回传 password_hash（Issue #7）。"""
        self._register_login()
        r = self.client.post("/api/login", json={"username": "mstu", "password": "123456"})
        user = r.get_json()["data"]["user"]
        self.assertNotIn("password_hash", user)
        self.assertEqual(user["username"], "mstu")

    def test_register_login_devices(self):
        self._register_login()
        r = self.client.get("/api/devices", headers=self.h)
        data = r.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["data"])

    def test_recommend(self):
        self._register_login()
        day = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        r = self.client.get(f"/api/recommend?did=1&day={day}&duration=2", headers=self.h)
        self.assertTrue(r.get_json()["ok"], r.get_json())

    def test_submit_list_cancel(self):
        self._register_login()
        start = datetime.now() + timedelta(days=5)
        start = start.replace(hour=9, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=2)
        r = self.client.post("/api/appointments", headers=self.h, json={
            "did": 1, "start": _db_str(start), "end": _db_str(end), "type": "instant"})
        self.assertTrue(r.get_json()["ok"], r.get_json())

        r = self.client.get("/api/appointments", headers=self.h)
        aids = r.get_json()["data"]
        self.assertTrue(aids)
        aid = aids[0]["aid"]

        r = self.client.post(f"/api/appointments/{aid}/cancel", headers=self.h)
        self.assertTrue(r.get_json()["ok"], r.get_json())

    def test_sign(self):
        self._register_login()
        start = datetime.now() + timedelta(days=5)
        start = start.replace(hour=9, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=2)
        self.client.post("/api/appointments", headers=self.h, json={
            "did": 1, "start": _db_str(start), "end": _db_str(end), "type": "instant"})
        r = self.client.get("/api/appointments", headers=self.h)
        aid = r.get_json()["data"][0]["aid"]
        # 未审核不能签到（学生提交默认 approve_stage=管理员，待审核状态）
        r = self.client.post("/api/sign", headers=self.h, json={"aid": aid, "method": "manual"})
        self.assertFalse(r.get_json()["ok"])


if __name__ == "__main__":
    unittest.main()
