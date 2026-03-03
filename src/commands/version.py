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
from src.utils.log import init_logger, get_logger
from src import VERSION

logger = get_logger(__name__)

# 获取版本号常量
KAOT_VERSION = VERSION


def register(subparsers):
    parser = subparsers.add_parser(
        "version", help="show the kaot tool version."
    )
    # 添加可选的详细版本信息参数
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="show detailed version information"
    )


def run(args):
    """执行version命令"""
    if args.verbose:
        # 详细版本信息
        print(f"kaot version {KAOT_VERSION}")
        print(f"Copyright (c) 2025 Huawei Technologies Co., Ltd")
        print(f"License: Apache License 2.0")
    else:
        # 简介版本信息
        print(f"kaot version {KAOT_VERSION}")
        