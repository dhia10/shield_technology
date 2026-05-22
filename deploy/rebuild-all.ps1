# Ange Gardien - Complete Rebuild
# Plan + App deleted. This recreates everything and deploys.
# All fixes included: no process.exit, port binds before DB connects.

$ErrorActionPreference = "Continue"

$SUB  = "dd304ca8-be36-4ad8-a6e0-34f6f9be2698"
$RG   = "ange-gardien-rg"
$LOC  = "francecentral"
$PLAN = "ange-gardien-plan"
$APP  = "ange-gardien-web"
$DB   = "ange-gardiendb01"
$ST   = "angegardienblob01"
$CTR  = "shield-media"
$PROJ = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  ANGE GARDIEN - Complete Rebuild" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

az account set --subscription $SUB
if ($LASTEXITCODE -ne 0) {
    Write-Host "Not logged in. Run: az login" -ForegroundColor Red
    exit 1
}
Write-Host "Subscription OK" -ForegroundColor Green

# STEP 1 - App Service Plan
Write-Host ""
Write-Host "[1/7] App Service Plan..." -ForegroundColor Yellow
az appservice plan show --name $PLAN --resource-group $RG --output none 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Plan exists." -ForegroundColor Gray
} else {
    az appservice plan create --name $PLAN --resource-group $RG --location $LOC --sku F1 --is-linux --output none
    Write-Host "Plan created." -ForegroundColor Green
}

# STEP 2 - Web App
Write-Host ""
Write-Host "[2/7] Web App..." -ForegroundColor Yellow
az webapp show --name $APP --resource-group $RG --output none 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "App exists." -ForegroundColor Gray
} else {
    az webapp create --name $APP --resource-group $RG --plan $PLAN --runtime "NODE:22-lts" --output none
    Write-Host "App created." -ForegroundColor Green
}
az webapp config set --name $APP --resource-group $RG --startup-file "node server.js" --output none
az resource update --resource-group $RG --name scm --namespace Microsoft.Web --resource-type basicPublishingCredentialsPolicies --parent "sites/$APP" --set properties.allow=true --output none 2>$null
Write-Host "Web App ready." -ForegroundColor Green

# STEP 3 - App Settings
Write-Host ""
Write-Host "[3/7] App settings..." -ForegroundColor Yellow
$MONGO = az cosmosdb keys list --name $DB --resource-group $RG --type connection-strings --query "connectionStrings[0].connectionString" --output tsv
$BLOB  = az storage account show-connection-string --name $ST --resource-group $RG --query connectionString --output tsv
$JWT   = [System.Guid]::NewGuid().ToString("N") + [System.Guid]::NewGuid().ToString("N")
Write-Host "  Cosmos URI retrieved." -ForegroundColor Gray

$PROPS = [ordered]@{
    MONGODB_URI                     = $MONGO
    AZURE_STORAGE_CONNECTION_STRING = $BLOB
    AZURE_STORAGE_CONTAINER         = $CTR
    JWT_SECRET                      = $JWT
    NODE_ENV                        = "production"
    ADMIN_EMAIL                     = "admin@shieldtechnology.tn"
    ADMIN_PASSWORD                  = "Shield@2025!"
    WEBSITE_NODE_DEFAULT_VERSION    = "~22"
    SCM_DO_BUILD_DURING_DEPLOYMENT  = "false"
}
$BODY = (@{ properties = $PROPS } | ConvertTo-Json -Depth 5)
$FILE = "$env:TEMP\ag-rebuild-settings.json"
[System.IO.File]::WriteAllText($FILE, $BODY, [System.Text.Encoding]::UTF8)
$URL  = "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Web/sites/$APP/config/appsettings?api-version=2022-03-01"
az rest --method PUT --url $URL --body "@$FILE" --output none
Remove-Item $FILE -Force -ErrorAction SilentlyContinue
Write-Host "Settings applied." -ForegroundColor Green

# STEP 4 - Build zip
Write-Host ""
Write-Host "[4/7] Building zip..." -ForegroundColor Yellow
$ZIP = "$env:TEMP\ag-rebuild.zip"
if (Test-Path $ZIP) { Remove-Item $ZIP -Force }

$SKIP_DIRS  = @(".git","deploy",".vscode")
$SKIP_FILES = @(".env","web.config",".deployment","deploy.cmd","deploy.sh","iisnode.yml")
$FILES = Get-ChildItem -Path $PROJ -Recurse -File | Where-Object {
    $rel = $_.FullName.Substring($PROJ.Length).TrimStart("\")
    $top = $rel.Split("\")[0]
    ($SKIP_DIRS -notcontains $top) -and ($SKIP_FILES -notcontains $_.Name)
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$ZS = [System.IO.Compression.ZipFile]::Open($ZIP, "Create")
foreach ($F in $FILES) {
    $E = $F.FullName.Substring($PROJ.Length).TrimStart("\").Replace("\","/")
    try { [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($ZS,$F.FullName,$E,[System.IO.Compression.CompressionLevel]::Optimal)|Out-Null } catch {}
}
$ZS.Dispose()
Write-Host "Zip: $([math]::Round((Get-Item $ZIP).Length/1MB,1)) MB  ($($FILES.Count) files)" -ForegroundColor Green

# STEP 5 - Deploy
Write-Host ""
Write-Host "[5/7] Deploying..." -ForegroundColor Yellow
az webapp deploy --name $APP --resource-group $RG --src-path $ZIP --type zip --output none
$D = $LASTEXITCODE
Remove-Item $ZIP -Force -ErrorAction SilentlyContinue
Write-Host "Deploy exit $D" -ForegroundColor $(if ($D -eq 0) {"Green"} else {"Yellow"})

# STEP 6 - Poll health
Write-Host ""
Write-Host "[6/7] Waiting for site (port binds in <1s)..." -ForegroundColor Yellow
$LIVE = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 15
    try {
        $H = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/api/health" -TimeoutSec 10
        Write-Host ""
        Write-Host "*** SITE IS LIVE ***" -ForegroundColor Green
        Write-Host $($H | ConvertTo-Json -Compress) -ForegroundColor Green
        $LIVE = $true
        break
    } catch { Write-Host "  $(($i+1)*15)s..." -ForegroundColor Gray }
}

# STEP 7 - Seed check
if ($LIVE) {
    Write-Host ""
    Write-Host "[7/7] Checking seed..." -ForegroundColor Yellow
    Start-Sleep -Seconds 25
    try {
        $PC = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/api/products?limit=1" -TimeoutSec 15
        if ($PC.products -and $PC.products.Count -gt 0) {
            Write-Host "Products exist - seed complete!" -ForegroundColor Green
        } else {
            Write-Host "Seed running in background. Wait 60s then open the site." -ForegroundColor Yellow
            Write-Host "Manual seed if needed:" -ForegroundColor Gray
            Write-Host "  https://$APP.scm.azurewebsites.net/DebugConsole" -ForegroundColor Cyan
            Write-Host "  node scripts/seed.js" -ForegroundColor White
        }
    } catch { Write-Host "Products check: $_" -ForegroundColor Yellow }
} else {
    Write-Host ""
    Write-Host "Site not up. Run:" -ForegroundColor Red
    Write-Host "  az webapp log tail --name $APP --resource-group $RG" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  ALL DONE" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host "Site:   https://$APP.azurewebsites.net" -ForegroundColor Cyan
Write-Host "Admin:  https://$APP.azurewebsites.net/admin" -ForegroundColor Cyan
Write-Host "Login:  admin@shieldtechnology.tn / Shield@2025!" -ForegroundColor Cyan
Write-Host ""
