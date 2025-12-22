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
