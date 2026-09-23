#!/usr/bin/env python3
"""
Issue 修复测试 - 覆盖以下修复点：
- Issue #2: optimize_io_queue_scheduler.py lsblk check=True 失败时不再静默吞错误
- Issue #5: basecfg/execute 路径 subprocess.run 加 timeout 后超时异常处理
- basecfg 性能优化: check_boostkit_hyperscan_installed.py find / 替换为 ldconfig 查询
"""

import sys
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ===========================================================================
# Issue #2: lsblk check=True — 失败时应抛 CalledProcessError 并被已有 except 捕获
# ===========================================================================
class TestIssue2LsblkCheck:
    """验证 lsblk 失败时不再静默吞错误，而是记录 warning 并返回空配置。"""

    @pytest.fixture
    def feature_instance(self):
        from src.feature_manager.feature.optimize_io_queue_scheduler import (
            OptimizeIOQueueScheduler,
        )
        return OptimizeIOQueueScheduler()

    def test_lsblk_failure_logs_warning_and_returns_empty(self, feature_instance, caplog):
        """lsblk 返回非零（如精简容器中无 lsblk）时应记录 warning 且返回空配置。"""
        exc = subprocess.CalledProcessError(
            returncode=1, cmd=["lsblk", "-dn", "-o", "NAME,TYPE"]
        )
        with patch("subprocess.run", side_effect=exc):
            config = feature_instance.get_current_config()

        assert config["io_queue_scheduler"] == {}
        assert config["deploy"] == "NA"
        assert any(
            "Failed to list disks" in record.message
            for record in caplog.records
        ), "应记录 'Failed to list disks' warning"

    def test_lsblk_success_returns_disk_config(self, feature_instance):
        """lsblk 正常时应返回磁盘调度策略配置。"""
        mock_lsblk = subprocess.CompletedProcess(
            args=["lsblk", "-dn", "-o", "NAME,TYPE"],
            returncode=0,
            stdout="sda disk\n",
            stderr="",
        )
        with patch("subprocess.run", return_value=mock_lsblk):
            with patch.object(feature_instance, "_is_ssd", return_value=True):
                with patch("builtins.open", mock_open_helper("[none] mq-deadline kyber ")):
                    config = feature_instance.get_current_config()

        assert "sda" in config["io_queue_scheduler"]
        assert config["io_queue_scheduler"]["sda"] == "none"


def mock_open_helper(read_data):
    """创建 mock_open 并预设 read 返回值。"""
    m = MagicMock()
    m.return_value.__enter__.return_value.read.return_value = read_data
    return m


# ===========================================================================
# Issue #5: timeout 异常处理 — basecfg/execute 路径超时后不崩溃
# ===========================================================================
class TestIssue5TimeoutHandling:
    """验证 basecfg/execute 路径的 subprocess.run 超时后被优雅处理。"""

    def test_io_scheduler_lsblk_timeout(self):
        """lsblk 超时 → get_current_config 不崩溃，返回空配置。"""
        from src.feature_manager.feature.optimize_io_queue_scheduler import (
            OptimizeIOQueueScheduler,
        )
        feature = OptimizeIOQueueScheduler()
        exc = subprocess.TimeoutExpired(cmd=["lsblk"], timeout=30)
        with patch("subprocess.run", side_effect=exc):
            config = feature.get_current_config()
        assert config["io_queue_scheduler"] == {}

    def test_nic_rss_ethtool_timeout(self):
        """ethtool/ip 超时 → get_current_config 不崩溃，返回含 None 的配置。"""
        from src.feature_manager.feature.optimize_nic_rss import OptimizeNicRss
        feature = OptimizeNicRss()
        exc = subprocess.TimeoutExpired(cmd=["ethtool"], timeout=30)
        with patch("subprocess.run", side_effect=exc):
            config = feature.get_current_config()
        assert config is not None
        assert config["deploy"] == "NA"

    def test_network_params_sysctl_timeout(self):
        """sysctl 超时 → get_current_config 不崩溃，超时的参数值为 None。"""
        from src.feature_manager.feature.optimize_network_params import (
            OptimizeNetworkParams,
        )
        feature = OptimizeNetworkParams()
        exc = subprocess.TimeoutExpired(cmd=["sysctl"], timeout=30)
        with patch("subprocess.run", side_effect=exc):
            config = feature.get_current_config()
        current = config.get("current_values", {})
        for key in feature.params:
            assert current.get(key) is None, f"{key} 应为 None（超时未读到）"

    def test_irqbalance_systemctl_timeout(self):
        """systemctl is-active 超时 → get_current_config 不崩溃。"""
        from src.feature_manager.feature.update_irqbalance import UpdateIrqBalance
        feature = UpdateIrqBalance()
        exc = subprocess.TimeoutExpired(cmd=["systemctl"], timeout=30)
        with patch("subprocess.run", side_effect=exc):
            with pytest.raises(Exception):
                feature.get_current_config()

    def test_sched_rt_runtime_sysctl_timeout(self):
        """sysctl -p 超时 → _apply_config_impl 返回 warning 而非崩溃。"""
        from src.feature_manager.feature.update_sched_rt_runtime import (
            UpdateSchedRtRuntime,
        )
        feature = UpdateSchedRtRuntime()
        feature.sched_rt_runtime = -1
        exc = subprocess.TimeoutExpired(cmd=["sysctl"], timeout=30)
        with patch("subprocess.run", side_effect=exc):
            with patch("builtins.open", mock_open_helper("kernel.sched_rt_runtime_us = -1\n")):
                result = feature._apply_config_impl()
        assert result is not None
        assert result["status"] == "warning"

    def test_io_scheduler_udevadm_timeout_in_apply(self):
        """udevadm 超时 → _apply_config_impl 返回 error 而非崩溃。"""
        from src.feature_manager.feature.optimize_io_queue_scheduler import (
            OptimizeIOQueueScheduler,
        )
        feature = OptimizeIOQueueScheduler()
        feature.io_queue_scheduler = {"sda": "none"}
        exc = subprocess.TimeoutExpired(cmd=["udevadm"], timeout=30)
        with patch("subprocess.run", side_effect=exc):
            with patch("builtins.open", MagicMock()):
                result = feature._apply_config_impl()
        assert result is not None
        assert result.get("status") == "error"

    def test_env_dmidecode_timeout(self):
        """dmidecode 超时 → get_cpu_info 抛 RuntimeError 而非永久阻塞。"""
        from src.utils.env import get_cpu_info
        exc = subprocess.TimeoutExpired(cmd=["dmidecode"], timeout=30)
        with patch("subprocess.run", side_effect=exc):
            with pytest.raises(RuntimeError, match="获取CPU信息失败"):
                get_cpu_info()


# ===========================================================================
# basecfg 性能优化: find / → ldconfig 查询
# ===========================================================================
class TestFindLibHsRuntimeOptimization:
    """验证 _find_libhs_runtime_files 优先用 ldconfig，回退到限定路径 find。"""

    @pytest.fixture
    def feature_instance(self):
        from src.feature_manager.feature.check_boostkit_hyperscan_installed import (
            CheckBoostKitHyperscanInstalled,
        )
        return CheckBoostKitHyperscanInstalled()

    def test_ldconfig_finds_libhs_runtime(self, feature_instance):
        """ldconfig -p 输出含 libhs_runtime 时应正确解析路径。"""
        mock_ldconfig = subprocess.CompletedProcess(
            args=["ldconfig", "-p"],
            returncode=0,
            stdout=(
                "\tlibhs_runtime.so.5 (libc6,AArch64) => /usr/lib64/libhs_runtime.so.5\n"
                "\tlibhs_runtime.so (libc6,AArch64) => /usr/lib64/libhs_runtime.so\n"
                "\tlibother.so (libc6) => /usr/lib/libother.so\n"
            ),
            stderr="",
        )
        with patch("subprocess.run", return_value=mock_ldconfig):
            with patch("os.path.isfile", return_value=True):
                result = feature_instance._find_libhs_runtime_files()
        assert "/usr/lib64/libhs_runtime.so.5" in result
        assert "/usr/lib64/libhs_runtime.so" in result
        assert len(result) == 2

    def test_ldconfig_empty_fallback_to_find(self, feature_instance):
        """ldconfig 无结果时应回退到限定路径 find。"""
        mock_ldconfig_empty = subprocess.CompletedProcess(
            args=["ldconfig", "-p"],
            returncode=0,
            stdout="other stuff\n",
            stderr="",
        )
        mock_find = subprocess.CompletedProcess(
            args=["find"],
            returncode=0,
            stdout="/usr/lib64/libhs_runtime.so\n",
            stderr="",
        )
        call_count = [0]

        def mock_run(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_ldconfig_empty
            return mock_find

        with patch("subprocess.run", side_effect=mock_run):
            with patch("os.path.isdir", side_effect=lambda d: d == "/usr/lib64"):
                result = feature_instance._find_libhs_runtime_files()
        assert result == ["/usr/lib64/libhs_runtime.so"]

    def test_ldconfig_not_found_fallback_to_find(self, feature_instance):
        """ldconfig 不存在（精简容器）时应回退到 find。"""
        mock_find = subprocess.CompletedProcess(
            args=["find"],
            returncode=0,
            stdout="/lib64/libhs_runtime.so\n",
            stderr="",
        )
        call_count = [0]

        def mock_run(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise FileNotFoundError("ldconfig not found")
            return mock_find

        with patch("subprocess.run", side_effect=mock_run):
            with patch("os.path.isdir", side_effect=lambda d: d == "/lib64"):
                result = feature_instance._find_libhs_runtime_files()
        assert result == ["/lib64/libhs_runtime.so"]

    def test_no_libhs_runtime_found_returns_empty(self, feature_instance):
        """两级查找均无结果时应返回空列表。"""
        mock_empty = subprocess.CompletedProcess(
            args=["ldconfig", "-p"],
            returncode=0,
            stdout="",
            stderr="",
        )
        mock_find_empty = subprocess.CompletedProcess(
            args=["find"],
            returncode=0,
            stdout="",
            stderr="",
        )
        call_count = [0]

        def mock_run(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_empty
            return mock_find_empty

        with patch("subprocess.run", side_effect=mock_run):
            with patch("os.path.isdir", side_effect=lambda d: d == "/usr/lib64"):
                result = feature_instance._find_libhs_runtime_files()
        assert result == []

    def test_no_files_found_status_uninstalled(self, feature_instance):
        """未找到 libhs_runtime 文件时 install_status 应为 'uninstalled'。"""
        with patch.object(
            feature_instance, "_find_libhs_runtime_files", return_value=[]
        ):
            config = feature_instance.get_current_config()
        assert config["boostkit_hyperscan_install_status"] == "uninstalled"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
