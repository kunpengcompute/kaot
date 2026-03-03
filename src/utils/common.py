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
from typing import Any, Dict, List
from src.utils.log import get_logger

logger = get_logger(__name__)

def parse_configfile(configfile_str, type_to_class, check_path=False, logger=None):
    """
    通用的--configfile参数解析函数。
    :param configfile_str: 传入的字符串，如 kingbase_database:/path1,opengauss_database:/path2
    :param type_to_class: 支持的类型到类的映射dict
    :param check_path: 是否校验路径存在
    :param logger: 日志对象，可选
    :return: dict，key为类型，value为路径列表
    """
    if not configfile_str:
        return {}
    result = {}
    items = [item.strip() for item in configfile_str.split(",") if item.strip()]
    for item in items:
        if ":" not in item:
            msg = f"Invalid --configfile item: {item}, should be type:/path/to/config"
            if logger:
                logger.warning(msg)
            else:
                print(msg)
            continue
        dbtype, path = item.split(":", 1)
        dbtype = dbtype.strip().lower()
        path = path.strip()
        if dbtype not in type_to_class:
            msg = f"Unknown db type '{dbtype}' in --configfile, skip."
            if logger:
                logger.warning(msg)
            else:
                print(msg)
            continue
        if check_path and not os.path.exists(path):
            msg = f"Config file path not found: {path}"
            if logger:
                logger.warning(msg)
            else:
                print(msg)
            continue
        result.setdefault(dbtype, []).append(path)
    return result

def is_features_config_equal(
    base_feature_config: Dict[str, Any],
    target_feature_config: Dict[str, Any],
    exclude_attrs: list = None,
) -> bool:
    exclude_attrs = exclude_attrs or []
    if not isinstance(base_feature_config, dict) or not isinstance(
        target_feature_config, dict
    ):
        raise TypeError("Both inputs must be dictionaries of Optimization Item instances")
    base_keys = set(base_feature_config.keys())
    target_keys = set(target_feature_config.keys())
    if base_keys != target_keys:
        missing_in_target = base_keys - target_keys
        missing_in_base = target_keys - base_keys
        logger.debug(
            f"Optimization Item name mismatch: \n"
            f"Missing in target_feature_config: {missing_in_target}\n"
            f"Missing in base_feature_config: {missing_in_base}"
        )
        return False

    for feat_name in base_keys:
        base_instance = base_feature_config[feat_name]
        target_instance = target_feature_config[feat_name]

        if not hasattr(base_instance, "__dict__") or not hasattr(
            target_instance, "__dict__"
        ):
            raise TypeError(
                f"Optimization Item [{feat_name}] value is not a custom class instance"
            )

        base_attrs = base_instance.__dict__.copy()
        target_attrs = target_instance.__dict__.copy()

        for attr in exclude_attrs:
            base_attrs.pop(attr, None)
            target_attrs.pop(attr, None)

        if base_attrs != target_attrs:
            logger.debug(
                f"Optimization Item [{feat_name}] instance mismatch: \n"
                f"base Optimization Item config attrs: {base_attrs}\n"
                f"target Optimization Item config attrs: {target_attrs}"
            )
            return False

    return True


def validate_subset(selected: List[str], valid: List[str]):
    """
    校验 selected 是否为 valid 的子集。
    如果 selected 中有元素不在 valid 中，则抛出 ValueError。
    """
    invalid = [f for f in selected if f not in valid]
    if invalid:
        raise ValueError(
            f"Invalid Optimization Items: {invalid}. "
            f"Optimization Items {selected} must be a subset of {valid}."
        )
    return


def build_feature_map(config):
    feature_map = {}
    feature_config = config.OPTIMIZATION_ITEMS

    for config in feature_config:
        name = config.name
        feature_map[name] = config

    return feature_map


def get_feature_keys(config):
    feature_map = build_feature_map(config)
    name_set = list(feature_map.keys())

    return name_set


def validate_yaml_name(file_name):
    yaml_suffixes = (".yaml", ".yml")
    if not file_name.lower().endswith(yaml_suffixes):
        raise RuntimeError(
            f"file name must be a YAML format file (suffix .yaml or .yml). Current input: {file_name}"
        )


def validate_yaml_path_exist(file_name):
    current_dir = os.getcwd()
    output_dir = os.path.join(current_dir, "output")
    full_file_path = os.path.join(output_dir, file_name)

    if not os.path.isdir(output_dir):
        raise RuntimeError(
            f"Output directory not found! Current working directory: {current_dir}\nPlease create the 'output' folder first and place the target file in it"
        )
    if not os.path.isfile(full_file_path):
        raise RuntimeError(
            f"Configuration file does not exist! Please verify the path: {full_file_path}\n"
            f"Note: The file must be placed in the 'output' folder of the current directory and have a .yaml/.yml suffix"
        )

    return full_file_path
