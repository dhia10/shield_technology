#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  Shield Technology — SSL + Custom Domain Setup
#  Run AFTER patch.ps1 and after DNS propagation (wait ~30 min)
#  Usage: bash deploy/ssl-custom-domain.sh
# ═══════════════════════════════════════════════════════════════

SUBSCRIPTION="dd304ca8-be36-4ad8-a6e0-34f6f9be2698"
RESOURCE_GROUP="ange-gardien-rg"
APP_NAME="ange-gardien-web"
DOMAIN="shieldtechnology.tn"
WWW_DOMAIN="www.shieldtechnology.tn"

az account set --subscription $SUBSCRIPTION

echo "🔒 Configuring custom domain and SSL for Shield Technology..."

# Add root domain
echo ""
echo "📌 Adding $DOMAIN..."
az webapp config hostname add \
  --webapp-name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --hostname "$DOMAIN"

# Add www subdomain
echo ""
echo "📌 Adding $WWW_DOMAIN..."
az webapp config hostname add \
  --webapp-name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --hostname "$WWW_DOMAIN"

# Create free App Service Managed Certificate for www
echo ""
echo "🔒 Creating free managed SSL certificate for $WWW_DOMAIN..."
az webapp config ssl create \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --hostname "$WWW_DOMAIN"

# Get thumbprint
echo ""
echo "🔑 Getting certificate thumbprint..."
THUMBPRINT=$(az webapp config ssl list \
  --resource-group "$RESOURCE_GROUP" \
  --query "[?subjectName=='$WWW_DOMAIN'].thumbprint | [0]" \
  --output tsv)

echo "   Thumbprint: $THUMBPRINT"

# Bind SSL to www
az webapp config ssl bind \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --certificate-thumbprint "$THUMBPRINT" \
  --ssl-type SNI

# Force HTTPS
echo ""
echo "🔐 Enforcing HTTPS-only..."
az webapp update \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --https-only true

echo ""
echo "✅ Done! Your site is now live at:"
echo "   https://$WWW_DOMAIN"
echo "   https://$DOMAIN"
