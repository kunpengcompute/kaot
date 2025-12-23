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
from abc import abstractmethod
from typing import Dict, Any
from kaot.utils.log import get_logger

logger = get_logger(__name__)

from pydantic import BaseModel


class BaseFeature(BaseModel):
    name: str
    deploy: str = "NA"

    class Config:
        extra = "forbid"

    @abstractmethod
    def get_current_config(self) -> dict:
        """获取当前系统的配置状态"""
        pass

    @abstractmethod
    def _apply_config_impl(self):
        """根据配置执行生效逻辑"""
        pass

    def generate_config(self) -> Dict[str, Any]:
        """
        通用配置生成逻辑（所有子类复用，无需修改）
        :return: 统一格式的配置字典
        """
        self.deploy = "Y"

        config = self.model_dump()
        logger.debug(f"Feature {self.name} config yaml is generated")
        return config

    def apply_config(self):
        """
        基类实现：模板方法（固定执行流程）
        """
        logger.info(
            f"Feature {self.name} config validation passed, starting to apply..."
        )
        self._apply_config_impl()
