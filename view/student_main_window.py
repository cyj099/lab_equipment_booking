# -*- coding: utf-8 -*-
"""学生主窗口：设备浏览/预约、日历视图、签到、信用分、报修、公告、消息、候补、个人信息。"""

from datetime import datetime, timedelta

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QCalendarWidget, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from controller.appointment_controller import AppointmentController
from controller.device_controller import DeviceController
from controller.message_controller import MessageController
from controller.notice_controller import NoticeController
from controller.repair_controller import RepairController
from controller.sign_controller import SignController
from controller.user_controller import UserController
from controller.waitlist_controller import WaitlistController
from model.credit_model import CreditLogDAO
from utils import face_util
from utils.constants import (
    APPT_WEEKLY, AUDIT_APPROVED, DEVICE_IDLE, DEVICE_IN_USE,
    ROLE_TEACHER, SIGN_FACE, SIGN_MANUAL,
)
from view.base_window import BaseMainWindow
from view.widgets import (
    AppointDialog, PasswordDialog, QRDialog, RepairDialog, appointment_view,
    confirm, device_view, fill_table, info, make_table, repair_view,
    waitlist_view, warn,
)


class StudentMainWindow(BaseMainWindow):
    """学生端主窗口。"""

    def __init__(self, user: dict) -> None:
        super().__init__(user)
        self.setWindowTitle("实验室设备预约系统 - 学生端")
        self.resize(1160, 720)

        self.user_ctrl = UserController()
        self.device_ctrl = DeviceController()
        self.appt_ctrl = AppointmentController()
        self.repair_ctrl = RepairController()
        self.notice_ctrl = NoticeController()
        self.waitlist_ctrl = WaitlistController()
        self.msg_ctrl = MessageController()
        self.sign_ctrl = SignController()
        self.credit_dao = CreditLogDAO()

        self.add_page("设备列表", self._page_devices())
        self.add_page("我的预约", self._page_my_appointments())
        self.add_page("预约日历", self._page_calendar())
        self.add_page("预约签到", self._page_sign())
        self.add_page("我的信用", self._page_credit())
        self.add_page("我的报修", self._page_repairs())
        self.add_page("系统公告", self._page_notices())
        self.add_page("站内消息", self._page_messages())
        self.add_page("候补队列", self._page_waitlist())
        self.add_page("个人信息", self._page_profile())

        self._reminded = set()
        self._remind_timer = QTimer(self)
        self._remind_timer.timeout.connect(self._check_reminders)
        self._remind_timer.start(60_000)
        self._release_timer = QTimer(self)
        self._release_timer.timeout.connect(self._auto_release)
        self._release_timer.start(120_000)

    # ---------- 设备列表 ----------
    def _page_devices(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        top = QHBoxLayout()
        self.dev_search = QLineEdit()
        self.dev_search.setPlaceholderText("按名称 / 编号搜索")
        self.dev_search.returnPressed.connect(self._refresh_devices)
        self.dev_category = QComboBox()
        self.dev_category.currentIndexChanged.connect(self._refresh_devices)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_devices)
        top.addWidget(QLabel("搜索："))
        top.addWidget(self.dev_search)
        top.addWidget(QLabel("分类："))
        top.addWidget(self.dev_category)
        top.addWidget(refresh_btn)
        v.addLayout(top)

        self.dev_table = make_table(["编号", "名称", "类别", "实验室", "规格", "总数", "当前可约", "状态"])
        v.addWidget(self.dev_table)

        btns = QHBoxLayout()
        submit_btn = QPushButton("提交预约")
        submit_btn.clicked.connect(self._submit_appointment)
        wait_btn = QPushButton("加入候补")
        wait_btn.clicked.connect(self._join_waitlist)
        qr_btn = QPushButton("查看二维码")
        qr_btn.setObjectName("ghost")
        qr_btn.clicked.connect(self._show_qr)
        btns.addWidget(submit_btn)
        btns.addWidget(wait_btn)
        btns.addWidget(qr_btn)
        btns.addStretch(1)
        v.addLayout(btns)
        self._refresh_devices()
        return w

    def _bookable_devices(self) -> list:
        return [d for d in self.device_ctrl.list_devices()
                if d["status"] in (DEVICE_IDLE, DEVICE_IN_USE)]

    def _tutors(self) -> list:
        return self.user_ctrl.dao.list_by_role(ROLE_TEACHER)

    def _refresh_devices(self) -> None:
        kw = self.dev_search.text().strip()
        cat = self.dev_category.currentData()
        devices = self.device_ctrl.list_devices(category=cat or "", keyword=kw)
        cats = sorted({d["category"] for d in self.device_ctrl.list_devices() if d["category"]})
        self.dev_category.blockSignals(True)
        self.dev_category.clear()
        self.dev_category.addItem("全部分类", "")
        for c in cats:
            self.dev_category.addItem(c, c)
        idx = self.dev_category.findData(cat)
        self.dev_category.setCurrentIndex(idx if idx >= 0 else 0)
        self.dev_category.blockSignals(False)

        now = datetime.now()
        for d in devices:
            d["current_available"] = self.appt_ctrl.available_count(
                d["did"], now, now + timedelta(hours=1))
        fill_table(self.dev_table, device_view(devices),
                   ["dev_no", "dev_name", "category", "lab_name", "spec",
                    "total_count", "current_available", "status_name"])

    def _selected_device(self) -> dict | None:
        row = self.dev_table.currentRow()
        if row < 0:
            warn("请先选择一台设备")
            return None
        dev_no = self.dev_table.item(row, 0).text()
        for d in self.device_ctrl.list_devices():
            if d["dev_no"] == dev_no:
                return d
        return None

    def _show_qr(self) -> None:
        device = self._selected_device()
        if not device:
            return
        QRDialog(device, self).exec()

    def _open_appoint(self, waitlist: bool = False) -> None:
        devices = self._bookable_devices()
        if not devices:
            warn("当前没有可预约的设备")
            return
        dlg = AppointDialog(devices, self, tutors=self._tutors(), appt_ctrl=self.appt_ctrl)
        if dlg.exec() != AppointDialog.DialogCode.Accepted:
            return
        f = dlg.values()
        if waitlist:
            ok, msg = self.waitlist_ctrl.join(self.user["uid"], f["did"], f["start"], f["end"])
        elif f["appointment_type"] == APPT_WEEKLY:
            ok, msg = self.appt_ctrl.submit_weekly(self.user["uid"], f["did"], f["start"],
                                                   f["end"], weeks=f["weeks"],
                                                   tutor_uid=f["tutor_uid"])
        else:
            ok, msg = self.appt_ctrl.submit_appointment(
                self.user["uid"], f["did"], f["start"], f["end"],
                appointment_type=f["appointment_type"], tutor_uid=f["tutor_uid"])
        if ok:
            info(msg)
            self._refresh_devices()
        elif not waitlist and "候补" in msg:
            if confirm(f"{msg}\n\n是否加入候补队列？"):
                ok2, msg2 = self.waitlist_ctrl.join(self.user["uid"], f["did"],
                                                    f["start"], f["end"])
                info(msg2) if ok2 else warn(msg2)
        else:
            warn(msg)

    def _submit_appointment(self) -> None:
        self._open_appoint(waitlist=False)

    def _join_waitlist(self) -> None:
        self._open_appoint(waitlist=True)

    # ---------- 我的预约 ----------
    def _page_my_appointments(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.appt_table = make_table(["单号", "设备", "开始", "结束", "状态", "审核意见"])
        v.addWidget(self.appt_table)
        btns = QHBoxLayout()
        cancel_btn = QPushButton("取消选中预约")
        cancel_btn.clicked.connect(self._cancel_appointment)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_appointments)
        btns.addWidget(cancel_btn)
        btns.addWidget(refresh_btn)
        btns.addStretch(1)
        v.addLayout(btns)
        self._refresh_appointments()
        return w

    def _refresh_appointments(self) -> None:
        rows = appointment_view(self.appt_ctrl.list_by_user(self.user["uid"]))
        fill_table(self.appt_table, rows,
                   ["aid", "dev_name", "start_time", "end_time", "status_name", "audit_msg"])

    def _cancel_appointment(self) -> None:
        row = self.appt_table.currentRow()
        if row < 0:
            warn("请先选择一条预约")
            return
        aid = int(self.appt_table.item(row, 0).text())
        if not confirm(f"确认取消预约单 {aid} ？"):
            return
        ok, msg = self.appt_ctrl.cancel(aid, self.user)
        info(msg) if ok else warn(msg)
        self._refresh_appointments()

    # ---------- 预约日历（日 / 周 / 月） ----------
    def _page_calendar(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.selectionChanged.connect(self._refresh_calendar)
        v.addWidget(self.calendar)

        mode = QHBoxLayout()
        self.cal_mode = QComboBox()
        self.cal_mode.addItem("日视图", "day")
        self.cal_mode.addItem("周视图", "week")
        self.cal_mode.addItem("月视图", "month")
        self.cal_mode.currentIndexChanged.connect(self._refresh_calendar)
        mode.addWidget(QLabel("视图："))
        mode.addWidget(self.cal_mode)
        mode.addStretch(1)
        v.addLayout(mode)

        self.cal_table = make_table(["单号", "设备", "开始", "结束", "状态"])
        v.addWidget(self.cal_table)
        self._refresh_calendar()
        return w

    def _refresh_calendar(self) -> None:
        sel = self.calendar.selectedDate()
        if not sel.isValid():
            return
        day = sel.toPyDate()
        mode = self.cal_mode.currentData()
        if mode == "week":
            start = day - timedelta(days=day.weekday())
            end = start + timedelta(days=6)
        elif mode == "month":
            start = day.replace(day=1)
            nxt = (start.replace(month=start.month % 12 + 1, day=1)
                   if start.month < 12 else start.replace(year=start.year + 1, month=1, day=1))
            end = nxt - timedelta(days=1)
        else:
            start = end = day
        start_dt = datetime.combine(start, datetime.min.time())
        end_dt = datetime.combine(end, datetime.max.time())
        from utils.time_util import parse_dt
        rows = []
        for a in self.appt_ctrl.list_by_user(self.user["uid"]):
            st = parse_dt(a["start_time"])
            if st and start_dt <= st <= end_dt:
                rows.append(a)
        fill_table(self.cal_table, appointment_view(rows),
                   ["aid", "dev_name", "start_time", "end_time", "status_name"])

    # ---------- 预约签到 ----------
    def _page_sign(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        hint = QLabel("选择一条「已通过」的预约进行签到，签到后门禁自动开门、设备通电。")
        hint.setStyleSheet("color:gray;")
        v.addWidget(hint)
        self.sign_table = make_table(["单号", "设备", "开始", "结束"])
        v.addWidget(self.sign_table)
        btns = QHBoxLayout()
        face_btn = QPushButton("人脸签到")
        face_btn.clicked.connect(self._face_sign)
        manual_btn = QPushButton("手动签到")
        manual_btn.setObjectName("ghost")
        manual_btn.clicked.connect(self._manual_sign)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_sign)
        btns.addWidget(face_btn)
        btns.addWidget(manual_btn)
        btns.addWidget(refresh_btn)
        btns.addStretch(1)
        v.addLayout(btns)
        self._refresh_sign()
        return w

    def _refresh_sign(self) -> None:
        rows = [a for a in self.appt_ctrl.list_by_user(self.user["uid"])
                if a["audit_status"] == AUDIT_APPROVED]
        fill_table(self.sign_table, rows, ["aid", "dev_name", "start_time", "end_time"])

    def _selected_sign_aid(self) -> int | None:
        row = self.sign_table.currentRow()
        if row < 0:
            warn("请先选择一条待签到预约")
            return None
        return int(self.sign_table.item(row, 0).text())

    def _manual_sign(self) -> None:
        aid = self._selected_sign_aid()
        if not aid:
            return
        ok, msg = self.sign_ctrl.sign_in(self.user["uid"], aid, SIGN_MANUAL)
        info(msg) if ok else warn(msg)
        self._refresh_sign()

    def _face_sign(self) -> None:
        aid = self._selected_sign_aid()
        if not aid:
            return
        if not face_util.face_available():
            warn("未安装人脸识别库（opencv / face_recognition），已回退手动签到")
            self._manual_sign()
            return
        frame = face_util.capture_frame()
        if frame is None:
            warn("无法打开摄像头，已回退手动签到")
            self._manual_sign()
            return
        result = face_util.verify_face(self.user["uid"], frame)
        if result is True:
            ok, msg = self.sign_ctrl.sign_in(self.user["uid"], aid, SIGN_FACE)
            info(msg) if ok else warn(msg)
        else:
            if confirm("人脸比对未通过（或尚未注册人脸），是否改用手动签到？"):
                self._manual_sign()
        self._refresh_sign()

    # ---------- 我的信用 ----------
    def _page_credit(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.credit_label = QLabel()
        self.credit_label.setStyleSheet("font-size:18px;font-weight:bold;color:#07C160;")
        v.addWidget(self.credit_label)
        v.addWidget(QLabel("信用分变动记录："))
        self.credit_table = make_table(["时间", "变动", "原因"])
        v.addWidget(self.credit_table)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_credit)
        v.addWidget(refresh_btn)
        self._refresh_credit()
        return w

    def _refresh_credit(self) -> None:
        u = self.user_ctrl.dao.get_by_id(self.user["uid"])
        score = (u or {}).get("credit_score", 100)
        self.credit_label.setText(f"当前信用分：{score}")
        rows = self.credit_dao.list_by_user(self.user["uid"])
        for r in rows:
            r["change_show"] = f"{'+' if r['change'] > 0 else ''}{r['change']}"
        fill_table(self.credit_table, rows, ["op_time", "change_show", "reason"])

    # ---------- 我的报修 ----------
    def _page_repairs(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.repair_table = make_table(["单号", "设备", "故障描述", "状态", "处理意见"])
        v.addWidget(self.repair_table)
        btns = QHBoxLayout()
        add_btn = QPushButton("提交报修")
        add_btn.clicked.connect(self._submit_repair)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_repairs)
        btns.addWidget(add_btn)
        btns.addWidget(refresh_btn)
        btns.addStretch(1)
        v.addLayout(btns)
        self._refresh_repairs()
        return w

    def _refresh_repairs(self) -> None:
        fill_table(self.repair_table, repair_view(self.repair_ctrl.list_by_user(self.user["uid"])),
                   ["rid", "dev_name", "content", "status_name", "deal_msg"])

    def _submit_repair(self) -> None:
        devices = self.device_ctrl.list_devices()
        if not devices:
            warn("暂无设备")
            return
        dlg = RepairDialog(devices, self)
        if dlg.exec() != RepairDialog.DialogCode.Accepted:
            return
        did, content = dlg.values()
        ok, msg = self.repair_ctrl.submit_repair(self.user["uid"], did, content)
        info(msg) if ok else warn(msg)
        self._refresh_repairs()

    # ---------- 系统公告 ----------
    def _page_notices(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.notice_table = make_table(["标题", "内容", "发布人", "发布时间"])
        v.addWidget(self.notice_table)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_notices)
        v.addWidget(refresh_btn)
        self._refresh_notices()
        return w

    def _refresh_notices(self) -> None:
        fill_table(self.notice_table, self.notice_ctrl.list_notices(),
                   ["title", "content", "publisher_name", "publish_time"])

    # ---------- 站内消息 ----------
    def _page_messages(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.msg_table = make_table(["标题", "内容", "时间", "状态"])
        v.addWidget(self.msg_table)
        btns = QHBoxLayout()
        read_btn = QPushButton("标记已读")
        read_btn.clicked.connect(self._mark_read)
        all_read_btn = QPushButton("全部已读")
        all_read_btn.clicked.connect(self._mark_all_read)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_messages)
        for b in (read_btn, all_read_btn, refresh_btn):
            btns.addWidget(b)
        btns.addStretch(1)
        v.addLayout(btns)
        self._refresh_messages()
        return w

    def _msg_rows(self):
        rows = self.msg_ctrl.list_by_user(self.user["uid"])
        for r in rows:
            r["read_name"] = "已读" if r["is_read"] else "未读"
        return rows

    def _refresh_messages(self) -> None:
        fill_table(self.msg_table, self._msg_rows(),
                   ["title", "content", "create_time", "read_name"])

    def _mark_read(self) -> None:
        row = self.msg_table.currentRow()
        if row < 0:
            warn("请先选择一条消息")
            return
        mids = [r["mid"] for r in self.msg_ctrl.list_by_user(self.user["uid"])]
        self.msg_ctrl.mark_read(mids[row])
        self._refresh_messages()

    def _mark_all_read(self) -> None:
        self.msg_ctrl.mark_all_read(self.user["uid"])
        self._refresh_messages()

    # ---------- 候补队列 ----------
    def _page_waitlist(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.wait_table = make_table(["编号", "设备", "开始", "结束", "状态"])
        v.addWidget(self.wait_table)
        btns = QHBoxLayout()
        cancel_btn = QPushButton("取消候补")
        cancel_btn.clicked.connect(self._cancel_waitlist)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_waitlist)
        btns.addWidget(cancel_btn)
        btns.addWidget(refresh_btn)
        btns.addStretch(1)
        v.addLayout(btns)
        self._refresh_waitlist()
        return w

    def _refresh_waitlist(self) -> None:
        rows = self.waitlist_ctrl.list_by_user(self.user["uid"])
        fill_table(self.wait_table, waitlist_view(rows),
                   ["wid", "dev_name", "start_time", "end_time", "status_name"])

    def _cancel_waitlist(self) -> None:
        row = self.wait_table.currentRow()
        if row < 0:
            warn("请先选择一条候补")
            return
        wid = int(self.wait_table.item(row, 0).text())
        ok, msg = self.waitlist_ctrl.cancel(wid, self.user["uid"])
        info(msg) if ok else warn(msg)
        self._refresh_waitlist()

    # ---------- 个人信息 ----------
    def _page_profile(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        form = QFormLayout()
        self.prof_name = QLineEdit(self.user["real_name"])
        self.prof_phone = QLineEdit(self.user.get("phone", ""))
        form.addRow("真实姓名：", self.prof_name)
        form.addRow("手机号：", self.prof_phone)
        form.addRow("用户名：", QLabel(self.user["username"]))
        form.addRow("信用分：", QLabel(str(self.user.get("credit_score", 100))))
        v.addLayout(form)

        save_btn = QPushButton("保存个人信息")
        save_btn.clicked.connect(self._save_profile)
        pwd_btn = QPushButton("修改密码")
        pwd_btn.clicked.connect(self._change_password)
        v.addWidget(save_btn)
        v.addWidget(pwd_btn)
        v.addStretch(1)
        return w

    def _save_profile(self) -> None:
        ok, msg = self.user_ctrl.update_profile(self.user["uid"],
                                                real_name=self.prof_name.text().strip(),
                                                phone=self.prof_phone.text().strip())
        info(msg) if ok else warn(msg)
        self.user["real_name"] = self.prof_name.text().strip()
        self.info_label.setText(f"当前用户：{self.user['real_name']}（学生）")

    def _change_password(self) -> None:
        dlg = PasswordDialog(self)
        if dlg.exec() != PasswordDialog.DialogCode.Accepted:
            return
        old, new, confirm_pwd = dlg.values()
        if new != confirm_pwd:
            warn("两次输入的新密码不一致")
            return
        ok, msg = self.user_ctrl.change_password(self.user["uid"], old, new)
        info(msg) if ok else warn(msg)

    # ---------- 定时任务：提醒 / 自动释放 ----------
    def _check_reminders(self) -> None:
        now = datetime.now()
        for a in self.appt_ctrl.list_by_user(self.user["uid"]):
            if a["audit_status"] != AUDIT_APPROVED or a["aid"] in self._reminded:
                continue
            from utils.time_util import parse_dt
            st = parse_dt(a["start_time"])
            if st and timedelta(0) <= st - now <= timedelta(minutes=30):
                self._reminded.add(a["aid"])
                info(f"预约即将开始：{a['dev_name']}\n{st:%m-%d %H:%M} 开始，请准时签到。",
                     "预约提醒")

    def _auto_release(self) -> None:
        n = self.appt_ctrl.auto_release_expired()
        if n:
            self._refresh_appointments()
