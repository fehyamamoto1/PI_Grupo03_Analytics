const mongoose = require('mongoose');

const IngredientsSchema = new mongoose.Schema ({
    ingredientId: {
        type: String
    },
    quantity: {
        type: Number
    },
    measurementUnit: {
        type: String,
        // NOVO: fecha a unidade. Hoje e texto livre, e "kg" em um produto com
        // "g" no insumo produz erro de mil vezes na baixa de estoque.
        enum: ['g', 'kg', 'ml', 'l', 'un'],
        default: 'g'
    }
}, { _id: false });


const MenuSchema = new mongoose.Schema({
  name: {
    type: String
  },
  imageUrl: {
    type: String
  },
  description: {
    type: String
  },
  value: {
    type: Number
  },
  // NOVO: categoria. Sem ela o mix de cardapio precisa ser adivinhado por nome.
  category: {
    type: String,
    enum: ['BURGER', 'ACOMPANHAMENTO', 'BEBIDA', 'SOBREMESA'],
    default: 'BURGER'
  },
  // NOVO: produto fora de linha sai do ranking e do plano de compras, mas
  // continua no historico de vendas.
  active: {
    type: Boolean,
    default: true
  },
  ingredients: {
    type: [IngredientsSchema],
  }
}, {versionKey: false});

const Menu = mongoose.model('Menu', MenuSchema, 'Menu');

module.exports = Menu;
