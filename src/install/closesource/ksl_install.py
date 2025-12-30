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
from src.utils.log import get_logger

logger = get_logger(__name__)

def install_boostkit_ksl(install_dir):
    logger.info("Installing hyperscan package...")
    zipfile = "BoostKit-ksl_2.5.2.zip"
    package_path = os.path.join(install_dir, zipfile)
    if not os.path.exists(package_path):
        logger.error(f"Installation package {os.path.abspath(package_path)} does not exist.")
        return
    logger.info(f"KSL package path: {os.path.abspath(package_path)}")
    try:
        subprocess.run(["unzip", "-o", zipfile], check=True, cwd=install_dir)
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to unzip installation package: {e}")
        return
    rpm_file = None
    for file in os.listdir(install_dir):
        if file.startswith("boostkit-ksl") and file.endswith(".rpm"):
            rpm_file = file
            break
    if not rpm_file:
        logger.error("No RPM file found after extraction.")
        return
    # 检查是否已安装
    rpm_query = subprocess.run([
        "rpm", "-qa", "boostkit-ksl*"
    ], capture_output=True, text=True, check=False)
    installed_pkgs = [line.strip() for line in rpm_query.stdout.splitlines() if line.strip()]
    if installed_pkgs:
        logger.info(f"boostkit-ksl 已经安装: {installed_pkgs}，跳过安装。")
        return
    logger.info(f"Found RPM file: {os.path.abspath(rpm_file)}, starting installation...")
    try:
        subprocess.run(["rpm", "-ivh", rpm_file], check=True, cwd=install_dir)
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install RPM file: {e}")
        return
    logger.info("boostkit_ksl installation completed successfully.")


def uninstall_boostkit_ksl():
    logger.info("Checking for installed boostkit-ksl RPM package...")
    rpm_query = subprocess.run(
        ["rpm", "-qa", "boostkit-ksl*"],
        capture_output=True,
        text=True,
        check=False,
    )
    pkgs = [line.strip() for line in rpm_query.stdout.splitlines() if line.strip()]
    if not pkgs:
        logger.info("No boostkit-ksl RPM package is currently installed.")
        return
    for pkg in pkgs:
        logger.info(f"Uninstalling package: {pkg}")
        try:
            subprocess.run(["rpm", "-e", pkg], check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to uninstall {pkg}: {e}")
            return
    rpm_query2 = subprocess.run(
        ["rpm", "-qa", "boostkit-ksl*"],
        capture_output=True,
        text=True,
        check=False,
    )
    pkgs_left = [line.strip() for line in rpm_query2.stdout.splitlines() if line.strip()]
    if not pkgs_left:
        logger.info("boostkit_ksl uninstalled successfully.")
    else:
        logger.error(f"Some boostkit-ksl packages remain after uninstall: {pkgs_left}")