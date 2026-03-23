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
import os
from src.feature_manager.feature import register_feature
from src.feature_manager.feature.base import BaseFeature
from src.utils.log import get_logger
from src.utils.common import run_cmd


logger = get_logger(__name__)

FEATURE_NAME = "disable_memory_overcommit"
FEATURE_DES = "禁用内存主动回收策略"


@register_feature(scenarios=["boundary_gateway_appliance"])
class OvercommitDisableFeature(BaseFeature):
    name: str = FEATURE_NAME
    zone_reclaim: int = 0

    def get_current_config(self) -> dict:
        paths = {
            "zone_reclaim": "/proc/sys/vm/zone_reclaim_mode",
        }
        for key, path in paths.items():
            try:
                with open(path, "r") as f:
                    value = f.read().strip()
                    self.__dict__[key] = int(value)
            except FileNotFoundError:
                logger.warning(f"Path {os.path.abspath(path)} not found, skip reading {key}")
        config = self.model_dump()
        logger.debug(f"Optimization Item {self.name} current config yaml is generated")
        return config

    def _apply_config_impl(self):
        """
        根据配置文件执行禁用内存主动回收策略的操作
        """
        zone_reclaim_mode = self.zone_reclaim

        valid_memory_values = [0, 1, 2, 4]
        if zone_reclaim_mode not in valid_memory_values:
            raise RuntimeError(
                f"overcommit_memory 配置值非法！当前值：'{zone_reclaim_mode}'，"
                f"合法值仅支持：{valid_memory_values} "
            )

        try:
            # 检查是否已存在配置
            check_cmd = ["grep", "-q", "^vm.zone_reclaim_mode", "/etc/sysctl.conf"]
            run_cmd(check_cmd)
            run_cmd(["sed", "-i", f"s/^vm.zone_reclaim_mode=.*/vm.zone_reclaim_mode={zone_reclaim_mode}/", "/etc/sysctl.conf"])
        except RuntimeError:
            run_cmd(f"echo vm.zone_reclaim_mode={zone_reclaim_mode} >> /etc/sysctl.conf",is_str=True)
        run_cmd(["sysctl", "-p"])