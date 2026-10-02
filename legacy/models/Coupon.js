const mongoose = require('mongoose');

const couponSchema = new mongoose.Schema({
  code: { type: String, required: true, unique: true, uppercase: true, trim: true },
  type: {
    type: String,
    enum: ['percentage', 'fixed', 'free_shipping'],
    required: true
  },
  value: { type: Number, default: 0 }, // % or DT amount
  minCartAmount: { type: Number, default: 0 },
  maxUses: { type: Number, default: null }, // null = unlimited
  usedCount: { type: Number, default: 0 },
  perUserLimit: { type: Number, default: 1 }, // max times one user can use
  isActive: { type: Boolean, default: true },
  expiresAt: { type: Date },
  description: { type: String },
  descriptionAr: { type: String },
  requiresPreviousOrder: { type: Boolean, default: false } // for FIDELITE15
}, { timestamps: true });

module.exports = mongoose.model('Coupon', couponSchema);
