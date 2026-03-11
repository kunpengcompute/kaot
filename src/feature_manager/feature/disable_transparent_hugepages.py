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
import os
from src.feature_manager.feature import register_feature
from src.feature_manager.feature.base import BaseFeature
from src.utils.log import get_logger
from src.utils.common import run_cmd

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
        enabled_path = "/sys/kernel/mm/transparent_hugepage/enabled"
        defrag_path = "/sys/kernel/mm/transparent_hugepage/defrag"
        if enabled not in enabled_list:
            raise RuntimeError(
                f"透明大页 enabled 配置值非法！"
                f"当前值：'{enabled}'，"
                f"合法值仅支持：{sorted(enabled_list)} "
                f"（可执行命令 cat {enabled_path} 查看）"
            )
        if defrag not in defrag_list:
            raise RuntimeError(
                f"透明大页 defrag 配置值非法！"
                f"当前值：'{defrag}'，"
                f"合法值仅支持：{sorted(defrag_list)} "
                f"（可执行命令 cat {defrag_path} 查看）"
            )

        SERVICE_PATH = "/etc/systemd/system/kaot.service"
        if not os.path.exists(SERVICE_PATH):
            import textwrap
            template = textwrap.dedent(
            f"""
            [Unit]
            Description=Configure kaot
            After=multi-user.target

            [Service]
            Type=oneshot
            ExecStart=/bin/bash -c "echo {enabled} > {enabled_path}"
            ExecStart=/bin/bash -c "echo {defrag} > {defrag_path}"

            [Install]
            WantedBy=multi-user.target
            """)
            logger.info(f"{SERVICE_PATH} does not exist. Creating with default content.")
            with open(SERVICE_PATH, "w", encoding="utf-8") as f:
                f.write(template)
        else:
            import subprocess
            logger.info(f"{SERVICE_PATH} exists. Modifying as needed.")
            exec_enabled_line = f'/bin/bash -c "echo {enabled} > {enabled_path}"'
            exec_defrag_line  = f'/bin/bash -c "echo {defrag} > {defrag_path}"'
            def line_exists(pattern: str) -> bool:
                result = subprocess.run(
                    ["grep", "-qE", pattern, SERVICE_PATH],
                    capture_output=True
                )
                return result.returncode == 0

            def sed_replace(pattern: str, replacement: str):
                run_cmd(["sed", "-i", f"s|{pattern}|{replacement}|", SERVICE_PATH])

            def sed_append_to_service(line: str):
                run_cmd(["sed", "-i", f"/\\[Service\\]/a\\{line}", SERVICE_PATH])

            enabled_pattern = f"ExecStart.*{re.escape(enabled_path)}"
            if line_exists(enabled_pattern):
                sed_replace(
                    f"ExecStart.*{enabled_path}.*",
                    f"ExecStart={exec_enabled_line}"
                )
            else:
                sed_append_to_service(f"ExecStart={exec_enabled_line}")

            defrag_pattern = f"ExecStart.*{re.escape(defrag_path)}"
            if line_exists(defrag_pattern):
                sed_replace(
                    f"ExecStart.*{defrag_path}.*",
                    f"ExecStart={exec_defrag_line}"
                )
            else:
                sed_append_to_service(f"ExecStart={exec_defrag_line}")

            logger.info(f"{SERVICE_PATH} updated successfully.")
        run_cmd(["systemctl", "daemon-reload"])
        run_cmd(["systemctl", "enable", "kaot"])
        run_cmd(["systemctl", "start", "kaot"])

        logger.info(f"Setting {enabled_path} to {enabled}")
        logger.info(f"Setting {defrag_path} to {defrag}")