# -*- coding: utf-8 -*-
"""设备表 DAO。"""

from db.base_model import BaseDAO


class DeviceDAO(BaseDAO):
    """设备数据访问对象。"""

    def create(self, dev_name: str, dev_no: str, category: str, lab_id: int,
               spec: str = "", status: int = 1, remark: str = "",
               total_count: int = 1, qr_code: str = "") -> int:
        return self.execute(
            "INSERT INTO device (dev_name, dev_no, category, lab_id, spec, status, "
            "remark, total_count, qr_code) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (dev_name, dev_no, category, lab_id, spec, status, remark, total_count, qr_code))

    def get_by_id(self, did: int) -> dict | None:
        return self.query_one(
            "SELECT d.*, l.lab_name, c.campus_name FROM device d "
            "LEFT JOIN lab l ON d.lab_id = l.lid "
            "LEFT JOIN campus c ON l.campus_id = c.cid WHERE d.did = ?", (did,))

    def get_by_no(self, dev_no: str) -> dict | None:
        return self.query_one("SELECT * FROM device WHERE dev_no = ?", (dev_no,))

    def list_all(self, category: str = "", keyword: str = "",
                 status: int | None = None, campus_id: int | None = None) -> list:
        """按分类、关键字、状态、校区筛选设备（联表带实验室名/校区名）。"""
        sql = ("SELECT d.*, l.lab_name, c.campus_name FROM device d "
               "LEFT JOIN lab l ON d.lab_id = l.lid "
               "LEFT JOIN campus c ON l.campus_id = c.cid WHERE 1=1")
        params: list = []
        if category:
            sql += " AND d.category = ?"
            params.append(category)
        if keyword:
            sql += " AND (d.dev_name LIKE ? OR d.dev_no LIKE ?)"
            params.append(f"%{keyword}%")
            params.append(f"%{keyword}%")
        if status is not None:
            sql += " AND d.status = ?"
            params.append(status)
        if campus_id is not None:
            sql += " AND l.campus_id = ?"
            params.append(campus_id)
        sql += " ORDER BY d.did"
        return self.query_all(sql, tuple(params))

    def update(self, did: int, **fields) -> None:
        """按字段更新设备（仅允许白名单字段）。"""
        allowed = {"dev_name", "dev_no", "category", "lab_id", "spec", "status",
                   "remark", "total_count", "qr_code"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        self.execute(f"UPDATE device SET {set_clause} WHERE did = ?",
                     (*updates.values(), did))

    def set_status(self, did: int, status: int) -> None:
        self.execute("UPDATE device SET status = ? WHERE did = ?", (status, did))
