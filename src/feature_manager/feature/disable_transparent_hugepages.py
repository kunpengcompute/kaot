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
import re
from src.feature_manager.feature import register_feature
from src.feature_manager.feature.base import BaseFeature
from src.utils.log import get_logger

logger = get_logger(__name__)


FEATURE_NAME = "disable_transparent_hugepages"
FEATURE_DES = "禁用透明大页"


@register_feature(scenarios=["boundary_gateway_appliance"])
class HugePageDisableFeature(BaseFeature):
    name: str = FEATURE_NAME
    enabled: str = "never"
    defrag: str = "never"

    def get_current_config(self) -> dict:
        self.deploy = "NA"
        paths = {
            "enabled": "/sys/kernel/mm/transparent_hugepage/enabled",
            "defrag": "/sys/kernel/mm/transparent_hugepage/defrag",
        }
        for key, path in paths.items():
            with open(path, "r", encoding="utf-8") as f:
                # 文件内容可能是 "[never] always" 这种格式，带方括号表示当前值
                content = f.read().strip()
                # 正则提取 [xxx] 之间的值
                match = re.search(r"\[([^]]+)\]", content)
                if match:
                    value = match.group(1)
                else:
                    value = content.split()[0] if content else ""
                self.__dict__[key] = value
        config = self.model_dump()
        logger.debug(f"Optimization Item {self.name} current config yaml is generated")
        return config

    def _apply_config_impl(self):
        """
        根据配置文件执行禁用透明大页的操作
        """
        # 配置参数：两个值都是 "never"
        enabled = self.enabled
        defrag = self.defrag
        enabled_list = ["always", "madvise", "never"]
        defrag_list = ["always", "defer", "defer+madvise", "madvise", "never"]
        if enabled not in enabled_list:
            raise RuntimeError(
                f"透明大页 enabled 配置值非法！"
                f"当前值：'{enabled}'，"
                f"合法值仅支持：{sorted(enabled_list)} "
                f"（可执行命令 cat /sys/kernel/mm/transparent_hugepage/enabled 查看）"
            )
        if defrag not in defrag_list:
            raise RuntimeError(
                f"透明大页 defrag 配置值非法！"
                f"当前值：'{defrag}'，"
                f"合法值仅支持：{sorted(defrag_list)} "
                f"（可执行命令 cat /sys/kernel/mm/transparent_hugepage/defrag 查看）"
            )
        paths = {
            "/sys/kernel/mm/transparent_hugepage/enabled": enabled,
            "/sys/kernel/mm/transparent_hugepage/defrag": defrag,
        }

        for path, value in paths.items():
            logger.info(f"Setting {path} to {value}")
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(str(value))
            except OSError as io_err:
                raise OSError(f"Failed to write {value} to {path}") from io_err
