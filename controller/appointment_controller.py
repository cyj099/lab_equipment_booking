# -*- coding: utf-8 -*-
"""预约核心控制器：提交、多级审核、取消、爽约判定、信用分、周期预约。"""

import uuid
from datetime import datetime, timedelta

from config import (BLACKLIST_THRESHOLD, CANCEL_DEADLINE_MINUTES,
                    MAX_BOOKING_HOURS, MIN_CREDIT_SCORE)
from controller.iot_controller import IoTController
from controller.log_controller import LogController
from controller.message_controller import MessageController
from controller.setting_controller import SettingController
from controller.waitlist_controller import WaitlistController
from model.appointment_model import AppointmentDAO
from model.credit_model import CreditLogDAO
from model.device_model import DeviceDAO
from model.user_model import UserDAO
from utils.constants import (
    APPT_APPROVAL, APPT_WEEKLY, AUDIT_APPROVED, AUDIT_CANCELLED, AUDIT_COMPLETED,
    AUDIT_NO_SHOW, AUDIT_PENDING, AUDIT_REJECTED, CREDIT_NO_SHOW_PENALTY,
    DEVICE_REPAIR, DEVICE_SCRAPPED, ROLE_LAB_ADMIN, ROLE_SUPER_ADMIN,
    STAGE_ADMIN, STAGE_TUTOR, USER_ACTIVE,
)
from utils.time_util import parse_dt, to_db_str

_ADMIN_ROLES = (ROLE_LAB_ADMIN, ROLE_SUPER_ADMIN)


class AppointmentController:
    """预约业务控制器 —— 系统核心模块。"""

    def __init__(self, db_path: str | None = None) -> None:
        self.dao = AppointmentDAO(db_path)
        self.device_dao = DeviceDAO(db_path)
        self.user_dao = UserDAO(db_path)
        self.credit_dao = CreditLogDAO(db_path)
        self.msg = MessageController(db_path)
        self.log = LogController(db_path)
        self.waitlist = WaitlistController(db_path)
        self.setting = SettingController(db_path)
        self.iot = IoTController(db_path)

    # ---------- 内部校验 ----------
    def _validate_booking(self, uid: int, did: int, start_time: datetime,
                          end_time: datetime, exclude_aid: int | None = None) -> tuple:
        """提交预约的公共校验。返回 (是否通过, 消息, 设备或 None)。"""
        now = datetime.now()
        if start_time >= end_time:
            return False, "结束时间必须晚于开始时间", None
        if start_time < now:
            return False, "不可预约过去时间", None
        hours = (end_time - start_time).total_seconds() / 3600
        max_hours = self.setting.get_int("max_booking_hours", MAX_BOOKING_HOURS)
        if hours > max_hours:
            return False, f"单次预约时长不可超过 {max_hours} 小时", None

        device = self.device_dao.get_by_id(did)
        if not device:
            return False, "设备不存在", None
        if device["status"] in (DEVICE_REPAIR, DEVICE_SCRAPPED):
            return False, "设备当前不可预约（维修/报废）", None

        user = self.user_dao.get_by_id(uid)
        if not user:
            return False, "用户不存在", None
        if user["status"] != USER_ACTIVE:
            return False, "账号已被禁用（黑名单），无法预约", None
        min_credit = self.setting.get_int("min_credit_score", MIN_CREDIT_SCORE)
        if (user["credit_score"] or 0) < min_credit:
            return False, f"信用分不足（当前 {user['credit_score']}，需 ≥ {min_credit}）", None

        total = device.get("total_count", 1) or 1
        overlap = self.dao.count_overlap(did, to_db_str(start_time),
                                         to_db_str(end_time), exclude_aid)
        if overlap >= total:
            return False, (f"该时段已约满（可约 {total} 台，已占用 {overlap} 台），"
                           "可加入候补队列"), None
        return True, "", device

    # ---------- 提交预约 ----------
    def submit_appointment(self, uid: int, did: int, start_time: datetime,
                           end_time: datetime, appointment_type: str = "instant",
                           tutor_uid: int | None = None) -> tuple:
        """提交预约申请。返回 (是否成功, 消息)。"""
        ok, msg, _ = self._validate_booking(uid, did, start_time, end_time)
        if not ok:
            return False, msg
        stage = STAGE_TUTOR if appointment_type in (APPT_APPROVAL, APPT_WEEKLY) and tutor_uid \
            else STAGE_ADMIN
        aid = self.dao.insert(uid, did, to_db_str(start_time), to_db_str(end_time),
                              appointment_type, tutor_uid, stage)
        self.log.record(uid, f"提交预约申请 {aid}（{appointment_type}）")
        return True, "预约申请已提交，等待审核"

    def submit_weekly(self, uid: int, did: int, start_time: datetime,
                      end_time: datetime, weeks: int = 4,
                      tutor_uid: int | None = None) -> tuple:
        """周期性预约：为未来 weeks 周生成每周同一天的预约单。返回 (是否成功, 消息)。"""
        if weeks < 1 or weeks > 12:
            return False, "周期周数需在 1~12 之间"
        group = uuid.uuid4().hex
        duration = end_time - start_time
        for i in range(weeks):
            s = start_time + timedelta(weeks=i)
            e = s + duration
            ok, msg, _ = self._validate_booking(uid, did, s, e)
            if not ok:
                return False, f"第 {i + 1} 周冲突：{msg}"
        stage = STAGE_TUTOR if tutor_uid else STAGE_ADMIN
        for i in range(weeks):
            s = start_time + timedelta(weeks=i)
            e = s + duration
            self.dao.insert(uid, did, to_db_str(s), to_db_str(e), APPT_WEEKLY,
                            tutor_uid, stage, group)
        self.log.record(uid, f"提交周期性预约 {weeks} 周（{group[:8]}…）")
        return True, f"已提交 {weeks} 周的周期性预约"

    # ---------- 审核 ----------
    def audit(self, aid: int, audit_status: int, audit_msg: str,
              operator: dict) -> tuple:
        """管理员审核通过 / 驳回。审批预约需导师先通过。"""
        r = self.dao.get_by_id(aid)
        if not r:
            return False, "预约单不存在"
        if r["audit_status"] != AUDIT_PENDING:
            return False, "仅「待审核」的预约可审核"
        if audit_status == AUDIT_APPROVED and r["approve_stage"] != STAGE_ADMIN:
            return False, "该预约需导师先审核"
        if audit_status == AUDIT_REJECTED and not audit_msg.strip():
            return False, "驳回必须填写理由"

        if audit_status == AUDIT_APPROVED:
            device = self.device_dao.get_by_id(r["did"])
            total = (device.get("total_count", 1) or 1) if device else 1
            overlap = self.dao.count_overlap(r["did"], r["start_time"],
                                             r["end_time"], exclude_aid=aid)
            if overlap >= total:
                return False, "审核时该时段已约满，请先处理冲突预约"

        self.dao.update_audit(aid, audit_status, audit_msg.strip())
        self.msg.send_message(r["uid"], "预约审核结果",
                              f"预约单 {aid} 已「{'通过' if audit_status == AUDIT_APPROVED else '驳回'}」"
                              + (f"：{audit_msg.strip()}" if audit_msg.strip() else ""))
        self.log.record(operator.get("uid"), f"审核预约单 {aid}")
        return True, "审核完成"

    def tutor_audit(self, aid: int, approved: bool, audit_msg: str,
                    tutor: dict) -> tuple:
        """导师一级审核：通过进入管理员审核，驳回直接结束。"""
        r = self.dao.get_by_id(aid)
        if not r:
            return False, "预约单不存在"
        if r["audit_status"] != AUDIT_PENDING:
            return False, "仅「待审核」的预约可审核"
        if r["approve_stage"] != STAGE_TUTOR:
            return False, "当前不在导师审核环节"
        if not approved:
            if not audit_msg.strip():
                return False, "驳回必须填写理由"
            self.dao.update_audit(aid, AUDIT_REJECTED, audit_msg.strip())
        else:
            self.dao.execute("UPDATE appointment SET approve_stage = ? WHERE aid = ?",
                             (STAGE_ADMIN, aid))
        self.msg.send_message(r["uid"], "导师审核结果",
                              f"预约单 {aid} 导师已「{'通过' if approved else '驳回'}」")
        self.log.record(tutor.get("uid"), f"导师审核预约单 {aid}")
        return True, "导师审核完成"

    # ---------- 取消 ----------
    def cancel(self, aid: int, operator: dict) -> tuple:
        """取消预约。本人或管理员可取消；通过后取消触发候补转正。"""
        r = self.dao.get_by_id(aid)
        if not r:
            return False, "预约单不存在"
        if r["audit_status"] not in (AUDIT_PENDING, AUDIT_APPROVED):
            return False, "当前状态不可取消"
        is_owner = r["uid"] == operator.get("uid")
        is_admin = operator.get("role") in _ADMIN_ROLES
        if not (is_owner or is_admin):
            return False, "只能取消本人预约"

        if r["audit_status"] == AUDIT_APPROVED:
            st = parse_dt(r["start_time"])
            if st and (st - datetime.now()).total_seconds() < CANCEL_DEADLINE_MINUTES * 60:
                return False, f"距开始不足 {CANCEL_DEADLINE_MINUTES} 分钟，不可取消"

        self.dao.update_status(aid, AUDIT_CANCELLED)
        self.dao.execute("UPDATE appointment SET cancel_time = datetime('now', 'localtime') "
                         "WHERE aid = ?", (aid,))
        self.log.record(operator.get("uid"), f"取消预约单 {aid}")
        self.waitlist.promote_first(r["did"], r["start_time"], r["end_time"])
        return True, "预约已取消"

    # ---------- 使用登记（爽约判定 + 信用分） ----------
    def _release_hardware(self, did: int) -> None:
        """释放设备硬件：电源断电、门禁复位。"""
        dev = self.device_dao.get_by_id(did)
        if not dev:
            return
        self.iot.set_power(did, False)
        if dev.get("lab_id"):
            self.iot.set_door(dev["lab_id"], False)

    def mark_completed(self, aid: int, operator: dict) -> tuple:
        """标记已完成的预约。"""
        r = self.dao.get_by_id(aid)
        if not r:
            return False, "预约单不存在"
        if r["audit_status"] != AUDIT_APPROVED:
            return False, "仅「已通过」的预约可标记完成"
        self.dao.update_status(aid, AUDIT_COMPLETED)
        self._release_hardware(r["did"])
        self.log.record(operator.get("uid"), f"标记预约单 {aid} 完成")
        return True, "已标记完成"

    def mark_no_show(self, aid: int, operator: dict) -> tuple:
        """标记爽约：爽约次数 +1、扣信用分，达到阈值则禁用账号（加入黑名单）。"""
        r = self.dao.get_by_id(aid)
        if not r:
            return False, "预约单不存在"
        if r["audit_status"] != AUDIT_APPROVED:
            return False, "仅「已通过」的预约可标记爽约"
        self.dao.update_status(aid, AUDIT_NO_SHOW)
        self._release_hardware(r["did"])

        user = self.user_dao.get_by_id(r["uid"])
        new_count = (user["blacklist_count"] or 0) + 1
        self.user_dao.set_blacklist_count(r["uid"], new_count)

        new_credit = max(0, (user["credit_score"] or 0) - CREDIT_NO_SHOW_PENALTY)
        self.user_dao.set_credit_score(r["uid"], new_credit)
        self.credit_dao.insert(r["uid"], -CREDIT_NO_SHOW_PENALTY, f"爽约扣分（预约单 {aid}）")

        threshold = self.setting.get_int("blacklist_threshold", BLACKLIST_THRESHOLD)
        parts = [f"已标记爽约，累计 {new_count} 次，信用分 {new_credit}"]
        if new_count >= threshold:
            self.user_dao.set_status(r["uid"], 0)  # 禁用
            self.msg.send_message(r["uid"], "账号禁用",
                                  "累计爽约达到阈值，账号已被禁用（加入黑名单）。")
            parts.append("，账号已加入黑名单")
        tip = "".join(parts)
        self.log.record(operator.get("uid"), f"标记预约单 {aid} 爽约")
        return True, tip

    # ---------- 查询 ----------
    def get_by_id(self, aid: int) -> dict | None:
        return self.dao.get_by_id(aid)

    def list_by_user(self, uid: int) -> list:
        return self.dao.list_by_user(uid)

    def list_by_status(self, audit_status: int) -> list:
        return self.dao.list_by_status(audit_status)

    def list_by_stage(self, approve_stage: int) -> list:
        return self.dao.query_all(
            "SELECT a.*, d.dev_name, d.dev_no, u.real_name, u.username "
            "FROM appointment a JOIN device d ON a.did = d.did "
            "JOIN user u ON a.uid = u.uid WHERE a.approve_stage = ? "
            "AND a.audit_status = 0 ORDER BY a.aid DESC", (approve_stage,))

    def list_by_tutor(self, tutor_uid: int) -> list:
        return self.dao.query_all(
            "SELECT a.*, d.dev_name, d.dev_no, u.real_name, u.username "
            "FROM appointment a JOIN device d ON a.did = d.did "
            "JOIN user u ON a.uid = u.uid WHERE a.tutor_uid = ? "
            "ORDER BY a.aid DESC", (tutor_uid,))

    def list_all(self) -> list:
        return self.dao.list_all()

    def available_count(self, did: int, start_time: datetime, end_time: datetime) -> int:
        """某设备在目标时段剩余可预约数量（总数 - 已重叠占用数）。"""
        device = self.device_dao.get_by_id(did)
        total = (device.get("total_count", 1) or 1) if device else 1
        overlap = self.dao.count_overlap(did, to_db_str(start_time), to_db_str(end_time))
        return max(0, total - overlap)

    def auto_release_expired(self) -> int:
        """自动把已过结束时间的「已通过」预约置为完成，并释放硬件。返回处理数量。"""
        rows = self.dao.query_all(
            "SELECT aid, did FROM appointment WHERE audit_status = ? AND end_time < ?",
            (AUDIT_APPROVED, to_db_str(datetime.now())))
        for r in rows:
            self.dao.update_status(r["aid"], AUDIT_COMPLETED)
            self._release_hardware(r["did"])
        if rows:
            self.log.record(None, f"自动释放 {len(rows)} 条已到期预约")
        return len(rows)
