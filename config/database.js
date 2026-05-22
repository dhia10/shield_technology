const mongoose = require('mongoose');

const connectDB = async () => {
  const uri = process.env.MONGODB_URI;
  if (!uri) {
    console.error('[db] MONGODB_URI is not set - running without database');
    return;
  }
  const MAX = 5;
  for (let attempt = 1; attempt <= MAX; attempt++) {
    try {
      const conn = await mongoose.connect(uri, {
        serverSelectionTimeoutMS: 30000,
        socketTimeoutMS: 60000,
        connectTimeoutMS: 30000
      });
      console.log('[db] Connected to Cosmos DB: ' + conn.connection.host);
      return;
    } catch (error) {
      console.error('[db] Attempt ' + attempt + '/' + MAX + ' failed: ' + error.message);
      if (attempt < MAX) {
        const wait = attempt * 5000;
        console.log('[db] Retrying in ' + (wait / 1000) + 's...');
        await new Promise(r => setTimeout(r, wait));
      }
    }
  }
  console.error('[db] All connection attempts failed - app will run without database');
  // Do NOT call process.exit() - let the app serve static files
};

module.exports = connectDB;
