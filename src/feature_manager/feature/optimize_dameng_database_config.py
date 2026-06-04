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
from typing import Optional
from src.feature_manager.feature import register_feature
from src.feature_manager.feature.base import BaseFeature
from src.utils.log import get_logger

logger = get_logger(__name__)

FEATURE_NAME = "optimize_dameng_database_config"
FEATURE_DES = "达梦数据库配置调优"


def _get_cpu_count() -> int:
    return os.cpu_count() or 1


def _get_available_memory_mb() -> int:
    try:
        import psutil
        return int(psutil.virtual_memory().total / (1024 * 1024))
    except ImportError:
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) // 1024
        except (FileNotFoundError, IndexError, ValueError):
            pass
        return 4096


def _is_prime(n: int) -> bool:
    if n < 2:
        return False
    if n < 4:
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i + 2) == 0:
            return False
        i += 6
    return True


def _next_prime_gt(n: int) -> int:
    candidate = n + 1
    while not _is_prime(candidate):
        candidate += 1
    return candidate


@register_feature(scenarios=["dameng_database"])
class OptimizeDamengDatabaseConfig(BaseFeature):
    name: str = FEATURE_NAME
    config_path: str = "/opt/dmdbms/data/DAMENG/dm.ini"
    config_bak_path: str = ""
    config_mapping_apps_name: str = "dameng_database"

    _cpu = _get_cpu_count()
    _mem_mb = _get_available_memory_mb()

    # ========== 事务合并提交 ==========
    COMMIT_BATCH: Optional[int] = 32
    COMMIT_BATCH_TIMEOUT: Optional[int] = 5

    # ========== 内存缓冲区优化 ==========
    MAX_OS_MEMORY: Optional[int] = 90
    MEMORY_POOL: Optional[int] = int(_mem_mb * 0.25)
    MEMORY_TARGET: Optional[int] = int(_mem_mb * 0.25)
    BUFFER: Optional[int] = int(_mem_mb * 0.5)
    BUFFER_POOLS: Optional[int] = _next_prime_gt(_cpu)

    # ========== 磁盘IO优化 ==========
    DIRECT_IO: Optional[int] = 1
    IO_THR_GROUPS: Optional[int] = _cpu

    # ========== 线程配置优化 ==========
    WORKER_THREADS: Optional[int] = _cpu
    TASK_THREADS: Optional[int] = _cpu

    def _parse_dm_ini_value(self, key: str, lines: list) -> Optional[str]:
        """在 dm.ini 行中查找 key 的最后一个有效值，跳过 ; 和 # 注释和章节头"""
        value = None
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith(('#', ';')) or stripped.startswith('['):
                continue
            if '=' in stripped:
                k, v = stripped.split('=', 1)
                if k.strip() == key:
                    raw = v.strip()
                    for comment_char in (';', '#'):
                        idx = raw.find(comment_char)
                        if idx != -1:
                            raw = raw[:idx].strip()
                    value = raw
        return value

    def get_current_config(self) -> Optional[dict]:
        self.deploy = "NA"
        non_config_keys = {"name", "config_path", "config_bak_path", "deploy", "config_mapping_apps_name"}

        if not os.path.exists(self.config_path):
            logger.info(f"Config file {self.config_path} not found, skip this optimization item and backup.")
            return None

        with open(self.config_path, "r", encoding="utf-8") as f:
            config_lines = f.readlines()

        for key in self.__dict__:
            if key in non_config_keys:
                continue
            value = self._parse_dm_ini_value(key, config_lines)
            if value is not None:
                field_type = type(getattr(self, key))
                if field_type in (int, float):
                    try:
                        self.__dict__[key] = field_type(value)
                    except (ValueError, TypeError):
                        self.__dict__[key] = None
                else:
                    self.__dict__[key] = value
            else:
                self.__dict__[key] = None

        logger.debug(f"Optimization Item {self.name} current config loaded from {self.config_path}")
        return self.model_dump()

    def _apply_config_impl(self) -> dict:
        non_config_keys = {"name", "config_path", "config_bak_path", "deploy", "config_mapping_apps_name"}
        keys_to_update = {k: v for k, v in self.__dict__.items() if k not in non_config_keys and v is not None}

        if not os.path.exists(self.config_path):
            error_msg = f"Config file {self.config_path} not found."
            logger.error(error_msg)
            return {"status": "error", "message": error_msg}

        with open(self.config_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # 记录每个key最后一次出现的行号
        last_occurrence = {}
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith(('#', ';')) or stripped.startswith('['):
                continue
            if '=' in stripped:
                k = stripped.split('=', 1)[0].strip()
                if k in keys_to_update:
                    last_occurrence[k] = idx

        # 更新已有参数（仅改最后一个出现的位置，保留原格式和行尾注释）
        new_lines = lines[:]
        for k in keys_to_update:
            if k in last_occurrence:
                idx = last_occurrence[k]
                line = lines[idx]
                prefix = line[:len(line) - len(line.lstrip())]

                eq_pos = line.find('=')
                if eq_pos != -1:
                    key_part = line[len(prefix):eq_pos + 1]
                    rhs = line[eq_pos + 1:]
                    val_start_spaces = rhs[:len(rhs) - len(rhs.lstrip())]
                    stripped_rhs = rhs.lstrip()

                    comment_idx = len(stripped_rhs)
                    for c in (';', '#'):
                        p = stripped_rhs.find(c)
                        if p != -1 and p < comment_idx:
                            comment_idx = p

                    val_and_padding = stripped_rhs[:comment_idx]
                    new_val_str = str(keys_to_update[k])
                    actual_old_val = val_and_padding.rstrip()
                    trailing_padding = val_and_padding[len(actual_old_val):]
                    after_part = stripped_rhs[comment_idx:]

                    new_lines[idx] = f"{prefix}{key_part}{val_start_spaces}{new_val_str}{trailing_padding}{after_part}"

        # 追加不存在的参数到文件末尾
        existing_keys = set(last_occurrence.keys())
        for k in keys_to_update:
            if k not in existing_keys:
                new_lines.append(f"{k} = {keys_to_update[k]}\n")

        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            logger.info(f"Dameng Config file {self.config_path} updated successfully.")
            logger.warning("Please restart the Dameng database to make the new configuration parameters take effect!")
            return {"status": "success", "message": f"Config file updated: {self.config_path}. Please restart the database to apply the new configuration."}
        except Exception as e:
            logger.error(f"Failed to update config file: {e}")
            return {"status": "error", "message": f"Failed to update config file: {e}"}
