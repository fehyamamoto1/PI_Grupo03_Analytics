from __future__ import annotations

import random
from datetime import datetime, timedelta

from .schema import (
    CHANNEL_COUNTER,
    CHANNEL_DELIVERY,
    CHANNEL_TABLE,
    ITEM_CANCELED,
    ITEM_OK,
    STATUS_CLOSED,
    STATUS_IN_USE,
)

_INGREDIENTS = [
    ("Pão brioche", "un", 140, 60, 1.20, 5),
    ("Hambúrguer 150 g", "g", 21000, 9000, 0.042, 90),
    ("Queijo cheddar", "g", 5400, 2000, 0.055, 30),
    ("Bacon em fatias", "g", 4100, 1500, 0.048, 20),
    ("Alface americana", "g", 2300, 800, 0.012, 5),
    ("Tomate", "g", 3100, 1000, 0.009, 7),
    ("Cebola caramelizada", "g", 1800, 700, 0.018, 10),
    ("Molho especial", "ml", 2600, 900, 0.020, 15),
    ("Batata congelada", "g", 12500, 5000, 0.014, 180),
    ("Óleo de girassol", "ml", 7000, 2000, 0.011, 365),
    ("Refrigerante lata", "un", 96, 48, 2.60, 300),
    ("Cerveja long neck", "un", 72, 36, 4.80, 180),
]

_MENU = [
    ("Classico", 32.00, "BURGER", [
        ("Pão brioche", 1, "un"), ("Hambúrguer 150 g", 150, "g"),
        ("Queijo cheddar", 40, "g"), ("Alface americana", 15, "g"),
        ("Tomate", 20, "g"), ("Molho especial", 25, "ml"),
    ], 30),
    ("Cheddar Bacon", 38.90, "BURGER", [
        ("Pão brioche", 1, "un"), ("Hambúrguer 150 g", 150, "g"),
        ("Queijo cheddar", 60, "g"), ("Bacon em fatias", 45, "g"),
        ("Molho especial", 25, "ml"),
    ], 26),
    ("Duplo Smash", 46.50, "BURGER", [
        ("Pão brioche", 1, "un"), ("Hambúrguer 150 g", 0.3, "kg"),
        ("Queijo cheddar", 80, "g"), ("Cebola caramelizada", 30, "g"),
        ("Molho especial", 30, "ml"),
    ], 16),
    ("Batata frita", 18.00, "ACOMPANHAMENTO", [
        ("Batata congelada", 180, "g"), ("Óleo de girassol", 20, "ml"),
    ], 34),
    ("Refrigerante", 8.00, "BEBIDA", [("Refrigerante lata", 1, "un")], 28),
    ("Cerveja", 12.00, "BEBIDA", [("Cerveja long neck", 1, "un")], 20),
]

_WEEKDAY_WEIGHT = [0.0, 0.45, 0.55, 0.75, 1.65, 2.00, 1.05]

_HOUR_WEIGHT = {
    CHANNEL_TABLE: {18: 0.40, 19: 0.90, 20: 1.60, 21: 1.65, 22: 1.00, 23: 0.35},
    CHANNEL_COUNTER: {18: 0.75, 19: 1.10, 20: 1.30, 21: 1.05, 22: 0.70, 23: 0.30},
    CHANNEL_DELIVERY: {18: 0.70, 19: 1.20, 20: 1.55, 21: 1.40, 22: 1.15, 23: 0.75},
}

_CHANNEL_WEIGHT = {CHANNEL_TABLE: 45, CHANNEL_DELIVERY: 38, CHANNEL_COUNTER: 17}
_PLATFORM_WEIGHT = {"PROPRIO": 34, "IFOOD": 48, "RAPPI": 18}
_PAYMENT_WEIGHT = {"PIX": 42, "CREDITO": 31, "DEBITO": 18, "DINHEIRO": 9}

_OPERATORS = [
    ("Ana", 2, 0.02),
    ("Bruno", 6, 0.10),
    ("Carla", 3, 0.04),
    ("Diego", 18, 0.34),
]


def _oid(rng: random.Random) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(24))


def _pick(rng: random.Random, weights: dict):
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def generate(days: int = 180, seed: int = 42) -> dict:
    rng = random.Random(seed)

    ingredients = [
        {"_id": _oid(rng), "name": name, "quantity": float(qty),
         "measurementUnit": unit, "alertLevel": float(alert),
         "unitCost": float(cost), "shelfLifeDays": int(shelf)}
        for name, unit, qty, alert, cost, shelf in _INGREDIENTS
    ]
    by_name = {doc["name"]: doc for doc in ingredients}

    menu = []
    for name, value, category, recipe, weight in _MENU:
        menu.append({
            "_id": _oid(rng),
            "name": name,
            "description": f"{name} da casa",
            "imageUrl": "",
            "value": float(value),
            "category": category,
            "active": True,
            "ingredients": [
                {"ingredientId": by_name[ing]["_id"],
                 "quantity": float(q), "measurementUnit": u}
                for ing, q, u in recipe
            ],
            "_weight": weight,
        })
    weights = [item.pop("_weight") for item in menu]

    no_beer = [m for m in menu if m["name"] != "Cerveja"]
    no_beer_w = [w for m, w in zip(menu, weights) if m["name"] != "Cerveja"]

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - timedelta(days=days - 1)

    orders = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        base = _WEEKDAY_WEIGHT[day.weekday()]
        if base == 0.0:
            continue

        trend = 1.0 + 0.22 * (offset / max(days - 1, 1))
        n_orders = max(0, int(rng.gauss(11 * base * trend, 2.2 * base)))
        shift_end = day + timedelta(hours=23, minutes=55)

        for _ in range(n_orders):
            channel = _pick(rng, _CHANNEL_WEIGHT)
            hours = _HOUR_WEIGHT[channel]
            hour = rng.choices(list(hours), weights=list(hours.values()))[0]
            when = day + timedelta(hours=hour, minutes=rng.randint(0, 59))

            op_name, op_delay, op_batch = rng.choice(_OPERATORS)

            if channel == CHANNEL_DELIVERY:
                n_items = rng.choices([1, 2, 3], weights=[26, 46, 28])[0]
                party = 0
                pool, pool_w = no_beer, no_beer_w
            elif channel == CHANNEL_COUNTER:
                n_items = rng.choices([1, 2, 3], weights=[38, 42, 20])[0]
                party = 1
                pool, pool_w = menu, weights
            else:
                n_items = rng.choices([2, 3, 4, 5], weights=[26, 34, 26, 14])[0]
                party = rng.choices([1, 2, 3, 4], weights=[14, 44, 24, 18])[0]
                pool, pool_w = menu, weights

            chosen = rng.choices(pool, weights=pool_w, k=n_items)

            item_list, total = [], 0.0
            for item in chosen:
                qty = rng.choices([1, 2], weights=[82, 18])[0]
                canceled = rng.random() < 0.012
                if not canceled:
                    total += item["value"] * qty
                item_list.append({
                    "itemId": item["_id"],
                    "itemName": item["name"],
                    "quantity": qty,
                    "itemValue": item["value"],
                    "itemStatus": ITEM_CANCELED if canceled else ITEM_OK,
                    "notes": rng.choice([
                        "", "", "", "", "sem cebola", "ponto mais passado",
                        "sem tomate", "molho a parte",
                    ]),
                })

            discount = 0.0
            if rng.random() < 0.08:
                discount = round(total * rng.choice([0.05, 0.10]), 2)

            minutes = {
                CHANNEL_TABLE: rng.gauss(52, 14),
                CHANNEL_COUNTER: rng.gauss(17, 5),
                CHANNEL_DELIVERY: rng.gauss(38, 11),
            }[channel]
            closed_at = when + timedelta(minutes=max(6.0, minutes))

            if rng.random() < op_batch:
                created_at = shift_end - timedelta(minutes=rng.randint(0, 25))
            else:
                created_at = when + timedelta(
                    minutes=max(0.0, rng.gauss(op_delay, op_delay * 0.6))
                )

            order = {
                "_id": _oid(rng),
                "diningTableId": rng.randint(1, 12) if channel == CHANNEL_TABLE else 0,
                "status": STATUS_CLOSED,
                "itemList": item_list,
                "totalValue": round(max(total - discount, 0.0), 2),
                "discountValue": discount,
                "orderDate": when,
                "closedAt": closed_at,
                "createdAt": created_at,
                "orderChannel": channel,
                "paymentMethod": _pick(rng, _PAYMENT_WEIGHT),
                "partySize": party,
                "operatorName": op_name,
            }
            if channel == CHANNEL_DELIVERY:
                order["deliveryPlatform"] = _pick(rng, _PLATFORM_WEIGHT)

            orders.append(order)

    orders.sort(key=lambda o: o["orderDate"])
    for order in orders[-2:]:
        order["status"] = STATUS_IN_USE
        order["closedAt"] = None

    return {"DiningTables": orders, "Menu": menu, "Ingredients": ingredients}
