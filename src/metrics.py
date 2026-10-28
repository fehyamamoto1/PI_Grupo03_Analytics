from __future__ import annotations

import numpy as np
import pandas as pd

from .schema import CHANNEL_DELIVERY, CHANNEL_LABEL, platform_commission

WEEKDAY_PT = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]


def window(sales: pd.DataFrame, days: int) -> pd.DataFrame:
    if sales.empty:
        return sales
    end = sales["date"].max()
    start = end - pd.Timedelta(days=days - 1)
    return sales[sales["date"].between(start, end)]


def kpis(sales: pd.DataFrame, days: int = 28) -> dict:
    empty = {
        "revenue": 0.0, "net_revenue": 0.0, "orders": 0, "ticket": 0.0,
        "items": 0.0, "canceled": 0.0, "discount": 0.0, "fees": 0.0,
        "orders_per_day": 0.0, "items_per_order": 0.0,
        "revenue_delta": None, "ticket_delta": None, "days": days,
        "has_previous": False, "period_start": None, "period_end": None,
    }
    if sales.empty:
        return empty

    end = sales["date"].max()
    cur_start = end - pd.Timedelta(days=days - 1)
    prev_start = cur_start - pd.Timedelta(days=days)

    cur = sales[sales["date"].between(cur_start, end)]
    prev = sales[sales["date"].between(prev_start, cur_start - pd.Timedelta(days=1))]

    def block(df):
        if df.empty:
            return 0.0, 0, 0.0, 0.0
        revenue = float(df["line_value"].sum())
        orders = int(df["order_id"].nunique())
        items = float(df.loc[~df["is_canceled"], "quantity"].sum())
        return revenue, orders, (revenue / orders if orders else 0.0), items

    revenue, orders, ticket, items = block(cur)
    p_revenue, _, p_ticket, _ = block(prev)

    def delta(now, before):
        return round(100.0 * (now - before) / before, 1) if before else None

    net = float(cur["net_value"].sum()) if not cur.empty else 0.0
    return {
        "revenue": revenue,
        "net_revenue": net,
        "fees": revenue - net,
        "orders": orders,
        "ticket": ticket,
        "items": items,
        "canceled": float(cur["canceled_value"].sum()) if not cur.empty else 0.0,
        "discount": float(cur["discount_share"].sum()) if not cur.empty else 0.0,
        "orders_per_day": orders / days if days else 0.0,
        "items_per_order": items / orders if orders else 0.0,
        "revenue_delta": delta(revenue, p_revenue),
        "ticket_delta": delta(ticket, p_ticket),
        "days": days,
        "period_start": cur_start,
        "period_end": end,
        "has_previous": not prev.empty,
    }


def daily_revenue(sales: pd.DataFrame) -> pd.DataFrame:
    if sales.empty:
        return pd.DataFrame(columns=["date", "revenue", "orders"])
    return (
        sales.groupby("date")
        .agg(revenue=("line_value", "sum"), orders=("order_id", "nunique"))
        .reset_index()
    )


def daily_revenue_by_channel(sales: pd.DataFrame) -> pd.DataFrame:
    if sales.empty:
        return pd.DataFrame(columns=["date", "channel", "revenue"])
    out = (
        sales.groupby(["date", "channel"], as_index=False)["line_value"]
        .sum().rename(columns={"line_value": "revenue"})
    )
    out["channel_label"] = out["channel"].map(
        lambda c: CHANNEL_LABEL.get(c, str(c).title())
    )
    return out


def weekday_hour_matrix(sales: pd.DataFrame) -> pd.DataFrame:
    if sales.empty:
        return pd.DataFrame()
    grid = (
        sales.groupby(["weekday", "hour"])["order_id"].nunique().reset_index(name="orders")
    )
    pivot = grid.pivot(index="weekday", columns="hour", values="orders")
    pivot = pivot.reindex(range(7)).fillna(0.0)
    pivot.index = [WEEKDAY_PT[i] for i in pivot.index]
    return pivot


def channel_breakdown(sales: pd.DataFrame) -> pd.DataFrame:
    cols = ["channel_label", "orders", "revenue", "net_value", "ticket",
            "items_per_order", "avg_duration", "share"]
    if sales.empty:
        return pd.DataFrame(columns=cols)

    out = sales.groupby("channel", as_index=False).agg(
        orders=("order_id", "nunique"),
        revenue=("line_value", "sum"),
        net_value=("net_value", "sum"),
        quantity=("quantity", "sum"),
        avg_duration=("duration_min", "mean"),
    )
    out["ticket"] = out["revenue"] / out["orders"].replace(0, np.nan)
    out["items_per_order"] = out["quantity"] / out["orders"].replace(0, np.nan)
    total = out["revenue"].sum()
    out["share"] = out["revenue"] / total * 100 if total else 0.0
    out["channel_label"] = out["channel"].map(
        lambda c: CHANNEL_LABEL.get(c, str(c).title())
    )
    return out.sort_values("revenue", ascending=False).reset_index(drop=True)


def platform_breakdown(sales: pd.DataFrame) -> pd.DataFrame:
    cols = ["platform", "orders", "revenue", "commission_pct",
            "commission_value", "net_value"]
    if sales.empty:
        return pd.DataFrame(columns=cols)

    sub = sales[(sales["channel"] == CHANNEL_DELIVERY) & (sales["platform"] != "")]
    if sub.empty:
        return pd.DataFrame(columns=cols)

    out = sub.groupby("platform", as_index=False).agg(
        orders=("order_id", "nunique"),
        revenue=("line_value", "sum"),
    )
    out["commission_pct"] = out["platform"].map(platform_commission) * 100
    out["commission_value"] = out["revenue"] * out["platform"].map(platform_commission)
    out["net_value"] = out["revenue"] - out["commission_value"]
    return out.sort_values("revenue", ascending=False).reset_index(drop=True)


def payment_mix(sales: pd.DataFrame) -> pd.DataFrame:
    cols = ["payment", "orders", "revenue", "share", "fee_value"]
    if sales.empty:
        return pd.DataFrame(columns=cols)

    out = sales.groupby("payment", as_index=False).agg(
        orders=("order_id", "nunique"),
        revenue=("line_value", "sum"),
        net_value=("net_value", "sum"),
    )
    out["fee_value"] = out["revenue"] - out["net_value"]
    total = out["revenue"].sum()
    out["share"] = out["revenue"] / total * 100 if total else 0.0
    return out.sort_values("revenue", ascending=False).reset_index(drop=True)


def category_mix(sales: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    cols = ["category", "quantity", "revenue", "share"]
    if sales.empty or products.empty:
        return pd.DataFrame(columns=cols)

    merged = sales.merge(products[["item_id", "category"]], on="item_id", how="left")
    merged["category"] = merged["category"].fillna("(sem categoria)")
    out = merged.groupby("category", as_index=False).agg(
        quantity=("quantity", "sum"),
        revenue=("line_value", "sum"),
    )
    total = out["revenue"].sum()
    out["share"] = out["revenue"] / total * 100 if total else 0.0
    return out.sort_values("revenue", ascending=False).reset_index(drop=True)


def attach_rate(sales: pd.DataFrame, products: pd.DataFrame,
                category: str = "BEBIDA") -> float:
    if sales.empty or products.empty:
        return 0.0
    merged = sales.merge(products[["item_id", "category"]], on="item_id", how="left")
    total = merged["order_id"].nunique()
    if not total:
        return 0.0
    with_cat = merged.loc[
        (merged["category"] == category) & (~merged["is_canceled"]), "order_id"
    ].nunique()
    return 100.0 * with_cat / total


def operator_discipline(sales: pd.DataFrame) -> pd.DataFrame:
    cols = ["operator", "orders", "median_lag_min", "p90_lag_min",
            "late_pct", "cancel_pct"]
    if sales.empty or sales["entry_lag_min"].isna().all():
        return pd.DataFrame(columns=cols)

    by_order = sales.groupby("order_id", as_index=False).agg(
        operator=("operator", "first"),
        entry_lag_min=("entry_lag_min", "first"),
        canceled=("is_canceled", "max"),
    )
    out = by_order.groupby("operator", as_index=False).agg(
        orders=("order_id", "nunique"),
        median_lag_min=("entry_lag_min", "median"),
        p90_lag_min=("entry_lag_min", lambda s: s.quantile(0.9)),
        late=("entry_lag_min", lambda s: (s > 30).sum()),
        cancels=("canceled", "sum"),
    )
    out["late_pct"] = out["late"] / out["orders"].replace(0, np.nan) * 100
    out["cancel_pct"] = out["cancels"] / out["orders"].replace(0, np.nan) * 100
    return out.sort_values("late_pct", ascending=False).reset_index(drop=True)


def duration_stats(sales: pd.DataFrame) -> pd.DataFrame:
    cols = ["channel_label", "orders", "median_min", "p90_min"]
    if sales.empty or sales["duration_min"].isna().all():
        return pd.DataFrame(columns=cols)

    by_order = sales.groupby("order_id", as_index=False).agg(
        channel=("channel", "first"),
        duration_min=("duration_min", "first"),
    ).dropna(subset=["duration_min"])
    if by_order.empty:
        return pd.DataFrame(columns=cols)

    out = by_order.groupby("channel", as_index=False).agg(
        orders=("order_id", "nunique"),
        median_min=("duration_min", "median"),
        p90_min=("duration_min", lambda s: s.quantile(0.9)),
    )
    out["channel_label"] = out["channel"].map(
        lambda c: CHANNEL_LABEL.get(c, str(c).title())
    )
    return out.sort_values("median_min", ascending=False).reset_index(drop=True)


def product_ranking(sales: pd.DataFrame) -> pd.DataFrame:
    if sales.empty:
        return pd.DataFrame(columns=["item_name", "quantity", "revenue", "share", "cum_share"])
    rank = (
        sales.groupby("item_name")
        .agg(quantity=("quantity", "sum"), revenue=("line_value", "sum"))
        .sort_values("revenue", ascending=False)
        .reset_index()
    )
    total = rank["revenue"].sum()
    rank["share"] = rank["revenue"] / total * 100 if total else 0.0
    rank["cum_share"] = rank["share"].cumsum()
    return rank


def margin_ranking(sales: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    cols = ["item_name", "category", "quantity", "revenue", "cost",
            "margin", "margin_pct"]
    if sales.empty or products.empty:
        return pd.DataFrame(columns=cols)

    merged = sales[~sales["is_canceled"]].merge(
        products[["item_id", "category", "unit_cost"]], on="item_id", how="left"
    )
    merged["cost"] = merged["quantity"] * merged["unit_cost"]
    out = merged.groupby(["item_name", "category"], as_index=False).agg(
        quantity=("quantity", "sum"),
        revenue=("line_value", "sum"),
        cost=("cost", "sum"),
    )
    out["margin"] = out["revenue"] - out["cost"]
    out["margin_pct"] = np.where(
        out["revenue"] > 0, out["margin"] / out["revenue"] * 100, np.nan
    )
    return out.sort_values("margin", ascending=False).reset_index(drop=True)


def ingredient_usage(consumption: pd.DataFrame, days: int = 28) -> pd.DataFrame:
    cols = ["ingredient_name", "unit_base", "total_base", "per_day"]
    if consumption.empty:
        return pd.DataFrame(columns=cols)
    end = consumption["date"].max()
    start = end - pd.Timedelta(days=days - 1)
    win = consumption[consumption["date"].between(start, end)]
    if win.empty:
        return pd.DataFrame(columns=cols)
    out = (
        win.groupby(["ingredient_name", "unit_base"], as_index=False)["qty_base"]
        .sum().rename(columns={"qty_base": "total_base"})
    )
    out["per_day"] = out["total_base"] / days
    return out.sort_values("total_base", ascending=False)


def stock_value(ingredients: pd.DataFrame) -> dict:
    if ingredients.empty:
        return {"total": 0.0, "priced": 0, "unpriced": 0, "below_alert": 0}
    priced = ingredients["stock_value"].notna()
    return {
        "total": float(ingredients.loc[priced, "stock_value"].sum()),
        "priced": int(priced.sum()),
        "unpriced": int((~priced).sum()),
        "below_alert": int(ingredients["below_alert"].sum()),
    }


def expiry_risk(ingredients: pd.DataFrame, usage: pd.DataFrame) -> pd.DataFrame:
    cols = ["ingredient_name", "unit_base", "stock_base", "per_day",
            "coverage_days", "shelf_life_days", "at_risk"]
    if ingredients.empty or usage.empty:
        return pd.DataFrame(columns=cols)

    merged = ingredients.merge(
        usage[["ingredient_name", "per_day"]], on="ingredient_name", how="inner"
    )
    merged = merged[merged["shelf_life_days"].notna() & (merged["per_day"] > 0)]
    if merged.empty:
        return pd.DataFrame(columns=cols)

    merged["coverage_days"] = merged["stock_base"] / merged["per_day"]
    merged["at_risk"] = merged["coverage_days"] > merged["shelf_life_days"]
    return (
        merged.loc[:, cols]
        .sort_values(["at_risk", "coverage_days"], ascending=[False, False])
        .reset_index(drop=True)
    )


def purchase_plan(
    item_forecast: pd.DataFrame,
    recipe: pd.DataFrame,
    ingredients: pd.DataFrame,
) -> pd.DataFrame:
    cols = ["ingredient_name", "unit_base", "stock_base", "needed_base",
            "buy_base", "buy_value", "coverage_days", "status"]
    if item_forecast.empty or recipe.empty:
        return pd.DataFrame(columns=cols)

    need = item_forecast.merge(
        recipe[["item_id", "ingredient_id", "ingredient_name",
                "qty_per_unit_base", "unit_base"]],
        on="item_id", how="inner",
    )
    if need.empty:
        return pd.DataFrame(columns=cols)

    need["needed_base"] = need["quantity"] * need["qty_per_unit_base"]
    agg = need.groupby(["ingredient_id", "ingredient_name", "unit_base"],
                       as_index=False)["needed_base"].sum()

    plan = agg.merge(
        ingredients[["ingredient_id", "stock_base", "unit_cost"]],
        on="ingredient_id", how="left",
    )
    plan["stock_base"] = plan["stock_base"].fillna(0.0)
    plan["buy_base"] = (plan["needed_base"] - plan["stock_base"]).clip(lower=0.0)
    plan["buy_value"] = plan["buy_base"] * plan["unit_cost"]

    horizon = (
        int(item_forecast["horizon_days"].iloc[0])
        if "horizon_days" in item_forecast else 7
    )
    per_day = plan["needed_base"] / max(horizon, 1)
    plan["coverage_days"] = np.where(
        per_day > 0, plan["stock_base"] / per_day, np.inf
    )

    def classify(row):
        if row["buy_base"] > 0:
            return "repor hoje"
        if row["coverage_days"] < horizon * 1.5:
            return "atenção"
        return "suficiente"

    plan["status"] = plan.apply(classify, axis=1)
    order = {"repor hoje": 0, "atenção": 1, "suficiente": 2}
    plan["_o"] = plan["status"].map(order)
    return (
        plan.sort_values(["_o", "buy_base"], ascending=[True, False])
        .loc[:, cols]
        .reset_index(drop=True)
    )
