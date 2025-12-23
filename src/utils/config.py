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
from typing import Any, List
from pydantic import BaseModel, field_validator
import yaml

from src.feature_manager.feature import FEATURE_MAP
from src.feature_manager.feature.base import BaseFeature
from src.utils.env import EnvConfig


class TotalConfig(BaseModel):
    SYSTEM_INFO: EnvConfig
    FEATURES: List[Any]

    @field_validator("FEATURES", mode="before")
    def parse_features(cls, value):
        parsed = []

        for idx, item in enumerate(value):
            if isinstance(item, BaseFeature):
                parsed.append(item)
                continue
            if not isinstance(item, dict):
                raise ValueError(
                    f"[FEATURES[{idx}]] must be dict or Feature instance, got: {type(item)}"
                )
            if "name" not in item:
                raise ValueError(f"[FEATURES[{idx}]] missing 'name' field: {item}")
            name = item["name"]
            if name not in FEATURE_MAP:
                raise ValueError(f"[FEATURES[{idx}]] unknown feature name '{name}'")
            ft_cls = FEATURE_MAP[name]

            valid_fields = set(ft_cls.model_fields.keys())
            input_fields = set(item.keys())
            unknown_fields = input_fields - valid_fields
            if unknown_fields:
                raise ValueError(
                    f"[FEATURES[{idx}] '{name}'] unknown fields: {unknown_fields}. "
                    f"Allowed fields are: {valid_fields}"
                )
            parsed.append(ft_cls(**item))
        return parsed

    def to_yaml(self, path):
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(
                self.model_dump(), f, sort_keys=False, allow_unicode=True, indent=2
            )


def load_config(path: str) -> TotalConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return TotalConfig(**data)
