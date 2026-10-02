#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  Ange Gardien — Azure Deployment Script
#  Prerequisites: az CLI logged in (az login), Node.js installed
# ═══════════════════════════════════════════════════════════════
set -e

# ─── CONFIG (edit these) ────────────────────────────────────
RESOURCE_GROUP="ange-gardien-rg"
LOCATION="francecentral"            # closest to Tunisia
APP_SERVICE_PLAN="ange-gardien-plan"
APP_NAME="ange-gardien-app"         # must be globally unique
COSMOS_ACCOUNT="ange-gardien-db"    # must be globally unique
DB_NAME="angegardien"
STORAGE_ACCOUNT="angegardienstore"  # must be globally unique, max 24 chars
STORAGE_CONTAINER="shield-media"
DOMAIN="shieldtechnology.tn"

echo ""
echo "🛡️  ═══════════════════════════════════════════"
echo "    ANGE GARDIEN — Azure Deployment"
echo "    Location: $LOCATION"
echo "═══════════════════════════════════════════════"
echo ""

# ─── STEP 1: Resource Group ────────────────────────────────
echo "📁 [1/7] Creating Resource Group..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output table
echo "✅ Resource group ready."

# ─── STEP 2: App Service Plan (Free tier for student) ──────
echo ""
echo "🖥️  [2/7] Creating App Service Plan (F1 Free)..."
az appservice plan create \
  --name "$APP_SERVICE_PLAN" \
  --resource-group "$RESOURCE_GROUP" \
  --sku F1 \
  --is-linux \
  --output table
echo "✅ App Service Plan ready."

# ─── STEP 3: Web App ───────────────────────────────────────
echo ""
echo "🌐 [3/7] Creating Web App ($APP_NAME)..."
az webapp create \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --plan "$APP_SERVICE_PLAN" \
  --runtime "NODE:18-lts" \
  --output table

# Startup command
az webapp config set \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --startup-file "node server.js" \
  --output none

echo "✅ Web App created: https://${APP_NAME}.azurewebsites.net"

# ─── STEP 4: Azure Cosmos DB (MongoDB API) ─────────────────
echo ""
echo "🗄️  [4/7] Creating Cosmos DB (MongoDB API)..."
az cosmosdb create \
  --name "$COSMOS_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --kind MongoDB \
  --server-version "6.0" \
  --default-consistency-level "Session" \
  --locations regionName="$LOCATION" failoverPriority=0 \
  --output table

# Create database
az cosmosdb mongodb database create \
  --account-name "$COSMOS_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --name "$DB_NAME" \
  --output table

echo "✅ Cosmos DB ready."

# Get connection string
COSMOS_CONN=$(az cosmosdb keys list \
  --name "$COSMOS_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --type connection-strings \
  --query "connectionStrings[?description=='Primary MongoDB Connection String'].connectionString" \
  --output tsv)

echo "📌 Cosmos DB Connection String retrieved."

# ─── STEP 5: Azure Blob Storage ────────────────────────────
echo ""
echo "📦 [5/7] Creating Blob Storage..."
az storage account create \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --output table

# Create container
az storage container create \
  --name "$STORAGE_CONTAINER" \
  --account-name "$STORAGE_ACCOUNT" \
  --public-access blob \
  --output table

STORAGE_CONN=$(az storage account show-connection-string \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --query connectionString \
  --output tsv)

echo "✅ Blob Storage ready."

# ─── STEP 6: Configure Environment Variables ───────────────
echo ""
echo "⚙️  [6/7] Configuring App Settings..."

JWT_SECRET=$(openssl rand -hex 32)

az webapp config appsettings set \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --settings \
    "MONGODB_URI=$COSMOS_CONN" \
    "AZURE_STORAGE_CONNECTION_STRING=$STORAGE_CONN" \
    "AZURE_STORAGE_CONTAINER=$STORAGE_CONTAINER" \
    "JWT_SECRET=$JWT_SECRET" \
    "NODE_ENV=production" \
    "ADMIN_EMAIL=admin@shieldtechnology.tn" \
    "ADMIN_PASSWORD=Shield@2025!" \
    "WEBSITE_NODE_DEFAULT_VERSION=~18" \
    "SCM_DO_BUILD_DURING_DEPLOYMENT=true" \
  --output none

echo "✅ Environment variables configured."

# ─── STEP 7: Deploy Code ───────────────────────────────────
echo ""
echo "🚀 [7/7] Deploying application code..."
cd "$(dirname "$0")/.."

# Create deployment zip
zip -r deploy.zip . \
  --exclude "*.git*" \
  --exclude "node_modules/*" \
  --exclude "deploy/*" \
  --exclude "*.env" \
  --exclude "deploy.zip"

az webapp deploy \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --src-path deploy.zip \
  --type zip \
  --output table

rm -f deploy.zip

echo ""
echo "✅ Code deployed!"

# ─── POST-DEPLOY: Seed Database ────────────────────────────
echo ""
echo "🌱 Seeding database (products + admin)..."
az webapp ssh --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" --command "cd /home/site/wwwroot && npm install && node scripts/seed.js" 2>/dev/null || \
  echo "⚠️  Run seed manually: navigate to https://${APP_NAME}.scm.azurewebsites.net/DebugConsole and run 'node scripts/seed.js'"

# ─── CUSTOM DOMAIN ─────────────────────────────────────────
echo ""
echo "🌐 Custom domain setup..."
echo "📌 Add this CNAME record in your DNS (domain: $DOMAIN):"
echo ""
echo "   Type: CNAME"
echo "   Name: www (or @)"
echo "   Value: ${APP_NAME}.azurewebsites.net"
echo ""
echo "   Then run:"
echo "   az webapp config hostname add --webapp-name $APP_NAME --resource-group $RESOURCE_GROUP --hostname www.$DOMAIN"
echo ""

# ─── SUMMARY ───────────────────────────────────────────────
echo "═══════════════════════════════════════════════"
echo "🎉 DEPLOYMENT COMPLETE!"
echo "═══════════════════════════════════════════════"
echo ""
echo "🌐 Site URL:     https://${APP_NAME}.azurewebsites.net"
echo "⚙️  Admin panel: https://${APP_NAME}.azurewebsites.net/admin"
echo "🔑 Admin login:  admin@shieldtechnology.tn / Shield@2025!"
echo "🗄️  Cosmos DB:   $COSMOS_ACCOUNT"
echo "📦 Blob Storage: $STORAGE_ACCOUNT"
echo ""
echo "📌 Next steps:"
echo "  1. Configure DNS: add CNAME $DOMAIN → ${APP_NAME}.azurewebsites.net"
echo "  2. Enable SSL: az webapp config ssl bind ..."
echo "  3. Monitor: az monitor metrics list --resource $APP_NAME ..."
echo ""
