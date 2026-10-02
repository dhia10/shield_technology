# ═══════════════════════════════════════════════════════════════
#  Ange Gardien — SSL + Custom Domain (PowerShell)
#  Run AFTER deploy.ps1 AND after DNS propagation (24-48h)
# ═══════════════════════════════════════════════════════════════

$RG     = "ange-gardien-rg"
$APP    = "ange-gardien-web"
$DOMAIN = "www.shieldtechnology.tn"

Write-Host "🔒 Binding custom domain and SSL..." -ForegroundColor Cyan

# 1. Add custom hostname
az webapp config hostname add `
  --webapp-name $APP `
  --resource-group $RG `
  --hostname $DOMAIN

# 2. Create free managed SSL certificate
az webapp config ssl create `
  --name $APP `
  --resource-group $RG `
  --hostname $DOMAIN

# 3. Get thumbprint and bind
$thumb = az webapp config ssl list `
  --resource-group $RG `
  --query "[?subjectName=='$DOMAIN'].thumbprint" `
  --output tsv

az webapp config ssl bind `
  --name $APP `
  --resource-group $RG `
  --certificate-thumbprint $thumb `
  --ssl-type SNI

# 4. Force HTTPS
az webapp update `
  --name $APP `
  --resource-group $RG `
  --https-only true

Write-Host ""
Write-Host "✅ SSL configured!" -ForegroundColor Green
Write-Host "🌐 Live at: https://$DOMAIN" -ForegroundColor Cyan
