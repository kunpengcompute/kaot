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
from src.utils.db_config_utils import get_config_file_lines, find_last_value_in_config, update_config_file

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

    def get_current_config(self) -> Optional[dict]:
        self.deploy = "NA"
        non_config_keys = {"name", "config_path", "config_bak_path", "deploy", "config_mapping_apps_name"}
        config_lines = get_config_file_lines(self.config_path)
        if not config_lines:
            logger.info(f"Config file {self.config_path} not found, skip this optimization item and backup.")
            return None

        for key in self.__dict__:
            if key in non_config_keys:
                continue
            value = find_last_value_in_config(key, config_lines)
            if value is not None:
                field_type = type(getattr(self, key))
                if field_type in (int, float):
                    try:
                        self.__dict__[key] = field_type(value)
                    except Exception:
                        self.__dict__[key] = None
                else:
                    self.__dict__[key] = value
            else:
                self.__dict__[key] = None

        logger.debug(f"Optimization Item {self.name} current config loaded from {self.config_path}")
        config_dict = self.model_dump()
        return config_dict

    def _apply_config_impl(self) -> dict:
        """
        调用db_config_utils工具写回配置文件。
        """
        non_config_keys = {"name", "config_path", "config_bak_path", "deploy", "config_mapping_apps_name"}
        config_dict = {k: v for k, v in self.__dict__.items() if k not in non_config_keys}
        success = update_config_file(self.config_path, config_dict, non_config_keys)
        if success:
            logger.info(f"Dameng Config file {self.config_path} updated successfully.")
            logger.warning("Please restart the Dameng database to make the new configuration parameters take effect!")
            return {"status": "success", "message": f"Config file updated: {self.config_path}. Please restart the database to apply the new configuration."}
        else:
            error_msg = f"Failed to update config file: {self.config_path}"
            logger.error(error_msg)
            return {"status": "error", "message": error_msg}