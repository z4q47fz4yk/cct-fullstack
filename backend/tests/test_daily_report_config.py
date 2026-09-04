"""施工日报解析引擎配置校验单元测试"""
# pyright: reportCallIssue=false

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.utils.daily_report_config import (
    CleaningSpec,
    FieldSpec,
    ParseEngineConfig,
    PartSpec,
    RowSpec,
    load_config,
    reset_cache,
)


@pytest.fixture(autouse=True)
def _clear_config_cache():
    reset_cache()
    yield
    reset_cache()


class TestDefaultConfig:
    """默认 bundled 配置"""

    def test_loads_with_all_blocks(self):
        cfg = load_config()
        assert isinstance(cfg, ParseEngineConfig)
        assert len(cfg.blocks) == 3
        assert cfg.blocks[0].category == "labor"
        assert cfg.blocks[1].category == "machinery"
        assert cfg.blocks[2].category == "transport"
        assert cfg.blocks[2].cargo_dimension == "运输货物"

    def test_each_block_has_name_and_quantity_fields(self):
        cfg = load_config()
        for blk in cfg.blocks:
            assert "name" in blk.fields
            assert "quantity" in blk.fields

    def test_compiled_patterns_cached(self):
        """label 并集与各 row regex 已挂到实例上"""
        cfg = load_config()
        for blk in cfg.blocks:
            assert blk.label_at_column == 0
            for row in blk.rows:
                # 并集必须能匹配每个 row 的标签（并集 = rows[*].label_regex 的 OR）
                assert blk._label_union  # 非空字符串
                assert row._compiled_label.pattern == row.label_regex
                assert row._compiled_content.pattern == row.content_regex


class TestRegexValidation:
    """坏 regex 应在校验阶段抛错"""

    def test_bad_label_regex_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            ParseEngineConfig.model_validate({
                "blocks": [
                    {
                        "category": "labor",
                        "label_at_column": 0,
                        "rows": [
                            {
                                "label_regex": "([",  # 未闭合
                                "content_regex": "(.+)",
                            },
                            {
                                "label_regex": "人员数量",
                                "content_regex": "(\\d+)",
                            },
                        ],
                        "fields": {
                            "name": {"parts": [{"row": 0, "group": 0}]},
                            "quantity": {"parts": [{"row": 1, "group": 1}]},
                        },
                    }
                ]
            })
        assert "label_regex" in str(exc_info.value)
        assert "编译失败" in str(exc_info.value)

    def test_bad_content_regex_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            ParseEngineConfig.model_validate({
                "blocks": [
                    {
                        "category": "labor",
                        "label_at_column": 0,
                        "rows": [
                            {
                                "label_regex": "现场人员",
                                "content_regex": "(.+)",
                            },
                            {
                                "label_regex": "人员数量",
                                "content_regex": "(\\d+",  # 未闭合
                            },
                        ],
                        "fields": {
                            "name": {"parts": [{"row": 0, "group": 0}]},
                            "quantity": {"parts": [{"row": 1, "group": 1}]},
                        },
                    }
                ]
            })
        assert "content_regex" in str(exc_info.value)


class TestFieldRequirements:
    """必填字段缺失"""

    def test_missing_name_field(self):
        with pytest.raises(ValidationError) as exc_info:
            ParseEngineConfig.model_validate({
                "blocks": [
                    {
                        "category": "labor",
                        "label_at_column": 0,
                        "rows": [
                            {"label_regex": "a", "content_regex": "(.+)"},
                            {"label_regex": "b", "content_regex": "(\\d+)"},
                        ],
                        "fields": {
                            "quantity": {"parts": [{"row": 1, "group": 1}]},
                        },
                    }
                ]
            })
        assert "name" in str(exc_info.value)

    def test_missing_quantity_field(self):
        with pytest.raises(ValidationError) as exc_info:
            ParseEngineConfig.model_validate({
                "blocks": [
                    {
                        "category": "labor",
                        "label_at_column": 0,
                        "rows": [
                            {"label_regex": "a", "content_regex": "(.+)"},
                            {"label_regex": "b", "content_regex": "(\\d+)"},
                        ],
                        "fields": {
                            "name": {"parts": [{"row": 0, "group": 0}]},
                        },
                    }
                ]
            })
        assert "quantity" in str(exc_info.value)


class TestRowIndexBounds:
    """parts[].row 必须落在 rows 索引范围内"""

    def test_out_of_range_row_index(self):
        with pytest.raises(ValidationError) as exc_info:
            ParseEngineConfig.model_validate({
                "blocks": [
                    {
                        "category": "labor",
                        "label_at_column": 0,
                        "rows": [
                            {"label_regex": "a", "content_regex": "(.+)"},
                            {"label_regex": "b", "content_regex": "(\\d+)"},
                        ],
                        "fields": {
                            "name": {"parts": [{"row": 0, "group": 0}]},
                            "quantity": {
                                "parts": [{"row": 5, "group": 1}]  # 越界
                            },
                        },
                    }
                ]
            })
        assert "越界" in str(exc_info.value)
        assert "rows 长度为 2" in str(exc_info.value)

    def test_negative_row_index(self):
        with pytest.raises(ValidationError):
            ParseEngineConfig.model_validate({
                "blocks": [
                    {
                        "category": "labor",
                        "label_at_column": 0,
                        "rows": [
                            {"label_regex": "a", "content_regex": "(.+)"},
                            {"label_regex": "b", "content_regex": "(\\d+)"},
                        ],
                        "fields": {
                            "name": {"parts": [{"row": -1, "group": 0}]},
                            "quantity": {"parts": [{"row": 1, "group": 1}]},
                        },
                    }
                ]
            })

    def test_negative_group(self):
        with pytest.raises(ValidationError):
            ParseEngineConfig.model_validate({
                "blocks": [
                    {
                        "category": "labor",
                        "label_at_column": 0,
                        "rows": [
                            {"label_regex": "a", "content_regex": "(.+)"},
                            {"label_regex": "b", "content_regex": "(\\d+)"},
                        ],
                        "fields": {
                            "name": {"parts": [{"row": 0, "group": -1}]},
                            "quantity": {"parts": [{"row": 1, "group": 1}]},
                        },
                    }
                ]
            })


class TestExtraKeys:
    """extra=forbid：未知顶层 / 嵌套键应被拒"""

    def test_unknown_top_level_key(self):
        with pytest.raises(ValidationError):
            ParseEngineConfig.model_validate({
                "blocks": [
                    {
                        "category": "labor",
                        "label_at_column": 0,
                        "rows": [
                            {"label_regex": "a", "content_regex": "(.+)"},
                            {"label_regex": "b", "content_regex": "(\\d+)"},
                        ],
                        "fields": {
                            "name": {"parts": [{"row": 0, "group": 0}]},
                            "quantity": {"parts": [{"row": 1, "group": 1}]},
                        },
                        "extra_top_key": "nope",
                    }
                ]
            })

    def test_unknown_field_spec_key(self):
        """FieldSpec 内部未知键（如 ``sep_misspelled``）应被拒"""
        with pytest.raises(ValidationError):
            ParseEngineConfig.model_validate({
                "blocks": [
                    {
                        "category": "labor",
                        "label_at_column": 0,
                        "rows": [
                            {"label_regex": "a", "content_regex": "(.+)"},
                            {"label_regex": "b", "content_regex": "(\\d+)"},
                        ],
                        "fields": {
                            "name": {
                                "parts": [{"row": 0, "group": 0}],
                                "sep_typo": "",
                            },
                            "quantity": {"parts": [{"row": 1, "group": 1}]},
                        },
                    }
                ]
            })

    def test_unknown_part_key(self):
        with pytest.raises(ValidationError):
            ParseEngineConfig.model_validate({
                "blocks": [
                    {
                        "category": "labor",
                        "label_at_column": 0,
                        "rows": [
                            {"label_regex": "a", "content_regex": "(.+)"},
                            {"label_regex": "b", "content_regex": "(\\d+)"},
                        ],
                        "fields": {
                            "name": {"parts": [{"row": 0, "group": 0, "extra": "y"}]},
                            "quantity": {"parts": [{"row": 1, "group": 1}]},
                        },
                    }
                ]
            })


class TestCategoryValidation:
    """category 必须是 ResourceCategory 成员"""

    def test_unknown_category_rejected(self):
        with pytest.raises(ValidationError):
            ParseEngineConfig.model_validate({
                "blocks": [
                    {
                        "category": "vehicle",  # 不在 ResourceCategory 中
                        "label_at_column": 0,
                        "rows": [
                            {"label_regex": "a", "content_regex": "(.+)"},
                            {"label_regex": "b", "content_regex": "(\\d+)"},
                        ],
                        "fields": {
                            "name": {"parts": [{"row": 0, "group": 0}]},
                            "quantity": {"parts": [{"row": 1, "group": 1}]},
                        },
                    }
                ]
            })


class TestCaching:
    """load_config 缓存行为"""

    def test_caches_default(self):
        cfg1 = load_config()
        cfg2 = load_config()
        assert cfg1 is cfg2

    def test_force_reload_returns_new_instance(self):
        cfg1 = load_config()
        cfg2 = load_config(force_reload=True)
        assert cfg1 is not cfg2
        # 但内容等价
        assert len(cfg1.blocks) == len(cfg2.blocks)
        assert cfg1.blocks[0].category == cfg2.blocks[0].category

    def test_explicit_path_not_cached(self, tmp_path: Path):
        """显式传 path 时不读写全局缓存"""
        cfg_path = tmp_path / "custom.json"
        cfg_path.write_text(
            json.dumps({
                "blocks": [
                    {
                        "category": "labor",
                        "label_at_column": 0,
                        "rows": [
                            {
                                "label_regex": "a",
                                "content_regex": "(.+)",
                            },
                            {
                                "label_regex": "b",
                                "content_regex": "(\\d+)",
                            },
                        ],
                        "fields": {
                            "name": {"parts": [{"row": 0, "group": 0}]},
                            "quantity": {"parts": [{"row": 1, "group": 1}]},
                        },
                    }
                ]
            }),
            encoding="utf-8",
        )
        cfg = load_config(cfg_path)
        assert cfg.blocks[0].category == "labor"
        # 默认缓存未被覆盖
        default = load_config()
        assert default.blocks[1].category == "machinery"


class TestModelsDirectly:
    """绕过 JSON，直接构造模型对象"""

    def test_part_spec(self):
        p = PartSpec(row=1, group=2)
        assert p.row == 1
        assert p.group == 2

    def test_field_spec_defaults(self):
        f = FieldSpec(parts=[PartSpec(row=0, group=0)])
        assert f.sep == ""
        assert f.filter_empty is False

    def test_cleaning_spec_defaults(self):
        c = CleaningSpec()
        assert c.break_on_empty is True
        assert c.ignore_values == []
        assert c.ignore_case is True

    def test_row_spec_compiles_in_post_init(self):
        r = RowSpec(label_regex="x", content_regex="(.+)")
        assert r._compiled_label.pattern == "x"
        assert r._compiled_content.pattern == "(.+)"
