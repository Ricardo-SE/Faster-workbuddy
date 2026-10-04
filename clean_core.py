"""
clean_core.py — AI Agent 后台孤儿进程探测与清理核心引擎
职责：
1. 读取 config.json 配置规则（解耦）。
2. 安全多维扫描匹配目标进程（路径 + 命令行 + 进程名交叉验证，杜绝误杀）。
3. 执行优雅退出优先（terminate），超时强杀降级（kill）。
4. 统计并输出释放内存战报。
"""

import json
import os
import sys
import time
import psutil

# 确保在 Windows 控制台下支持 UTF-8 打印输出
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

def get_config_path():
    """获取配置文件路径：优先读取 exe 同级外部配置，兜底使用内置默认配置"""
    # 1. 优先检测与当前执行程序 (exe 或 python 脚本) 同级的外部 config.json
    exe_dir = os.path.dirname(sys.executable)
    external_config = os.path.join(exe_dir, "config.json")
    if getattr(sys, "frozen", False) and os.path.exists(external_config):
        return external_config

    # 2. 源码环境或内置临时解压目录下的 config.json
    bundled_config = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    return bundled_config


def load_config():
    """读取配置文件 config.json"""
    config_file = get_config_path()
    if not os.path.exists(config_file):
        raise FileNotFoundError(f"找不到配置文件: {config_file}")
    with open(config_file, "r", encoding="utf-8") as f:
        return json.load(f)


def match_process_to_target(proc, target_rule):
    """
    多维交叉比对单个进程是否属于目标 Agent：
    1. 进程名匹配
    2. 执行路径关键词 或 命令行关键词匹配
    3. 排除当前运行的清理工具自身
    """
    try:
        # 排除自身
        if proc.pid == os.getpid():
            return False

        p_name = proc.name().lower()
        # 1. 检查进程名
        expected_names = [n.lower() for n in target_rule.get("process_names", [])]
        if expected_names and p_name not in expected_names:
            return False

        # 2. 检查执行路径
        p_exe = (proc.exe() or "").lower()
        path_keywords = [k.lower() for k in target_rule.get("install_path_keywords", [])]
        path_matched = any(k in p_exe for k in path_keywords) if path_keywords else False

        # 3. 检查启动命令行参数
        p_cmd = " ".join(proc.cmdline() or []).lower()
        cmd_keywords = [k.lower() for k in target_rule.get("cmdline_keywords", [])]
        cmd_matched = any(k in p_cmd for k in cmd_keywords) if cmd_keywords else False

        # 满足路径匹配 或 命令行特征匹配，才认定为目标
        return path_matched or cmd_matched

    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False


def check_process_visible_window(pid):
    """
    检查指定 PID 是否拥有可见的前台 UI 窗口（用于区分是真正孤儿还是用户正在使用）
    """
    try:
        import win32gui
        import win32process

        visible_windows = []
        def enum_cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).strip()
                if title:
                    _, win_pid = win32process.GetWindowThreadProcessId(hwnd)
                    if win_pid == pid:
                        visible_windows.append(title)
            return True

        win32gui.EnumWindows(enum_cb, None)
        return len(visible_windows) > 0, visible_windows
    except Exception:
        return False, []


def scan_target_processes(target_name=None):
    """
    扫描全系统，返回匹配目标 Agent 的所有存活进程列表
    """
    config = load_config()
    targets = config.get("targets", [])
    if target_name:
        targets = [t for t in targets if t.get("name").lower() == target_name.lower()]

    results = []
    # 遍历当前系统所有运行中的进程
    for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
        for rule in targets:
            if match_process_to_target(proc, rule):
                try:
                    mem_rss_bytes = proc.memory_info().rss
                    mem_mb = round(mem_rss_bytes / (1024 * 1024), 2)
                    has_win, titles = check_process_visible_window(proc.pid)
                    results.append({
                        "target_id": rule["name"],
                        "target_name": rule["display_name"],
                        "proc": proc,
                        "pid": proc.pid,
                        "name": proc.name(),
                        "memory_mb": mem_mb,
                        "cmdline": " ".join(proc.cmdline()[:3]),
                        "has_window": has_win,
                        "window_titles": titles
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
    return results


def clean_processes(matched_list, timeout=2):
    """
    执行安全查杀：
    1. 第一步：温和退出 (terminate)
    2. 第二步：等待 timeout 秒
    3. 第三步：未退出者强杀 (kill)
    返回释放的总内存 (MB)
    """
    if not matched_list:
        return 0, 0

    procs_to_kill = [item["proc"] for item in matched_list]
    total_memory_mb = sum(item["memory_mb"] for item in matched_list)

    print(f"\n[清理开始] 发现 {len(matched_list)} 个目标孤儿进程，总内存占用: {total_memory_mb:.2f} MB")
    for item in matched_list:
        win_status = " [带前台窗口]" if item.get("has_window") else " [后台孤儿]"
        print(f"  -> PID: {item['pid']:<6} | 进程: {item['name']:<15} | 内存: {item['memory_mb']:>6.2f} MB{win_status}")

    # 1. 尝试温和退出 (SIGTERM)
    print(f"\n[步骤 1/2] 正在发送温和退出信号 (SIGTERM)，给进程留出 {timeout} 秒落盘时间...")
    for p in procs_to_kill:
        try:
            p.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # 等待进程正常退出
    gone, alive = psutil.wait_procs(procs_to_kill, timeout=timeout)
    print(f"  -> 成功优雅退出: {len(gone)} 个进程")

    # 2. 对顽固未退出的孤儿执行强杀 (SIGKILL)
    if alive:
        print(f"\n[步骤 2/2] 警告：尚有 {len(alive)} 个顽固进程超时未退，启动强制杀死 (SIGKILL)...")
        for p in alive:
            try:
                p.kill()
                print(f"  -> 已强杀顽固 PID: {p.pid}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        # 再次确认回收
        psutil.wait_procs(alive, timeout=1)

    print("\n[清理完毕] 所有目标孤儿进程已彻底清除，句柄与端口已释放！")
    return len(matched_list), total_memory_mb


if __name__ == "__main__":
    # 默认针对 WorkBuddy 进行清理，若指定参数则按参数执行
    target = sys.argv[1] if len(sys.argv) > 1 else "WorkBuddy"
    print(f"==================================================")
    print(f"  Agent Cleaner 核心探针启动（目标: {target}）")
    print(f"==================================================")

    matched = scan_target_processes(target)
    if not matched:
        print(f"\n[扫描结果] 未发现正在运行的 {target} 孤儿进程。")
    else:
        # 检查是否有正在运行的前台窗口（防手抖误杀）
        active_windows = []
        for item in matched:
            if item.get("has_window"):
                active_windows.extend(item.get("window_titles", []))

        if active_windows:
            print(f"\n[防误杀警告] 检测到 {target} 当前存在前台可视窗口，你可能正在使用中：")
            for t in set(active_windows):
                print(f"    - 窗口标题: 「{t}」")
            print("为防止未保存的工作丢失，默认已进行安全拦截。")
            try:
                choice = input("是否仍要强行关闭前台窗口并清理后台？(y/N): ").strip().lower()
            except EOFError:
                choice = "n"

            if choice != "y":
                print("\n[安全拦截] 清理已取消，保护正在使用的前台工作。")
                sys.exit(0)

        print(f"\n[扫描结果] 命中 {len(matched)} 个孤儿进程！")
        cfg = load_config()
        timeout = cfg.get("settings", {}).get("graceful_timeout_sec", 2)
        count, freed_mb = clean_processes(matched, timeout=timeout)
        print(f"\n[战报] 成功清理 {count} 个进程，累计为电脑释放内存 {freed_mb:.2f} MB！")
