# -*- coding: utf-8 -*-
"""
optimize_core.py — WorkBuddy 启动加速与存储瘦身核心引擎
功能：
1. 探测 WorkBuddy 内部存储膨胀（traces 轨迹、旧 logs 日志、插件列表）。
2. 安全备份 settings.json 配置文件。
3. 裁剪冗余内置重型插件（如微信支付、腾讯文档、PPT/Excel 插件等），显著加速冷启动。
4. 安全清空沉重的历史 traces（800MB+）与旧日志垃圾，解除磁盘 I/O 锁死。
5. 支持一键还原配置。
"""

import os
import shutil
import json
import time
import sqlite3
from typing import Dict, List, Tuple

WORKBUDDY_DIR = os.path.expanduser(r"~\.workbuddy")
SETTINGS_PATH = os.path.join(WORKBUDDY_DIR, "settings.json")
TRACES_DIR = os.path.join(WORKBUDDY_DIR, "traces")
LOGS_DIR = os.path.join(WORKBUDDY_DIR, "logs")
SHELL_SNAPSHOTS_DIR = os.path.join(WORKBUDDY_DIR, "shell-snapshots")
AUDIT_LOG_DIR = os.path.join(WORKBUDDY_DIR, "audit-log")
LOCAL_APPDATA_DIR = os.path.expandvars(r"%LOCALAPPDATA%\WorkBuddy")
WORKBUDDY_DB = os.path.join(WORKBUDDY_DIR, "workbuddy.db")
EDGE_SYNC_DB = os.path.join(WORKBUDDY_DIR, "edge-sync-mapping.db")

# 建议禁用的重型非必要插件（启动耗时大、容易拉起孤儿 Node 进程）
HEAVY_PLUGINS_TO_DISABLE = [
    "weixinpay@workbuddy-builtin",
    "tencent-docs-plugin@workbuddy-builtin",
    "sheetagent@workbuddy-builtin",
    "tencent-pptx@workbuddy-builtin",
    "tencent-docx@workbuddy-builtin",
    "long-manuscript-expert@experts",
]


def _get_dir_size_mb(path: str) -> float:
    """计算目录物理占用大小 (MB)"""
    if not os.path.exists(path):
        return 0.0
    total_bytes = 0
    for root, _, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total_bytes += os.path.getsize(fp)
            except OSError:
                pass
    return round(total_bytes / (1024 * 1024), 2)


def _get_local_appdata_junk_mb() -> float:
    """计算 LocalAppData 中的诊断压缩包与旧日志体积 (MB)"""
    if not os.path.exists(LOCAL_APPDATA_DIR):
        return 0.0
    total = 0
    try:
        for f in os.listdir(LOCAL_APPDATA_DIR):
            if f.endswith(".zip") and "workbuddy" in f.lower():
                fp = os.path.join(LOCAL_APPDATA_DIR, f)
                total += os.path.getsize(fp)
        logs_dir = os.path.join(LOCAL_APPDATA_DIR, "logs")
        if os.path.exists(logs_dir):
            for f in os.listdir(logs_dir):
                if f.endswith(".old.log") or f.endswith(".bak"):
                    fp = os.path.join(logs_dir, f)
                    total += os.path.getsize(fp)
    except OSError:
        pass
    return round(total / (1024 * 1024), 2)


def get_storage_stats() -> Dict:
    """获取 WorkBuddy 存储与插件状态概览（涵盖日志、快照与崩溃转储包）"""
    traces_mb = _get_dir_size_mb(TRACES_DIR)
    logs_mb = _get_dir_size_mb(LOGS_DIR)
    snapshots_mb = _get_dir_size_mb(SHELL_SNAPSHOTS_DIR)
    audit_mb = _get_dir_size_mb(AUDIT_LOG_DIR)
    local_junk_mb = _get_local_appdata_junk_mb()

    total_junk = round(traces_mb + logs_mb + snapshots_mb + audit_mb + local_junk_mb, 2)

    enabled_plugins = {}
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                enabled_plugins = data.get("enabledPlugins", {})
        except Exception:
            pass

    return {
        "workbuddy_exists": os.path.exists(WORKBUDDY_DIR),
        "traces_mb": traces_mb,
        "logs_mb": logs_mb,
        "snapshots_mb": snapshots_mb,
        "audit_mb": audit_mb,
        "local_junk_mb": local_junk_mb,
        "total_junk_mb": total_junk,
        "enabled_plugins": enabled_plugins,
    }


def backup_settings() -> str:
    """安全备份 settings.json"""
    if not os.path.exists(SETTINGS_PATH):
        raise FileNotFoundError(f"未找到配置文件: {SETTINGS_PATH}")
    
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(WORKBUDDY_DIR, f"settings.json.bak_{timestamp}")
    shutil.copy2(SETTINGS_PATH, backup_file)
    return backup_file


def optimize_plugins(disable_list: List[str] = None) -> Tuple[int, List[str]]:
    """
    精简裁剪内置重型插件
    :param disable_list: 要禁用的插件列表，默认采用 HEAVY_PLUGINS_TO_DISABLE
    :return: (被禁用的插件数量, 被禁用的插件名列表)
    """
    if disable_list is None:
        disable_list = HEAVY_PLUGINS_TO_DISABLE

    if not os.path.exists(SETTINGS_PATH):
        raise FileNotFoundError(f"未找到配置文件: {SETTINGS_PATH}")

    # 先做安全备份
    backup_settings()

    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    enabled_plugins = data.setdefault("enabledPlugins", {})
    disabled_names = []

    for plugin in disable_list:
        if enabled_plugins.get(plugin, False) is True:
            enabled_plugins[plugin] = False
            disabled_names.append(plugin)
        elif plugin not in enabled_plugins:
            # 显式置为 false，防止默认拉起
            enabled_plugins[plugin] = False
            disabled_names.append(plugin)

    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return len(disabled_names), disabled_names


def purge_traces() -> float:
    """清空 traces 追踪日志目录（消除 800MB 磁盘扫描拖累）"""
    if not os.path.exists(TRACES_DIR):
        return 0.0

    before_mb = _get_dir_size_mb(TRACES_DIR)
    for item in os.listdir(TRACES_DIR):
        item_path = os.path.join(TRACES_DIR, item)
        try:
            if os.path.isdir(item_path):
                shutil.rmtree(item_path, ignore_errors=True)
            else:
                os.remove(item_path)
        except OSError:
            pass

    after_mb = _get_dir_size_mb(TRACES_DIR)
    return round(before_mb - after_mb, 2)


def purge_old_logs(keep_today: bool = True) -> float:
    """清理历史过期日志与沙盒沉淀日志"""
    if not os.path.exists(LOGS_DIR):
        return 0.0

    before_mb = _get_dir_size_mb(LOGS_DIR)
    today_str = time.strftime("%Y-%m-%d")

    for item in os.listdir(LOGS_DIR):
        item_path = os.path.join(LOGS_DIR, item)
        if os.path.isdir(item_path):
            # 保留今天的日志目录，清理历史日期目录与过大沙盒日志
            if keep_today and item == today_str:
                continue
            if item.startswith("202") or item in ("sandbox", "Crash-Log"):
                try:
                    shutil.rmtree(item_path, ignore_errors=True)
                except OSError:
                    pass
        elif os.path.isfile(item_path) and item.endswith(".log"):
            # 清理过大的诊断历史日志（如 mcp-apps-diag.log 超过 5MB 的）
            try:
                if os.path.getsize(item_path) > 5 * 1024 * 1024:
                    with open(item_path, "w", encoding="utf-8") as f:
                        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Log truncated by Agent Cleaner\n")
            except OSError:
                pass

    after_mb = _get_dir_size_mb(LOGS_DIR)
    return round(before_mb - after_mb, 2)


def purge_shell_snapshots() -> Tuple[int, float]:
    """清空命令历史快照缓存目录 (shell-snapshots)"""
    if not os.path.exists(SHELL_SNAPSHOTS_DIR):
        return 0, 0.0

    before_mb = _get_dir_size_mb(SHELL_SNAPSHOTS_DIR)
    count = 0
    for item in os.listdir(SHELL_SNAPSHOTS_DIR):
        fp = os.path.join(SHELL_SNAPSHOTS_DIR, item)
        try:
            if os.path.isfile(fp):
                os.remove(fp)
                count += 1
            elif os.path.isdir(fp):
                shutil.rmtree(fp, ignore_errors=True)
                count += 1
        except OSError:
            pass

    after_mb = _get_dir_size_mb(SHELL_SNAPSHOTS_DIR)
    return count, round(max(0.0, before_mb - after_mb), 2)


def purge_audit_logs() -> Tuple[int, float]:
    """清理历史审计日志 (audit-log)"""
    if not os.path.exists(AUDIT_LOG_DIR):
        return 0, 0.0

    before_mb = _get_dir_size_mb(AUDIT_LOG_DIR)
    count = 0
    for item in os.listdir(AUDIT_LOG_DIR):
        fp = os.path.join(AUDIT_LOG_DIR, item)
        try:
            if os.path.isfile(fp):
                os.remove(fp)
                count += 1
            elif os.path.isdir(fp):
                shutil.rmtree(fp, ignore_errors=True)
                count += 1
        except OSError:
            pass

    after_mb = _get_dir_size_mb(AUDIT_LOG_DIR)
    return count, round(max(0.0, before_mb - after_mb), 2)


def purge_local_appdata_logs() -> float:
    """清理 LocalAppData 中的崩溃转储 zip 包与旧日志备份"""
    if not os.path.exists(LOCAL_APPDATA_DIR):
        return 0.0

    freed_bytes = 0
    # 1. 根目录的诊断与崩溃压缩包
    try:
        for f in os.listdir(LOCAL_APPDATA_DIR):
            if f.endswith(".zip") and "workbuddy" in f.lower():
                fp = os.path.join(LOCAL_APPDATA_DIR, f)
                try:
                    size = os.path.getsize(fp)
                    os.remove(fp)
                    freed_bytes += size
                except OSError:
                    pass
    except OSError:
        pass

    # 2. logs 目录下的 .old.log 轮转旧日志
    logs_dir = os.path.join(LOCAL_APPDATA_DIR, "logs")
    if os.path.exists(logs_dir):
        try:
            for f in os.listdir(logs_dir):
                if f.endswith(".old.log") or f.endswith(".bak"):
                    fp = os.path.join(logs_dir, f)
                    try:
                        size = os.path.getsize(fp)
                        os.remove(fp)
                        freed_bytes += size
                    except OSError:
                        pass
        except OSError:
            pass

    return round(freed_bytes / (1024 * 1024), 2)


def vacuum_databases() -> float:
    """对 WorkBuddy 的核心 SQLite 数据库执行 VACUUM 碎片整理与 WAL 合并"""
    freed_bytes = 0
    db_paths = [WORKBUDDY_DB, EDGE_SYNC_DB]
    for db_path in db_paths:
        if not os.path.exists(db_path):
            continue
        try:
            size_before = os.path.getsize(db_path)
            wal_path = db_path + "-wal"
            wal_size_before = os.path.getsize(wal_path) if os.path.exists(wal_path) else 0

            conn = sqlite3.connect(db_path, timeout=2.0)
            cur = conn.cursor()
            # 1. 将 WAL 预写日志合并回主数据库
            cur.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            # 2. 执行 VACUUM 回收被删除数据占用的碎片空洞并重排索引
            cur.execute("VACUUM;")
            conn.close()

            size_after = os.path.getsize(db_path)
            wal_size_after = os.path.getsize(wal_path) if os.path.exists(wal_path) else 0
            freed_bytes += max(0, (size_before + wal_size_before) - (size_after + wal_size_after))
        except Exception:
            pass

    return round(freed_bytes / (1024 * 1024), 2)


def run_full_purge_and_optimize() -> Dict:
    """一键执行完整排毒瘦身与启动优化（涵盖插件裁剪、traces/日志清理、快照清理与数据库整理）"""
    stats_before = get_storage_stats()
    backup_file = backup_settings()

    # 1. 裁剪重型插件
    count, disabled = optimize_plugins()

    # 2. 清理 traces
    traces_freed = purge_traces()

    # 3. 清理旧日志
    logs_freed = purge_old_logs()

    # 4. 清理 shell-snapshots 快照
    snap_count, snap_freed = purge_shell_snapshots()

    # 5. 清理 audit-log 审计流水
    audit_count, audit_freed = purge_audit_logs()

    # 6. 清理 LocalAppData 中的崩溃 zip 与 old.log
    local_freed = purge_local_appdata_logs()

    # 7. 数据库碎片整理与压缩
    db_freed = vacuum_databases()

    total_freed = round(traces_freed + logs_freed + snap_freed + audit_freed + local_freed + db_freed, 2)
    stats_after = get_storage_stats()

    return {
        "backup_file": backup_file,
        "disabled_plugins": disabled,
        "traces_freed_mb": traces_freed,
        "logs_freed_mb": logs_freed,
        "snapshots_freed_mb": snap_freed,
        "snapshots_count": snap_count,
        "audit_freed_mb": audit_freed,
        "audit_count": audit_count,
        "local_freed_mb": local_freed,
        "db_freed_mb": db_freed,
        "total_freed_mb": total_freed,
        "remaining_junk_mb": stats_after["total_junk_mb"],
    }


if __name__ == "__main__":
    print("=" * 60)
    print("WorkBuddy 启动加速与排毒瘦身引擎 (MVP 思路一全功能)")
    print("=" * 60)
    res = run_full_purge_and_optimize()
    print(f"安全备份完成: {res['backup_file']}")
    print(f"成功裁剪插件: {len(res['disabled_plugins'])} 个 ({', '.join(res['disabled_plugins'])})")
    print(f"释放 traces 空间: {res['traces_freed_mb']} MB")
    print(f"释放 logs 空间: {res['logs_freed_mb']} MB")
    print(f"释放快照空间: {res['snapshots_freed_mb']} MB ({res['snapshots_count']} 个快照)")
    print(f"释放审计流水: {res['audit_freed_mb']} MB ({res['audit_count']} 个审计文件)")
    print(f"释放 LocalAppData 崩溃与旧日志: {res['local_freed_mb']} MB")
    print(f"数据库 VACUUM 释放: {res['db_freed_mb']} MB")
    print(f"[*] 累计释放磁盘空间: {res['total_freed_mb']} MB")
    print("=" * 60)

