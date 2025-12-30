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
import subprocess
from src.feature_manager.feature import register_feature
from src.feature_manager.feature.base import BaseFeature
from src.utils.log import get_logger

logger = get_logger(__name__)

FEATURE_NAME = "check_boostkit_hyperscan_installed"
FEATURE_DES = "检查hyperscan是否安装"


@register_feature(scenarios=["boundary_gateway_appliance"])
class CheckBoostKitHyperscanInstalled(BaseFeature):
    name: str = FEATURE_NAME
    boostkit_hyperscan_install_status: str = "installed"

    def get_current_config(self) -> dict:
        """
        全局查找所有以 libhs_runtime 开头的文件，遍历这些文件，
        执行 strings + 文件路径 | grep -i "KHSEL"，如有返回则判定已安装，否则未安装。
        """
        self.deploy = "NA"
        found = False
        # 查找所有 libhs_runtime* 文件
        proc = subprocess.run(
            ["find", "/", "-type", "f", "-name", "libhs_runtime*"],
            capture_output=True,
            text=True,
            check=False,
        )
        file_list = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        logger.debug(f"Found libhs_runtime files: {file_list}")

        for fpath in file_list:
            # strings | grep -i KHSEL
            strings_proc = subprocess.run(
                ["strings", fpath],
                capture_output=True,
                text=True,
                check=False,
            )
            grep_proc = subprocess.run(
                ["grep", "-i", "KHSEL"],
                input=strings_proc.stdout,
                capture_output=True,
                text=True,
                check=False,
            )
            if grep_proc.stdout.strip():
                found = True
                logger.warning(f"KHSEL marker found in {os.path.abspath(fpath)}")
                break

        self.boostkit_hyperscan_install_status = "installed" if found else "uninstalled"

        config = self.model_dump()
        logger.debug(f"Optimization Item {self.name} current config yaml is generated")
        return config

    def _apply_config_impl(self) -> dict:
        """
        状态查询并给出英文指引。
        """
        status = self.boostkit_hyperscan_install_status

        # 获取kaot安装路径
        pip_proc = subprocess.run(
            ["pip", "show", "kaot"],
            capture_output=True,
            text=True,
            check=False,
        )
        location = ""
        for line in pip_proc.stdout.splitlines():
            if line.startswith("Location:"):
                location = line.split(":", 1)[1].strip()
                break
        install_dir = (
            f"{location}/kaot/install/opensource"
            if location
            else "<kaot_install_path>/kaot/install/opensource"
        )

        if status == "installed":
            logger.warning(
                "BoostKit KSL acceleration library is not installed. "
                "Please run 'kaot install -n boostkit_ksl' to install it first."
            )
            logger.warning(
                f"After installation, please go to the directory '{os.path.abspath(install_dir)}' and run the script 'hyperscan_build.sh' to compile Hyperscan with Kunpeng BoostKit KSL acceleration."
            )
            logger.warning(
                "To compile, execute 'sh hyperscan_build.sh'.\n"
                "If you do not provide parameters, the script will create an 'install_files' directory in the script's location, "
                "download the required packages from the internet, and then build Hyperscan automatically.\n"
                "If you use the '-d' parameter, the script will look for the required packages in the specified directory for compilation. "
                "In this case, you need to prepare all required packages in advance."
            )
            return {
                "status": "success",
                "message": (
                    "BoostKit KSL is not installed. "
                    "Run 'python src.py install -n boostkit_ksl -d [specific directory]' first, then go to "
                    f"'{os.path.abspath(install_dir)}' and run 'hyperscan_build.sh' to build the Kunpeng-accelerated Hyperscan."
                ),
            }
        else:
            logger.warning(
                "To uninstall the KSL package, please run: kaot install -u -n boostkit_ksl"
            )
            logger.warning(
                "To compile native Hyperscan, use the v5.4.2.aarch64.zip file from the directory specified by the -d parameter when you previously ran hyperscan.sh."
            )
            logger.warning(
                f"If you did not specify a directory, please use v5.4.2.aarch64.zip in the directory '{os.path.abspath(install_dir)}/install_files' to compile native Hyperscan."
            )
            return {
                "status": "success",
                "message": (
                    "BoostKit KSL is installed. "
                    "To uninstall, run 'kaot install -u -n boostkit_ksl'. "
                    "To build native Hyperscan, use the v5.4.2.aarch64.zip from your previous -d directory, "
                    f"or from '{os.path.abspath(install_dir)}/install_files' if not specified."
                ),
            }
