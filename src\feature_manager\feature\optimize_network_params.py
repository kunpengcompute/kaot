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
import subprocess
from typing import Dict, Any
from src.feature_manager.feature import register_feature
from src.feature_manager.feature.base import BaseFeature
from src.utils.log import get_logger

logger = get_logger(__name__)


FEATURE_NAME = "optimize_network_params"
FEATURE_DES = "优化网络内核参数(高并发建连保稳)"


@register_feature(scenarios=["opengauss_database", "kingbase_database", "dameng_database", "common"])
class OptimizeNetworkParams(BaseFeature):
    name: str = FEATURE_NAME
    # key: (参数, 目标值)
    params: dict = {
        "net.core.somaxconn": 65535,
        "net.core.netdev_max_backlog": 65535,
        "net.ipv4.tcp_max_syn_backlog": 65535,
        "net.core.rmem_max": 21299200,
        "net.core.wmem_max": 21299200,
    }
    persistent: bool = True

    def get_current_config(self) -> dict:
        """读取当前 sysctl 值，用于 base/target 对比。"""
        self.deploy = "NA"
        current = {}
        for key in self.params:
            try:
                r = subprocess.run(
                    ["sysctl", "-n", key], capture_output=True, text=True, check=False,
                    env={**os.environ, "LANG": "C"},
                )
                current[key] = r.stdout.strip()
            except Exception as e:
                logger.warning(f"Failed to read sysctl {key}: {e}")
                current[key] = None
        self.__dict__["current_values"] = current
        cfg = self.model_dump()
        return cfg

    def generate_config(self) -> Dict[str, Any]:
        self.deploy = "Y"
        config = self.model_dump()
        logger.debug(f"Optimization Item {self.name} config yaml is generated")
        return config

    def _apply_config_impl(self) -> dict:
        results = {}
        errors = []
        for key, value in self.params.items():
            try:
                r = subprocess.run(
                    ["sysctl", "-w", f"{key}={value}"], capture_output=True, text=True, check=False,
                    env={**os.environ, "LANG": "C"},
                )
                results[key] = {"returncode": r.returncode, "output": (r.stdout or r.stderr).strip()}
                logger.info(f"sysctl -w {key}={value}: rc={r.returncode}")
                if r.returncode != 0:
                    errors.append(f"{key}: {(r.stdout or r.stderr).strip()}")
            except Exception as e:
                results[key] = {"error": str(e)}
                errors.append(f"{key}: {e}")

        if self.persistent:
            try:
                lines = []
                for key, value in self.params.items():
                    lines.append(f"{key} = {value}\n")
                with open("/etc/sysctl.conf", "a") as f:
                    f.writelines(lines)
                subprocess.run(["sysctl", "--system"], capture_output=True, text=True, check=False)
                logger.info("Network params persisted to /etc/sysctl.conf")
            except Exception as e:
                logger.error(f"Failed to persist sysctl.conf: {e}")
                errors.append(f"persist /etc/sysctl.conf: {e}")

        if errors:
            return {
                "status": "error",
                "message": f"Some network kernel params failed: {'; '.join(errors)}",
                "details": results,
            }
        return {"status": "success", "message": "Network kernel params applied.", "details": results}
