"""
app_gui.py — Agent Cleaner 现代化桌面仪表盘 (CustomTkinter GUI)
功能：
1. 动态读取 config.json 中的目标 Agent 规则与进程监控卡片。
2. 实时呈现各 Agent 状态卡片（醒目文字状态标签、进程数、物理内存占用、端口信息）。
3. 先藏后显（Withdraw & Deiconify）+ 屏幕居中，彻底消除窗口启动闪跳。
4. 多线程（threading）异步处理扫描与清理，保证界面 100% 丝滑不卡死。
"""

import os
import sys
import threading
import time
import customtkinter as ctk

# 导入底层核心清理引擎与优化引擎
from clean_core import scan_target_processes, clean_processes, load_config
from optimize_core import get_storage_stats, run_full_purge_and_optimize

# 设置全局外观主题：深色现代模式
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class AgentCleanerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # 窗口基本属性
        self.title("Agent Cleaner - 进程孤儿清理与启动加速")
        self.geometry("620x470")
        self.minsize(580, 380)

        # 状态映射字典与并发控制锁
        self.target_cards = {}
        self.is_scanning = False
        self.is_cleaning = False
        self.is_optimizing = False
        self.auto_refresh_job = None
        self._scan_counter = 0

        # 构建界面组件
        self._build_header()
        self._build_cards_container()
        self._build_footer()

        # 注册窗口关闭事件（安全销毁定时器）
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # 默认开启 1 秒自动刷新检测，并启动首次检测
        self.auto_switch.select()
        self.after(200, self.refresh_status_async)
        self.after(1200, self._auto_refresh_tick)

    def _build_header(self):
        """顶部标题区域"""
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=24, pady=(20, 10))

        title_label = ctk.CTkLabel(
            header_frame,
            text="⚡ Agent Cleaner",
            font=ctk.CTkFont(size=22, weight="bold")
        )
        title_label.pack(anchor="w")

        sub_label = ctk.CTkLabel(
            header_frame,
            text="AI Agent 进程孤儿清理 · 物理内存回收 · 窗口状态防误杀感知",
            font=ctk.CTkFont(size=12),
            text_color="#888888"
        )
        sub_label.pack(anchor="w")

    def _build_cards_container(self):
        """中间可滚动的卡片列表"""
        self.scroll_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True, padx=20, pady=10)

        # 1. 顶部：WorkBuddy 启动加速与排毒卡片
        self._create_optimizer_card()

        # 2. 中部：各 Agent 孤儿进程监控卡片
        config = load_config()
        targets = config.get("targets", [])

        for rule in targets:
            name = rule["name"]
            display_name = rule.get("display_name", name)
            ports = rule.get("ports", [])
            self._create_agent_card(name, display_name, ports)

    def _create_optimizer_card(self):
        """创建 WorkBuddy 启动加速与存储排毒卡片"""
        card = ctk.CTkFrame(self.scroll_frame, corner_radius=12, fg_color="#18232C")
        card.pack(fill="x", pady=8, padx=4)

        # 左侧：名称与醒目文字状态胶囊
        left_box = ctk.CTkFrame(card, fg_color="transparent")
        left_box.pack(side="left", padx=16, pady=14, fill="x", expand=True)

        title_box = ctk.CTkFrame(left_box, fg_color="transparent")
        title_box.pack(anchor="w", fill="x")

        # 标题
        name_label = ctk.CTkLabel(
            title_box,
            text="🚀 WorkBuddy 启动加速与排毒",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        name_label.pack(side="left", padx=(0, 12))

        # 状态胶囊标签
        self.opt_badge = ctk.CTkLabel(
            title_box,
            text="  正在探测  ",
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=6,
            fg_color="#333333",
            text_color="#AAAAAA"
        )
        self.opt_badge.pack(side="left")

        # 详细参数信息（垃圾体积、插件裁剪状态）
        self.opt_info = ctk.CTkLabel(
            left_box,
            text="正在检测 Traces 垃圾与插件加载状态...",
            font=ctk.CTkFont(size=13),
            text_color="#999999"
        )
        self.opt_info.pack(anchor="w", pady=(6, 0))

        # 右侧：一键加速按钮
        self.opt_btn = ctk.CTkButton(
            card,
            text="一键加速",
            width=96,
            height=34,
            corner_radius=8,
            fg_color="#E67E22",
            hover_color="#D35400",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.optimize_async
        )
        self.opt_btn.pack(side="right", padx=16)

    def _create_agent_card(self, target_name, display_name, ports):
        """创建单个 Agent 的仪表盘监控卡片"""
        card = ctk.CTkFrame(self.scroll_frame, corner_radius=12, fg_color="#1E1E1E")
        card.pack(fill="x", pady=8, padx=4)

        # 左侧：名称与醒目文字状态胶囊
        left_box = ctk.CTkFrame(card, fg_color="transparent")
        left_box.pack(side="left", padx=16, pady=14, fill="x", expand=True)

        title_box = ctk.CTkFrame(left_box, fg_color="transparent")
        title_box.pack(anchor="w", fill="x")

        # 软件名称
        name_label = ctk.CTkLabel(
            title_box,
            text=display_name,
            font=ctk.CTkFont(size=16, weight="bold")
        )
        name_label.pack(side="left", padx=(0, 12))

        # 醒目的文字状态胶囊标签（Pill Badge）
        badge_label = ctk.CTkLabel(
            title_box,
            text="  正在探测  ",
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=6,
            fg_color="#333333",
            text_color="#AAAAAA"
        )
        badge_label.pack(side="left")

        # 详细参数信息（内存占用、进程数量、监听端口）
        port_str = f" | 端口: {','.join(map(str, ports))}" if ports else ""
        info_label = ctk.CTkLabel(
            left_box,
            text=f"内存检测中...{port_str}",
            font=ctk.CTkFont(size=13),
            text_color="#999999"
        )
        info_label.pack(anchor="w", pady=(6, 0))

        # 右侧：专属清理按钮
        clean_btn = ctk.CTkButton(
            card,
            text="立即清理",
            width=96,
            height=34,
            corner_radius=8,
            fg_color="#1F6AA5",
            hover_color="#144870",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda t=target_name: self.clean_single_async(t)
        )
        clean_btn.pack(side="right", padx=16)

        # 登记卡片控件以便后续刷新更新文字与颜色
        self.target_cards[target_name] = {
            "badge": badge_label,
            "info": info_label,
            "btn": clean_btn,
            "ports": ports,
            "matched_data": []
        }

    def _build_footer(self):
        """底部控制栏与战报区域"""
        footer_frame = ctk.CTkFrame(self, fg_color="#181818", corner_radius=0)
        footer_frame.pack(fill="x", side="bottom")

        # 战报消息条
        self.banner_label = ctk.CTkLabel(
            footer_frame,
            text="状态就绪。系统已开启防误杀感知保护，点击「立即清理」释放内存。",
            font=ctk.CTkFont(size=12),
            text_color="#A0A0A0"
        )
        self.banner_label.pack(fill="x", padx=20, pady=(12, 6))

        # 底部按钮栏
        btn_box = ctk.CTkFrame(footer_frame, fg_color="transparent")
        btn_box.pack(fill="x", padx=20, pady=(6, 16))

        refresh_btn = ctk.CTkButton(
            btn_box,
            text="🔄 手动刷新",
            width=100,
            height=36,
            corner_radius=8,
            fg_color="#333333",
            hover_color="#444444",
            font=ctk.CTkFont(size=13),
            command=self.refresh_status_async
        )
        refresh_btn.pack(side="left", padx=(0, 14))

        # 自动刷新检测开关
        self.auto_switch = ctk.CTkSwitch(
            btn_box,
            text="自动刷新检测",
            font=ctk.CTkFont(size=13),
            command=self._on_toggle_auto_refresh
        )
        self.auto_switch.pack(side="left", padx=(0, 10))

        clean_all_btn = ctk.CTkButton(
            btn_box,
            text="⚡ 一键清理全部",
            width=140,
            height=36,
            corner_radius=8,
            fg_color="#D32F2F",
            hover_color="#9A0007",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.clean_all_async
        )
        clean_all_btn.pack(side="right")

    def _on_close(self):
        """窗口安全关闭钩子：取消定时器，防止残留回调引发异常"""
        if self.auto_refresh_job is not None:
            try:
                self.after_cancel(self.auto_refresh_job)
            except Exception:
                pass
        self.destroy()

    # ================= 自动与异步刷新逻辑（1秒巡检） =================

    def _on_toggle_auto_refresh(self):
        """用户切换「自动刷新检测」开关时的响应"""
        if self.auto_switch.get() == 1:
            self._update_banner("已开启自动刷新检测。")
            self._schedule_auto_refresh(200)
        else:
            self._update_banner("已停止自动刷新检测。")
            if self.auto_refresh_job is not None:
                try:
                    self.after_cancel(self.auto_refresh_job)
                except Exception:
                    pass
                self.auto_refresh_job = None

    def _schedule_auto_refresh(self, delay_ms=1000):
        """安全调度下一次自动刷新"""
        if self.auto_refresh_job is not None:
            try:
                self.after_cancel(self.auto_refresh_job)
            except Exception:
                pass
            self.auto_refresh_job = None

        if self.auto_switch.get() == 1:
            self.auto_refresh_job = self.after(delay_ms, self._auto_refresh_tick)

    def _auto_refresh_tick(self):
        """1秒定时器 Tick：防重入安全检查 + 触发静默扫描"""
        self.auto_refresh_job = None

        # 若开关已被用户关闭，立即停止循环
        if self.auto_switch.get() != 1:
            return

        # 互斥守卫：如果当前正在扫描、清理或优化，跳过本次但调度下一次
        if self.is_scanning or self.is_cleaning or self.is_optimizing:
            self._schedule_auto_refresh(1000)
            return

        # 启动后台工作线程执行轻量级单次快照扫描
        threading.Thread(target=self._worker_silent_scan, daemon=True).start()

    def _worker_silent_scan(self):
        """后台静默扫描：单次遍历系统进程树，不闪烁横幅，保护战报文字"""
        self.is_scanning = True
        self._scan_counter += 1
        try:
            # 1. 进程扫描：单循环一次性匹配全系统目标，极速无感
            all_matched = scan_target_processes(None)
            grouped = {k: [] for k in self.target_cards.keys()}
            for item in all_matched:
                tid = item.get("target_id")
                if tid in grouped:
                    grouped[tid].append(item)

            # 更新各卡片 UI
            for tid, matched in grouped.items():
                controls = self.target_cards.get(tid)
                if controls:
                    controls["matched_data"] = matched
                    self.after(0, self._update_card_ui, tid, matched)

            # 2. 存储与插件状态无需每秒读盘，每 10 次（10秒）周期性静默巡检一次
            if self._scan_counter % 10 == 0:
                self._worker_refresh_optimizer()

        except Exception:
            pass
        finally:
            self.is_scanning = False
            # 无论成功或异常，回到主线程调度下一个 1 秒 Tick
            self.after(0, lambda: self._schedule_auto_refresh(1000))

    def refresh_status_async(self):
        """用户点击「手动刷新」时的显式全量刷新"""
        if self.is_scanning or self.is_cleaning or self.is_optimizing:
            return
        threading.Thread(target=self._worker_refresh_status, daemon=True).start()

    def _worker_refresh_status(self):
        self.is_scanning = True
        self._update_banner("正在扫描全系统后台进程与存储健康状态...")
        try:
            # 1. 刷新启动优化卡片状态
            self._worker_refresh_optimizer()

            # 2. 单次高效遍历进程
            all_matched = scan_target_processes(None)
            grouped = {k: [] for k in self.target_cards.keys()}
            for item in all_matched:
                tid = item.get("target_id")
                if tid in grouped:
                    grouped[tid].append(item)

            for tid, matched in grouped.items():
                controls = self.target_cards.get(tid)
                if controls:
                    controls["matched_data"] = matched
                    self.after(0, self._update_card_ui, tid, matched)

            self._update_banner("就绪。Agent 状态与存储健康度已更新。")
        finally:
            self.is_scanning = False

    def _worker_refresh_optimizer(self):
        """后台探测 WorkBuddy 存储与插件状态"""
        try:
            stats = get_storage_stats()
            self.after(0, self._update_optimizer_display, stats)
        except Exception as e:
            self.after(0, self._update_optimizer_error, str(e))

    def _update_optimizer_display(self, stats):
        junk_mb = stats.get("total_junk_mb", 0.0)
        plugins = stats.get("enabled_plugins", {})
        disabled_count = sum(
            1 for k in (
                "weixinpay@workbuddy-builtin",
                "tencent-docs-plugin@workbuddy-builtin",
                "sheetagent@workbuddy-builtin",
                "tencent-pptx@workbuddy-builtin",
                "tencent-docx@workbuddy-builtin",
            )
            if plugins.get(k) is False
        )

        if junk_mb > 50.0 or disabled_count < 3:
            badge_text = "  建议优化  "
            badge_bg = "#3D3216"
            badge_fg = "#F1C40F"
            btn_text = "一键加速"
        else:
            badge_text = "  🟢 极速就绪  "
            badge_bg = "#1B3B2B"
            badge_fg = "#2ECC71"
            btn_text = "再次排毒"

        info_text = f"冗余日志与快照缓存: {junk_mb} MB | 已裁剪 {disabled_count} 个重型插件"
        self.opt_badge.configure(text=badge_text, fg_color=badge_bg, text_color=badge_fg)
        self.opt_info.configure(text=info_text)
        self.opt_btn.configure(state="normal", text=btn_text)

    def _update_optimizer_error(self, err_msg):
        self.opt_badge.configure(text="  未就绪  ", fg_color="#442222", text_color="#FF6B6B")
        self.opt_info.configure(text=f"检测异常: {err_msg[:45]}")

    def optimize_async(self):
        """异步执行 WorkBuddy 启动优化与排毒"""
        if self.is_optimizing:
            return
        threading.Thread(target=self._worker_optimize, daemon=True).start()

    def _worker_optimize(self):
        self.is_optimizing = True
        self.after(0, lambda: self.opt_btn.configure(state="disabled", text="优化中..."))
        self._update_banner("正在清理历史快照、旧日志与数据库碎片整理...")
        try:
            res = run_full_purge_and_optimize()
            self._worker_refresh_optimizer()
            snap_str = f"（含 {res.get('snapshots_count', 0)} 个历史快照）" if res.get('snapshots_count') else ""
            self._update_banner(f"🎉 优化完成！成功释放 {res['total_freed_mb']} MB 空间{snap_str}，数据库已整理压实！")
        except Exception as e:
            self._update_banner(f"❌ 启动优化失败: {e}")
        finally:
            self.is_optimizing = False
            self.after(0, lambda: self.opt_btn.configure(state="normal", text="再次排毒"))

    def _update_card_ui(self, target_name, matched):
        controls = self.target_cards.get(target_name)
        if not controls:
            return

        ports = controls.get("ports", [])
        port_str = f" | 端口: {','.join(map(str, ports))}" if ports else ""

        if not matched:
            # 状态 1：正常干净
            controls["badge"].configure(
                text="  🟢 正常  ",
                fg_color="#1E392A",
                text_color="#2ECC71"
            )
            controls["info"].configure(text=f"后台干净 · 无孤儿常驻 (0 MB){port_str}")
            controls["btn"].configure(state="disabled", text="无需清理", fg_color="#333333")
        else:
            total_mb = sum(m["memory_mb"] for m in matched)
            has_window = any(m.get("has_window") for m in matched)

            if has_window:
                # 状态 2：前台使用中（黄色警示）
                controls["badge"].configure(
                    text="  🟡 使用中  ",
                    fg_color="#3D3216",
                    text_color="#F1C40F"
                )
                controls["info"].configure(
                    text=f"前台窗口打开中 · 占用 {total_mb:.1f} MB ({len(matched)} 个进程){port_str}"
                )
                controls["btn"].configure(state="normal", text="强退清理", fg_color="#D32F2F", hover_color="#9A0007")
            else:
                # 状态 3：孤儿异常常驻（红色高危）
                controls["badge"].configure(
                    text="  🔴 异常常驻  ",
                    fg_color="#441E1E",
                    text_color="#FF4D4F"
                )
                controls["info"].configure(
                    text=f"孤儿在后台偷吃内存 · 占用 {total_mb:.1f} MB ({len(matched)} 个进程){port_str}"
                )
                controls["btn"].configure(state="normal", text="立即清理", fg_color="#1F6AA5", hover_color="#144870")

    def clean_single_async(self, target_name):
        """单卡片专项清理"""
        if self.is_cleaning:
            return
        threading.Thread(target=self._worker_clean, args=([target_name],), daemon=True).start()

    def clean_all_async(self):
        """一键清理全部 Agent"""
        if self.is_cleaning:
            return
        threading.Thread(target=self._worker_clean, args=(list(self.target_cards.keys()),), daemon=True).start()

    def _worker_clean(self, target_names):
        self.is_cleaning = True
        self._update_banner("正在执行优雅退出与内存回收，请稍候...")

        all_matched = []
        for name in target_names:
            matched = scan_target_processes(name)
            all_matched.extend(matched)

        if not all_matched:
            self._update_banner("未发现需要清理的孤儿进程。")
            self.is_cleaning = False
            return

        cfg = load_config()
        timeout = cfg.get("settings", {}).get("graceful_timeout_sec", 2)
        count, freed_mb = clean_processes(all_matched, timeout=timeout)

        # 战报输出
        msg = f"🎉 战报：成功清理 {count} 个孤儿进程，累计释放内存 {freed_mb:.2f} MB！"
        self._update_banner(msg)

        # 清理后自动重新探测刷新
        self._worker_refresh_status()
        self.is_cleaning = False

    def _update_banner(self, text):
        """安全更新底部消息条"""
        self.after(0, lambda: self.banner_label.configure(text=text))


if __name__ == "__main__":
    app = AgentCleanerApp()
    app.mainloop()
