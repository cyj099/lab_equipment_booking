# -*- coding: utf-8 -*-
"""实验室管理员主窗口：设备管理、预约审核、报修、公告、候补、报表、签到、物联、统计。"""

from PyQt6.QtCore import QDateTime, QTimer
from PyQt6.QtWidgets import (
    QComboBox, QDateTimeEdit, QFileDialog, QHBoxLayout, QInputDialog, QLabel,
    QPushButton, QTableWidgetItem, QVBoxLayout, QWidget,
)

from controller.appointment_controller import AppointmentController
from controller.device_controller import DeviceController
from controller.iot_controller import IoTController
from controller.notice_controller import NoticeController
from controller.repair_controller import RepairController
from controller.sign_controller import SignController
from controller.waitlist_controller import WaitlistController
from model.campus_model import CampusDAO
from model.lab_model import LabDAO
from utils.constants import (
    AUDIT_APPROVED, AUDIT_REJECTED, DEVICE_IDLE, DEVICE_REPAIR, DEVICE_SCRAPPED,
    REPAIR_FIXED, REPAIR_IN_PROGRESS, SIGN_METHOD_NAMES,
)
from utils.csv_export import export_to_csv
from utils.time_util import parse_dt
from view.base_window import BaseMainWindow
from view.chart_widget import build_stats_chart
from view.widgets import (
    DeviceDialog, NoticeDialog, QRDialog, appointment_view, confirm, device_view,
    fill_table, info, make_table, repair_view, waitlist_view, warn,
)


class LabAdminWindow(BaseMainWindow):
    """实验室管理员端主窗口。"""

    def __init__(self, user: dict) -> None:
        super().__init__(user)
        self.setWindowTitle("实验室设备预约系统 - 实验室管理员端")
        self.resize(1200, 740)

        self.device_ctrl = DeviceController()
        self.appt_ctrl = AppointmentController()
        self.repair_ctrl = RepairController()
        self.notice_ctrl = NoticeController()
        self.waitlist_ctrl = WaitlistController()
        self.sign_ctrl = SignController()
        self.iot_ctrl = IoTController()
        self.lab_dao = LabDAO()
        self.campus_dao = CampusDAO()

        self.add_page("设备管理", self._page_devices())
        self.add_page("预约审核", self._page_audit())
        self.add_page("签到记录", self._page_sign_records())
        self.add_page("报修工单", self._page_repairs())
        self.add_page("公告管理", self._page_notices())
        self.add_page("候补管理", self._page_waitlist())
        self.add_page("门禁电源", self._page_hardware())
        self.add_page("实时监控", self._page_monitor())
        self.add_page("统计图表", self._page_charts())
        self.add_page("预约报表", self._page_report())

        self._release_timer = QTimer(self)
        self._release_timer.timeout.connect(self._auto_release)
        self._release_timer.start(120_000)

    # ---------- 设备管理 ----------
    def _page_devices(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        top = QHBoxLayout()
        top.addWidget(QLabel("校区："))
        self.dev_campus = QComboBox()
        self.dev_campus.currentIndexChanged.connect(self._refresh_devices)
        top.addWidget(self.dev_campus)
        top.addStretch(1)
        v.addLayout(top)

        self.dev_table = make_table(["ID", "名称", "编号", "类别", "实验室", "校区", "规格", "数量", "状态"])
        v.addWidget(self.dev_table)
        btns = QHBoxLayout()
        add_btn = QPushButton("新增设备")
        add_btn.clicked.connect(self._add_device)
        edit_btn = QPushButton("编辑设备")
        edit_btn.clicked.connect(self._edit_device)
        idle_btn = QPushButton("设为空闲")
        idle_btn.clicked.connect(lambda: self._set_device_status(DEVICE_IDLE))
        repair_btn = QPushButton("设为维修")
        repair_btn.clicked.connect(lambda: self._set_device_status(DEVICE_REPAIR))
        scrap_btn = QPushButton("报废")
        scrap_btn.clicked.connect(lambda: self._set_device_status(DEVICE_SCRAPPED))
        qr_btn = QPushButton("查看二维码")
        qr_btn.setObjectName("ghost")
        qr_btn.clicked.connect(self._show_qr)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_devices)
        for b in (add_btn, edit_btn, idle_btn, repair_btn, scrap_btn, qr_btn, refresh_btn):
            btns.addWidget(b)
        btns.addStretch(1)
        v.addLayout(btns)
        self._refresh_campus()
        self._refresh_devices()
        return w

    def _refresh_campus(self) -> None:
        self.dev_campus.blockSignals(True)
        self.dev_campus.clear()
        self.dev_campus.addItem("全部校区", None)
        for c in self.campus_dao.list_all():
            self.dev_campus.addItem(c["campus_name"], c["cid"])
        self.dev_campus.blockSignals(False)

    def _refresh_devices(self) -> None:
        campus_id = self.dev_campus.currentData()
        fill_table(self.dev_table, device_view(self.device_ctrl.list_devices(campus_id=campus_id)),
                   ["did", "dev_name", "dev_no", "category", "lab_name", "campus_name",
                    "spec", "total_count", "status_name"])

    def _selected_device_id(self) -> int | None:
        row = self.dev_table.currentRow()
        if row < 0:
            warn("请先选择一条设备")
            return None
        return int(self.dev_table.item(row, 0).text())

    def _show_qr(self) -> None:
        did = self._selected_device_id()
        if not did:
            return
        QRDialog(self.device_ctrl.get_device(did), self).exec()

    def _add_device(self) -> None:
        dlg = DeviceDialog(self.lab_dao.list_all(), None, self)
        if dlg.exec() != DeviceDialog.DialogCode.Accepted:
            return
        f = dlg.values()
        ok, msg = self.device_ctrl.add_device(f["dev_name"], f["dev_no"], f["category"],
                                              f["lab_id"], f["spec"], f["remark"],
                                              total_count=f["total_count"])
        info(msg) if ok else warn(msg)
        self._refresh_devices()

    def _edit_device(self) -> None:
        did = self._selected_device_id()
        if not did:
            return
        device = self.device_ctrl.get_device(did)
        dlg = DeviceDialog(self.lab_dao.list_all(), device, self)
        if dlg.exec() != DeviceDialog.DialogCode.Accepted:
            return
        f = dlg.values()
        ok, msg = self.device_ctrl.update_device(did, **f)
        info(msg) if ok else warn(msg)
        self._refresh_devices()

    def _set_device_status(self, status: int) -> None:
        did = self._selected_device_id()
        if not did:
            return
        ok, msg = self.device_ctrl.set_status(did, status)
        info(msg) if ok else warn(msg)
        self._refresh_devices()

    # ---------- 预约审核 ----------
    def _page_audit(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        top = QHBoxLayout()
        top.addWidget(QLabel("状态筛选："))
        self.audit_filter = QComboBox()
        self.audit_filter.addItem("待审核", 0)
        self.audit_filter.addItem("已通过", 1)
        self.audit_filter.addItem("全部", -1)
        self.audit_filter.currentIndexChanged.connect(self._refresh_audit)
        top.addWidget(self.audit_filter)
        top.addStretch(1)
        v.addLayout(top)

        self.audit_table = make_table(["单号", "设备", "申请人", "开始", "结束", "状态"])
        v.addWidget(self.audit_table)

        btns = QHBoxLayout()
        approve_btn = QPushButton("通过")
        approve_btn.clicked.connect(lambda: self._audit(AUDIT_APPROVED))
        reject_btn = QPushButton("驳回")
        reject_btn.clicked.connect(lambda: self._audit(AUDIT_REJECTED))
        done_btn = QPushButton("标记完成")
        done_btn.clicked.connect(self._mark_completed)
        noshow_btn = QPushButton("标记爽约")
        noshow_btn.clicked.connect(self._mark_no_show)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_audit)
        for b in (approve_btn, reject_btn, done_btn, noshow_btn, refresh_btn):
            btns.addWidget(b)
        btns.addStretch(1)
        v.addLayout(btns)
        self._refresh_audit()
        return w

    def _refresh_audit(self) -> None:
        status = self.audit_filter.currentData()
        rows = (self.appt_ctrl.list_all() if status == -1
                else self.appt_ctrl.list_by_status(status))
        fill_table(self.audit_table, appointment_view(rows),
                   ["aid", "dev_name", "real_name", "start_time", "end_time", "status_name"])

    def _selected_aid(self) -> int | None:
        row = self.audit_table.currentRow()
        if row < 0:
            warn("请先选择一条预约")
            return None
        return int(self.audit_table.item(row, 0).text())

    def _audit(self, status: int) -> None:
        aid = self._selected_aid()
        if not aid:
            return
        reason = ""
        if status == AUDIT_REJECTED:
            reason, ok = QInputDialog.getText(self, "驳回原因", "请输入驳回原因：")
            if not ok:
                return
        ok, msg = self.appt_ctrl.audit(aid, status, reason, self.user)
        info(msg) if ok else warn(msg)
        self._refresh_audit()

    def _mark_completed(self) -> None:
        aid = self._selected_aid()
        if not aid:
            return
        ok, msg = self.appt_ctrl.mark_completed(aid, self.user)
        info(msg) if ok else warn(msg)
        self._refresh_audit()

    def _mark_no_show(self) -> None:
        aid = self._selected_aid()
        if not aid:
            return
        if not confirm(f"确认将预约单 {aid} 标记为爽约？爽约次数将累计。"):
            return
        ok, msg = self.appt_ctrl.mark_no_show(aid, self.user)
        info(msg) if ok else warn(msg)
        self._refresh_audit()

    # ---------- 签到记录 ----------
    def _page_sign_records(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.sign_table = make_table(["ID", "姓名", "设备", "方式", "时间"])
        v.addWidget(self.sign_table)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_sign)
        v.addWidget(refresh_btn)
        self._refresh_sign()
        return w

    def _refresh_sign(self) -> None:
        rows = self.sign_ctrl.list_all()
        for r in rows:
            r["method_name"] = SIGN_METHOD_NAMES.get(r.get("method"), r.get("method", ""))
        fill_table(self.sign_table, rows,
                   ["sid", "real_name", "dev_name", "method_name", "sign_time"])

    # ---------- 报修工单 ----------
    def _page_repairs(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.repair_table = make_table(["单号", "设备", "报修人", "故障描述", "状态", "处理意见"])
        v.addWidget(self.repair_table)
        btns = QHBoxLayout()
        doing_btn = QPushButton("开始维修")
        doing_btn.clicked.connect(lambda: self._handle_repair(REPAIR_IN_PROGRESS))
        fixed_btn = QPushButton("标记已修复")
        fixed_btn.clicked.connect(lambda: self._handle_repair(REPAIR_FIXED))
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_repairs)
        for b in (doing_btn, fixed_btn, refresh_btn):
            btns.addWidget(b)
        btns.addStretch(1)
        v.addLayout(btns)
        self._refresh_repairs()
        return w

    def _refresh_repairs(self) -> None:
        fill_table(self.repair_table, repair_view(self.repair_ctrl.list_all()),
                   ["rid", "dev_name", "real_name", "content", "status_name", "deal_msg"])

    def _handle_repair(self, status: int) -> None:
        row = self.repair_table.currentRow()
        if row < 0:
            warn("请先选择一条报修")
            return
        rid = int(self.repair_table.item(row, 0).text())
        deal_msg, ok = QInputDialog.getText(self, "处理意见", "请输入处理意见（可空）：")
        if not ok:
            return
        ok, msg = self.repair_ctrl.handle(rid, status, deal_msg, self.user["uid"])
        info(msg) if ok else warn(msg)
        self._refresh_repairs()

    # ---------- 公告管理 ----------
    def _page_notices(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.notice_table = make_table(["编号", "标题", "内容", "发布时间"])
        v.addWidget(self.notice_table)
        btns = QHBoxLayout()
        pub_btn = QPushButton("发布公告")
        pub_btn.clicked.connect(self._publish_notice)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_notices)
        btns.addWidget(pub_btn)
        btns.addWidget(refresh_btn)
        btns.addStretch(1)
        v.addLayout(btns)
        self._refresh_notices()
        return w

    def _refresh_notices(self) -> None:
        fill_table(self.notice_table, self.notice_ctrl.list_notices(),
                   ["nid", "title", "content", "publish_time"])

    def _publish_notice(self) -> None:
        dlg = NoticeDialog(self)
        if dlg.exec() != NoticeDialog.DialogCode.Accepted:
            return
        title, content = dlg.values()
        ok, msg = self.notice_ctrl.publish(title, content, self.user["uid"])
        info(msg) if ok else warn(msg)
        self._refresh_notices()

    # ---------- 候补管理 ----------
    def _page_waitlist(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.wait_table = make_table(["编号", "设备", "候补人", "开始", "结束", "状态"])
        v.addWidget(self.wait_table)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_waitlist)
        v.addWidget(refresh_btn)
        self._refresh_waitlist()
        return w

    def _refresh_waitlist(self) -> None:
        fill_table(self.wait_table, waitlist_view(self.waitlist_ctrl.list_all()),
                   ["wid", "dev_name", "real_name", "start_time", "end_time", "status_name"])

    # ---------- 门禁 / 电源联动 ----------
    def _page_hardware(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("实验室门禁："))
        self.door_table = make_table(["实验室", "状态", "操作"])
        v.addWidget(self.door_table)
        v.addWidget(QLabel("设备电源："))
        self.power_table = make_table(["设备", "状态", "操作"])
        v.addWidget(self.power_table)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_hardware)
        v.addWidget(refresh_btn)
        self._refresh_hardware()
        return w

    def _refresh_hardware(self) -> None:
        doors = self.iot_ctrl.list_doors()
        self.door_table.setRowCount(len(doors))
        for i, d in enumerate(doors):
            self.door_table.setItem(i, 0, _item(d["lab_name"]))
            self.door_table.setItem(i, 1, _item("已开门" if d["state"] else "已关门"))
            btn = QPushButton("关门" if d["state"] else "开门")
            lab_id = d["lab_id"]
            btn.clicked.connect(lambda _=False, lid=lab_id, st=not d["state"]:
                                self._toggle_door(lid, st))
            self.door_table.setCellWidget(i, 2, btn)

        powers = self.iot_ctrl.list_powers()
        self.power_table.setRowCount(len(powers))
        for i, p in enumerate(powers):
            self.power_table.setItem(i, 0, _item(p["dev_name"]))
            self.power_table.setItem(i, 1, _item("通电" if p["state"] else "断电"))
            btn = QPushButton("断电" if p["state"] else "通电")
            did = p["did"]
            btn.clicked.connect(lambda _=False, dd=did, st=not p["state"]:
                                self._toggle_power(dd, st))
            self.power_table.setCellWidget(i, 2, btn)

    def _toggle_door(self, lab_id: int, opened: bool) -> None:
        self.iot_ctrl.set_door(lab_id, opened)
        self._refresh_hardware()

    def _toggle_power(self, did: int, on: bool) -> None:
        self.iot_ctrl.set_power(did, on)
        self._refresh_hardware()

    # ---------- 实时监控 ----------
    def _page_monitor(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("设备物联网实时读数（每 2 秒刷新，模拟数据）："))
        self.metric_table = make_table(["设备", "电压(V)", "电流(A)", "温度(℃)", "在线", "更新时间"])
        v.addWidget(self.metric_table)
        self._refresh_metrics()
        self._monitor_timer = QTimer(self)
        self._monitor_timer.timeout.connect(self._refresh_metrics)
        self._monitor_timer.start(2000)
        return w

    def _refresh_metrics(self) -> None:
        self.iot_ctrl.refresh_metrics()
        rows = self.iot_ctrl.get_metrics()
        for r in rows:
            r["online_name"] = "在线" if r.get("online") else "离线"
        fill_table(self.metric_table, rows,
                   ["dev_name", "voltage", "current", "temperature", "online_name", "update_time"])

    # ---------- 统计图表 ----------
    def _page_charts(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        refresh_btn = QPushButton("刷新图表")
        refresh_btn.clicked.connect(self._refresh_charts)
        v.addWidget(refresh_btn)
        self.chart_container = QVBoxLayout()
        v.addLayout(self.chart_container)
        self._refresh_charts()
        return w

    def _refresh_charts(self) -> None:
        while self.chart_container.count():
            item = self.chart_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.chart_container.addWidget(build_stats_chart(self.appt_ctrl.list_all()))

    # ---------- 预约报表 ----------
    def _page_report(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        row = QHBoxLayout()
        row.addWidget(QLabel("开始时间："))
        self.export_start = QDateTimeEdit(QDateTime.currentDateTime().addMonths(-1))
        self.export_start.setDisplayFormat("yyyy-MM-dd HH:mm")
        row.addWidget(self.export_start)
        row.addWidget(QLabel("结束时间："))
        self.export_end = QDateTimeEdit(QDateTime.currentDateTime().addMonths(1))
        self.export_end.setDisplayFormat("yyyy-MM-dd HH:mm")
        row.addWidget(self.export_end)
        row.addStretch(1)
        v.addLayout(row)

        export_btn = QPushButton("导出预约报表 (CSV)")
        export_btn.clicked.connect(self._export_report)
        v.addWidget(export_btn)
        v.addWidget(QLabel("报表包含所选时间范围内的全部预约记录，用于设备使用率统计。"))
        v.addStretch(1)
        return w

    def _export_report(self) -> None:
        start = self.export_start.dateTime().toPyDateTime()
        end = self.export_end.dateTime().toPyDateTime()
        rows = self.appt_ctrl.list_all()
        filtered = []
        for r in rows:
            st, et = parse_dt(r["start_time"]), parse_dt(r["end_time"])
            if st and et and st >= start and et <= end:
                r = dict(r)
                from utils.constants import AUDIT_STATUS_NAMES
                r["status_name"] = AUDIT_STATUS_NAMES.get(r["audit_status"], "")
                filtered.append(r)
        path, _ = QFileDialog.getSaveFileName(self, "保存报表", "预约报表.csv",
                                              "CSV 文件 (*.csv)")
        if not path:
            return
        cols = ["aid", "dev_name", "real_name", "start_time", "end_time",
                "status_name", "audit_msg"]
        headers = ["单号", "设备", "申请人", "开始时间", "结束时间", "状态", "备注"]
        ok = export_to_csv(filtered, cols, headers, path)
        info(f"报表已导出：{path}") if ok else warn("导出失败")

    # ---------- 定时任务 ----------
    def _auto_release(self) -> None:
        n = self.appt_ctrl.auto_release_expired()
        if n:
            self._refresh_audit()


def _item(text) -> QTableWidgetItem:
    return QTableWidgetItem("" if text is None else str(text))
