# -*- coding: utf-8 -*-
"""公告通知控制器：发布公告并向全员推送站内消息。"""

from controller.message_controller import MessageController
from model.notice_model import NoticeDAO
from model.user_model import UserDAO


class NoticeController:
    """公告发布与查询。"""

    def __init__(self, db_path: str | None = None) -> None:
        self.dao = NoticeDAO(db_path)
        self.user_dao = UserDAO(db_path)
        self.msg = MessageController(db_path)

    def publish(self, title: str, content: str, publisher_uid: int) -> tuple:
        title = (title or "").strip()
        content = (content or "").strip()
        if not title or not content:
            return False, "公告标题和内容不能为空"
        self.dao.insert(title, content, publisher_uid)
        for u in self.user_dao.list_all():
            self.msg.send_message(u["uid"], "新公告", title)
        return True, "公告已发布"

    def list_notices(self) -> list:
        return self.dao.list_all()
