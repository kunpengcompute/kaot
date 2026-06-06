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
import shutil
from src.utils.common import (
    build_feature_map,
    get_feature_keys,
    validate_subset,
    validate_yaml_name,
    validate_yaml_path_exist,
)
from src.utils.config import TotalConfig, load_config
from src.utils.env import get_environment_info
from src.utils.log import get_logger
from src.feature_manager.feature import FEATURE_MAP, load_scenario
from src.feature_manager.feature.base import BaseFeature

logger = get_logger(__name__)


def generate_yaml(features, feature_map, output_dir, generate_type, yaml_path=None):
    if not features:
        raise ValueError("Optimization Items cannot be empty")
    if not os.path.isdir(output_dir):
        raise FileNotFoundError(f"Output directory does not exist: {output_dir}")
    feature_list = []
    for feat_name in features:
        if feat_name not in feature_map:
            raise KeyError(f"Optimization Item '{feat_name}' not found in feature_map")

        obj = feature_map[feat_name]
        # 支持两种形式：
        # 1) obj 为 BaseFeature 实例（如从 YAML 反序列化而来）
        # 2) obj 为特性类（如 FEATURE_MAP 中的类），需要此处进行实例化
        if isinstance(obj, BaseFeature):
            feature = obj
        else:
            feature_cls = obj
            feature = feature_cls()
            # 如果类级别的 config_path 已被外部覆盖（例如 basecfg 传入的自定义路径），
            # 则在新实例上显式同步该路径，避免 Pydantic 默认值缓存导致仍使用旧路径。
            if hasattr(feature_cls, "config_path"):
                setattr(feature, "config_path", getattr(feature_cls, "config_path"))
        if generate_type == "target":
            config = feature.generate_config()
            yaml_name = "feature_config.yaml"
            feature_list.append(config)
            logger.debug(f"Merged Optimization Item: {feat_name}")
        elif generate_type == "base":
            try:
                
                # 自动备份config_path文件
                if hasattr(feature, "config_path") and getattr(feature, "config_path", None):
                    config_path = getattr(feature, "config_path")
                    if os.path.isfile(config_path):
                        base_name = os.path.basename(config_path)
                        backup_path = os.path.abspath(os.path.join(output_dir, base_name + ".bak"))
                        try:
                            shutil.copy2(config_path, backup_path)
                            logger.info(f"Config file {config_path} has been backed up to {backup_path}")
                            feature.config_bak_path = backup_path
                        except Exception as e:
                            logger.warning(f"Failed to backup config file {config_path}: {e}")
                config = feature.get_current_config()
            except Exception as e:
                logger.error(f"get_current_config failed for {feature.name}")
                raise RuntimeError(f"Error message blow: {e}")
            yaml_name = "base_config.yaml"
            if config is not None:
                feature_list.append(config)
                logger.debug(f"Merged Optimization Item: {feat_name}")
        else:
            raise ValueError(
                f"Invalid generate_type: {generate_type}, must be 'target' or 'base'"
            )
    env_cfg = get_environment_info()
    final_config = TotalConfig(SYSTEM_INFO=env_cfg, OPTIMIZATION_ITEMS=feature_list)
    if yaml_path:
        output_yaml = yaml_path
    else:
        output_yaml = os.path.join(output_dir, yaml_name)
    final_config.to_yaml(output_yaml)
    return output_yaml


def run_generate(args, output_dir):
    logger.debug("Starting generation process.")
    configfile_map = getattr(args, "configfile_map", None)
    if args.features and not args.target_file_name:
        validate_output_file_name(args)
        generate_with_features_or_scenario(args, output_dir, configfile_map)
    elif args.target_file_name and args.base_file_name:
        validate_yaml_name(args.base_file_name)
        validate_yaml_name(args.target_file_name)
        args.base_file_name = validate_yaml_path_exist(args.base_file_name)
        args.target_file_name = validate_yaml_path_exist(args.target_file_name)
        logger.info(f"The base file path is {args.base_file_name}")
        logger.info(f"The target file path is {args.target_file_name}")
        generate_with_target_and_base(args, output_dir)
    elif args.target_file_name:
        validate_yaml_name(args.target_file_name)
        args.target_file_name = validate_yaml_path_exist(args.target_file_name)
        logger.info(f"The target file path is {args.target_file_name}")
        generate_with_target_only(args, output_dir)
    elif args.base_file_name:
        validate_output_file_name(args)
        validate_yaml_name(args.base_file_name)
        args.base_file_name = validate_yaml_path_exist(args.base_file_name)
        logger.info(f"The base file path is {args.base_file_name}")
        generate_with_base_only(args, output_dir)
    elif args.scenario:
        validate_output_file_name(args)
        generate_with_features_or_scenario(args, output_dir, configfile_map)
    else:
        raise RuntimeError(
            "You must specify one of --features, --scenario, --target_file or --base_file"
        )


def generate_with_target_and_base(args, output_dir):
    logger.info("Operation: update target_file with Optimization Items from base_file.")
    base_file = args.base_file_name
    target_file = args.target_file_name

    base_cfg = load_config(base_file)
    target_cfg = load_config(target_file)

    base_features = get_feature_keys(base_cfg)
    target_features = get_feature_keys(target_cfg)

    logger.debug(f"target_features: {target_features}")
    logger.debug(f"base_features: {base_features}")
    if args.features:
        change_features = args.features
        validate_subset(change_features, base_features)
    else:
        change_features = base_features
    logger.debug(f"change_features: {change_features}")
    validate_subset(change_features, target_features)

    base_map = build_feature_map(base_cfg)
    target_map = build_feature_map(target_cfg)

    for feature in change_features:
        logger.debug(f"Updating Optimization Item {feature} from base_file")
        deploy = target_map[feature].deploy
        target_map[feature] = base_map[feature]
        target_map[feature].deploy = deploy

    update_target_map = list(target_map.values())
    target_cfg.OPTIMIZATION_ITEMS = update_target_map
    yaml_name = "config_backup.yaml"
    backup_yaml = os.path.join(output_dir, yaml_name)
    output_yaml = backup_and_prepare_output(target_file, backup_yaml)
    target_cfg.to_yaml(output_yaml)
    logger.info(f"Updated target YAML saved to {os.path.abspath(output_yaml)}")
    return


def generate_with_target_only(args, output_dir):
    logger.info("Operation: update target_file from Optimization Items.")
    target_file = args.target_file_name
    target_cfg = load_config(target_file)

    if args.add_features and args.delete_features:
        overlap = set(args.add_features) & set(args.delete_features)
        if overlap:
            raise ValueError(f"Optimization Item {overlap} appear in both add and delete lists.")

    feature_map = build_feature_map(target_cfg)
    if args.delete_features:
        for feat in args.delete_features:
            if feat not in feature_map:
                raise ValueError(f"Optimization Item {feat} not found in target_file")
            del feature_map[feat]
    if args.add_features:
        for feat in args.add_features:
            feature_cls = FEATURE_MAP[feat]
            feature = feature_cls()
            update_config = feature.generate_config()
            if feat in feature_map:
                logger.warning(
                    f"Optimization Item config [{feat}] already exists, update operation will be performed. "
                    f"Original config: {feature_map[feat]} | New config: {update_config}"
                )
            else:
                logger.info(
                    f"Add new Optimization Item config [{feat}], config content: {update_config}"
                )
            feature_map[feat] = update_config

    update_feature_config = list(feature_map.values())
    target_cfg.OPTIMIZATION_ITEMS = update_feature_config
    yaml_name = "config_backup.yaml"
    backup_yaml = os.path.join(output_dir, yaml_name)
    output_yaml = backup_and_prepare_output(target_file, backup_yaml)
    target_cfg.to_yaml(output_yaml)
    logger.info(f"New target YAML generated at {os.path.abspath(output_yaml)}")
    return


def generate_with_base_only(args, output_dir):
    logger.info(
        "Operation: set all 'deploy' fields in base file to 'Y' and generate new config."
    )

    base_yaml = args.base_file_name
    base_cfg = load_config(base_yaml)

    feature_config = base_cfg.OPTIMIZATION_ITEMS
    if not feature_config:
        raise ValueError("No Optimization Item section found in base YAML")
    for fea in feature_config:
        fea.deploy = "Y"

    output_yaml = args.output_file_name
    base_cfg.to_yaml(output_yaml)
    logger.info(f"New target YAML generated at {os.path.abspath(output_yaml)}")
    return


def generate_with_features_or_scenario(args, output_dir, configfile_map=None):
    logger.info("Operation: generate target_file with Optimization Items.")
    if args.features:
        features = args.features
        feature_map = FEATURE_MAP
    elif args.scenario:
        feature_map, features = load_scenario(args.scenario)
        tuning_count = len(features)
        logger.info(
            f"Based on selected scenario '{args.scenario}', {tuning_count} tuning items are recommended:"
        )
        logger.info(
            f"Detailed tuning items for scenario '{args.scenario}': {' '.join(features)}"
        )
    # 针对 kingbase/opengauss 场景，动态设置 feature config_path
    # 映射规则：优先使用 feature.config_mapping_apps_name，其次回退为 feat_name.lower()
    if configfile_map:
        for feat_name in features:
            if feat_name not in feature_map:
                continue
            feature_cls = feature_map[feat_name]

            dbtype = None
            # 尝试通过临时实例读取 config_mapping_apps_name
            try:
                tmp_inst = feature_cls()
                dbtype = getattr(tmp_inst, "config_mapping_apps_name", None)
            except Exception:
                dbtype = None

            if not dbtype:
                dbtype = feat_name.lower()

            if dbtype in configfile_map and configfile_map[dbtype]:
                # 多实例支持：当前实现只取第一个路径（如需多实例可扩展）
                path = configfile_map[dbtype][0]
                feature_cls.config_path = path
                logger.info(
                    f"Feature '{feat_name}' config_path set from --configfile mapping type '{dbtype}': {path}"
                )
    output_yaml = generate_yaml(
        features, feature_map, output_dir, "target", yaml_path=args.output_file_name
    )
    logger.info(f"Merged YAML generated at {os.path.abspath(output_yaml)}")
    logger.info(
        f"All configurations and logs have been saved to {os.path.abspath(output_dir)}"
    )
    return


def backup_and_prepare_output(
    target_file, backup_yaml
):
    try:
        shutil.copy2(target_file, backup_yaml)
        logger.debug(f"Successfully backed up target file {os.path.abspath(target_file)} to backup: {os.path.abspath(backup_yaml)}")
    except Exception as e:
        raise RuntimeError(
            f"Failed to back up target file! Original file: {os.path.abspath(target_file)}, Backup path: {os.path.abspath(backup_yaml)}, Error: {str(e)}"
        )
    new_output_yaml = target_file

    # 4. 输出 Warning 日志：提示即将生成新文件并覆盖原 target_file
    logger.warning(f"A new configuration file will be generated and overwrite the original target file!")
    logger.warning(f"Original file: {os.path.abspath(target_file)}")
    logger.warning(f"Backup file: {os.path.abspath(backup_yaml)}")
    return new_output_yaml


def validate_output_file_name(args):
    if args.output_file_name:
        validate_yaml_name(args.output_file_name)
        args.output_file_name = validate_output_path_exist(args.output_file_name)
    else:
        raise RuntimeError(
            "Output file name is required! Please specify via -o/--output_file_name (e.g., -o feature.yaml)"
        )


def validate_output_path_exist(file_name):
    current_dir = os.getcwd()
    output_dir = os.path.join(current_dir, "output")
    full_file_path = os.path.join(output_dir, file_name)

    if not os.path.isdir(output_dir):
        raise RuntimeError(
            f"Output directory not found! Current working directory: {current_dir}\n"
            f"Please create the 'output' folder first before proceeding"
        )

    if os.path.isfile(full_file_path):
        raise RuntimeError(
            f"Configuration file already exists! Existing path: {full_file_path}\n"
            f"Please choose a different file name or delete the existing file"
        )

    return full_file_path
