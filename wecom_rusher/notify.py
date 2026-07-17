from __future__ import annotations

import logging


class Notifier:
    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)

    def notify(self, status: str, message: str) -> None:
        labels = {
            "submitted": "接龙提交成功",
            "dry_run": "接龙 dry-run",
            "already_submitted": "接龙已处理",
            "not_found": "未发现新接龙",
            "timeout": "接龙页面超时",
            "unsafe_state": "接龙状态无法确认",
            "unsafe_state_after_attempt": "接龙已停止且不会重试",
        }
        title = labels.get(status, "企业微信接龙助手")
        try:
            from winotify import Notification

            Notification(app_id="企业微信接龙助手", title=title, msg=message).show()
        except Exception:
            self.logger.info("notification %s: %s", status, message)
