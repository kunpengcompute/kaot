import argparse
import datetime
import os
from kaot.commands.generate import (
    FEATURE_INDEX_CHOICES,
    build_help,
    normalize_features,
    parse_feature_input,
    validate_features,
)
from kaot.feature_manager.execute_yaml import run_execute
from kaot.feature_manager.feature import FEATURE_DESCRIPTION
from kaot.utils.common import validate_yaml_name, validate_yaml_path_exist
from kaot.utils.log import init_logger, LOG_LEVEL


def register(subparsers):
    parser = subparsers.add_parser(
        "execute",
        help="Execute feature yaml",
        formatter_class=lambda prog: argparse.RawTextHelpFormatter(prog, width=120),
    )
    # -tp 参数：配置文件路径
    parser.add_argument(
        "-tp",
        "--target_file_name",
        type=str,
        required=True,
        metavar="",
        help="配置文件名称，必选，需为yaml格式，且文件需存在于./output下（如：./output/config.yaml）",
    )
    # -f 参数：特性名称，可多选
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
            info="特性名称（输入序号或名称，可多选，逗号分隔，如 -f 1,2）",
        ),
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
    validate_features(args.features, "features")
    args.features = normalize_features(args.features, FEATURE_INDEX_CHOICES)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join("./output", "log", f"execute_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)

    log_path = os.path.join(output_dir, "execute.log")
    init_logger(level=args.log, log_file=log_path)
    validate_yaml_name(args.target_file_name)
    args.target_file_name = validate_yaml_path_exist(args.target_file_name)
    run_execute(args, output_dir)
