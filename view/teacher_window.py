# -*- coding: utf-8 -*-
"""导师（教师）主窗口：审批型 / 周期型预约的一级审核（导师 → 管理员二级审批）。"""

from PyQt6.QtWidgets import (
    QHBoxLayout, QInputDialog, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from controller.appointment_controller import AppointmentController
from utils.constants import STAGE_TUTOR
from view.base_window import BaseMainWindow
from view.widgets import fill_table, info, make_table, warn


class TeacherWindow(BaseMainWindow):
    """教师/导师端主窗口。"""

    def __init__(self, user: dict) -> None:
        super().__init__(user)
        self.setWindowTitle("实验室设备预约系统 - 导师端")
        self.resize(1000, 640)

        self.appt_ctrl = AppointmentController()

        self.add_page("待我审核", self._page_audit())

    def _page_audit(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        hint = QLabel("审批型 / 周期型预约需导师先通过，再由实验室管理员审核。")
        hint.setStyleSheet("color:gray;")
        v.addWidget(hint)

        self.audit_table = make_table(["单号", "设备", "申请人", "开始", "结束", "类型"])
        v.addWidget(self.audit_table)

        btns = QHBoxLayout()
        approve_btn = QPushButton("通过（转管理员审核）")
        approve_btn.clicked.connect(lambda: self._audit(True))
        reject_btn = QPushButton("驳回")
        reject_btn.clicked.connect(lambda: self._audit(False))
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh)
        for b in (approve_btn, reject_btn, refresh_btn):
            btns.addWidget(b)
        btns.addStretch(1)
        v.addLayout(btns)
        self._refresh()
        return w

    def _refresh(self) -> None:
        rows = self.appt_ctrl.list_by_stage(STAGE_TUTOR)
        for r in rows:
            from utils.constants import APPT_TYPE_NAMES
            r["type_name"] = APPT_TYPE_NAMES.get(r.get("appointment_type"), "")
        fill_table(self.audit_table, rows,
                   ["aid", "dev_name", "real_name", "start_time", "end_time", "type_name"])

    def _selected_aid(self) -> int | None:
        row = self.audit_table.currentRow()
        if row < 0:
            warn("请先选择一条预约")
            return None
        return int(self.audit_table.item(row, 0).text())

    def _audit(self, approved: bool) -> None:
        aid = self._selected_aid()
        if not aid:
            return
        reason = ""
        if not approved:
            reason, ok = QInputDialog.getText(self, "驳回原因", "请输入驳回原因：")
            if not ok:
                return
        ok, msg = self.appt_ctrl.tutor_audit(aid, approved, reason, self.user)
        info(msg) if ok else warn(msg)
        self._refresh()
