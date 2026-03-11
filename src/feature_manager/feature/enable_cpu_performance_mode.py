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
import subprocess
import platform
from src.feature_manager.feature import register_feature
from src.feature_manager.feature.base import BaseFeature
from src.utils.log import get_logger

logger = get_logger(__name__)


FEATURE_NAME = "enable_cpu_performance_mode"
FEATURE_DES = "使能CPU高性能模式"


@register_feature(scenarios=["boundary_gateway_appliance", "common", "opengauss_database"])
class EnableCPUPerformanceMode(BaseFeature):
    name: str = FEATURE_NAME
    cpufreq_default_governor: str = "performance"

    def get_current_config(self) -> dict:
        config_keys = [k for k in self.__dict__.keys() if k != "name"]
        self.deploy = "NA"
        self.cpufreq_default_governor = "NA"
        with open("/etc/default/grub", "r") as f:
            # 目标字段都在GRUB_CMDLINE_LINUX行
            content = f.read()
            match = re.search(
                r'^\s*GRUB_CMDLINE_LINUX\s*=\s*"([^"]*)"', content, re.MULTILINE
            )
            if match:
                cmdline_value = match.group(1)
                for part in cmdline_value.split():
                    if "=" in part:
                        k, v = part.split("=", 1)
                        if k in config_keys:
                            self.__dict__[k] = v
            else:
                raise RuntimeError("GRUB_CMDLINE_LINUX not found")
        config = self.model_dump()
        logger.debug(f"Optimization Item {self.name} current config yaml is generated")
        return config

    def _update_grub(
        self,
        cpufreq_default_governor: str,
        grub_file="/etc/default/grub",
    ):
        """
        修改 /etc/default/grub 文件中的 GRUB_CMDLINE_LINUX 行
        """
        with open(grub_file, "r") as f:
            lines = f.readlines()

        new_lines = []
        pattern = re.compile(r'^(GRUB_CMDLINE_LINUX\s*=\s*")(.*)(")$')

        for line in lines:
            match = pattern.match(line)
            if match:
                prefix, content, suffix = match.groups()

                # 删除已有的 性能模式 参数，避免重复
                content = re.sub(r"cpufreq.default_governor=\S+", "", content)

                # 拼接新的参数
                extra = f"cpufreq.default_governor={cpufreq_default_governor}"
                # 去掉多余空格再拼接
                content = content.strip()
                if content:
                    content = f"{content} {extra}"
                else:
                    content = extra

                line = f"{prefix}{content}{suffix}\n"

            new_lines.append(line)

        # 写回文件
        with open(grub_file, "w") as f:
            f.writelines(new_lines)

        logger.warning(
            "GRUB_CMDLINE_LINUX has been updated. The changes will take effect after reboot."
        )

    def _apply_config_impl(self):
        """
        根据配置文件执行启用高性能模式的操作
        """
        cpufreq_default_governor = self.cpufreq_default_governor
        # 硬编码支持的CPU调速器
        valid_values = ["performance", "powersave", "userspace", "ondemand", "conservative", "schedutil"]
        kernel_version = platform.release()
        match = re.match(r'^(\d+)\.(\d+)', kernel_version)

        if match:
            major, minor = int(match.group(1)), int(match.group(2))
            if (major > 4) or (major == 4 and minor >= 7):
                valid_values.append("schedutil")

        if cpufreq_default_governor not in valid_values:
            raise RuntimeError(
                f"Invalid cpufreq.default_governor configuration! "
                f"Current value: {cpufreq_default_governor}, "
                f"valid values are: {valid_values}"
            )

        self._update_grub(cpufreq_default_governor=cpufreq_default_governor)

        commands = [
            ["grub2-mkconfig","-o","/boot/grub2/grub.cfg"],
        ]

        timeout = 10
        for cmd in commands:
            logger.info(f"Executing: {cmd}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True,
            )
            if result.stdout.strip():
                logger.info(f"Command {cmd} output: {result.stdout.strip()}")
