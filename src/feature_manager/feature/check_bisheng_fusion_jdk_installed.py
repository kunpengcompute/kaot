
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
from src.feature_manager.feature import register_feature
from src.feature_manager.feature.base import BaseFeature
from src.utils.log import get_logger

logger = get_logger(__name__)

FEATURE_NAME = "check_bisheng_fusion_jdk_installed"
FEATURE_DES = "检查毕昇融合JDK是否安装"
COMPATIBLE_STR = "compatible with BiShengJDK Fusion"
UNKNOWN_COMPATIBILITY = "unknown compatibility"
SAME_AS_FUSION_VERSION = "Current JDK version is BiShengJDK Fusion"

def parse_jdk_info():
    try:
        proc = subprocess.run(["java", "-version"], capture_output=True, text=True, check=False)
        output = (proc.stdout or "") + (proc.stderr or "")
        lines = [l.strip() for l in output.splitlines() if l.strip()]
        result = {"jdk_name": "unknown", "jdk_version": "unknown", "compatibility": UNKNOWN_COMPATIBILITY}
        if not lines:
            return result
        # 检查是否有bisheng
        is_bisheng = any("bisheng" in l.lower() for l in lines)
        if is_bisheng:
            result["jdk_name"] = "BiShengJDK"
            # 解析版本
            # openjdk version "1.8.0_462" 取第三块
            parts = lines[0].split()
            version = parts[2].strip('"') if len(parts) > 2 else "unknown"
            result["jdk_version"] = version
            # 如果带1.8.0，查找bishengjdk和1.8.0都在的行
            if "1.8.0" in version:
                for l in lines:
                    l_low = l.lower()
                    if "bisheng" in l_low and "1.8.0" in l_low:
                        idx = l_low.find("-b")
                        if idx != -1 and idx+2 < len(l_low):
                            next_char = l_low[idx+2]
                            # 只取-b后第一个数字
                            if next_char == "2":
                                result["jdk_version"] = "Fusion"
                                result["compatibility"] = SAME_AS_FUSION_VERSION
                            else:
                                result["jdk_version"] = version
                                # 该处判断为毕昇JDK8版本，兼容毕昇JDK Fusion版本
                                result["compatibility"] = COMPATIBLE_STR
                        break
        else:
            # 非毕昇JDK
            parts = lines[0].split()
            result["jdk_name"] = parts[0] if parts else "unknown"
            result["jdk_version"] = parts[2].strip('"') if len(parts) > 2 else "unknown"
            # 若版本为openJDK 8，也兼容毕昇JDK Fusion版本
            if result["jdk_name"].lower() == "openjdk" and "1.8.0" in result["jdk_version"]:
                result["compatibility"] = COMPATIBLE_STR
        return result
    except Exception as e:
        logger.warning(f"Failed to get java version: {e}")
        return {"jdk_name": "unknown", "jdk_version": "unknown", "compatibility": UNKNOWN_COMPATIBILITY}
    
@register_feature(scenarios=["common"])
class CheckBishengFusionJDKInstalled(BaseFeature):
    name: str = FEATURE_NAME
    jdk_name: str = "BiShengJDK"
    jdk_version: str = "Fusion"
    compatibility: str = SAME_AS_FUSION_VERSION

    def get_current_config(self) -> dict:
        """
        通过 java -version 解析当前JDK类型和版本，返回字典。
        """
        self.deploy = "NA"
        jdk_info = parse_jdk_info()
        self.jdk_name = jdk_info["jdk_name"]
        self.jdk_version = jdk_info["jdk_version"]
        self.compatibility = jdk_info["compatibility"]
        config = self.model_dump()
        logger.debug(f"Optimization Item {self.name} current config yaml is generated")
        return config

    def _apply_config_impl(self) -> None:
        """
        根据JDK状态给出安装或卸载指令提示。
        """
        config = self.get_current_config()
        jdk_name = config.get("jdk_name", "").lower()
        jdk_version = config.get("jdk_version", "").lower()
        compatibility = config.get("compatibility", "")
        if jdk_name == "bishengjdk" and jdk_version == "fusion":
            logger.warning("BiSheng JDK Fusion is already installed. To uninstall, you can run: kaot uninstall -n bishengjdk_fusion")
        elif compatibility == COMPATIBLE_STR:
            logger.warning("BiSheng JDK Fusion Version is not installed. Current JDK version is compatible with BiSheng JDK Fusion Version. To install, please run: kaot install -n bishengjdk_fusion")
        else:
            logger.warning("BiSheng JDK Fusion Version is not installed. The compatibility with BiSheng JDK Fusion Version is unknown. Please check if the current JDK version is compatible before installation.")
