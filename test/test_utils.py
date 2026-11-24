# -*- coding: utf-8 -*-
"""工具与实验室模块单元测试：备份恢复、CSV 导出、实验室 CRUD。"""

import os

from model.lab_model import LabDAO
from test.common import BaseTestCase
from utils.backup_util import backup_database, list_backups, restore_database
from utils.csv_export import export_to_csv


class TestBackup(BaseTestCase):
    def test_backup_and_restore(self):
        backup_dir = os.path.join(self.tmp, "backup")
        ok, path = backup_database(self.db_path, backup_dir)
        self.assertTrue(ok)
        self.assertIn("device_booking", os.path.basename(path))
        self.assertTrue(list_backups(backup_dir))
        ok, msg = restore_database(os.path.basename(path), self.db_path, backup_dir)
        self.assertTrue(ok, msg)

    def test_restore_missing(self):
        ok, _ = restore_database("nope.db", self.db_path, os.path.join(self.tmp, "b"))
        self.assertFalse(ok)


class TestCsvExport(BaseTestCase):
    def test_export(self):
        path = os.path.join(self.tmp, "out.csv")
        ok = export_to_csv([{"a": 1, "b": "x"}], ["a", "b"], ["A", "B"], path)
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(path))


class TestLab(BaseTestCase):
    def test_lab_crud(self):
        dao = LabDAO(self.db_path)
        lid = dao.create("新实验室", "N700")
        self.assertGreater(lid, 0)
        self.assertTrue(any(lab["lab_name"] == "新实验室" for lab in dao.list_all()))
        self.assertEqual(dao.get_by_id(lid)["location"], "N700")
