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
from src.utils.log import get_logger, init_logger, LOG_LEVEL
from src.install.closesource.boostkit_ksl import uninstall_boostkit_ksl
from src.install.closesource.bisheng_jdk_fusion import uninstall_bisheng_jdk_fusion

logger = get_logger(__name__)

# 支持的卸载包列表
uninstall_list = ["boostkit_ksl", "bisheng_jdk_fusion"]

uninstall_funcs = {
    "boostkit_ksl": uninstall_boostkit_ksl,
    "bisheng_jdk_fusion": uninstall_bisheng_jdk_fusion,
}


def register(subparsers):
    parser = subparsers.add_parser(
        "uninstall", help="Uninstall BoostKit acceleration suite"
    )
    # -n 参数：特性名称，可多选
    parser.add_argument(
        "-n",
        "--name",
        type=str,
        nargs="+",  # 允许多个值
        choices=["boostkit_ksl", "bisheng_jdk_fusion"],  # 可选范围
        required=True,
        metavar="",
        help="加速库名称 (可多选)，可选boostkit_ksl,bisheng_jdk_fusion"
    )
    # -l 参数：日志级别，仅单选
    parser.add_argument(
        "-l",
        "--log",
        type=str,
        choices=LOG_LEVEL,  # 可选范围
        default="info",
        metavar="",
        help=f"日志级别 (可选{','.join(LOG_LEVEL)})"
    )

    parser.set_defaults(func=run)


def run(args):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join("./output", "log", f"uninstall_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)

    log_path = os.path.join(output_dir, "uninstall.log")
    init_logger(level=args.log, log_file=log_path)

    if args.name is None:
        logger.info("No package name provided. Please specify a target package.")
        return

    for name in args.name:
        uninstall_func = uninstall_funcs.get(name)
        if uninstall_func:
            logger.info(f"Uninstalling package '{name}' ...")
            uninstall_func()
        else:
            logger.error(f"No uninstall function defined for package '{name}'.")