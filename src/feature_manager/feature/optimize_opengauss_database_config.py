# 全局非配置参数key集合
NON_CONFIG_KEYS = {"name", "config_path", "config_bak_path", "deploy", "config_mapping_apps_name"}
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
from typing import Optional
from src.feature_manager.feature import register_feature
from src.feature_manager.feature.base import BaseFeature
from src.utils.log import get_logger
from src.utils.db_config_utils import get_config_file_lines, find_last_value_in_config, update_config_file
from src.utils.env import get_memory_info


logger = get_logger(__name__)


FEATURE_NAME = "optimize_opengauss_database_config"
FEATURE_DES = "opengauss数据库配置调优"


@register_feature(scenarios=["opengauss_database"])
class OptimizeOpenGaussDatabaseConfig(BaseFeature):
    name: str = FEATURE_NAME
    config_path: str = "/opt/software/opengauss/data/opengauss.conf"
    config_bak_path: str = ""
    config_mapping_apps_name: str = "opengauss_database"
    max_connections: Optional[int] = 2048
    allow_concurrent_tuple_update: Optional[str] = "true"
    audit_enabled: Optional[str] = "off"
    checkpoint_segments: Optional[int] = 1024
    cstore_buffers: Optional[str] = "16MB"
    enable_alarm: Optional[str] = "off"
    full_page_writes: Optional[str] = "off"
    max_files_per_process: Optional[int] = 100000
    max_prepared_transactions: Optional[int] = 2048
    wal_buffers: Optional[str] = "1GB"
    synchronous_commit: Optional[str] = "on"
    maintenance_work_mem: Optional[str] = "2GB"
    vacuum_cost_limit: Optional[int] = 10000
    autovacuum_max_workers: Optional[int] = 10
    autovacuum_vacuum_cost_delay: Optional[int] = 10
    enable_material: Optional[str] = "off"
    wal_log_hints: Optional[str] = "off"
    autovacuum_vacuum_scale_factor: Optional[float] = 0.1
    autovacuum_analyze_scale_factor: Optional[float] = 0.02
    enable_save_datachanged_timestamp: Optional[str] = "false"
    instr_unique_sql_count: Optional[int] = 5000
    advance_xlog_file_num: Optional[int] = 100
    track_counts: Optional[str] = "on"
    track_sql_count: Optional[str] = "on"
    plog_merge_age: Optional[int] = 0
    session_timeout: Optional[int] = 0
    enable_instance_metric_persistent: Optional[str] = "off"
    enable_logical_io_statistics: Optional[str] = "off"
    enable_user_metric_persistent: Optional[str] = "off"
    enable_xlog_prune: Optional[str] = "off"
    fenable_resource_track: Optional[str] = "on"
    remote_read_mode: Optional[str] = "non_authentication"
    wal_level: Optional[str] = "hot_standby"
    hot_standby: Optional[str] = "on"
    hot_standby_feedback: Optional[str] = "off"
    enable_asp: Optional[str] = "off"
    enable_bbox_dump: Optional[str] = "off"
    bgwriter_flush_after: Optional[int] = 32
    wal_keep_segments: Optional[int] = 1025
    xloginsert_locks: Optional[int] = 48
    bgwriter_delay: Optional[int] = 5
    sincremental_checkpoint_timeout: Optional[str] = "5min"
    walwriter_sleep_threshold: Optional[int] = 50000
    xloginsert_locks_2: Optional[int] = 16
    pagewriter_sleep: Optional[str] = "100ms"
    incremental_checkpoint_timeout: Optional[str] = "120s"
    wal_file_init_num: Optional[int] = 30
    pagewriter_thread_num: Optional[int] = 2
    max_redo_log_size: Optional[str] = "400GB"
    max_io_capacity: Optional[str] = "1GB"
    enable_cachedplan_mgr: Optional[str] = "off"
    light_comm: Optional[str] = "on"
    enable_indexscan_optimization: Optional[str] = "on"
    time_record_level: Optional[int] = 1
    
    def _calc_shared_buffers():
        try:
            mem_str = get_memory_info()
            mem_gb = float(mem_str.split()[0])
            val = mem_gb * 0.3
            val_int = math.ceil(val)
            return f"{val_int}GB"
        except Exception:
            return "NA"
    shared_buffers: Optional[str] = _calc_shared_buffers()  # 30%内存，向上取整

    def get_current_config(self) -> Optional[dict]:
        """
        1. 根据config_path找到数据库配置文件
        2. 构建非配置参数列表（name, config_path, config_bak_path）
        3. 其他参数从配置文件查找最后一个值并更新self.__dict__
        若找不到配置文件则返回None
        """
        self.deploy = "NA"
        config_lines = get_config_file_lines(self.config_path)
        if not config_lines:
            logger.info(f"Config file {self.config_path} not found, skip this optimization item.")
            return None
        for key in self.__dict__:
            if key in NON_CONFIG_KEYS:
                continue
            value = find_last_value_in_config(key, config_lines)
            if value is not None:
                # 类型转换：int/float参数自动转换
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
        return self.model_dump()

    def _apply_config_impl(self) -> dict:
        """
        调用db_config_utils工具写回配置文件。
        """
        config_dict = {k: v for k, v in self.__dict__.items() if k not in NON_CONFIG_KEYS}
        success = update_config_file(self.config_path, config_dict, NON_CONFIG_KEYS)
        if success:
            logger.info(f"OpenGauss Config file {self.config_path} updated successfully.")
            logger.warning("Please restart the OpenGauss database to make the new configuration parameters take effect!")
            return {"status": "success", "message": f"Config file updated: {self.config_path}. Please restart the database to apply the new configuration."}
        else:
            return {"status": "error", "message": f"Failed to update config file: {self.config_path}"}
