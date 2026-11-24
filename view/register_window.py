# -*- coding: utf-8 -*-
"""注册窗口：学生自助注册。"""

from PyQt6.QtWidgets import (
    QFormLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from controller.user_controller import UserController
from view.widgets import info, warn


class RegisterWindow(QWidget):
    """注册新账号（默认学生角色）。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("注册新账号")
        self.setFixedSize(360, 300)
        self.user_ctrl = UserController()

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.username = QLineEdit()
        self.real_name = QLineEdit()
        self.password = QLineEdit()
        self.confirm = QLineEdit()
        self.phone = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm.setEchoMode(QLineEdit.EchoMode.Password)

        form.addRow("用户名：", self.username)
        form.addRow("真实姓名：", self.real_name)
        form.addRow("密码：", self.password)
        form.addRow("确认密码：", self.confirm)
        form.addRow("手机号：", self.phone)
        layout.addLayout(form)

        reg_btn = QPushButton("注册")
        reg_btn.clicked.connect(self._register)
        layout.addWidget(reg_btn)

    def _register(self) -> None:
        if self.password.text() != self.confirm.text():
            warn("两次输入的密码不一致")
            return
        ok, msg = self.user_ctrl.register(
            self.username.text(), self.password.text(),
            self.real_name.text(), self.phone.text())
        if ok:
            info("注册成功，请返回登录")
            self.close()
        else:
            warn(msg)
