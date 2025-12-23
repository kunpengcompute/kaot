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
# ===========================================================================import subprocess
import re
from src.feature_manager.feature import register_feature
from src.feature_manager.feature.base import BaseFeature
from src.utils.log import get_logger

logger = get_logger(__name__)

FEATURE_NAME = "config_hugepages"
FEATURE_DES = "使用大页内存"


@register_feature(scenarios=["boundary_gateway_appliance"])
class ConfigHugepages(BaseFeature):
    name: str = FEATURE_NAME
    hugepagesz: str = "1G"
    hugepages: int = 4

    def get_current_config(self) -> dict:
        config_keys = [k for k in self.__dict__.keys() if k != "name"]
        self.deploy = "NA"
        self.hugepagesz = "NA"
        self.hugepages = -1
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
                            if k == "hugepages":
                                self.__dict__[k] = int(v)
            else:
                raise RuntimeError("GRUB_CMDLINE_LINUX not found")
        config = self.model_dump()
        logger.debug(f"Feature {self.name} current config yaml is generated")
        return config

    def _format_hugepage_size(self, size):
        kb = int(size.rstrip("kB"))
        if kb >= 1024 * 1024:  # 1GB = 1024*1024 KB
            return f"{kb // (1024 * 1024)}G"
        elif kb >= 1024:  # 1MB = 1024 KB
            return f"{kb // 1024}M"
        else:
            return f"{kb}K"

    def _parse_size_to_kb(self, size_str: str) -> int:
        """
        将字符串形式的内存大小（如 '64MB', '1GB', '2048KB'）转换为 KB 整数
        支持单位：KB, MB, GB
        """
        size_str = size_str.strip().upper()
        match = re.match(r"(\d+)(K|M|G)", size_str)
        if not match:
            raise ValueError(f"Failed to parse memory size: {size_str}")
        value, unit = match.groups()
        value = int(value)
        if unit == "K":
            return value
        elif unit == "M":
            return value * 1024
        elif unit == "G":
            return value * 1024 * 1024
        else:
            raise ValueError(f"Unknown unit: {unit}")

    def update_grub_cmdline(
        self, hugepagesz: str, hugepages: int, grub_file="/etc/default/grub"
    ):
        """
        修改 /etc/default/grub 文件中的 GRUB_CMDLINE_LINUX 行，添加或更新 hugepages 参数
        """
        with open(grub_file, "r") as f:
            lines = f.readlines()

        new_lines = []
        pattern = re.compile(r'^(GRUB_CMDLINE_LINUX\s*=\s*")(.*)(")$')

        for line in lines:
            match = pattern.match(line)
            if match:
                prefix, content, suffix = match.groups()

                # 删除已有的 hugepages 参数，避免重复
                content = re.sub(r"hugepagesz=\S+", "", content)
                content = re.sub(r"hugepages=\S+", "", content)

                # 拼接新的参数
                extra = f"hugepagesz={hugepagesz} hugepages={hugepages}"
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
            "GRUB_CMDLINE_LINUX has been updated. Changes will take effect after reboot."
        )

    def _extract_from_fstab(self):
        """
        从 /etc/fstab 中提取所有 hugetlbfs 挂载项的 pagesize 值。

        Returns:
            List[str]: 例如 ['2M', '1G']
        """
        pagesizes = []
        try:
            with open("/etc/fstab", "r") as f:
                for line in f:
                    line = line.strip()
                    # 跳过空行和注释
                    if not line or line.startswith("#"):
                        continue
                    # 仅处理包含 hugetlbfs 的行
                    if "hugetlbfs" in line:
                        match = re.search(r"pagesize=(\S+)", line)
                        if match:
                            pagesizes.append(match.group(1))
        except FileNotFoundError:
            raise RuntimeError(
                "/etc/fstab not found. This file is expected to exist on a standard Linux system."
            )
        except PermissionError:
            raise RuntimeError(
                "Permission denied while reading /etc/fstab. Please run the program as root."
            )

        return pagesizes

    def _apply_config_impl(self):
        import os

        """
        根据配置文件执行配置内存大页的操作
        """
        exist_hugepagesz = self._extract_from_fstab()
        hugepagesz = self.hugepagesz
        hugepages = self.hugepages

        valid_hugepagesz_values = []
        content = os.listdir("/sys/kernel/mm/hugepages")
        for item in content:
            _, val = item.split("-", 1)
            valid_hugepagesz_values.append(val)
        for i in range(len(valid_hugepagesz_values)):
            valid_hugepagesz_values[i] = self._format_hugepage_size(
                valid_hugepagesz_values[i]
            )

        if hugepagesz not in valid_hugepagesz_values:
            raise RuntimeError(
                f"Invalid default_hugepagesz configuration! Current value: '{hugepagesz}', "
                f"valid values are: {valid_hugepagesz_values}"
            )
        if hugepages < 0:
            raise RuntimeError(
                f"Invalid hugepages configuration! Current value: '{hugepages}', must be a non-negative integer"
            )
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total_kb = int(line.split()[1])
                    hugepagesz_kb = self._parse_size_to_kb(hugepagesz)
                    if hugepagesz_kb * hugepages >= total_kb:
                        raise RuntimeError(
                            f"Invalid hugepages configuration! Current value: '{hugepages}', "
                            f"hugepages * hugepagesz_kb = {hugepagesz_kb * hugepages}, total memory = {total_kb}"
                        )
        self.update_grub_cmdline(hugepagesz=hugepagesz, hugepages=hugepages)

        if hugepagesz in exist_hugepagesz:
            logger.warning(
                f"Huge pages with page size {hugepagesz} already exist; no configuration needed."
            )
            return

        commands = [
            "grub2-mkconfig -o /boot/grub2/grub.cfg",
            f"mkdir -p /mnt/kap/huge_{hugepagesz}",
            f'echo "none /mnt/kap/huge_{hugepagesz} hugetlbfs pagesize={hugepagesz} 0 0" >> /etc/fstab',
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
