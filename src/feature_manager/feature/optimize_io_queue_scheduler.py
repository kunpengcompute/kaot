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

logger = get_logger(__name__)


FEATURE_NAME = "optimize_io_queue_scheduler"
FEATURE_DES = "优化磁盘IO调度策略"


@register_feature(scenarios=["kingbase_database", "dameng_database"])
class OptimizeIOQueueScheduler(BaseFeature):
    name: str = FEATURE_NAME
    io_queue_scheduler: dict = {}  # {disk: scheduler}

    def get_current_config(self) -> dict:
        """
        查询所有SSD磁盘的调度策略，返回feature配置字典。
        只返回SSD磁盘，HDD磁盘不包含在配置中。
        """
        self.deploy = "NA"
        schedulers = {}
        try:
            lsblk_proc = subprocess.run(["lsblk", "-dn", "-o", "NAME,TYPE"], capture_output=True, text=True, check=False)
            disks = [line.split()[0] for line in lsblk_proc.stdout.strip().splitlines() if line.strip() and line.split()[1] == "disk"]
            for disk in disks:
                if not self._is_ssd(disk):
                    logger.debug(f"Disk {disk} is HDD, skipped in get_current_config.")
                    continue
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
                    logger.debug(f"Disk {disk} is SSD, current scheduler '{schedulers[disk]}'.")
                except Exception as e:
                    logger.warning(f"Failed to get IO scheduler for {disk}: {e}")
                    schedulers[disk] = "unknown"
        except Exception as e:
            logger.warning(f"Failed to list disks: {e}")
        self.io_queue_scheduler = schedulers
        config = self.model_dump()
        logger.debug(f"Optimization Item {self.name} current config yaml is generated")
        return config

    def _is_ssd(self, disk: str) -> bool:
        """
        判断磁盘是否为SSD。
        优先通过rotational判断，其次通过discard_granularity（TRIM支持）判断。
        """
        try:
            rotational_path = f"/sys/block/{disk}/queue/rotational"
            with open(rotational_path, "r") as f:
                is_rotational = f.read().strip()
            if is_rotational == "0":
                logger.info(f"Disk {disk} rotational=0, identified as SSD.")
                return True
        except Exception as e:
            logger.warning(f"Failed to read rotational for {disk}: {e}")

        try:
            discard_path = f"/sys/block/{disk}/queue/discard_granularity"
            with open(discard_path, "r") as f:
                discard_gran = f.read().strip()
            if discard_gran and int(discard_gran) > 0:
                logger.info(f"Disk {disk} supports TRIM (discard_granularity={discard_gran}), identified as SSD.")
                return True
        except Exception as e:
            logger.warning(f"Failed to read discard_granularity for {disk}: {e}")

        return False

    def pre_generate_config(self):
        """
        获取所有SSD磁盘的调度策略，将其调度策略设为none。
        """
        logger.info("Starting pre_generate_config for io_queue_scheduler.")
        config = self.get_current_config()
        schedulers = config.get("io_queue_scheduler", {})
        for disk, current_scheduler in schedulers.items():
            self.io_queue_scheduler[disk] = "none"
            if current_scheduler == "none":
                logger.info(f"Disk {disk} is SSD and scheduler already 'none'.")
            else:
                logger.info(f"Disk {disk} is SSD, current scheduler '{current_scheduler}', target scheduler 'none'.")
    
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
        使用udev规则对SSD盘下发IO调度策略。
        """
        schedulers = self.io_queue_scheduler
        if not schedulers or not isinstance(schedulers, dict):
            logger.info("No SSD disks found, no optimization needed.")
            return {
                "status": "success",
                "message": "No SSD disks found.",
            }
        
        # 创建udev规则文件
        udev_rule_path = "/etc/udev/rules.d/io-queue-scheduler.rules"
        try:
            with open(udev_rule_path, "w") as f:
                for disk, value in schedulers.items():
                    f.write(f'ACTION=="add", KERNEL=="{disk}", ATTR{{queue/scheduler}}="{value}"\n')
                    f.write(f'ACTION=="change", KERNEL=="{disk}", ATTR{{queue/scheduler}}="{value}"\n')
            logger.info(f"Udev rules written to {udev_rule_path}")
        except Exception as e:
            logger.error(f"Failed to write udev rules to {udev_rule_path}: {e}")
            return {
                "status": "error",
                "message": f"Failed to write udev rules: {e}"
            }
        
        # 重载udev规则
        try:
            reload_result = subprocess.run(
                ["udevadm", "control", "--reload-rules"],
                capture_output=True,
                text=True,
                check=False
            )
            if reload_result.returncode != 0:
                logger.error(f"Failed to reload udev rules: {reload_result.stderr}")
                return {
                    "status": "error",
                    "message": f"Failed to reload udev rules: {reload_result.stderr}"
                }
        except Exception as e:
            logger.error(f"Exception when reloading udev rules: {e}")
            return {
                "status": "error",
                "message": f"Exception when reloading udev rules: {e}"
            }
        
        # 对当前存在的SSD应用规则
        results = {}
        for disk, value in schedulers.items():
            try:
                trigger_result = subprocess.run(
                    ["udevadm", "trigger", "--name-match=" + disk],
                    capture_output=True,
                    text=True,
                    check=False
                )
                if trigger_result.returncode == 0:
                    logger.info(f"IO scheduler for {disk} set to {value} successfully via udev rule.")
                    results[disk] = {"status": "success", "message": f"IO scheduler for {disk} set to {value} via udev rule"}
                else:
                    logger.error(f"Failed to trigger udev rule for {disk}: {trigger_result.stderr}")
                    results[disk] = {"status": "error", "message": f"Failed to trigger udev rule for {disk}: {trigger_result.stderr}"}
            except Exception as e:
                logger.error(f"Exception when triggering udev rule for {disk}: {e}")
                results[disk] = {"status": "error", "message": f"Exception: {e}"}

        return results
      
