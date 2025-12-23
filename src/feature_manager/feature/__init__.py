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
import pkgutil
import importlib
from typing import List, Optional, Type, Dict
from kaot.feature_manager.feature.base import BaseFeature


FEATURE_MAP: Dict[str, Type["BaseFeature"]] = {}
FEATURE_NAMES = []
SCENARIO_FEATURES: dict[str, list[str]] = {}
FEATURE_DESCRIPTION = {}
ALL_SCENARIO_DESCRIPTION = {
    "boundary_gateway_appliance": "边界网关一体机场景",
    "common": "通用场景",
    "ssaf": "ssss",
}
SCENARIO_DESCRIPTION = {}

def register_feature(*, scenarios: Optional[List[str]] = None):
    """Decorator to register feature class with optional scenarios."""

    def wrapper(cls):
        name_default = cls.model_fields["name"].default
        if name_default is None:
            raise ValueError(
                f"Feature class {cls.__name__} must define default 'name' value"
            )

        FEATURE_MAP[name_default] = cls
        FEATURE_NAMES.append(name_default)

        if scenarios:
            for sc in scenarios:
                if sc not in ALL_SCENARIO_DESCRIPTION:
                    raise RuntimeError(
                        f"Invalid scenario '{sc}'. Supported scenarios are: {', '.join(ALL_SCENARIO_DESCRIPTION.keys())}"
                    )
                SCENARIO_FEATURES.setdefault(sc, []).append(name_default)
                SCENARIO_DESCRIPTION[sc] = ALL_SCENARIO_DESCRIPTION[sc]

        return cls

    return wrapper


for module_info in pkgutil.iter_modules(__path__):
    if module_info.name == "base":
        continue
    module = importlib.import_module(f"{__name__}.{module_info.name}")
    FEATURE_DESCRIPTION[module.FEATURE_NAME] = module.FEATURE_DES


def load_scenario(scenario: str):
    """
    根据场景返回对应的 feature_map 和 features 列表
    """
    if scenario not in SCENARIO_FEATURES:
        raise ValueError(f"Unknown scenario: {scenario}")
    selected_features = SCENARIO_FEATURES[scenario]
    feature_map = {name: FEATURE_MAP[name] for name in selected_features}
    return feature_map, selected_features
