"""碳排放计算共享工具。

提供资源周转折减后的碳排放因子计算，供优化器和月度报表共用。
"""

from src.models.resource_reuse_config import ResourceReuseConfig


def get_effective_carbon_factor(
    resource_cf: float,
    reuse_cfg: ResourceReuseConfig | None,
) -> float:
    """根据周转配置返回修正后的碳排放因子。

    修正公式：effective_cf = raw_cf / (max_reuses * reuse_count)
    无周转配置时直接返回原始值。
    """
    if reuse_cfg is None:
        return resource_cf
    divisor = max(1, reuse_cfg.max_reuses) * max(1, reuse_cfg.reuse_count)
    return resource_cf / divisor


def compute_resource_emission(
    quantity: float,
    resource_cf: float,
    reuse_cfg: ResourceReuseConfig | None,
) -> float:
    """单条资源用量 × 修正后碳排放因子 = 碳排放量。"""
    return quantity * get_effective_carbon_factor(resource_cf, reuse_cfg)


def get_effective_unit_price(
    unit_price: float,
    reuse_cfg: ResourceReuseConfig | None,
) -> float:
    """根据周转配置返回修正后的单价（仅 affect_cost=True 时修正）。"""
    if reuse_cfg is None or not reuse_cfg.affect_cost:
        return unit_price
    divisor = max(1, reuse_cfg.max_reuses) * max(1, reuse_cfg.reuse_count)
    return unit_price / divisor
