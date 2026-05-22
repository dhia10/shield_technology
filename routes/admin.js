const express = require('express');
const router = express.Router();
const multer = require('multer');
const Product = require('../models/Product');
const Order = require('../models/Order');
const User = require('../models/User');
const Coupon = require('../models/Coupon');
const { protect, adminOnly, superAdminOnly } = require('../middleware/auth');
const { uploadBuffer, deleteBlob } = require('../config/azureStorage');

const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 5 * 1024 * 1024 } });

// All admin routes require auth + admin role
router.use(protect, adminOnly);

// ─── DASHBOARD STATS ───────────────────────────────────────────────────────────
router.get('/dashboard', async (req, res) => {
  try {
    const [totalOrders, totalProducts, totalUsers, totalCoupons] = await Promise.all([
      Order.countDocuments(),
      Product.countDocuments({ isActive: true }),
      User.countDocuments({ role: 'customer' }),
      Coupon.countDocuments({ isActive: true })
    ]);

    const revenueAgg = await Order.aggregate([
      { $match: { status: { $nin: ['cancelled'] } } },
      { $group: { _id: null, total: { $sum: '$total' } } }
    ]);
    const totalRevenue = revenueAgg[0]?.total || 0;

    const recentOrders = await Order.find().sort({ _id: -1 }).limit(10);
    const ordersByStatus = await Order.aggregate([
      { $group: { _id: '$status', count: { $sum: 1 } } }
    ]);

    const monthlyRevenue = await Order.aggregate([
      { $match: { status: { $nin: ['cancelled'] } } },
      {
        $group: {
          _id: { year: { $year: '$createdAt' }, month: { $month: '$createdAt' } },
          revenue: { $sum: '$total' },
          orders: { $sum: 1 }
        }
      },
      { $sort: { '_id.year': -1, '_id.month': -1 } },
      { $limit: 12 }
    ]);

    res.json({ success: true, stats: {
      totalOrders, totalProducts, totalUsers, totalCoupons, totalRevenue,
      recentOrders, ordersByStatus, monthlyRevenue
    }});
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

// ─── PRODUCTS CRUD ─────────────────────────────────────────────────────────────
router.get('/products', async (req, res) => {
  try {
    const products = await Product.find().sort({ _id: -1 });
    res.json({ success: true, products });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

router.post('/products', upload.array('images', 5), async (req, res) => {
  try {
    const data = { ...req.body };
    if (typeof data.features === 'string') data.features = JSON.parse(data.features || '[]');
    data.priceOnRequest = data.priceOnRequest === 'true';
    data.featured = data.featured === 'true';
    if (!data.slug) data.slug = data.name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '');
    if (!data.sku) data.sku = 'SKU-' + Date.now();

    const imageUrls = [];
    if (req.files && req.files.length > 0) {
      for (const file of req.files) {
        const url = await uploadBuffer(file.buffer, file.originalname, file.mimetype);
        imageUrls.push(url);
      }
    }
    if (imageUrls.length > 0) {
      data.images = imageUrls;
      data.thumbnail = imageUrls[0];
    }

    const product = await Product.create(data);
    res.status(201).json({ success: true, product });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

router.put('/products/:id', upload.array('images', 5), async (req, res) => {
  try {
    const data = { ...req.body };
    if (typeof data.features === 'string') data.features = JSON.parse(data.features || '[]');
    data.priceOnRequest = data.priceOnRequest === 'true';
    data.featured = data.featured === 'true';

    const imageUrls = [];
    if (req.files && req.files.length > 0) {
      for (const file of req.files) {
        const url = await uploadBuffer(file.buffer, file.originalname, file.mimetype);
        imageUrls.push(url);
      }
      data.images = imageUrls;
      data.thumbnail = imageUrls[0];
    }

    const product = await Product.findByIdAndUpdate(req.params.id, data, { new: true });
    if (!product) return res.status(404).json({ success: false, message: 'Produit introuvable' });
    res.json({ success: true, product });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

router.delete('/products/:id', async (req, res) => {
  try {
    const product = await Product.findById(req.params.id);
    if (!product) return res.status(404).json({ success: false, message: 'Produit introuvable' });
    for (const imgUrl of product.images || []) await deleteBlob(imgUrl);
    await product.deleteOne();
    res.json({ success: true, message: 'Produit supprimé' });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

// ─── ORDERS CRUD ───────────────────────────────────────────────────────────────
router.get('/orders', async (req, res) => {
  try {
    const filter = {};
    if (req.query.status) filter.status = req.query.status;
    const orders = await Order.find(filter).sort({ _id: -1 }).limit(200);
    res.json({ success: true, orders });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

router.get('/orders/:id', async (req, res) => {
  try {
    const order = await Order.findById(req.params.id);
    if (!order) return res.status(404).json({ success: false, message: 'Commande introuvable' });
    res.json({ success: true, order });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

router.put('/orders/:id/status', async (req, res) => {
  try {
    const { status, note } = req.body;
    const order = await Order.findById(req.params.id);
    if (!order) return res.status(404).json({ success: false, message: 'Commande introuvable' });
    order.status = status;
    order.statusHistory.push({ status, note: note || '', date: new Date() });
    await order.save();
    res.json({ success: true, order });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

// ─── USERS ─────────────────────────────────────────────────────────────────────
router.get('/users', async (req, res) => {
  try {
    const users = await User.find().sort({ _id: -1 });
    res.json({ success: true, users });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

// Create admin (superadmin only)
router.post('/users/admin', superAdminOnly, async (req, res) => {
  try {
    const { name, email, password } = req.body;
    const existing = await User.findOne({ email });
    if (existing) return res.status(409).json({ success: false, message: 'Email déjà utilisé' });
    const user = await User.create({ name, email, password, role: 'admin' });
    res.status(201).json({ success: true, user });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

router.put('/users/:id/toggle', superAdminOnly, async (req, res) => {
  try {
    const user = await User.findById(req.params.id);
    if (!user) return res.status(404).json({ success: false, message: 'Utilisateur introuvable' });
    user.isActive = !user.isActive;
    await user.save();
    res.json({ success: true, user });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

// ─── COUPONS ───────────────────────────────────────────────────────────────────
router.get('/coupons', async (req, res) => {
  try {
    const coupons = await Coupon.find().sort({ _id: -1 });
    res.json({ success: true, coupons });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

router.post('/coupons', async (req, res) => {
  try {
    const coupon = await Coupon.create(req.body);
    res.status(201).json({ success: true, coupon });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

router.put('/coupons/:id', async (req, res) => {
  try {
    const coupon = await Coupon.findByIdAndUpdate(req.params.id, req.body, { new: true });
    if (!coupon) return res.status(404).json({ success: false, message: 'Coupon introuvable' });
    res.json({ success: true, coupon });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

router.delete('/coupons/:id', superAdminOnly, async (req, res) => {
  try {
    await Coupon.findByIdAndDelete(req.params.id);
    res.json({ success: true, message: 'Coupon supprimé' });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

module.exports = router;
