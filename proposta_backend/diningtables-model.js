const mongoose = require('mongoose');

const TableItem = new mongoose.Schema({
    itemId: {
        type: String
    },
    itemName: {
        type: String
    },
    quantity: {
        type: Number
    },
    itemValue: {
        type: Number
    },
    // NOVO: item cancelado nao gera receita e nao da baixa de insumo.
    itemStatus: {
        type: String,
        enum: ['OK', 'CANCELADO'],
        default: 'OK'
    },
    // NOVO: "sem cebola" quebra a ficha tecnica; registrar permite medir isso.
    notes: {
        type: String,
        default: ''
    }
}, { _id: false });

const DiningTableSchema = new mongoose.Schema({
  diningTableId: {
    type: Number
  },
  status: {
    type: String
  },
  itemList: {
    type: [TableItem]
  },
  totalValue: {
    type: Number
  },
  orderDate: {
    type: Date
  },
  // NOVO: canal de venda. Mesa, balcao ou delivery.
  orderChannel: {
    type: String,
    enum: ['MESA', 'BALCAO', 'DELIVERY'],
    default: 'MESA'
  },
  // NOVO: so quando orderChannel === 'DELIVERY'. A comissao muda a receita real.
  deliveryPlatform: {
    type: String,
    enum: ['PROPRIO', 'IFOOD', 'RAPPI'],
    required: false
  },
  // NOVO: preenchido no fechamento. Da duracao do atendimento e giro de mesa.
  closedAt: {
    type: Date,
    required: false
  },
  // NOVO: quando o registro foi digitado, nao quando o pedido aconteceu.
  // A diferenca contra orderDate e a inconsistencia de lancamento manual que
  // justifica o projeto. Sem este campo ela nao e mensuravel.
  createdAt: {
    type: Date,
    default: Date.now
  },
  paymentMethod: {
    type: String,
    enum: ['PIX', 'CREDITO', 'DEBITO', 'DINHEIRO'],
    required: false
  },
  // NOVO: pessoas na mesa. Permite ticket por pessoa e ocupacao do salao.
  partySize: {
    type: Number,
    default: 0
  },
  operatorName: {
    type: String,
    required: false
  },
  discountValue: {
    type: Number,
    default: 0
  }
},{versionKey: false});

const DiningTable = mongoose.model('DiningTables', DiningTableSchema, 'DiningTables');

module.exports = DiningTable;
