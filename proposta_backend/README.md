# Campos propostos para o backend

Os três `*-model.js` desta pasta são os models do PI III com os campos novos
marcados `// NOVO`. **Não apliquei nada no repositório do server** — copie
quando o grupo decidir.

Todos os campos têm `default` ou `required: false`, então documento antigo
continua válido e o pipeline analítico já lê os dois formatos. A ordem sugerida
é aplicar os models, criar a massa de teste nova, e deixar os pedidos antigos
como estão.

## O que cada campo destrava

| Campo | Model | Análise que passa a existir |
|---|---|---|
| `orderChannel` | DiningTables | Receita, ticket e mix por mesa / balcão / delivery. Perfil de horário muda bastante por canal. |
| `deliveryPlatform` | DiningTables | Receita líquida depois da comissão. É a diferença entre faturar e ganhar. |
| `closedAt` | DiningTables | Duração do atendimento, giro de mesa, pico de ocupação. |
| `createdAt` | DiningTables | **Atraso de lançamento** — ver abaixo. |
| `paymentMethod` | DiningTables | Mix de pagamento e custo de adquirência. |
| `partySize` | DiningTables | Ticket por pessoa, ocupação do salão. |
| `operatorName` | DiningTables | Disciplina de lançamento e cancelamento por operador. |
| `discountValue` | DiningTables | Receita bruta contra líquida de desconto. |
| `itemStatus` | TableItem | Cancelamento e desperdício. Item cancelado não dá baixa de insumo. |
| `notes` | TableItem | "sem cebola" quebra a ficha técnica; dá para medir o quanto. |
| `category` | Menu | Mix de cardápio e attach rate de bebida, sem adivinhar por nome. |
| `active` | Menu | Produto fora de linha sai do plano de compras e continua no histórico. |
| `unitCost` | Ingredients | Margem por produto, CMV, valor do estoque em reais. |
| `shelfLifeDays` | Ingredients | Sinaliza insumo cujo estoque cobre mais dias que a validade. |

## `createdAt` é o campo mais importante da lista

A justificativa do relatório inteiro é que os lançamentos são feitos com atraso
e em lote no fim do expediente, e que isso distorce os indicadores. Hoje existe
só `orderDate`, então essa distorção é uma afirmação sem medida.

Com `orderDate` (quando o pedido aconteceu) separado de `createdAt` (quando foi
digitado), a diferença entre os dois **é** o indicador. Dá para dizer quantos
por cento dos pedidos entram com mais de 30 minutos de atraso, por operador e
por turno. Vira número para a seção 2.4.10.1 e assunto concreto na validação com
a gestão.

Uma observação: `orderDate` precisa continuar sendo o horário do **pedido**, não
o do lançamento. Se o controller gravar `Date.now()` nos dois, o indicador nasce
zerado e a análise por hora continua errada sem ninguém perceber. Para pedido
lançado depois, a interface tem que deixar corrigir a hora.

## Mudanças necessárias nos controllers

### `diningtables-controller.js`

Em `create`, aceitar e gravar os campos do pedido:

```js
await DiningTable.create({
    diningTableId: req.params.id,
    itemList: itemList,
    orderDate: req.body.orderDate ?? Date.now(),   // hora do pedido
    createdAt: Date.now(),                          // hora do lançamento
    status: "IN_USE",
    totalValue: totalValue,
    orderChannel: req.body.orderChannel ?? "MESA",
    deliveryPlatform: req.body.deliveryPlatform,
    paymentMethod: req.body.paymentMethod,
    partySize: req.body.partySize ?? 0,
    operatorName: req.body.operatorName,
    discountValue: req.body.discountValue ?? 0
})
```

Em `close`, gravar o fechamento:

```js
await DiningTable.updateOne({_id: diningTable[0]._id}, {
    status: "CLOSED",
    closedAt: Date.now()
});
```

Na baixa de insumo, pular item cancelado — hoje o loop desconta tudo:

```js
for (const item of itemList){
    if (item.itemStatus === "CANCELADO") continue;
    // ... resto igual
}
```

### Dois bugs que vale corrigir na mesma passada

**`ObjectId` não importado** em `ingredients-controller.js` e
`menu-controller.js`. As chamadas caem no `catch` e devolvem 400. Na prática
`/repor/:id`, `/atualizarNivelAlerta/:id`, `/deletar/:id` e a edição de item do
menu nunca funcionaram. Falta a linha:

```js
const { ObjectId } = require('mongodb');
```

**Histórico de pedidos invisível na API.** `getAll` e `get` filtram
`status != "CLOSED"`, o que é correto para a tela de mesas, mas significa que
nenhum endpoint devolve pedido fechado. Hoje o pipeline lê direto do Mongo e
contorna. Se quiserem servir o histórico pela API, precisa de uma rota nova —
com paginação, porque a base cresce.

## O que ainda fica fora de alcance

Mesmo com tudo isso aplicado, três coisas continuam impossíveis porque dependem
de registro que não existe:

- **Movimentação de estoque** — a reposição sobrescreve a quantidade e a baixa é
  um `$inc` direto. Nenhuma das duas deixa histórico.
- **Histórico de compras** — a reposição não guarda data, quantidade nem preço.
- **Vencimento por lote** — `shelfLifeDays` estima risco de sobra, mas não diz
  qual lote vence primeiro.

As três saem com uma collection `StockMovements` (`ingredientId`, `type`
entrada/saída/ajuste/perda, `quantity`, `unitCost`, `lot`, `expiryDate`,
`occurredAt`, `createdAt`, `operatorName`) alimentada tanto pela venda quanto
pela reposição. É a mudança maior, e eu deixaria para uma segunda rodada — não é
necessária para o relatório parcial.
