# 受限流程：可运行的源码与启动器

本项目仍是 WeCom Join Helper。原 `run_app.pyw`、原 GUI 和发布过的旧安装器不变。
本页的新入口只运行仓库自带的 form / report 示例，不接管现有企微、网页、账号或公司业务。
源码 ZIP **不是便携 EXE，不是安装器**；文件示例、两自有网页、原 GUI 分层交付。

## 1. 最小可运行入口（仅 Python 标准库）

需要已有 Python 3.12 或以上。先在解压目录检查：

```powershell
python -B -m wecom_rusher.workflow_start --check
python -B -m wecom_rusher.workflow_start --example form --workspace .runtime/demo-form
python -B -m wecom_rusher.workflow_start --example report --workspace .runtime/demo-report
```

Windows 可用 `./workflow.cmd` 替代 `python -B -m wecom_rusher.workflow_start`。
启动器以自身目录定位模块和示例；相对 workspace/cancel-file 也相对于该目录。
如果 `python` 不在 PATH，可仅在当前终端设置 `$env:WORKFLOW_PYTHON` 为可信 python.exe，
或直接使用该解释器执行模块；不需要更改系统 PATH。
`--help` 显示选项，缺 workspace 会报错且不执行；`--check` 不创建工作目录、不启动浏览器。

只选择 `--example form|report`、`--mode file|dom`。没有 URL、selector、shell、eval、
已有窗口或任意插件参数。需要编辑受限 JSON 的开发者可继续使用原 `workflow_cli`，
其 schema 和六种动作边界不变。

## 2. 自有 DOM：显式的可复现依赖

只支持 Windows；检查器要求 Node >=20、固定 Playwright 1.56.1、已有 Chrome 可执行文件。
这是一组保守的受支持工具链条件，不是声称上游只支持这些版本。
Node 默认从 PATH 查找；Playwright 默认定位本项目 `tools/workflow/node_modules/playwright`；
Chrome 默认定位 Program Files 下标准安装位置。不存在开发机私人路径或 Edge 项目的依赖。

在本项目内安装可选 Node 包（不安装浏览器、不执行依赖安装脚本、不改全局环境/配置）：

```powershell
npm ci --prefix tools/workflow --cache .runtime/npm-cache --ignore-scripts --no-audit --no-fund
python -B -m wecom_rusher.workflow_start --mode dom --check
python -B -m wecom_rusher.workflow_start --mode dom --example form --workspace .runtime/dom-form
python -B -m wecom_rusher.workflow_start --mode dom --example report --workspace .runtime/dom-report
```

默认路径不适用时，使用 `--node <可信node.exe>`、`--playwright <可信包目录>`、
`--browser <已安装Chrome.exe>`；这些是工具链绑定，不是网页/脚本输入。
检查器验证 Python/Node/Playwright 版本及固定 API，浏览器只检查文件存在；
**ready 不证明浏览器能启动、能附着、能保存或下载**，这些由实际运行单独验证。
本批执行的版本及完整命令保存在私有维护证据，不将某台机器的 Chrome 版本当通用保证。

DOM 始终有头，覆盖继承的 headless 设置；只创建新的隔离 profile、随机 loopback 服务和
CDP 端口。用父进程持有的 Windows Job 约束自有后代，退出后读回 PID/创建时间、已记录端口和
临时 profile 清理状态。不会连接个人 profile、已有浏览器端口、第三方网站或硬件。
若依赖不齐，返回 `dependency_not_ready` 和固定补齐说明，未创建工作目录。
路径要短：Windows/Chrome 会继续追加 hash 和 profile 文件名，不要使用网络盘或深层目录。

## 3. 产物、错误和不可盲重放

每个目录形如 `<workspace>/<SHA256(示例runId)>/`。文件示例 runId 是 `fixture-form-v1` /
`fixture-report-v1`，DOM 是 `owned-form-example` / `owned-report-example`；以自带 JSON 为准。

- `artifacts/records.json`：文件 form 产物；report 为 `artifacts/export.csv`。
- DOM form：`artifacts/app-records.json`，包括真实应用 receipt 和 input-event 计数。
- DOM report：真实浏览器下载 `artifacts/export.csv`；服务端独立保存 `app-export.csv` 和
  `app-exports.json`，可比对字节、SHA-256、instanceId 和 receipt。
- DOM `owned-dom/cleanup.json`：真实清理读回。`verified=false` 不能解释成成功。
- `audit.jsonl`：只记固定状态码/ordinal/action/run hash，不记业务值或原始异常。
  应用产物和截图不是脱敏审计，不要直接公开 workspace。

截图只作诊断，不是应用提交收据。D-MAINT-2 修复候选在已观察到应用回执/下载、
并复核页面身份后，将截图自身的 `TimeoutError` 记录为固定
`diagnostic_screenshot_timeout` 事件，再次校验页面身份；不再仅因此返回 unknown。
截图超时时 `final.png` 可能缺失或仍是上一步画面，不能用它证明保存完成。
非超时错误、身份变化、回执丢失、执行超时或取消不被此处理吞掉。
范围、实测与尚未获得的独立审查见 [DOM 可靠性记录](workflow-dom-reliability.md)。

CLI 状态/退出码：completed=0；rejected/failed=2；timed_out=3；unknown=4；cancelled=130。
`invalid_workflow` 为格式/边界拒绝，`run_already_reserved` 为已有持久预留，
`input_io_error` 为输入读取失败，`cleanup_failed` 为资源清理未证实。
依赖检查成功不是流程 completed；审计末行也不是最终返回值。

Ctrl+C 或 `--cancel-file <自有停止标记>` 可取消；只检查标记是否存在，不读其内容。
运行后必须保存预留目录，同一示例同一 workspace 会拒绝重放。
unknown 表示某次写入已派发但缺确定确认；先核对已有 records/receipt/下载，
**不要删预留、换 runId/workspace、重复点击或把杀进程当回滚**。
新的 workspace 只用于另一次明确独立演示，不用于恢复未知业务结果。

## 4. 原 GUI 与打包边界

原应用仍由 `run_app.pyw` 启动，需 `requirements.txt` 的 GUI/OCR/Windows 依赖。
文件/DOM 入口不导入这些桌面自动化依赖；不因使用新入口而安装它们。
原 GUI 不新增按钮：独立 CLI 已满足可用入口，避免改变原窗口行为。
本批 GUI 验证是安全的 fake 单测及入口/源码兼容检查，不运行真实企微。

`JoinHelper.spec` / `scripts/build_release.ps1` 是原 PyInstaller/OCR 打包链；原脚本会
全量 discover 测试，不应在包含未知私人物料的工作区直接运行。
新的白名单源码打包命令：

```powershell
python -B scripts/build_workflow_source.py --output .runtime/JoinHelper-Workflow-Source.zip
```

它只读固定文件清单，ZIP 内有逐文件 SHA-256 的 `SOURCE-MANIFEST.json`；
不递归扫描、不包含 .git/.runtime/node_modules、个人截图、配置或未知 release。
缺输入/目标已存在则拒绝，不覆盖旧候选。解压后仍需 Python；DOM 仍需外置 Node/Chrome 及
上述本地 npm 依赖。旧 v1.0.10 的 106 项/安装卸载不能算本次新证据。
当前批次的验证、独立审查、发布状态见 [维护计划](desktop-maintenance.md) 和本批 result.json。
