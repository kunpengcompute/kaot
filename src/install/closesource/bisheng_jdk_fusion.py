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

def install_bisheng_jdk_fusion(install_dir):
    # 检查root权限
    if hasattr(os, 'geteuid'):
        if os.geteuid() != 0:
            logger.error("Root privileges are required to install BiSheng JDK Fusion. Please run as root or use sudo.")
            return

    # 检查当前JAVA版本兼容性
    try:
        from src.feature_manager.feature.check_bisheng_fusion_jdk_installed import parse_jdk_info, COMPATIBLE_STR, SAME_AS_FUSION_VERSION
        jdk_info = parse_jdk_info()
        compatibility = jdk_info.get("compatibility", "unknown")
        if compatibility == COMPATIBLE_STR:
            logger.info(f"Current JAVA version compatibility check passed")
        elif compatibility == SAME_AS_FUSION_VERSION:
            logger.info(f"Current JAVA version is the same as BiSheng JDK Fusion version,stop installation to avoid conflicts")
            return
        else:
            logger.error(f"Current JAVA version is not compatible with BiSheng JDK Fusion: {jdk_info}")
            return
           
    except Exception as e:
        logger.error(f"Failed to check JAVA version compatibility: {e}")
        return

    logger.info("Start installing BiSheng JDK Fusion...")
    # 查找包含bisheng、fusion、aarch64关键字的tar包
    tarfile = None
    for fname in os.listdir(install_dir):
        if fname.endswith(".tar.gz") and all(k in fname.lower() for k in ["bisheng", "fusion", "aarch64"]):
            tarfile = fname
            break
    if not tarfile:
        logger.error("No installation package found with keywords 'bisheng', 'fusion', 'aarch64' in the filename.")
        return
    package_path = os.path.join(install_dir, tarfile)
    # 解压tar包
    try:
        subprocess.run(["tar", "-xzf", tarfile], check=True, cwd=install_dir)
        logger.info(f"Package {tarfile} extracted successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to extract tar package: {e}")
        return
    # 查找解压后的目录，包含bisheng、fusion、aarch64关键字
    extracted_dir = None
    for item in os.listdir(install_dir):
        if (
            os.path.isdir(os.path.join(install_dir, item))
            and all(k in item.lower() for k in ["bisheng", "fusion", "aarch64"])
        ):
            extracted_dir = os.path.join(install_dir, item)
            break
    if not extracted_dir:
        logger.error("Extracted directory not found with keywords 'bisheng', 'fusion', 'aarch64'.")
        return
    dest_dir = "/usr/local/bisheng_jdk_fusion"
    # 复制到目标目录
    try:
        subprocess.run(["cp", "-r", extracted_dir, dest_dir], check=True)
        logger.info(f"Copied JDK Fusion to {dest_dir}.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to copy files: {e}")
        return
    # 设置系统级环境变量并持久化到/etc/profile.d/bisheng_jdk_fusion.sh
    profile_d_path = "/etc/profile.d/bisheng_jdk_fusion.sh"
    env_lines = [
        f'export JAVA_HOME={dest_dir}\n',
        'export PATH=$JAVA_HOME/bin:$PATH\n'
    ]
    try:
        with open(profile_d_path, "w", encoding="utf-8") as f:
            f.writelines(env_lines)
        logger.info(f"System environment variables set and persisted in {profile_d_path}.")
    except Exception as e:
        logger.error(f"Failed to persist system environment variables: {e}")
        return
    logger.warning(f"BiSheng JDK Fusion installation completed. Please run 'source {profile_d_path}' in your shell to activate JAVA_HOME and PATH, then use 'java -version' or 'python3 kaot.py basecfg' to verify installation.")


def uninstall_bisheng_jdk_fusion():
    # 检查root权限
    if hasattr(os, 'geteuid'):
        if os.geteuid() != 0:
            logger.error("Root privileges are required to uninstall BiSheng JDK Fusion. Please run as root or use sudo.")
            return
    logger.info("Start uninstalling BiSheng JDK Fusion...")
    # 删除系统级环境变量文件
    profile_d_path = "/etc/profile.d/bisheng_jdk_fusion.sh"
    try:
        if os.path.exists(profile_d_path):
            os.remove(profile_d_path)
            logger.info(f"Removed system environment file {profile_d_path}.")
        else:
            logger.info(f"System environment file {profile_d_path} does not exist.")
    except Exception as e:
        logger.error(f"Failed to remove system environment file: {e}")
        return
    # 删除安装目录
    dest_dir = "/usr/local/bisheng_jdk_fusion"
    try:
        subprocess.run(["rm", "-rf", dest_dir], check=True)
        logger.info(f"Removed directory {dest_dir}.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to remove directory: {e}")
        return
    logger.warning(f"BiSheng JDK Fusion uninstallation completed. Please run 'source /etc/profile' or re-login, then use 'java -version' or 'python3 kaot.py basecfg' to verify environment restoration.")

