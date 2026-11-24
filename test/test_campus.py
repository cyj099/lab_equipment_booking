# -*- coding: utf-8 -*-
"""多校区 / 多实验室分级管理单元测试。"""

from model.campus_model import CampusDAO
from model.lab_model import LabDAO
from test.common import BaseTestCase


class TestCampus(BaseTestCase):
    def test_seed_campuses(self):
        names = [c["campus_name"] for c in CampusDAO(self.db_path).list_all()]
        self.assertIn("本部校区", names)
        self.assertIn("南校区", names)

    def test_lab_campus_join(self):
        labs = LabDAO(self.db_path).list_all()
        self.assertTrue(all(lab.get("campus_name") for lab in labs))

    def test_device_campus_filter(self):
        devs = self.device_ctrl.list_devices(campus_id=1)
        self.assertTrue(devs)
        self.assertTrue(all(d.get("campus_name") == "本部校区" for d in devs))
