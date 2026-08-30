"""中国省市行政区划校验。"""

import json
from functools import lru_cache
from pathlib import Path

_DATA_PATH = Path(__file__).with_name("china_region_data.json")


@lru_cache(maxsize=1)
def _load_regions() -> dict[str, frozenset[str]]:
    """加载由原始行政区划数据预处理得到的省市索引。"""
    with _DATA_PATH.open(encoding="utf-8") as file:
        raw_data: dict[str, list[str]] = json.load(file)
    return {province: frozenset(cities) for province, cities in raw_data.items()}


def validate_province_city(
    province: str | None,
    city: str | None,
) -> None:
    """校验省市是否存在且属于同一行政区划。"""
    if province is None or city is None:
        return

    regions = _load_regions()
    if province not in regions:
        raise ValueError(f"省份不存在：{province}")
    if city not in regions[province]:
        raise ValueError(f"城市不属于省份{province}：{city}")


__all__ = ["validate_province_city"]
