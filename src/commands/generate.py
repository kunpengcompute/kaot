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
from src.feature_manager.generate_yaml import run_generate
from src.feature_manager.feature import (
    FEATURE_DESCRIPTION,
    SCENARIO_DESCRIPTION,
    FEATURE_MAP,
    SUPPORTED_APPS,
)
from src.utils.common import parse_configfile
from src.utils.log import init_logger, LOG_LEVEL

FEATURE_INDEX_CHOICES = {str(i + 1): name for i, name in enumerate(FEATURE_DESCRIPTION)}
SCENARIO_INDEX_CHOICES = {
    str(i + 1): name for i, name in enumerate(SCENARIO_DESCRIPTION)
}

generate_description = """Usage：
  1. 根据调优项生成配置文件：指定输出文件名称
    python kaot.py generate -f 1,2 -o feature.yaml
  2. 根据场景生成配置文件：指定输出文件名称
    python kaot.py generate -s 1 -o feature.yaml
  3. 增减调优配置文件的调优项：修改原有配置文件
    python kaot.py generate -tp feature.yaml -af 1,2 -df 3
  4. 修改基线文件deploy值为Y：指定输出文件名称
    python kaot.py generate -bp base_config.yaml -o target.yaml
  5. 同步基线文件指定调优项配置到配置文件中：修改原有配置文件
    python kaot.py generate -bp base_config.yaml -tp target.yaml -f 5
"""


def _features_require_configfile(features):
    """判断当前选择的调优项中，是否包含需要 --configfile 的数据库类调优项。

    规则：如果任意调优项名称（不区分大小写）包含任意 SUPPORTED_APPS 中的应用名
    （同样不区分大小写，例如 kingbase_database、opengauss_database），则视为需要
    传入 --configfile。
    """
    if not features:
        return False
    supported = [app.lower() for app in SUPPORTED_APPS]
    for feat in features:
        name = str(feat).lower()
        for app in supported:
            if app in name:
                return True
    return False


def register(subparsers):
    parser = subparsers.add_parser(
        "generate",
        help="Generate target Optimization Item config yaml",
        description=generate_description,
        formatter_class=lambda prog: argparse.RawTextHelpFormatter(prog, width=120),
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
    parser.add_argument(
        "-o",
        "--output_file_name",
        type=str,
        metavar="",
        help="输出文件名称，可选，需为yaml格式，文件会生成./output下（如：./output/target.yaml）",
    )
    # -f 参数：调优项名称，可多选
    parser.add_argument(
        "-f",
        "--features",
        type=parse_feature_input,
        nargs="?",
        const=[],
        metavar="",
        help=build_help(
            FEATURE_INDEX_CHOICES,
            FEATURE_DESCRIPTION,
            info="调优项名称（输入序号或名称，可多选，逗号分隔，如 -f 1,2）",
        ),
    )
    # -s 参数：场景名称
    parser.add_argument(
        "-s",
        "--scenario",
        type=str,
        choices=list(SCENARIO_INDEX_CHOICES.values())
        + list(SCENARIO_INDEX_CHOICES.keys()),  # 可选范围
        metavar="",
        help=build_help(
            SCENARIO_INDEX_CHOICES,
            SCENARIO_DESCRIPTION,
            info="调优场景名称（输入序号或名称，仅单选，如 -s 1）",
        ),
    )
    # -tp 参数：配置文件路径
    parser.add_argument(
        "-tp",
        "--target_file_name",
        type=str,
        metavar="",
        help="配置文件名称，必选，需为yaml格式，且文件需存在于./output下（如：./output/feature.yaml）",
    )
    # -bp 参数：基线文件路径
    parser.add_argument(
        "-bp",
        "--base_file_name",
        type=str,
        metavar="",
        help="基线文件名称，必选，需为yaml格式，且文件需存在于./output下（如：./output/base.yaml）"
    )
    # -af 参数：增加调优项的名称，可多选
    parser.add_argument(
        "-af",
        "--add_features",
        type=parse_feature_input,
        nargs="?",
        const=[],
        metavar="",
        help=f"增加调优项的名称 (允许同时增加多个调优项)，可选范围同-f参数",
    )
    # -df 参数：删除调优项的名称，可多选
    parser.add_argument(
        "-df",
        "--delete_features",
        type=parse_feature_input,
        nargs="?",
        const=[],
        metavar="",
        help=f"删除调优项的名称 (允许同时删除多个调优项)，可选范围同-f参数",
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


def parse_feature_input(value):
    features = [feat.strip() for feat in value.split(",") if feat.strip()]
    return list(dict.fromkeys(features))


def build_help(CHOICES, DESCRIPTION, info=""):
    lines = []
    lines.append(info)
    lines.append("可选范围：")
    for index, name in CHOICES.items():
        desc = DESCRIPTION[name]
        lines.append(f"  {index}. {name:30} {desc}")
    return " \n".join(lines)


def run(args):
    # 处理--configfile参数，强制 opengauss/kingbase/dameng 相关场景或调优项必须指定
    scenario_requires_configfile = {"kingbase_database", "opengauss_database", "dameng_database"}

    validate_features(args.features, "features")
    validate_features(args.add_features, "add_features")
    validate_features(args.delete_features, "delete_features")
    # 解析features、add_features、delete_features
    args.features = normalize_features(args.features, FEATURE_INDEX_CHOICES)
    args.add_features = normalize_features(args.add_features, FEATURE_INDEX_CHOICES)
    args.delete_features = normalize_features(
        args.delete_features, FEATURE_INDEX_CHOICES
    )
    # 解析 scenario
    if args.scenario:
        args.scenario = normalize_features([args.scenario], SCENARIO_INDEX_CHOICES)[0]
   
   
    # 根据场景 & 调优项判断是否必须传入 --configfile
    is_configfile_required = (
        args.scenario in scenario_requires_configfile
        or _features_require_configfile(args.features)
    )
    
    configfile_str = getattr(args, "configfile", None)
    # 验证：如果需要configfile但未提供，则报错
    if is_configfile_required and not configfile_str:
        if args.scenario in scenario_requires_configfile:
            raise ValueError(
                f"Scenario '{args.scenario}' requires --configfile parameter. "
                f"Supported types: {', '.join(sorted(SUPPORTED_APPS))}"
            )
        else:
            raise ValueError(
                f"Feature '{', '.join(args.features)}' requires --configfile parameter. "
                f"Supported types: {', '.join(sorted(SUPPORTED_APPS))}"
            )

    # 验证：如果提供了configfile但不是必需的，则报错
    if not is_configfile_required and configfile_str:
        raise ValueError(
            "The --configfile parameter is not required for the selected scenario or features. "
            "Please remove it or select a database-related scenario/feature."
        )

     # 解析 configfile
    configfile_map = parse_configfile(
        configfile_str,
        SUPPORTED_APPS,
        check_path=True,
    ) if configfile_str else {}

    # 验证: 目前不支持多实例场景，验证congfigfile参数只能输入一个并且必须是跟feature/scenario相关的
    if len(configfile_map) > 1:
        raise ValueError(
            "Multiple --configfile parameters are not supported in generate mode. "
            "Please specify only one type of database."
        )
    
    # 验证：configfile_map返回的dbtype是否为当前所选scenario或feature名称的子字符串
    if configfile_map:
        dbtype = list(configfile_map.keys())[0]  # 获取唯一的数据库类型
        scenario_or_feature = ""
        
        if args.scenario:
            scenario_or_feature = args.scenario.lower()
        elif args.features:
            # 检查所有features是否都包含相同的dbtype
            for feature in args.features:
                if dbtype in feature.lower():
                    break
            else:
                raise ValueError(
                    f"The database type '{dbtype}' in --configfile does not match the selected features/scenario. "
                    f"The selected features/scenario do not contain '{dbtype}'. Please check your input."
                )
        else:
            # 如果既没有指定scenario也没有指定features，但在之前已经验证了这种情况不会发生
            pass

        # 检查dbtype是否为scenario或feature名称的子字符串
        if args.scenario and dbtype not in scenario_or_feature:
            raise ValueError(
                f"The database type '{dbtype}' in --configfile does not match the selected scenario '{args.scenario}'. "
                f"'{dbtype}' should be a substring of '{args.scenario}'. Please check your input."
            )
        elif args.features:
            # 检查当前dbtype是否与任何feature名称匹配
            feature_matches_dbtype = any(dbtype in feature.lower() for feature in args.features)
            if not feature_matches_dbtype:
                feature_list = "', '".join(args.features) if args.features else ""
                raise ValueError(
                    f"The database type '{dbtype}' in --configfile does not match the selected features '{feature_list}'. Please check your input."
                )



    # 将configfile_map挂到args上，供后续generate_yaml使用
    args.configfile_map = configfile_map

    # 校验依赖关系
    validate_args(args)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join("./output", "log", f"generate_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)

    log_path = os.path.join(output_dir, "generate.log")
    init_logger(level=args.log, log_file=log_path)
    from src.feature_manager import generate_yaml as _gen_yaml_mod
    _gen_yaml_mod.run_generate(args, output_dir)


def validate_args(args):
    # 如果没有选择 --features/--scenario
    if not args.features and not args.scenario:
        # 那么必须至少有 -bp 或 -tp
        if not args.target_file_name and not args.base_file_name:
            raise ValueError("You must specify -f, -s, or (-bp or -tp)")
    # -af/-df 必须和 -tp 配套使用
    if (args.add_features or args.delete_features) and not args.target_file_name:
        raise ValueError("参数 -af/-df 只能在使用 -tp 时指定")
    if args.target_file_name and not (
        args.base_file_name or args.add_features or args.delete_features
    ):
        raise ValueError("只使用-tp参数时，需配合-af或-df参数使用")


def validate_features(features, args_name):
    valid_options = list(FEATURE_INDEX_CHOICES.values()) + list(
        FEATURE_INDEX_CHOICES.keys()
    )
    if features:
        for feat in features:
            if feat not in valid_options:
                raise RecursionError(
                    f"Invalid Optimization Item '{feat}' for --{args_name}. Valid options are: {', '.join(valid_options)}"
                )
            if " " in feat:
                raise RecursionError(
                    f"Invalid format for -f: spaces are not allowed. Use comma-separated values (e.g., -f 1,2)."
                )


def normalize_features(values, CHOICES):
    """将序号转换为名称，名称保持不变，最终去重"""
    if not values:
        return None
    values_set = set()
    result = []
    for v in values:
        if v in CHOICES:
            name = CHOICES[v]
        else:
            name = v
        if name not in values_set:
            values_set.add(name)
            result.append(name)

    return result
