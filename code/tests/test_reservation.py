# -*- coding: utf-8 -*-
"""预约 / 审核 / 使用登记 模块单元测试（覆盖正常与异常场景）。"""

import os
import sys
import unittest

# 支持两种运行方式：`python -m unittest discover -s tests -t .` 与 IDE 直接运行本文件
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab_reservation import (
    EquipmentStatus, ReservationStatus, Role,
)
from lab_reservation.exceptions import (
    ConflictError, NotFoundError, PermissionError, StateError, ValidationError,
)
from lab_reservation.services import slots_overlap

try:
    from .common import D, make_services
except ImportError:  # 直接运行本文件时无包上下文
    from common import D, make_services


class TestSlotsOverlap(unittest.TestCase):
    """时段重叠判定。"""

    def test_same_slot_overlap(self):
        self.assertTrue(slots_overlap("08:00-10:00", "08:00-10:00"))

    def test_partial_overlap(self):
        self.assertTrue(slots_overlap("08:00-10:00", "09:00-11:00"))

    def test_contained_overlap(self):
        self.assertTrue(slots_overlap("08:00-12:00", "09:00-10:00"))

    def test_adjacent_no_overlap(self):
        # 首尾相接（10:00 相接）不算冲突
        self.assertFalse(slots_overlap("08:00-10:00", "10:00-12:00"))

    def test_disjoint_no_overlap(self):
        self.assertFalse(slots_overlap("08:00-10:00", "14:00-16:00"))


class TestSubmitReservation(unittest.TestCase):
    """预约提交。"""

    def setUp(self):
        self.svc = make_services()

    def test_submit_success(self):
        _, _, _, rsvc, stu, _ = self.svc
        r = rsvc.submit(stu, "E01", D, "08:00-10:00", "实验")
        self.assertEqual(r.status, ReservationStatus.PENDING)

    def test_submit_equipment_not_found(self):
        _, _, _, rsvc, stu, _ = self.svc
        with self.assertRaises(NotFoundError):
            rsvc.submit(stu, "E99", D, "08:00-10:00", "实验")

    def test_submit_unavailable_equipment(self):
        _, _, esvc, rsvc, stu, _ = self.svc
        esvc.change_status("E01", EquipmentStatus.REPAIR)
        with self.assertRaises(ValidationError):
            rsvc.submit(stu, "E01", D, "08:00-10:00", "实验")

    def test_submit_empty_purpose(self):
        _, _, _, rsvc, stu, _ = self.svc
        with self.assertRaises(ValidationError):
            rsvc.submit(stu, "E01", D, "08:00-10:00", "  ")

    def test_submit_equipment_slot_conflict(self):
        _, _, _, rsvc, stu, _ = self.svc
        rsvc.submit(stu, "E01", D, "08:00-10:00", "实验")
        with self.assertRaises(ConflictError):
            rsvc.submit(stu, "E01", D, "09:00-11:00", "复测")

    def test_submit_user_slot_conflict_different_equipment(self):
        _, _, _, rsvc, stu, _ = self.svc
        rsvc.submit(stu, "E01", D, "08:00-10:00", "实验")
        with self.assertRaises(ConflictError):
            rsvc.submit(stu, "E02", D, "08:30-10:00", "另一台")

    def test_submit_disabled_user(self):
        _, usvc, _, rsvc, stu, _ = self.svc
        stu.status = "禁用"
        with self.assertRaises(PermissionError):
            rsvc.submit(stu, "E01", D, "08:00-10:00", "实验")


class TestAudit(unittest.TestCase):
    """预约审核。"""

    def setUp(self):
        self.svc = make_services()

    def test_approve_success(self):
        _, _, _, rsvc, stu, adm = self.svc
        r = rsvc.submit(stu, "E01", D, "08:00-10:00", "实验")
        rsvc.approve(r.reserve_id, adm)
        self.assertEqual(r.status, ReservationStatus.APPROVED)

    def test_approve_wrong_state(self):
        _, _, _, rsvc, stu, adm = self.svc
        r = rsvc.submit(stu, "E01", D, "08:00-10:00", "实验")
        rsvc.reject(r.reserve_id, adm, "时间不合适")
        with self.assertRaises(StateError):
            rsvc.approve(r.reserve_id, adm)

    def test_reject_requires_reason(self):
        _, _, _, rsvc, stu, adm = self.svc
        r = rsvc.submit(stu, "E01", D, "08:00-10:00", "实验")
        with self.assertRaises(ValidationError):
            rsvc.reject(r.reserve_id, adm, "  ")

    def test_reject_success(self):
        _, _, _, rsvc, stu, adm = self.svc
        r = rsvc.submit(stu, "E01", D, "08:00-10:00", "实验")
        rsvc.reject(r.reserve_id, adm, "设备检修")
        self.assertEqual(r.status, ReservationStatus.REJECTED)


class TestCancel(unittest.TestCase):
    """预约取消。"""

    def setUp(self):
        self.svc = make_services()

    def test_cancel_by_owner(self):
        _, _, _, rsvc, stu, _ = self.svc
        r = rsvc.submit(stu, "E01", D, "08:00-10:00", "实验")
        rsvc.cancel(r.reserve_id, stu)
        self.assertEqual(r.status, ReservationStatus.CANCELLED)

    def test_cancel_by_admin(self):
        _, usvc, _, rsvc, stu, adm = self.svc
        other = usvc.register("李四", "2022002", Role.STUDENT, "abc12345")
        r = rsvc.submit(other, "E01", D, "08:00-10:00", "实验")
        rsvc.cancel(r.reserve_id, adm)
        self.assertEqual(r.status, ReservationStatus.CANCELLED)

    def test_cancel_by_other_user_forbidden(self):
        _, usvc, _, rsvc, stu, _ = self.svc
        other = usvc.register("李四", "2022002", Role.STUDENT, "abc12345")
        r = rsvc.submit(stu, "E01", D, "08:00-10:00", "实验")
        with self.assertRaises(PermissionError):
            rsvc.cancel(r.reserve_id, other)

    def test_cancel_completed_forbidden(self):
        _, _, _, rsvc, stu, adm = self.svc
        r = rsvc.submit(stu, "E01", D, "08:00-10:00", "实验")
        rsvc.approve(r.reserve_id, adm)
        rsvc.sign_in(r.reserve_id, stu)
        rsvc.sign_out(r.reserve_id, stu)
        with self.assertRaises(StateError):
            rsvc.cancel(r.reserve_id, stu)


class TestUsageRegistration(unittest.TestCase):
    """使用登记（签到 / 签退）。"""

    def setUp(self):
        self.svc = make_services()

    def _approved(self):
        _, _, _, rsvc, stu, adm = self.svc
        r = rsvc.submit(stu, "E01", D, "08:00-10:00", "实验")
        rsvc.approve(r.reserve_id, adm)
        return r, stu

    def test_sign_in_success(self):
        _, _, esvc, _, _, _ = self.svc
        r, stu = self._approved()
        rec = self.svc[3].sign_in(r.reserve_id, stu)
        self.assertIsNotNone(rec.sign_in_time)
        self.assertEqual(esvc.find_equipment("E01").status, EquipmentStatus.IN_USE)

    def test_sign_in_before_approve(self):
        _, _, _, rsvc, stu, _ = self.svc
        r = rsvc.submit(stu, "E01", D, "08:00-10:00", "实验")
        with self.assertRaises(StateError):
            rsvc.sign_in(r.reserve_id, stu)

    def test_sign_in_duplicate(self):
        _, _, _, rsvc, _, _ = self.svc
        r, stu = self._approved()
        rsvc.sign_in(r.reserve_id, stu)
        with self.assertRaises(StateError):
            rsvc.sign_in(r.reserve_id, stu)

    def test_sign_out_success(self):
        _, _, esvc, rsvc, _, _ = self.svc
        r, stu = self._approved()
        rsvc.sign_in(r.reserve_id, stu)
        rec = rsvc.sign_out(r.reserve_id, stu)
        self.assertIsNotNone(rec.sign_out_time)
        self.assertEqual(r.status, ReservationStatus.COMPLETED)
        self.assertEqual(esvc.find_equipment("E01").status, EquipmentStatus.AVAILABLE)

    def test_sign_out_without_sign_in(self):
        _, _, _, rsvc, _, _ = self.svc
        r, stu = self._approved()
        with self.assertRaises(StateError):
            rsvc.sign_out(r.reserve_id, stu)


if __name__ == "__main__":
    unittest.main()
