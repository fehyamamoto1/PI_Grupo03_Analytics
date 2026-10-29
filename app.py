from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import metrics
from src.config import load_config
from src.extract import load_raw
from src.forecast import daily_item_series, forecast_all, forecast_band
from src.schema import CHANNEL_LABEL
from src.transform import build_all

st.set_page_config(
    page_title="Hamburgueria - Painel Analítico",
    page_icon="*",
    layout="wide",
)

RAMP = ["#F6EEDF", "#E8D3A9", "#D4AC66", "#B8781F", "#8F540B"]
ACCENT = "#B8781F"
INK = "#4C534D"
CAT_COLORS = ["#B8781F", "#3D6B7D", "#7A5C2E", "#9E5B52"]

PLOT_BASE = dict(
    margin=dict(l=8, r=8, t=8, b=8),
    font=dict(color=INK),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
)


@st.cache_data(show_spinner="Lendo os dados...")
def load_tables(source: str, seed: int) -> dict:
    return build_all(load_raw(load_config()))


@st.cache_data(show_spinner="Treinando os modelos...")
def load_forecast(source: str, seed: int, horizon: int):
    tables = load_tables(source, seed)
    return forecast_all(tables["sales"], horizon)


def brl(value: float) -> str:
    if value is None or pd.isna(value):
        return "-"
    text = f"{value:,.2f}".replace(",", "~").replace(".", ",").replace("~", ".")
    return "R$ " + text


def qty(value: float, unit: str = "") -> str:
    if value is None or pd.isna(value):
        return "-"
    text = f"{value:,.0f}".replace(",", ".")
    return (text + " " + unit).strip()


def pct(value: float) -> str:
    return "-" if value is None or pd.isna(value) else f"{value:.1f}%"


def minutes(value: float) -> str:
    return "-" if value is None or pd.isna(value) else f"{value:.0f} min"


def channel_name(code: str) -> str:
    return CHANNEL_LABEL.get(code, str(code).title())


cfg = load_config()

with st.sidebar:
    st.subheader("Fonte dos dados")
    if cfg.is_mongo:
        st.success("Atlas - " + cfg.mongo_db)
    else:
        st.warning("Dados sinteticos")
        st.caption(
            "O schema é idêntico ao do PI III mais os campos propostos. Para ler "
            "o banco de verdade, preencha MONGO_URI no .env e troque "
            "DATA_SOURCE para mongo."
        )
    st.divider()
    period = st.select_slider("Período analisado", options=[7, 14, 28, 56, 90], value=28)
    horizon = st.select_slider("Horizonte da previsão", options=[7, 14], value=7)
    st.divider()
    if st.button("Recarregar dados", width="stretch"):
        st.cache_data.clear()
        st.rerun()

try:
    tables = load_tables(cfg.data_source, cfg.seed)
except Exception as exc:
    st.error("Não foi possível carregar os dados: " + str(exc))
    st.stop()

sales = tables["sales"]
products = tables["products"]

if sales.empty:
    st.title("Painel Analítico")
    st.warning(
        "Nenhuma venda fechada encontrada. Com DATA_SOURCE=mongo, confira se a "
        "collection DiningTables tem documentos com status CLOSED."
    )
    st.stop()

st.title("Painel Analítico da Hamburgueria")
st.caption(
    f"{sales['date'].min():%d/%m/%Y} a {sales['date'].max():%d/%m/%Y}"
    f"  -  {sales['order_id'].nunique()} pedidos fechados"
)

win = metrics.window(sales, period)

tabs = st.tabs([
    "Visão geral", "Quando vendo", "O que vendo", "O que comprar",
    "Consultar operações", "Qualidade do dado",
])

with tabs[0]:
    k = metrics.kpis(sales, period)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Faturamento", brl(k["revenue"]),
        f"{k['revenue_delta']:+.1f}%" if k["revenue_delta"] is not None else None,
    )
    c2.metric("Pedidos", qty(k["orders"]), f"{k['orders_per_day']:.1f} por dia",
              delta_color="off")
    c3.metric(
        "Ticket médio", brl(k["ticket"]),
        f"{k['ticket_delta']:+.1f}%" if k["ticket_delta"] is not None else None,
    )
    c4.metric("Itens vendidos", qty(k["items"]),
              f"{k['items_per_order']:.1f} por pedido", delta_color="off")

    d1, d2, d3 = st.columns(3)
    d1.metric("Receita líquida de taxas", brl(k["net_revenue"]),
              "-" + brl(k["fees"]) + " em taxas", delta_color="off")
    d2.metric("Cancelado", brl(k["canceled"]), delta_color="off")
    d3.metric("Descontos", brl(k["discount"]), delta_color="off")
    if not k["has_previous"]:
        st.caption("Sem período anterior completo para comparar.")

    st.divider()
    st.subheader("Por onde vendo")
    channels = metrics.channel_breakdown(win)
    if channels.empty:
        st.info("Sem canal registrado. O campo orderChannel ainda não existe no banco.")
    else:
        cols = st.columns(len(channels))
        for col, (_, row) in zip(cols, channels.iterrows()):
            col.metric(
                row["channel_label"], brl(row["revenue"]),
                f"{row['share']:.0f}% da receita", delta_color="off",
            )
        st.dataframe(
            channels.assign(
                revenue=channels["revenue"].map(brl),
                net_value=channels["net_value"].map(brl),
                ticket=channels["ticket"].map(brl),
                items_per_order=channels["items_per_order"].map(lambda v: f"{v:.2f}"),
                avg_duration=channels["avg_duration"].map(minutes),
                share=channels["share"].map(pct),
            )[["channel_label", "orders", "revenue", "net_value", "ticket",
               "items_per_order", "avg_duration", "share"]].rename(columns={
                "channel_label": "Canal", "orders": "Pedidos",
                "revenue": "Receita", "net_value": "Líquido",
                "ticket": "Ticket", "items_per_order": "Itens/pedido",
                "avg_duration": "Duração média", "share": "Participacao",
            }),
            width="stretch", hide_index=True,
        )

    platforms = metrics.platform_breakdown(win)
    if not platforms.empty:
        st.subheader("Delivery: quanto a plataforma leva")
        st.dataframe(
            platforms.assign(
                revenue=platforms["revenue"].map(brl),
                commission_pct=platforms["commission_pct"].map(lambda v: f"{v:.0f}%"),
                commission_value=platforms["commission_value"].map(brl),
                net_value=platforms["net_value"].map(brl),
            ).rename(columns={
                "platform": "Plataforma", "orders": "Pedidos", "revenue": "Bruto",
                "commission_pct": "Comissão", "commission_value": "Comissão R$",
                "net_value": "Líquido",
            }),
            width="stretch", hide_index=True,
        )
        st.caption(
            "A comissão sai de schema.PLATFORM_COMMISSION. Confira os percentuais "
            "com os contratos reais antes de usar numa decisão."
        )

    pay = metrics.payment_mix(win)
    if not pay.empty:
        st.subheader("Meios de pagamento")
        pie = go.Figure(go.Pie(
            labels=pay["payment"], values=pay["revenue"], hole=0.55,
            marker=dict(colors=CAT_COLORS[:len(pay)]),
            hovertemplate="%{label}<br>R$ %{value:,.2f}<extra></extra>",
        ))
        pie.update_layout(height=280, **PLOT_BASE)
        left, right = st.columns([1, 1])
        left.plotly_chart(pie, width="stretch")
        right.dataframe(
            pay.assign(
                revenue=pay["revenue"].map(brl),
                share=pay["share"].map(pct),
                commission_value=pay["commission_value"].map(brl),
                fee_value=pay["fee_value"].map(brl),
            )[["payment", "orders", "revenue", "share", "commission_value",
               "fee_value"]].rename(columns={
                "payment": "Meio", "orders": "Pedidos", "revenue": "Receita",
                "share": "Participação",
                "commission_value": "Comissão plataforma",
                "fee_value": "Taxa do meio",
            }),
            width="stretch", hide_index=True,
        )
        st.caption(
            "As duas retenções são separadas de propósito. Pix e dinheiro têm "
            "taxa zero: o que aparece em comissão são pedidos de delivery pagos "
            "por esses meios, e essa retenção é do app, não da maquininha. "
            "Desconto para Pix se paga com a coluna Taxa do meio, não com a "
            "coluna de comissão."
        )

with tabs[1]:
    st.subheader("Quando o movimento acontece")
    st.caption("Pedidos por dia da semana e hora. Sai só de orderDate, sem modelo.")

    opcoes = ["Todos os canais"] + [channel_name(c) for c in sorted(win["channel"].unique())]
    escolha = st.radio("Canal", opcoes, horizontal=True, key="hm_canal")
    base = win if escolha == "Todos os canais" else win[
        win["channel"].map(channel_name) == escolha
    ]

    grid = metrics.weekday_hour_matrix(base)
    if grid.empty:
        st.info("Sem dados no período.")
    else:
        heat = go.Figure(go.Heatmap(
            z=grid.values,
            x=[str(h) + "h" for h in grid.columns],
            y=list(grid.index),
            colorscale=[[i / (len(RAMP) - 1), c] for i, c in enumerate(RAMP)],
            texttemplate="%{z:.0f}",
            textfont={"size": 11},
            hovertemplate="%{y} %{x}<br>%{z:.0f} pedidos<extra></extra>",
            colorbar={"title": "pedidos"},
        ))
        heat.update_layout(height=330, yaxis=dict(autorange="reversed"), **PLOT_BASE)
        st.plotly_chart(heat, width="stretch")

        flat = grid.stack()
        st.info(
            f"Pico em {flat.idxmax()[0]} as {flat.idxmax()[1]}h, com "
            f"{flat.max():.0f} pedidos no período."
        )

    st.subheader("Faturamento por dia e canal")
    by_day = metrics.daily_revenue_by_channel(win)
    fig = go.Figure()
    for i, (name, part) in enumerate(by_day.groupby("channel_label")):
        fig.add_trace(go.Scatter(
            x=part["date"], y=part["revenue"], mode="lines", name=name,
            line=dict(color=CAT_COLORS[i % len(CAT_COLORS)], width=2),
            hovertemplate="%{x|%d/%m}<br>R$ %{y:,.2f}<extra></extra>",
        ))
    fig.update_layout(
        height=280, yaxis_title="R$",
        legend=dict(orientation="h", y=1.14, x=0), **PLOT_BASE,
    )
    st.plotly_chart(fig, width="stretch")

    dur = metrics.duration_stats(win)
    if dur.empty:
        st.info("Sem duração de atendimento. O campo closedAt ainda não existe.")
    else:
        st.subheader("Tempo de atendimento")
        st.dataframe(
            dur.assign(
                median_min=dur["median_min"].map(minutes),
                p90_min=dur["p90_min"].map(minutes),
            )[["channel_label", "orders", "median_min", "p90_min"]].rename(columns={
                "channel_label": "Canal", "orders": "Pedidos",
                "median_min": "Mediana", "p90_min": "90% em até",
            }),
            width="stretch", hide_index=True,
        )
        st.caption(
            "Mesa ocupada é mesa que não gira. Com partySize dá para estimar "
            "quantas pessoas por hora o salão atende."
        )

with tabs[2]:
    rank = metrics.product_ranking(win)
    st.subheader("Ranking de produtos")
    bar = go.Figure(go.Bar(
        x=rank["revenue"], y=rank["item_name"], orientation="h",
        marker_color=ACCENT,
        hovertemplate="%{y}<br>R$ %{x:,.2f}<extra></extra>",
    ))
    bar.update_layout(
        height=max(260, 42 * len(rank)), yaxis=dict(autorange="reversed"),
        xaxis_title="receita no período", **PLOT_BASE,
    )
    st.plotly_chart(bar, width="stretch")

    cat = metrics.category_mix(win, products)
    if not cat.empty:
        st.subheader("Mix por categoria")
        a, b = st.columns([1, 1])
        donut = go.Figure(go.Pie(
            labels=cat["category"], values=cat["revenue"], hole=0.55,
            marker=dict(colors=CAT_COLORS[:len(cat)]),
            hovertemplate="%{label}<br>R$ %{value:,.2f}<extra></extra>",
        ))
        donut.update_layout(height=280, **PLOT_BASE)
        a.plotly_chart(donut, width="stretch")
        b.metric("Pedidos que levam bebida", pct(metrics.attach_rate(win, products)))
        b.caption(
            "Attach rate de bebida. Sobe com sugestão no atendimento e é o "
            "indicador mais fácil de mover sem mexer em preço."
        )

    margin = metrics.margin_ranking(win, products)
    if margin.empty or margin["margin"].isna().all():
        st.info(
            "Sem margem calculada. Preencha unitCost nos insumos para que a "
            "ficha técnica produza custo por produto."
        )
    else:
        st.subheader("Margem por produto")
        st.dataframe(
            margin.assign(
                revenue=margin["revenue"].map(brl),
                cost=margin["cost"].map(brl),
                margin_value=margin["margin"].map(brl),
                margin_pct=margin["margin_pct"].map(pct),
                quantity=margin["quantity"].map(lambda v: qty(v)),
            )[["item_name", "category", "quantity", "revenue", "cost",
               "margin_value", "margin_pct"]].rename(columns={
                "item_name": "Produto", "category": "Categoria",
                "quantity": "Unidades", "revenue": "Receita", "cost": "Custo",
                "margin_value": "Margem", "margin_pct": "Margem %",
            }),
            width="stretch", hide_index=True,
        )
        st.caption(
            "Custo vem da ficha técnica x unitCost do insumo. Não inclui mao de "
            "obra, embalagem nem energia, então é margem de contribuição bruta."
        )

    st.subheader("Consumo de insumos derivado da ficha técnica")
    usage = metrics.ingredient_usage(tables["consumption"], period)
    if usage.empty:
        st.info("Sem consumo calculado no período.")
    else:
        st.dataframe(
            usage.assign(
                total_base=usage.apply(
                    lambda r: qty(r["total_base"], r["unit_base"]), axis=1),
                per_day=usage.apply(
                    lambda r: qty(r["per_day"], r["unit_base"]), axis=1),
            )[["ingredient_name", "total_base", "per_day"]].rename(columns={
                "ingredient_name": "Insumo",
                "total_base": f"Consumo em {period} dias",
                "per_day": "Média diária",
            }),
            width="stretch", hide_index=True,
        )

with tabs[3]:
    fc_daily, fc_total, scores = load_forecast(cfg.data_source, cfg.seed, horizon)

    st.subheader(f"Previsão de demanda - próximos {horizon} dias")
    series_all = daily_item_series(sales)
    chosen = st.selectbox("Produto", sorted(series_all["item_name"].unique()))

    hist = series_all[series_all["item_name"] == chosen].sort_values("date")
    fut = fc_daily[fc_daily["item_name"] == chosen].sort_values("date")
    band = forecast_band(hist, fut)
    tail = hist.tail(28)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(band["date"]) + list(band["date"])[::-1],
        y=list(band["high"]) + list(band["low"])[::-1],
        fill="toself", fillcolor="rgba(184,120,31,0.18)",
        line=dict(width=0), hoverinfo="skip", name="faixa de erro",
    ))
    fig.add_trace(go.Scatter(
        x=tail["date"], y=tail["quantity"], mode="lines", name="observado",
        line=dict(color=ACCENT, width=2),
        hovertemplate="%{x|%d/%m}<br>%{y:.0f} un<extra></extra>",
    ))
    bridge = pd.concat([tail.tail(1)[["date", "quantity"]], fut[["date", "quantity"]]])
    fig.add_trace(go.Scatter(
        x=bridge["date"], y=bridge["quantity"], mode="lines+markers", name="previsto",
        line=dict(color=ACCENT, width=2, dash="dash"),
        hovertemplate="%{x|%d/%m}<br>%{y:.0f} un previstos<extra></extra>",
    ))
    fig.update_layout(
        height=330, yaxis_title="unidades por dia",
        legend=dict(orientation="h", y=1.12, x=0), **PLOT_BASE,
    )
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "A faixa vem do desvio do histórico recente, não é intervalo de confiança "
        "estatístico. Está na tela para impedir compra por cima de número cravado."
    )

    st.subheader("Compras sugeridas")
    plan = metrics.purchase_plan(fc_total, tables["recipe"], tables["ingredients"])
    if plan.empty:
        st.info("Sem plano de compras: falta ficha técnica ou previsão.")
    else:
        total_buy = plan["buy_value"].sum(min_count=1)
        if pd.notna(total_buy) and total_buy > 0:
            st.metric("Compra estimada do período", brl(total_buy))
        st.dataframe(
            plan.assign(
                stock_base=plan.apply(
                    lambda r: qty(r["stock_base"], r["unit_base"]), axis=1),
                needed_base=plan.apply(
                    lambda r: qty(r["needed_base"], r["unit_base"]), axis=1),
                buy_base=plan.apply(
                    lambda r: qty(r["buy_base"], r["unit_base"]), axis=1),
                buy_value=plan["buy_value"].map(brl),
                coverage_days=plan["coverage_days"].map(
                    lambda v: "-" if v == float("inf") else f"{v:.1f} d"),
            )[["ingredient_name", "stock_base", "needed_base", "buy_base",
               "buy_value", "coverage_days", "status"]].rename(columns={
                "ingredient_name": "Insumo", "stock_base": "Estoque",
                "needed_base": f"Previsto {horizon} d", "buy_base": "Comprar",
                "buy_value": "Custo estimado", "coverage_days": "Cobertura",
                "status": "Situação",
            }),
            width="stretch", hide_index=True,
        )
        st.caption(
            "Estoque vem de Ingredients.quantity, que é o saldo atual e não tem "
            "histórico. Confira o saldo físico antes de comprar."
        )

    uso_periodo = metrics.ingredient_usage(tables["consumption"], period)
    risk = metrics.expiry_risk(tables["ingredients"], uso_periodo)
    if not risk.empty:
        st.subheader("Risco de sobra por validade")
        flagged = risk[risk["at_risk"]]
        if flagged.empty:
            st.success("Nenhum insumo com cobertura acima da validade declarada.")
        else:
            st.warning(
                f"{len(flagged)} insumos têm estoque para mais dias do que a "
                "própria validade. Tende a sobrar e vencer."
            )
        st.dataframe(
            risk.assign(
                stock_base=risk.apply(
                    lambda r: qty(r["stock_base"], r["unit_base"]), axis=1),
                per_day=risk.apply(
                    lambda r: qty(r["per_day"], r["unit_base"]), axis=1),
                coverage_days=risk["coverage_days"].map(lambda v: f"{v:.1f} d"),
                shelf_life_days=risk["shelf_life_days"].map(lambda v: f"{v:.0f} d"),
                at_risk=risk["at_risk"].map({True: "sim", False: "não"}),
            )[["ingredient_name", "stock_base", "per_day", "coverage_days",
               "shelf_life_days", "at_risk"]].rename(columns={
                "ingredient_name": "Insumo", "stock_base": "Estoque",
                "per_day": "Consumo/dia", "coverage_days": "Cobertura",
                "shelf_life_days": "Validade", "at_risk": "Risco",
            }),
            width="stretch", hide_index=True,
        )
        st.caption(
            "Aproximação por cobertura, não controle de lote. Vencimento de "
            "verdade exige lote e data de recebimento, que o schema não tem."
        )

    st.subheader("Modelo contra baseline sazonal")
    if scores.empty:
        st.info(
            "Histórico insuficiente para validação temporal. A previsão acima "
            "está usando o baseline da mediana do mesmo dia da semana."
        )
    else:
        st.dataframe(
            scores[["item_name", "n_days", "folds", "baseline_mae", "model_mae",
                    "model_rmse", "gain_pct", "winner"]].rename(columns={
                "item_name": "Produto", "n_days": "Dias", "folds": "Folds",
                "baseline_mae": "MAE baseline", "model_mae": "MAE modelo",
                "model_rmse": "RMSE modelo", "gain_pct": "Ganho %",
                "winner": "Vence",
            }),
            width="stretch", hide_index=True,
        )
        lost = scores[scores["winner"] == "baseline"]["item_name"].tolist()
        if lost:
            st.warning(
                "O baseline ganhou do modelo em: " + ", ".join(lost)
                + ". Para esses produtos, usar a mediana do mesmo dia da semana "
                "é mais honesto do que usar o Random Forest."
            )

with tabs[4]:
    st.subheader("Consultar operações")
    st.caption(
        "Navegação sobre os pedidos. Filtre, inspecione um pedido item a item "
        "e exporte o recorte."
    )

    orders = tables["orders"]
    f1, f2, f3 = st.columns(3)
    dmin, dmax = sales["date"].min().date(), sales["date"].max().date()
    faixa = f1.date_input("Período", (dmin, dmax), min_value=dmin, max_value=dmax)
    canais = f2.multiselect(
        "Canal", sorted(orders["channel"].unique()),
        format_func=channel_name, placeholder="Todos",
    )
    pagamentos = f3.multiselect(
        "Pagamento", sorted(orders["payment"].unique()), placeholder="Todos"
    )

    g1, g2, g3 = st.columns(3)
    operadores = g1.multiselect(
        "Operador", sorted(orders["operator"].unique()), placeholder="Todos"
    )
    produtos = g2.multiselect(
        "Contem o produto", sorted(sales["item_name"].dropna().unique()),
        placeholder="Qualquer",
    )
    minimo = g3.number_input("Valor mínimo do pedido", min_value=0.0, step=10.0, value=0.0)

    view = orders.copy()
    if isinstance(faixa, (tuple, list)) and len(faixa) == 2:
        ini, fim = pd.Timestamp(faixa[0]), pd.Timestamp(faixa[1]) + pd.Timedelta(days=1)
        view = view[(view["order_date"] >= ini) & (view["order_date"] < fim)]
    if canais:
        view = view[view["channel"].isin(canais)]
    if pagamentos:
        view = view[view["payment"].isin(pagamentos)]
    if operadores:
        view = view[view["operator"].isin(operadores)]
    if produtos:
        ids = sales.loc[sales["item_name"].isin(produtos), "order_id"].unique()
        view = view[view["order_id"].isin(ids)]
    if minimo > 0:
        view = view[view["revenue"] >= minimo]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Pedidos no filtro", qty(len(view)))
    m2.metric("Receita", brl(view["revenue"].sum()))
    m3.metric("Ticket médio", brl(view["revenue"].mean() if len(view) else 0))
    m4.metric("Cancelado", brl(view["canceled_value"].sum()))

    if view.empty:
        st.info("Nenhum pedido atende a esse filtro.")
    else:
        st.dataframe(
            view.assign(
                order_date=view["order_date"].dt.strftime("%d/%m/%Y %H:%M"),
                channel=view["channel"].map(channel_name),
                revenue=view["revenue"].map(brl),
                net_value=view["net_value"].map(brl),
                duration_min=view["duration_min"].map(minutes),
                entry_lag_min=view["entry_lag_min"].map(minutes),
                dining_table_id=view["dining_table_id"].map(
                    lambda v: "-" if not v else str(int(v))),
            )[["order_date", "channel", "platform", "payment", "operator",
               "dining_table_id", "items", "revenue", "net_value",
               "duration_min", "entry_lag_min"]].rename(columns={
                "order_date": "Data", "channel": "Canal", "platform": "Plataforma",
                "payment": "Pagamento", "operator": "Operador",
                "dining_table_id": "Mesa", "items": "Itens", "revenue": "Receita",
                "net_value": "Líquido", "duration_min": "Duração",
                "entry_lag_min": "Atraso no lancamento",
            }),
            width="stretch", hide_index=True, height=360,
        )

        st.download_button(
            "Baixar este recorte em CSV",
            view.to_csv(index=False).encode("utf-8-sig"),
            file_name="pedidos.csv", mime="text/csv",
        )

        st.divider()
        st.subheader("Detalhe do pedido")
        rotulos = {
            f"{row.order_date:%d/%m %H:%M} - {channel_name(row.channel)} - "
            f"{brl(row.revenue)}": row.order_id
            for row in view.head(300).itertuples()
        }
        rotulo = st.selectbox("Pedido", list(rotulos))
        oid = rotulos[rotulo]
        head = view[view["order_id"] == oid].iloc[0]

        h1, h2, h3, h4 = st.columns(4)
        h1.metric("Canal", channel_name(head["channel"]))
        h2.metric("Pagamento", head["payment"])
        h3.metric("Operador", head["operator"])
        h4.metric("Pessoas", qty(head["party_size"]) if head["party_size"] else "-")

        itens = sales[sales["order_id"] == oid]
        st.dataframe(
            itens.assign(
                quantity=itens["quantity"].map(lambda v: qty(v)),
                unit_value=itens["unit_value"].map(brl),
                line_value=itens["line_value"].map(brl),
                is_canceled=itens["is_canceled"].map({True: "cancelado", False: ""}),
            )[["item_name", "quantity", "unit_value", "line_value",
               "is_canceled", "notes"]].rename(columns={
                "item_name": "Produto", "quantity": "Qtd",
                "unit_value": "Valor unit.", "line_value": "Total",
                "is_canceled": "Status", "notes": "Observacao",
            }),
            width="stretch", hide_index=True,
        )
        st.caption("ID do pedido: " + str(oid))

with tabs[5]:
    q = tables["quality"]
    st.subheader("Qualidade da base analítica")
    st.caption("Alimenta direto a seção 2.4.10.1 do relatório.")

    a, b, c = st.columns(3)
    a.metric("Linhas de venda", qty(q["sale_lines"]))
    b.metric("Linhas validas", f"{q['valid_pct']:.2f}%")
    c.metric(
        "Meta do relatório", "95,00%",
        "atingida" if q["valid_pct"] >= 95 else "abaixo",
        delta_color="normal" if q["valid_pct"] >= 95 else "inverse",
    )

    st.dataframe(
        pd.DataFrame([
            ("Pedidos lidos", q["orders"]),
            ("Produtos no menu", q["menu_items"]),
            ("Insumos cadastrados", q["ingredients"]),
            ("Linhas de pedidos abertos (excluídas)", q["lines_open_orders"]),
            ("Linhas com item fora do menu", q["lines_item_not_in_menu"]),
            ("Linhas sem data", q["lines_without_date"]),
            ("Linhas com quantidade não positiva", q["lines_non_positive_qty"]),
            ("Itens cancelados", q["lines_canceled"]),
            ("Lancamentos com mais de 30 min de atraso", q["lines_late_entry"]),
        ], columns=["Verificacao", "Registros"]),
        width="stretch", hide_index=True,
    )

    disc = metrics.operator_discipline(win)
    if disc.empty:
        st.info(
            "Sem medicao de atraso de lancamento. Exige o campo createdAt, que "
            "guarda quando o registro foi digitado."
        )
    else:
        st.subheader("Disciplina de lancamento por operador")
        st.caption(
            "A diferença entre orderDate (quando o pedido aconteceu) e createdAt "
            "(quando foi digitado). É a inconsistência que o relatório descreve "
            "na seção 2.4.1, agora medida."
        )
        st.dataframe(
            disc.assign(
                median_lag_min=disc["median_lag_min"].map(minutes),
                p90_lag_min=disc["p90_lag_min"].map(minutes),
                late_pct=disc["late_pct"].map(pct),
                cancel_pct=disc["cancel_pct"].map(pct),
            )[["operator", "orders", "median_lag_min", "p90_lag_min",
               "late_pct", "cancel_pct"]].rename(columns={
                "operator": "Operador", "orders": "Pedidos",
                "median_lag_min": "Atraso mediano", "p90_lag_min": "90% em até",
                "late_pct": "Acima de 30 min", "cancel_pct": "Cancelamento",
            }),
            width="stretch", hide_index=True,
        )
        pior = disc.iloc[0]
        if pior["late_pct"] and pior["late_pct"] > 15:
            st.warning(
                f"{pior['operator']} lanca {pior['late_pct']:.0f}% dos pedidos com "
                "mais de 30 min de atraso. Indicador por hora desse turno fica "
                "distorcido, e é um achado para a validação com a gestão."
            )

    sv = metrics.stock_value(tables["ingredients"])
    st.subheader("Estoque")
    s1, s2, s3 = st.columns(3)
    s1.metric("Valor em estoque", brl(sv["total"]))
    s2.metric("Insumos sem custo", qty(sv["unpriced"]))
    s3.metric("Abaixo do nível de alerta", qty(sv["below_alert"]))

    st.divider()
    st.subheader("Campos propostos ainda ausentes no banco")
    faltando = {k: v for k, v in q["missing"].items() if v}
    if not faltando:
        st.success("Todos os campos propostos estao preenchidos nos dados lidos.")
    else:
        st.dataframe(
            pd.DataFrame(
                [(k, v) for k, v in faltando.items()],
                columns=["Campo", "Linhas sem o campo"],
            ),
            width="stretch", hide_index=True,
        )
        st.caption(
            "O pipeline roda com o campo ausente, mas a análise que depende dele "
            "fica indisponível. O schema proposto está em proposta_backend/."
        )

    if q["unknown_units"]:
        st.error(
            "Unidades não reconhecidas na ficha técnica: "
            + ", ".join(map(str, q["unknown_units"]))
            + ". A quantidade passou sem conversão. Corrija em Menu.ingredients "
            "ou adicione a unidade em src/schema.py."
        )
    else:
        st.success("Todas as unidades da ficha técnica foram convertidas.")

    if q["categories_inferred"]:
        st.warning(
            "Categoria inferida pelo nome em: "
            + ", ".join(map(str, q["categories_inferred"]))
            + ". Preencha Menu.category para não depender da heurística."
        )
    if q["products_without_cost"]:
        st.warning(
            "Produtos sem custo completo: "
            + ", ".join(map(str, q["products_without_cost"]))
            + ". Falta unitCost em algum insumo da ficha técnica."
        )
    if q["recipes_with_orphan_ingredient"]:
        st.error(
            "Produtos com insumo inexistente na ficha técnica: "
            + ", ".join(map(str, q["recipes_with_orphan_ingredient"]))
        )

    st.divider()
    st.subheader("O que continua fora de alcance")
    st.markdown(
        "Mesmo com os campos propostos, estas analises seguem impossiveis "
        "porque dependem de registro que não existe:\n\n"
        "- **Movimentação de estoque** - a reposição sobrescreve a quantidade e "
        "a baixa é um incremento direto; nenhuma das duas deixa histórico\n"
        "- **Histórico de compras** - a reposição não guarda data, quantidade "
        "nem preço pago\n"
        "- **Vencimento por lote** - `shelfLifeDays` permite estimar risco de "
        "sobra, mas não dizer qual lote vence primeiro\n"
        "- **Divergência consumo esperado x registrado** - precisa do movimento "
        "de saída para comparar com a ficha técnica\n\n"
        "As três primeiras saem com uma collection `StockMovements` e um campo "
        "de lote. A quarta vem de graça depois disso."
    )
