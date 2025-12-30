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
import subprocess
from src.feature_manager.feature import register_feature
from src.feature_manager.feature.base import BaseFeature
from src.utils.log import get_logger
import shlex

logger = get_logger(__name__)


FEATURE_NAME = "update_sched_rt_runtime"
FEATURE_DES = "关闭实时任务运行时间限制"


@register_feature(scenarios=["boundary_gateway_appliance"])
class UpdateSchedRtRuntime(BaseFeature):
    name: str = FEATURE_NAME
    sched_rt_runtime: int = -1

    def get_current_config(self) -> dict:
        """
        查询 /proc/sys/kernel/sched_rt_runtime_us 的当前值,
        返回 feature 的配置字典，extra field 名称为 sched_rt_runtime_us。
        异常由调用方统一处理，不在此捕获。
        """
        self.deploy = "NA"

        proc = subprocess.run(
            ["cat", "/proc/sys/kernel/sched_rt_runtime_us"],
            capture_output=True,
            text=True,
            check=False,
        )
        value = (proc.stdout or proc.stderr or "").strip() or "unknown"

        self.sched_rt_runtime = int(value)
        config = self.model_dump()
        logger.debug(f"Optimization Item {self.name} current config yaml is generated")
        return config

    def _apply_config_impl(self) -> dict:
        """
        根据输入配置字典中的 sched_rt_runtime_us 字段（整数类型），
        写入 /proc/sys/kernel/sched_rt_runtime_us。
        """
        value = self.sched_rt_runtime

        # 检查值是否为 None
        if value is None:
            logger.warning(
                "The 'sched_rt_runtime_us' parameter is missing. The unit of this parameter is microseconds (us)."
            )
            return {
                "status": "error",
                "message": "Missing parameter: sched_rt_runtime_us",
            }

        # 将整数转换为安全的字符串用于命令执行
        value_str = str(value)
        safe_value = shlex.quote(value_str)
        cmd = [
            "bash",
            "-c",
            f"echo {safe_value} > /proc/sys/kernel/sched_rt_runtime_us",
        ]

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.returncode == 0:
                logger.info(
                    "Successfully set /proc/sys/kernel/sched_rt_runtime_us to %d (unit: us)",
                    value,
                )
                return {
                    "status": "success",
                    "message": f"sched_rt_runtime_us is set to {value}",
                }
            else:
                logger.error(
                    "Failed to set sched_rt_runtime_us. stdout=%s stderr=%s",
                    proc.stdout,
                    proc.stderr,
                )
                return {
                    "status": "error",
                    "message": (proc.stderr or proc.stdout).strip() or "Unknown error",
                }
        except Exception as e:
            logger.exception(
                "An exception occurred while writing to /proc/sys/kernel/sched_rt_runtime_us"
            )
            return {"status": "error", "message": str(e)}
