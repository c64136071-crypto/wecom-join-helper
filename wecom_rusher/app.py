from __future__ import annotations

import json
import logging
import os
import queue
import sys
import threading
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tkinter import (
    BOTH,
    LEFT,
    RIGHT,
    X,
    Button,
    Frame,
    Label,
    StringVar,
    Tk,
    messagebox,
    simpledialog,
)

from .config import Config
from .paths import AppPaths
from .logging_utils import setup_file_logger
from .runner import build_rusher
from .settings import (
    activate_live_mode,
    mark_recognition_test_passed,
    needs_first_run,
    update_keyword,
)
from .smoke import run_smoke_test


STATUS_TEXT = {
    "starting": "正在启动",
    "first_run": "首次设置",
    "ready": "准备就绪",
    "testing": "正在测试识别",
    "waiting": "等待接龙",
    "rush_waiting": "高频监控中（11:00-12:00）",
    "not_found": "等待接龙",
    "dry_run": "测试识别成功，未执行提交",
    "submitted": "接龙成功，企微可能需要重新登录",
    "already_submitted": "本次接龙已经处理",
    "timeout": "未确认成功，已停止且不会重试",
    "unsafe_state": "界面状态异常，已停止且不会重试",
    "unsafe_state_after_attempt": "提交后状态异常，已停止且不会重试",
    "inactive_day": "今天不是下午茶日",
    "stopped": "已停止",
    "fatal_error": "程序发生错误，已停止",
}


def status_text(status: str) -> str:
    return STATUS_TEXT.get(status, status)


def save_title_keyword(path: Path, keyword: str) -> None:
    clean = keyword.strip()
    if not clean:
        raise ValueError("title keyword must not be empty")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["title_keyword"] = clean
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def resolve_application_paths(
    app_root: str | Path,
    *,
    local_app_data: str | Path | None = None,
) -> AppPaths:
    root = Path(app_root)
    return AppPaths.resolve(
        root,
        portable=(root / "portable.marker").exists(),
        local_app_data=local_app_data,
    )


def load_application_config(paths: AppPaths) -> Config:
    paths.ensure()
    config = Config.load_or_create(paths.config_path)
    return config.with_runtime_paths(
        templates_dir=paths.templates_dir,
        state_path=paths.state_path,
        log_path=paths.log_path,
    )


def config_for_worker(config: Config, *, test_mode: bool) -> Config:
    return replace(config, dry_run=True) if test_mode else config


def persist_application_config(path: Path, config: Config) -> None:
    config.write_json(path)


def setup_logging(path: Path) -> logging.Logger:
    return setup_file_logger(path)


class WeComRusherApp:
    def __init__(self, root: Tk, config: Config, logger: logging.Logger, paths: AppPaths):
        self.root = root
        self.config = config
        self.logger = logger
        self.paths = paths
        self.app_root = paths.app_root
        self.config_path = paths.config_path
        self.stop_event = threading.Event()
        self.status_queue: queue.Queue[str] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.worker_mode: str | None = None
        self.close_scheduled = False

        self.status_var = StringVar(value=status_text("starting"))
        self.time_var = StringVar(value="尚未扫描")
        self.detail_var = StringVar(value="请保持企业微信目标群窗口可见")
        self._build_window()
        if needs_first_run(self.config):
            self.status_var.set(status_text("first_run"))
            self.detail_var.set("打开目标群后，先进行无点击识别测试")
            self._configure_setup_controls()
        else:
            self.root.after(150, self._start_live)
        self.root.after(100, self._drain_status_queue)

    def _build_window(self) -> None:
        self.root.title("接龙助手")
        self.root.geometry("560x240")
        self.root.resizable(False, False)
        self.root.configure(bg="#f5f7f8")
        self.root.protocol("WM_DELETE_WINDOW", self._close)

        icon_path = self.app_root / "assets" / "wecom-rusher.ico"
        if icon_path.exists():
            try:
                self.root.iconbitmap(default=str(icon_path))
            except Exception:
                self.logger.debug("window icon could not be loaded", exc_info=True)

        header = Frame(self.root, bg="#1f6f54", height=54)
        header.pack(fill=X)
        Label(
            header,
            text="接龙助手",
            bg="#1f6f54",
            fg="white",
            font=("Microsoft YaHei UI", 14, "bold"),
            padx=18,
            pady=14,
        ).pack(side=LEFT)

        body = Frame(self.root, bg="#f5f7f8", padx=20, pady=18)
        body.pack(fill=BOTH, expand=True)
        Label(
            body,
            textvariable=self.status_var,
            bg="#f5f7f8",
            fg="#17252f",
            font=("Microsoft YaHei UI", 13, "bold"),
            anchor="w",
        ).pack(fill=X)
        Label(
            body,
            textvariable=self.detail_var,
            bg="#f5f7f8",
            fg="#53636d",
            font=("Microsoft YaHei UI", 9),
            anchor="w",
            pady=8,
        ).pack(fill=X)

        footer = Frame(body, bg="#f5f7f8")
        footer.pack(fill=X, side="bottom")
        Label(
            footer,
            textvariable=self.time_var,
            bg="#f5f7f8",
            fg="#71808a",
            font=("Microsoft YaHei UI", 9),
        ).pack(side=LEFT)
        self.stop_button = Button(
            footer,
            text="停止",
            command=self._request_stop,
            width=8,
            bg="#ffffff",
            fg="#25343d",
            relief="solid",
            borderwidth=1,
            font=("Microsoft YaHei UI", 9),
        )
        self.stop_button.pack(side=RIGHT)
        self.stop_button.configure(state="disabled")
        self.start_button = Button(
            footer,
            text="开始",
            command=self._start_live,
            width=11,
            bg="#1f6f54",
            fg="white",
            relief="flat",
            font=("Microsoft YaHei UI", 9),
        )
        self.start_button.pack(side=RIGHT, padx=(0, 8))
        self.test_button = Button(
            footer,
            text="测试识别",
            command=self._start_test,
            width=10,
            bg="#ffffff",
            fg="#1f6f54",
            relief="solid",
            borderwidth=1,
            font=("Microsoft YaHei UI", 9),
        )
        self.test_button.pack(side=RIGHT, padx=(0, 8))
        self.settings_button = Button(
            footer,
            text="设置关键词",
            command=self._edit_keyword,
            width=10,
            bg="#f5f7f8",
            fg="#1f6f54",
            relief="flat",
            font=("Microsoft YaHei UI", 9),
        )
        self.settings_button.pack(side=RIGHT, padx=(0, 10))

    def _configure_setup_controls(self) -> None:
        self.start_button.configure(
            text="启用正式模式",
            command=self._enable_live_mode,
            state="normal" if self.config.recognition_test_passed else "disabled",
        )
        self.test_button.configure(state="normal")
        self.stop_button.configure(state="disabled")

    def _configure_live_controls(self) -> None:
        self.start_button.configure(text="开始", command=self._start_live, state="normal")
        self.test_button.configure(state="normal")
        self.stop_button.configure(state="disabled")

    def _start_test(self) -> None:
        self._start_worker(test_mode=True)

    def _start_live(self) -> None:
        if needs_first_run(self.config):
            self._configure_setup_controls()
            return
        self._start_worker(test_mode=False)

    def _start_worker(self, *, test_mode: bool) -> None:
        if self.worker is not None and self.worker.is_alive():
            return
        self.stop_event = threading.Event()
        self.worker_mode = "test" if test_mode else "live"
        worker_config = config_for_worker(self.config, test_mode=test_mode)
        rusher = build_rusher(worker_config, self.logger)
        self.start_button.configure(state="disabled")
        self.test_button.configure(state="disabled")
        self.settings_button.configure(state="disabled")
        self.stop_button.configure(state="normal", text="停止", command=self._request_stop)
        if test_mode:
            self.status_var.set(status_text("testing"))
            self.detail_var.set("仅识别标题和接龙卡片，不发送鼠标输入")

        def run() -> None:
            try:
                rusher.run_forever(
                    stop_event=self.stop_event,
                    status_callback=self.status_queue.put,
                )
            except Exception:
                self.logger.exception("desktop runner failed")
                self.status_queue.put("fatal_error")
            finally:
                self.status_queue.put("worker_done")

        self.worker = threading.Thread(target=run, name="wecom-rusher", daemon=True)
        self.worker.start()

    def _drain_status_queue(self) -> None:
        try:
            while True:
                self._apply_status(self.status_queue.get_nowait())
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(100, self._drain_status_queue)

    def _apply_status(self, status: str) -> None:
        if status == "worker_done":
            self.worker = None
            self.stop_button.configure(state="disabled")
            self.settings_button.configure(state="normal")
            if self.worker_mode == "test" and self.config.recognition_test_passed:
                self._configure_setup_controls()
            elif not self.close_scheduled and not needs_first_run(self.config):
                self._configure_live_controls()
            self.worker_mode = None
            return
        self.status_var.set(status_text(status))
        self.time_var.set(f"最后更新：{datetime.now():%H:%M:%S}")
        if status == "rush_waiting":
            self.detail_var.set("正在高频检查固定群中的下午茶接龙")
        elif status in {"waiting", "not_found"}:
            self.detail_var.set("请保持企业微信目标群窗口可见")
        elif status == "dry_run":
            self.config = mark_recognition_test_passed(self.config)
            persist_application_config(self.config_path, self.config)
            self.detail_var.set("识别测试通过，可以启用正式模式")
            self._configure_setup_controls()
        elif status == "submitted":
            self.detail_var.set("本轮已停止；新接龙出现后可再次开始")
            self.stop_button.configure(state="disabled")
        elif status in {
            "timeout",
            "unsafe_state",
            "unsafe_state_after_attempt",
            "fatal_error",
        }:
            self.detail_var.set(f"日志：{self.config.log_path}")
            self.stop_button.configure(text="关闭", command=self._close)
        elif status == "inactive_day":
            self.detail_var.set("当前日期不在设置的运行范围内")
            if not self.close_scheduled:
                self.close_scheduled = True
                self.root.after(3000, self._close)

    def _request_stop(self) -> None:
        self.stop_event.set()
        self.status_var.set("正在停止")
        self.stop_button.configure(state="disabled")

    def _enable_live_mode(self) -> None:
        try:
            self.config = activate_live_mode(self.config)
            persist_application_config(self.config_path, self.config)
        except Exception as exc:
            messagebox.showerror("无法启用", str(exc), parent=self.root)
            return
        self.status_var.set(status_text("ready"))
        self.detail_var.set("正式模式已启用；点击开始或下次直接启动")
        self._configure_live_controls()

    def _edit_keyword(self) -> None:
        keyword = simpledialog.askstring(
            "设置接龙关键词",
            "只有标题包含该关键词的接龙才会处理：",
            initialvalue=self.config.title_keyword,
            parent=self.root,
        )
        if keyword is None:
            return
        try:
            self.config = update_keyword(self.config, keyword)
            persist_application_config(self.config_path, self.config)
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc), parent=self.root)
            return
        self.stop_event.set()
        self.status_var.set(status_text("first_run"))
        self.detail_var.set("关键词已更新，请重新进行识别测试")
        self._configure_setup_controls()

    def _close(self) -> None:
        self.stop_event.set()
        try:
            self.root.destroy()
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    app_root = application_root()
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "--smoke-test":
        if len(arguments) != 2:
            return 2
        try:
            run_smoke_test(app_root, result_path=arguments[1])
        except Exception:
            return 2
        return 0
    os.chdir(app_root)
    try:
        paths = resolve_application_paths(app_root)
        config = load_application_config(paths)
        logger = setup_logging(config.log_path)
    except Exception as exc:
        root = Tk()
        root.withdraw()
        messagebox.showerror("下午茶接龙助手", f"无法读取配置：\n{exc}")
        root.destroy()
        return 2

    root = Tk()
    WeComRusherApp(root, config, logger, paths)
    root.mainloop()
    return 0
