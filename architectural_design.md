# Faster-WorkBuddy 核心架构设计与工程免疫指南 (architectural_design.md)

> **文档定位**：记录 Faster-WorkBuddy (kill_rogue_agents) 核心架构选型、设计模式（ADR）以及在恶劣物理环境下的工程防坑免疫方案。  
> **核心原则**：不写易碎的温室逻辑，把“死线宪法”与“原子操作”焊进软件骨架。

---

## 目录
1. [ADR-001：配置持久化之原子写入架构 (Atomic Write)](#adr-001配置持久化之原子写入架构-atomic-write)
2. [ADR-002：多维特征指纹与 Windows 设备防御架构](#adr-002多维特征指纹与-windows-设备防御架构)
3. [ADR-003：双层增量对账自愈架构 (Incremental Diff)](#adr-003双层增量对账自愈架构-incremental-diff)

---

## ADR-001：配置持久化之原子写入架构 (Atomic Write)

### 1. 痛点背景：为什么传统写入是“自杀式代码”？

在常规 Python 教程与初级代码中，保存配置文件通常使用如下写法：

```python
# ❌ 工业级禁忌：极度危险的直接覆写
with open("config.json", "w", encoding="utf-8") as f:
    json.dump(config_data, f)
```

这种看似简单的写法，在真实操作系统的物理世界中隐藏着**致命暗雷**：

```
操作时序:
[1. open(..., 'w')] ──────► 操作系统立即执行 Truncate (文件直接被抹成 0 字节！)
                             │
                             ▼ (若在这一瞬间发生突发断电 / 强杀 / 磁盘满)
[2. json.dump(...)] ──────► 💥 灾难发生：新内容未写完，原配置永久灰飞烟灭！
                             │
                             ▼
[3. 操作系统页缓存] ──────► 数据只停留在内存 Cache 中，尚未物理刻入硬盘磁道
```

* **原理解析**：
  1. `open(..., 'w')` 触发底层截断调用，在硬盘文件分配表（MFT / Inode）中把文件大小**立刻置零**；
  2. 哪怕随后的 `json.dump` 耗时只有几毫秒，只要在这期间电脑突然**死机、断电、蓝屏、或进程被任务管理器强制杀除**，硬盘上就只剩下一个 **0 字节的空白废纸**；
  3. 下次开机启动时，软件读取到一个空的 JSON 文件，直接触发 `json.JSONDecodeError`，导致**主界面当场闪退或白屏崩溃**。

---

### 2. 解决方案：影子空间原子写入四步法（贴海报模式）

为了彻底杜绝此类灾难，系统必须遵循**“永远不在原数据上直接动刀，先在影子空间雕刻完整，确认无误后瞬态切换”**的原子写入原则。

```mermaid
flowchart TD
    A["触发 save_config(data)"] --> B["【步骤 1: 影子草稿】<br>创建同级临时文件 .config.json.PID_NS.tmp<br>原 config.json 毫发无损"]
    B --> C["【步骤 2: 强制物理刷盘 (os.fsync)】<br>穿透操作系统页缓存，确保数据物理刻盘"]
    C --> D["【步骤 3: 备份底牌】<br>保留一份 config.json.bak 历史副本"]
    D --> E["【步骤 4: 瞬态指针切换 (os.replace)】<br>文件系统级别原子重命名，覆盖原文件"]
    E --> F["落盘成功，0 字节风险归零"]
    
    B -.->|若发生异常| G["【回滚清理】<br>安全删除未写完的 .tmp 草稿<br>原配置 100% 毫发无损"]
```

#### 核心代码实现解析 (落地于 clean_core.py)

```python
def save_config(config_data):
    """
    保存配置数据至外部或本地 config.json：
    【原子写入设计 (Atomic Write)】
    先写入同级临时文件并强制刷盘 (fsync)，再通过 os.replace 原子覆盖，
    彻底消除写盘中途断电/强杀导致原配置被截断为 0 字节的灾难性隐患。
    """
    config_file = get_config_path()
    config_dir = os.path.dirname(os.path.abspath(config_file))
    
    # 1. 创建带 PID 与纳秒时间戳的同级隐藏临时文件（防止多进程写入冲突）
    temp_file = os.path.join(
        config_dir, 
        f".{os.path.basename(config_file)}.{os.getpid()}_{time.time_ns()}.tmp"
    )
    
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
            f.flush()
            # 2. 强制物理刷盘：强令 OS 必须立即将页缓存刷入物理扇区，不可推迟
            os.fsync(f.fileno())

        # 3. 自动留存一份 .bak 有效备份底牌
        bak_file = f"{config_file}.bak"
        if os.path.exists(config_file):
            try:
                shutil.copy2(config_file, bak_file)
            except OSError:
                pass

        # 4. 原子重命名覆盖：微秒级门牌号指针切换（NTFS / ext4 文件系统不可分割操作）
        os.replace(temp_file, config_file)
        
    except Exception:
        # 若中途遭遇任何破坏崩溃，清理残破草稿，原文件安然无恙
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except OSError:
                pass
        raise
```

---

### 3. 破坏测试与物理宇宙不变量验证

在恶劣破坏场景下，该架构能够经受住物理宇宙**四大死线**的拷问：

| 突发物理灾难 | 原代码表现 | 原子写入架构表现 | 死线判定 |
| :--- | :--- | :--- | :---: |
| **在步骤 1（写临时文件）时突然拔掉电源** | 产生 0 字节空文件，软件报废 | 只有无辜的 `.tmp` 草稿损坏，原 `config.json` 碰都没被碰过，旧配置 100% 完整 | **守恒律通过** |
| **在步骤 2（fsync 刷盘）时系统死机** | 数据留在易失内存中，重启后消失 | 数据要么已完全刻盘，要么停留在草稿状态，原文件安全 | **守恒律通过** |
| **在步骤 4（os.replace）执行那一微秒断电** | 不适用 | 文件系统以原子事务切换指针：要么新配置成功生效，要么依旧指向旧配置，**绝对不存在“中间半截状态”** | **幂等与时间律通过** |
| **10 个并发线程同时发起写入踩踏** | 产生文件写锁冲突、脏写乱序崩溃 | 每个线程各写各的带独立纳秒戳的 `.tmp`，最后瞬态替换，配置永远是合法完整 JSON | **纯净律通过** |

---

## ADR-002：多维特征指纹与 Windows 设备防御架构

### 1. 痛点：Windows 幽灵设备保留名误判
在 Windows 系统历史遗留设计中，`CON`、`PRN`、`AUX`、`NUL`、`COM1~COM9`、`LPT1~LPT9` 是虚拟字符设备保留名。
* **暗雷现象**：无论当前目录下存不存在该文件，Python 执行 `os.path.exists("CON")` **永远返回 True**！
* **致命后果**：如果配置规则中误填或被注入了 `"detect_paths": ["CON"]`，探测器会误以为该 Agent 已安装在系统上，造成误判上架。

### 2. 解决方案：DOS 设备黑名单 + 物理属性双重门禁
在 `check_agent_installed()` 中建立严密的防御门禁：
1. **黑名单过滤**：提取 `os.path.basename`，一旦命中系统保留设备名，直接拒绝跳过；
2. **物理文件/目录校验**：严格要求 `os.path.isfile(path) or os.path.isdir(path)` 必须为真。由于 Windows 虚拟设备既不是普通文件也不是普通目录，幽灵设备被彻底斩草除根。

### 3. 增强：通配符嗅探 (Globbing) 与 MSIX 微软商店沙盒包族适配
* **痛点**：微软应用商店应用（如官方 ChatGPT 桌面端）安装在受保护的 `WindowsApps`，数据存储在 `%LOCALAPPDATA%\Packages\<包族名>\` 下（如 `OpenAI.Codex_2p2nqsd0c76g0`）。其目录往往带有动态哈希或版本号，固定死路径会导致开机自愈误以为未安装而下架。
* **架构升级**：
  1. 在 `check_agent_installed()` 中集成通配符嗅探（`glob.glob`），支持 `%LOCALAPPDATA%\Packages\OpenAI.Codex_*` 与 `*ChatGPT*`；
  2. 防御性过滤剥离通配符（如 `CON*`、`PRN?`），确保保留设备名变体依然 100% 无法穿透；
  3. 经过自动化破坏性沙箱测试（TC-1.4）全面验证，确保 0 Panic、0 误杀、0 穿透。

---

## ADR-003：双层增量对账自愈架构 (Incremental Diff)

### 1. 架构目标
彻底解耦“内置预置模板库（`preset_catalog`）”与“用户活跃卡片监控列表（`targets`）”。

### 2. 运转机理
1. **查新装（自动扩容）**：开机遍历预置库，若发现磁盘上新装了某个 Agent（如检测到 `dsh` 存在）且当前不在活跃列表中，**0.5 毫秒内自动上架激活**；
2. **查卸载（自动下架）**：遍历活跃列表，若发现已彻底卸载（所有探测路径均物理消失），自动下架清理卡片；
3. **保护自定义（用户资产神圣不可侵犯）**：用户手动添加的自定义目标（无预置 `detect_paths`）受到守恒律铁律保护，对账引擎**绝对不执行自动下架**，确保用户配置永不丢失。
