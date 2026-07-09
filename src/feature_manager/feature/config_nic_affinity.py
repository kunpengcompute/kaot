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
import json
from datetime import datetime
from typing import Dict, List, Tuple, Set, Optional, Any, Union
from src.feature_manager.feature import register_feature
from src.feature_manager.feature.base import BaseFeature
from src.utils.log import get_logger
from src.utils.common import run_cmd

logger = get_logger(__name__)

FEATURE_NAME = "config_nic_affinity"
FEATURE_DES = "配置多网卡中断绑核"


@register_feature(scenarios=["kingbase_database", "dameng_database", "common"])
class ConfigNicAffinity(BaseFeature):
    name: str = FEATURE_NAME
    deploy: str = "NA"  # NA | Y
    irqbalance_status: str = "disabled"  # enabled | disabled
    nic_policies: Union[Dict[str, str], str] = {}  # 或 = "" 

    # 内部快照（不暴露给 YAML）
    _current_nic_affinities: Dict[str, Dict[str, str]] = {}  # {nic: {irq_num: cpu_list}}

    def _is_service_active(self, service_name: str) -> bool:
        """
        检查指定 systemd 服务是否处于 active 状态。

        Args:
            service_name (str): 服务名称，如 'irqbalance'。

        Returns:
            bool: 如果服务处于 active 状态则返回 True，否则返回 False。
        """
        try:
            run_cmd(["systemctl", "is-active", service_name], check=True)
            return True
        except Exception:
            return False

    def _parse_cpu_list(self, cpu_str: str) -> List[int]:
        """
        将 CPU 列表字符串（如 "0-3,8,10-12"）解析为排序后的整数列表。

        Args:
            cpu_str (str): CPU 范围字符串，支持逗号分隔和连字符范围。

        Returns:
            List[int]: 排序后的 CPU 核心编号列表。

        Raises:
            ValueError: 当输入格式非法（如 start > end）时抛出。
        """
        cpus = set()
        for part in cpu_str.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start, end = map(int, part.split("-"))
                if start > end:
                    raise ValueError(f"Invalid CPU range: {part}")
                cpus.update(range(start, end + 1))
            else:
                cpus.add(int(part))
        return sorted(cpus)

    def _validate_cpu_range(self, cpus: List[int]):
        """
        校验 CPU 编号是否在系统有效范围内。

        Args:
            cpus (List[int]): 待校验的 CPU 编号列表。

        Raises:
            RuntimeError: 若任一 CPU 超出 [0, total_cpu_count - 1] 范围。
        """
        total = os.cpu_count()
        for cpu in cpus:
            if cpu < 0 or cpu >= total:
                raise RuntimeError(f"CPU {cpu} out of bounds [0, {total - 1}]")

    def _get_pcie_from_nic(self, nic: str) -> str:
        """
        通过 ethtool 获取指定网卡对应的 PCIe 地址（bus-info）。

        Args:
            nic (str): 网卡名称，如 'eth0'。

        Returns:
            str: PCIe 地址（如 '0000:18:00.1'）。

        Raises:
            RuntimeError: 若无法获取 bus-info。
        """
        output = run_cmd(["ethtool", "-i", nic])
        match = re.search(r"bus-info:\s*(\S+)", output)
        if not match:
            raise RuntimeError(f"Cannot get bus-info for NIC {nic}")
        return match.group(1)

    def _get_numa_node(self, pcie: str) -> int:
        """
        通过 lspci 查询指定 PCIe 设备所属的 NUMA 节点。

        Args:
            pcie (str): PCIe 地址，如 '0000:18:00.1'。

        Returns:
            int or None: NUMA 节点编号；若查询失败或未找到，返回 None。
        """
        try:
            output = run_cmd(["lspci", "-vvv", "-s", pcie])
            for line in output.splitlines():
                if "NUMA node:" in line:
                    parts = line.strip().split(":")
                    if len(parts) >= 2:
                        node_str = parts[1].strip()
                        if node_str.isdigit():
                            return int(node_str)
        except Exception as e:
            logger.debug(f"lspci failed to get NUMA for {pcie}: {e}")

    def _get_all_up_nics(self) -> List[str]:
        """
        获取当前所有处于 UP 状态的网卡列表。

        Returns:
            List[str]: 网卡名称列表，如 ['eth0', 'enp24s0f1']。
        """
        nics = []
        for line in run_cmd(["ip", "-br", "link", "show"]).splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "UP":
                nics.append(parts[0])
        return nics

    def _get_nic_irqs(self, nic: str) -> List[Tuple[str, str]]:
        """
        获取指定网卡关联的数据面中断（IRQ）列表，排除管理/控制面中断。

        Args:
            nic (str): 网卡名称。

        Returns:
            List[Tuple[str, str]]: 列表项为 (IRQ编号, 中断名称)，如 [('1627', 'enp24s0f1-TxRx-0')]。

        Raises:
            RuntimeError: 若无法获取 PCIe 地址。
        """
        pcie = self._get_pcie_from_nic(nic)
        exclude_keywords = [
            "mlx5_pages_eq", "mlx5_cmd_eq", "mlx5_async",
            "hclge-misc", "hinic_aeq", "hinic_ceq"
        ]
        exclude_re = "|".join(re.escape(k) for k in exclude_keywords)

        patterns = [re.escape(nic), re.escape(pcie)]
        try:
            dmesg = run_cmd(["dmesg"])
            for line in dmesg.splitlines():
                if "renamed" in line and pcie in line:
                    old_name = line.split()[-1]
                    patterns.append(re.escape(old_name))
        except Exception:
            pass

        pattern_re = "|".join(patterns)
        irqs = []
        with open("/proc/interrupts", "r") as f:
            for line in f:
                if not re.search(pattern_re, line):
                    continue
                if re.search(exclude_re, line):
                    continue
                parts = line.strip().split()
                if not parts:
                    continue
                irq_num = parts[0].rstrip(":")
                irq_name = parts[-1]
                irqs.append((irq_num, irq_name))
        return irqs

    def _transform_nic_affinity_cpu_range(self):
        """
        将内部快照 `_current_nic_affinities` 转换为用户友好的 CPU 范围字符串，
        并更新到 `nic_policies` 字段中（用于生成配置）。
        """
        for nic, irq_map in self._current_nic_affinities.items():
            # 收集所有被绑定的CPU核心
            cpus = set()
            for irq, cpu in irq_map.items():
                # 处理可能的逗号分隔的CPU列表
                for c in cpu.split(','):
                    c = c.strip()
                    if c and c.isdigit():
                        cpus.add(int(c))
            
            if cpus:
                # 将CPU核心排序并转换为范围表示法
                sorted_cpus = sorted(cpus)
                ranges = []
                start = sorted_cpus[0]
                end = sorted_cpus[0]
                
                for cpu in sorted_cpus[1:]:
                    if cpu == end + 1:
                        end = cpu
                    else:
                        if start == end:
                            ranges.append(str(start))
                        else:
                            ranges.append(f"{start}-{end}")
                        start = end = cpu
                # 处理最后一个范围
                if start == end:
                    ranges.append(str(start))
                else:
                    ranges.append(f"{start}-{end}")
                
                # 格式化为 "32-61,63" 这样的字符串
                self.nic_policies[nic] = ','.join(ranges)
                logger.info(f"NIC {nic}: IRQs bound to CPUs {self.nic_policies[nic]}")
            else:
                self.nic_policies[nic] = ""

    def _get_numa_cpu_ranges(self) -> Dict[int, str]:
        """
        解析 lscpu 输出，获取每个 NUMA 节点对应的 CPU 范围。

        Returns:
            Dict[int, str]: 映射关系，如 {0: '0-31', 1: '32-63'}。
        """
        numa_cpus = {}
        try:
            output = run_cmd(["lscpu"])
            for line in output.splitlines():
                # 匹配 "NUMA node0 CPU(s):    0-31" 这样的行
                match = re.match(r'NUMA node(\d+)\s+CPU\(s\):\s+(\S+)', line.strip())
                if match:
                    node = int(match.group(1))
                    cpu_range = match.group(2)
                    numa_cpus[node] = cpu_range
        except Exception as e:
            logger.error(f"Failed to parse lscpu: {e}")
        
        return numa_cpus

    def get_current_config(self) -> dict:
        """
        捕获当前系统的网卡中断绑核状态，用于后续恢复（restore）。

        功能包括：
        - 检测 irqbalance 服务状态
        - 获取所有 UP 网卡的 IRQ 及其 smp_affinity_list
        - 将快照保存为 JSON 文件，并将文件路径赋值给 nic_policies

        Returns:
            dict: 当前配置的字典表示（通过 Pydantic model_dump 生成）。
        """
        self.irqbalance_status = "enabled" if self._is_service_active("irqbalance") else "disabled"
        up_nics = self._get_all_up_nics()
        self._current_nic_affinities = {}

        for nic in up_nics:
            try:
                irqs = self._get_nic_irqs(nic)
                affinity_map = {}
                for irq_num, _ in irqs:
                    path = f"/proc/irq/{irq_num}/smp_affinity_list"
                    if os.path.exists(path):
                        with open(path, "r") as f:
                            affinity_map[irq_num] = f.read().strip()
                if affinity_map:
                    self._current_nic_affinities[nic] = affinity_map
            except Exception as e:
                logger.warning(f"Failed to get IRQ affinity for {nic}: {e}")
        # self.nic_policies 更新下
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"output/log/nic_affinities/{timestamp}.json"
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        # 绑核关系存为文件
        try:
            with open(filename, 'w') as f:
                json.dump(self._current_nic_affinities, f, indent=2)
            logger.debug(f"Saved NIC IRQ affinities to {filename}")
            self.nic_policies = filename
        except Exception as e:
            logger.warning(f"Failed to save NIC affinities: {e}")
        config = self.model_dump()
        logger.debug("Current NIC IRQ affinity snapshot captured.")
        return config
    
    def pre_generate_config(self):
        """
        自动生成推荐的网卡绑核策略：
        - 为每个 UP 网卡分配其所在 NUMA 节点的全部 CPU。
        - 结果存入 self.nic_policies（格式：{'eth0': '0-31', ...}）。
        """
        logger.info("Starting NIC policy pre-generation")
        # 获取所有UP状态的网卡
        nic_list = self._get_all_up_nics()
        logger.info(f"UP NICs: {nic_list}")
        # 获取NUMA节点的CPU范围
        cpu_numa_range = self._get_numa_cpu_ranges()
        logger.info(f"NUMA CPU ranges: {cpu_numa_range}")
        # 遍历每个网卡
        for nic in nic_list:
            try:
                # 获取网卡的PCIe地址
                pcie = self._get_pcie_from_nic(nic)
                if not pcie:
                    logger.warning(f"Cannot get PCIe for {nic}, skipping")
                    continue
                # 获取NUMA节点
                numa_node = self._get_numa_node(pcie)
                if numa_node is None:
                    logger.warning(f"Cannot get NUMA node for {nic} (PCIe: {pcie}), skipping")
                    continue
                # 获取该NUMA节点的CPU范围
                cpu_range = cpu_numa_range.get(numa_node)
                if not cpu_range:
                    logger.warning(f"No CPU range found for NUMA node {numa_node}, skipping {nic}")
                    continue
                # 更新 nic_policies
                self.nic_policies[nic] = cpu_range
                logger.info(f"NIC {nic} (PCIe: {pcie}, NUMA: {numa_node}) -> CPU: {cpu_range}")
            except Exception as e:
                logger.error(f"Failed to process NIC {nic}: {e}")
                continue
        logger.info(f"Generated NIC policies: {self.nic_policies}")

    def generate_config(self) -> Dict[str, Any]:
        """
        通用配置生成逻辑
        :return: 统一格式的配置字典
        """
        self.deploy = "Y"
        self.pre_generate_config()

        config = self.model_dump()
        logger.debug(f"Optimization Item {self.name} config yaml is generated")
        return config

    def _validate_and_analyze_policies(self) -> Dict[str, Dict[str, List[int]]]:
        """
        校验并标准化用户输入的 nic_policies 配置。

        支持三种输入形式：
        1. 字符串：JSON 文件路径（包含详细 IRQ 映射）
        2. 字典（简化）：{nic: "cpu_range"} → 视为所有 IRQ 绑定相同 CPU
        3. 字典（详细）：{nic: {irq: "cpu_range"}}

        执行以下校验：
        - CPU 范围合法性（越界检查）
        - NUMA 亲和性警告（跨 NUMA 绑定）
        - CPU 冲突警告（多个 IRQ 共享同一 CPU）

        Returns:
            Dict[str, Dict[str, List[int]]]: 标准化后的策略，格式为 {nic: {irq: [cpu_ids]}}

        Raises:
            RuntimeError: 配置格式错误或 CPU 越界。
        """
        total_cpus = os.cpu_count()
        all_used_cpus: Set[int] = set()
        numa_warnings = []
        conflict_warnings = []
        
        # 返回格式: {nic: {irq: [cpus]}}
        parsed: Dict[str, Dict[str, List[int]]] = {}
        
        # === 情况1：nic_policies 是文件路径 ===
        if isinstance(self.nic_policies, str):
            try:
                with open(self.nic_policies, 'r') as f:
                    irq_affinity_map = json.load(f)
                
                # 转换文件内容，解析CPU范围
                for nic, irq_map in irq_affinity_map.items():
                    parsed_nic = {}
                    for irq, cpu_str in irq_map.items():
                        # 使用现有的CPU列表解析方法
                        cpus = self._parse_cpu_list(cpu_str)
                        parsed_nic[irq] = cpus
                    parsed[nic] = parsed_nic
                    logger.debug(f"NIC {nic}: loaded {len(parsed_nic)} IRQ mappings from file")
                    
            except Exception as e:
                raise RuntimeError(f"Failed to load NIC policies from file {self.nic_policies}: {e}")
        
        # === 情况2：nic_policies 是字典 ===
        elif isinstance(self.nic_policies, dict):
            for nic, value in self.nic_policies.items():
                parsed_nic = {}
                
                # 判断是格式1（网卡:CPU范围）还是格式2（网卡:{中断号:CPU}）
                if isinstance(value, str):
                    # 格式1：简化表示法，使用虚拟中断号'all'
                    try:
                        cpus = self._parse_cpu_list(value)
                        self._validate_cpu_range(cpus)
                        parsed_nic['all'] = cpus
                    except Exception as e:
                        raise RuntimeError(f"Invalid CPU spec for NIC {nic}: {e}")
                        
                elif isinstance(value, dict):
                    # 格式2：详细中断映射
                    for irq, cpu_str in value.items():
                        try:
                            cpus = self._parse_cpu_list(cpu_str)
                            parsed_nic[irq] = cpus
                        except Exception as e:
                            raise RuntimeError(f"Invalid CPU spec for NIC {nic}, IRQ {irq}: {e}")
                else:
                    raise RuntimeError(f"NIC {nic} policy must be str or dict, got {type(value)}")
                
                parsed[nic] = parsed_nic
        
        else:
            raise RuntimeError(f"nic_policies must be dict or file path, got {type(self.nic_policies)}")
        
        # === 后续校验逻辑（需要适配新的数据结构）===
        # 收集所有使用的CPU用于冲突检测
        for nic, irq_map in parsed.items():
            for irq, cpus in irq_map.items():
                all_used_cpus.update(cpus)
        
        # CPU序号越界检查
        max_cpu_index = total_cpus - 1 if total_cpus else 0

        for nic, irq_map in parsed.items():
            for irq, cpus in irq_map.items():
                # 检查每个CPU序号是否在有效范围内
                invalid_cpus = [cpu for cpu in cpus if cpu < 0 or cpu > max_cpu_index]
                if invalid_cpus:
                    raise RuntimeError(
                        f"NIC {nic} IRQ {irq} contains invalid CPU numbers: {invalid_cpus}. "
                        f"Valid CPU range is 0-{max_cpu_index} (total {total_cpus} CPUs)"
                    )

        # === NUMA 亲和性检查 ===
        for nic, irq_map in parsed.items():
            try:
                pcie = self._get_pcie_from_nic(nic)
                numa_node = self._get_numa_node(pcie)
                if numa_node >= 0:
                    numa_file = f"/sys/devices/system/node/node{numa_node}/cpulist"
                    if os.path.exists(numa_file):
                        with open(numa_file, "r") as f:
                            numa_cpus = set(self._parse_cpu_list(f.read().strip()))
                        
                        # 检查每个中断绑定的CPU是否在NUMA节点内
                        for irq, cpus in irq_map.items():
                            cross = set(cpus) - numa_cpus
                            if cross:
                                numa_warnings.append(
                                    f"NIC {nic} IRQ {irq} (NUMA {numa_node}) uses CPUs {sorted(cross)} outside its NUMA node."
                                )
            except Exception as e:
                logger.warning(f"NUMA check failed for {nic}: {e}")
        
        # CPU冲突检查（不同网卡/中断使用相同CPU）
        cpu_to_owner = {}  # {cpu: [(nic, irq)]}
        for nic, irq_map in parsed.items():
            for irq, cpus in irq_map.items():
                for cpu in cpus:
                    if cpu in cpu_to_owner:
                        cpu_to_owner[cpu].append((nic, irq))
                    else:
                        cpu_to_owner[cpu] = [(nic, irq)]
        
        for cpu, owners in cpu_to_owner.items():
            if len(owners) > 1:
                conflict_warnings.append(
                    f"CPU {cpu} is shared by multiple NICs/IRQs: {owners}"
                )
        
        for w in numa_warnings:
            logger.warning(w)
        for w in conflict_warnings:
            logger.warning(w)
        
        return parsed

    def _bind_irqs_for_nic(self, nic: str, cpu_list: List[int]):
        irqs = self._get_nic_irqs(nic)
        cpu_str = ",".join(map(str, cpu_list))
        for irq_num, irq_name in irqs:
            path = f"/proc/irq/{irq_num}/smp_affinity_list"
            if not os.path.exists(path):
                continue
            try:
                with open(path, "w") as f:
                    f.write(cpu_str)
                logger.debug(f"Bound {nic} IRQ {irq_num} ({irq_name}) → CPUs: {cpu_str}")
            except PermissionError:
                raise RuntimeError("Permission denied. Run as root.")
            except Exception as e:
                logger.error(f"Bind failed for IRQ {irq_num} ({nic}): {e}")
                raise

    def _apply_config_impl(self):
        """
        应用网卡中断绑核配置的核心逻辑。

        步骤：
        1. 若 irqbalance_status 为真，停止应用绑核
        2. 解析并校验 nic_policies
        3. 根据策略绑定每个 IRQ 到指定 CPU

        注意：需以 root 权限运行。
        """
        if self.irqbalance_status == "enabled":
            run_cmd(["systemctl", "restart", "irqbalance"], check=False)
            run_cmd(["systemctl", "enable", "irqbalance"], check=False)
            return
        
        # 校验并分析策略
        parsed_policies = self._validate_and_analyze_policies()
        logger.info(f"Parsed policies: {parsed_policies}")

        # 关闭 irqbalance
        run_cmd(["systemctl", "stop", "irqbalance"], check=False)
        run_cmd(["systemctl", "disable", "irqbalance"], check=False)

        # 应用绑核
        for nic, irq_map in parsed_policies.items():
            # 获取该网卡的所有数据面IRQ
            nic_irqs = self._get_nic_irqs(nic)
            if not nic_irqs:
                logger.warning(f"No data-path IRQs for {nic}, skipped.")
                continue
            
            # 情况1：简化格式（使用'all'代表所有IRQ绑定到相同CPU集）
            if 'all' in irq_map:
                cpu_list = irq_map['all']
                cpu_str = ",".join(map(str, cpu_list))
                for irq_num, irq_name in nic_irqs:
                    self._bind_single_irq(irq_num, cpu_str, nic, irq_name)
            
            # 情况2：详细格式（每个IRQ单独指定）
            else:
                for irq_num, irq_name in nic_irqs:
                    if irq_num in irq_map:
                        cpu_list = irq_map[irq_num]
                        cpu_str = ",".join(map(str, cpu_list))
                        self._bind_single_irq(irq_num, cpu_str, nic, irq_name)
                    else:
                        logger.warning(f"IRQ {irq_num} for {nic} not found in policy, skipped.")

        logger.info("Multi-NIC IRQ affinity applied successfully.")

    def _bind_single_irq(self, irq_num: str, cpu_str: str, nic: str, irq_name: str = ""):
        """
        将单个 IRQ 绑定到指定的 CPU 列表。

        Args:
            irq_num (str): 中断号，如 '1627'
            cpu_str (str): CPU 列表字符串，如 '32-63' 或 '38,62,63'
            nic (str): 所属网卡名称
            irq_name (str): 中断名称（可选，用于日志）

        Raises:
            RuntimeError: 权限不足或其他写入错误。
        """
        path = f"/proc/irq/{irq_num}/smp_affinity_list"
        if not os.path.exists(path):
            logger.warning(f"IRQ {irq_num} path not exists, skipped.")
            return
        
        try:
            with open(path, "w") as f:
                f.write(cpu_str)
            logger.debug(f"Bound {nic} IRQ {irq_num} ({irq_name}) → CPUs: {cpu_str}")
        except PermissionError:
            raise RuntimeError("Permission denied. Run as root.")
        except Exception as e:
            logger.error(f"Bind failed for IRQ {irq_num} ({nic}): {e}")
            raise