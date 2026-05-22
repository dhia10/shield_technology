const express = require('express');
const router = express.Router();
const Order = require('../models/Order');
const Coupon = require('../models/Coupon');
const User = require('../models/User');
const { protect, optionalAuth } = require('../middleware/auth');

// Validate coupon
router.post('/validate-coupon', optionalAuth, async (req, res) => {
  try {
    const { code, cartTotal } = req.body;
    if (!code) return res.status(400).json({ success: false, message: 'Code requis' });

    const coupon = await Coupon.findOne({ code: code.toUpperCase(), isActive: true });
    if (!coupon) return res.status(404).json({ success: false, message: 'Code promo invalide' });

    if (coupon.expiresAt && new Date() > coupon.expiresAt) {
      return res.status(400).json({ success: false, message: 'Code promo expiré' });
    }
    if (coupon.maxUses && coupon.usedCount >= coupon.maxUses) {
      return res.status(400).json({ success: false, message: 'Code promo épuisé' });
    }
    if (cartTotal < coupon.minCartAmount) {
      return res.status(400).json({
        success: false,
        message: `Montant minimum requis : ${coupon.minCartAmount} DT`
      });
    }

    // Check per-user limit
    if (req.user) {
      const userUsage = req.user.usedCoupons.filter(c => c === coupon.code).length;
      if (userUsage >= coupon.perUserLimit) {
        return res.status(400).json({ success: false, message: 'Vous avez déjà utilisé ce coupon' });
      }
      if (coupon.requiresPreviousOrder && req.user.totalOrders === 0) {
        return res.status(400).json({
          success: false,
          message: 'Ce coupon est réservé aux clients fidèles'
        });
      }
    }

    // Calculate discount
    let discountAmount = 0;
    let freeShipping = false;
    if (coupon.type === 'percentage') discountAmount = (cartTotal * coupon.value) / 100;
    else if (coupon.type === 'fixed') discountAmount = Math.min(coupon.value, cartTotal);
    else if (coupon.type === 'free_shipping') { freeShipping = true; discountAmount = 15; }

    res.json({
      success: true,
      coupon: {
        code: coupon.code,
        type: coupon.type,
        value: coupon.value,
        discountAmount: Math.round(discountAmount * 100) / 100,
        freeShipping,
        description: coupon.description
      }
    });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

// Create order
router.post('/', optionalAuth, async (req, res) => {
  try {
    const { customer, shippingAddress, items, subtotal, discount, couponCode, shippingFee, total, paymentMethod, notes } = req.body;

    // Calculate estimated delivery
    const region = shippingAddress.region || '';
    const isTunis = ['Tunis', 'tunis', 'TUNIS', 'Tunis 1', 'El Menzah'].some(r => region.includes(r));
    const estimatedDelivery = isTunis ? '24h' : '48-72h';

    const order = await Order.create({
      customer: { ...customer, userId: req.user?._id },
      shippingAddress,
      items,
      subtotal,
      discount,
      couponCode,
      shippingFee,
      total,
      paymentMethod,
      notes,
      estimatedDelivery,
      deliveryRegion: region,
      statusHistory: [{ status: 'pending', note: 'Commande reçue' }]
    });

    // Update coupon usage
    if (couponCode) {
      await Coupon.findOneAndUpdate(
        { code: couponCode.toUpperCase() },
        { $inc: { usedCount: 1 } }
      );
      if (req.user) {
        await User.findByIdAndUpdate(req.user._id, {
          $push: { usedCoupons: couponCode.toUpperCase() },
          $inc: { totalOrders: 1, totalSpent: total }
        });
      }
    } else if (req.user) {
      await User.findByIdAndUpdate(req.user._id, {
        $inc: { totalOrders: 1, totalSpent: total }
      });
    }

    res.status(201).json({ success: true, order });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

// Track order by number (public)
router.get('/track/:orderNumber', async (req, res) => {
  try {
    const order = await Order.findOne({ orderNumber: req.params.orderNumber })
      .select('orderNumber status statusHistory estimatedDelivery createdAt total customer.name shippingAddress.city');
    if (!order) return res.status(404).json({ success: false, message: 'Commande introuvable' });
    res.json({ success: true, order });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

// Get user's orders
router.get('/my-orders', protect, async (req, res) => {
  try {
    const orders = await Order.find({ 'customer.userId': req.user._id }).sort({ _id: -1 });
    res.json({ success: true, orders });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

module.exports = router;
