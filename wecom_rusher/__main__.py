from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import Config
from .logging_utils import setup_file_logger
from .runner import build_rusher
from .ui import UIError, WeComUI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="非官方企业微信接龙辅助工具")
    parser.add_argument("--config", type=Path, required=True, help="JSON 配置文件")
    parser.add_argument("--once", action="store_true", help="只扫描一次后退出")
    parser.add_argument("--calibrate", action="store_true", help="保存校准截图，不执行点击")
    parser.add_argument(
        "--calibrate-hotkey",
        action="store_true",
        help="切回企业微信并等待 Ctrl+Alt+F8 后截图",
    )
    return parser


def setup_logging(path: Path) -> logging.Logger:
    return setup_file_logger(path, console=True)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = Config.from_json(args.config)
    except (OSError, ValueError) as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 2

    logger = setup_logging(config.log_path)
    if args.calibrate:
        try:
            path = WeComUI(config, logger).save_calibration_screenshot(
                wait_for_hotkey=args.calibrate_hotkey
            )
        except UIError as exc:
            logger.error("校准失败：%s", exc)
            return 2
        print(f"校准截图已保存：{path.resolve()}")
        print("请按 templates/README.md 检查四个模板，并保持 dry_run=true 验证。")
        return 0

    rusher = build_rusher(config, logger)
    if args.once:
        result = rusher.scan_once()
        logger.info("single scan result: %s", result)
        return 0 if result in {"submitted", "dry_run", "already_submitted", "not_found"} else 2
    rusher.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
