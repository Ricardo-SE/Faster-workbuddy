# Faster-WorkBuddy (Agent Cleaner)

> 针对 WorkBuddy 客户端打开耗时长、冷启动迟缓，以及关闭窗口后长期在后台堆叠霸占物理内存的问题提供带外优化方案。

[![Platform Windows](https://img.shields.io/badge/Platform-Windows-0078D6.svg)](https://microsoft.com/windows)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![GUI CustomTkinter](https://img.shields.io/badge/GUI-CustomTkinter-blueviolet.svg)](https://github.com/TomSchimansky/CustomTkinter)
[![License MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[免安装版下载 (Releases)](../../releases) · [源码运行指南](#方式二clone-源码运行适合开发者) · [模块功能清单](#模块功能清单)

---

## 痛点与创作背景

你是否感觉打开 WorkBuddy 仿佛在运行一款 3A 大作？  
关闭了窗口，它仍然在后台静默运行，吃掉大量内存。

> “某天下午我开着多个 Agent 赶工，忙完后明明关闭了 WorkBuddy 窗口，但笔记本风扇仍然转个不停，整台电脑卡的像PPT...在那之后，我决定做这样的一个优化工具。”  
> —— 作者的真实遭遇

很多依赖 AI 编程辅助工具的开发者都曾遇到类似情况：明明任务已经完成、主界面也已点叉关闭，但由底层 Electron 衍生出的 `node.exe`、`editor_sdk.exe`、`OpenConsole.exe` 等子进程却沦为了孤儿进程，常年在后台静默驻留，霸占 1GB 至 2GB 以上的物理内存。日积月累下，本地数据目录堆积了成百上千个历史 Shell 快照与废弃调试 Traces，导致客户端冷启动从几秒拖慢至数十秒。

### 设计初衷
当宿主进程退出异常或前端界面假死时，客户端自身的垃圾回收与子进程退出机制往往无法自愈。本项目采用**带外管理（Out-of-Band）**的独立设计思路：作为一个完全解耦的外部轻量工具，在宿主之外独立监控系统状态，以安全、无感、零破坏性的方式接管进程清理与存储瘦身。

---

## 快速使用

### 方式一：免安装绿色版（推荐普通用户）

无需配置任何 Python 环境即可使用：

1. 前往本仓库右侧的 Releases 页面；
2. 下载最新发布的 `AgentCleaner.exe` 单文件便携版；
3. 双击直接运行，随开随用，不修改注册表与系统路径。

> 提示：建议将 `AgentCleaner.exe`（或源码目录中的 `run_gui.bat`）右键选择「发送到桌面快捷方式」，或直接右键「固定到任务栏」，日常使用点击即开。

---

### 方式二：Clone 源码运行（适合开发者）

确保本机已安装 Python 3.8 或更高版本：

1. 克隆仓库：
   ```bash
   git clone https://github.com/Ricardo-SE/Faster-workbuddy.git
   cd Faster-workbuddy
   ```

2. 一键启动：
   双击目录下的 `run_gui.bat` 脚本。  
   *自愈向导说明：首次运行时脚本会自动检测系统 Python 并检查依赖；若缺少 `customtkinter` 或 `psutil`，将自动调用 pip 安装并以无控制台黑框模式启动界面。*

3. 手动命令行启动（可选）：
   ```bash
   pip install -r requirements.txt
   python app_gui.py
   ```

---

## 模块功能清单

### 1. 孤儿进程精准清理内核 (clean_core)
- **多维指纹交叉校验**：联合可执行文件名、安装目录关键词与进程命令行参数进行三维匹配，杜绝误杀系统或其他开发者的正常 Node/Python 进程。
- **两阶段安全查杀**：优先向目标进程发送 `SIGTERM` 退出信号促使其正常释放资源；在设定超时（默认 2 秒）仍未退出时，再降级执行强制终止。
- **物理内存精确回收**：实时比对查杀前后目标进程占用的物理工作集（RSS），精准统计并反馈释放的内存容量。

### 2. 存储排毒与冷启动加速内核 (optimize_core)
- **临时快照与废弃日志清理**：一键清除长期积累的 `shell-snapshots` 历史命令快照、调试 Traces 轨迹与过大的崩溃转储包，解除本地磁盘 I/O 锁死。
- **SQLite 数据库碎片压实**：对核心数据库文件（`workbuddy.db` 等）执行 `PRAGMA wal_checkpoint(TRUNCATE)` 合并预写日志，并通过 `VACUUM` 整理数据页与索引碎片。
- **重型冗余插件裁剪**：支持在配置中禁用启动开销大、容易拉起额外 Node 进程的非核心内置插件，显著缩短客户端冷启动耗时。

### 3. 状态感知与交互控制台 (app_gui)
- **1 秒无感自动巡检**：底部集成物理开关，采用全系统进程单快照遍历机制，单次扫描耗时仅 10 至 20 毫秒，CPU 占用率低于 0.1%。
- **并发防重入安全锁**：引入多状态互斥机制，在执行清理或优化任务期间自动挂起自动巡检，杜绝后台线程争抢与雪崩。
- **现代化深色仪表盘**：基于 CustomTkinter 构建，提供直观的运行状态灯与实时任务战报。

---

## 安全与备份保障

1. **严格的数据安全边界**：本工具仅针对孤儿进程生命周期、临时快照缓存和数据库碎片进行处理，绝不修改、删除用户的真实历史会话与项目工程源码。
2. **全自动时间戳备份**：任何针对配置文件的修改操作，均会在 `.workbuddy` 目录下生成带有精确时间戳的 `.bak` 备份文件，确保可随时无损回滚。
3. **带外独立运行**：程序完全在本地离线运行，无需申请敏感系统特权，不包含任何网络上传逻辑。

---

## 后续演进规划

当前 v1.0 专版针对 WorkBuddy 进行了深度定制。后续版本将进一步将清理规则抽象为可插拔的 Adapter 适配器架构，逐步扩展支持 zcode, qoder, trae 等各类 AI 编程工具与常驻 Agent 的全生命周期管理。

---

## 开源许可证

本项目基于 [MIT License](LICENSE) 开源。
