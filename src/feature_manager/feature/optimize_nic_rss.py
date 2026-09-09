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
import re
import subprocess
from typing import Dict, Any, Optional
from src.feature_manager.feature import register_feature
from src.feature_manager.feature.base import BaseFeature
from src.utils.log import get_logger

logger = get_logger(__name__)


FEATURE_NAME = "optimize_nic_rss"
FEATURE_DES = "配置网卡RSS多队列与环形缓冲"


def _sub_env():
    return {**os.environ, "LANG": "C"}


@register_feature(scenarios=["opengauss_database", "kingbase_database", "dameng_database", "common"])
class OptimizeNicRss(BaseFeature):
    name: str = FEATURE_NAME
    nic: str = ""
    auto_select: bool = True
    rss_combined: int = 64
    ring_rx: int = 16384
    ring_tx: int = 1024
    # 硬件上限（由 get_current_config 探测填充；None=未探测/不支持）
    rss_max: Optional[int] = None
    ring_rx_max: Optional[int] = None
    ring_tx_max: Optional[int] = None
    ring_supported: bool = True

    def _parse_value(self, text: str) -> Optional[int]:
        """解析 ethtool 输出中的数值；'n/a' 或无法解析则返回 None。"""
        t = (text or "").strip().lower()
        if not t or t == "n/a" or t == "na" or not t.isdigit():
            return None
        return int(t)

    def _get_nic_limits(self, nic: str) -> tuple:
        """
        读取网卡硬件上限。返回 (rss_max, ring_rx_max, ring_tx_max, ring_supported)。
        ethtool -l -> Combined 的 Pre-set maximums (RSS 队列上限)
        ethtool -g -> RX/TX 的 Pre-set maximums (环形缓冲上限)；无输出/不支持则 ring_supported=False
        """
        rss_max = ring_rx_max = ring_tx_max = None
        ring_support = True

        try:
            out = subprocess.run(
                ["ethtool", "-l", nic], capture_output=True, text=True, check=False, env=_sub_env(),
            ).stdout
            # 只取 Pre-set maximums 段，跳过 Current
            pre = out.split("Current hardware settings:", 1)[0]
            if "Pre-set maximums" in pre:
                in_pre = False
                for line in pre.splitlines():
                    s = line.strip()
                    if s.startswith("Pre-set maximums"):
                        in_pre = True
                        continue
                    if in_pre and s.startswith("Combined:"):
                        rss_max = self._parse_value(s.split(":", 1)[1])
        except Exception as e:
            logger.warning(f"Failed to get RSS limits for {nic}: {e}")

        try:
            out = subprocess.run(
                ["ethtool", "-g", nic], capture_output=True, text=True, check=False, env=_sub_env(),
            ).stdout
            pre = out.split("Current hardware settings:", 1)[0]
            if "Pre-set maximums" in pre:
                in_pre = False
                for line in pre.splitlines():
                    s = line.strip()
                    if s.startswith("Pre-set maximums"):
                        in_pre = True
                        continue
                    if in_pre:
                        if s.startswith("RX:"):
                            ring_rx_max = self._parse_value(s.split(":", 1)[1])
                        elif s.startswith("TX:"):
                            ring_tx_max = self._parse_value(s.split(":", 1)[1])
            else:
                ring_support = False  # ethtool -g 无可配置 ring -> 不支持
        except Exception as e:
            logger.warning(f"Failed to get ring limits for {nic}: {e}")
            ring_support = False

        logger.info(
            f"NIC {nic} limits: rss_max={rss_max} ring_rx_max={ring_rx_max} "
            f"ring_tx_max={ring_tx_max} ring_supported={ring_support}"
        )
        return rss_max, ring_rx_max, ring_tx_max, ring_support

    def _get_nic_speed(self, nic: str) -> int:
        """通过 ethtool 读取网卡带宽(Mb/s)，失败返回 -1。"""
        try:
            out = subprocess.run(
                ["ethtool", nic], capture_output=True, text=True, check=False, env=_sub_env()
            ).stdout
            m = re.search(r"Speed:\s*(\d+)", out)
            return int(m.group(1)) if m else -1
        except Exception as e:
            logger.warning(f"Failed to get speed for {nic}: {e}")
            return -1

    def _auto_detect_nic(self) -> str:
        """选 UP 状态且带宽最大的网卡（规避 lo/down 口）。"""
        nic_speed = {}
        try:
            out = subprocess.run(
                ["ip", "-br", "link", "show"], capture_output=True, text=True, check=False,
                env=_sub_env(),
            ).stdout
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "UP":
                    nic = parts[0]
                    if nic == "lo":
                        continue
                    nic_speed[nic] = self._get_nic_speed(nic)
        except Exception as e:
            logger.warning(f"Failed to list NICs: {e}")
        if not nic_speed:
            return ""
        best = max(nic_speed, key=nic_speed.get)
        logger.info(f"Auto-selected NIC '{best}' (Speed={nic_speed[best]}Mb/s) among UP: {nic_speed}")
        return best

    def get_current_config(self) -> dict:
        """捕获当前网卡的RSS队列数与环形缓冲，用于恢复/对比。"""
        self.deploy = "NA"
        config = {"rss_combined": None, "ring_rx": None, "ring_tx": None}
        if self.auto_select and not self.nic:
            self.nic = self._auto_detect_nic()

        if self.nic:
            # 探测硬件上限并保存到实例
            (self.rss_max, self.ring_rx_max, self.ring_tx_max, self.ring_supported) = self._get_nic_limits(self.nic)
            try:
                combined = subprocess.run(
                    ["ethtool", "-l", self.nic], capture_output=True, text=True, check=False,
                    env=_sub_env(),
                )
                for line in combined.stdout.splitlines():
                    s = line.strip()
                    if s.startswith("Combined:"):
                        config["rss_combined"] = s.split(":", 1)[1].strip()
            except Exception as e:
                logger.warning(f"Failed to get RSS for {self.nic}: {e}")

            try:
                ring = subprocess.run(
                    ["ethtool", "-g", self.nic], capture_output=True, text=True, check=False,
                    env=_sub_env(),
                )
                cur = False
                for line in ring.stdout.splitlines():
                    s = line.strip()
                    if s.startswith("Current hardware settings:"):
                        cur = True
                        continue
                    if cur:
                        if s.startswith("RX:"):
                            config["ring_rx"] = s.split(":", 1)[1].strip()
                        elif s.startswith("TX:"):
                            config["ring_tx"] = s.split(":", 1)[1].strip()
            except Exception as e:
                logger.warning(f"Failed to get ring for {self.nic}: {e}")

        return self._merge_config(config)

    def _merge_config(self, current: dict) -> dict:
        """当前无值(None)时回退到目标值，保证 YAML 字段非空且 base/target 可比。"""
        self_vals = {
            "rss_combined": None if current.get("rss_combined") is None else self.rss_combined,
            "ring_rx": None if current.get("ring_rx") is None else self.ring_rx,
            "ring_tx": None if current.get("ring_tx") is None else self.ring_tx,
        }
        merged = dict(self_vals)
        for k in current:
            if current[k] is not None:
                merged[k] = current[k]
        self.current_rss = current.get("rss_combined")
        self.current_rx = current.get("ring_rx")
        self.current_tx = current.get("ring_tx")
        cfg = self.model_dump()
        cfg["nic"] = self.nic
        cfg["deploy"] = self.deploy
        return cfg

    def generate_config(self) -> Dict[str, Any]:
        self.deploy = "Y"
        if self.auto_select and not self.nic:
            self.nic = self._auto_detect_nic()
            if self.nic:
                logger.info(f"Auto-selected NIC '{self.nic}' for RSS optimization.")
        config = self.model_dump()
        if not self.nic:
            logger.warning("No NIC detected (no UP link found), skip RSS optimization.")
            config["deploy"] = "NA"
        logger.debug(f"Optimization Item {self.name} config yaml is generated")
        return config

    def _apply_config_impl(self) -> dict:
        if self.auto_select and not self.nic:
            self.nic = self._auto_detect_nic()
        if not self.nic:
            return {"status": "error", "message": "No NIC detected. Set 'nic' field (e.g. enp65s0f0) or ensure a UP link exists."}
        results = {}
        rss_max, ring_rx_max, ring_tx_max, ring_supported = self._get_nic_limits(self.nic)

        # RSS：目标值 clamp 到硬件上限
        rss_target = self.rss_combined
        if rss_max is not None:
            rss_target = min(rss_target, rss_max)
        try:
            r = subprocess.run(
                ["ethtool", "-L", self.nic, "combined", str(rss_target)],
                capture_output=True, text=True, check=False, env=_sub_env(),
            )
            results["rss"] = {"desired": self.rss_combined, "applied": rss_target,
                              "hw_max": rss_max, "returncode": r.returncode, "stderr": r.stderr.strip()}
            logger.info(f"ethtool -L {self.nic} combined {rss_target} (desired {self.rss_combined}, hw_max {rss_max}): rc={r.returncode}")
        except Exception as e:
            results["rss"] = {"error": str(e)}

        # 环形缓冲：仅当网卡支持时设置，且 clamp 到上限
        if ring_supported:
            rx_target, tx_target = self.ring_rx, self.ring_tx
            if ring_rx_max is not None:
                rx_target = min(rx_target, ring_rx_max)
            if ring_tx_max is not None:
                tx_target = min(tx_target, ring_tx_max)
            try:
                r = subprocess.run(
                    ["ethtool", "-G", self.nic, "rx", str(rx_target), "tx", str(tx_target)],
                    capture_output=True, text=True, check=False, env=_sub_env(),
                )
                results["ring"] = {"desired": [self.ring_rx, self.ring_tx],
                                   "applied": [rx_target, tx_target],
                                   "hw_max": [ring_rx_max, ring_tx_max],
                                   "returncode": r.returncode, "stderr": r.stderr.strip()}
                logger.info(f"ethtool -G {self.nic} rx {rx_target} tx {tx_target} (desired {self.ring_rx}/{self.ring_tx}): rc={r.returncode}")
            except Exception as e:
                results["ring"] = {"error": str(e)}
        else:
            logger.warning(f"NIC {self.nic} does not support ring buffer tuning (ethtool -g), skipping.")
            results["ring"] = {"skipped": "NIC does not support ring buffer tuning"}
        return {"status": "success", "message": f"NIC {self.nic} RSS/ring applied (clamped to hw limits).", "details": results}
