COLLECTIONS = ("DiningTables", "Menu", "Ingredients")

STATUS_IN_USE = "IN_USE"
STATUS_CLOSED = "CLOSED"

CHANNEL_TABLE = "MESA"
CHANNEL_COUNTER = "BALCAO"
CHANNEL_DELIVERY = "DELIVERY"
CHANNELS = (CHANNEL_TABLE, CHANNEL_COUNTER, CHANNEL_DELIVERY)

CHANNEL_LABEL = {
    CHANNEL_TABLE: "Mesa",
    CHANNEL_COUNTER: "Balcão",
    CHANNEL_DELIVERY: "Delivery",
}

PLATFORM_OWN = "PROPRIO"
PLATFORM_COMMISSION = {
    PLATFORM_OWN: 0.00,
    "IFOOD": 0.23,
    "RAPPI": 0.20,
}

PAYMENT_METHODS = ("PIX", "CREDITO", "DEBITO", "DINHEIRO")

PAYMENT_FEE = {
    "PIX": 0.00,
    "DINHEIRO": 0.00,
    "DEBITO": 0.015,
    "CREDITO": 0.032,
}

ITEM_OK = "OK"
ITEM_CANCELED = "CANCELADO"

CATEGORIES = ("BURGER", "ACOMPANHAMENTO", "BEBIDA", "SOBREMESA")

CATEGORY_LABEL = {
    "BURGER": "Burger",
    "ACOMPANHAMENTO": "Acompanhamento",
    "BEBIDA": "Bebida",
    "SOBREMESA": "Sobremesa",
}

UNIT_TO_BASE = {
    "g": ("g", 1.0),
    "grama": ("g", 1.0),
    "gramas": ("g", 1.0),
    "kg": ("g", 1000.0),
    "quilo": ("g", 1000.0),
    "ml": ("ml", 1.0),
    "l": ("ml", 1000.0),
    "litro": ("ml", 1000.0),
    "un": ("un", 1.0),
    "und": ("un", 1.0),
    "unidade": ("un", 1.0),
    "unidades": ("un", 1.0),
    "fatia": ("un", 1.0),
    "fatias": ("un", 1.0),
}


def normalize_unit(value, quantity):
    key = str(value or "").strip().lower()
    if key not in UNIT_TO_BASE:
        return float(quantity), key or "?", False
    base_unit, factor = UNIT_TO_BASE[key]
    return float(quantity) * factor, base_unit, True


def platform_commission(platform) -> float:
    if not platform:
        return 0.0
    return PLATFORM_COMMISSION.get(str(platform).strip().upper(), 0.0)


def payment_fee(method) -> float:
    if not method:
        return 0.0
    return PAYMENT_FEE.get(str(method).strip().upper(), 0.0)


def infer_category(name) -> str:
    text = str(name or "").lower()
    bebidas = ("refrigerante", "cerveja", "suco", "agua", "água", "refri",
               "long neck", "coca")
    acomp = ("batata", "onion", "fritas", "nuggets", "polenta")
    doces = ("sobremesa", "milkshake", "brownie", "petit", "sorvete", "pudim")
    if any(w in text for w in bebidas):
        return "BEBIDA"
    if any(w in text for w in acomp):
        return "ACOMPANHAMENTO"
    if any(w in text for w in doces):
        return "SOBREMESA"
    return "BURGER"
