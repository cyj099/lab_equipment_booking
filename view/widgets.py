# -*- coding: utf-8 -*-
"""通用视图组件：表格工具函数与各类业务弹窗。"""

from PyQt6.QtCore import QDateTime, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QComboBox, QDateTimeEdit, QDialog, QDialogButtonBox, QFormLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QMessageBox,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget,
)

from utils.ai_recommend import recommend_slots
from utils.constants import (
    APPT_APPROVAL, APPT_INSTANT, APPT_WEEKLY, APPT_TYPE_NAMES,
    AUDIT_STATUS_NAMES, DEVICE_STATUS_NAMES, REPAIR_STATUS_NAMES,
    WAIT_STATUS_NAMES,
)
from utils.time_util import parse_dt


def make_table(headers: list) -> QTableWidget:
    """构造一个只读、整行选择、自动拉伸列宽的空表格。"""
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    t.verticalHeader().setVisible(False)
    return t


def fill_table(table: QTableWidget, rows: list, cols: list) -> None:
    """按 cols 字段顺序填充 rows（dict 列表）。"""
    table.setRowCount(len(rows))
    for i, row in enumerate(rows):
        for j, col in enumerate(cols):
            val = row.get(col, "")
            table.setItem(i, j, QTableWidgetItem("" if val is None else str(val)))


def device_view(rows: list) -> list:
    """设备行状态码转中文。"""
    for r in rows:
        r["status_name"] = DEVICE_STATUS_NAMES.get(r.get("status"), "")
    return rows


def appointment_view(rows: list) -> list:
    """预约行审核状态码转中文。"""
    for r in rows:
        r["status_name"] = AUDIT_STATUS_NAMES.get(r.get("audit_status"), "")
    return rows


def repair_view(rows: list) -> list:
    """报修行状态码转中文。"""
    for r in rows:
        r["status_name"] = REPAIR_STATUS_NAMES.get(r.get("status"), "")
    return rows


def waitlist_view(rows: list) -> list:
    """候补行状态码转中文。"""
    for r in rows:
        r["status_name"] = WAIT_STATUS_NAMES.get(r.get("status"), "")
    return rows


def info(msg: str, title: str = "提示") -> None:
    QMessageBox.information(None, title, msg)


def warn(msg: str, title: str = "提示") -> None:
    QMessageBox.warning(None, title, msg)


def confirm(msg: str, title: str = "确认") -> bool:
    return QMessageBox.question(None, title, msg) == QMessageBox.StandardButton.Yes


class RecommendDialog(QDialog):
    """AI 智能推荐空闲时段选择弹窗：列出候选时段，点选回填。"""

    def __init__(self, slots: list, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("AI 智能推荐空闲时段")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("以下为推荐的空闲时段（越靠前越优先）："))
        self.slots = slots
        self.slot_list = QListWidget()
        for s, e in slots:
            self.slot_list.addItem(f"{s:%Y-%m-%d %H:%M}  ~  {e:%H:%M}")
        layout.addWidget(self.slot_list)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def chosen(self):
        row = self.slot_list.currentRow()
        if 0 <= row < len(self.slots):
            return self.slots[row]
        return None


class AppointDialog(QDialog):
    """预约 / 候补 弹窗：选设备 + 起止时间 + 预约类型 + 导师 + 剩余数量 + AI 推荐。"""

    def __init__(self, devices: list, parent: QWidget | None = None,
                 tutors: list | None = None, appt_ctrl=None):
        super().__init__(parent)
        self.setWindowTitle("提交预约")
        self.setMinimumWidth(420)
        self.appt_ctrl = appt_ctrl
        self.tutors = tutors or []
        layout = QFormLayout(self)

        self.device_combo = QComboBox()
        for d in devices:
            total = d.get("total_count", 1) or 1
            self.device_combo.addItem(f"{d['dev_name']}（{d['dev_no']} · 共 {total} 台）", d["did"])
        layout.addRow("设备：", self.device_combo)

        self.start_edit = QDateTimeEdit(QDateTime.currentDateTime())
        self.end_edit = QDateTimeEdit(QDateTime.currentDateTime().addSecs(7200))
        for e in (self.start_edit, self.end_edit):
            e.setDisplayFormat("yyyy-MM-dd HH:mm")
            e.setCalendarPopup(True)
        layout.addRow("开始时间：", self.start_edit)
        layout.addRow("结束时间：", self.end_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItem(APPT_TYPE_NAMES[APPT_INSTANT], APPT_INSTANT)
        self.type_combo.addItem(APPT_TYPE_NAMES[APPT_APPROVAL], APPT_APPROVAL)
        self.type_combo.addItem(APPT_TYPE_NAMES[APPT_WEEKLY], APPT_WEEKLY)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        layout.addRow("预约类型：", self.type_combo)

        self.tutor_combo = QComboBox()
        self._fill_tutors()
        layout.addRow("导师：", self.tutor_combo)

        self.weeks_spin = QSpinBox()
        self.weeks_spin.setRange(1, 12)
        self.weeks_spin.setValue(4)
        layout.addRow("周期周数：", self.weeks_spin)

        self.purpose = QLineEdit()
        self.purpose.setPlaceholderText("预约用途（如：课程实验）")
        layout.addRow("用途：", self.purpose)

        self.available_label = QLabel("剩余可约：—")
        self.available_label.setStyleSheet("color:#07C160;font-weight:bold;")
        layout.addRow("", self.available_label)

        ai_btn = QPushButton("AI 智能推荐空闲时段")
        ai_btn.setObjectName("ghost")
        ai_btn.clicked.connect(self._ai_recommend)
        layout.addRow(ai_btn)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

        self.device_combo.currentIndexChanged.connect(self._update_available)
        self.start_edit.dateTimeChanged.connect(self._update_available)
        self.end_edit.dateTimeChanged.connect(self._update_available)
        self._on_type_changed()
        self._update_available()

    def _fill_tutors(self) -> None:
        self.tutor_combo.clear()
        if self.tutors:
            for t in self.tutors:
                self.tutor_combo.addItem(f"{t['real_name']}（{t['username']}）", t["uid"])
        else:
            self.tutor_combo.addItem("无导师（直接管理员审核）", None)

    def _on_type_changed(self) -> None:
        needs_tutor = self.type_combo.currentData() in (APPT_APPROVAL, APPT_WEEKLY)
        self.tutor_combo.setEnabled(needs_tutor and bool(self.tutors))
        self.weeks_spin.setEnabled(self.type_combo.currentData() == APPT_WEEKLY)

    def _slot(self):
        return (self.start_edit.dateTime().toPyDateTime(),
                self.end_edit.dateTime().toPyDateTime())

    def _update_available(self) -> None:
        if not self.appt_ctrl:
            return
        did = self.device_combo.currentData()
        start, end = self._slot()
        if start < end:
            n = self.appt_ctrl.available_count(did, start, end)
            self.available_label.setText(f"剩余可约：{n} 台")
        else:
            self.available_label.setText("剩余可约：—")

    def _ai_recommend(self) -> None:
        if not self.appt_ctrl:
            warn("当前环境暂不支持智能推荐")
            return
        did = self.device_combo.currentData()
        duration_h = self.end_edit.dateTime().toSecsSinceEpoch() \
            - self.start_edit.dateTime().toSecsSinceEpoch()
        duration_h = max(1.0, duration_h / 3600)
        day = self.start_edit.dateTime().toPyDateTime()
        booked = [(parse_dt(s), parse_dt(e))
                  for s, e in self.appt_ctrl.dao.get_valid_time_range_by_device(did)]
        booked = [(s, e) for s, e in booked if s and e]
        slots = recommend_slots(booked, day, duration_h)
        if not slots:
            warn("当日无满足时长的空闲时段，请更换日期或缩短时长")
            return
        dlg = RecommendDialog(slots, self)
        if dlg.exec() != RecommendDialog.DialogCode.Accepted:
            return
        chosen = dlg.chosen()
        if not chosen:
            return
        s, e = chosen
        from PyQt6.QtCore import QDateTime as QDT
        self.start_edit.setDateTime(QDT(s))
        self.end_edit.setDateTime(QDT(e))

    def values(self) -> dict:
        """返回预约参数 dict。"""
        start, end = self._slot()
        return {
            "did": self.device_combo.currentData(),
            "start": start,
            "end": end,
            "purpose": self.purpose.text().strip(),
            "appointment_type": self.type_combo.currentData(),
            "tutor_uid": self.tutor_combo.currentData(),
            "weeks": self.weeks_spin.value(),
        }


class RepairDialog(QDialog):
    """报修提交弹窗。"""

    def __init__(self, devices: list, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("提交报修")
        self.setMinimumWidth(360)
        layout = QFormLayout(self)

        self.device_combo = QComboBox()
        for d in devices:
            self.device_combo.addItem(f"{d['dev_name']}（{d['dev_no']}）", d["did"])
        layout.addRow("设备：", self.device_combo)

        self.content = QTextEdit()
        self.content.setPlaceholderText("请描述故障现象")
        self.content.setFixedHeight(120)
        layout.addRow("故障描述：", self.content)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def values(self) -> tuple:
        return self.device_combo.currentData(), self.content.toPlainText().strip()


class NoticeDialog(QDialog):
    """公告发布弹窗。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("发布公告")
        self.setMinimumWidth(400)
        layout = QFormLayout(self)
        self.title = QLineEdit()
        layout.addRow("标题：", self.title)
        self.content = QTextEdit()
        self.content.setFixedHeight(140)
        layout.addRow("内容：", self.content)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def values(self) -> tuple:
        return self.title.text().strip(), self.content.toPlainText().strip()


class PasswordDialog(QDialog):
    """修改密码弹窗。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("修改密码")
        self.setMinimumWidth(320)
        layout = QFormLayout(self)
        self.old_pwd = QLineEdit()
        self.new_pwd = QLineEdit()
        self.confirm_pwd = QLineEdit()
        for e in (self.old_pwd, self.new_pwd, self.confirm_pwd):
            e.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("原密码：", self.old_pwd)
        layout.addRow("新密码：", self.new_pwd)
        layout.addRow("确认新密码：", self.confirm_pwd)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def values(self) -> tuple:
        return (self.old_pwd.text(), self.new_pwd.text(), self.confirm_pwd.text())


class DeviceDialog(QDialog):
    """设备新增/编辑弹窗（含数量与二维码）。"""

    def __init__(self, labs: list, device: dict | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("编辑设备" if device else "新增设备")
        self.setMinimumWidth(360)
        layout = QFormLayout(self)

        self.dev_name = QLineEdit(device["dev_name"] if device else "")
        self.dev_no = QLineEdit(device["dev_no"] if device else "")
        self.dev_no.setEnabled(device is None)  # 编号不可改
        self.category = QLineEdit(device["category"] if device else "")
        self.spec = QLineEdit(device["spec"] if device else "")
        self.remark = QLineEdit(device["remark"] if device else "")
        self.total_spin = QSpinBox()
        self.total_spin.setRange(1, 999)
        self.total_spin.setValue((device or {}).get("total_count", 1) or 1)
        self.lab_combo = QComboBox()
        for lab in labs:
            self.lab_combo.addItem(lab["lab_name"], lab["lid"])
            if device and lab["lid"] == device["lab_id"]:
                self.lab_combo.setCurrentIndex(self.lab_combo.count() - 1)

        layout.addRow("名称：", self.dev_name)
        layout.addRow("编号：", self.dev_no)
        layout.addRow("类别：", self.category)
        layout.addRow("实验室：", self.lab_combo)
        layout.addRow("规格型号：", self.spec)
        layout.addRow("数量（台）：", self.total_spin)
        layout.addRow("备注：", self.remark)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def values(self) -> dict:
        return {
            "dev_name": self.dev_name.text().strip(),
            "dev_no": self.dev_no.text().strip(),
            "category": self.category.text().strip(),
            "lab_id": self.lab_combo.currentData(),
            "spec": self.spec.text().strip(),
            "remark": self.remark.text().strip(),
            "total_count": self.total_spin.value(),
        }


class UserDialog(QDialog):
    """账号新增弹窗（超级管理员）。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("新增账号")
        self.setMinimumWidth(340)
        layout = QFormLayout(self)
        self.username = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.real_name = QLineEdit()
        self.phone = QLineEdit()
        self.role_combo = QComboBox()
        self.role_combo.addItem("学生", 1)
        self.role_combo.addItem("实验室管理员", 2)
        self.role_combo.addItem("超级管理员", 3)
        self.role_combo.addItem("教师/导师", 4)

        layout.addRow("用户名：", self.username)
        layout.addRow("密码：", self.password)
        layout.addRow("真实姓名：", self.real_name)
        layout.addRow("手机号：", self.phone)
        layout.addRow("角色：", self.role_combo)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def values(self) -> dict:
        return {
            "username": self.username.text().strip(),
            "password": self.password.text(),
            "real_name": self.real_name.text().strip(),
            "phone": self.phone.text().strip(),
            "role": self.role_combo.currentData(),
        }


class QRDialog(QDialog):
    """设备二维码展示弹窗（优先渲染二维码图片，缺库时回退显示文本）。"""

    def __init__(self, device: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"设备二维码 - {device.get('dev_name', '')}")
        self.setMinimumSize(300, 320)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        content = device.get("qr_code") or f"DEV:{device.get('dev_no', '')}"
        info_label = QLabel(f"{device.get('dev_name', '')}（{device.get('dev_no', '')}）")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info_label)

        pixmap = self._make_qr_pixmap(content)
        if pixmap is not None:
            lbl = QLabel()
            lbl.setPixmap(pixmap)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(lbl)
        else:
            text = QLabel(content)
            text.setAlignment(Qt.AlignmentFlag.AlignCenter)
            text.setStyleSheet("font-size:16px;font-weight:bold;padding:20px;")
            layout.addWidget(text)
            layout.addWidget(QLabel("（未安装 qrcode/Pillow，展示二维码内容文本）"))
        layout.addWidget(QLabel("扫码可查看 / 预约该设备"))

    @staticmethod
    def _make_qr_pixmap(content: str) -> QPixmap | None:
        try:
            import qrcode
            from io import BytesIO
            img = qrcode.make(content)
            buf = BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            pm = QPixmap()
            pm.loadFromData(buf.read(), "PNG")
            return pm.scaled(220, 220, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        except Exception:
            return None
