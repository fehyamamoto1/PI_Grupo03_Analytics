const mongoose = require('mongoose');

const IngredientsSchema = new mongoose.Schema({
  name: {
    type: String
  },
  quantity: {
    type: Number
  },
  measurementUnit: {
    type: String,
    enum: ['g', 'ml', 'un'],
    default: 'g'
  },
  alertLevel: {
    type: Number
  },
  // NOVO: custo por unidade BASE (R$/g, R$/ml, R$/un).
  // Destrava margem por produto, CMV e valor do estoque em reais.
  unitCost: {
    type: Number,
    required: false
  },
  // NOVO: validade em dias. Nao substitui controle de lote, mas permite
  // sinalizar insumo cujo estoque cobre mais dias do que a propria validade.
  shelfLifeDays: {
    type: Number,
    required: false
  }
}, {versionKey: false});

const Ingredients = mongoose.model('Ingredients', IngredientsSchema, 'Ingredients');

module.exports = Ingredients;
