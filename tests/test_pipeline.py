from datetime import datetime

import pandas as pd
import pytest

from src import config, extract, metrics
from src.schema import (
    CHANNEL_DELIVERY,
    CHANNELS,
    ITEM_CANCELED,
    ITEM_OK,
    STATUS_CLOSED,
    STATUS_IN_USE,
    infer_category,
    normalize_unit,
)
from src.seed import generate
from src.transform import build_all, build_sales, closed_only


def test_kg_vira_gramas():
    assert normalize_unit("kg", 1.5) == (1500.0, "g", True)


def test_litro_vira_mililitro():
    assert normalize_unit("L", 2) == (2000.0, "ml", True)


def test_unidade_desconhecida_nao_converte_e_sinaliza():
    qty, unit, known = normalize_unit("xicara", 3)
    assert (qty, known) == (3.0, False)
    assert unit == "xicara"


def test_unidade_vazia_nao_quebra():
    qty, unit, known = normalize_unit(None, 5)
    assert (qty, unit, known) == (5.0, "?", False)


def _raw_minimo():
    ing = {"_id": "i1", "name": "Pão", "quantity": 100.0,
           "measurementUnit": "un", "alertLevel": 10.0}
    menu = {"_id": "m1", "name": "Classico", "value": 30.0,
            "ingredients": [{"ingredientId": "i1", "quantity": 2, "measurementUnit": "un"}]}
    order = {
        "_id": "o1", "diningTableId": 3, "status": STATUS_CLOSED,
        "totalValue": 90.0, "orderDate": datetime(2026, 3, 14, 20, 30),
        "itemList": [
            {"itemId": "m1", "itemName": "Classico", "quantity": 2, "itemValue": 30.0},
            {"itemId": "m1", "itemName": "Classico", "quantity": 1, "itemValue": 30.0},
        ],
    }
    return {"DiningTables": [order], "Menu": [menu], "Ingredients": [ing]}


def test_um_pedido_com_dois_itens_vira_duas_linhas():
    sales = build_sales(_raw_minimo())
    assert len(sales) == 2
    assert sales["order_id"].nunique() == 1


def test_line_value_e_quantidade_vezes_valor_unitario():
    sales = build_sales(_raw_minimo())
    assert sales["line_value"].tolist() == [60.0, 30.0]


def test_hora_e_dia_da_semana_saem_do_order_date():
    sales = build_sales(_raw_minimo())
    assert sales["hour"].iloc[0] == 20
    assert sales["weekday"].iloc[0] == 5


def test_pedido_aberto_fica_fora_da_analise():
    raw = _raw_minimo()
    raw["DiningTables"][0]["status"] = STATUS_IN_USE
    assert build_sales(raw).shape[0] == 2
    assert closed_only(build_sales(raw)).empty


def test_consumo_aplica_a_ficha_tecnica():
    tables = build_all(_raw_minimo())
    consumo = tables["consumption"]
    assert len(consumo) == 1
    assert consumo["qty_base"].iloc[0] == pytest.approx(6.0)
    assert consumo["unit_base"].iloc[0] == "un"


def test_ficha_tecnica_em_kg_chega_em_gramas_no_consumo():
    raw = _raw_minimo()
    raw["Menu"][0]["ingredients"] = [
        {"ingredientId": "i1", "quantity": 0.15, "measurementUnit": "kg"}
    ]
    consumo = build_all(raw)["consumption"]
    assert consumo["qty_base"].iloc[0] == pytest.approx(450.0)


def test_item_fora_do_menu_entra_no_relatorio_de_qualidade():
    raw = _raw_minimo()
    raw["DiningTables"][0]["itemList"][0]["itemId"] = "nao-existe"
    q = build_all(raw)["quality"]
    assert q["lines_item_not_in_menu"] == 1
    assert q["valid_pct"] < 100


def test_base_vazia_nao_quebra():
    tables = build_all({"DiningTables": [], "Menu": [], "Ingredients": []})
    assert tables["sales"].empty
    assert tables["consumption"].empty
    assert tables["quality"]["valid_pct"] == 0.0


def test_kpis_somam_a_receita_da_janela():
    tables = build_all(_raw_minimo())
    k = metrics.kpis(tables["sales"], days=3650)
    assert k["revenue"] == pytest.approx(90.0)
    assert k["orders"] == 1
    assert k["ticket"] == pytest.approx(90.0)


def test_matriz_hora_dia_conta_pedidos_distintos_nao_linhas():
    grid = metrics.weekday_hour_matrix(build_all(_raw_minimo())["sales"])
    assert grid.loc["Sab", 20] == 1.0


def test_plano_de_compras_nunca_sugere_quantidade_negativa():
    tables = build_all(_raw_minimo())
    fc = pd.DataFrame([{"item_id": "m1", "item_name": "Classico",
                        "quantity": 1.0, "horizon_days": 7}])
    plan = metrics.purchase_plan(fc, tables["recipe"], tables["ingredients"])
    assert (plan["buy_base"] >= 0).all()
    assert plan["status"].iloc[0] == "suficiente"


def test_plano_de_compras_pede_reposicao_quando_falta():
    tables = build_all(_raw_minimo())
    fc = pd.DataFrame([{"item_id": "m1", "item_name": "Classico",
                        "quantity": 500.0, "horizon_days": 7}])
    plan = metrics.purchase_plan(fc, tables["recipe"], tables["ingredients"])
    assert plan["buy_base"].iloc[0] == pytest.approx(900.0)
    assert plan["status"].iloc[0] == "repor hoje"


def test_seed_e_reprodutivel():
    a = generate(days=40, seed=7)
    b = generate(days=40, seed=7)
    assert len(a["DiningTables"]) == len(b["DiningTables"])
    assert a["DiningTables"][0]["totalValue"] == b["DiningTables"][0]["totalValue"]


def test_seed_passa_pelo_pipeline_inteiro():
    tables = build_all(generate(days=120, seed=1))
    assert not tables["sales"].empty
    assert not tables["consumption"].empty
    assert tables["quality"]["valid_pct"] == 100.0
    assert tables["quality"]["unknown_units"] == []


def test_seed_nao_abre_na_segunda():
    sales = build_all(generate(days=120, seed=1))["sales"]
    assert 0 not in set(sales["weekday"].unique())


def test_seed_vende_mais_no_fim_de_semana():
    sales = build_all(generate(days=180, seed=1))["sales"]
    por_dia = sales.groupby("weekday")["order_id"].nunique()
    assert por_dia[5] > por_dia[1]


def _raw_legado():
    ing = {"_id": "i1", "name": "Pão", "quantity": 100.0,
           "measurementUnit": "un", "alertLevel": 10.0}
    menu = {"_id": "m1", "name": "Classico", "value": 30.0,
            "ingredients": [{"ingredientId": "i1", "quantity": 2,
                             "measurementUnit": "un"}]}
    order = {"_id": "o1", "diningTableId": 3, "status": STATUS_CLOSED,
             "totalValue": 60.0, "orderDate": datetime(2026, 3, 14, 20, 30),
             "itemList": [{"itemId": "m1", "itemName": "Classico",
                           "quantity": 2, "itemValue": 30.0}]}
    return {"DiningTables": [order], "Menu": [menu], "Ingredients": [ing]}


def test_banco_sem_os_campos_novos_continua_rodando():
    tables = build_all(_raw_legado())
    assert tables["sales"]["line_value"].sum() == pytest.approx(60.0)
    assert not tables["consumption"].empty


def test_campos_ausentes_entram_no_relatorio_de_qualidade():
    q = build_all(_raw_legado())["quality"]
    assert q["missing"]["orderChannel"] == 1
    assert q["missing"]["paymentMethod"] == 1
    assert q["missing"]["createdAt"] == 1
    assert q["lines_late_entry"] == 0


def test_sem_created_at_nao_ha_disciplina_de_operador():
    sales = build_all(_raw_legado())["sales"]
    assert metrics.operator_discipline(sales).empty


def test_categoria_e_inferida_quando_o_campo_nao_existe():
    tables = build_all(_raw_legado())
    assert tables["products"]["category_inferred"].all()
    assert tables["quality"]["categories_inferred"] == ["Classico"]


def test_categoria_do_banco_tem_prioridade_sobre_a_heuristica():
    raw = _raw_legado()
    raw["Menu"][0]["category"] = "SOBREMESA"
    products = build_all(raw)["products"]
    assert products["category"].iloc[0] == "SOBREMESA"
    assert not products["category_inferred"].iloc[0]


def test_infere_bebida_por_nome():
    assert infer_category("Refrigerante lata") == "BEBIDA"
    assert infer_category("Batata frita") == "ACOMPANHAMENTO"
    assert infer_category("Duplo Smash") == "BURGER"


def _raw_com_cancelado():
    raw = _raw_legado()
    raw["DiningTables"][0]["itemList"] = [
        {"itemId": "m1", "itemName": "Classico", "quantity": 2,
         "itemValue": 30.0, "itemStatus": ITEM_OK},
        {"itemId": "m1", "itemName": "Classico", "quantity": 1,
         "itemValue": 30.0, "itemStatus": ITEM_CANCELED},
    ]
    return raw


def test_item_cancelado_nao_gera_receita():
    sales = build_all(_raw_com_cancelado())["sales"]
    assert sales["line_value"].sum() == pytest.approx(60.0)
    assert sales["canceled_value"].sum() == pytest.approx(30.0)


def test_item_cancelado_nao_consome_insumo():
    consumo = build_all(_raw_com_cancelado())["consumption"]
    assert consumo["qty_base"].iloc[0] == pytest.approx(4.0)


def test_cancelado_aparece_na_qualidade():
    assert build_all(_raw_com_cancelado())["quality"]["lines_canceled"] == 1


def _raw_delivery(platform="IFOOD", payment="CREDITO"):
    raw = _raw_legado()
    raw["DiningTables"][0].update({
        "orderChannel": CHANNEL_DELIVERY,
        "deliveryPlatform": platform,
        "paymentMethod": payment,
        "closedAt": datetime(2026, 3, 14, 21, 10),
        "createdAt": datetime(2026, 3, 14, 20, 33),
        "operatorName": "Ana",
    })
    return raw


def test_comissao_e_taxa_descontam_da_receita_liquida():
    sales = build_all(_raw_delivery())["sales"]
    assert sales["fee_rate"].iloc[0] == pytest.approx(0.262)
    assert sales["net_value"].sum() == pytest.approx(60.0 * (1 - 0.262))


def test_plataforma_propria_nao_tem_comissao():
    sales = build_all(_raw_delivery(platform="PROPRIO", payment="PIX"))["sales"]
    assert sales["net_value"].sum() == pytest.approx(60.0)


def test_plataforma_desconhecida_nao_inventa_comissao():
    sales = build_all(_raw_delivery(platform="GOPUFF", payment="PIX"))["sales"]
    assert sales["net_value"].sum() == pytest.approx(60.0)


def test_duracao_e_atraso_saem_das_datas():
    sales = build_all(_raw_delivery())["sales"]
    assert sales["duration_min"].iloc[0] == pytest.approx(40.0)
    assert sales["entry_lag_min"].iloc[0] == pytest.approx(3.0)


def test_canal_entra_no_breakdown():
    sales = build_all(_raw_delivery())["sales"]
    canais = metrics.channel_breakdown(sales)
    assert canais["channel_label"].tolist() == ["Delivery"]
    assert canais["revenue"].iloc[0] == pytest.approx(60.0)


def test_plataforma_so_conta_pedido_de_delivery():
    plat = metrics.platform_breakdown(build_all(_raw_delivery())["sales"])
    assert plat["platform"].tolist() == ["IFOOD"]
    assert plat["commission_value"].iloc[0] == pytest.approx(60.0 * 0.23)
    assert metrics.platform_breakdown(build_all(_raw_legado())["sales"]).empty


def test_pix_no_canal_proprio_nao_tem_taxa_nem_comissao():
    raw = _raw_com_cancelado()
    raw["DiningTables"][0]["paymentMethod"] = "PIX"
    pay = metrics.payment_mix(build_all(raw)["sales"])
    linha = pay[pay["payment"] == "PIX"].iloc[0]
    assert linha["fee_value"] == pytest.approx(0.0)
    assert linha["commission_value"] == pytest.approx(0.0)


def test_pix_no_ifood_tem_comissao_mas_taxa_zero():
    pay = metrics.payment_mix(
        build_all(_raw_delivery(platform="IFOOD", payment="PIX"))["sales"]
    )
    linha = pay[pay["payment"] == "PIX"].iloc[0]
    assert linha["fee_value"] == pytest.approx(0.0)
    assert linha["commission_value"] == pytest.approx(60.0 * 0.23)


def test_dinheiro_no_ifood_tem_comissao_mas_taxa_zero():
    pay = metrics.payment_mix(
        build_all(_raw_delivery(platform="IFOOD", payment="DINHEIRO"))["sales"]
    )
    linha = pay[pay["payment"] == "DINHEIRO"].iloc[0]
    assert linha["fee_value"] == pytest.approx(0.0)
    assert linha["commission_value"] == pytest.approx(60.0 * 0.23)


def test_credito_no_canal_proprio_tem_taxa_mas_nao_comissao():
    raw = _raw_com_cancelado()
    raw["DiningTables"][0]["paymentMethod"] = "CREDITO"
    pay = metrics.payment_mix(build_all(raw)["sales"])
    linha = pay[pay["payment"] == "CREDITO"].iloc[0]
    assert linha["commission_value"] == pytest.approx(0.0)
    assert linha["fee_value"] == pytest.approx(linha["revenue"] * 0.032)


def test_comissao_mais_taxa_fecham_com_o_liquido():
    pay = metrics.payment_mix(
        build_all(_raw_delivery(platform="IFOOD", payment="CREDITO"))["sales"]
    )
    linha = pay.iloc[0]
    assert linha["revenue"] - linha["commission_value"] - linha["fee_value"] == (
        pytest.approx(linha["net_value"])
    )


def test_payment_mix_vazio_devolve_as_duas_colunas():
    pay = metrics.payment_mix(build_all(_raw_minimo())["sales"].iloc[0:0])
    assert "commission_value" in pay.columns
    assert "fee_value" in pay.columns


def test_desconto_do_pedido_nao_duplica_entre_itens():
    raw = _raw_com_cancelado()
    raw["DiningTables"][0]["discountValue"] = 10.0
    sales = build_all(raw)["sales"]
    assert sales["discount_share"].sum() == pytest.approx(10.0)


def _raw_com_custo():
    raw = _raw_legado()
    raw["Ingredients"][0]["unitCost"] = 1.50
    raw["Ingredients"][0]["shelfLifeDays"] = 5
    return raw


def test_custo_do_produto_vem_da_ficha_tecnica():
    products = build_all(_raw_com_custo())["products"]
    assert products["unit_cost"].iloc[0] == pytest.approx(3.0)
    assert products["margin_value"].iloc[0] == pytest.approx(27.0)
    assert products["margin_pct"].iloc[0] == pytest.approx(90.0)


def test_sem_unit_cost_a_margem_fica_vazia_em_vez_de_zero():
    products = build_all(_raw_legado())["products"]
    assert products["unit_cost"].isna().all()
    assert products["margin_value"].isna().all()


def test_insumo_sem_custo_derruba_o_custo_do_produto_inteiro():
    raw = _raw_com_custo()
    raw["Ingredients"].append({"_id": "i2", "name": "Queijo", "quantity": 500.0,
                               "measurementUnit": "g", "alertLevel": 100.0})
    raw["Menu"][0]["ingredients"].append(
        {"ingredientId": "i2", "quantity": 40, "measurementUnit": "g"}
    )
    products = build_all(raw)["products"]
    assert products["unit_cost"].isna().all()


def test_valor_do_estoque_usa_unidade_base():
    sv = metrics.stock_value(build_all(_raw_com_custo())["ingredients"])
    assert sv["total"] == pytest.approx(150.0)
    assert sv["unpriced"] == 0


def test_margem_por_produto_no_periodo():
    tables = build_all(_raw_com_custo())
    m = metrics.margin_ranking(tables["sales"], tables["products"])
    assert m["revenue"].iloc[0] == pytest.approx(60.0)
    assert m["cost"].iloc[0] == pytest.approx(6.0)
    assert m["margin_pct"].iloc[0] == pytest.approx(90.0)


def test_risco_de_validade_sinaliza_cobertura_maior_que_a_validade():
    tables = build_all(_raw_com_custo())
    usage = metrics.ingredient_usage(tables["consumption"], days=1)
    risco = metrics.expiry_risk(tables["ingredients"], usage)
    assert risco["coverage_days"].iloc[0] == pytest.approx(25.0)
    assert bool(risco["at_risk"].iloc[0])


def test_sem_shelf_life_nao_calcula_risco():
    tables = build_all(_raw_legado())
    usage = metrics.ingredient_usage(tables["consumption"], days=1)
    assert metrics.expiry_risk(tables["ingredients"], usage).empty


def test_orders_agrupa_uma_linha_por_pedido():
    orders = build_all(_raw_com_cancelado())["orders"]
    assert len(orders) == 1
    assert orders["items"].iloc[0] == 2
    assert orders["revenue"].iloc[0] == pytest.approx(60.0)
    assert orders["canceled_value"].iloc[0] == pytest.approx(30.0)


def test_orders_vem_do_mais_recente_para_o_mais_antigo():
    orders = build_all(generate(days=90, seed=3))["orders"]
    assert orders["order_date"].is_monotonic_decreasing


def test_seed_preenche_todos_os_campos_propostos():
    q = build_all(generate(days=90, seed=5))["quality"]
    assert q["missing"]["orderChannel"] == 0
    assert q["missing"]["paymentMethod"] == 0
    assert q["missing"]["createdAt"] == 0
    assert q["categories_inferred"] == []
    assert q["products_without_cost"] == []


def test_seed_cobre_os_tres_canais():
    sales = build_all(generate(days=90, seed=5))["sales"]
    assert set(sales["channel"].unique()) == set(CHANNELS)


def test_seed_nao_vende_cerveja_no_delivery():
    sales = build_all(generate(days=120, seed=5))["sales"]
    delivery = sales[sales["channel"] == CHANNEL_DELIVERY]
    assert "Cerveja" not in set(delivery["item_name"])


def test_seed_mesa_tem_ticket_maior_que_balcao():
    sales = build_all(generate(days=150, seed=5))["sales"]
    canais = metrics.channel_breakdown(sales).set_index("channel")
    assert canais.loc["MESA", "ticket"] > canais.loc["BALCAO", "ticket"]


def test_seed_produz_operador_indisciplinado_para_a_analise():
    sales = build_all(generate(days=150, seed=5))["sales"]
    disc = metrics.operator_discipline(sales)
    assert len(disc) == 4
    assert disc["late_pct"].max() > disc["late_pct"].min() + 10


def test_seed_mesa_demora_mais_que_balcao():
    sales = build_all(generate(days=120, seed=5))["sales"]
    dur = metrics.duration_stats(sales).set_index("channel")
    assert dur.loc["MESA", "median_min"] > dur.loc["BALCAO", "median_min"]


def test_senha_entra_no_lugar_do_placeholder():
    uri = "mongodb+srv://user:<db_password>@cluster0.abc.mongodb.net/"
    assert config._resolve_uri(uri, "segredo") == (
        "mongodb+srv://user:segredo@cluster0.abc.mongodb.net/"
    )


def test_senha_com_caractere_especial_e_escapada():
    uri = "mongodb+srv://user:<db_password>@cluster0.abc.mongodb.net/"
    montada = config._resolve_uri(uri, "p@ss/w0rd")
    assert "p%40ss%2Fw0rd" in montada
    assert montada.count("@") == 1


def test_uri_sem_placeholder_fica_intacta():
    uri = "mongodb+srv://user:jasenha@cluster0.abc.mongodb.net/"
    assert config._resolve_uri(uri, "outra") == uri


def test_placeholder_sem_senha_sobrevive_para_o_extract_avisar():
    uri = "mongodb+srv://user:<db_password>@cluster0.abc.mongodb.net/"
    assert config.PASSWORD_PLACEHOLDER in config._resolve_uri(uri, "")


def test_safe_uri_nao_mostra_a_senha():
    cfg = config.Config(
        data_source="mongo",
        mongo_uri="mongodb+srv://user:segredo@cluster0.abc.mongodb.net/",
        mongo_db="PrincipalDB",
        seed=42,
    )
    assert "segredo" not in cfg.safe_uri
    assert "user:***@" in cfg.safe_uri


def test_extract_recusa_uri_com_placeholder_antes_de_conectar():
    cfg = config.Config(
        data_source="mongo",
        mongo_uri="mongodb+srv://user:<db_password>@cluster0.abc.mongodb.net/",
        mongo_db="PrincipalDB",
        seed=42,
    )
    with pytest.raises(RuntimeError, match="placeholder"):
        extract.from_mongo(cfg)
