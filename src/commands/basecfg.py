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
import datetime
import os
from src.feature_manager.generate_yaml import generate_yaml
from src.utils.log import init_logger, get_logger, LOG_LEVEL
from src.feature_manager.feature import FEATURE_MAP, FEATURE_NAMES

logger = get_logger(__name__)


def register(subparsers):
    parser = subparsers.add_parser(
        "basecfg", help="Generate base feature yaml(all feature)"
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

    parser.set_defaults(func=run)


def run(args):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join("./output", "log", f"basecfg_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)

    log_path = os.path.join(output_dir, "basecfg.log")
    init_logger(level=args.log, log_file=log_path)
    feature_map = FEATURE_MAP
    features = FEATURE_NAMES

    output_yaml = generate_yaml(features, feature_map, output_dir, "base")

    logger.info(f"Merged YAML generated at {os.path.abspath(output_yaml)}")
    logger.info(f"All configurations and logs have been saved to: {os.path.abspath(output_dir)}")
