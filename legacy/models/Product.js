const mongoose = require('mongoose');

const productSchema = new mongoose.Schema({
  name: { type: String, required: true, trim: true },
  nameAr: { type: String, trim: true },
  slug: { type: String, required: true, unique: true, lowercase: true },
  category: {
    type: String,
    required: true,
    enum: ['alarmes', 'videosurveillance', 'incendie', 'controle-acces']
  },
  description: { type: String },
  descriptionAr: { type: String },
  price: { type: Number, default: 0 }, // 0 = sur devis
  priceOnRequest: { type: Boolean, default: false },
  installationPrice: { type: Number, default: 0 },
  brand: { type: String, trim: true },
  images: [{ type: String }], // Azure Blob URLs
  thumbnail: { type: String },
  stock: { type: Number, default: 0 },
  stockStatus: { type: String, enum: ['available', 'on_order', 'out_of_stock'], default: 'available' },
  features: [{ type: String }],
  featured: { type: Boolean, default: false },
  isActive: { type: Boolean, default: true },
  warranty: { type: String },
  sku: { type: String, unique: true },
  salesCount: { type: Number, default: 0 }
}, { timestamps: true });

productSchema.index({ category: 1, isActive: 1 });
productSchema.index({ featured: 1 });
productSchema.index({ name: 'text', description: 'text' });

module.exports = mongoose.model('Product', productSchema);
