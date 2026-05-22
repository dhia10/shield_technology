/**
 * Ange Gardien — Cart Manager
 * Persistent cart using localStorage
 */
const Cart = {
  STORAGE_KEY: 'ag_cart',
  COUPON_KEY: 'ag_coupon',
  SHIPPING_FEE: 15,
  FREE_SHIPPING_THRESHOLD: 500,

  getItems() {
    try { return JSON.parse(localStorage.getItem(this.STORAGE_KEY)) || []; }
    catch { return []; }
  },

  saveItems(items) {
    localStorage.setItem(this.STORAGE_KEY, JSON.stringify(items));
    this.updateCartCount();
  },

  addItem(product, quantity = 1, withInstallation = false) {
    const items = this.getItems();
    const key = `${product.id || product.slug}_${withInstallation}`;
    const existing = items.find(i => i.key === key);
    if (existing) {
      existing.quantity += quantity;
    } else {
      items.push({
        key,
        id: product.id || product.slug,
        slug: product.slug,
        name: product.name,
        nameAr: product.nameAr,
        price: product.price,
        thumbnail: product.thumbnail,
        withInstallation,
        installationPrice: withInstallation ? (product.installationPrice || 0) : 0,
        quantity,
        priceOnRequest: product.priceOnRequest || false,
        brand: product.brand
      });
    }
    this.saveItems(items);
    return items;
  },

  removeItem(key) {
    const items = this.getItems().filter(i => i.key !== key);
    this.saveItems(items);
    if (items.length === 0) this.clearCoupon();
    return items;
  },

  updateQuantity(key, quantity) {
    const items = this.getItems();
    const item = items.find(i => i.key === key);
    if (item) {
      if (quantity <= 0) return this.removeItem(key);
      item.quantity = quantity;
      this.saveItems(items);
    }
    return items;
  },

  clearCart() {
    localStorage.removeItem(this.STORAGE_KEY);
    this.clearCoupon();
    this.updateCartCount();
  },

  getSubtotal() {
    return this.getItems().reduce((sum, item) => {
      if (item.priceOnRequest) return sum;
      return sum + (item.price + item.installationPrice) * item.quantity;
    }, 0);
  },

  getCount() {
    return this.getItems().reduce((sum, item) => sum + item.quantity, 0);
  },

  // ── Coupon ──
  getCoupon() {
    try { return JSON.parse(localStorage.getItem(this.COUPON_KEY)); }
    catch { return null; }
  },

  saveCoupon(coupon) {
    localStorage.setItem(this.COUPON_KEY, JSON.stringify(coupon));
  },

  clearCoupon() {
    localStorage.removeItem(this.COUPON_KEY);
  },

  // ── Totals ──
  getTotals() {
    const subtotal = this.getSubtotal();
    const coupon = this.getCoupon();
    let discount = 0;
    let freeShipping = false;
    if (coupon) {
      discount = coupon.discountAmount || 0;
      freeShipping = coupon.freeShipping || false;
    }
    const afterDiscount = Math.max(0, subtotal - discount);
    const shipping = (freeShipping || afterDiscount >= this.FREE_SHIPPING_THRESHOLD) ? 0 : this.SHIPPING_FEE;
    const total = afterDiscount + shipping;
    return { subtotal, discount, freeShipping, shipping, total, coupon };
  },

  // ── UI ──
  updateCartCount() {
    const el = document.getElementById('cartCount');
    if (el) {
      const count = this.getCount();
      el.textContent = count;
      el.style.display = count > 0 ? 'flex' : 'none';
    }
  },

  // ── API coupon validation ──
  async validateCoupon(code) {
    const subtotal = this.getSubtotal();
    try {
      const resp = await fetch('/api/orders/validate-coupon', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...Auth.getAuthHeader() },
        body: JSON.stringify({ code, cartTotal: subtotal })
      });
      return await resp.json();
    } catch {
      // Offline fallback
      return this._validateCouponOffline(code, subtotal);
    }
  },

  _validateCouponOffline(code, cartTotal) {
    const coupons = {
      'BIENVENUE10': { type:'percentage', value:10, minCartAmount:0 },
      'LIVRAISONGRATUITE': { type:'free_shipping', value:0, minCartAmount:100 },
      'ANGE50': { type:'fixed', value:50, minCartAmount:500 },
      'FIDELITE15': { type:'percentage', value:15, minCartAmount:0, requiresPreviousOrder:true }
    };
    const coupon = coupons[code.toUpperCase()];
    if (!coupon) return { success:false, message:'Code promo invalide' };
    if (cartTotal < coupon.minCartAmount) return { success:false, message:`Montant minimum requis: ${coupon.minCartAmount} DT` };
    let discountAmount = 0, freeShipping = false;
    if (coupon.type === 'percentage') discountAmount = (cartTotal * coupon.value) / 100;
    else if (coupon.type === 'fixed') discountAmount = Math.min(coupon.value, cartTotal);
    else if (coupon.type === 'free_shipping') { freeShipping = true; discountAmount = 15; }
    return { success:true, coupon:{ code:code.toUpperCase(), type:coupon.type, value:coupon.value, discountAmount, freeShipping, description:`${coupon.type === 'percentage' ? '-'+coupon.value+'%' : coupon.type === 'fixed' ? '-'+coupon.value+' DT' : 'Livraison gratuite'}` } };
  }
};

// ── Auth Helper ──
const Auth = {
  TOKEN_KEY: 'ag_token',
  USER_KEY: 'ag_user',

  getToken() { return localStorage.getItem(this.TOKEN_KEY); },
  getUser() {
    try { return JSON.parse(localStorage.getItem(this.USER_KEY)); }
    catch { return null; }
  },
  isLoggedIn() { return !!this.getToken(); },
  save(token, user) {
    localStorage.setItem(this.TOKEN_KEY, token);
    localStorage.setItem(this.USER_KEY, JSON.stringify(user));
  },
  logout() {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.USER_KEY);
  },
  getAuthHeader() {
    const token = this.getToken();
    return token ? { 'Authorization': `Bearer ${token}` } : {};
  },

  async login(email, password) {
    try {
      const resp = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });
      return await resp.json();
    } catch { return { success:false, message:'Erreur réseau' }; }
  },

  async register(name, email, password, phone) {
    try {
      const resp = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, password, phone })
      });
      return await resp.json();
    } catch { return { success:false, message:'Erreur réseau' }; }
  }
};
