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
import importlib
import pkgutil
from kaot.commands import __path__ as commands_path


def load_commands():
    """
    自动扫描 kaot/commands/*.py
    返回格式：
    {
        "generate": <module>,
        "execute": <module>,
        ...
    }
    """
    command_map = {}

    # 遍历 commands 目录下的所有模块（排除 __init__.py）
    for module_info in pkgutil.iter_modules(commands_path):
        module_name = module_info.name  # generate / execute / others
        module = importlib.import_module(f"kaot.commands.{module_name}")

        # 必须包含 register() 和 run()
        if hasattr(module, "register") and hasattr(module, "run"):
            command_map[module_name] = module

    return command_map


def main():
    parser = argparse.ArgumentParser(
        prog="kaot", description="KunPeng & Ascend Auto Optimization Tool"
    )

    subparsers = parser.add_subparsers(dest="command", title="Subcommands")

    # 自动注册所有子命令
    commands = load_commands()
    for _, module in commands.items():
        module.register(subparsers)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # 执行对应子命令
    commands[args.command].run(args)
