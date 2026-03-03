# coding: utf-8
"""
Common database config file utilities for feature classes.
Provides parameter lookup and config file update logic for Kingbase, OpenGauss, and future database features.
"""
import os
import logging

logger = logging.getLogger(__name__)

def get_config_file_lines(config_path):
    """Read config file lines, return list."""
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return f.readlines()
    return []

def find_last_value_in_config(key, config_lines):
    """Find last value for key in config file lines, ignoring comments."""
    values = []
    for line in config_lines:
        line_no_comment = line.split('#', 1)[0].strip()
        if not line_no_comment:
            continue
        if "=" in line_no_comment:
            k, v = line_no_comment.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k == key:
                values.append(v)
    return values[-1] if values else None

def update_config_file(config_path, config_dict, non_config_keys=None):
    """
    Update config file with values from config_dict.
    Only keys not in non_config_keys are updated.
    """
    if non_config_keys is None:
        non_config_keys = set()
    config_lines = get_config_file_lines(config_path)
    new_lines = config_lines[:]
    keys_to_update = {k for k in config_dict if k not in non_config_keys}
    # 记录每个key最后一次出现的行号
    last_occurrence = {}
    for idx, line in enumerate(config_lines):
        line_strip = line.strip()
        if not line_strip or line_strip.startswith("#") or "=" not in line_strip:
            continue
        k, v = line_strip.split("=", 1)
        k = k.strip()
        if k in keys_to_update:
            last_occurrence[k] = idx

    # 先处理已存在的（只改最后一个）
    for k in keys_to_update:
        if k in last_occurrence:
            idx = last_occurrence[k]
            if config_dict[k] is None:
                # 删除该行
                new_lines[idx] = None
            else:
                # 保留原行前后空白和注释
                line = config_lines[idx]
                prefix = line[:line.find(k)] if line.find(k) != -1 else ''
                # 只保留key=val，去掉原注释
                new_line = f"{prefix}{k} = {config_dict[k]}\n"
                new_lines[idx] = new_line

    # 再处理没出现过的，且值不为None，追加到文件末尾
    for k in keys_to_update:
        if k not in last_occurrence and config_dict[k] is not None:
            new_line = f"{k} = {config_dict[k]}\n"
            new_lines.append(new_line)

    # 删除被标记为None的行
    new_lines = [line for line in new_lines if line is not None]

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        return True
    except Exception as e:
        logger.exception(f"Failed to update config file: {e}")
        return False
