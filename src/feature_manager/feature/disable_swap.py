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
from src.utils.common import run_cmd

logger = get_logger(__name__)

FEATURE_NAME = "disable_swap"
FEATURE_DES = "禁用交换内存"


@register_feature(scenarios=["boundary_gateway_appliance", "kingbase_database", "dameng_database", "common"])
class DisableSwap(BaseFeature):
    name: str = FEATURE_NAME
    swappiness: int = 0

    def get_current_config(self) -> dict:
        self.deploy = "NA"
        paths = {
            "swappiness": "/proc/sys/vm/swappiness",
        }
        for key, path in paths.items():
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                self.__dict__[key] = int(content)
        config = self.model_dump()
        logger.debug(f"Optimization Item {self.name} current config yaml is generated")
        return config

    def _apply_config_impl(self):
        """
        根据配置文件执行关闭交换分区的操作
        """
        # 配置参数
        swappiness = self.swappiness
        if swappiness < 0 or swappiness > 80:
            raise RuntimeError(
                f"Invalid swappiness configuration! "
                f"Current value: '{swappiness}'. "
                f"Valid range is 0–80 "
                f"(you can check it with: cat /proc/sys/vm/swappiness)"
            )
        try:
            # 检查是否已存在配置
            check_cmd = ["grep", "-q", "^vm.swappiness", "/etc/sysctl.conf"]
            run_cmd(check_cmd)
            run_cmd(["sed", "-i", f"s/^vm.swappiness=.*/vm.swappiness={swappiness}/", "/etc/sysctl.conf"])
        except RuntimeError:
            run_cmd(f"echo vm.swappiness={swappiness} >> /etc/sysctl.conf",is_str=True)
        run_cmd(["sysctl", "-p"])
