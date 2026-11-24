# -*- coding: utf-8 -*-
"""实验室设备预约系统 —— 交互式命令行入口（可登录测试）。

运行方式：
    python cli.py

提供登录 / 注册，并按角色（学生 / 教师 / 实验室管理员 / 系统管理员）展示不同菜单，
覆盖核心业务：设备查询、提交预约、审核、取消、签到、签退、设备台账管理。

说明：本入口在内存仓库上运行，关闭程序后数据不保留，适合功能测试演示。
"""

from __future__ import annotations

import sys
from datetime import date
from typing import List, Optional

from lab_reservation import (
    Equipment, EquipmentService, EquipmentStatus, Lab, Reservation,
    ReservationService, ReservationStatus, Role, User, UserService,
)
from lab_reservation.exceptions import ReservationError
from lab_reservation.repositories import InMemoryRepository


def _setup_console() -> None:
    """让 Windows 控制台按 UTF-8 读写中文，避免乱码。"""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


ROLE_CHOICES = {
    "1": Role.STUDENT,
    "2": Role.TEACHER,
    "3": Role.LAB_ADMIN,
    "4": Role.SYS_ADMIN,
}

_ADMIN_ROLES = (Role.LAB_ADMIN, Role.SYS_ADMIN)


def _read_slot_minutes(slot: str):
    """校验并解析 "HH:MM-HH:MM"，非法返回 None。"""
    try:
        start, end = slot.split("-")

        def _to_min(s: str) -> int:
            h, m = s.strip().split(":")
            return int(h) * 60 + int(m)

        s, e = _to_min(start), _to_min(end)
        if not (0 <= s < e <= 24 * 60):
            return None
        return s, e
    except Exception:
        return None


class ReservationApp:
    """交互式应用：持有仓库与服务，驱动登录与角色菜单。"""

    def __init__(self) -> None:
        self.repo = InMemoryRepository()
        self.user_svc = UserService(self.repo)
        self.equip_svc = EquipmentService(self.repo)
        self.reserve_svc = ReservationService(self.repo)
        self.current: Optional[User] = None
        self._seed()

    # ---------- 初始数据 ----------
    def _seed(self) -> None:
        self.user_svc.register("张三", "2022001", Role.STUDENT, "abc12345", phone="13800000000")
        self.user_svc.register("李四", "2022002", Role.STUDENT, "abc12345", phone="13900000000")
        self.user_svc.register("王实验员", "T0001", Role.LAB_ADMIN, "admin123")
        self.user_svc.register("系统管理员", "A0001", Role.SYS_ADMIN, "admin123")

        self.repo.add_lab(Lab("L01", "网络实验室", "N515"))
        self.repo.add_lab(Lab("L02", "电子测量实验室", "N516"))
        self.equip_svc.add(Equipment("E01", "示波器", "电子测量", "L01", model="TBS1000"))
        self.equip_svc.add(Equipment("E02", "函数信号发生器", "电子测量", "L01", model="AFG1022"))
        self.equip_svc.add(Equipment("E03", "逻辑分析仪", "数字电路", "L02", model="LA1032"))
        self.equip_svc.add(Equipment("E04", "数字万用表", "电子测量", "L02", model="DM3058"))

    # ---------- 输入辅助 ----------
    @staticmethod
    def _read_date() -> date:
        while True:
            raw = input("预约日期 (YYYY-MM-DD)：").strip()
            try:
                return date.fromisoformat(raw)
            except ValueError:
                print("  日期格式错误，请重试（例如 2026-10-20）")

    @staticmethod
    def _read_slot() -> str:
        while True:
            raw = input("预约时段 (HH:MM-HH:MM)：").strip()
            if _read_slot_minutes(raw) is None:
                print("  时段格式错误，请重试（例如 08:00-10:00，且结束需晚于开始）")
                continue
            return raw

    @staticmethod
    def _read_choice(prompt: str, choices: List[str]) -> str:
        while True:
            value = input(prompt).strip()
            if value in choices:
                return value
            print(f"  请输入 {'/'.join(choices)} 之一")

    # ---------- 登录 / 注册 ----------
    def _login(self) -> bool:
        print("\n=== 登录 ===")
        sid = input("学号/工号：").strip()
        password = input("密码：").strip()
        try:
            self.current = self.user_svc.login(sid, password)
        except ReservationError as e:
            print(f"  登录失败：{e}")
            return False
        print(f"\n欢迎，{self.current.name}（{self.current.role.value}）")
        return True

    def _register(self) -> bool:
        print("\n=== 注册新账号 ===")
        name = input("姓名：").strip()
        sid = input("学号/工号：").strip()
        password = input("密码（不少于 6 位）：").strip()
        phone = input("手机号（可空）：").strip()
        print("角色：1 学生 / 2 教师 / 3 实验室管理员 / 4 系统管理员")
        role = ROLE_CHOICES[self._read_choice("请选择角色：", list(ROLE_CHOICES))]
        try:
            self.current = self.user_svc.register(name, sid, role, password, phone=phone)
        except ReservationError as e:
            print(f"  注册失败：{e}")
            return False
        print(f"\n注册成功，已自动登录：{self.current.name}（{self.current.role.value}）")
        return True

    def _show_welcome(self) -> None:
        print("\n" + "=" * 40)
        print("       实验室设备预约系统")
        print("=" * 40)
        print("预置账号：")
        print("  学生   2022001 / abc12345")
        print("  学生   2022002 / abc12345")
        print("  管理员 T0001   / admin123")
        print("  管理员 A0001   / admin123")
        print("=" * 40)

    # ---------- 设备显示 ----------
    def _print_equipments(self, eqs: List[Equipment]) -> None:
        if not eqs:
            print("  （无设备）")
            return
        print(f"  {'编号':<6}{'名称':<14}{'类别':<10}{'实验室':<8}{'状态':<8}{'型号'}")
        for e in eqs:
            print(f"  {e.equip_id:<6}{e.name:<14}{e.category:<10}{e.lab_id:<8}"
                  f"{e.status.value:<8}{e.model}")

    def _print_reservations(self, rs: List[Reservation]) -> None:
        if not rs:
            print("  （无预约单）")
            return
        print(f"  {'单号':<7}{'设备':<6}{'日期':<12}{'时段':<14}{'用途':<12}{'状态'}")
        for r in rs:
            print(f"  {r.reserve_id:<7}{r.equip_id:<6}{str(r.reserve_date):<12}"
                  f"{r.time_slot:<14}{r.purpose:<12}{r.status.value}")

    # ---------- 学生 / 教师菜单 ----------
    def _menu_student(self) -> None:
        while True:
            print("\n--- 功能菜单 ---")
            print("1. 查看设备")
            print("2. 提交预约")
            print("3. 我的预约")
            print("4. 取消预约")
            print("5. 签到")
            print("6. 签退")
            print("0. 退出登录")
            choice = self._read_choice("请选择：", ["0", "1", "2", "3", "4", "5", "6"])
            if choice == "0":
                self.current = None
                return
            self._dispatch_student(choice)

    def _dispatch_student(self, choice: str) -> None:
        try:
            if choice == "1":
                self._print_equipments(self.equip_svc.query())
            elif choice == "2":
                self._do_submit()
            elif choice == "3":
                mine = [r for r in self.repo.list_reservations()
                        if r.user_id == self.current.user_id]
                self._print_reservations(mine)
            elif choice == "4":
                self._do_cancel()
            elif choice == "5":
                self._do_sign("in")
            elif choice == "6":
                self._do_sign("out")
        except ReservationError as e:
            print(f"  操作失败：{e}")

    # ---------- 管理员菜单 ----------
    def _menu_admin(self) -> None:
        while True:
            print("\n--- 管理员菜单 ---")
            print("1. 查看设备")
            print("2. 新增设备")
            print("3. 修改设备状态")
            print("4. 查看全部预约")
            print("5. 审核预约")
            print("0. 退出登录")
            choice = self._read_choice("请选择：", ["0", "1", "2", "3", "4", "5"])
            if choice == "0":
                self.current = None
                return
            self._dispatch_admin(choice)

    def _dispatch_admin(self, choice: str) -> None:
        try:
            if choice == "1":
                self._print_equipments(self.equip_svc.query())
            elif choice == "2":
                self._do_add_equipment()
            elif choice == "3":
                self._do_change_status()
            elif choice == "4":
                self._print_reservations(self.repo.list_reservations())
            elif choice == "5":
                self._do_audit()
        except ReservationError as e:
            print(f"  操作失败：{e}")

    # ---------- 具体业务 ----------
    def _do_submit(self) -> None:
        print("\n--- 提交预约 ---")
        self._print_equipments(self.equip_svc.query())
        equip_id = input("设备编号：").strip()
        d = self._read_date()
        slot = self._read_slot()
        purpose = input("预约用途：").strip()
        r = self.reserve_svc.submit(self.current, equip_id, d, slot, purpose)
        print(f"  预约成功，单号 {r.reserve_id}，状态：{r.status.value}")

    def _do_cancel(self) -> None:
        print("\n--- 取消预约 ---")
        if self.current.role in _ADMIN_ROLES:
            rs = [r for r in self.repo.list_reservations()
                  if r.status in (ReservationStatus.PENDING, ReservationStatus.APPROVED)]
        else:
            rs = [r for r in self.repo.list_reservations()
                  if r.user_id == self.current.user_id
                  and r.status in (ReservationStatus.PENDING, ReservationStatus.APPROVED)]
        self._print_reservations(rs)
        rid = input("要取消的预约单号：").strip()
        self.reserve_svc.cancel(rid, self.current)
        print(f"  预约单 {rid} 已取消")

    def _do_sign(self, action: str) -> None:
        label = "签到" if action == "in" else "签退"
        print(f"\n--- {label} ---")
        mine = [r for r in self.repo.list_reservations()
                if r.user_id == self.current.user_id]
        self._print_reservations(mine)
        rid = input("预约单号：").strip()
        rec = self.reserve_svc.sign_in(rid, self.current) if action == "in" \
            else self.reserve_svc.sign_out(rid, self.current)
        if action == "in":
            print(f"  签到成功，使用记录 {rec.record_id}，设备已置为「使用中」")
        else:
            print(f"  签退成功，使用时长 {rec.duration_minutes} 分钟，预约单已「已完成」")

    def _do_add_equipment(self) -> None:
        print("\n--- 新增设备 ---")
        equip_id = input("设备编号：").strip()
        name = input("设备名称：").strip()
        category = input("类别：").strip()
        lab_id = input("实验室编号：").strip()
        model = input("型号（可空）：").strip()
        eq = Equipment(equip_id, name, category, lab_id, model=model)
        self.equip_svc.add(eq)
        print(f"  设备 {equip_id} 已录入")

    def _do_change_status(self) -> None:
        print("\n--- 修改设备状态 ---")
        self._print_equipments(self.equip_svc.query())
        equip_id = input("设备编号：").strip()
        print("状态：1 可用 / 2 使用中 / 3 维修 / 4 报废")
        mapping = {
            "1": EquipmentStatus.AVAILABLE,
            "2": EquipmentStatus.IN_USE,
            "3": EquipmentStatus.REPAIR,
            "4": EquipmentStatus.SCRAPPED,
        }
        status = mapping[self._read_choice("请选择：", list(mapping))]
        self.equip_svc.change_status(equip_id, status)
        print(f"  设备 {equip_id} 状态已更新为「{status.value}」")

    def _do_audit(self) -> None:
        print("\n--- 审核预约 ---")
        pending = [r for r in self.repo.list_reservations()
                   if r.status == ReservationStatus.PENDING]
        if not pending:
            print("  （当前没有待审核的预约单）")
            return
        self._print_reservations(pending)
        rid = input("要审核的预约单号：").strip()
        decision = self._read_choice("1 通过 / 2 驳回：", ["1", "2"])
        if decision == "1":
            self.reserve_svc.approve(rid, self.current)
            print(f"  预约单 {rid} 已通过")
        else:
            reason = input("驳回原因：").strip()
            self.reserve_svc.reject(rid, self.current, reason)
            print(f"  预约单 {rid} 已驳回：{reason}")

    # ---------- 主循环 ----------
    def run(self) -> None:
        self._show_welcome()
        while True:
            try:
                print("\n1. 登录\n2. 注册新账号\n0. 退出系统")
                choice = self._read_choice("请选择：", ["0", "1", "2"])
                if choice == "0":
                    print("再见！")
                    return
                ok = self._login() if choice == "1" else self._register()
                if not ok:
                    continue
                if self.current.role in _ADMIN_ROLES:
                    self._menu_admin()
                else:
                    self._menu_student()
            except (EOFError, KeyboardInterrupt):
                print("\n再见！")
                return


def main() -> None:
    _setup_console()
    ReservationApp().run()


if __name__ == "__main__":
    main()
