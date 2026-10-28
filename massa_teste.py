from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta

from pymongo import MongoClient

from src.config import load_config

TAG = "massa-pi4"
INICIO = datetime(2025, 11, 1)
BASE_PEDIDOS_DIA = 11

PESO_SEMANA = [0.0, 0.45, 0.55, 0.75, 1.65, 2.00, 1.05]

CUSTO_VALIDADE = {
    "Hambúrguer Bovino": (0.042, 60),
    "Hambúrguer Vegetal": (0.055, 90),
    "Frango Empanado": (0.028, 90),
    "Bacon": (0.038, 30),
    "Calabresa": (0.026, 30),
    "Queijo Cheddar": (0.055, 45),
    "Queijo Prato": (0.048, 45),
    "Pão Brioche": (0.018, 7),
    "Pão Integral": (0.016, 7),
    "Ovo": (0.020, 21),
    "Alface": (0.012, 4),
    "Tomate": (0.009, 6),
    "Cebola Caramelizada": (0.022, 10),
    "Molho Especial": (0.015, 60),
    "Molho Barbecue": (0.018, 60),
    "Molho Verde": (0.016, 20),
    "Maionese": (0.011, 60),
    "Maionese Temperada": (0.013, 60),
}

NOVOS_INSUMOS = [
    ("Refrigerante Lata 350ml", "un", 2.80, 180, 240),
    ("Suco de Laranja Integral", "ml", 0.012, 15, 12000),
    ("Cerveja Long Neck", "un", 4.50, 180, 120),
    ("Água Mineral 500ml", "un", 1.20, 365, 150),
    ("Batata Congelada", "g", 0.014, 180, 25000),
    ("Óleo de Fritura", "ml", 0.009, 120, 9000),
    ("Nuggets de Frango", "g", 0.022, 180, 6000),
    ("Anel de Cebola Congelado", "g", 0.019, 180, 4500),
    ("Massa de Brownie", "g", 0.028, 90, 3000),
    ("Sorvete de Creme", "ml", 0.016, 120, 5000),
]

NOVOS_ITENS = [
    ("Refrigerante Lata", 7.00, "BEBIDA",
     [("Refrigerante Lata 350ml", 1, "un")]),
    ("Suco de Laranja 300ml", 11.00, "BEBIDA",
     [("Suco de Laranja Integral", 300, "ml")]),
    ("Cerveja Long Neck", 12.00, "BEBIDA",
     [("Cerveja Long Neck", 1, "un")]),
    ("Água Mineral", 5.00, "BEBIDA",
     [("Água Mineral 500ml", 1, "un")]),
    ("Batata Frita", 14.00, "ACOMPANHAMENTO",
     [("Batata Congelada", 180, "g"), ("Óleo de Fritura", 25, "ml")]),
    ("Batata Frita com Cheddar e Bacon", 22.00, "ACOMPANHAMENTO",
     [("Batata Congelada", 200, "g"), ("Óleo de Fritura", 25, "ml"),
      ("Queijo Cheddar", 40, "g"), ("Bacon", 30, "g")]),
    ("Nuggets 8 Unidades", 16.00, "ACOMPANHAMENTO",
     [("Nuggets de Frango", 160, "g"), ("Óleo de Fritura", 25, "ml")]),
    ("Onion Rings", 15.00, "ACOMPANHAMENTO",
     [("Anel de Cebola Congelado", 150, "g"), ("Óleo de Fritura", 25, "ml")]),
    ("Brownie com Sorvete", 16.00, "SOBREMESA",
     [("Massa de Brownie", 90, "g"), ("Sorvete de Creme", 80, "ml")]),
]

OPERADORES = [
    ("Ana", 2, 0.02),
    ("Bruno", 6, 0.10),
    ("Carla", 3, 0.04),
    ("Diego", 18, 0.34),
]

PESO_CANAL = [("MESA", 45), ("DELIVERY", 38), ("BALCAO", 17)]

FAIXA_MINUTOS = 30

FAIXA_PESO = {
    "MESA": [
        ((18, 0), 4), ((18, 30), 7), ((19, 0), 12), ((19, 30), 18),
        ((20, 0), 20), ((20, 30), 17), ((21, 0), 12), ((21, 30), 6),
        ((22, 0), 3), ((22, 30), 1),
    ],
    "BALCAO": [
        ((18, 0), 6), ((18, 30), 10), ((19, 0), 14), ((19, 30), 18),
        ((20, 0), 17), ((20, 30), 13), ((21, 0), 9), ((21, 30), 5),
        ((22, 0), 2), ((22, 30), 1),
    ],
    "DELIVERY": [
        ((18, 0), 3), ((18, 30), 6), ((19, 0), 11), ((19, 30), 17),
        ((20, 0), 21), ((20, 30), 18), ((21, 0), 13), ((21, 30), 7),
        ((22, 0), 3), ((22, 30), 1),
    ],
}

FECHADO = "fechado"
FERIADO = "feriado"
COMEMORATIVA = "comemorativa"

DATAS_ESPECIAIS = {
    (2025, 11, 2): ("Finados", FERIADO),
    (2025, 11, 15): ("Proclamação da República", FERIADO),
    (2025, 11, 20): ("Consciência Negra", FERIADO),
    (2025, 12, 24): ("Véspera de Natal", FECHADO),
    (2025, 12, 25): ("Natal", FECHADO),
    (2025, 12, 31): ("Véspera de Ano Novo", FERIADO),
    (2026, 1, 1): ("Confraternização Universal", FECHADO),
    (2026, 2, 16): ("Carnaval", FERIADO),
    (2026, 2, 17): ("Carnaval", FERIADO),
    (2026, 4, 3): ("Paixão de Cristo", FERIADO),
    (2026, 4, 5): ("Páscoa", COMEMORATIVA),
    (2026, 4, 21): ("Tiradentes", FERIADO),
    (2026, 5, 1): ("Dia do Trabalho", FERIADO),
    (2026, 5, 10): ("Dia das Mães", COMEMORATIVA),
    (2026, 6, 4): ("Corpus Christi", FERIADO),
    (2026, 6, 12): ("Dia dos Namorados", COMEMORATIVA),
    (2026, 8, 9): ("Dia dos Pais", COMEMORATIVA),
    (2026, 9, 7): ("Independência", FERIADO),
    (2026, 10, 12): ("Nossa Senhora Aparecida", FERIADO),
}

MULTIPLICADOR = {
    FERIADO: (2.0, 2.8),
    COMEMORATIVA: (1.4, 1.9),
}
MULTIPLICADOR_VESPERA = (1.35, 1.75)
MULTIPLICADOR_MAXIMO = 3.2

PESO_SEGUNDA_FERIADO = 0.75
PESO_SEGUNDA_VESPERA = 0.60
CHANCE_ABRE_SEGUNDA_FERIADO = 0.60
CHANCE_ABRE_SEGUNDA_VESPERA = 0.45

DURACAO = {"MESA": (38, 14), "BALCAO": (12, 5), "DELIVERY": (30, 10)}
PESO_PAGAMENTO = [("CREDITO", 34), ("PIX", 32), ("DEBITO", 22), ("DINHEIRO", 12)]
PESO_PLATAFORMA = [("PROPRIO", 45), ("IFOOD", 40), ("RAPPI", 15)]
OBSERVACOES = ["sem cebola", "sem tomate", "ponto bem passado", "maionese a parte",
               "sem alface", "cortar ao meio", "capricha no bacon"]


def chave(nome: str) -> str:
    import unicodedata
    texto = unicodedata.normalize("NFKD", str(nome or ""))
    return "".join(c for c in texto if not unicodedata.combining(c)).strip().lower()


def sorteia(pares):
    valores = [p[0] for p in pares]
    pesos = [p[1] for p in pares]
    return random.choices(valores, weights=pesos, k=1)[0]


class Plano:

    def __init__(self, db, aplicar: bool):
        self.db = db
        self.aplicar = aplicar
        self.contagem = {}

    def conta(self, acao: str, n: int = 1):
        self.contagem[acao] = self.contagem.get(acao, 0) + n

    def update_one(self, col, filtro, update, acao):
        if self.aplicar:
            self.db[col].update_one(filtro, update)
        self.conta(acao)

    def insert_many(self, col, docs, acao):
        if not docs:
            return []
        if self.aplicar:
            res = self.db[col].insert_many(docs)
            ids = [str(i) for i in res.inserted_ids]
        else:
            ids = [f"(novo-{col}-{i})" for i in range(len(docs))]
        self.conta(acao, len(docs))
        return ids

    def resumo(self):
        titulo = "ESCRITO" if self.aplicar else "SERIA ESCRITO (dry-run)"
        print(f"\n=== {titulo} ===")
        for acao, n in self.contagem.items():
            print(f"  {acao}: {n}")


def corrigir_vegetariano(db, plano: Plano) -> int:
    por_nome = {chave(i["name"]): str(i["_id"]) for i in db.Ingredients.find({})}
    corrigidos = 0
    for item in db.Menu.find({}):
        linhas = item.get("ingredients") or []
        novas, mudou = [], False
        for linha in linhas:
            iid = str(linha.get("ingredientId") or "")
            if iid in por_nome.values():
                novas.append(linha)
                continue
            alvo = por_nome.get(chave(iid.replace("-", " ")))
            if alvo:
                novas.append({**linha, "ingredientId": alvo})
                mudou = True
            else:
                novas.append(linha)
                print(f"    ATENÇÃO: {item['name']}: não achei insumo para {iid!r}")
        if mudou:
            plano.update_one("Menu", {"_id": item["_id"]},
                             {"$set": {"ingredients": novas}}, "Menu.ficha corrigida")
            corrigidos += 1
            print(f"    {item['name']}: ficha religada aos insumos reais")
    return corrigidos


def enriquecer_insumos(db, plano: Plano):
    tabela = {chave(k): v for k, v in CUSTO_VALIDADE.items()}
    for doc in db.Ingredients.find({}):
        if doc.get("seedTag") == TAG:
            continue
        valores = tabela.get(chave(doc["name"]))
        if not valores:
            print(f"    sem custo definido para {doc['name']!r}, deixando sem")
            continue
        custo, validade = valores
        plano.update_one(
            "Ingredients", {"_id": doc["_id"]},
            {"$set": {"unitCost": custo, "shelfLifeDays": validade,
                      "seedFields": True}},
            "Ingredients.custo+validade",
        )


def completar_cardapio(db, plano: Plano) -> dict:
    for item in db.Menu.find({}):
        if item.get("seedTag") == TAG:
            continue
        plano.update_one(
            "Menu", {"_id": item["_id"]},
            {"$set": {"category": "BURGER", "active": True, "seedFields": True}},
            "Menu.categoria+ativo",
        )

    existentes = {chave(i["name"]) for i in db.Ingredients.find({})}
    novos = [
        {"name": nome, "quantity": qtd, "measurementUnit": unidade,
         "alertLevel": round(qtd * 0.2), "unitCost": custo,
         "shelfLifeDays": validade, "seedTag": TAG}
        for nome, unidade, custo, validade, qtd in NOVOS_INSUMOS
        if chave(nome) not in existentes
    ]
    plano.insert_many("Ingredients", novos, "Ingredients.novos")

    por_nome = {chave(i["name"]): str(i["_id"]) for i in db.Ingredients.find({})}
    ja_no_menu = {chave(i["name"]) for i in db.Menu.find({})}

    itens = []
    for nome, preco, categoria, ficha in NOVOS_ITENS:
        if chave(nome) in ja_no_menu:
            continue
        linhas = []
        for insumo, qtd, unidade in ficha:
            iid = por_nome.get(chave(insumo))
            if not iid:
                if plano.aplicar:
                    print(f"    ATENÇÃO: {nome}: insumo {insumo!r} não cadastrado")
                continue
            linhas.append({"ingredientId": iid, "quantity": qtd,
                           "measurementUnit": unidade})
        itens.append({
            "name": nome, "value": preco, "category": categoria, "active": True,
            "description": f"{nome} - item de teste do PI IV",
            "imageUrl": "", "ingredients": linhas, "seedTag": TAG,
        })
    plano.insert_many("Menu", itens, "Menu.novos")
    return {}


def _escolhe_horario(canal: str, estende: bool = False) -> tuple:
    faixas = FAIXA_PESO[canal]
    if estende:
        faixas = [(inicio, peso + (4 if inicio >= (21, 30) else 0))
                  for inicio, peso in faixas]
    hora, minuto = sorteia(faixas)
    return hora, minuto + random.randint(0, FAIXA_MINUTOS - 1)


def _data_especial(dia) -> tuple:
    return DATAS_ESPECIAIS.get((dia.year, dia.month, dia.day), (None, None))


def _vespera_de_feriado(dia) -> bool:
    _, tipo = _data_especial(dia + timedelta(days=1))
    return tipo == FERIADO


def _expediente(dia) -> tuple:
    """Devolve (peso do dia, multiplicador, rotulo) ou (0, 0, None) se fechado."""
    nome, tipo = _data_especial(dia)
    if tipo == FECHADO:
        return 0.0, 0.0, nome

    vespera = _vespera_de_feriado(dia)
    peso = PESO_SEMANA[dia.weekday()]
    if peso == 0:
        if tipo == FERIADO and random.random() < CHANCE_ABRE_SEGUNDA_FERIADO:
            peso = PESO_SEGUNDA_FERIADO
        elif vespera and random.random() < CHANCE_ABRE_SEGUNDA_VESPERA:
            peso = PESO_SEGUNDA_VESPERA
        else:
            return 0.0, 0.0, nome

    multiplicador = 1.0
    if tipo in MULTIPLICADOR:
        multiplicador *= random.uniform(*MULTIPLICADOR[tipo])
    if vespera:
        multiplicador *= random.uniform(*MULTIPLICADOR_VESPERA)
    multiplicador = min(multiplicador, MULTIPLICADOR_MAXIMO)

    rotulo = nome if nome else ("véspera de feriado" if vespera else None)
    return peso, multiplicador, rotulo


def _composicao(canal: str, por_cat: dict) -> list:
    escolhidos = []
    burgers = por_cat.get("BURGER") or []
    bebidas = por_cat.get("BEBIDA") or []
    acomp = por_cat.get("ACOMPANHAMENTO") or []
    doces = por_cat.get("SOBREMESA") or []

    quantos = {"MESA": [35, 45, 20], "BALCAO": [70, 25, 5],
               "DELIVERY": [55, 35, 10]}[canal]
    n_burger = random.choices([1, 2, 3], weights=quantos, k=1)[0]
    for _ in range(n_burger):
        if burgers:
            escolhidos.append((random.choice(burgers), 1))

    pool_bebida = [b for b in bebidas
                   if canal != "DELIVERY" or "cerveja" not in chave(b["name"])]
    chance_bebida = {"MESA": 0.62, "BALCAO": 0.50, "DELIVERY": 0.45}[canal]
    if pool_bebida and random.random() < chance_bebida:
        escolhidos.append((random.choice(pool_bebida),
                           random.choices([1, 2], weights=[75, 25], k=1)[0]))

    chance_acomp = {"MESA": 0.52, "BALCAO": 0.33, "DELIVERY": 0.42}[canal]
    if acomp and random.random() < chance_acomp:
        escolhidos.append((random.choice(acomp), 1))

    chance_doce = {"MESA": 0.12, "BALCAO": 0.04, "DELIVERY": 0.06}[canal]
    if doces and random.random() < chance_doce:
        escolhidos.append((random.choice(doces), 1))

    return escolhidos


def _monta_itens(canal: str, por_cat: dict) -> tuple:
    itens, bruto = [], 0.0
    for item, qtd in _composicao(canal, por_cat):
        cancelado = random.random() < 0.02
        linha = {
            "itemId": str(item["_id"]),
            "itemName": item["name"],
            "quantity": qtd,
            "itemValue": float(item["value"]),
            "itemStatus": "CANCELADO" if cancelado else "OK",
        }
        if random.random() < 0.06:
            linha["notes"] = random.choice(OBSERVACOES)
        itens.append(linha)
        if not cancelado:
            bruto += qtd * float(item["value"])
    return itens, bruto


def gerar_pedidos(db, plano: Plano) -> int:
    menu = [m for m in db.Menu.find({}) if m.get("active", True)]
    if not menu:
        raise SystemExit("cardápio vazio")
    por_cat = {}
    for item in menu:
        por_cat.setdefault(item.get("category") or "BURGER", []).append(item)

    agora = datetime.now()
    hoje = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    total_dias = (hoje - INICIO).days
    lote, criados = [], 0

    for d in range(total_dias + 1):
        dia = INICIO + timedelta(days=d)
        peso, multiplicador, _ = _expediente(dia)
        if peso == 0:
            continue
        estende = multiplicador > 1.0
        crescimento = 0.75 + 0.40 * (d / max(total_dias, 1))
        quantos = round(BASE_PEDIDOS_DIA * peso * crescimento * multiplicador
                        * random.uniform(0.75, 1.25))

        for _ in range(max(quantos, 0)):
            canal = sorteia(PESO_CANAL)
            hora, minuto = _escolhe_horario(canal, estende)
            quando = dia.replace(hour=hora, minute=minuto,
                                 second=random.randint(0, 59))
            if quando > agora:
                continue

            operador, atraso_tipico, chance_lote = random.choice(OPERADORES)
            itens, bruto = _monta_itens(canal, por_cat)
            if not itens:
                continue

            desconto = (round(bruto * random.uniform(0.05, 0.15), 2)
                        if random.random() < 0.08 else 0.0)
            media, desvio = DURACAO[canal]
            duracao = max(5.0, random.gauss(media, desvio))

            if random.random() < chance_lote:
                fim = dia.replace(hour=23, minute=random.randint(0, 59))
                criado = max(fim, quando + timedelta(minutes=duracao))
            else:
                criado = quando + timedelta(
                    minutes=max(0.5, random.expovariate(1.0 / atraso_tipico)))

            pessoas = {
                "MESA": random.choices([1, 2, 3, 4, 5, 6],
                                       weights=[8, 34, 22, 20, 9, 7], k=1)[0],
                "BALCAO": random.choices([1, 2], weights=[70, 30], k=1)[0],
                "DELIVERY": 1,
            }[canal]

            lote.append({
                "diningTableId": random.randint(1, 12) if canal == "MESA" else 0,
                "status": "CLOSED",
                "itemList": itens,
                "totalValue": round(bruto - desconto, 2),
                "orderDate": quando,
                "closedAt": quando + timedelta(minutes=duracao),
                "createdAt": criado,
                "orderChannel": canal,
                "deliveryPlatform": (sorteia(PESO_PLATAFORMA)
                                     if canal == "DELIVERY" else "PROPRIO"),
                "paymentMethod": sorteia(PESO_PAGAMENTO),
                "partySize": pessoas,
                "operatorName": operador,
                "discountValue": desconto,
                "seedTag": TAG,
            })
            criados += 1

            if len(lote) >= 500:
                plano.insert_many("DiningTables", lote, "DiningTables.pedidos")
                lote = []

    for _ in range(2 if agora.hour >= 18 else 0):
        itens, bruto = _monta_itens("MESA", por_cat)
        if not itens:
            continue
        lote.append({
            "diningTableId": random.randint(1, 12),
            "status": "IN_USE",
            "itemList": itens,
            "totalValue": round(bruto, 2),
            "orderDate": agora - timedelta(minutes=random.randint(5, 40)),
            "createdAt": agora,
            "orderChannel": "MESA",
            "deliveryPlatform": "PROPRIO",
            "partySize": random.randint(2, 4),
            "operatorName": random.choice(OPERADORES)[0],
            "discountValue": 0.0,
            "seedTag": TAG,
        })
        criados += 1

    plano.insert_many("DiningTables", lote, "DiningTables.pedidos")
    return criados


def ajustar_estoque(db, plano: Plano):
    receita = {str(item["_id"]): item.get("ingredients") or []
               for item in db.Menu.find({})}

    corte = datetime.now() - timedelta(days=28)
    consumo = {}
    for pedido in db.DiningTables.find({"status": "CLOSED",
                                        "orderDate": {"$gte": corte}}):
        for linha in pedido.get("itemList") or []:
            if linha.get("itemStatus") == "CANCELADO":
                continue
            qtd = float(linha.get("quantity") or 0)
            for ing in receita.get(str(linha.get("itemId")), []):
                iid = str(ing.get("ingredientId"))
                consumo[iid] = (consumo.get(iid, 0.0)
                                + qtd * float(ing.get("quantity") or 0))

    coberturas = [3, 5, 8, 12, 20, 30]
    sem_consumo = []
    for pos, doc in enumerate(db.Ingredients.find({})):
        por_dia = consumo.get(str(doc["_id"]), 0.0) / 28.0
        if por_dia <= 0:
            sem_consumo.append(doc["name"])
            continue
        dias = coberturas[pos % len(coberturas)]
        alvo = {"$set": {
            "quantity": max(round(por_dia * dias), 1),
            "alertLevel": max(round(por_dia * 3), 1),
            "seedFields": True,
        }}
        if "seedBackup" not in doc and doc.get("seedTag") != TAG:
            alvo["$set"]["seedBackup"] = {
                "quantity": doc.get("quantity"),
                "alertLevel": doc.get("alertLevel"),
            }
        plano.update_one("Ingredients", {"_id": doc["_id"]}, alvo,
                         "Ingredients.saldo ajustado")
    if sem_consumo:
        print(f"    sem consumo nos 28 dias, saldo mantido: {sem_consumo}")


def limpar(db, plano: Plano):
    for col in ("DiningTables", "Menu", "Ingredients"):
        n = db[col].count_documents({"seedTag": TAG})
        if n and plano.aplicar:
            db[col].delete_many({"seedTag": TAG})
        if n:
            plano.conta(f"{col}.removidos", n)

    for doc in db.Ingredients.find({"seedFields": True}):
        backup = doc.get("seedBackup") or {}
        update = {"$unset": {"unitCost": "", "shelfLifeDays": "",
                             "seedFields": "", "seedBackup": ""}}
        if backup.get("quantity") is not None:
            update["$set"] = {"quantity": backup["quantity"],
                              "alertLevel": backup.get("alertLevel")}
        plano.update_one("Ingredients", {"_id": doc["_id"]}, update,
                         "Ingredients.revertidos")

    for doc in db.Menu.find({"seedFields": True}):
        plano.update_one(
            "Menu", {"_id": doc["_id"]},
            {"$unset": {"category": "", "active": "", "seedFields": ""}},
            "Menu.revertidos")

    print("\n  A ficha técnica do Vegetariano NÃO foi revertida: aquilo é")
    print("  conserto de bug, não massa de teste.")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Gera massa de teste no banco. Sem --aplicar, só mostra "
                    "o que faria.")
    ap.add_argument("--aplicar", action="store_true",
                    help="escreve de verdade (sem isso, só mostra o que faria)")
    ap.add_argument("--limpar", action="store_true",
                    help="remove a massa criada por este script")
    ap.add_argument("--semente", type=int, default=7,
                    help="semente do random, para repetir a mesma massa")
    args = ap.parse_args()

    cfg = load_config()
    if not cfg.is_mongo:
        print("Este script escreve no Mongo. Ponha DATA_SOURCE=mongo no .env.")
        return 1
    random.seed(args.semente)

    client = MongoClient(cfg.mongo_uri, serverSelectionTimeoutMS=20000)
    db = client[cfg.mongo_db]
    plano = Plano(db, args.aplicar)
    print(f"banco: {cfg.safe_uri} -> {cfg.mongo_db}")
    if not args.aplicar:
        print("MODO DRY-RUN: nada será escrito. Use --aplicar para valer.\n")

    try:
        if args.limpar:
            print("Removendo a massa de teste...")
            limpar(db, plano)
        else:
            print("1. corrigindo a ficha técnica quebrada")
            corrigir_vegetariano(db, plano)
            print("2. custo e validade dos insumos")
            enriquecer_insumos(db, plano)
            print("3. categoria, ativo, e os itens que faltam no cardápio")
            completar_cardapio(db, plano)
            print("4. gerando pedidos")
            criados = gerar_pedidos(db, plano)
            print(f"   {criados} pedidos")
            print("5. ajustando o saldo de estoque")
            if args.aplicar:
                ajustar_estoque(db, plano)
            else:
                print("   (precisa dos pedidos no banco; roda só com --aplicar)")
        plano.resumo()
    finally:
        client.close()

    if not args.aplicar and not args.limpar:
        print("\nNada foi escrito. Rode de novo com --aplicar.")
    else:
        print("\nAgora rode: python diagnostico.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
