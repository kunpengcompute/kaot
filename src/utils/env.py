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
import platform
import subprocess
import psutil
from typing import Optional
from pydantic import BaseModel


class EnvConfig(BaseModel):
    os: Optional[str] = "NA"
    cpu: Optional[str] = "NA"
    memory: Optional[str] = "NA"
    uname: Optional[str] = "NA"

    class Config:
        extra = "forbid"


def get_os_info() -> str:
    """获取操作系统信息"""
    with open("/etc/os-release") as f:
        for line in f:
            if line.startswith("PRETTY_NAME="):
                return line.strip().split("=")[1].strip('"')


def get_cpu_info() -> str:
    """
    获取CPU类型
    返回: CPU类型字符串
    """
    try:
        cmd = ["dmidecode", "-t", "processor"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True
        )
        output_lines = [
            line.strip() for line in result.stdout.splitlines()
            if "Version" in line.strip()
        ]
        last_line = output_lines[-1]

        CPU_TYPE = str(last_line)[16:]
        return CPU_TYPE
    except Exception as e:
        raise RuntimeError(f"获取CPU信息失败: {e}")


def get_memory_info() -> str:
    """获取内存信息 (GB)"""
    mem = psutil.virtual_memory()
    return f"{mem.total / (1024 ** 3):.2f} GB"


def get_uname_info() -> str:
    """获取 uname 详细信息"""
    return platform.release()


def get_environment_info() -> EnvConfig:
    """组合各项环境信息生成 EnvConfig"""
    return EnvConfig(
        os=get_os_info(),
        cpu=get_cpu_info(),
        memory=get_memory_info(),
        uname=get_uname_info(),
    )


def check_environment_match(config):
    """
    检查当前环境信息是否与config中的环境信息一致。

    - 一致：打印 info
    - 不一致：raise ValueError，并输出差异信息
    """
    from src.utils.log import get_logger

    logger = get_logger(__name__)

    env_cfg = get_environment_info()
    if env_cfg == config.SYSTEM_INFO:
        logger.debug("Environment matches the configuration")
        return True

    diff = []
    for field in env_cfg.model_fields:
        env_v = getattr(env_cfg, field)
        cfg_v = getattr(config.SYSTEM_INFO, field)
        if env_v != cfg_v:
            diff.append(f"{field}: expected={cfg_v}, actual={env_v}")

    diff_text = "\n".join(diff)
    logger.error("Environment mismatch:\n" + diff_text)
    return False
