require('dotenv').config();

// ─── Global crash guards (Node 22 exits on unhandled rejections by default) ──
process.on('uncaughtException', (err) => {
  console.error('[fatal] uncaughtException:', err.message, err.stack);
  // Do NOT exit — keep serving static files
});
process.on('unhandledRejection', (reason, promise) => {
  console.error('[fatal] unhandledRejection at:', promise, 'reason:', reason);
  // Do NOT exit — keep serving static files
});

const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const compression = require('compression');
const morgan = require('morgan');
const rateLimit = require('express-rate-limit');
const path = require('path');

const connectDB = require('./config/database');
const { initStorage } = require('./config/azureStorage');

const app = express();
const PORT = process.env.PORT || 3000;

// ─── Security & Middleware ───────────────────────────────────────────────────
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      styleSrc: ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com", "https://cdnjs.cloudflare.com"],
      fontSrc: ["'self'", "https://fonts.gstatic.com", "https://cdnjs.cloudflare.com"],
      scriptSrc: ["'self'", "'unsafe-inline'", "https://cdnjs.cloudflare.com"],
      scriptSrcAttr: ["'unsafe-inline'"],   // Allow onclick, onmouseover handlers
      imgSrc: ["'self'", "data:", "https:", "blob:"],  // Fixed: https: not https://
      connectSrc: ["'self'", "https:"]
    }
  }
}));
app.use(compression());
app.use(cors({ origin: process.env.ALLOWED_ORIGIN || '*', credentials: true }));
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));
if (process.env.NODE_ENV !== 'production') app.use(morgan('dev'));

// Rate limiting
const limiter = rateLimit({ windowMs: 15 * 60 * 1000, max: 200, message: 'Too many requests' });
const authLimiter = rateLimit({ windowMs: 15 * 60 * 1000, max: 20, message: 'Too many auth requests' });
app.use('/api', limiter);
app.use('/api/auth', authLimiter);

// ─── API Routes ─────────────────────────────────────────────────────────────
try {
  app.use('/api/auth', require('./routes/auth'));
  app.use('/api/products', require('./routes/products'));
  app.use('/api/orders', require('./routes/orders'));
  app.use('/api/admin', require('./routes/admin'));
  console.log('[routes] All routes loaded OK');
} catch (e) {
  console.error('[routes] Failed to load routes:', e.message, e.stack);
}

// ─── Health check ───────────────────────────────────────────────────────────
app.get('/api/health', (req, res) => {
  res.json({ success: true, status: 'OK', timestamp: new Date().toISOString(), env: process.env.NODE_ENV });
});

// ─── Static frontend ────────────────────────────────────────────────────────
app.use(express.static(path.join(__dirname, 'public'), {
  maxAge: process.env.NODE_ENV === 'production' ? '7d' : 0,
  setHeaders: (res, filePath) => {
    // Never cache index.html — deploys must take effect immediately
    if (filePath.endsWith('index.html')) {
      res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
      res.setHeader('Pragma', 'no-cache');
      res.setHeader('Expires', '0');
    }
  }
}));

// SPA fallback
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// ─── Error handler ──────────────────────────────────────────────────────────
app.use((err, req, res, next) => {
  console.error(err.stack);
  res.status(err.status || 500).json({ success: false, message: err.message || 'Erreur serveur' });
});

// ─── Auto-seed on first boot ─────────────────────────────────────────────────
const autoSeed = async () => {
  try {
    const User = require('./models/User');
    const Product = require('./models/Product');
    const count = await Product.countDocuments();
    if (count === 0) {
      console.log('[seed] Empty database detected - running auto-seed...');
      require('child_process').execSync('node scripts/seed.js', {
        cwd: __dirname,
        stdio: 'inherit',
        timeout: 60000
      });
      console.log('[seed] Auto-seed complete.');
    } else {
      console.log('[seed] Database already has ' + count + ' products - skipping seed.');
    }
  } catch (e) {
    console.error('[seed] Auto-seed error (non-fatal):', e.message);
  }
};

// ─── Start ──────────────────────────────────────────────────────────────────
const start = () => {
  // Bind port IMMEDIATELY - Azure health check must see a response within 230s
  app.listen(PORT, () => {
    console.log('[start] Ange Gardien running on port ' + PORT);
  });

  // Connect DB + storage in the background (non-blocking)
  // .catch() on the IIFE prevents unhandled rejection crash
  (async () => {
    try {
      await connectDB();
      await initStorage();
      await autoSeed();
    } catch (e) {
      console.error('[start] Background init error (non-fatal):', e.message);
    }
  })().catch(e => console.error('[start] IIFE catch:', e.message));
};

start();
