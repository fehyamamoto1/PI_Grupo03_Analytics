from __future__ import annotations

import sys

import pandas as pd

from src import forecast, transform
from src.config import load_config
from src.extract import load_raw
from src.schema import COLLECTIONS


def main() -> int:
    cfg = load_config()
    if cfg.is_mongo:
        print(f"fonte: mongo | {cfg.safe_uri} | banco: {cfg.mongo_db}")
    else:
        print(f"fonte: seed | gerador sintetico, semente {cfg.seed}")

    try:
        raw = load_raw(cfg)
    except Exception as exc:
        print(f"\nNAO FOI POSSÍVEL LER:\n{exc}")
        return 1

    print("\n=== documentos por collection ===")
    for name in COLLECTIONS:
        print(f"  {name}: {len(raw.get(name, []))}")

    pedidos = raw.get("DiningTables", [])
    if pedidos:
        print("\n=== status dos pedidos ===")
        for k, v in pd.Series([p.get("status") for p in pedidos]).value_counts().items():
            print(f"  {k}: {v}")

    tables = transform.build_all(raw)
    sales, orders = tables["sales"], tables["orders"]
    print("\n=== depois do transform ===")
    print(f"  pedidos fechados: {len(orders)}")
    print(f"  itens vendidos:   {len(sales)}")
    if not sales.empty:
        ini, fim = sales["date"].min(), sales["date"].max()
        print(f"  período: {ini:%d/%m/%Y} a {fim:%d/%m/%Y} "
              f"({(fim - ini).days + 1} dias)")

    qual = tables["quality"]
    linhas = qual["sale_lines"]
    print("\n=== campos propostos ===")
    for campo, ausentes in qual["missing"].items():
        if not linhas:
            print(f"  {campo}: sem linha para medir")
        elif ausentes == 0:
            print(f"  {campo}: presente nas {linhas} linhas")
        elif ausentes == linhas:
            print(f"  {campo}: AUSENTE em todas -> análise indisponível")
        else:
            print(f"  {campo}: ausente em {ausentes} de {linhas}")

    print("\n=== qualidade ===")
    for chave in ("valid_pct", "lines_open_orders", "lines_item_not_in_menu",
                  "lines_without_date", "lines_canceled", "lines_late_entry"):
        print(f"  {chave}: {qual[chave]}")
    for chave in ("unknown_units", "recipes_with_orphan_ingredient",
                  "categories_inferred", "products_without_cost"):
        valor = qual[chave]
        print(f"  {chave}: {valor if valor else 'nenhum'}")

    print("\n=== previsão: histórico por produto ===")
    serie = forecast.daily_item_series(sales)
    if serie.empty:
        print("  sem série: nenhuma venda fechada")
    else:
        for nome, grupo in serie.groupby("item_name"):
            apto = "treina modelo" if len(grupo) >= forecast.MIN_DAYS else "cai no baseline"
            print(f"  {nome}: {len(grupo)} dias -> {apto}")
        print(f"  (mínimo para treinar: {forecast.MIN_DAYS} dias)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
