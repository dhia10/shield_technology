# Ange Gardien - STOP → Deploy → START
# KEY INSIGHT: stop the app before deploying so it never tries to start
# with missing code. Only starts AFTER code + settings are both in place.
# Also: global uncaughtException + unhandledRejection handlers added to server.js
# to prevent Node 22 from exiting on any async error.

$ErrorActionPreference = "Continue"
$SUB  = "dd304ca8-be36-4ad8-a6e0-34f6f9be2698"
$RG   = "ange-gardien-rg"
$PLAN = "ange-gardien-plan"
$APP  = "ange-gardien-web"
$DB   = "ange-gardiendb01"
$ST   = "angegardienblob01"
$CTR  = "shield-media"
$PROJ = Split-Path -Parent $PSScriptRoot

az account set --subscription $SUB

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  ANGE GARDIEN - Stop-Deploy-Start" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# ── STEP 1: Clean slate ──────────────────────────────────────────────────────
Write-Host ""
Write-Host "[1] Deleting app (keep plan)..." -ForegroundColor Yellow
az webapp delete --name $APP --resource-group $RG --keep-empty-plan 2>$null
Start-Sleep -Seconds 15

# ── STEP 2: Ensure plan ──────────────────────────────────────────────────────
Write-Host "[2] Ensuring App Service Plan..." -ForegroundColor Yellow
az appservice plan show --name $PLAN --resource-group $RG --output none 2>$null
if ($LASTEXITCODE -ne 0) {
    az appservice plan create --name $PLAN --resource-group $RG --location francecentral --sku F1 --is-linux --output none
    Write-Host "    Plan created." -ForegroundColor Green
} else {
    Write-Host "    Plan OK." -ForegroundColor Gray
}

# ── STEP 3: Create app ───────────────────────────────────────────────────────
Write-Host "[3] Creating web app..." -ForegroundColor Yellow
az webapp create --name $APP --resource-group $RG --plan $PLAN --runtime "NODE:22-lts" --output none
Write-Host "    Created." -ForegroundColor Green

# ── STEP 4: STOP the app immediately (before it tries to start with no code) ─
Write-Host "[4] Stopping app before any code is deployed..." -ForegroundColor Yellow
az webapp stop --name $APP --resource-group $RG --output none
Write-Host "    App stopped." -ForegroundColor Green
Start-Sleep -Seconds 10

# ── STEP 5: Apply ALL settings while app is stopped ─────────────────────────
Write-Host "[5] Fetching Cosmos DB connection string..." -ForegroundColor Yellow
$MONGO = $null
for ($t = 1; $t -le 5; $t++) {
    $MONGO = az cosmosdb keys list --name $DB --resource-group $RG --type connection-strings `
        --query "connectionStrings[0].connectionString" --output tsv 2>$null
    if ($MONGO -and $MONGO.Length -gt 20) {
        Write-Host "    Cosmos URI: OK ($($MONGO.Length) chars)" -ForegroundColor Green
        break
    }
    Write-Host "    Attempt $t failed, waiting 10s..." -ForegroundColor Yellow
    Start-Sleep -Seconds 10
}
if (-not $MONGO -or $MONGO.Length -lt 20) {
    Write-Host "    ERROR: Cannot get Cosmos connection string!" -ForegroundColor Red
    exit 1
}

$BLOB = az storage account show-connection-string --name $ST --resource-group $RG --query connectionString --output tsv
$JWT  = [System.Guid]::NewGuid().ToString("N") + [System.Guid]::NewGuid().ToString("N")

Write-Host "[5b] Applying app settings + startup command..." -ForegroundColor Yellow

# Set startup command
az webapp config set --name $APP --resource-group $RG --startup-file "node server.js" --output none
Write-Host "    Startup: node server.js" -ForegroundColor Gray

# Apply env vars via REST (avoids PowerShell | and & parsing issues)
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
$FILE = "$env:TEMP\ag-stop-settings.json"
[System.IO.File]::WriteAllText($FILE, $BODY, [System.Text.Encoding]::UTF8)
$URL  = "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Web/sites/$APP/config/appsettings?api-version=2022-03-01"
$OUT  = az rest --method PUT --url $URL --body "@$FILE" 2>&1
Remove-Item $FILE -Force -ErrorAction SilentlyContinue

if ($OUT -match '"error"' -or $OUT -match "BadRequest") {
    Write-Host "    Settings warning: $OUT" -ForegroundColor Yellow
} else {
    Write-Host "    Settings applied." -ForegroundColor Green
}

# Enable Basic Auth on Kudu SCM
az resource update --resource-group $RG --name scm --namespace Microsoft.Web `
    --resource-type basicPublishingCredentialsPolicies `
    --parent "sites/$APP" --set properties.allow=true --output none 2>$null
Write-Host "    Kudu Basic Auth enabled." -ForegroundColor Gray

# ── STEP 6: Build zip ────────────────────────────────────────────────────────
Write-Host ""
Write-Host "[6] Building deployment zip (with node_modules)..." -ForegroundColor Yellow
$ZIP = "$env:TEMP\ag-stop-deploy.zip"
if (Test-Path $ZIP) { Remove-Item $ZIP -Force }

$SKIP_DIRS  = @(".git", "deploy", ".vscode")
$SKIP_FILES = @(".env", "web.config", ".deployment", "deploy.cmd", "deploy.sh", "iisnode.yml")
$FILES = Get-ChildItem -Path $PROJ -Recurse -File | Where-Object {
    $rel = $_.FullName.Substring($PROJ.Length).TrimStart("\")
    $top = $rel.Split("\")[0]
    ($SKIP_DIRS -notcontains $top) -and ($SKIP_FILES -notcontains $_.Name)
}
Write-Host "    $($FILES.Count) files" -ForegroundColor Gray

Add-Type -AssemblyName System.IO.Compression.FileSystem
$ZS = [System.IO.Compression.ZipFile]::Open($ZIP, "Create")
foreach ($F in $FILES) {
    $E = $F.FullName.Substring($PROJ.Length).TrimStart("\").Replace("\", "/")
    try {
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $ZS, $F.FullName, $E,
            [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
    } catch {}
}
$ZS.Dispose()
$SizeMB = [math]::Round((Get-Item $ZIP).Length / 1MB, 1)
Write-Host "    Zip: $SizeMB MB" -ForegroundColor Green

# ── STEP 7: Deploy code ASYNC (don't wait for startup - app is stopped) ──────
Write-Host ""
Write-Host "[7] Uploading code (async - app is stopped, no startup race)..." -ForegroundColor Yellow
az webapp deploy --name $APP --resource-group $RG --src-path $ZIP --type zip --async true --output none
$D = $LASTEXITCODE
Remove-Item $ZIP -Force -ErrorAction SilentlyContinue
Write-Host "    Deploy initiated (exit: $D)" -ForegroundColor $(if ($D -eq 0) {"Green"} else {"Yellow"})

# Wait for Kudu to finish extracting (zip deploy is fast without npm install)
Write-Host "    Waiting 60s for Kudu to finish extraction..." -ForegroundColor Gray
Start-Sleep -Seconds 60

# ── STEP 8: START the app (code + settings both in place now) ────────────────
Write-Host ""
Write-Host "[8] Starting app (code deployed, settings applied)..." -ForegroundColor Yellow
az webapp start --name $APP --resource-group $RG --output none
Write-Host "    Start command sent." -ForegroundColor Green

# ── STEP 9: Poll health ──────────────────────────────────────────────────────
Write-Host ""
Write-Host "[9] Polling /api/health (up to 10 min)..." -ForegroundColor Yellow
$LIVE = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 15
    try {
        $H = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/api/health" -TimeoutSec 10
        Write-Host ""
        Write-Host "*** SITE IS LIVE ***" -ForegroundColor Green
        Write-Host $($H | ConvertTo-Json -Compress) -ForegroundColor Green
        $LIVE = $true
        break
    } catch {
        $secs = ($i + 1) * 15
        Write-Host "  ${secs}s - not up yet..." -ForegroundColor Gray
    }
}

if (-not $LIVE) {
    Write-Host ""
    Write-Host "Still not up after 10 min. Fetching live logs..." -ForegroundColor Red
    Write-Host ""
    Write-Host "Run this to tail logs:" -ForegroundColor Yellow
    Write-Host "  az webapp log tail --name $APP --resource-group $RG" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Or download logs:" -ForegroundColor Yellow
    Write-Host "  az webapp log download --name $APP --resource-group $RG --log-file C:\Users\DELL\Desktop\azure-logs.zip" -ForegroundColor Cyan
} else {
    # Quick seed check
    Write-Host ""
    Write-Host "[10] Checking products (seed verification)..." -ForegroundColor Yellow
    Start-Sleep -Seconds 20
    try {
        $PC = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/api/products?limit=1" -TimeoutSec 15
        if ($PC.products -and $PC.products.Count -gt 0) {
            Write-Host "    Products seeded OK ($($PC.count) total)" -ForegroundColor Green
        } else {
            Write-Host "    Seed running in background. Wait 60s then open the site." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "    Products check: $_ (seed may still be running)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  DONE" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host "Site:   https://$APP.azurewebsites.net" -ForegroundColor Cyan
Write-Host "Admin:  https://$APP.azurewebsites.net/admin" -ForegroundColor Cyan
Write-Host "Login:  admin@shieldtechnology.tn / Shield@2025!" -ForegroundColor Cyan
Write-Host ""
