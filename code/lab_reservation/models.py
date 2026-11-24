# -*- coding: utf-8 -*-
"""数据模型定义。

本模块使用 dataclass + Enum 定义系统核心实体，
对应《软件需求规格说明书》6.1 节数据字典中的各表结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class Role(str, Enum):
    """用户角色（RBAC）。"""

    STUDENT = "学生"
    TEACHER = "教师"
    LAB_ADMIN = "实验室管理员"
    SYS_ADMIN = "系统管理员"


class EquipmentStatus(str, Enum):
    """设备状态机。"""

    AVAILABLE = "可用"
    IN_USE = "使用中"
    REPAIR = "维修"
    SCRAPPED = "报废"


class ReservationStatus(str, Enum):
    """预约单状态机。"""

    PENDING = "待审核"
    APPROVED = "已通过"
    REJECTED = "已驳回"
    CANCELLED = "已取消"
    COMPLETED = "已完成"


@dataclass
class User:
    """用户实体（对应 t_user 表）。"""

    user_id: str
    name: str
    sid: str                       # 学号 / 工号，作为登录账号
    role: Role
    password_hash: str             # 密码哈希（核心模块用 SHA-256，正式系统用 bcrypt）
    phone: str = ""
    email: str = ""
    dept: str = ""
    status: str = "正常"           # 正常 / 禁用


@dataclass
class Lab:
    """实验室实体（对应 t_lab 表）。"""

    lab_id: str
    name: str
    location: str = ""
    manager: str = ""


@dataclass
class Equipment:
    """设备实体（对应 t_equipment 表）。"""

    equip_id: str
    name: str
    category: str
    lab_id: str
    model: str = ""
    status: EquipmentStatus = EquipmentStatus.AVAILABLE
    buy_date: date | None = None
    remark: str = ""


@dataclass
class Reservation:
    """预约单实体（对应 t_reservation 表）。"""

    reserve_id: str
    user_id: str
    equip_id: str
    reserve_date: date
    time_slot: str                 # 形如 "08:00-10:00"
    purpose: str
    status: ReservationStatus = ReservationStatus.PENDING
    apply_time: datetime = field(default_factory=datetime.now)
    approver: str = ""
    approve_time: datetime | None = None
    opinion: str = ""              # 审核意见 / 驳回原因


@dataclass
class UsageRecord:
    """使用记录实体（对应 t_usage_record 表）。"""

    record_id: str
    reserve_id: str
    equip_id: str
    user_id: str
    sign_in_time: datetime | None = None
    sign_out_time: datetime | None = None
    return_status: str = "完好"

    @property
    def duration_minutes(self) -> int:
        """实际使用时长（分钟）。"""
        if self.sign_in_time and self.sign_out_time:
            return int((self.sign_out_time - self.sign_in_time).total_seconds() // 60)
        return 0
