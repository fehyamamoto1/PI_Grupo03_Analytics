from __future__ import annotations

import pandas as pd

from .schema import (
    CHANNEL_TABLE,
    ITEM_CANCELED,
    ITEM_OK,
    STATUS_CLOSED,
    infer_category,
    normalize_unit,
    payment_fee,
    platform_commission,
)

_UNSET = "(não informado)"


def _clean(value, default=_UNSET):
    text = str(value).strip() if value is not None else ""
    return text.upper() if text else default


def build_sales(raw: dict) -> pd.DataFrame:
    rows = []
    for order in raw["DiningTables"]:
        order_date = pd.to_datetime(order.get("orderDate"), errors="coerce")
        closed_at = pd.to_datetime(order.get("closedAt"), errors="coerce")
        created_at = pd.to_datetime(order.get("createdAt"), errors="coerce")

        channel = _clean(order.get("orderChannel"))
        platform = _clean(order.get("deliveryPlatform"), "")
        payment = _clean(order.get("paymentMethod"))

        duration = (
            (closed_at - order_date).total_seconds() / 60.0
            if pd.notna(closed_at) and pd.notna(order_date) else None
        )
        entry_lag = (
            (created_at - order_date).total_seconds() / 60.0
            if pd.notna(created_at) and pd.notna(order_date) else None
        )

        n_items = len(order.get("itemList") or [])
        discount = float(order.get("discountValue") or 0.0)

        for item in order.get("itemList") or []:
            qty = float(item.get("quantity") or 0)
            unit_value = float(item.get("itemValue") or 0.0)
            gross = qty * unit_value
            canceled = _clean(item.get("itemStatus"), ITEM_OK) == ITEM_CANCELED

            rows.append({
                "order_id": order["_id"],
                "order_date": order_date,
                "closed_at": closed_at,
                "created_at": created_at,
                "duration_min": duration,
                "entry_lag_min": entry_lag,
                "dining_table_id": order.get("diningTableId"),
                "status": order.get("status"),
                "channel": channel,
                "platform": platform,
                "payment": payment,
                "party_size": float(order.get("partySize") or 0),
                "operator": _clean(order.get("operatorName")).title(),
                "item_id": item.get("itemId"),
                "item_name": item.get("itemName"),
                "quantity": qty,
                "unit_value": unit_value,
                "line_value": 0.0 if canceled else gross,
                "canceled_value": gross if canceled else 0.0,
                "is_canceled": canceled,
                "notes": str(item.get("notes") or "").strip(),
                "discount_share": discount / n_items if n_items else 0.0,
            })

    sales = pd.DataFrame(rows, columns=[
        "order_id", "order_date", "closed_at", "created_at", "duration_min",
        "entry_lag_min", "dining_table_id", "status", "channel", "platform",
        "payment", "party_size", "operator", "item_id", "item_name",
        "quantity", "unit_value", "line_value", "canceled_value",
        "is_canceled", "notes", "discount_share",
    ])
    if sales.empty:
        return sales

    sales["date"] = sales["order_date"].dt.normalize()
    sales["hour"] = sales["order_date"].dt.hour
    sales["weekday"] = sales["order_date"].dt.day_of_week

    commission = sales["platform"].map(platform_commission).fillna(0.0)
    fee = sales["payment"].map(payment_fee).fillna(0.0)
    sales["fee_rate"] = commission + fee
    sales["net_value"] = sales["line_value"] * (1.0 - sales["fee_rate"])
    return sales


def closed_only(sales: pd.DataFrame) -> pd.DataFrame:
    if sales.empty:
        return sales
    return sales[sales["status"] == STATUS_CLOSED].copy()


def build_ingredients(raw: dict) -> pd.DataFrame:
    rows = []
    for doc in raw["Ingredients"]:
        unit_raw = doc.get("measurementUnit")
        qty_base, unit_base, known = normalize_unit(unit_raw, doc.get("quantity") or 0)
        alert_base, _, _ = normalize_unit(unit_raw, doc.get("alertLevel") or 0)

        unit_cost = doc.get("unitCost")
        rows.append({
            "ingredient_id": doc["_id"],
            "ingredient_name": doc.get("name"),
            "stock_base": qty_base,
            "alert_base": alert_base,
            "unit_base": unit_base,
            "unit_raw": unit_raw,
            "unit_known": known,
            "unit_cost": float(unit_cost) if unit_cost is not None else None,
            "has_cost": unit_cost is not None,
            "shelf_life_days": doc.get("shelfLifeDays"),
            "stock_value": (
                qty_base * float(unit_cost) if unit_cost is not None else None
            ),
            "below_alert": qty_base < alert_base,
        })
    return pd.DataFrame(rows, columns=[
        "ingredient_id", "ingredient_name", "stock_base", "alert_base",
        "unit_base", "unit_raw", "unit_known", "unit_cost", "has_cost",
        "shelf_life_days", "stock_value", "below_alert",
    ])


def build_recipe(raw: dict) -> pd.DataFrame:
    info = {
        doc["_id"]: (doc.get("name"), doc.get("unitCost"))
        for doc in raw["Ingredients"]
    }
    rows = []
    for item in raw["Menu"]:
        for ing in item.get("ingredients") or []:
            qty_base, unit_base, known = normalize_unit(
                ing.get("measurementUnit"), ing.get("quantity") or 0
            )
            name, unit_cost = info.get(ing.get("ingredientId"), (None, None))
            rows.append({
                "item_id": item["_id"],
                "item_name": item.get("name"),
                "item_value": float(item.get("value") or 0.0),
                "ingredient_id": ing.get("ingredientId"),
                "ingredient_name": name,
                "qty_per_unit_base": qty_base,
                "unit_base": unit_base,
                "unit_raw": ing.get("measurementUnit"),
                "unit_known": known,
                "line_cost": (
                    qty_base * float(unit_cost) if unit_cost is not None else None
                ),
            })
    return pd.DataFrame(rows, columns=[
        "item_id", "item_name", "item_value", "ingredient_id", "ingredient_name",
        "qty_per_unit_base", "unit_base", "unit_raw", "unit_known", "line_cost",
    ])


def build_products(raw: dict, recipe: pd.DataFrame) -> pd.DataFrame:
    cost_by_item, complete = {}, {}
    if not recipe.empty:
        grouped = recipe.groupby("item_id")["line_cost"]
        cost_by_item = grouped.sum(min_count=1).to_dict()
        complete = grouped.apply(lambda s: s.notna().all()).to_dict()

    rows = []
    for item in raw["Menu"]:
        category = _clean(item.get("category"), "")
        inferred = not category
        if inferred:
            category = infer_category(item.get("name"))

        value = float(item.get("value") or 0.0)
        cost = cost_by_item.get(item["_id"])
        cost_ok = bool(complete.get(item["_id"], False)) and cost is not None

        rows.append({
            "item_id": item["_id"],
            "item_name": item.get("name"),
            "category": category,
            "category_inferred": inferred,
            "item_value": value,
            "unit_cost": cost if cost_ok else None,
            "margin_value": (value - cost) if cost_ok else None,
            "margin_pct": (
                100.0 * (value - cost) / value if cost_ok and value else None
            ),
            "active": bool(item.get("active", True)),
        })
    return pd.DataFrame(rows, columns=[
        "item_id", "item_name", "category", "category_inferred", "item_value",
        "unit_cost", "margin_value", "margin_pct", "active",
    ])


def build_consumption(sales: pd.DataFrame, recipe: pd.DataFrame) -> pd.DataFrame:
    cols = ["date", "ingredient_id", "ingredient_name", "unit_base", "qty_base"]
    if sales.empty or recipe.empty:
        return pd.DataFrame(columns=cols)

    effective = sales[~sales["is_canceled"]]
    if effective.empty:
        return pd.DataFrame(columns=cols)

    merged = effective.merge(
        recipe[["item_id", "ingredient_id", "ingredient_name",
                "qty_per_unit_base", "unit_base"]],
        on="item_id", how="inner",
    )
    if merged.empty:
        return pd.DataFrame(columns=cols)

    merged["qty_base"] = merged["quantity"] * merged["qty_per_unit_base"]
    return (
        merged.groupby(["date", "ingredient_id", "ingredient_name", "unit_base"],
                       as_index=False)["qty_base"].sum()
    )


def build_orders(sales: pd.DataFrame) -> pd.DataFrame:
    cols = ["order_id", "order_date", "channel", "platform", "payment",
            "operator", "dining_table_id", "party_size", "items", "quantity",
            "revenue", "net_value", "canceled_value", "duration_min",
            "entry_lag_min", "status"]
    if sales.empty:
        return pd.DataFrame(columns=cols)

    grouped = sales.groupby("order_id", as_index=False).agg(
        order_date=("order_date", "first"),
        channel=("channel", "first"),
        platform=("platform", "first"),
        payment=("payment", "first"),
        operator=("operator", "first"),
        dining_table_id=("dining_table_id", "first"),
        party_size=("party_size", "first"),
        items=("item_id", "size"),
        quantity=("quantity", "sum"),
        revenue=("line_value", "sum"),
        net_value=("net_value", "sum"),
        canceled_value=("canceled_value", "sum"),
        duration_min=("duration_min", "first"),
        entry_lag_min=("entry_lag_min", "first"),
        status=("status", "first"),
    )
    return grouped.sort_values("order_date", ascending=False).reset_index(drop=True)


def quality_report(raw: dict, sales: pd.DataFrame, recipe: pd.DataFrame,
                   products: pd.DataFrame) -> dict:
    menu_ids = {item["_id"] for item in raw["Menu"]}
    ingredient_ids = {doc["_id"] for doc in raw["Ingredients"]}

    total = len(sales)
    orphan_items = int((~sales["item_id"].isin(menu_ids)).sum()) if total else 0
    open_lines = int((sales["status"] != STATUS_CLOSED).sum()) if total else 0
    no_date = int(sales["order_date"].isna().sum()) if total else 0
    non_positive = int((sales["quantity"] <= 0).sum()) if total else 0
    canceled = int(sales["is_canceled"].sum()) if total else 0

    missing_channel = int((sales["channel"] == _UNSET).sum()) if total else 0
    missing_payment = int((sales["payment"] == _UNSET).sum()) if total else 0
    missing_operator = int((sales["operator"] == _UNSET.title()).sum()) if total else 0
    missing_duration = int(sales["duration_min"].isna().sum()) if total else 0
    missing_lag = int(sales["entry_lag_min"].isna().sum()) if total else 0

    late = 0
    if total and sales["entry_lag_min"].notna().any():
        late = int((sales["entry_lag_min"] > 30).sum())

    bad_units = recipe.loc[~recipe["unit_known"], "unit_raw"].dropna().unique().tolist()
    orphan_recipe = (
        recipe.loc[~recipe["ingredient_id"].isin(ingredient_ids), "item_name"]
        .dropna().unique().tolist()
    )
    inferred_cat = (
        products.loc[products["category_inferred"], "item_name"].tolist()
        if not products.empty else []
    )
    without_cost = (
        products.loc[products["unit_cost"].isna(), "item_name"].tolist()
        if not products.empty else []
    )

    valid = total - orphan_items - no_date - non_positive
    return {
        "orders": len(raw["DiningTables"]),
        "menu_items": len(menu_ids),
        "ingredients": len(ingredient_ids),
        "sale_lines": total,
        "valid_lines": max(valid, 0),
        "valid_pct": round(100.0 * max(valid, 0) / total, 2) if total else 0.0,
        "lines_open_orders": open_lines,
        "lines_item_not_in_menu": orphan_items,
        "lines_without_date": no_date,
        "lines_non_positive_qty": non_positive,
        "lines_canceled": canceled,
        "lines_late_entry": late,
        "unknown_units": bad_units,
        "recipes_with_orphan_ingredient": orphan_recipe,
        "categories_inferred": inferred_cat,
        "products_without_cost": without_cost,
        "missing": {
            "orderChannel": missing_channel,
            "paymentMethod": missing_payment,
            "operatorName": missing_operator,
            "closedAt": missing_duration,
            "createdAt": missing_lag,
        },
    }


def build_all(raw: dict) -> dict:
    sales_all = build_sales(raw)
    recipe = build_recipe(raw)
    products = build_products(raw, recipe)
    sales = closed_only(sales_all)
    return {
        "sales_all": sales_all,
        "sales": sales,
        "orders": build_orders(sales),
        "recipe": recipe,
        "products": products,
        "ingredients": build_ingredients(raw),
        "consumption": build_consumption(sales, recipe),
        "quality": quality_report(raw, sales_all, recipe, products),
    }
