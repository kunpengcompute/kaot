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
from src.utils.log import get_logger

logger = get_logger(__name__)


FEATURE_NAME = "update_irqbalance"
FEATURE_DES = "关闭内核中断平衡"


@register_feature(scenarios=["boundary_gateway_appliance"])
class UpdateIrqBalance(BaseFeature):
    name: str = FEATURE_NAME
    irq_balance_status: str = "inactive"

    def get_current_config(self) -> dict:
        """
        查询 irqbalance 服务当前状态，返回 feature 的配置字典。
        异常由调用方统一处理，不在此捕获。
        """
        self.deploy = "NA"

        proc = subprocess.run(
            ["systemctl", "is-active", "irqbalance"],
            capture_output=True,
            text=True,
            check=False,
        )
        status = (proc.stdout or proc.stderr or "").strip() or "unknown"

        self.__dict__["irq_balance_status"] = status
        config = self.model_dump()
        logger.debug(f"Optimization Item {self.name} current config yaml is generated")
        # 返回英文
        return config

    def _apply_config_impl(self) -> dict:
        """
        根据输入配置字典中的 status 字段，启动或停止 irqbalance 服务。
        """
        status = self.irq_balance_status
        command_start_stop = ""
        command_enable_disable = ""

        if status == "active":
            command_start_stop = ["systemctl", "start", "irqbalance"]
            command_enable_disable = ["systemctl", "enable", "irqbalance"]
        elif status == "inactive":
            command_start_stop = ["systemctl", "stop", "irqbalance"]
            command_enable_disable = ["systemctl", "disable", "irqbalance"]
        else:
            logger.warning("Unknown status: %s", status)
            return {"status": "error", "message": "Unknown status"}

        try:
            # 执行 start/stop 命令
            subprocess.run(
                command_start_stop,
                capture_output=True,
                text=True,
                check=False,
            )
            logger.info("Command executed successfully: %s", " ".join(command_start_stop))
            
            # 执行 enable/disable 命令
            subprocess.run(
                command_enable_disable,
                capture_output=True,
                text=True,
                check=False,
            )
            logger.info("Command executed successfully: %s", " ".join(command_enable_disable))
            
            return {"status": "success", "message": f"Service is {status}"}
        except subprocess.CalledProcessError as e:
            logger.exception("Failed to execute command: %s", e)
            return {"status": "error", "message": str(e)}
