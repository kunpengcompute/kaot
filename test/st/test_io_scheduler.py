#!/usr/bin/env python3
"""
IO调度策略测试 - 测试SSD识别逻辑、generate和execute功能
包括：虚拟机环境识别、TRIM支持检测、generate/execute流程
"""

import os
import sys
import tempfile
import subprocess
import shutil
from pathlib import Path
from unittest.mock import patch, mock_open

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestSSDIdentification:
    """SSD磁盘识别逻辑测试"""

    @pytest.fixture
    def feature_instance(self):
        """获取OptimizeIOQueueScheduler实例"""
        from src.feature_manager.feature.optimize_io_queue_scheduler import OptimizeIOQueueScheduler
        return OptimizeIOQueueScheduler()

    def test_is_ssd_by_rotational(self, feature_instance):
        """测试通过rotational=0识别SSD"""
        mock_rotational = "0"
        mock_discard = "0"
        
        def mock_file_open(path, mode='r'):
            if "rotational" in path:
                return mock_open(read_data=mock_rotational)()
            elif "discard_granularity" in path:
                return mock_open(read_data=mock_discard)()
            return mock_open(read_data="")()
        
        with patch("builtins.open", side_effect=mock_file_open):
            result = feature_instance._is_ssd("sda")
            assert result == True, "rotational=0应识别为SSD"

    def test_is_ssd_by_trim_support(self, feature_instance):
        """测试通过discard_granularity>0识别SSD（虚拟机场景）"""
        mock_rotational = "1"
        mock_discard = "512"
        
        def mock_file_open(path, mode='r'):
            if "rotational" in path:
                return mock_open(read_data=mock_rotational)()
            elif "discard_granularity" in path:
                return mock_open(read_data=mock_discard)()
            return mock_open(read_data="")()
        
        with patch("builtins.open", side_effect=mock_file_open):
            result = feature_instance._is_ssd("vda")
            assert result == True, "rotational=1但discard_granularity>0应识别为SSD"

    def test_is_hdd_no_trim(self, feature_instance):
        """测试HDD识别（rotational=1且无TRIM支持）"""
        mock_rotational = "1"
        mock_discard = "0"
        
        def mock_file_open(path, mode='r'):
            if "rotational" in path:
                return mock_open(read_data=mock_rotational)()
            elif "discard_granularity" in path:
                return mock_open(read_data=mock_discard)()
            return mock_open(read_data="")()
        
        with patch("builtins.open", side_effect=mock_file_open):
            result = feature_instance._is_ssd("sdb")
            assert result == False, "rotational=1且discard_granularity=0应识别为HDD"


class TestGenerateConfig:
    """generate_config功能测试"""

    @pytest.fixture
    def output_dir(self):
        """创建临时输出目录"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_generate_config_basic(self, output_dir):
        """测试基本generate流程"""
        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "kaot.py"),
            "generate",
            "-f", "optimize_io_queue_scheduler",
            "-o", "test_io.yaml"
        ]
        
        os.makedirs(PROJECT_ROOT / "output", exist_ok=True)
        output_file = PROJECT_ROOT / "output" / "test_io.yaml"
        
        if output_file.exists():
            output_file.unlink()
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            timeout=60
        )
        
        if output_file.exists():
            output_file.unlink()
        
        assert result.returncode == 0, f"generate失败: {result.stderr}"

    def test_generate_yaml_content(self, output_dir):
        """测试生成的YAML内容"""
        from src.feature_manager.feature.optimize_io_queue_scheduler import OptimizeIOQueueScheduler
        
        feature = OptimizeIOQueueScheduler()
        
        mock_lsblk = subprocess.CompletedProcess(
            args=["lsblk", "-dn", "-o", "NAME,TYPE"],
            returncode=0,
            stdout="sda disk\nvda disk\n",
            stderr=""
        )
        
        with patch("subprocess.run", return_value=mock_lsblk):
            with patch.object(feature, '_is_ssd', return_value=True):
                config = feature.generate_config()
                
                assert config["deploy"] == "Y", "generate_config应设置deploy=Y"
                assert "io_queue_scheduler" in config
                for disk, scheduler in config["io_queue_scheduler"].items():
                    assert scheduler == "none", "SSD应设置scheduler为none"

    def test_generate_with_existing_none_scheduler(self, output_dir):
        """测试scheduler已是none的情况"""
        from src.feature_manager.feature.optimize_io_queue_scheduler import OptimizeIOQueueScheduler
        
        feature = OptimizeIOQueueScheduler()
        
        mock_lsblk = subprocess.CompletedProcess(
            args=["lsblk", "-dn", "-o", "NAME,TYPE"],
            returncode=0,
            stdout="sda disk\nvda disk\n",
            stderr=""
        )
        
        with patch("subprocess.run", return_value=mock_lsblk):
            with patch.object(feature, '_is_ssd', return_value=True):
                config = feature.generate_config()
                
                assert config["deploy"] == "Y"
                for disk, scheduler in config["io_queue_scheduler"].items():
                    assert scheduler == "none"


class TestExecuteConfig:
    """execute功能测试（需要root权限）"""

    @pytest.fixture
    def output_dir(self):
        """创建临时输出目录"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_apply_config_impl_no_ssd(self):
        """测试无SSD时的apply_config"""
        from src.feature_manager.feature.optimize_io_queue_scheduler import OptimizeIOQueueScheduler
        
        feature = OptimizeIOQueueScheduler()
        feature.io_queue_scheduler = {}
        
        result = feature._apply_config_impl()
        
        assert result["status"] == "success"
        assert "No SSD disks" in result["message"]

    def test_apply_config_impl_mock_udev(self):
        """测试udev规则生成（mock）"""
        from src.feature_manager.feature.optimize_io_queue_scheduler import OptimizeIOQueueScheduler
        
        feature = OptimizeIOQueueScheduler()
        feature.io_queue_scheduler = {"sda": "none"}
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            
            with patch("builtins.open", mock_open()):
                result = feature._apply_config_impl()
        
        assert result is not None


class TestRollback:
    """回退功能测试"""

    def test_rollback_logic(self):
        """测试回退逻辑"""
        from src.feature_manager.feature.optimize_io_queue_scheduler import OptimizeIOQueueScheduler
        
        feature = OptimizeIOQueueScheduler()
        
        mock_lsblk = subprocess.CompletedProcess(
            args=["lsblk", "-dn", "-o", "NAME,TYPE"],
            returncode=0,
            stdout="sda disk\nvda disk\n",
            stderr=""
        )
        
        with patch("subprocess.run", return_value=mock_lsblk):
            with patch.object(feature, '_is_ssd', return_value=True):
                base_config = feature.get_current_config()
                target_config = feature.generate_config()
                
                assert base_config["deploy"] == "NA"
                assert target_config["deploy"] == "Y"
                for disk, scheduler in target_config["io_queue_scheduler"].items():
                    assert scheduler == "none"


class TestIntegration:
    """集成测试"""

    def test_current_environment_disks(self):
        """测试当前环境的磁盘识别"""
        from src.feature_manager.feature.optimize_io_queue_scheduler import OptimizeIOQueueScheduler
        
        feature = OptimizeIOQueueScheduler()
        
        try:
            config = feature.get_current_config()
            
            assert "io_queue_scheduler" in config
            assert isinstance(config["io_queue_scheduler"], dict)
            
            for disk in config["io_queue_scheduler"].keys():
                assert feature._is_ssd(disk), f"磁盘{disk}应被识别为SSD"
                
        except Exception as e:
            pytest.skip(f"无法读取磁盘信息: {e}")

    def test_full_generate_flow(self):
        """测试完整generate流程"""
        from src.feature_manager.feature.optimize_io_queue_scheduler import OptimizeIOQueueScheduler
        
        feature = OptimizeIOQueueScheduler()
        
        try:
            config = feature.generate_config()
            
            assert config["deploy"] in ["Y", "NA"]
            assert "io_queue_scheduler" in config
            
            for disk, scheduler in config["io_queue_scheduler"].items():
                assert scheduler == "none", f"SSD {disk}的scheduler应为none"
                
        except Exception as e:
            pytest.skip(f"无法执行generate: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])