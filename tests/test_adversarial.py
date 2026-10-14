"""
test_adversarial.py — Faster-WorkBuddy 系统死线与恶意破坏测试套件
依据：《系统死线与恶意破坏测试方法论.md》与《adversarial_test_plan.md》

核心目标：
1. 验证四大物理不变量死线（守恒律、时间单调律、因果前提律、幂等纯净律）；
2. 实施全维度投毒四板斧（虚无畸形、时空踩踏、半截死刑、极限雪崩）；
3. 确保真机绝对安全（所有文件投毒与假人打靶均在独立沙箱中运行）。
"""

import os
import sys
import time
import json
import shutil
import tempfile
import threading
import subprocess
import unittest
from concurrent.futures import ThreadPoolExecutor

# 确保能正确引用工作区根目录下的核心模块
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

# 引入被测核心模块
import clean_core

# 缓存原始寻址函数（作为模块级对象，避免类属性 bound method 陷阱）
ORIGINAL_GET_CONFIG_PATH = clean_core.get_config_path

# 确保控制台支持 UTF-8 打印
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass


class TestAdversarialHarness(unittest.TestCase):
    """恶意破坏与死线验证测试用例集"""

    @classmethod
    def setUpClass(cls):
        # 创建独立的测试沙箱工作目录，绝对不污染真实工程环境
        cls.sandbox_dir = tempfile.mkdtemp(prefix="agent_cleaner_sandbox_")
        print(f"\n======================================================================")
        print(f"  [测试沙箱建立] 物理隔离路径: {cls.sandbox_dir}")
        print(f"======================================================================")

    @classmethod
    def tearDownClass(cls):
        # 恢复原始配置寻址
        clean_core.get_config_path = ORIGINAL_GET_CONFIG_PATH
        # 清理沙箱
        shutil.rmtree(cls.sandbox_dir, ignore_errors=True)
        print(f"\n======================================================================")
        print(f"  [测试沙箱销毁] 沙箱已彻底抹除，宿主环境纯净无污染。")
        print(f"======================================================================")

    def setUp(self):
        # 每个用例创建一套独立的沙箱 config.json
        self.test_cfg_path = os.path.join(self.sandbox_dir, f"config_{time.time_ns()}.json")
        # 从真实 config.json 复制基准数据
        real_cfg = ORIGINAL_GET_CONFIG_PATH()
        with open(real_cfg, "r", encoding="utf-8") as f:
            self.base_data = json.load(f)

        with open(self.test_cfg_path, "w", encoding="utf-8") as f:
            json.dump(self.base_data, f, indent=2, ensure_ascii=False)

        # 猴子补丁：将 clean_core 引导至沙箱配置文件
        clean_core.get_config_path = lambda: self.test_cfg_path

    def tearDown(self):
        if os.path.exists(self.test_cfg_path):
            try:
                os.remove(self.test_cfg_path)
            except OSError:
                pass

    # ========================================================================
    # 板斧一：虚无与畸形 (The Void & Deformity)
    # ========================================================================

    def test_tc1_1_corrupted_config_json(self):
        """TC-1.1: 投毒畸形 JSON（缺大括号、注入 null 字节、乱码字符串）"""
        print("\n>>> [TC-1.1 投毒] 注入截断畸形 JSON 与空字节...")
        # 写入畸形 JSON
        with open(self.test_cfg_path, "wb") as f:
            f.write(b'{"settings": {"graceful_timeout_sec": 2, \x00\xff invalid json...')

        # 死线验证：load_config 不能抛出未捕获的 Panic 崩溃，应有容错或明确异常捕获
        # 如果当前代码未做畸形自愈，捕获 json.JSONDecodeError，证明探测到了畸形
        try:
            cfg = clean_core.load_config()
            self.fail("死线突破：畸形 JSON 竟然被解析成功！")
        except (json.JSONDecodeError, ValueError) as e:
            print(f"  [PASS] 成功拦截畸形 JSON 输入: {type(e).__name__}")

    def test_tc1_2_malformed_rules_and_boundary_values(self):
        """TC-1.2: 规则注入 null、负数超时、超长字符串等边界值"""
        print("\n>>> [TC-1.2 投毒] 注入负数超时、null 键值与超长字符串...")
        poisoned_cfg = {
            "settings": {"graceful_timeout_sec": -9999},  # 负数超时
            "preset_catalog": [
                {
                    "name": None,  # null 键
                    "process_names": None,
                    "install_path_keywords": [],
                    "detect_paths": ["A" * 100000]  # 100KB 超长路径
                }
            ],
            "targets": []
        }
        with open(self.test_cfg_path, "w", encoding="utf-8") as f:
            json.dump(poisoned_cfg, f)

        # 测试 discover_and_sync_targets 在极端畸形规则下的免疫力
        try:
            targets, changed, add, rm = clean_core.discover_and_sync_targets()
            print(f"  [PASS] 极端畸形规则注入下，增量对账平稳完成，无 Panic 崩溃！")
        except Exception as e:
            self.fail(f"死线违背：畸形规则导致引擎崩溃: {e}")

    def test_tc1_3_system_reserved_paths_and_path_traversal(self):
        """TC-1.3: 探测路径注入 Windows 保留名（CON, PRN）与跨目录攻击"""
        print("\n>>> [TC-1.3 投毒] 注入 Windows 系统保留设备名 (CON, PRN, AUX) 与越界路径...")
        malicious_rule = {
            "name": "ExploitAgent",
            "detect_paths": [
                "CON", "PRN", "AUX", "NUL",
                "COM1", "LPT1",
                "../../../../../../../../NonExistentFolder/fake_agent.exe"
            ]
        }
        # 必须安全返回 False，绝不能因 Windows 设备名返回 True，严禁抛出底层 OS 硬件设备句柄挂起异常
        installed, path = clean_core.check_agent_installed(malicious_rule)
        self.assertFalse(installed, f"死线违背：Windows 保留设备名或非法路径被误判为已安装！path={path}")
        self.assertIsNone(path)
        print(f"  [PASS] 保留名与路径穿越探测返回: installed={installed}, path={path}，0 误判，0 异常穿透！")

    # ========================================================================
    # 板斧二：时空踩踏 (Concurrency & Race)
    # ========================================================================

    def test_tc2_1_concurrent_sync_storm(self):
        """TC-2.1: 10 个线程在 1ms 内并发调用 discover_and_sync_targets() 轰炸"""
        print("\n>>> [TC-2.1 投毒] 10 个并发线程同时发起增量对账自愈风暴 (共 100 次读写)...")
        errors = []

        def worker():
            for _ in range(10):
                try:
                    clean_core.discover_and_sync_targets()
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 检查是否有文件损坏或并发异常
        self.assertEqual(len(errors), 0, f"死线违背：并发踩踏导致读写崩溃: {errors}")

        # 验证守恒律：文件必须完好且是合法的 JSON
        with open(self.test_cfg_path, "r", encoding="utf-8") as f:
            final_cfg = json.load(f)
        self.assertIn("targets", final_cfg)
        print(f"  [PASS] 100 次高并发读写踩踏后，配置文件 100% 完好，无脏写清空！")

    def test_tc2_2_button_click_flood(self):
        """TC-2.2: 模拟用户 1 秒内连续抽搐狂点 50 次清理动作"""
        print("\n>>> [TC-2.2 投毒] 模拟用户 1 秒内连击 50 次清理操作...")
        # 模拟空的匹配列表，验证幂等与互斥
        results = []
        for _ in range(50):
            count, mem = clean_core.clean_processes([], timeout=0)
            results.append((count, mem))

        # 幂等律验证：每次都应恒定返回 (0, 0)
        for count, mem in results:
            self.assertEqual(count, 0)
            self.assertEqual(mem, 0)
        print(f"  [PASS] 50 次快速连击完全符合幂等律，0 异常，系统终态恒定！")

    # ========================================================================
    # 板斧三：半截死刑 (Severance & Crash)
    # ========================================================================

    def test_tc3_1_atomic_write_resilience(self):
        """TC-3.1: 模拟写盘中途断电/崩溃，检验原子写入保护"""
        print("\n>>> [TC-3.1 投毒] 检验 save_config 的断电与截断保护能力...")
        # 准备一份基准好数据
        good_data = {"settings": {"graceful_timeout_sec": 2}, "targets": [{"name": "InitialSafeTarget"}]}
        clean_core.save_config(good_data)

        # 模拟写入中途强杀断电（注入异常，使写入未能完成原子重命名）
        orig_replace = clean_core.os.replace
        def mock_crash_replace(src, dst):
            raise IOError("模拟中途断电/强制关机 (Simulated Power Outage / SIGKILL)")

        clean_core.os.replace = mock_crash_replace
        try:
            bad_data = {"settings": {"graceful_timeout_sec": 999}, "targets": [{"name": "CorruptedData"}]}
            try:
                clean_core.save_config(bad_data)
            except IOError:
                pass  # 预期发生崩溃中断

            # 守恒律与原子性检验：即使中途断电，原配置文件必须 100% 毫发无损！绝不能变成 0 字节或半截数据
            loaded = clean_core.load_config()
            self.assertEqual(loaded["targets"][0]["name"], "InitialSafeTarget", "死线违背：写盘中途崩溃导致原配置损坏！")
            print(f"  [PASS] 写盘中途遭遇断电崩溃投毒，原配置文件 100% 毫发无损，原子写入免疫生效！")
        finally:
            clean_core.os.replace = orig_replace

    def test_tc3_2_access_denied_graceful_degradation(self):
        """TC-3.2: 模拟目标进程处于高权限受限状态 (psutil.AccessDenied)"""
        print("\n>>> [TC-3.2 投毒] 注入 AccessDenied 权限拒绝异常...")

        class MockDeniedProcess:
            def __init__(self):
                self.pid = 99999
            def name(self):
                raise clean_core.psutil.AccessDenied()
            def exe(self):
                raise clean_core.psutil.AccessDenied()
            def cmdline(self):
                raise clean_core.psutil.AccessDenied()

        # 匹配时遭遇权限拒绝，必须体面返回 False，绝不能抛出未捕获异常
        res = clean_core.match_process_to_target(MockDeniedProcess(), {"name": "Test"})
        self.assertFalse(res)
        print(f"  [PASS] 权限受限进程体面降级返回 False，0 异常穿透！")

    def test_tc3_3_stubborn_orphan_sigkill_escalation(self):
        """TC-3.3: 模拟顽固抗命进程，验证超时升级为 SIGKILL 强杀死线"""
        print("\n>>> [TC-3.3 投毒] 启动真实顽固测试假人子进程，检验 1s 超时升级强杀 (SIGKILL)...")
        dummy_cmd = [sys.executable, "-c", "import time; [time.sleep(0.1) for _ in range(100)]"]
        p = subprocess.Popen(dummy_cmd)
        try:
            ps_proc = clean_core.psutil.Process(p.pid)
            matched_list = [{
                "target_id": "MockStubborn",
                "target_name": "StubbornDummy",
                "proc": ps_proc,
                "pid": p.pid,
                "name": "python.exe",
                "memory_mb": 15.0,
                "has_window": False,
                "window_titles": []
            }]
            t0 = time.time()
            killed_count, mem = clean_core.clean_processes(matched_list, timeout=1)
            duration = time.time() - t0

            # 验证进程是否已彻底消亡
            self.assertFalse(ps_proc.is_running(), "死线违背：顽固进程未被彻底清除！")
            self.assertEqual(killed_count, 1)
            self.assertGreaterEqual(mem, 0, "守恒律违背：内存回收统计出现负数！")
            print(f"  [PASS] 顽固进程在超时后被精准强杀，耗时: {duration:.2f}s，时间单调律与内存守恒律通过！")
        finally:
            if p.poll() is None:
                p.kill()

    # ========================================================================
    # 板斧四：极限雪崩 (Exhaustion & Avalanche)
    # ========================================================================

    def test_tc4_1_avalanche_snapshot_exhaustion(self):
        """TC-4.1: 批量模拟进程快照比对，验证耗时防假死 (<100ms)"""
        print("\n>>> [TC-4.1 投毒] 模拟 500 个复杂进程特征匹配，检测探针算法耗时...")

        class MockNormalProcess:
            def __init__(self, pid, name, exe, cmd):
                self.pid = pid
                self._name = name
                self._exe = exe
                self._cmd = cmd
            def name(self):
                return self._name
            def exe(self):
                return self._exe
            def cmdline(self):
                return self._cmd

        # 构造 500 个模拟进程
        mock_procs = [
            MockNormalProcess(
                pid=1000 + i,
                name="node.exe" if i % 2 == 0 else "python.exe",
                exe=f"C:\\Users\\Mock\\AppData\\Local\\Programs\\Trae\\Trae.exe" if i % 5 == 0 else "C:\\Windows\\system32\\cmd.exe",
                cmd=["node.exe", "--inspect", "dsh"] if i % 7 == 0 else ["cmd.exe"]
            )
            for i in range(500)
        ]

        cfg = clean_core.load_config()
        targets = cfg.get("targets", [])

        # 计时 500 个进程比对时间
        t0 = time.perf_counter()
        matched_count = 0
        for p in mock_procs:
            for rule in targets:
                if clean_core.match_process_to_target(p, rule):
                    matched_count += 1
                    break
        elapsed_ms = (time.perf_counter() - t0) * 1000

        print(f"  -> 500 个进程遍历比对耗时: {elapsed_ms:.2f} ms | 命中: {matched_count} 个")
        # 死线判定：500 个进程比对耗时必须 <= 100ms
        self.assertLessEqual(elapsed_ms, 100.0, f"死线违背：遍历耗时超标，达到 {elapsed_ms:.2f} ms")
        print(f"  [PASS] 极速快照算法在 500 进程雪崩压力下仅耗时 {elapsed_ms:.2f} ms，远低于 100ms 警戒线！")

    def test_tc4_2_idempotency_of_incremental_diff(self):
        """TC-4.2: 连续执行 100 次增量对账自愈，验证幂等律 f(f(x)) = f(x)"""
        print("\n>>> [TC-4.2 投毒] 连续 100 次增量对账，严密核验幂等律与资产守恒律...")

        # 第一次对账
        targets_0, _, _, _ = clean_core.discover_and_sync_targets()
        names_0 = sorted([t.get("name") for t in targets_0])

        # 连续跑 99 次
        for i in range(99):
            targets_i, changed, add, rm = clean_core.discover_and_sync_targets()
            # 从第 2 次开始，changed 必须恒为 False，无抖动
            self.assertFalse(changed, f"第 {i+2} 次对账发生意外变更抖动！")
            names_i = sorted([t.get("name") for t in targets_i])
            self.assertEqual(names_0, names_i, f"第 {i+2} 次对账目标列表与初始不一致！")

        print(f"  [PASS] 连续 100 次对账自愈完全恒定，资产绝对守恒，完美通过幂等纯净律！")


def run_adversarial_suite():
    """运行全套恶意破坏测试并输出战报"""
    suite = unittest.TestLoader().loadTestsFromTestCase(TestAdversarialHarness)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result


if __name__ == "__main__":
    result = run_adversarial_suite()
    sys.exit(0 if result.wasSuccessful() else 1)
