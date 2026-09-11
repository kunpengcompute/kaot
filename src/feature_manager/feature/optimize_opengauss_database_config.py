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
import math
import os
import re
from pydantic import BaseModel
from typing import Optional
from src.feature_manager.feature import register_feature
from src.feature_manager.feature.base import BaseFeature
from src.utils.log import get_logger
from src.utils.db_config_utils import get_config_file_lines, find_last_value_in_config, update_config_file, restart_opengauss_db, reload_opengauss_db
from src.utils.env import get_memory_info


logger = get_logger(__name__)


FEATURE_NAME = "optimize_opengauss_database_config"
FEATURE_DES = "opengauss数据库配置调优"

# postmaster 级参数：修改后必须重启数据库才能生效
POSTMASTER_PARAMS = [
    "shared_buffers",
    "enable_thread_pool",
    "thread_pool_attr",
    "enable_double_write",
    "max_connections",
    "max_prepared_transactions",
    "wal_buffers",
    "cstore_buffers",
]


def _calc_shared_buffers():
    try:
        mem_str = get_memory_info()
        mem_gb = float(mem_str.split()[0])
        val = mem_gb * 0.25  # 实测 25% 内存
        val_int = math.ceil(val)
        return f"{val_int}GB"
    except Exception:
        return "NA"


class OpenGaussParams(BaseModel):
    """openGauss 需要改动的参数主体（独立结构体）。

    与特性类元数据（name/config_path/deploy 等）解耦，便于统一读写与对比。
    """
    # ===== 实测 12 项(hard) =====
    shared_buffers: Optional[str] = _calc_shared_buffers()  # 25% 内存，向上取整
    enable_thread_pool: Optional[str] = "on"
    thread_pool_attr: Optional[str] = "'512,8,(cpubind:0-255)'"
    autovacuum: Optional[str] = "on"
    autovacuum_max_workers: Optional[int] = 4
    autovacuum_naptime: Optional[str] = "30s"
    autovacuum_vacuum_scale_factor: Optional[float] = 0.02
    autovacuum_analyze_scale_factor: Optional[float] = 0.01
    bgwriter_delay: Optional[int] = 50
    bgwriter_lru_maxpages: Optional[int] = 1000
    bgwriter_lru_multiplier: Optional[float] = 10
    checkpoint_completion_target: Optional[float] = 0.9
    enable_double_write: Optional[str] = "off"

    # ===== measure 态 / 还原杂项 / 可观测（商用版：可观测 on） =====
    fsync: Optional[str] = "on"
    synchronous_commit: Optional[str] = "on"
    full_page_writes: Optional[str] = "on"
    enable_mergejoin: Optional[str] = "on"
    enable_nestloop: Optional[str] = "on"
    track_activities: Optional[str] = "on"
    enable_resource_track: Optional[str] = "on"
    enable_save_datachanged_timestamp: Optional[str] = "on"

    # ===== 保留的通用有效项 =====
    max_connections: Optional[int] = 2048
    max_prepared_transactions: Optional[int] = 2048
    maintenance_work_mem: Optional[str] = "2GB"
    wal_buffers: Optional[str] = "1GB"
    checkpoint_segments: Optional[int] = 1024
    cstore_buffers: Optional[str] = "16MB"


@register_feature(scenarios=["opengauss_database"])
class OptimizeOpenGaussDatabaseConfig(BaseFeature):
    name: str = FEATURE_NAME
    config_path: str = "/opt/software/opengauss/data/opengauss.conf"
    config_bak_path: str = ""
    config_mapping_apps_name: str = "opengauss_database"
    params: OpenGaussParams = OpenGaussParams()

    def get_current_config(self) -> Optional[dict]:
        self.deploy = "NA"
        """
        1. 根据config_path找到数据库配置文件
        2. 从配置文件查找每个参数最后一个值并更新 params 结构体
        3. 返回 model_dump 供 base/target 对比
        若找不到配置文件则返回None
        """
        config_lines = get_config_file_lines(self.config_path)
        if not config_lines:
            logger.info(f"Config file {self.config_path} not found, skip this optimization item and backup.")
            return None

        for key in self.params.__dict__:
            value = find_last_value_in_config(key, config_lines)
            if value is None:
                setattr(self.params, key, None)
                continue
            field_type = type(getattr(self.params, key))
            if field_type not in (int, float):
                setattr(self.params, key, value)
                continue
            try:
                setattr(self.params, key, field_type(value))
            except Exception:
                setattr(self.params, key, None)
        logger.debug(f"Optimization Item {self.name} current config loaded from {self.config_path}")
        return self.model_dump()

    def _clamp_thread_pool_attr(self):
        """thread_pool_attr 的 cpubind 最高核号超过实际核数时，clamp 到 cpu_count-1（防越界启动失败）。"""
        tpa = getattr(self.params, "thread_pool_attr", None)
        if not tpa:
            return
        text = str(tpa)
        match = re.search(r"cpubind:([\d,\-]+)", text)
        if not match:
            return
        total = os.cpu_count() or 128
        max_cpu = total - 1
        over = False
        for part in match.group(1).split(","):
            part = part.strip()
            if not part:
                continue
            ceiling = int(part.split("-")[1].rstrip()) if "-" in part else int(part)
            if ceiling > max_cpu:
                over = True
                break
        if not over:
            return
        # clamp cpubind 上限到 max_cpu（保留格式：0-X）
        try:
            new_bind = "0-{0}".format(max_cpu)
            text = text.replace(match.group(1), new_bind, 1)
            setattr(self.params, "thread_pool_attr", text)
            logger.warning(
                f"thread_pool_attr cpubind {match.group(1)} exceeds {total} CPUs; "
                f"clamped to {new_bind} to avoid DB start failure."
            )
        except Exception as e:
            logger.warning(f"Failed to clamp thread_pool_attr: {e}")

    def _apply_config_impl(self) -> dict:
        """
        写入 OpenGaussParams 结构体到配置文件。
        postmaster 级参数若被改动，则自动重启数据库以生效。
        """
        self._clamp_thread_pool_attr()
        config_dict = self.params.model_dump()
        success = update_config_file(self.config_path, config_dict)
        if not success:
            return {"status": "error", "message": f"Failed to update config file: {self.config_path}"}
        logger.info(f"OpenGauss Config file {self.config_path} updated successfully.")

        # 判断是否有 postmaster 级参数被改动（需要重启）
        changed_postmaster = []
        if self.config_bak_path and os.path.exists(self.config_bak_path):
            bak_lines = get_config_file_lines(self.config_bak_path)
            for key in POSTMASTER_PARAMS:
                bak_val = find_last_value_in_config(key, bak_lines)
                new_val = config_dict.get(key)
                if str(bak_val).strip() != str(new_val).strip():
                    changed_postmaster.append(key)
        else:
            changed_postmaster = list(POSTMASTER_PARAMS)

        if changed_postmaster:
            ok, restart_msg = restart_opengauss_db(self.config_path)
            if not ok:
                return {
                    "status": "error",
                    "message": (
                        f"Config file updated but database restart FAILED for postmaster params "
                        f"{sorted(changed_postmaster)}. {restart_msg}"
                    ),
                }
            return {
                "status": "success",
                "message": f"Config file updated & database restarted for postmaster params: {sorted(changed_postmaster)}. {restart_msg}",
            }
        logger.info("No postmaster-level params changed; reloading to apply SIGHUP-reloadable params.")
        ok, reload_msg = reload_opengauss_db(self.config_path)
        if not ok:
            return {
                "status": "error",
                "message": (
                    f"Config file updated but database reload FAILED: {reload_msg}"
                ),
            }
        return {
            "status": "success",
            "message": f"Config file updated & database reloaded (SIGHUP) to apply non-postmaster params: {self.config_path}. {reload_msg}",
        }
