# 桌面开源工具｜维护计划

唯一项目：原 `wecom-join-helper`（MIT），不是新增简历项目或工业视觉系统。
本长期主对话负责桌面仓，原 D 对话只作历史参考，不并行写入。

| 批次 | 当前范围 | 验证与停止点 |
|---|---|---|
| D-MAINT-1 | 独立受限启动器、依赖检查、两种安全示例、白名单源码包；保留原 GUI | 真实文件产物及两自有网页保存/CSV、清理读回、聚焦独立审查；交付后停 |
| 后续维护（未启动） | 建议仅做独立工具链的冻结 EXE/安装器支持评估 | 需新授权；不自动新增业务适配或 RPA 平台 |

## D-MAINT-1 交付与边界

入口和依赖：[workflow-start.md](workflow-start.md)。原流程内核、DOM bridge、原 GUI/状态机不改。
本批新行为按纵向 RED→GREEN 保存原始命令与 ledger；原33项内核回归的历史设计不冒充新 TDD。
审查预算：一次独立聚焦主审，最多两轮范围修复及一次针对确认，不复审未变旧模块。

本批证据独占 `.runtime/desktop-maintenance-20261101/m1/`：基线、索引 hash、窄白名单、
真实命令/原始结果、TDD ledger、候选包与下载/收据、独立审查及最终 `result.json`。
本页不将候选的预期结果写成已执行事实；以最终 result.json 的状态和 hash 为准。

本次选源码/启动器候选，不强行改旧打包链。当前解释器缺 PyInstaller、OpenCV、
pyautogui、pywinauto、RapidOCR 和 winotify；未构建/验证新便携 EXE 或安装器。
可选 DOM 依赖隔离安装到本批自有证据目录；源码交付含公开 npm 锁文件，不含 node_modules 或浏览器。

不会运行全仓 hygiene/discover、扫描 `release-final-v1.0.9/` 或读取 `current-desktop.png`。
未修改 Edge、简历、公司 Java/Maven/全局 PATH；未操作真实企微、公司账号、已有浏览器或硬件。
旧源码预览 `workflow-mvp-20261101` 不等于包含新入口的新安装器。
本批是否公开发布及精确远端读回，只有最终 result.json 明确记载才成立；本页不声称已发布。
