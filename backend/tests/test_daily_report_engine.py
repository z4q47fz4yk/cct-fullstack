"""施工日报解析引擎单元测试

使用合成 polars DataFrame 覆盖解析引擎分支，不依赖外部样本文件。
"""
# pyright: reportCallIssue=false

from pathlib import Path

import polars as pl
import pytest

from src.schemas.daily_report import FileParseError, ParsedItem
from src.utils.daily_report_config import (
    ParseEngineConfig,
    load_config,
    reset_cache,
)
from src.utils.daily_report_parser import parse_daily_report, parse_report


@pytest.fixture(autouse=True)
def _clear_config_cache():
    """每个测试前后清空默认配置缓存，避免互相污染"""
    reset_cache()
    yield
    reset_cache()


def _labor_cfg() -> ParseEngineConfig:
    """最小 labor block 配置（覆盖 ignore_values 默认集）"""
    return ParseEngineConfig.model_validate({
        "blocks": [
            {
                "category": "labor",
                "label_at_column": 0,
                "rows": [
                    {"label_regex": "^(?:现场人员)$", "content_regex": "(.*)"},
                    {
                        "label_regex": "^(?:人员数量)$",
                        "content_regex": "(\\d+)\\s*人?",
                    },
                ],
                "cleaning": {
                    "break_on_empty": True,
                    "ignore_values": [
                        "总计",
                        "总量",
                        "总人数",
                        "total",
                        "0",
                        "/",
                    ],
                },
                "fields": {
                    "name": {"parts": [{"row": 0, "group": 0}], "sep": ""},
                    "quantity": {"parts": [{"row": 1, "group": 1}], "sep": ""},
                },
            }
        ]
    })


def _machinery_cfg() -> ParseEngineConfig:
    """最小 machinery block 配置"""
    return ParseEngineConfig.model_validate({
        "blocks": [
            {
                "category": "machinery",
                "label_at_column": 0,
                "rows": [
                    {"label_regex": "^(?:施工机械)$", "content_regex": "(.*)"},
                    {
                        "label_regex": "^(?:数量)$",
                        "content_regex": "(\\d+)\\s*(?:台|台班)?",
                    },
                    {"label_regex": "^(?:机械型号)$", "content_regex": "(.*)"},
                ],
                "cleaning": {
                    "break_on_empty": True,
                    "ignore_values": ["0", "/"],
                },
                "fields": {
                    "name": {
                        "parts": [
                            {"row": 0, "group": 0},
                            {"row": 2, "group": 0},
                        ],
                        "sep": "-",
                        "filter_empty": True,
                    },
                    "quantity": {"parts": [{"row": 1, "group": 1}], "sep": ""},
                },
            }
        ]
    })


class TestLaborBlock:
    """人员块解析"""

    def test_single_group(self):
        df = pl.DataFrame({"a": ["现场人员", "人员数量"], "b": ["木工", "181"]})
        result = parse_report(df, config=_labor_cfg())
        assert result.items == [ParsedItem(name="木工", count=181, category="labor")]
        assert result.warnings == []

    def test_multi_consecutive_groups(self):
        """两个 labor block 拼起来"""
        df = pl.DataFrame({
            "a": [
                "现场人员",
                "人员数量",
                "现场人员",
                "人员数量",
            ],
            "b": ["木工", "181", "钢筋工", "83"],
            "c": ["泥工", "360", "小工", "160"],
        })
        result = parse_report(df, config=_labor_cfg())
        assert {i.name: i.count for i in result.items} == {
            "木工": 181,
            "钢筋工": 83,
            "泥工": 360,
            "小工": 160,
        }
        assert result.warnings == []

    def test_break_on_empty_skips_blank_column(self):
        """c 列为空 → 该列被跳过，b 列正常解析"""
        df = pl.DataFrame(
            {
                "a": ["现场人员", "人员数量"],
                "b": ["木工", "181"],
                "c": [None, None],
            },
            schema={"a": pl.Utf8, "b": pl.Utf8, "c": pl.Utf8},
        )
        result = parse_report(df, config=_labor_cfg())
        assert result.items == [ParsedItem(name="木工", count=181, category="labor")]
        assert result.warnings == []

    def test_total_name_filtered(self):
        """名称 '总计' 应被 ignore_values 过滤"""
        df = pl.DataFrame({
            "a": ["现场人员", "人员数量", "现场人员", "人员数量"],
            "b": ["木工", "181", "总计", "658"],
        })
        result = parse_report(df, config=_labor_cfg())
        assert {i.name: i.count for i in result.items} == {"木工": 181}

    def test_count_zero_filtered(self):
        """数量 '0' 应被 ignore_values 过滤"""
        df = pl.DataFrame({
            "a": ["现场人员", "人员数量"],
            "b": ["木工", "0"],
        })
        result = parse_report(df, config=_labor_cfg())
        assert result.items == []


class TestMachineryBlock:
    """机械块解析"""

    def test_with_code(self):
        df = pl.DataFrame({
            "a": ["施工机械", "数量", "机械型号"],
            "b": ["挖机", "4台", "SE135-9W"],
        })
        result = parse_report(df, config=_machinery_cfg())
        assert result.items == [
            ParsedItem(name="挖机-SE135-9W", count=4, category="machinery")
        ]

    def test_without_code_filter_empty(self):
        """机械型号为空 → filter_empty 跳过该 part，name 不带尾部 '-'"""
        df = pl.DataFrame({
            "a": ["施工机械", "数量", "机械型号"],
            "b": ["挖机", "2台", ""],
        })
        result = parse_report(df, config=_machinery_cfg())
        assert result.items == [ParsedItem(name="挖机", count=2, category="machinery")]

    def test_count_zero_filtered(self):
        df = pl.DataFrame({
            "a": ["施工机械", "数量", "机械型号"],
            "b": ["挖机", "0台", "SE"],
        })
        result = parse_report(df, config=_machinery_cfg())
        assert result.items == []

    def test_slash_filtered(self):
        df = pl.DataFrame({
            "a": ["施工机械", "数量", "机械型号"],
            "b": ["挖机", "/", "/"],
        })
        result = parse_report(df, config=_machinery_cfg())
        assert result.items == []

    def test_count_with_suffix_parsed(self):
        """'台班' 后缀应被 \\s*(?:台|台班)? 吞掉，group 1 仍是数字"""
        df = pl.DataFrame({
            "a": ["施工机械", "数量", "机械型号"],
            "b": ["塔吊", "2台班", "QTZ250"],
        })
        result = parse_report(df, config=_machinery_cfg())
        assert result.items == [
            ParsedItem(name="塔吊-QTZ250", count=2, category="machinery")
        ]


class TestErrorHandling:
    """异常 / 边界"""

    def test_row_count_not_multiple_raises(self):
        """3 行匹配 2-row block → FileParseError"""
        df = pl.DataFrame({
            "a": ["现场人员", "人员数量", "现场人员"],
            "b": ["木工", "181", "钢筋工"],
        })
        with pytest.raises(FileParseError):
            parse_report(df, config=_labor_cfg())

    def test_quantity_group_not_int_warning(self):
        """content_regex 命中但 group 1 不是数字 → ParseWarning 追加"""
        cfg = ParseEngineConfig.model_validate({
            "blocks": [
                {
                    "category": "labor",
                    "label_at_column": 0,
                    "rows": [
                        {
                            "label_regex": "^(?:现场人员)$",
                            "content_regex": "(.*)",
                        },
                        {
                            "label_regex": "^(?:人员数量)$",
                            "content_regex": "(\\D+)",  # 故意只匹配非数字
                        },
                    ],
                    "cleaning": {
                        "break_on_empty": True,
                        "ignore_values": [],
                    },
                    "fields": {
                        "name": {
                            "parts": [{"row": 0, "group": 0}],
                            "sep": "",
                        },
                        "quantity": {
                            "parts": [{"row": 1, "group": 1}],
                            "sep": "",
                        },
                    },
                }
            ]
        })
        df = pl.DataFrame({"a": ["现场人员", "人员数量"], "b": ["木工", "abc"]})
        result = parse_report(df, config=cfg)
        assert result.items == []
        assert len(result.warnings) == 1
        assert "木工" in result.warnings[0].detail
        assert "abc" in result.warnings[0].detail


class TestDedup:
    """同名资源处理 —— 任一 name 重复出现则整组丢弃 + warning

    由于 ``resource`` 表受 ``UNIQUE(project_id, name)`` 约束,
    解析器遇到同名条目时无法决定保留哪一个,故全部丢弃并告警。
    """

    def test_within_category_duplicate_excluded_with_warning(self):
        """同 block 内同 name 出现 2 次 → 全部排除 + 1 条 warning"""
        df = pl.DataFrame({
            "a": ["现场人员", "人员数量", "现场人员", "人员数量"],
            "b": ["木工", "5", "木工", "3"],
        })
        result = parse_report(df, config=_labor_cfg())
        assert result.items == []
        assert len(result.warnings) == 1
        assert "木工" in result.warnings[0].detail
        assert "2" in result.warnings[0].detail

    def test_cross_category_collision_excluded_with_warning(self):
        """labor "木工"(5) + machinery "木工"(3) → 全部排除 + warning"""
        cfg = ParseEngineConfig.model_validate({
            "blocks": [
                {
                    "category": "labor",
                    "label_at_column": 0,
                    "rows": [
                        {
                            "label_regex": "^(?:现场人员)$",
                            "content_regex": "(.*)",
                        },
                        {
                            "label_regex": "^(?:人员数量)$",
                            "content_regex": "(\\d+)\\s*人?",
                        },
                    ],
                    "cleaning": {
                        "break_on_empty": True,
                        "ignore_values": [],
                    },
                    "fields": {
                        "name": {
                            "parts": [{"row": 0, "group": 0}],
                            "sep": "",
                        },
                        "quantity": {
                            "parts": [{"row": 1, "group": 1}],
                            "sep": "",
                        },
                    },
                },
                {
                    "category": "machinery",
                    "label_at_column": 0,
                    "rows": [
                        {
                            "label_regex": "^(?:施工机械)$",
                            "content_regex": "(.*)",
                        },
                        {
                            "label_regex": "^(?:数量)$",
                            "content_regex": "(\\d+)\\s*(?:台|台班)?",
                        },
                        {
                            "label_regex": "^(?:机械型号)$",
                            "content_regex": "(.*)",
                        },
                    ],
                    "cleaning": {
                        "break_on_empty": True,
                        "ignore_values": [],
                    },
                    "fields": {
                        "name": {
                            "parts": [
                                {"row": 0, "group": 0},
                                {"row": 2, "group": 0},
                            ],
                            "sep": "-",
                            "filter_empty": True,
                        },
                        "quantity": {
                            "parts": [{"row": 1, "group": 1}],
                            "sep": "",
                        },
                    },
                },
            ]
        })
        df = pl.DataFrame({
            "a": [
                "现场人员",
                "人员数量",
                "施工机械",
                "数量",
                "机械型号",
            ],
            "b": ["木工", "5", "木工", "3台", ""],
        })
        result = parse_report(df, config=cfg)
        assert result.items == []
        assert len(result.warnings) == 1
        assert "木工" in result.warnings[0].detail
        assert "2" in result.warnings[0].detail

    def test_three_way_collision_single_warning(self):
        """同 name 出现 3 次 → 仅 1 条 warning,3 条全丢

        三列机械型号列均填空,``filter_empty`` 让三列均解析为 name="木工"。
        """
        df = pl.DataFrame({
            "a": ["施工机械", "数量", "机械型号"],
            "b": ["木工", "3台", ""],
            "c": ["木工", "5台", ""],
            "d": ["木工", "2台", ""],
        })
        result = parse_report(df, config=_machinery_cfg())
        assert result.items == []
        assert len(result.warnings) == 1
        assert "木工" in result.warnings[0].detail
        assert "3" in result.warnings[0].detail

    def test_unique_names_pass_through(self):
        """每个 name 仅出现 1 次 → 全部进入结果,无 warning"""
        df = pl.DataFrame({
            "a": ["现场人员", "人员数量", "现场人员", "人员数量"],
            "b": ["木工", "5", "钢筋工", "3"],
        })
        result = parse_report(df, config=_labor_cfg())
        assert {i.name for i in result.items} == {"木工", "钢筋工"}
        assert result.warnings == []

    def test_mixed_unique_and_colliding(self):
        """部分 name 重复、部分唯一 → 仅重复项被丢弃 + 1 条 warning"""
        df = pl.DataFrame({
            "a": [
                "现场人员",
                "人员数量",
                "现场人员",
                "人员数量",
                "现场人员",
                "人员数量",
            ],
            "b": ["木工", "5", "木工", "3", "钢筋工", "10"],
        })
        result = parse_report(df, config=_labor_cfg())
        assert [i.name for i in result.items] == ["钢筋工"]
        assert len(result.warnings) == 1
        assert "木工" in result.warnings[0].detail


class TestEdgeCases:
    """边界场景"""

    def test_empty_dataframe(self):
        df = pl.DataFrame(
            {"a": [], "b": []},
            schema={"a": pl.Utf8, "b": pl.Utf8},
        )
        result = parse_report(df, config=_labor_cfg())
        assert result.items == []
        assert result.warnings == []

    def test_no_matching_rows(self):
        """locator 正则不命中任何行"""
        df = pl.DataFrame(
            {"a": ["无关", "数据"], "b": ["x", "y"]},
            schema={"a": pl.Utf8, "b": pl.Utf8},
        )
        result = parse_report(df, config=_labor_cfg())
        assert result.items == []
        assert result.warnings == []

    def test_input_dataframe_not_mutated(self):
        """parse_report 不应修改调用方 df"""
        df = pl.DataFrame({"a": ["现场人员", "人员数量"], "b": ["木工", "181"]})
        df_before = df.clone()
        parse_report(df, config=_labor_cfg())
        assert df.equals(df_before)


class TestDefaultConfig:
    """默认 bundled 配置"""

    def test_load_default_caches(self):
        cfg1 = load_config()
        cfg2 = load_config()
        assert cfg1 is cfg2  # 命中缓存

    def test_force_reload_re_reads(self):
        cfg1 = load_config()
        cfg2 = load_config(force_reload=True)
        # 不同实例但等价
        assert cfg1 is not cfg2
        assert len(cfg1.blocks) == len(cfg2.blocks) == 3

    def test_default_parses_sample(self):
        """默认配置对示例样本的解析结果与历史一致"""
        csv = (Path(__file__).parent.parent / "docs" / "20251214.csv").read_bytes()
        result = parse_daily_report("test.csv", csv)
        labor = {i.name: i.count for i in result.items if i.category == "labor"}
        mach = {i.name: i.count for i in result.items if i.category == "machinery"}
        assert labor["管理人员"] == 68
        assert labor["泥工"] == 96
        assert labor["木工"] == 181
        assert labor["钢筋工"] == 83
        assert mach["挖机-SE135-9W"] == 4
        assert mach["挖机-SY135C"] == 2
        assert "总计" not in {i.name for i in result.items}
        assert not any("每台型号" in n for n in {i.name for i in result.items})


class TestLabelAtColumn:
    """label_at_column 任意列定位：标签不在第 0 列时也能正确定位与解析"""

    def _cfg(self, label_at_column: int) -> ParseEngineConfig:
        return ParseEngineConfig.model_validate({
            "blocks": [
                {
                    "category": "labor",
                    "label_at_column": label_at_column,
                    "rows": [
                        {"label_regex": "^现场人员$", "content_regex": "(.*)"},
                        {
                            "label_regex": "^人员数量$",
                            "content_regex": r"(\d+)\s*人?",
                        },
                    ],
                    "cleaning": {
                        "break_on_empty": True,
                        "ignore_values": ["总计", "0", "/"],
                    },
                    "fields": {
                        "name": {"parts": [{"row": 0, "group": 0}], "sep": ""},
                        "quantity": {"parts": [{"row": 1, "group": 1}], "sep": ""},
                    },
                }
            ]
        })

    def test_label_in_second_column(self):
        """标签在第 1 列（列0 是无关前缀文本），数据从第 2 列开始"""
        df = pl.DataFrame({
            "prefix": ["xxx", "yyy", "xxx", "yyy"],
            "label": ["现场人员", "人员数量", "现场人员", "人员数量"],
            "data1": ["木工", "181", "钢筋工", "83"],
            "data2": ["泥工", "96", "小工", "12"],
        })
        result = parse_report(df, config=self._cfg(label_at_column=1))
        assert {i.name: i.count for i in result.items} == {
            "木工": 181,
            "钢筋工": 83,
            "泥工": 96,
            "小工": 12,
        }
        assert result.warnings == []

    def test_label_in_first_column_still_works(self):
        """label_at_column=0 与旧行为一致（回归）"""
        df = pl.DataFrame({
            "label": ["现场人员", "人员数量"],
            "data1": ["木工", "181"],
        })
        result = parse_report(df, config=self._cfg(label_at_column=0))
        assert result.items == [ParsedItem(name="木工", count=181, category="labor")]

    def test_prefix_column_ignored_when_label_later(self):
        """label_at_column=1 时，第 0 列即使也含同名文本也不参与匹配/数据"""
        df = pl.DataFrame({
            "prefix": ["现场人员", "人员数量"],  # 干扰：与标签同文本但列不对
            "label": ["现场人员", "人员数量"],
            "data1": ["木工", "181"],
        })
        result = parse_report(df, config=self._cfg(label_at_column=1))
        assert result.items == [ParsedItem(name="木工", count=181, category="labor")]

    def test_label_in_third_column(self):
        """标签在第 2 列、前两列是装饰列，验证一般化 k"""
        df = pl.DataFrame({
            "c0": ["a", "b"],
            "c1": ["a", "b"],
            "label": ["现场人员", "人员数量"],
            "data": ["木工", "181"],
        })
        result = parse_report(df, config=self._cfg(label_at_column=2))
        assert result.items == [ParsedItem(name="木工", count=181, category="labor")]
