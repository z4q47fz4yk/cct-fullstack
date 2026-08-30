"""施工日报解析功能单元测试"""
# pyright: reportCallIssue=false

from pathlib import Path

import polars as pl

from src.utils.daily_report_parser import (
    ParsedItem,
    ParsedResult,
    get_polars_df,
    parse_daily_report,
)


def get_csv_content(filename: str = "20251214.csv") -> bytes:
    """读取测试用 CSV 文件"""
    test_file = Path(__file__).parent.parent / "docs" / filename
    return test_file.read_bytes()


class TestDailyReportParser:
    """施工日报解析测试"""

    def test_get_polars_df_csv(self):
        """测试 CSV 文件读取"""
        content = get_csv_content()
        df = get_polars_df("test.csv", content)
        assert isinstance(df, pl.DataFrame)
        assert len(df) > 0

    def test_parse_daily_report_returns_typed_result(self):
        """测试解析返回类型"""
        content = get_csv_content()
        result = parse_daily_report("test.csv", content)

        assert isinstance(result, ParsedResult)
        assert isinstance(result.items, list)
        assert isinstance(result.warnings, list)

    def test_parse_personnel_items(self):
        """测试人员数据解析"""
        content = get_csv_content()
        result = parse_daily_report("test.csv", content)

        labor_items = [item for item in result.items if item.category == "labor"]

        assert len(labor_items) > 0

        labor_names = {item.name: item.count for item in labor_items}

        assert "管理人员" in labor_names
        assert labor_names["管理人员"] == 68

        assert "泥工" in labor_names
        assert labor_names["泥工"] == 96

        assert "木工" in labor_names
        assert labor_names["木工"] == 181

        assert "钢筋工" in labor_names
        assert labor_names["钢筋工"] == 83

    def test_parse_machinery_items(self):
        """测试机械数据解析"""
        content = get_csv_content()
        result = parse_daily_report("test.csv", content)

        machinery_items = [
            item for item in result.items if item.category == "machinery"
        ]

        assert len(machinery_items) > 0

        machinery_data = {item.name: item.count for item in machinery_items}

        assert "挖机-SE135-9W" in machinery_data
        assert machinery_data["挖机-SE135-9W"] == 4

        assert "挖机-SY135C" in machinery_data
        assert machinery_data["挖机-SY135C"] == 2

    def test_total_parsed_items(self):
        """测试解析出的总条目数"""
        content = get_csv_content()
        result = parse_daily_report("test.csv", content)

        assert len(result.items) > 0

    def test_category_classification(self):
        """测试资源分类正确性"""
        content = get_csv_content()
        result = parse_daily_report("test.csv", content)

        labor_count = sum(1 for item in result.items if item.category == "labor")
        machinery_count = sum(
            1 for item in result.items if item.category == "machinery"
        )

        assert labor_count > 0
        assert machinery_count > 0
        assert labor_count + machinery_count == len(result.items)

    def test_invalid_data_filtering(self):
        """测试无效数据被正确过滤"""
        content = get_csv_content()
        result = parse_daily_report("test.csv", content)

        resource_names = [item.name for item in result.items]

        assert not any("每台型号" in name for name in resource_names)
        assert "总计" not in resource_names

    def test_item_structure(self):
        """测试条目结构"""
        content = get_csv_content()
        result = parse_daily_report("test.csv", content)

        for item in result.items:
            assert isinstance(item, ParsedItem)
            assert isinstance(item.name, str)
            assert isinstance(item.count, int)
            assert isinstance(item.category, str)
            assert item.category in ("labor", "machinery")
            assert item.count >= 0
