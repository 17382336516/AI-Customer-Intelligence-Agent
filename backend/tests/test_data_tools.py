from __future__ import annotations

import pandas as pd
import pytest

from app.services.data_tools import (
    build_quality_report,
    clean_dataset,
    detect_mapping,
)


def test_detects_chinese_and_english_field_aliases():
    mapping = detect_mapping(["用户ID", "订单金额", "商品名称", "下单时间"])
    assert mapping == {
        "user_id": "用户ID",
        "amount": "订单金额",
        "product": "商品名称",
        "event_time": "下单时间",
    }


def test_quality_report_blocks_missing_required_fields():
    raw = pd.DataFrame({"user_id": ["U1"], "product": ["拿铁"]})
    report = build_quality_report(raw)
    assert report["can_analyze"] is False
    assert {item["field"] for item in report["issues"] if item["severity"] == "error"} == {
        "amount",
        "event_time",
    }


def test_online_retail_schema_uses_derived_amount():
    raw = pd.DataFrame(
        {
            "InvoiceNo": ["536365", "536365", "536366"],
            "StockCode": ["85123A", "71053", "84406B"],
            "Description": ["WHITE HEART", "METAL LANTERN", "COFFEE MUG"],
            "Quantity": [6, 6, 2],
            "InvoiceDate": ["2010-12-01 08:26:00", "2010-12-01 08:26:00", "2010-12-01 08:28:00"],
            "UnitPrice": [2.55, 3.39, 4.25],
            "CustomerID": [17850, 17850, 13047],
            "Country": ["United Kingdom", "United Kingdom", "United Kingdom"],
        }
    )

    report = build_quality_report(raw)
    assert report["can_analyze"] is True
    assert report["field_mapping"]["user_id"] == "CustomerID"
    assert report["field_mapping"]["event_time"] == "InvoiceDate"
    assert report["field_mapping"]["amount"] == "__derived_amount__"

    cleaned, stats = clean_dataset(raw, report["field_mapping"])
    assert stats["duplicates_removed"] == 0
    assert cleaned["amount"].tolist() == pytest.approx([15.3, 20.34, 8.5])


def test_cleaning_removes_refunds_duplicates_and_invalid_amounts():
    raw = pd.DataFrame(
        [
            {
                "order_id": "A1",
                "user_id": "U1",
                "amount": 30,
                "product": "拿铁",
                "event_time": "2026-07-01 08:00:00",
                "status": "paid",
            },
            {
                "order_id": "A1",
                "user_id": "U1",
                "amount": 30,
                "product": "拿铁",
                "event_time": "2026-07-01 08:00:00",
                "status": "paid",
            },
            {
                "order_id": "A2",
                "user_id": "U1",
                "amount": -30,
                "product": "拿铁",
                "event_time": "2026-07-02 08:00:00",
                "status": "refund",
            },
        ]
    )
    mapping = detect_mapping(list(raw.columns))
    cleaned, stats = clean_dataset(raw, mapping)
    assert len(cleaned) == 1
    assert stats["duplicates_removed"] == 1
    assert stats["invalid_removed"] == 1
    assert cleaned.iloc[0]["persona_category"] == "coffee"
