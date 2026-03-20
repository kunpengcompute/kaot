#!/usr/bin/env python3
# coding: utf-8
# Copyright 2025 Huawei Technologies Co., Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ===========================================================================
import subprocess
from src.feature_manager.feature import register_feature
from src.feature_manager.feature.base import BaseFeature
from typing import Dict, Any
from src.utils.log import get_logger
import shlex

logger = get_logger(__name__)


FEATURE_NAME = "optimize_io_queue_scheduler"
FEATURE_DES = "优化磁盘IO调度策略"


@register_feature(scenarios=["kingbase_database", "opengauss_database"])
class OptimizeIOQueueScheduler(BaseFeature):
    name: str = FEATURE_NAME
    io_queue_scheduler: dict = {}  # {disk: scheduler}

    def get_current_config(self) -> dict:
        """
        查询所有磁盘的调度策略，返回feature配置字典。
        """
        self.deploy = "NA"
        schedulers = {}
        try:
            # 获取所有块设备（过滤掉loop、ram等）
            lsblk_proc = subprocess.run(["lsblk", "-dn", "-o", "NAME,TYPE"], capture_output=True, text=True, check=False)
            disks = [line.split()[0] for line in lsblk_proc.stdout.strip().splitlines() if line.strip() and line.split()[1] == "disk"]
            for disk in disks:
                path = f"/sys/block/{disk}/queue/scheduler"
                try:
                    with open(path, "r") as f:
                        value = f.read().strip()
                    scheduler_list = value.split()
                    current_scheduler = None
                    for s in scheduler_list:
                        if s.startswith("[") and s.endswith("]"):
                            current_scheduler = s[1:-1]
                            break
                    schedulers[disk] = current_scheduler or "unknown"
                except Exception as e:
                    logger.warning(f"Failed to get IO scheduler for {disk}: {e}")
                    schedulers[disk] = "unknown"
        except Exception as e:
            logger.warning(f"Failed to list disks: {e}")
        self.io_queue_scheduler = schedulers
        config = self.model_dump()
        logger.debug(f"Optimization Item {self.name} current config yaml is generated")
        return config

    def pre_generate_config(self):
        """
        获取所有磁盘的调度策略，识别SSD并将其调度策略设为none。
        """
        logger.info("Starting pre_generate_config for io_queue_scheduler.")
        config = self.get_current_config()
        schedulers = config.get("io_queue_scheduler", {})
        # 识别SSD: 通过/sys/block/{disk}/queue/rotational，0为SSD，1为HDD
        for disk in schedulers.keys():
            try:
                rotational_path = f"/sys/block/{disk}/queue/rotational"
                with open(rotational_path, "r") as f:
                    is_rotational = f.read().strip()
                if is_rotational == "0":
                    self.io_queue_scheduler[disk] = "none"
                    logger.info(f"Disk {disk} is SSD, set scheduler to 'none'.")
                else:
                    self.io_queue_scheduler[disk] = schedulers[disk]
            except Exception as e:
                logger.warning(f"Failed to determine disk type for {disk}: {e}")
                self.io_queue_scheduler[disk] = schedulers[disk]
    
    def generate_config(self) -> Dict[str, Any]:
        """
        通用配置生成逻辑
        :return: 统一格式的配置字典
        """ 
        self.pre_generate_config()
        self.deploy = "Y"
        config = self.model_dump()
        logger.debug(f"Optimization Item {self.name} config yaml is generated")
        return config
    
    def _apply_config_impl(self) -> dict:
        """
        只对SSD盘下发IO调度策略到/sys/block/{disk}/queue/scheduler。
        """
        schedulers = self.io_queue_scheduler
        if not schedulers or not isinstance(schedulers, dict):
            logger.warning("The 'io_queue_scheduler' parameter is missing or invalid.")
            return {
                "status": "error",
                "message": "Missing or invalid parameter: io_queue_scheduler",
            }
        results = {}
        ssd_disks = []
        # 识别SSD盘
        for disk in schedulers.keys():
            rotational_path = f"/sys/block/{disk}/queue/rotational"
            try:
                with open(rotational_path, "r") as f:
                    is_rotational = f.read().strip()
                if is_rotational == "0":
                    ssd_disks.append(disk)
            except Exception:
                pass
        # 只对SSD盘下发
        for disk in ssd_disks:
            value = schedulers[disk]
            safe_value = shlex.quote(str(value))
            cmd = [
                "bash",
                "-c",
                f"echo {safe_value} > /sys/block/{disk}/queue/scheduler",
            ]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if proc.returncode == 0:
                    logger.info(f"IO scheduler for {disk} set to {value} successfully.")
                    results[disk] = {"status": "success", "message": f"IO scheduler for {disk} set to {value}"}
                else:
                    logger.error(f"Failed to set IO scheduler for {disk}: {proc.stderr}")
                    results[disk] = {"status": "error", "message": f"Failed to set IO scheduler for {disk}: {proc.stderr}"}
            except Exception as e:
                logger.error(f"Exception when setting IO scheduler for {disk}: {e}")
                results[disk] = {"status": "error", "message": f"Exception: {e}"}

        # 检查SSD盘调度策略是否真的变化
        unchanged_disks = []
        for disk in ssd_disks:
            value = schedulers[disk]
            path = f"/sys/block/{disk}/queue/scheduler"
            try:
                with open(path, "r") as f:
                    sched_value = f.read().strip()
                # 当前调度策略用[]包裹
                current = None
                for s in sched_value.split():
                    if s.startswith("[") and s.endswith("]"):
                        current = s[1:-1]
                        break
                if current != str(value):
                    unchanged_disks.append(disk)
            except Exception:
                pass
        if unchanged_disks:
            logger.warning(
                f"Optimization has been executed successfully, but io_queue_scheduler did not change for disks: {', '.join(unchanged_disks)}. Please check if disk io_queue_scheduler policy is locked."
            )
        return results
      
