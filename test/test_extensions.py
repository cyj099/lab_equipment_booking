# -*- coding: utf-8 -*-
"""扩展功能单元测试：周期预约、多级审批、爽约信用分、自动释放、剩余数量、校区、账号。"""

from datetime import timedelta

from model.campus_model import CampusDAO
from model.credit_model import CreditLogDAO
from test.common import BaseTestCase
from utils.constants import (
    APPT_APPROVAL, APPT_WEEKLY, AUDIT_APPROVED, AUDIT_COMPLETED,
    CREDIT_NO_SHOW_PENALTY, ROLE_TEACHER, USER_DISABLED,
)


class TestExtensions(BaseTestCase):
    def test_available_count(self):
        start, end = self.future(), self.future() + timedelta(hours=2)
        # 种子设备 DEV-001 示波器 total_count = 5
        self.assertEqual(self.appt_ctrl.available_count(1, start, end), 5)

    def test_submit_weekly_creates_weeks(self):
        start, end = self.future(), self.future() + timedelta(hours=2)
        ok, msg = self.appt_ctrl.submit_weekly(self.student1["uid"], self.dev1["did"],
                                               start, end, weeks=4)
        self.assertTrue(ok, msg)
        rows = self.appt_ctrl.list_by_user(self.student1["uid"])
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(r["appointment_type"] == APPT_WEEKLY for r in rows))

    def test_submit_weekly_conflict(self):
        # 先把未来连续 4 周其中一周占满
        start, end = self.future(), self.future() + timedelta(hours=2)
        self.appt_ctrl.submit_appointment(self.student1["uid"], self.dev2["did"], start, end)
        self.appt_ctrl.submit_appointment(self.student2["uid"], self.dev2["did"], start, end)
        self.appt_ctrl.submit_appointment(self.student1["uid"], self.dev2["did"], start, end)
        self.appt_ctrl.submit_appointment(self.student2["uid"], self.dev2["did"], start, end)
        # dev2 total_count = 4，占满 4 台后周期预约应冲突
        ok, msg = self.appt_ctrl.submit_weekly(self.student1["uid"], self.dev2["did"],
                                               start, end, weeks=4)
        self.assertFalse(ok)
        self.assertIn("冲突", msg)

    def test_tutor_audit_flow(self):
        self.user_ctrl.register("teacher1", "abc12345", "王导师", "13800000005", ROLE_TEACHER)
        teacher = self.user_ctrl.dao.get_by_username("teacher1")
        start, end = self.future(), self.future() + timedelta(hours=2)
        self.appt_ctrl.submit_appointment(self.student1["uid"], self.dev1["did"], start, end,
                                          appointment_type=APPT_APPROVAL,
                                          tutor_uid=teacher["uid"])
        aid = self.appt_ctrl.list_by_user(self.student1["uid"])[0]["aid"]

        # 管理员不能跨级审核（需导师先通过）
        self.assertFalse(self.appt_ctrl.audit(aid, AUDIT_APPROVED, "", self.admin1)[0])
        # 导师通过 → 进入管理员审核
        self.assertTrue(self.appt_ctrl.tutor_audit(aid, True, "", teacher)[0])
        self.assertTrue(self.appt_ctrl.audit(aid, AUDIT_APPROVED, "", self.admin1)[0])

    def test_tutor_audit_reject(self):
        self.user_ctrl.register("teacher2", "abc12345", "李导师", "13800000006", ROLE_TEACHER)
        teacher = self.user_ctrl.dao.get_by_username("teacher2")
        start, end = self.future(), self.future() + timedelta(hours=2)
        self.appt_ctrl.submit_appointment(self.student1["uid"], self.dev1["did"], start, end,
                                          appointment_type=APPT_APPROVAL,
                                          tutor_uid=teacher["uid"])
        aid = self.appt_ctrl.list_by_user(self.student1["uid"])[0]["aid"]
        ok, _ = self.appt_ctrl.tutor_audit(aid, False, "不符合要求", teacher)
        self.assertTrue(ok)
        r = self.appt_ctrl.get_by_id(aid)
        self.assertEqual(r["audit_status"], 2)  # 已驳回

    def test_mark_no_show_deducts_credit(self):
        start, end = self.future(), self.future() + timedelta(hours=2)
        self.appt_ctrl.submit_appointment(self.student1["uid"], self.dev1["did"], start, end)
        aid = self.appt_ctrl.list_by_user(self.student1["uid"])[0]["aid"]
        self.appt_ctrl.audit(aid, AUDIT_APPROVED, "", self.admin1)

        ok, _ = self.appt_ctrl.mark_no_show(aid, self.admin1)
        self.assertTrue(ok)
        stu = self.user_ctrl.dao.get_by_id(self.student1["uid"])
        self.assertEqual(stu["credit_score"], 100 - CREDIT_NO_SHOW_PENALTY)
        self.assertEqual(stu["blacklist_count"], 1)
        logs = CreditLogDAO(self.db_path).list_by_user(self.student1["uid"])
        self.assertTrue(logs)
        self.assertEqual(logs[0]["change"], -CREDIT_NO_SHOW_PENALTY)

    def test_auto_release_expired(self):
        # 直接构造一条已过结束时间且已通过的预约
        aid = self.appt_ctrl.dao.insert(
            self.student1["uid"], self.dev1["did"],
            "2020-01-01 08:00:00", "2020-01-01 10:00:00",
            "instant", None, 2)
        self.appt_ctrl.dao.update_audit(aid, AUDIT_APPROVED, "")
        n = self.appt_ctrl.auto_release_expired()
        self.assertEqual(n, 1)
        self.assertEqual(self.appt_ctrl.get_by_id(aid)["audit_status"], AUDIT_COMPLETED)

    def test_campus_crud(self):
        dao = CampusDAO(self.db_path)
        cid = dao.create("测试校区")
        self.assertTrue(dao.get_by_name("测试校区"))
        dao.delete(cid)
        self.assertIsNone(dao.get_by_name("测试校区"))

    def test_user_password_and_status(self):
        self.assertTrue(self.user_ctrl.change_password(
            self.student1["uid"], "abc12345", "newpass123")[0])
        self.assertTrue(self.user_ctrl.reset_password(
            self.student1["uid"], "reset123")[0])
        self.assertTrue(self.user_ctrl.set_status(
            self.student1["uid"], USER_DISABLED)[0])
        stu = self.user_ctrl.dao.get_by_id(self.student1["uid"])
        self.assertEqual(stu["status"], USER_DISABLED)
