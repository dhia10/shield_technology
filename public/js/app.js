/**
 * Shield Technology — Main Application
 */

// ── State ──
let currentLang = 'fr';
let currentPage = 'home';
let allProducts = [...PRODUCTS_DATA];
let filteredProducts = [...PRODUCTS_DATA];
let activeCategory = 'all';
let activeStockFilter = 'all';
let selectedPayment = 'cash_on_delivery';
let searchQuery = '';

// ── Init ──
document.addEventListener('DOMContentLoaded', () => {
  Cart.updateCartCount();
  updateUserBtn();
  loadProducts();
  window.addEventListener('scroll', onScroll);
  // Restore last page from hash
  const hash = location.hash.replace('#', '');
  if (hash) showPage(hash);
  else showPage('home');
});

// ── Language Toggle ──
function toggleLang() {
  currentLang = currentLang === 'fr' ? 'ar' : 'fr';
  document.documentElement.lang = currentLang;
  document.documentElement.dir = currentLang === 'ar' ? 'rtl' : 'ltr';
  document.getElementById('langBtn').textContent = currentLang === 'fr' ? '🌐 عربي' : '🌐 Français';
  applyTranslations();
}

function applyTranslations() {
  document.querySelectorAll('[data-fr], [data-ar]').forEach(el => {
    const text = el.getAttribute(`data-${currentLang}`);
    if (text) {
      if (el.tagName === 'INPUT') el.placeholder = text;
      else el.innerHTML = text;
    }
  });
  // Re-render product grids
  if (currentPage === 'home') renderProductGrid('featuredProducts', allProducts.filter(p => p.featured));
  if (currentPage === 'shop') renderShop();
}

// ── Page Navigation ──
function showPage(page) {
  document.querySelectorAll('[id^="page-"]').forEach(el => el.classList.add('hidden'));
  const target = document.getElementById(`page-${page}`);
  if (target) target.classList.remove('hidden');
  currentPage = page;
  location.hash = page;
  window.scrollTo({ top: 0, behavior: 'smooth' });

  // Update active nav link
  document.querySelectorAll('.nav__link').forEach(l => l.classList.remove('active'));

  // Page-specific init
  if (page === 'home') {
    renderProductGrid('featuredProducts', allProducts.filter(p => p.featured));
  } else if (page === 'shop') {
    renderShop();
  } else if (page === 'cart') {
    renderCart();
  } else if (page === 'checkout') {
    renderCheckoutSummary();
    prefillCheckout();
  }
}

function filterShop(category) {
  activeCategory = category;
  showPage('shop');
  updateFilterOptions(category);
}

function filterByStock(stock) {
  activeStockFilter = stock;
  renderShop();
}

function updateFilterOptions(category) {
  document.querySelectorAll('.filter-option').forEach(opt => {
    opt.classList.remove('active');
    const text = opt.getAttribute('data-fr') || opt.textContent;
    if (category === 'all' && (text.includes('Toutes') || text.includes('tout'))) opt.classList.add('active');
    if (text.toLowerCase().includes(category) || opt.onclick?.toString().includes(`'${category}'`)) {
      if (category !== 'all') opt.classList.add('active');
    }
  });
}

// ── Scroll ──
function onScroll() {
  const header = document.getElementById('header');
  if (window.scrollY > 50) header.classList.add('header--scrolled');
  else header.classList.remove('header--scrolled');
}

// ── Mobile Menu ──
function toggleMobileMenu() {
  document.getElementById('mobileMenu').classList.toggle('open');
}
function closeMobileMenu() {
  document.getElementById('mobileMenu').classList.remove('open');
}

// ── Load Products ──
async function loadProducts() {
  try {
    const resp = await fetch('/api/products');
    const data = await resp.json();
    if (data.success && data.products.length > 0) {
      allProducts = data.products.map(p => ({
        ...p, id: p._id || p.slug
      }));
      filteredProducts = [...allProducts];
    }
  } catch { /* Use static data */ }
  renderProductGrid('featuredProducts', allProducts.filter(p => p.featured));
}

// ── Render Product Card ──
function renderProductCard(p) {
  const name = currentLang === 'ar' && p.nameAr ? p.nameAr : p.name;
  const stockBadge = p.stockStatus === 'available'
    ? '<span class="badge badge--green">✓ En stock</span>'
    : '<span class="badge badge--orange">⏳ Sur commande</span>';

  const priceBlock = p.priceOnRequest
    ? `<div class="product-card__price"><span style="font-size:0.95rem;">Prix sur demande</span></div>`
    : `<div class="product-card__price">${p.price.toFixed(2)} <span class="product-card__price-label">DT TTC</span></div>`;

  const addBtn = p.priceOnRequest
    ? `<button class="btn btn--secondary" onclick="showPage('contact')" style="flex:1">Demander un devis</button>`
    : `<button class="btn btn--primary" onclick="addToCart('${p.slug || p.id}')">🛒 Ajouter</button>`;

  const installCheck = !p.priceOnRequest && p.installationPrice > 0
    ? `<div class="product-install"><input type="checkbox" id="inst-${p.id}" onchange=""> <label for="inst-${p.id}">Installation (+${p.installationPrice} DT)</label></div>`
    : '';

  return `
    <div class="product-card">
      <div class="product-card__img" onclick="showProduct('${p.slug || p.id}')">
        <img src="${p.thumbnail}" alt="${name}" loading="lazy" onerror="this.src='https://via.placeholder.com/400x300/1a3272/ffffff?text=${encodeURIComponent(p.brand||'AG')}'" />
        <div class="product-card__badge">${stockBadge}</div>
      </div>
      <div class="product-card__body">
        <div class="product-card__brand">${p.brand || ''}</div>
        <div class="product-card__name" onclick="showProduct('${p.slug || p.id}')" style="cursor:pointer">${name}</div>
        ${priceBlock}
        ${installCheck}
        <div class="product-card__actions">
          ${addBtn}
          <button class="btn btn--outline btn--sm" onclick="showProduct('${p.slug || p.id}')">Détails</button>
        </div>
      </div>
    </div>`;
}

function renderProductGrid(containerId, products) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (products.length === 0) {
    el.innerHTML = `<div class="empty-state" style="grid-column:1/-1"><div class="empty-state__icon">🔍</div><div class="empty-state__title">Aucun produit trouvé</div></div>`;
    return;
  }
  el.innerHTML = products.map(renderProductCard).join('');
}

// ── Shop ──
function renderShop() {
  let products = [...allProducts];
  if (activeCategory !== 'all') products = products.filter(p => p.category === activeCategory);
  if (activeStockFilter !== 'all') products = products.filter(p => p.stockStatus === activeStockFilter);
  if (searchQuery) {
    const q = searchQuery.toLowerCase();
    products = products.filter(p => p.name.toLowerCase().includes(q) || (p.brand||'').toLowerCase().includes(q) || (p.description||'').toLowerCase().includes(q));
  }
  filteredProducts = products;
  const count = document.getElementById('shopResultCount');
  if (count) count.textContent = `${products.length} produit${products.length !== 1 ? 's' : ''} trouvé${products.length !== 1 ? 's' : ''}`;
  renderProductGrid('shopGrid', products);
}

function searchProducts(query) {
  searchQuery = query;
  renderShop();
}

// ── Product Detail ──
function showProduct(slug) {
  const p = allProducts.find(pr => pr.slug === slug || pr.id === slug);
  if (!p) return;
  const name = currentLang === 'ar' && p.nameAr ? p.nameAr : p.name;
  const desc = currentLang === 'ar' && p.descriptionAr ? p.descriptionAr : (p.description || '');

  document.getElementById('productBreadcrumb').textContent = name;

  const priceBlock = p.priceOnRequest
    ? `<div class="product-detail__price" style="font-size:1.5rem;">Prix sur demande</div>`
    : `<div class="product-detail__price">${p.price.toFixed(2)} DT TTC</div>`;

  const installBlock = !p.priceOnRequest && p.installationPrice > 0 ? `
    <div class="product-install" style="margin-bottom:20px; font-size:0.95rem;">
      <input type="checkbox" id="detInst" />
      <label for="detInst">Installation professionnelle possible (+${p.installationPrice} DT)</label>
    </div>` : '';

  const ctaBtn = p.priceOnRequest
    ? `<button class="btn btn--primary" onclick="showPage('contact')">📋 Demander un devis</button>`
    : `<button class="btn btn--primary" onclick="addToCartFromDetail('${slug}')">🛒 Ajouter au panier</button>`;

  const features = (p.features || []).map(f => `<li>${f}</li>`).join('');

  document.getElementById('productDetail').innerHTML = `
    <div class="product-detail__gallery">
      <img src="${p.thumbnail}" alt="${name}" onerror="this.src='https://via.placeholder.com/600x400/1a3272/ffffff?text=${encodeURIComponent(p.brand||'AG')}'" />
    </div>
    <div>
      <div class="product-detail__brand">${p.brand || ''}</div>
      <h1 class="product-detail__name">${name}</h1>
      <div style="margin-bottom:12px;">${p.stockStatus === 'available' ? '<span class="badge badge--green">✓ En stock</span>' : '<span class="badge badge--orange">⏳ Sur commande</span>'}</div>
      ${priceBlock}
      <p class="product-detail__description">${desc}</p>
      ${features ? `<ul class="features-list" style="margin-bottom:24px;">${features}</ul>` : ''}
      ${p.warranty ? `<div style="font-size:0.9rem;color:var(--text-muted);margin-bottom:16px;">🏅 Garantie : ${p.warranty}</div>` : ''}
      ${installBlock}
      <div style="display:flex;gap:12px;flex-wrap:wrap;">
        ${ctaBtn}
        <button class="btn btn--outline" onclick="showPage('shop')">← Retour boutique</button>
      </div>
    </div>`;

  showPage('product');
}

function addToCartFromDetail(slug) {
  const p = allProducts.find(pr => pr.slug === slug || pr.id === slug);
  if (!p) return;
  const withInst = document.getElementById('detInst')?.checked || false;
  Cart.addItem(p, 1, withInst);
  showToast(`✅ ${p.name} ajouté au panier`, 'success');
}

// ── Cart ──
function addToCart(slug) {
  const p = allProducts.find(pr => pr.slug === slug || pr.id === slug);
  if (!p) return;
  const instEl = document.getElementById(`inst-${p.id}`);
  const withInst = instEl?.checked || false;
  Cart.addItem(p, 1, withInst);
  showToast(`✅ ${p.name} ajouté au panier`, 'success');
}

function renderCart() {
  const items = Cart.getItems();
  const el = document.getElementById('cartContent');
  if (!el) return;

  if (items.length === 0) {
    el.innerHTML = `<div class="empty-state"><div class="empty-state__icon">🛒</div><div class="empty-state__title">Votre panier est vide</div><div class="empty-state__text">Ajoutez des produits depuis notre boutique</div><button class="btn btn--primary" onclick="showPage('shop')">🛍️ Continuer les achats</button></div>`;
    return;
  }

  const { subtotal, discount, shipping, total, coupon } = Cart.getTotals();

  const itemsHtml = items.map(item => `
    <div class="cart-item">
      <img class="cart-item__img" src="${item.thumbnail}" alt="${item.name}" onerror="this.src='https://via.placeholder.com/80x80/1a3272/ffffff?text=AG'" />
      <div>
        <div class="cart-item__name">${currentLang === 'ar' && item.nameAr ? item.nameAr : item.name}</div>
        <div class="cart-item__sub">${item.brand || ''} ${item.withInstallation ? '• Avec installation' : ''}</div>
        <div style="font-weight:700;color:var(--orange);margin-top:4px;">${((item.price + item.installationPrice) * item.quantity).toFixed(2)} DT</div>
      </div>
      <div class="quantity-control">
        <button onclick="changeQty('${item.key}', ${item.quantity - 1})">-</button>
        <span>${item.quantity}</span>
        <button onclick="changeQty('${item.key}', ${item.quantity + 1})">+</button>
      </div>
      <button onclick="removeFromCart('${item.key}')" style="background:none;color:var(--danger);font-size:1.1rem;">🗑️</button>
    </div>`).join('');

  const couponInfo = coupon ? `<div style="display:flex;justify-content:space-between;align-items:center;background:#e8f5e9;padding:10px 14px;border-radius:8px;margin-bottom:12px;"><span style="color:var(--success);font-weight:600;">🏷️ ${coupon.code}</span><button onclick="removeCoupon()" style="background:none;color:var(--danger);font-size:0.8rem;">Retirer</button></div>` : '';

  el.innerHTML = `
    <div class="cart-layout">
      <div class="cart-table">${itemsHtml}</div>
      <div class="cart-summary">
        <h3>Récapitulatif</h3>
        <div class="summary-row"><span>Sous-total</span><span>${subtotal.toFixed(2)} DT</span></div>
        ${discount > 0 ? `<div class="summary-row summary-row--discount"><span>Réduction</span><span>-${discount.toFixed(2)} DT</span></div>` : ''}
        <div class="summary-row"><span>Livraison</span><span>${shipping === 0 ? '<span style="color:var(--success)">Gratuite</span>' : shipping.toFixed(2)+' DT'}</span></div>
        <div class="summary-row summary-row--total"><span>Total TTC</span><span>${total.toFixed(2)} DT</span></div>

        ${couponInfo}
        <div class="coupon-form">
          <div class="filter-label">Code promo</div>
          <div class="coupon-input" style="margin-top:8px;">
            <input type="text" id="couponInput" class="form-input" placeholder="Ex: BIENVENUE10" style="text-transform:uppercase;" />
            <button class="btn btn--secondary btn--sm" onclick="applyCoupon()">Appliquer</button>
          </div>
          <div id="couponMsg" style="font-size:0.8rem;margin-top:6px;"></div>
        </div>
        <button class="btn btn--primary btn--full" onclick="goToCheckout()">✅ Commander</button>
        <button class="btn btn--outline btn--full" onclick="showPage('shop')" style="margin-top:10px;">← Continuer</button>
        <div style="font-size:0.75rem;color:var(--text-muted);text-align:center;margin-top:12px;">🚚 Livraison gratuite dès 500 DT</div>
      </div>
    </div>`;
}

function changeQty(key, qty) {
  Cart.updateQuantity(key, qty);
  renderCart();
}

function removeFromCart(key) {
  Cart.removeItem(key);
  renderCart();
}

function removeCoupon() {
  Cart.clearCoupon();
  renderCart();
}

async function applyCoupon() {
  const code = document.getElementById('couponInput')?.value?.trim();
  if (!code) return;
  const msg = document.getElementById('couponMsg');
  msg.textContent = 'Validation...';
  msg.style.color = 'var(--text-muted)';

  const result = await Cart.validateCoupon(code);
  if (result.success) {
    Cart.saveCoupon(result.coupon);
    msg.textContent = `✅ ${result.coupon.description || 'Coupon appliqué!'}`;
    msg.style.color = 'var(--success)';
    renderCart();
  } else {
    msg.textContent = `❌ ${result.message}`;
    msg.style.color = 'var(--danger)';
  }
}

function goToCheckout() {
  const items = Cart.getItems();
  if (items.length === 0) { showToast('Votre panier est vide', 'danger'); return; }
  showPage('checkout');
}

// ── Checkout ──
function prefillCheckout() {
  const user = Auth.getUser();
  if (user) {
    document.getElementById('co-name').value = user.name || '';
    document.getElementById('co-email').value = user.email || '';
    document.getElementById('co-phone').value = user.phone || '';
  }
}

function renderCheckoutSummary() {
  const { subtotal, discount, shipping, total, coupon } = Cart.getTotals();
  const items = Cart.getItems();
  const el = document.getElementById('checkoutSummaryContent');
  if (!el) return;

  const itemsHtml = items.map(i => `
    <div style="display:flex;justify-content:space-between;font-size:0.85rem;padding:6px 0;border-bottom:1px solid var(--grey-bg);">
      <span>${i.name} × ${i.quantity}</span>
      <span>${((i.price + i.installationPrice) * i.quantity).toFixed(2)} DT</span>
    </div>`).join('');

  el.innerHTML = `
    ${itemsHtml}
    <div class="summary-row"><span>Sous-total</span><span>${subtotal.toFixed(2)} DT</span></div>
    ${discount > 0 ? `<div class="summary-row summary-row--discount"><span>Réduction (${coupon?.code})</span><span>-${discount.toFixed(2)} DT</span></div>` : ''}
    <div class="summary-row"><span>Livraison</span><span>${shipping === 0 ? 'Gratuite' : shipping.toFixed(2)+' DT'}</span></div>
    <div class="summary-row summary-row--total"><span>Total</span><span>${total.toFixed(2)} DT</span></div>`;
}

function selectPayment(method) {
  selectedPayment = method;
  document.getElementById('pay-cod').classList.toggle('selected', method === 'cash_on_delivery');
  document.getElementById('pay-online').classList.toggle('selected', method === 'online');
  document.getElementById('online-payment-form').classList.toggle('hidden', method !== 'online');
}

async function placeOrder() {
  const name = document.getElementById('co-name')?.value?.trim();
  const email = document.getElementById('co-email')?.value?.trim();
  const phone = document.getElementById('co-phone')?.value?.trim();
  const address = document.getElementById('co-address')?.value?.trim();
  const city = document.getElementById('co-city')?.value?.trim();
  const region = document.getElementById('co-region')?.value;
  const notes = document.getElementById('co-notes')?.value?.trim();

  if (!name || !email || !phone || !address || !city) {
    showToast('❌ Veuillez remplir tous les champs obligatoires', 'danger');
    return;
  }

  const items = Cart.getItems();
  if (items.length === 0) { showToast('Votre panier est vide', 'danger'); return; }

  const { subtotal, discount, shipping, total, coupon } = Cart.getTotals();

  const orderData = {
    customer: { name, email, phone },
    shippingAddress: { street: address, city, region },
    items: items.map(i => ({
      product: i.id,
      productName: i.name,
      productSlug: i.slug,
      price: i.price,
      quantity: i.quantity,
      withInstallation: i.withInstallation,
      installationPrice: i.installationPrice,
      thumbnail: i.thumbnail
    })),
    subtotal, discount,
    couponCode: coupon?.code || null,
    shippingFee: shipping,
    total,
    paymentMethod: selectedPayment,
    notes
  };

  try {
    const resp = await fetch('/api/orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...Auth.getAuthHeader() },
      body: JSON.stringify(orderData)
    });
    const data = await resp.json();
    if (data.success) {
      const orderNum = data.order.orderNumber;
      showConfirmation(orderNum, region, shipping);
      Cart.clearCart();
    } else {
      showToast('❌ Erreur lors de la commande: ' + data.message, 'danger');
    }
  } catch {
    // Offline mode: simulate order number
    const fakeNum = `AG-${new Date().getFullYear()}-${String(Math.floor(Math.random() * 99999)).padStart(5, '0')}`;
    showConfirmation(fakeNum, region, shipping);
    Cart.clearCart();
  }
}

function showConfirmation(orderNum, region, shipping) {
  document.getElementById('confirmOrderNum').textContent = orderNum;
  const isTunis = ['Tunis', 'Ariana', 'Ben Arous'].includes(region);
  document.getElementById('confirmDeliveryInfo').innerHTML = `
    <div style="font-weight:600;color:var(--blue-dark);margin-bottom:8px;">📦 Détails de livraison</div>
    <div>🕐 Délai estimé : <strong>${isTunis ? '24h' : '48-72h'}</strong></div>
    <div>📍 Région : ${region}</div>
    <div>💳 Livraison : <strong>${shipping === 0 ? 'Gratuite' : shipping + ' DT'}</strong></div>
    <div style="margin-top:8px;font-size:0.85rem;color:var(--text-muted);">Vous recevrez une confirmation par email.</div>`;
  showPage('confirmation');
}

// ── Order Tracking ──
async function trackOrder() {
  const num = document.getElementById('trackingInput')?.value?.trim().toUpperCase();
  if (!num) return;
  const el = document.getElementById('trackingResult');
  el.innerHTML = '<div class="loader"><div class="spinner"></div></div>';

  try {
    const resp = await fetch(`/api/orders/track/${num}`);
    const data = await resp.json();
    if (data.success) renderTracking(data.order);
    else el.innerHTML = `<div class="empty-state"><div class="empty-state__icon">❌</div><div class="empty-state__title">Commande introuvable</div><div class="empty-state__text">Vérifiez votre numéro de commande</div></div>`;
  } catch {
    // Demo tracking
    renderDemoTracking(num);
  }
}

function renderDemoTracking(num) {
  const el = document.getElementById('trackingResult');
  const steps = [
    { status:'pending', label:'Commande reçue', date:'Aujourd\'hui', done:true, current:false },
    { status:'confirmed', label:'Commande confirmée', date:'Aujourd\'hui', done:true, current:false },
    { status:'processing', label:'En préparation', date:'En cours', done:false, current:true },
    { status:'shipped', label:'Expédiée', date:'—', done:false, current:false },
    { status:'delivered', label:'Livrée', date:'—', done:false, current:false }
  ];
  el.innerHTML = `
    <div class="tracking-status">
      <h3 style="color:var(--blue-dark);margin-bottom:4px;">Commande #${num}</h3>
      <div class="badge badge--orange" style="margin-bottom:24px;">En préparation</div>
      <div class="status-timeline">
        ${steps.map(s => `
          <div class="status-step ${s.done ? 'done' : ''} ${s.current ? 'current' : ''}">
            <div class="status-dot"></div>
            <div style="font-weight:${s.current ? '700' : '500'};color:${s.current ? 'var(--orange)' : s.done ? 'var(--success)' : 'var(--text-muted)'}">${s.label}</div>
            <div style="font-size:0.8rem;color:var(--text-muted);">${s.date}</div>
          </div>`).join('')}
      </div>
    </div>`;
}

function renderTracking(order) {
  const el = document.getElementById('trackingResult');
  const statusMap = { pending:'En attente', confirmed:'Confirmée', processing:'En préparation', shipped:'Expédiée', delivered:'Livrée', cancelled:'Annulée' };
  const statusClass = { pending:'badge--blue', confirmed:'badge--blue', processing:'badge--orange', shipped:'badge--orange', delivered:'badge--green', cancelled:'badge--red' };
  const history = (order.statusHistory || []).map(h => `
    <div class="status-step done">
      <div class="status-dot"></div>
      <div style="font-weight:500;">${statusMap[h.status] || h.status}</div>
      <div style="font-size:0.8rem;color:var(--text-muted);">${new Date(h.date).toLocaleString('fr-FR')} ${h.note ? '— '+h.note : ''}</div>
    </div>`).join('');

  el.innerHTML = `
    <div class="tracking-status">
      <h3 style="color:var(--blue-dark);margin-bottom:8px;">${order.orderNumber}</h3>
      <span class="badge ${statusClass[order.status] || 'badge--blue'}" style="margin-bottom:24px;">${statusMap[order.status] || order.status}</span>
      ${order.estimatedDelivery ? `<div style="margin-bottom:16px;font-size:0.9rem;color:var(--text-muted);">⏱️ Délai estimé : <strong>${order.estimatedDelivery}</strong></div>` : ''}
      <div class="status-timeline">${history}</div>
    </div>`;
}

// ── Contact Form ──
function submitContact(e) {
  e.preventDefault();
  showToast('✅ Message envoyé ! Nous vous répondrons dans les plus brefs délais.', 'success');
  e.target.reset();
}

// ── Auth Modal ──
function openAuthModal() {
  const user = Auth.getUser();
  const modal = document.getElementById('authModal');
  modal.classList.remove('hidden');
  if (user) {
    renderUserPanel(user);
  } else {
    renderLoginForm();
  }
}

function closeAuthModal() {
  document.getElementById('authModal').classList.add('hidden');
}

function renderLoginForm() {
  document.getElementById('authModalTitle').textContent = 'Se connecter';
  document.getElementById('authModalBody').innerHTML = `
    <form onsubmit="submitLogin(event)">
      <div style="display:flex;flex-direction:column;gap:16px;">
        <div class="form-group"><label class="form-label">Email</label><input type="email" id="l-email" class="form-input" required /></div>
        <div class="form-group"><label class="form-label">Mot de passe</label><input type="password" id="l-pwd" class="form-input" required /></div>
        <button type="submit" class="btn btn--primary btn--full">🔑 Se connecter</button>
        <div style="text-align:center;font-size:0.9rem;color:var(--text-muted);">Pas encore de compte ? <a onclick="renderRegisterForm()" style="color:var(--orange);cursor:pointer;font-weight:600;">S'inscrire</a></div>
      </div>
    </form>`;
}

function renderRegisterForm() {
  document.getElementById('authModalTitle').textContent = 'Créer un compte';
  document.getElementById('authModalBody').innerHTML = `
    <form onsubmit="submitRegister(event)">
      <div style="display:flex;flex-direction:column;gap:16px;">
        <div class="form-group"><label class="form-label">Nom complet *</label><input type="text" id="r-name" class="form-input" required /></div>
        <div class="form-group"><label class="form-label">Email *</label><input type="email" id="r-email" class="form-input" required /></div>
        <div class="form-group"><label class="form-label">Téléphone</label><input type="tel" id="r-phone" class="form-input" /></div>
        <div class="form-group"><label class="form-label">Mot de passe *</label><input type="password" id="r-pwd" class="form-input" required minlength="6" /></div>
        <button type="submit" class="btn btn--primary btn--full">✅ Créer mon compte</button>
        <div style="text-align:center;font-size:0.9rem;color:var(--text-muted);">Déjà un compte ? <a onclick="renderLoginForm()" style="color:var(--orange);cursor:pointer;font-weight:600;">Se connecter</a></div>
      </div>
    </form>`;
}

async function submitLogin(e) {
  e.preventDefault();
  const email = document.getElementById('l-email').value;
  const password = document.getElementById('l-pwd').value;
  const result = await Auth.login(email, password);
  if (result.success) {
    Auth.save(result.token, result.user);
    updateUserBtn();
    closeAuthModal();
    showToast(`✅ Bienvenue ${result.user.name} !`, 'success');
    if (result.user.role === 'admin' || result.user.role === 'superadmin') {
      showToast('🔐 Accès admin disponible sur /admin', 'success');
    }
  } else {
    showToast(`❌ ${result.message}`, 'danger');
  }
}

async function submitRegister(e) {
  e.preventDefault();
  const name = document.getElementById('r-name').value;
  const email = document.getElementById('r-email').value;
  const phone = document.getElementById('r-phone').value;
  const password = document.getElementById('r-pwd').value;
  const result = await Auth.register(name, email, password, phone);
  if (result.success) {
    Auth.save(result.token, result.user);
    updateUserBtn();
    closeAuthModal();
    showToast(`✅ Compte créé ! Bienvenue ${result.user.name}`, 'success');
  } else {
    showToast(`❌ ${result.message}`, 'danger');
  }
}

function renderUserPanel(user) {
  document.getElementById('authModalTitle').textContent = `👤 ${user.name}`;
  document.getElementById('authModalBody').innerHTML = `
    <div style="text-align:center;margin-bottom:20px;">
      <div style="width:70px;height:70px;background:var(--off-white);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:2rem;margin:0 auto 12px;">👤</div>
      <div style="font-weight:700;color:var(--blue-dark);">${user.name}</div>
      <div style="font-size:0.85rem;color:var(--text-muted);">${user.email}</div>
      ${user.role !== 'customer' ? `<span class="badge badge--orange" style="margin-top:8px;">${user.role}</span>` : ''}
    </div>
    <div style="display:flex;flex-direction:column;gap:10px;">
      ${user.role === 'admin' || user.role === 'superadmin' ? `<a href="/admin" class="btn btn--secondary btn--full">⚙️ Tableau de bord admin</a>` : ''}
      <button class="btn btn--outline btn--full" onclick="logoutUser()">🚪 Se déconnecter</button>
    </div>`;
}

function logoutUser() {
  Auth.logout();
  updateUserBtn();
  closeAuthModal();
  showToast('👋 À bientôt !', 'success');
}

function updateUserBtn() {
  const btn = document.getElementById('userBtn');
  if (!btn) return;
  const user = Auth.getUser();
  btn.innerHTML = user ? '👤' : '<i class="fa fa-user"></i>';
  btn.style.background = user ? 'rgba(255,111,0,0.25)' : '';
}

// ── Toast ──
function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast ${type === 'success' ? 'toast--success' : type === 'danger' ? 'toast--danger' : ''}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

// Close modal on overlay click
document.addEventListener('click', (e) => {
  const modal = document.getElementById('authModal');
  if (e.target === modal) closeAuthModal();
});
