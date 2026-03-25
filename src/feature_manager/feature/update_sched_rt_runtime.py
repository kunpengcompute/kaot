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
        根据输入配置字典中的 sched_rt_runtime 字段（整数类型），
        修改 /etc/sysctl.conf 文件中的 kernel.sched_rt_runtime_us 参数，
        如果文件不存在则创建，如果参数不存在则追加到文件末尾，
        最后使用 sysctl -p 命令应用更改。
        """
        value = self.sched_rt_runtime

        # 检查值是否为 None
        if value is None:
            logger.warning(
                "The 'sched_rt_runtime' parameter is missing. The unit of this parameter is microseconds (us)."
            )
            return {
                "status": "error",
                "message": "Missing parameter: sched_rt_runtime",
            }

        sysctl_conf_path = "/etc/sysctl.conf"
        
        # 读取现有文件内容，如果文件不存在则初始化为空列表
        try:
            with open(sysctl_conf_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except FileNotFoundError:
            # 文件不存在，创建空列表
            lines = []
            logger.info(f"{sysctl_conf_path} does not exist, will create a new file.")
        except Exception as e:
            logger.error(f"Failed to read {sysctl_conf_path}: {e}")
            return {
                "status": "error",
                "message": f"Failed to read {sysctl_conf_path}: {str(e)}"
            }

        # 查找 kernel.sched_rt_runtime_us 行
        param_exists = False
        updated_lines = []
        param_line = f"kernel.sched_rt_runtime_us = {value}"

        for line in lines:
            if line.strip().startswith("kernel.sched_rt_runtime_us"):
                # 替换这一行
                updated_lines.append(param_line + "\n")
                param_exists = True
            else:
                updated_lines.append(line)

        # 如果参数不存在，则追加到文件末尾
        if not param_exists:
            updated_lines.append(param_line + "\n")

        # 写入更新后的内容
        try:
            with open(sysctl_conf_path, "w", encoding="utf-8") as f:
                f.writelines(updated_lines)
            logger.info(f"Successfully updated {sysctl_conf_path} with {param_line}")
        except Exception as e:
            logger.error(f"Failed to write to {sysctl_conf_path}: {e}")
            return {
                "status": "error",
                "message": f"Failed to write to {sysctl_conf_path}: {str(e)}"
            }

        # 使用 sysctl -p 应用更改
        try:
            proc = subprocess.run(
                ["sysctl", "-p"],
                capture_output=True,
                text=True,
                check=False
            )
            if proc.returncode == 0:
                logger.info("Successfully applied sysctl changes using 'sysctl -p'")
                return {
                    "status": "success",
                    "message": f"sched_rt_runtime is set to {value} and applied via sysctl -p",
                }
            else:
                logger.error(
                    "Failed to apply sysctl changes. stdout=%s stderr=%s",
                    proc.stdout,
                    proc.stderr,
                )
                return {
                    "status": "warning",
                    "message": f"sched_rt_runtime is set to {value} in {sysctl_conf_path} but failed to apply via sysctl -p: {(proc.stderr or proc.stdout).strip()}",
                }
        except Exception as e:
            logger.error(f"An exception occurred while applying sysctl changes: {e}")
            return {
                "status": "warning",
                "message": f"sched_rt_runtime is set to {value} in {sysctl_conf_path} but exception occurred during sysctl -p: {str(e)}",
            }
