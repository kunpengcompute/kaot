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
    Preserves original line formatting (indentation, spacing, trailing comments).
    """
    if non_config_keys is None:
        non_config_keys = set()
    config_lines = get_config_file_lines(config_path)
    new_lines = config_lines[:]
    keys_to_update = {k for k in config_dict if k not in non_config_keys}
    comment_chars = ('#', ';')
    # 记录每个key最后一次出现的行号
    last_occurrence = {}
    for idx, line in enumerate(config_lines):
        line_strip = line.strip()
        if not line_strip or "=" not in line_strip:
            continue
        # 跳过注释行
        if line_strip.startswith(comment_chars):
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
                new_lines[idx] = None
            else:
                line = config_lines[idx]
                # 保留前导空白（缩进）
                prefix = line[:len(line) - len(line.lstrip())]
                eq_pos = line.find('=')
                if eq_pos != -1:
                    key_part = line[len(prefix):eq_pos + 1]
                    rhs = line[eq_pos + 1:]
                    val_start_spaces = rhs[:len(rhs) - len(rhs.lstrip())]
                    stripped_rhs = rhs.lstrip()

                    # 找到注释起始位置
                    comment_idx = len(stripped_rhs)
                    for c in comment_chars:
                        p = stripped_rhs.find(c)
                        if p != -1 and p < comment_idx:
                            comment_idx = p

                    val_and_padding = stripped_rhs[:comment_idx]
                    new_val_str = str(config_dict[k])
                    actual_old_val = val_and_padding.rstrip()
                    trailing_padding = val_and_padding[len(actual_old_val):]
                    after_part = stripped_rhs[comment_idx:]

                    new_lines[idx] = f"{prefix}{key_part}{val_start_spaces}{new_val_str}{trailing_padding}{after_part}"
                else:
                    new_lines[idx] = f"{prefix}{k} = {config_dict[k]}\n"

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
