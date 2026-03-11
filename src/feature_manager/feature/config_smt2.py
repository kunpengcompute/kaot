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
import re
from src.feature_manager.feature import register_feature
from src.feature_manager.feature.base import BaseFeature
from src.utils.log import get_logger
from src.utils.common import run_cmd
from typing import List

logger = get_logger(__name__)

FEATURE_NAME = "config_smt2"
FEATURE_DES = "配置超线程"


@register_feature(scenarios=["boundary_gateway_appliance", "common"])
class CheckSMT2(BaseFeature):
    name: str = FEATURE_NAME
    SMT2_status: str = 'enable'

    def get_current_config(self) -> dict:
        self.deploy = "NA"
        output = run_cmd(['lscpu'])
        for line in output.split('\n'):
            if 'Thread(s) per core' in line:
                per_core = line.split(':')[1].strip()
                if per_core == '1':
                    self.SMT2_status = 'disable'
        config = self.model_dump()
        logger.debug(f"Optimization Item {self.name} current config yaml is generated")
        return config

    def _show_smt_hint(self, is_new_920_mode, SMT2_status):
        """显示SMT配置提示信息"""
        if is_new_920_mode:
            # 根据SMT2_status的值确定提示内容
            if SMT2_status == 'enable':
                status_text = "设置为 Enabled(开启)"
            else:
                status_text = "设置为 Disabled(关闭)"
            
            hint = f"""
    ╔══════════════════════════════════════════════════════════╗
    ║                   超线程(SMT)配置指南                    ║
    ╠══════════════════════════════════════════════════════════╣
    ║  1. 重启服务器进入BIOS                                   ║
    ║  2. 进入 Advanced 菜单                                   ║
    ║  3. 选择 Power and Performance Configuration             ║
    ║  4. 选择 CPU PM Control                                  ║
    ║  5. 找到 SMT2 选项                                       ║
    ║  6. {status_text:<46}  ║
    ║  7. 按 F10 保存并退出                                    ║
    ╚══════════════════════════════════════════════════════════╝
    """
            logger.warning(hint)
        else:
            logger.warning("⚠️  当前920平台不支持超线程(SMT)特性")

    def _apply_config_impl(self):
        """
        根据配置文件执行开启/关闭超线程操作
        """
        # 配置参数
        SMT2_status = self.SMT2_status
        valid_statuses = ['disable', 'enable']  # 注意大小写
        if SMT2_status not in valid_statuses:
            raise ValueError(f"参数校验错误: SMT2_status 必须是 '{' 或 '.join(valid_statuses)}'，当前值为 '{SMT2_status}'")
       
        dmidecode_output = run_cmd(['dmidecode', '-t', '4'], timeout=15)
        is_new_920_mode = '0xd01' not in dmidecode_output.lower()

        self._show_smt_hint(is_new_920_mode, SMT2_status)