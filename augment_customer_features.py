"""Create reproducible business features and separate benchmark labels."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

LIFECYCLE_NAMES = {
    "high_value": "高价值用户",
    "young_growth": "年轻成长用户",
    "price_sensitive": "价格敏感用户",
    "category_interest": "品类兴趣用户",
    "scenario_churn": "scenario_enhanced_churn_user",
}

CATEGORY_CATALOG: dict[str, list[tuple[str, str, float]]] = {
    "电子产品": [
        ("华为", "智能手机", 3999),
        ("小米", "无线耳机", 399),
        ("联想", "轻薄笔记本", 5699),
        ("索尼", "降噪耳机", 1899),
    ],
    "服饰": [
        ("优衣库", "基础款外套", 399),
        ("李宁", "运动休闲鞋", 699),
        ("太平鸟", "潮流卫衣", 329),
        ("蕉内", "舒适家居服", 259),
    ],
    "食品": [
        ("三只松鼠", "坚果礼盒", 129),
        ("伊利", "常温牛奶组合", 89),
        ("良品铺子", "休闲零食组合", 99),
        ("农夫山泉", "饮用水组合", 48),
    ],
    "美妆": [
        ("珀莱雅", "精华液", 329),
        ("花西子", "彩妆礼盒", 259),
        ("薇诺娜", "舒敏面霜", 288),
        ("欧莱雅", "护肤套装", 499),
    ],
    "家居": [
        ("小熊", "多功能料理机", 299),
        ("九阳", "智能电饭煲", 499),
        ("水星家纺", "纯棉床品套装", 599),
        ("宜家", "家居收纳组合", 199),
    ],
    "旅游": [
        ("飞猪", "周末酒店套餐", 899),
        ("携程", "城市短途套餐", 1299),
        ("途家", "民宿体验套餐", 699),
        ("春秋旅游", "国内跟团套餐", 2399),
    ],
    "运动": [
        ("安踏", "跑步鞋", 499),
        ("Keep", "家庭健身套装", 299),
        ("迪卡侬", "户外运动装备", 399),
        ("特步", "运动服套装", 359),
    ],
    "母婴": [
        ("Babycare", "婴童用品组合", 299),
        ("巴拉巴拉", "儿童服饰套装", 399),
        ("乐高", "益智积木", 599),
        ("帮宝适", "婴儿护理组合", 239),
    ],
}

INPUT_COLUMNS = [
    "customer_id",
    "age",
    "gender",
    "city",
    "income_level",
    "membership_level",
    "order_id",
    "purchase_date",
    "product_category",
    "product_brand",
    "product_name",
    "purchase_amount",
    "quantity",
    "purchase_frequency",
    "total_consumption",
    "average_order_value",
    "last_purchase_days",
    "category_diversity",
    "coupon_usage",
    "activity_frequency",
    "preferred_channel",
    "amount",
    "event_time",
    "category",
]
LABEL_COLUMNS = [
    "dataset_id",
    "customer_id",
    "category_ground_truth",
    "lifecycle_ground_truth",
    "label_source",
]


@dataclass
class BehaviorSummary:
    purchases: pd.DataFrame
    users: pd.DataFrame


def stable_int(*values: object) -> int:
    payload = "|".join(str(value) for value in values).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def stable_choice(values: list[str], *keys: object) -> str:
    return values[stable_int(*keys) % len(values)]


def load_behavior_summary(path: Path, chunksize: int = 500_000) -> BehaviorSummary:
    count_parts: list[pd.DataFrame] = []
    range_parts: list[pd.DataFrame] = []
    active_day_parts: list[pd.DataFrame] = []
    purchase_parts: list[pd.DataFrame] = []

    for chunk in pd.read_csv(path, chunksize=chunksize, parse_dates=["event_time"]):
        chunk = chunk.dropna(subset=["user_id", "item_id", "behavior_type", "event_time"])
        counts = pd.crosstab(chunk["user_id"].astype(str), chunk["behavior_type"])
        count_parts.append(counts)
        ranges = chunk.groupby("user_id")["event_time"].agg(first_event="min", last_event="max")
        range_parts.append(ranges)
        active_day_parts.append(
            chunk.assign(active_date=chunk["event_time"].dt.date)[["user_id", "active_date"]]
            .drop_duplicates()
        )
        purchase_parts.append(chunk[chunk["behavior_type"] == "purchase"].copy())

    if not purchase_parts:
        raise ValueError("No purchase behavior was found in the cleaned source.")

    counts = pd.concat(count_parts).groupby(level=0).sum()
    for column in ("view", "favorite", "cart", "purchase"):
        if column not in counts:
            counts[column] = 0
    counts = counts[["view", "favorite", "cart", "purchase"]].astype(int)

    ranges_all = pd.concat(range_parts).reset_index()
    ranges = ranges_all.groupby("user_id").agg(
        first_event=("first_event", "min"), last_event=("last_event", "max")
    )
    active_days = (
        pd.concat(active_day_parts)
        .drop_duplicates()
        .groupby("user_id")
        .size()
        .rename("active_days")
    )
    users = counts.join(ranges, how="left").join(active_days, how="left").fillna({"active_days": 1})
    users["event_count"] = users[["view", "favorite", "cart", "purchase"]].sum(axis=1)
    users["activity_frequency"] = (users["event_count"] / users["active_days"]).round(2)

    purchases = pd.concat(purchase_parts, ignore_index=True).drop_duplicates(
        subset=["user_id", "item_id", "event_time"], keep="first"
    )
    purchases["user_id"] = purchases["user_id"].astype(str)
    purchases["item_id"] = purchases["item_id"].astype(str)
    purchases["item_category"] = purchases["item_category"].astype(str)
    users.index = users.index.astype(str)
    return BehaviorSummary(purchases=purchases, users=users)


def _catalog_fields(row: pd.Series) -> pd.Series:
    source_category = row["item_category"]
    if not source_category or source_category.lower() in {"nan", "none", "unknown"}:
        source_category = row["item_id"]
    categories = list(CATEGORY_CATALOG)
    category = categories[stable_int("category", source_category) % len(categories)]
    products = CATEGORY_CATALOG[category]
    brand, product, base_price = products[stable_int("product", row["item_id"]) % len(products)]
    return pd.Series(
        {
            "product_category": category,
            "product_brand": brand,
            "product_name": product,
            "base_price": float(base_price),
        }
    )


def _rank(series: pd.Series, ascending: bool = True) -> pd.Series:
    return series.rank(method="average", pct=True, ascending=ascending).fillna(0.5)


def _quota_counts(total: int, ratios: dict[str, float]) -> dict[str, int]:
    raw = {key: total * value for key, value in ratios.items()}
    counts = {key: int(value) for key, value in raw.items()}
    for key, _ in sorted(raw.items(), key=lambda item: item[1] - int(item[1]), reverse=True):
        if sum(counts.values()) >= total:
            break
        counts[key] += 1
    return counts


def assign_lifecycle(
    features: pd.DataFrame,
    total_users: int,
    ratios: dict[str, float],
    seed: int,
) -> pd.Series:
    if len(features) < total_users:
        raise ValueError(f"Need {total_users} purchasing users, found {len(features)}.")

    scores = pd.DataFrame(index=features.index)
    scores["scenario_churn"] = (
        _rank(features["source_recency_days"]) * 0.65
        + _rank(features["event_count"], ascending=False) * 0.35
    )
    scores["high_value"] = (
        _rank(features["purchase_count"]) * 0.3
        + _rank(features["preliminary_total"]) * 0.3
        + _rank(features["preliminary_aov"]) * 0.2
        + _rank(features["category_diversity"]) * 0.2
    )
    scores["category_interest"] = (
        _rank(features["category_concentration"]) * 0.8
        + _rank(features["category_diversity"], ascending=False) * 0.2
    )
    scores["price_sensitive"] = (
        _rank(features["preliminary_aov"], ascending=False) * 0.55
        + _rank(features["cart_favorite_ratio"]) * 0.45
    )
    scores["young_growth"] = (
        _rank(features["activity_frequency"]) * 0.45
        + _rank(features["purchase_count"]) * 0.35
        + _rank(features["trend_category_share"]) * 0.2
    )
    tie = pd.Series({user: stable_int(seed, user) for user in features.index})
    quotas = _quota_counts(total_users, ratios)
    selected: set[str] = set()
    labels: dict[str, str] = {}

    for segment in (
        "scenario_churn",
        "high_value",
        "category_interest",
        "price_sensitive",
        "young_growth",
    ):
        candidates = scores.index[~scores.index.isin(selected)]
        ordered = pd.DataFrame(
            {"score": scores.loc[candidates, segment], "tie": tie.loc[candidates]}
        ).sort_values(["score", "tie"], ascending=[False, True])
        chosen = ordered.head(quotas[segment]).index
        selected.update(chosen)
        labels.update({user: segment for user in chosen})

    return pd.Series(labels, name="lifecycle_code")


def _limit_orders(frame: pd.DataFrame, maximum: int, seed: int) -> pd.DataFrame:
    if len(frame) <= maximum:
        return frame
    ordered = frame.sort_values(["user_id", "event_time", "item_id"])
    required = ordered.groupby("user_id", as_index=False).head(1)
    remaining = ordered.drop(required.index).copy()
    remaining["_pick"] = [
        stable_int(seed, user, item, timestamp)
        for user, item, timestamp in zip(
            remaining["user_id"], remaining["item_id"], remaining["event_time"], strict=True
        )
    ]
    return pd.concat(
        [required, remaining.nsmallest(maximum - len(required), "_pick").drop(columns="_pick")]
    ).sort_values(["user_id", "event_time"])


def _profile_for_user(user: str, lifecycle: str, seed: int) -> dict[str, object]:
    age_ranges = {
        "high_value": (29, 55),
        "young_growth": (18, 30),
        "price_sensitive": (23, 60),
        "category_interest": (21, 55),
        "scenario_churn": (31, 60),
    }
    low, high = age_ranges[lifecycle]
    age = low + stable_int(seed, user, "age") % (high - low + 1)
    gender = stable_choice(["女", "男", "女", "男", "未知"], seed, user, "gender")
    city = stable_choice(
        ["上海", "北京", "深圳", "广州", "杭州", "成都", "武汉", "南京", "西安", "长沙"],
        seed,
        user,
        "city",
    )
    income_choices = {
        "high_value": ["high", "high", "middle"],
        "young_growth": ["middle", "middle", "low"],
        "price_sensitive": ["low", "low", "middle"],
        "category_interest": ["middle", "middle", "high"],
        "scenario_churn": ["middle", "low", "high"],
    }
    membership_choices = {
        "high_value": ["VIP", "VIP", "金卡"],
        "young_growth": ["银卡", "普通用户", "金卡"],
        "price_sensitive": ["普通用户", "普通用户", "银卡"],
        "category_interest": ["金卡", "银卡", "普通用户"],
        "scenario_churn": ["普通用户", "银卡", "金卡"],
    }
    channel_choices = {
        "high_value": ["App", "App", "官网"],
        "young_growth": ["App", "小程序", "App"],
        "price_sensitive": ["小程序", "App", "官网"],
        "category_interest": ["App", "官网", "App"],
        "scenario_churn": ["官网", "App", "线下门店"],
    }
    return {
        "age": age,
        "gender": gender,
        "city": city,
        "income_level": stable_choice(income_choices[lifecycle], seed, user, "income"),
        "membership_level": stable_choice(
            membership_choices[lifecycle], seed, user, "membership"
        ),
        "preferred_channel": stable_choice(channel_choices[lifecycle], seed, user, "channel"),
    }


def build_augmented_dataset(
    summary: BehaviorSummary,
    dataset_id: str,
    ratios: dict[str, float],
    total_users: int = 4_000,
    seed: int = 20260810,
    as_of_date: str = "2026-06-30",
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    if "base_price" not in summary.purchases.columns:
        catalog = summary.purchases.apply(_catalog_fields, axis=1)
        summary.purchases = pd.concat(
            [summary.purchases.reset_index(drop=True), catalog.reset_index(drop=True)], axis=1
        )
    purchases = summary.purchases.copy()
    purchases["preliminary_amount"] = purchases["base_price"]

    preliminary = purchases.groupby("user_id").agg(
        purchase_count=("item_id", "size"),
        preliminary_total=("preliminary_amount", "sum"),
        preliminary_aov=("preliminary_amount", "mean"),
        category_diversity=("product_category", "nunique"),
        last_purchase=("event_time", "max"),
    )
    category_spend = purchases.pivot_table(
        index="user_id", columns="product_category", values="preliminary_amount", aggfunc="sum", fill_value=0
    )
    preliminary["category_concentration"] = (
        category_spend.max(axis=1) / category_spend.sum(axis=1).replace(0, np.nan)
    ).fillna(0)
    trend_columns = [column for column in ("电子产品", "服饰") if column in category_spend]
    preliminary["trend_category_share"] = (
        category_spend[trend_columns].sum(axis=1)
        / category_spend.sum(axis=1).replace(0, np.nan)
        if trend_columns
        else 0.0
    )

    features = preliminary.join(summary.users, how="left", rsuffix="_source")
    source_reference = features["last_purchase"].max().normalize() + pd.Timedelta(days=1)
    features["source_recency_days"] = (source_reference - features["last_purchase"]).dt.days
    features["cart_favorite_ratio"] = (
        (features["cart"] + features["favorite"]) / features["purchase_count"].clip(lower=1)
    )
    lifecycle_codes = assign_lifecycle(features, total_users, ratios, seed)
    selected_users = lifecycle_codes.index
    purchases = purchases[purchases["user_id"].isin(selected_users)].copy()
    purchases = _limit_orders(purchases, maximum=28_000, seed=seed)
    if len(purchases) < 10_000:
        raise ValueError(
            f"{dataset_id} has only {len(purchases)} purchase rows; choose more eligible users/source data."
        )

    lifecycle_codes = lifecycle_codes.loc[purchases["user_id"].unique()]
    purchases["lifecycle_code"] = purchases["user_id"].map(lifecycle_codes)
    purchases["quantity"] = [
        1 + stable_int(seed, user, item, timestamp, "quantity") % (
            4 if category == "食品" else 2
        )
        for user, item, timestamp, category in zip(
            purchases["user_id"],
            purchases["item_id"],
            purchases["event_time"],
            purchases["product_category"],
            strict=True,
        )
    ]
    discount_ranges = {
        "high_value": (0.00, 0.08, 1.60),
        "young_growth": (0.04, 0.15, 1.00),
        "price_sensitive": (0.15, 0.35, 0.72),
        "category_interest": (0.02, 0.12, 1.00),
        "scenario_churn": (0.08, 0.20, 0.90),
    }

    def paid_amount(row: pd.Series) -> float:
        low, high, value_factor = discount_ranges[row["lifecycle_code"]]
        unit = stable_int(seed, row["user_id"], row["item_id"], row["event_time"], "discount") % 10_001
        discount = low + (high - low) * unit / 10_000
        return round(row["base_price"] * row["quantity"] * value_factor * (1 - discount), 2)

    purchases["purchase_amount"] = purchases.apply(paid_amount, axis=1)

    as_of = pd.Timestamp(as_of_date)
    recency_ranges = {
        "high_value": (1, 20),
        "young_growth": (1, 35),
        "price_sensitive": (5, 50),
        "category_interest": (3, 45),
        "scenario_churn": (91, 180),
    }
    original_last = purchases.groupby("user_id")["event_time"].max()
    user_recency: dict[str, int] = {}
    for user, lifecycle in lifecycle_codes.items():
        low, high = recency_ranges[lifecycle]
        user_recency[user] = low + stable_int(seed, user, "recency") % (high - low + 1)
    purchases["purchase_date"] = [
        as_of
        - pd.Timedelta(days=user_recency[user])
        - (original_last[user] - timestamp)
        for user, timestamp in zip(purchases["user_id"], purchases["event_time"], strict=True)
    ]

    user_metrics = purchases.groupby("user_id").agg(
        purchase_frequency=("item_id", "size"),
        total_consumption=("purchase_amount", "sum"),
        average_order_value=("purchase_amount", "mean"),
        category_diversity=("product_category", "nunique"),
    )
    category_totals = purchases.pivot_table(
        index="user_id", columns="product_category", values="purchase_amount", aggfunc="sum", fill_value=0
    )
    category_ground_truth = category_totals.idxmax(axis=1).astype(str) + "偏好用户"

    profiles = pd.DataFrame.from_dict(
        {
            user: _profile_for_user(user, lifecycle, seed)
            for user, lifecycle in lifecycle_codes.items()
        },
        orient="index",
    )
    user_metrics = user_metrics.join(profiles).join(
        summary.users[["cart", "favorite", "activity_frequency"]], how="left"
    )
    user_metrics["last_purchase_days"] = pd.Series(user_recency)
    coupon_rates = {
        "high_value": 0.15,
        "young_growth": 0.35,
        "price_sensitive": 0.75,
        "category_interest": 0.25,
        "scenario_churn": 0.40,
    }
    user_metrics["coupon_usage"] = pd.Series(
        {
            user: min(
                int(user_metrics.loc[user, "purchase_frequency"]),
                round(
                    (
                        user_metrics.loc[user, "cart"]
                        + user_metrics.loc[user, "favorite"]
                        + 1
                    )
                    * coupon_rates[lifecycle]
                ),
            )
            for user, lifecycle in lifecycle_codes.items()
        }
    )
    user_metrics["lifecycle_code"] = lifecycle_codes

    purchases["customer_id"] = purchases["user_id"].map(lambda value: f"C{stable_int(value) % 10**10:010d}")
    purchases["order_id"] = [
        f"O{stable_int(dataset_id, user, item, timestamp) % 10**14:014d}"
        for user, item, timestamp in zip(
            purchases["user_id"], purchases["item_id"], purchases["event_time"], strict=True
        )
    ]
    metric_columns = [
        "age",
        "gender",
        "city",
        "income_level",
        "membership_level",
        "purchase_frequency",
        "total_consumption",
        "average_order_value",
        "last_purchase_days",
        "category_diversity",
        "coupon_usage",
        "activity_frequency",
        "preferred_channel",
    ]
    for column in metric_columns:
        purchases[column] = purchases["user_id"].map(user_metrics[column])

    purchases["purchase_date"] = pd.to_datetime(purchases["purchase_date"]).dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    purchases["total_consumption"] = purchases["total_consumption"].round(2)
    purchases["average_order_value"] = purchases["average_order_value"].round(2)
    purchases["amount"] = purchases["purchase_amount"]
    purchases["event_time"] = purchases["purchase_date"]
    purchases["category"] = purchases["product_category"]
    benchmark_input = purchases[INPUT_COLUMNS].sort_values(["customer_id", "purchase_date"])

    customer_ids = purchases.drop_duplicates("user_id").set_index("user_id")["customer_id"]
    labels = pd.DataFrame(
        {
            "dataset_id": dataset_id,
            "customer_id": customer_ids,
            "category_ground_truth": category_ground_truth.loc[customer_ids.index],
            "lifecycle_ground_truth": lifecycle_codes.loc[customer_ids.index].map(LIFECYCLE_NAMES),
            "label_source": lifecycle_codes.loc[customer_ids.index].map(
                lambda value: "scenario_enhanced" if value == "scenario_churn" else "rule_derived"
            ),
        }
    ).reset_index(drop=True)[LABEL_COLUMNS]

    diagnostics = {
        "source_behavior_rows": int(summary.users["event_count"].sum()),
        "total_users": int(labels["customer_id"].nunique()),
        "total_orders": len(benchmark_input),
        "lifecycle_distribution": labels["lifecycle_ground_truth"].value_counts().to_dict(),
        "category_distribution": labels["category_ground_truth"].value_counts().to_dict(),
    }
    return benchmark_input, labels, diagnostics


def validate_isolation(benchmark_input: pd.DataFrame, labels: pd.DataFrame) -> None:
    forbidden = {"ground_truth_segment", "category_ground_truth", "lifecycle_ground_truth"}
    leaked = forbidden.intersection(benchmark_input.columns)
    if leaked:
        raise AssertionError(f"Evaluation labels leaked into upload input: {sorted(leaked)}")
    if list(benchmark_input.columns) != INPUT_COLUMNS:
        raise AssertionError("Upload schema does not match the required 24-column schema.")
    if labels["customer_id"].duplicated().any():
        raise AssertionError("benchmark_labels.csv must contain one row per customer.")
    churn_ids = labels.loc[
        labels["lifecycle_ground_truth"] == "scenario_enhanced_churn_user", "customer_id"
    ]
    churn_recency = benchmark_input[
        benchmark_input["customer_id"].isin(churn_ids)
    ].drop_duplicates("customer_id")["last_purchase_days"]
    if not churn_recency.empty and int(churn_recency.min()) <= 90:
        raise AssertionError("Scenario-enhanced churn users must have recency above 90 days.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build one augmented benchmark dataset.")
    parser.add_argument("cleaned", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("data/benchmark/dataset_01"))
    parser.add_argument("--dataset-id", default="dataset_01")
    parser.add_argument("--users", type=int, default=4_000)
    parser.add_argument("--seed", type=int, default=20260810)
    args = parser.parse_args()

    ratios = {
        "high_value": 0.19,
        "young_growth": 0.31,
        "price_sensitive": 0.20,
        "category_interest": 0.17,
        "scenario_churn": 0.13,
    }
    summary = load_behavior_summary(args.cleaned)
    benchmark_input, labels, diagnostics = build_augmented_dataset(
        summary, args.dataset_id, ratios, total_users=args.users, seed=args.seed
    )
    validate_isolation(benchmark_input, labels)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    benchmark_input.to_csv(
        args.output_dir / "customer_behavior_benchmark_input.csv",
        index=False,
        encoding="utf-8-sig",
    )
    labels.to_csv(args.output_dir / "benchmark_labels.csv", index=False, encoding="utf-8-sig")
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
