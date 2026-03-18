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
from typing import Optional
from src.feature_manager.feature import register_feature
from src.feature_manager.feature.base import BaseFeature
from src.utils.log import get_logger
from src.utils.db_config_utils import get_config_file_lines, find_last_value_in_config, update_config_file
from src.utils.env import get_memory_info
import math             

logger = get_logger(__name__)


FEATURE_NAME = "optimize_kingbase_database_config"
FEATURE_DES = "金仓数据库配置调优"


@register_feature(scenarios=["kingbase_database"])
class OptimizeKingbaseDatabaseConfig(BaseFeature):
    name: str = FEATURE_NAME
    config_mapping_apps_name: str = "kingbase_database"
    config_path: str = "/opt/Kingbase/ES/V8/data/kingbase.conf"
    config_bak_path: str = ""
    
    
    def _calc_shared_buffers():
        try:
            mem_str = get_memory_info()
            mem_gb = float(mem_str.split()[0])
            val = mem_gb * 0.65
            val_int = math.ceil(val)
            return f"{val_int}GB"
        except Exception:
            return "NA"
    shared_buffers: Optional[str] = _calc_shared_buffers()  # 65%内存，向上取整
    checkpoint_timeout: Optional[str] = "20min"  # 单位min
    bgwriter_delay: Optional[str] = "10ms"  # 单位ms
    max_wal_size: Optional[str] = "300GB"  # 单位GB
    checkpoint_completion_target: Optional[float] = 0.9  # 0-1之间的小数
    max_connections: Optional[int] = 2048

    def get_current_config(self) -> Optional[dict]:
        self.deploy = "NA"
        """
        1. 根据config_path找到数据库配置文件
        2. 构建非配置参数列表（name, config_path, config_bak_path）
        3. 其他参数从配置文件查找最后一个值并更新self.__dict__
        若找不到配置文件则返回None
        """
        non_config_keys = {"name", "config_path", "config_bak_path","deploy","config_mapping_apps_name"}
        config_lines = get_config_file_lines(self.config_path)
        if not config_lines:
            logger.info(f"Config file {self.config_path} not found, skip this optimization item and backup.")
            return None
        
        for key in self.__dict__:
            if key in non_config_keys:
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
        config_dict = self.model_dump()
        # 不在此处将None转为'NA'，直接返回，展示层/序列化时再处理
        return config_dict

    def _apply_config_impl(self) -> dict:
        """
        调用db_config_utils工具写回配置文件。
        """
        non_config_keys = {"name", "config_path", "config_bak_path","deploy","config_mapping_apps_name"}
        config_dict = {k: v for k, v in self.__dict__.items() if k not in non_config_keys}
        success = update_config_file(self.config_path, config_dict, non_config_keys)
        if success:
            logger.info(f"Kingbase Config file {self.config_path} updated successfully.")
            logger.warning("Please restart the Kingbase database to make the new configuration parameters take effect!")
            return {"status": "success", "message": f"Config file updated: {self.config_path}. Please restart the database to apply the new configuration."}
        else:
            return {"status": "error", "message": f"Failed to update config file: {self.config_path}"}
