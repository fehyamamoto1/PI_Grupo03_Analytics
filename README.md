# Painel Analítico da Hamburgueria — PI IV, Grupo 10

Front e back num projeto só. O Streamlit serve a interface e executa a consulta;
não há API separada para manter. Lê as collections do sistema do PI III e entrega
análise de vendas, previsão de demanda e sugestão de compras.

## Rodar

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt
copy .env.example .env            # Windows  (cp no Linux/Mac)
streamlit run app.py
```

Abre em `http://localhost:8501`.

Antes de abrir o painel, vale rodar o diagnóstico — ele diz o que realmente veio
do banco, e separa "o painel está vazio porque tem bug" de "está vazio porque o
campo ainda não existe":

```bash
python diagnostico.py
```

## As duas fontes de dados

`DATA_SOURCE` no `.env` decide de onde vêm os dados. O resto do código não sabe
a diferença — `extract.load_raw()` devolve a mesma forma nos dois casos.

| Valor | O que faz |
|---|---|
| `mongo` | Lê o Atlas de verdade. É o padrão. Exige `MONGO_URI` e `MONGO_PASSWORD`. |
| `seed` | Gera ~6 meses de pedidos sintéticos no schema exato do PI III. Reprodutível pela variável `SEED`. Serve para rodar com o cluster pausado. |

A string de conexão entra **colada do painel do Atlas, com o `<db_password>`
literal**; a senha vai separada em `MONGO_PASSWORD`:

```ini
DATA_SOURCE=mongo
MONGO_URI=mongodb+srv://23215784:<db_password>@cluster0.d47zfry.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0
MONGO_PASSWORD=
MONGO_DB=PrincipalDB
```

O código substitui o placeholder em tempo de execução e aplica `quote_plus` na
senha. Isso não é frescura: senha com `@` ou `/` entra crua e quebra o parse da
URI, com erro que não aponta para a causa.

Crie um usuário no Atlas com papel **`read` apenas**. O processo analítico nunca
escreve na base operacional, e o papel garante isso mesmo se alguém errar o código.
O IP da máquina precisa estar liberado em **Network Access**.

O `.env` está no `.gitignore`.

## Estrutura

```
app.py                 interface + orquestração (Streamlit)
diagnostico.py         relatorio do que existe na base real
src/config.py          leitura do ambiente + montagem da URI
src/schema.py          contrato das collections + unidades, canais, taxas
src/extract.py         leitura do Mongo (somente leitura)
src/seed.py            gerador sintético no mesmo formato
src/transform.py       documentos crus -> tabelas analíticas + relatório de qualidade
src/metrics.py         KPIs, canal, pagamento, margem, operador, plano de compras
src/forecast.py        previsão por produto + baseline sazonal + validação temporal
tests/test_pipeline.py 57 testes das regras que erram em silêncio
proposta_backend/      models Mongoose com os campos propostos, prontos para colar
```

## As seis abas

| Aba | Responde |
|---|---|
| Visão geral | Quanto vendi, por qual canal, em qual forma de pagamento, quanto sobrou de taxas |
| Quando vendo | Matriz dia × hora (filtrável por canal), faturamento diário, tempo de atendimento |
| O que vendo | Ranking com Pareto, mix por categoria, attach rate de bebida, margem por produto |
| O que comprar | Previsão com faixa de erro, plano de compras com custo, risco de sobra por validade |
| Consultar operações | Navegação pedido a pedido com filtros, detalhe item a item e export CSV |
| Qualidade do dado | Validade da base, disciplina de lançamento por operador, campos ausentes |

## Tabelas que o pipeline produz

| Tabela | Grão |
|---|---|
| `sales` | uma linha por item vendido, só de pedidos `CLOSED` |
| `orders` | uma linha por pedido — é o que a aba de consulta navega |
| `products` | produto com categoria, custo de ficha técnica e margem |
| `recipe` | ficha técnica achatada: um insumo por linha de produto |
| `consumption` | consumo de insumo por dia, derivado de venda × ficha técnica |
| `ingredients` | saldo atual por insumo, em unidade base, com custo |
| `quality` | contagens para a seção 2.4.10.1 do relatório |

## Campos propostos para o modelo

O pipeline já lê e usa campos que o banco ainda não tem. Todos entram com valor
padrão, então **o schema atual continua funcionando** — a análise que depende do
campo é que fica indisponível, e a aba *Qualidade do dado* diz quais faltam.

| Campo | Model | Destrava |
|---|---|---|
| `orderChannel` | DiningTables | Mesa / balcão / delivery: receita, ticket e horário por canal |
| `deliveryPlatform` | DiningTables | Receita líquida após comissão da plataforma |
| `closedAt` | DiningTables | Duração do atendimento e giro de mesa |
| `createdAt` | DiningTables | **Atraso de lançamento** contra `orderDate` |
| `paymentMethod` | DiningTables | Mix de pagamento e custo de adquirência |
| `partySize` | DiningTables | Ticket por pessoa |
| `operatorName` | DiningTables | Disciplina de lançamento por operador |
| `discountValue` | DiningTables | Receita bruta contra líquida de desconto |
| `itemStatus` | TableItem | Cancelamento; item cancelado não dá baixa de insumo |
| `notes` | TableItem | Observação que quebra a ficha técnica |
| `category` | Menu | Mix de cardápio sem adivinhar por nome |
| `active` | Menu | Produto fora de linha sai do plano de compras |
| `unitCost` | Ingredients | Margem por produto, CMV, valor do estoque |
| `shelfLifeDays` | Ingredients | Risco de sobra por validade |

O mais importante é `createdAt`. A justificativa do relatório é que lançamentos
atrasados distorcem os indicadores, mas hoje existe só `orderDate` — a distorção
é afirmação sem medida. Separando quando o pedido aconteceu de quando foi
digitado, a diferença **é** o indicador, por operador e por turno.

Os models Mongoose prontos e as mudanças de controller estão em
`proposta_backend/`. Nada foi aplicado no repositório do server.

## Duas decisões que valem explicar na banca

**A validação é temporal.** `forecast.py` usa `TimeSeriesSplit`, não
`train_test_split` aleatório. Embaralhar datas vaza o futuro no treino e produz
métrica boa que não se repete na operação.

**Todo modelo é comparado com um baseline sazonal** — a mediana do mesmo dia da
semana nas últimas 4 ocorrências. Quando o Random Forest não ganha do baseline, a
tela diz isso em vez de esconder. Com os dados sintéticos o baseline vence em
boa parte dos produtos, o que é um resultado honesto e esperado: 6 meses de
histórico é pouco para o modelo superar sazonalidade simples de dia da semana.
O placar da aba *O que comprar* mostra o resultado do dado que está carregado —
não vale citar um número fixo aqui, porque ele muda com a base.

## Conversão de unidades

`Ingredients` converte kg para g no cadastro, mas `Menu.ingredients[].measurementUnit`
é texto livre. Toda quantidade passa por `schema.normalize_unit()` antes de
qualquer conta. Unidade não reconhecida **não** é convertida em silêncio: a
quantidade passa intacta e a divergência aparece na aba *Qualidade do dado*, onde
dá para corrigir o cadastro ou acrescentar a unidade em `src/schema.py`.

## O que este projeto não calcula, e por quê

Quatro fontes citadas no relatório não existem no schema do PI III:

- **Movimentações de entrada** — a reposição sobrescreve a quantidade, sem registrar
- **Movimentações de saída** — a baixa é um incremento direto no insumo
- **Datas de validade** — não há campo de validade nem de lote em `Ingredients`
- **Histórico de compras** — a reposição não guarda data, quantidade nem preço

Enquanto isso continuar assim, previsão de vencimento de perecíveis não é
executável, nem o painel de divergência entre consumo esperado e registrado. A
aba *Qualidade do dado* repete esse aviso na tela, para não parecer que falta código.

## Testes

```bash
.venv\Scripts\python -m pytest tests -q
```

57 testes. Cobrem conversão de unidade, explosão do `itemList`, aplicação da
ficha técnica, exclusão de pedidos abertos, base vazia, limites do plano de
compras, comissão e taxa na receita líquida, cancelamento que não consome
insumo, custo incompleto que não vira margem falsa, montagem da URI com senha
escapada, e — o mais importante — que
**o schema legado, sem nenhum campo novo, continua rodando** e apenas reporta
os campos ausentes.
