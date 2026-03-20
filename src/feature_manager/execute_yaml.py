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
from typing import List, Dict, Any
from src.feature_manager.generate_yaml import generate_yaml
from src.feature_manager.feature import FEATURE_MAP, FEATURE_NAMES
from src.utils.config import load_config
from src.utils.env import check_environment_match
from src.utils.log import get_logger
from src.utils.common import (
    build_feature_map,
    get_feature_keys,
    is_features_config_equal,
    validate_subset,
)

logger = get_logger(__name__)


def run_execute(args, output_dir):
    target_features, base_map, target_map, base_yaml, same_flag = (
        check_features_and_generate_base(args, output_dir)
    )
    if same_flag:
        return
    for feat_name in target_features:
        base_feature = base_map[feat_name]
        target_feature = target_map[feat_name]
        base_feature_config = {feat_name: base_feature}
        target_feature_config = {feat_name: target_feature}
        same_flag = is_features_config_equal(
            base_feature_config, target_feature_config, exclude_attrs=["deploy"]
        )
        logger.debug(f"{feat_name} same_flag is : {same_flag}")
        deploy = target_feature.deploy
        logger.debug(f"{feat_name} deploy is : {deploy}")
        if deploy not in ["Y", "N", "NA"]:
            raise RuntimeError(
                f"Invalid deploy for {feat_name}: {deploy}, must be 'Y' or 'N' or 'NA"
            )
        if deploy == "Y" and not same_flag:
            logger.info(f"start apply config Optimization Item: {feat_name}")
            try:
                target_feature.apply_config()
                logger.info(f"Applied {feat_name} configuration successful.")
            except Exception as exec_err:
                logger.error(f"Unexpected error when executing Optimization Item {feat_name}: {str(exec_err)}")
                logger.warning(f"Terminating process because Optimization Item '{feat_name}' failed and triggered a rollback.")
                try:
                    base_feature.deploy = "Y"
                    base_feature.apply_config()
                    logger.debug("Rollback applied successfully.")
                except Exception as rollback_err:
                    logger.error(f"Rollback applied failed. You can see you base config in {os.path.abspath(base_yaml)}")
                    raise RuntimeError(f"Failed to rollback config: {rollback_err}")
                logger.info(
                    f"Optimization Item '{feat_name}' failed to execute, but the system has successfully rolled back. "
                    f"Subsequent Optimization Items will not be executed."
                )
                return
            logger.debug(f"Apply config Optimization Item finish: {feat_name}")
        elif deploy == "N" or deploy == "NA":
            logger.warning(f"The Optimization Item {feat_name} is not required to change.")
        else:
            logger.warning(
                f"The Optimization Item {feat_name} current configuration already matches the target configuration. "
                f"No changes are required."
            )


def check_features_and_generate_base(args, output_dir):
    target_file = args.target_file_name

    target_cfg = load_config(target_file)
    # 从 target_cfg 中构建当前目标配置的 feature 映射（实例，包含 YAML 中的 config_path 等字段）
    target_full_map = build_feature_map(target_cfg)
    target_features = list(target_full_map.keys())

    check_env = check_environment_match(target_cfg)
    if not check_env:
        raise RuntimeError(
            f"Environment mismatch | Target config system info: {target_cfg.SYSTEM_INFO}"
        )

    # 空校验
    if not target_features:
        logger.warning("OPTIMIZATION_ITEMS in target_file is empty, skip execute")
        return
    # 校验target_file是否在已支持的调优项中
    validate_subset(target_features, FEATURE_NAMES)
    logger.debug(f"args.features : {args.features}")
    if args.features is not None:
        validate_subset(args.features, target_features)
        target_features = args.features
    logger.debug(f"Apply Optimization Items : {target_features}")

    logger.debug("Starting generation process.")
    logger.info(f"The target file path is {target_file}")

    # 为生成 base 配置构建 feature_map：
    #   对每个调优项，根据 FEATURE_MAP 创建新的实例，
    #   并优先继承 target YAML 中的 config_path 等字段（如 Kingbase/OpenGauss 的自定义路径）。
    base_feature_map = {}
    for feat_name in target_features:
        if feat_name not in FEATURE_MAP:
            continue
        feature_cls = FEATURE_MAP[feat_name]
        base_inst = feature_cls()
        target_inst = target_full_map.get(feat_name)
        if target_inst is not None and hasattr(target_inst, "config_path"):
            setattr(base_inst, "config_path", getattr(target_inst, "config_path"))
        base_feature_map[feat_name] = base_inst

    base_yaml = generate_yaml(target_features, base_feature_map, output_dir, "base")
    logger.info(f"Merged base Optimization Item config YAML generated at {os.path.abspath(base_yaml)}")

    logger.debug("Starting execute process.")
    base_cfg = load_config(base_yaml)
    base_map = build_feature_map(base_cfg)
    target_map = build_feature_map(target_cfg)

    update_target_map = update_features_data(target_features, target_map)
    update_base_map = update_features_data(target_features, base_map)
    logger.debug(f"update_target_map: {update_target_map}")
    logger.debug(f"update_base_map: {update_base_map}")
    same_flag = is_features_config_equal(
        update_base_map, update_target_map, exclude_attrs=["deploy"]
    )
    if same_flag:
        logger.warning(
            f"The current configuration already matches the target configuration in config file {os.path.abspath(target_file)}. No changes are required."
        )
    return target_features, base_map, target_map, base_yaml, same_flag


def update_features_data(
    selected_features: List[str], target_features_data: Dict[str, Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """
    根据 selected_features 筛选 target_features_data 中的配置。

    Args:
        selected_features: 要筛选的调优项名称列表，例如 ["test_feature"]
        target_features_data: 调优项配置字典，key=调优项名称，value=调优项配置字典
                              示例: {"test_feature": {"enable": True, "param": 10}}
    Returns:
        字典，包含筛选后的调优项配置（key=调优项名称，value=配置字典）
    """
    filtered_features = {
        feat_name: config
        for feat_name, config in target_features_data.items()
        if feat_name in selected_features
    }

    return filtered_features
