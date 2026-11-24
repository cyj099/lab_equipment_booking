# -*- coding: utf-8 -*-
"""实验室设备预约系统 —— 核心模块演示入口。

运行方式：
    python main.py

演示一次完整的预约闭环：注册 → 录入设备 → 提交预约 → 审核通过
→ 签到 → 签退，并演示时段冲突检测。
"""

from datetime import date

from lab_reservation import (
    Equipment, EquipmentService, EquipmentStatus, Lab, ReservationService,
    Role, UserService,
)
from lab_reservation.exceptions import ConflictError
from lab_reservation.repositories import InMemoryRepository


def main() -> None:
    repo = InMemoryRepository()
    user_svc = UserService(repo)
    equip_svc = EquipmentService(repo)
    reserve_svc = ReservationService(repo)

    # 1. 注册用户
    student = user_svc.register("张三", "2022001", Role.STUDENT, "abc12345", phone="13800000000")
    admin = user_svc.register("王实验员", "T0001", Role.LAB_ADMIN, "admin123")

    # 2. 录入实验室与设备
    lab = Lab(lab_id="L01", name="网络实验室", location="N515")
    repo.add_lab(lab)
    equip_svc.add(Equipment("E01", "示波器", "电子测量", "L01", model="TBS1000"))
    equip_svc.add(Equipment("E02", "函数信号发生器", "电子测量", "L01", model="AFG1022"))

    print("=== 场景 1：正常预约闭环 ===")
    r = reserve_svc.submit(student, "E01", date(2026, 10, 20), "08:00-10:00", "课程实验")
    print(f"[提交] 预约单 {r.reserve_id} 状态={r.status.value}")
    r = reserve_svc.approve(r.reserve_id, admin)
    print(f"[审核] 预约单 {r.reserve_id} 状态={r.status.value}，审核人={admin.name}")
    rec = reserve_svc.sign_in(r.reserve_id, student)
    print(f"[签到] 使用记录 {rec.record_id}，设备状态={equip_svc.query()[0].status.value}")
    rec = reserve_svc.sign_out(r.reserve_id, student)
    print(f"[签退] 使用时长 {rec.duration_minutes} 分钟，预约状态={r.status.value}")

    print("\n=== 场景 2：时段冲突检测 ===")
    reserve_svc.submit(student, "E02", date(2026, 10, 20), "09:00-11:00", "调试")
    try:
        # 与 09:00-11:00 重叠，应抛出冲突
        reserve_svc.submit(student, "E02", date(2026, 10, 20), "10:00-12:00", "复测")
    except ConflictError as e:
        print(f"[冲突拦截] {e}")

    print("\n=== 场景 3：非可用设备不可预约 ===")
    equip_svc.change_status("E01", EquipmentStatus.REPAIR)
    try:
        reserve_svc.submit(student, "E01", date(2026, 10, 21), "08:00-10:00", "实验")
    except Exception as e:
        print(f"[校验拦截] {e}")

    print("\n演示结束，核心业务运行正常。")


if __name__ == "__main__":
    main()
