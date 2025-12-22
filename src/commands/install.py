import datetime
import os
import subprocess
from kaot.utils.log import get_logger, init_logger, LOG_LEVEL
from kaot.install.closesource.ksl_install import install_boostkit_ksl, uninstall_boostkit_ksl

logger = get_logger(__name__)


def register(subparsers):
    parser = subparsers.add_parser(
        "install", help="Install or uninstall BoostKit acceleration suite"
    )
    # -n 参数：特性名称，可多选
    parser.add_argument(
        "-n",
        "--name",
        type=str,
        nargs="+",  # 允许多个值
        choices=["boostkit_ksl"],  # 可选范围
        required=True,
        metavar="",
        help="加速库名称名称 (可多选)，可选boostkit_ksl",
    )
    # -d 参数：指定安装包路径
    parser.add_argument(
        "-d",
        "--dir",
        type=str,
        metavar="",
        help="指定安装包路径, 若不指定则为联网场景，自动生成install_files目录并且将安装包下载到该目录",
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
    # -u 参数：卸载
    parser.add_argument(
        "-u",
        "--uninstall",
        action="store_true",
        help="卸载指定的加速库",
    )

    parser.set_defaults(func=run)


def run(args):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join("./output", "log", f"install_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)

    log_path = os.path.join(output_dir, "install.log")
    init_logger(level=args.log, log_file=log_path)

    if args.uninstall:
        run_uninstall(args)
        return

    if args.dir:
        install_dir = args.dir
        if not os.path.exists(install_dir):
            logger.error(f"Specified installation package path {os.path.abspath(install_dir)} does not exist.")
            return
    else:
        install_dir = os.path.join(output_dir, "install_files")
        os.makedirs(install_dir, exist_ok=True)
        # 联网场景，不指定路径则联网下载到默认路径
        for name in args.name:
            if name in auto_download_url_mapping:
                url = auto_download_url_mapping[name]
                zipfile = url.split("/")[-1]
                dest_path = os.path.join(install_dir, zipfile)
                logger.info(f"Downloading {name} from {url} to {os.path.abspath(dest_path)}...")
                try:
                    subprocess.run(["wget", "-O", dest_path, url], check=True)
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to download {name}: {e}")
                    return
            elif name in manual_download_url_mapping:
                url = manual_download_url_mapping[name]
                logger.error(f"{name} requires manual download. Please visit the following URL, download the package, upload it to your specified directory, and then run: kaot install -n {name} -d <your_dir>")
                logger.error(f"Download URL: {url}")
                return
            else:
                logger.error(f"No download link found for {name}.")
                return
        logger.info(f"No installation package path specified, downloaded to default path {os.path.abspath(install_dir)}.")

    run_install(args, install_dir)


# 支持的安装包列表
install_list = ["boostkit_ksl"]


install_funcs = {
    "boostkit_ksl": install_boostkit_ksl,
}

uninstall_funcs = {
    "boostkit_ksl": uninstall_boostkit_ksl,
}

auto_download_url_mapping = {
}

manual_download_url_mapping = {
    "boostkit_ksl": "https://www.hikunpeng.com/boostkit/library/detail?subtab=Hyperscan",

}


def run_install(args, install_dir):
    if args.name is None:
        logger.info("No package name provided. Please specify a target package.")
        return

    for name in args.name:
        if name in install_list:
            logger.info(f"Package '{name}' is supported. Starting installation...")
            install_func = install_funcs.get(name)
            if install_func:
                install_func(install_dir)
            else:
                logger.error(f"No installation function defined for package '{name}'.")
        else:
            logger.warning(
                f"Package '{name}' is not in the supported install list. Skipping."
            )


def run_uninstall(args):
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
