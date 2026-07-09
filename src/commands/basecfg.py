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
import argparse
import datetime
import os
from src.feature_manager.generate_yaml import generate_yaml
from src.utils.log import init_logger, get_logger, LOG_LEVEL
from src.feature_manager.feature import FEATURE_MAP, FEATURE_NAMES, SUPPORTED_APPS
from src.utils.common import parse_configfile

logger = get_logger(__name__)


def register(subparsers):
    parser = subparsers.add_parser(
        "basecfg", help="Generate a base configuration file in YAML format containing all Optimization Items.",
        formatter_class=lambda prog: argparse.RawTextHelpFormatter(prog, width=120),
    )
    # -l 参数：日志级别，仅单选
    parser.add_argument(
        "-l",
        "--log",
        type=str,
        choices=LOG_LEVEL,  # 可选范围
        default="info",
        metavar="",
        help=f"日志级别 (可选{','.join(LOG_LEVEL)})",
    )

    parser.add_argument(
        "--configfile",
        type=str,
        metavar="",
        help=(
            "可选参数\n"
            "格式：应用1：/path1, 应用2：/path2。 示例：kingbase_database:/opt/Kingbase/ES/V8/data/kingbase.conf,opengauss_database:/opt/openGuass/data/postgresql.conf\n"
            "用逗号分隔多个实例或应用。路径为应用的配置文件路径\n"
            "当前版本支持 kingbase_database（金仓数据库）、opengauss_database（openGauss数据库）和 dameng_database（达梦数据库）"
        ),
    )
    parser.set_defaults(func=run)


def run(args):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join("./output", "log", f"basecfg_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)

    log_path = os.path.join(output_dir, "basecfg.log")
    init_logger(level=args.log, log_file=log_path)


    # 处理--configfile参数，优先用用户指定路径，否则用feature默认路径
    configfile_map = parse_configfile(
        getattr(args, "configfile", None),
        SUPPORTED_APPS,
        check_path=True,
    )

    # 方案1：按实例粒度设置 config_path，将实例传入 generate_yaml
    feature_instances = []
    for name in FEATURE_NAMES:
        feature_cls = FEATURE_MAP[name]
        instance = feature_cls()

        # 根据实例上的 config_mapping_apps_name 找到对应的应用类型映射
        config_mapping_apps_name = getattr(instance, "config_mapping_apps_name", name)
        user_paths = configfile_map.get(config_mapping_apps_name)
        if user_paths and user_paths[0]:
            instance.config_path = user_paths[0]
            logger.info(
                f"Feature '{name}' instance config_path set to user value: {user_paths[0]}"
            )

        feature_instances.append(instance)

    feature_map = {inst.name: inst for inst in feature_instances}
    features = [inst.name for inst in feature_instances]
    output_yaml = generate_yaml(features, feature_map, output_dir, "base")

    logger.info(f"Merged YAML generated at {os.path.abspath(output_yaml)}")
    logger.info(f"All configurations and logs have been saved to: {os.path.abspath(output_dir)}")
