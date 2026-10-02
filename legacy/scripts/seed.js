require('dotenv').config();
const mongoose = require('mongoose');
const bcrypt = require('bcryptjs');
const User = require('../models/User');
const Product = require('../models/Product');
const Coupon = require('../models/Coupon');

const connectDB = async () => {
  await mongoose.connect(process.env.MONGODB_URI);
  console.log('✅ Connected to DB');
};

const products = [
  // ─── Alarmes intrusion ──────────────────────────────────────────────────────
  {
    name: 'Kit DSC Power Series Neo', nameAr: 'طقم DSC Power Series Neo',
    slug: 'kit-dsc-power-series-neo', category: 'alarmes',
    description: 'Kit complet : centrale + 3 détecteurs + sirène. La référence en alarme anti-intrusion.',
    descriptionAr: 'طقم كامل: لوحة تحكم + 3 كاشفات + صفارة إنذار. المرجع في أنظمة الإنذار ضد الاقتحام.',
    price: 890, installationPrice: 150, brand: 'DSC',
    thumbnail: 'https://via.placeholder.com/400x300/1a237e/ffffff?text=Kit+DSC+Neo',
    images: ['https://via.placeholder.com/400x300/1a237e/ffffff?text=Kit+DSC+Neo'],
    stockStatus: 'available', stock: 15, featured: true, warranty: '2 ans',
    sku: 'DSC-KIT-001',
    features: ['Centrale HS2016 16 zones', '3 détecteurs PIR', 'Sirène intérieure', 'Communication IP/GPRS', 'Application mobile']
  },
  {
    name: 'Détecteur de mouvement DSC filaire', nameAr: 'كاشف حركة DSC سلكي',
    slug: 'detecteur-mouvement-dsc-filaire', category: 'alarmes',
    description: 'Détecteur PIR filaire haute performance avec anti-masquage.',
    descriptionAr: 'كاشف PIR سلكي عالي الأداء مع حماية ضد الإخفاء.',
    price: 120, installationPrice: 50, brand: 'DSC',
    thumbnail: 'https://via.placeholder.com/400x300/1a237e/ffffff?text=DSC+PIR',
    images: ['https://via.placeholder.com/400x300/1a237e/ffffff?text=DSC+PIR'],
    stockStatus: 'available', stock: 40, warranty: '2 ans', sku: 'DSC-PIR-001',
    features: ['Portée 12m × 12m', 'Anti-masquage', 'Immunité animaux <25kg', 'Montage mural facile']
  },
  {
    name: "Détecteur d'ouverture DSC sans fil", nameAr: 'كاشف فتح DSC لاسلكي',
    slug: 'detecteur-ouverture-dsc-sans-fil', category: 'alarmes',
    description: 'Détecteur magnétique sans fil pour portes et fenêtres.',
    descriptionAr: 'كاشف مغناطيسي لاسلكي للأبواب والنوافذ.',
    price: 85, installationPrice: 30, brand: 'DSC',
    thumbnail: 'https://via.placeholder.com/400x300/1a237e/ffffff?text=DSC+Contact',
    images: ['https://via.placeholder.com/400x300/1a237e/ffffff?text=DSC+Contact'],
    stockStatus: 'available', stock: 60, warranty: '2 ans', sku: 'DSC-CON-001',
    features: ['Sans fil 433MHz', 'Pile incluse 3 ans', 'Tamper protection', 'LED de test']
  },
  {
    name: 'Sirène intérieure DSC', nameAr: 'صفارة إنذار داخلية DSC',
    slug: 'sirene-interieure-dsc', category: 'alarmes',
    description: 'Sirène auto-alimentée haute décibels pour usage intérieur.',
    descriptionAr: 'صفارة إنذار داخلية عالية الديسيبل ذاتية التغذية.',
    price: 95, installationPrice: 40, brand: 'DSC',
    thumbnail: 'https://via.placeholder.com/400x300/1a237e/ffffff?text=Sirène+DSC',
    images: ['https://via.placeholder.com/400x300/1a237e/ffffff?text=Sirène+DSC'],
    stockStatus: 'available', stock: 30, warranty: '2 ans', sku: 'DSC-SIR-001',
    features: ['110 dB', 'Batterie secours 4h', 'Tamper intégré', 'LED flash']
  },

  // ─── Vidéosurveillance ──────────────────────────────────────────────────────
  {
    name: 'Caméra Grundig Essential IP 2MP', nameAr: 'كاميرا Grundig Essential IP 2 ميجابكسل',
    slug: 'camera-grundig-essential-ip-2mp', category: 'videosurveillance',
    description: "Caméra IP dôme 2MP Full HD avec vision nocturne 30m. Idéale pour l'entrée des commerces et bureaux.",
    descriptionAr: 'كاميرا IP دوم 2 ميجابكسل Full HD مع رؤية ليلية 30م. مثالية لمدخل المحلات والمكاتب.',
    price: 320, installationPrice: 80, brand: 'Grundig',
    thumbnail: 'https://via.placeholder.com/400x300/263238/ffffff?text=Grundig+2MP',
    images: ['https://via.placeholder.com/400x300/263238/ffffff?text=Grundig+2MP'],
    stockStatus: 'available', stock: 25, featured: true, warranty: '3 ans', sku: 'GRU-CAM-2MP',
    features: ['Résolution 1080p', 'Vision nocturne IR 30m', 'IP66 résistant', 'ONVIF compatible', 'H.265+']
  },
  {
    name: 'Caméra Grundig Pro 4MP Vision Nocturne', nameAr: 'كاميرا Grundig Pro 4 ميجابكسل رؤية ليلية',
    slug: 'camera-grundig-pro-4mp', category: 'videosurveillance',
    description: 'Caméra IP 4MP avec vision nocturne couleur et intelligence artificielle.',
    descriptionAr: 'كاميرا IP 4 ميجابكسل مع رؤية ليلية ملونة وذكاء اصطناعي.',
    price: 520, installationPrice: 80, brand: 'Grundig',
    thumbnail: 'https://via.placeholder.com/400x300/263238/ffffff?text=Grundig+4MP',
    images: ['https://via.placeholder.com/400x300/263238/ffffff?text=Grundig+4MP'],
    stockStatus: 'available', stock: 18, warranty: '3 ans', sku: 'GRU-CAM-4MP',
    features: ['Résolution 4MP', 'Vision nocturne couleur', 'IA : détection personnes/véhicules', 'IP67', 'WDR 120dB']
  },
  {
    name: 'Caméra Panasonic i-PRO 4K IA intégrée', nameAr: 'كاميرا Panasonic i-PRO 4K بذكاء اصطناعي',
    slug: 'camera-panasonic-ipro-4k', category: 'videosurveillance',
    description: 'Caméra 4K avec IA embarquée : distinction personnes/véhicules, réduction fausses alarmes. Certifiée NDAA.',
    descriptionAr: 'كاميرا 4K مع ذكاء اصطناعي مدمج: تمييز الأشخاص/المركبات، تقليل الإنذارات الكاذبة. معتمدة NDAA.',
    price: 890, installationPrice: 100, brand: 'Panasonic',
    thumbnail: 'https://via.placeholder.com/400x300/263238/ffffff?text=Panasonic+4K',
    images: ['https://via.placeholder.com/400x300/263238/ffffff?text=Panasonic+4K'],
    stockStatus: 'available', stock: 10, featured: true, warranty: '5 ans', sku: 'PAN-4K-001',
    features: ['4K Ultra HD', 'IA embarquée', 'Certifiée NDAA', 'Vision nocturne 50m', 'Cybersécurité intégrée']
  },
  {
    name: 'Enregistreur Grundig 8 canaux + 1To', nameAr: 'مسجل Grundig 8 قنوات + 1 تيرابايت',
    slug: 'enregistreur-grundig-8ch', category: 'videosurveillance',
    description: 'NVR 8 canaux avec disque dur 1To intégré. Accès à distance via application mobile.',
    descriptionAr: 'مسجل شبكي NVR 8 قنوات مع قرص صلب 1 تيرابايت. الوصول عن بُعد عبر التطبيق المحمول.',
    price: 650, installationPrice: 120, brand: 'Grundig',
    thumbnail: 'https://via.placeholder.com/400x300/263238/ffffff?text=NVR+Grundig+8CH',
    images: ['https://via.placeholder.com/400x300/263238/ffffff?text=NVR+Grundig+8CH'],
    stockStatus: 'available', stock: 12, warranty: '3 ans', sku: 'GRU-NVR-8CH',
    features: ['8 canaux IP', 'HDD 1To inclus', 'Accès mobile iOS/Android', 'PoE intégré', 'H.265']
  },

  // ─── Détection incendie ─────────────────────────────────────────────────────
  {
    name: 'Détecteur de fumée FireClass', nameAr: 'كاشف دخان FireClass',
    slug: 'detecteur-fumee-fireclass', category: 'incendie',
    description: "Détecteur optique de fumée FireClass. Certifié EN54. Installation simple et fiable.",
    descriptionAr: 'كاشف دخان بصري FireClass. معتمد EN54. تركيب بسيط وموثوق.',
    price: 180, installationPrice: 40, brand: 'FireClass',
    thumbnail: 'https://via.placeholder.com/400x300/b71c1c/ffffff?text=FireClass+Fumée',
    images: ['https://via.placeholder.com/400x300/b71c1c/ffffff?text=FireClass+Fumée'],
    stockStatus: 'available', stock: 50, warranty: '5 ans', sku: 'FC-SMK-001',
    features: ['Certifié EN54-7', 'LED d\'alarme 360°', 'Test automatique', 'Adressable', 'Base universelle']
  },
  {
    name: 'Centrale incendie FireClass 2 boucles', nameAr: 'لوحة إنذار حريق FireClass 2 حلقات',
    slug: 'centrale-incendie-fireclass-2-boucles', category: 'incendie',
    description: 'Centrale adressable 2 boucles jusqu\'à 250 détecteurs par boucle. Conforme NF S61-931.',
    descriptionAr: 'لوحة تحكم قابلة للعنونة بحلقتين حتى 250 كاشف لكل حلقة. متوافقة مع NF S61-931.',
    price: 1200, installationPrice: 300, brand: 'FireClass',
    thumbnail: 'https://via.placeholder.com/400x300/b71c1c/ffffff?text=Centrale+FC',
    images: ['https://via.placeholder.com/400x300/b71c1c/ffffff?text=Centrale+FC'],
    stockStatus: 'available', stock: 5, featured: true, warranty: '5 ans', sku: 'FC-CEN-2L',
    features: ['2 boucles adressables', '250 points/boucle', 'Écran LCD', 'Imprimante intégrée', 'Réseau TCP/IP']
  },
  {
    name: 'Sirène incendie extérieure', nameAr: 'صفارة إنذار حريق خارجية',
    slug: 'sirene-incendie-exterieure', category: 'incendie',
    description: 'Sirène flash extérieure haute visibilité pour signalisation incendie.',
    descriptionAr: 'صفارة فلاش خارجية عالية الرؤية للإشارة إلى الحريق.',
    price: 210, installationPrice: 60, brand: 'FireClass',
    thumbnail: 'https://via.placeholder.com/400x300/b71c1c/ffffff?text=Sirène+Ext',
    images: ['https://via.placeholder.com/400x300/b71c1c/ffffff?text=Sirène+Ext'],
    stockStatus: 'available', stock: 20, warranty: '3 ans', sku: 'FC-SIR-EXT',
    features: ['100 dB', 'Flash rouge/blanc', 'IP65', '12/24V', 'Boîtier anti-vandalisme']
  },
  {
    name: 'Détecteur de chaleur FireClass', nameAr: 'كاشف حرارة FireClass',
    slug: 'detecteur-chaleur-fireclass', category: 'incendie',
    description: 'Détecteur thermique différentiel et température fixe. Idéal cuisines et parkings.',
    descriptionAr: 'كاشف حراري تفاضلي ودرجة حرارة ثابتة. مثالي للمطابخ ومواقف السيارات.',
    price: 160, installationPrice: 40, brand: 'FireClass',
    thumbnail: 'https://via.placeholder.com/400x300/b71c1c/ffffff?text=Détecteur+Chaleur',
    images: ['https://via.placeholder.com/400x300/b71c1c/ffffff?text=Détecteur+Chaleur'],
    stockStatus: 'available', stock: 35, warranty: '5 ans', sku: 'FC-HTD-001',
    features: ['57°C fixe + 8.5°C/min', 'Certifié EN54-5', 'Adressable', 'Cuisines et parkings']
  },

  // ─── Contrôle d'accès ───────────────────────────────────────────────────────
  {
    name: 'Kit Kantech KT-4 (contrôleur 4 portes)', nameAr: 'طقم Kantech KT-4 (وحدة تحكم 4 أبواب)',
    slug: 'kit-kantech-kt4', category: 'controle-acces',
    description: 'Contrôleur de contrôle d\'accès 4 portes Kantech. Solution IP haute sécurité avec gestion des badges.',
    descriptionAr: 'وحدة تحكم في الوصول 4 أبواب Kantech. حل IP عالي الأمان مع إدارة البطاقات.',
    price: 1450, installationPrice: 400, brand: 'Kantech',
    thumbnail: 'https://via.placeholder.com/400x300/37474f/ffffff?text=Kantech+KT4',
    images: ['https://via.placeholder.com/400x300/37474f/ffffff?text=Kantech+KT4'],
    stockStatus: 'available', stock: 8, featured: true, warranty: '3 ans', sku: 'KAN-KT4-001',
    features: ['4 portes', 'IP intégré', '100 000 badges', 'Historique 100 000 événements', 'Anti-passback', 'PoE']
  },
  {
    name: 'Tourniquet tripode', nameAr: 'بوابة دوارة ثلاثية',
    slug: 'tourniquet-tripode', category: 'controle-acces',
    description: 'Tourniquet tripode inox pour contrôle d\'accès en entreprise, hôtels et espaces publics.',
    descriptionAr: 'بوابة دوارة ثلاثية من الفولاذ المقاوم للصدأ للتحكم في الدخول في المؤسسات والفنادق والأماكن العامة.',
    price: 2500, priceOnRequest: true, installationPrice: 500, brand: 'Ange Gardien',
    thumbnail: 'https://via.placeholder.com/400x300/37474f/ffffff?text=Tourniquet',
    images: ['https://via.placeholder.com/400x300/37474f/ffffff?text=Tourniquet'],
    stockStatus: 'on_order', stock: 0, warranty: '2 ans', sku: 'AG-TURN-001',
    features: ['Inox 304', 'Bidirectionnel', 'Moteur silencieux', 'Anti-retour', 'Intégration lecteur badge']
  },
  {
    name: 'Scanner bagages à rayons X', nameAr: 'جهاز فحص الأمتعة بالأشعة السينية',
    slug: 'scanner-bagages-rayons-x', category: 'controle-acces',
    description: 'Tunnel de sécurité à rayons X pour inspection bagages en milieux sécurisés.',
    descriptionAr: 'نفق أمني بالأشعة السينية لفحص الأمتعة في البيئات الآمنة.',
    price: 8900, priceOnRequest: true, installationPrice: 1500, brand: 'Tyco',
    thumbnail: 'https://via.placeholder.com/400x300/37474f/ffffff?text=Scanner+X',
    images: ['https://via.placeholder.com/400x300/37474f/ffffff?text=Scanner+X'],
    stockStatus: 'on_order', stock: 0, warranty: '3 ans', sku: 'TYC-XRAY-001',
    features: ['Résolution 0.1mm', 'Conveyor 0.22m/s', 'Écran couleur 19"', 'Archivage images', 'Certifié CE']
  },
  {
    name: 'Radio Midland G10 Pro (paire)', nameAr: 'راديو Midland G10 Pro (زوج)',
    slug: 'radio-midland-g10-pro', category: 'controle-acces',
    description: 'Paire de radios PMR446 professionnelles Midland G10 Pro. Portée jusqu\'à 10km.',
    descriptionAr: 'زوج من أجهزة اللاسلكي المهنية PMR446 Midland G10 Pro. مدى يصل إلى 10 كم.',
    price: 450, installationPrice: 0, brand: 'Midland',
    thumbnail: 'https://via.placeholder.com/400x300/37474f/ffffff?text=Midland+G10',
    images: ['https://via.placeholder.com/400x300/37474f/ffffff?text=Midland+G10'],
    stockStatus: 'available', stock: 20, warranty: '1 an', sku: 'MID-G10-PAIR',
    features: ['PMR446 sans licence', 'Portée 10km', '8 canaux + 38 sous-tons', 'Batterie Li-ion', 'IP54']
  }
];

const coupons = [
  { code: 'BIENVENUE10', type: 'percentage', value: 10, minCartAmount: 0, perUserLimit: 1, description: '-10% de bienvenue', descriptionAr: '-10% ترحيباً بك' },
  { code: 'LIVRAISONGRATUITE', type: 'free_shipping', value: 0, minCartAmount: 100, description: 'Livraison gratuite', descriptionAr: 'توصيل مجاني' },
  { code: 'ANGE50', type: 'fixed', value: 50, minCartAmount: 500, description: '-50 DT sur tout panier > 500 DT', descriptionAr: '-50 دت على أي سلة > 500 دت' },
  { code: 'FIDELITE15', type: 'percentage', value: 15, minCartAmount: 0, requiresPreviousOrder: true, perUserLimit: 3, description: '-15% fidélité', descriptionAr: '-15% ولاء' }
];

const seed = async () => {
  await connectDB();

  // Clear existing data
  await Promise.all([Product.deleteMany({}), Coupon.deleteMany({}), User.deleteOne({ role: 'superadmin' })]);
  console.log('🗑️  Cleared existing data');

  // Create products
  await Product.insertMany(products);
  console.log(`✅ ${products.length} produits créés`);

  // Create coupons
  await Coupon.insertMany(coupons);
  console.log(`✅ ${coupons.length} coupons créés`);

  // Create superadmin
  const admin = new User({
    name: 'Super Admin',
    email: process.env.ADMIN_EMAIL || 'admin@shieldtechnology.tn',
    password: process.env.ADMIN_PASSWORD || 'Shield@2025!',
    role: 'superadmin',
    isActive: true
  });
  await admin.save();
  console.log(`✅ Super admin créé: ${admin.email}`);

  console.log('\n🎉 Base de données initialisée avec succès!');
  process.exit(0);
};

seed().catch(err => { console.error(err); process.exit(1); });
