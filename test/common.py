# -*- coding: utf-8 -*-
"""测试公共夹具：临时数据库 + 各控制器 + 预置用户/设备。"""

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta

from controller.appointment_controller import AppointmentController
from controller.device_controller import DeviceController
from controller.message_controller import MessageController
from controller.notice_controller import NoticeController
from controller.repair_controller import RepairController
from controller.user_controller import UserController
from controller.waitlist_controller import WaitlistController
from db.init_db import init_db
from utils.constants import ROLE_LAB_ADMIN, ROLE_STUDENT


class BaseTestCase(unittest.TestCase):
    """每个用例使用独立临时数据库，互不影响。"""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        init_db(self.db_path)

        self.user_ctrl = UserController(self.db_path)
        self.device_ctrl = DeviceController(self.db_path)
        self.appt_ctrl = AppointmentController(self.db_path)
        self.repair_ctrl = RepairController(self.db_path)
        self.notice_ctrl = NoticeController(self.db_path)
        self.waitlist_ctrl = WaitlistController(self.db_path)
        self.msg_ctrl = MessageController(self.db_path)

        # 预置用户（超级管理员 admin 由 init_db 自动创建）
        self.user_ctrl.register("student1", "abc12345", "张三", "13800000001", ROLE_STUDENT)
        self.user_ctrl.register("student2", "abc12345", "李四", "13800000002", ROLE_STUDENT)
        self.user_ctrl.register("admin1", "admin123", "王实验员", "13800000003", ROLE_LAB_ADMIN)
        self.student1 = self.user_ctrl.dao.get_by_username("student1")
        self.student2 = self.user_ctrl.dao.get_by_username("student2")
        self.admin1 = self.user_ctrl.dao.get_by_username("admin1")

        # 预置设备由 init_db 种子数据提供（did=1 示波器、did=2 信号发生器）
        self.dev1 = self.device_ctrl.get_device(1)
        self.dev2 = self.device_ctrl.get_device(2)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def future(days: int = 10, hour: int = 8) -> datetime:
        """返回未来某天整点时间。"""
        base = datetime.now() + timedelta(days=days)
        return base.replace(hour=hour, minute=0, second=0, microsecond=0)

    def submit_and_approve(self, uid: int, did: int, start: datetime,
                           end: datetime) -> int:
        """提交并审核通过，返回 aid。"""
        ok, _ = self.appt_ctrl.submit_appointment(uid, did, start, end)
        self.assertTrue(ok)
        aid = self.appt_ctrl.dao.query_one(
            "SELECT aid FROM appointment WHERE uid=? AND did=? "
            "AND start_time=? AND end_time=?",
            (uid, did,
             start.strftime("%Y-%m-%d %H:%M:%S"),
             end.strftime("%Y-%m-%d %H:%M:%S")))["aid"]
        self.appt_ctrl.audit(aid, 1, "", self.admin1)
        return aid
