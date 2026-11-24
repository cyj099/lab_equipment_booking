# -*- coding: utf-8 -*-
"""预约核心模块单元测试：覆盖正常 / 边界 / 异常场景（对应测试设计 UT-01~UT-10）。"""

from datetime import timedelta

from test.common import BaseTestCase
from utils.constants import (DEVICE_REPAIR, USER_DISABLED)


class TestSubmitAppointment(BaseTestCase):
    """UT-01~UT-07：提交预约的校验场景。"""

    def test_submit_success(self):  # UT-01 正常无冲突
        start = self.future()
        ok, msg = self.appt_ctrl.submit_appointment(
            self.student1["uid"], self.dev1["did"], start, start + timedelta(hours=2))
        self.assertTrue(ok, msg)

    def test_submit_past_time(self):  # UT-02 过去时间
        from datetime import datetime, timedelta as td
        ok, _ = self.appt_ctrl.submit_appointment(
            self.student1["uid"], self.dev1["did"],
            datetime.now() - td(hours=1), datetime.now() + td(hours=1))
        self.assertFalse(ok)

    def test_submit_over_max_hours(self):  # UT-03 超过最大时长
        start = self.future()
        ok, _ = self.appt_ctrl.submit_appointment(
            self.student1["uid"], self.dev1["did"], start, start + timedelta(hours=8))
        self.assertFalse(ok)

    def test_submit_time_conflict(self):  # UT-04 时段冲突（单台设备）
        # 将示波器总量设为 1，重叠时段即冲突
        self.device_ctrl.dao.execute("UPDATE device SET total_count = 1 WHERE did = ?",
                                     (self.dev1["did"],))
        start = self.future()
        self.appt_ctrl.submit_appointment(self.student1["uid"], self.dev1["did"],
                                          start, start + timedelta(hours=2))
        ok, _ = self.appt_ctrl.submit_appointment(self.student2["uid"], self.dev1["did"],
                                                  start + timedelta(hours=1),
                                                  start + timedelta(hours=3))
        self.assertFalse(ok)

    def test_submit_multi_count_allows_concurrent(self):  # 多数量并发
        # 示波器总量 5，允许 5 台同时段预约，第 6 台冲突
        start = self.future()
        for i in range(5):
            u = self.user_ctrl.dao.get_by_username(f"student{i % 2 + 1}")
            ok, _ = self.appt_ctrl.submit_appointment(u["uid"], self.dev1["did"],
                                                      start, start + timedelta(hours=2))
            self.assertTrue(ok)
        ok, _ = self.appt_ctrl.submit_appointment(self.student1["uid"], self.dev1["did"],
                                                  start, start + timedelta(hours=2))
        self.assertFalse(ok)

    def test_submit_blacklist_user(self):  # UT-05 黑名单用户
        self.user_ctrl.set_status(self.student1["uid"], USER_DISABLED)
        start = self.future()
        ok, _ = self.appt_ctrl.submit_appointment(
            self.student1["uid"], self.dev1["did"], start, start + timedelta(hours=2))
        self.assertFalse(ok)

    def test_submit_device_repair(self):  # UT-06 设备维修
        self.device_ctrl.set_status(self.dev1["did"], DEVICE_REPAIR)
        start = self.future()
        ok, _ = self.appt_ctrl.submit_appointment(
            self.student1["uid"], self.dev1["did"], start, start + timedelta(hours=2))
        self.assertFalse(ok)

    def test_submit_end_before_start(self):  # UT-07 结束早于开始
        start = self.future()
        ok, _ = self.appt_ctrl.submit_appointment(
            self.student1["uid"], self.dev1["did"], start + timedelta(hours=2), start)
        self.assertFalse(ok)


class TestAppointmentAudit(BaseTestCase):
    def test_audit_approve(self):
        start = self.future()
        ok, _ = self.appt_ctrl.submit_appointment(
            self.student1["uid"], self.dev1["did"], start, start + timedelta(hours=2))
        self.assertTrue(ok)
        aid = self.appt_ctrl.list_by_user(self.student1["uid"])[0]["aid"]
        ok, _ = self.appt_ctrl.audit(aid, 1, "", self.admin1)
        self.assertTrue(ok)
        self.assertEqual(self.appt_ctrl.get_by_id(aid)["audit_status"], 1)

    def test_audit_reject_requires_reason(self):
        start = self.future()
        self.appt_ctrl.submit_appointment(self.student1["uid"], self.dev1["did"],
                                          start, start + timedelta(hours=2))
        aid = self.appt_ctrl.list_by_user(self.student1["uid"])[0]["aid"]
        ok, _ = self.appt_ctrl.audit(aid, 2, "", self.admin1)
        self.assertFalse(ok)


class TestNoShowBlacklist(BaseTestCase):
    def test_no_show_threshold_blacklist(self):  # UT-10
        for i in range(3):
            start = self.future(days=10 + i)
            aid = self.submit_and_approve(self.student1["uid"], self.dev1["did"],
                                          start, start + timedelta(hours=2))
            ok, tip = self.appt_ctrl.mark_no_show(aid, self.admin1)
            self.assertTrue(ok, tip)
        user = self.user_ctrl.dao.get_by_id(self.student1["uid"])
        self.assertEqual(user["status"], USER_DISABLED)
        self.assertEqual(user["blacklist_count"], 3)
