# Ange Gardien - Linux Clean Deploy
#
# ROOT CAUSE FIX: node_modules installed on Windows cannot run on Linux.
# Even pure-JS packages can fail because npm may compile optional native
# bindings on Windows that produce broken .node files for Linux.
# Solution: deploy SOURCE ONLY (no node_modules) and let Azure/Oryx run
# npm install natively on Linux — correct binaries, correct environment.
#
# Sequence:
# 1. Delete + recreate app
# 2. Apply all settings (SCM_DO_BUILD_DURING_DEPLOYMENT=true this time)
# 3. Set startup command
# 4. STOP app
# 5. Deploy zip WITHOUT node_modules (small, fast upload)
# 6. Oryx runs npm install during the build step (~2-3 min)
# 7. START app (code + fresh Linux node_modules ready)
# 8. Poll health

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
Write-Host "  ANGE GARDIEN - Linux Clean Deploy" -ForegroundColor Cyan
Write-Host "  (no Windows node_modules, Oryx npm install)" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# ── STEP 1: Clean slate ──────────────────────────────────────────────────────
Write-Host ""
Write-Host "[1] Deleting app (keep plan)..." -ForegroundColor Yellow
az webapp delete --name $APP --resource-group $RG --keep-empty-plan 2>$null
Start-Sleep -Seconds 15

# ── STEP 2: Ensure plan ──────────────────────────────────────────────────────
Write-Host "[2] App Service Plan..." -ForegroundColor Yellow
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

# ── STEP 4: STOP immediately (no premature start) ────────────────────────────
Write-Host "[4] Stopping app immediately..." -ForegroundColor Yellow
az webapp stop --name $APP --resource-group $RG --output none
Write-Host "    Stopped." -ForegroundColor Green
Start-Sleep -Seconds 5

# ── STEP 5: Apply ALL settings ───────────────────────────────────────────────
Write-Host "[5] Fetching Cosmos DB connection string..." -ForegroundColor Yellow
$MONGO = $null
for ($t = 1; $t -le 5; $t++) {
    $MONGO = az cosmosdb keys list --name $DB --resource-group $RG --type connection-strings `
        --query "connectionStrings[0].connectionString" --output tsv 2>$null
    if ($MONGO -and $MONGO.Length -gt 20) {
        Write-Host "    Cosmos URI: OK ($($MONGO.Length) chars)" -ForegroundColor Green; break
    }
    Write-Host "    Attempt $t failed, retrying in 10s..." -ForegroundColor Yellow
    Start-Sleep -Seconds 10
}
if (-not $MONGO -or $MONGO.Length -lt 20) {
    Write-Host "    FATAL: Cannot get Cosmos connection string." -ForegroundColor Red; exit 1
}

$BLOB = az storage account show-connection-string --name $ST --resource-group $RG --query connectionString --output tsv
$JWT  = [System.Guid]::NewGuid().ToString("N") + [System.Guid]::NewGuid().ToString("N")

Write-Host "[5b] Setting startup command..." -ForegroundColor Yellow
az webapp config set --name $APP --resource-group $RG --startup-file "node server.js" --output none
Write-Host "    startup-file = node server.js" -ForegroundColor Gray

Write-Host "[5c] Applying environment variables..." -ForegroundColor Yellow
$PROPS = [ordered]@{
    MONGODB_URI                     = $MONGO
    AZURE_STORAGE_CONNECTION_STRING = $BLOB
    AZURE_STORAGE_CONTAINER         = $CTR
    JWT_SECRET                      = $JWT
    NODE_ENV                        = "production"
    ADMIN_EMAIL                     = "admin@shieldtechnology.tn"
    ADMIN_PASSWORD                  = "Shield@2025!"
    WEBSITE_NODE_DEFAULT_VERSION    = "~22"
    SCM_DO_BUILD_DURING_DEPLOYMENT  = "true"
    ENABLE_ORYX_BUILD               = "true"
    NPM_CONFIG_PRODUCTION           = "true"
}
$BODY = (@{ properties = $PROPS } | ConvertTo-Json -Depth 5)
$FILE = "$env:TEMP\ag-linux-settings.json"
[System.IO.File]::WriteAllText($FILE, $BODY, [System.Text.Encoding]::UTF8)
$URL  = "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Web/sites/$APP/config/appsettings?api-version=2022-03-01"
$OUT  = az rest --method PUT --url $URL --body "@$FILE" 2>&1
Remove-Item $FILE -Force -ErrorAction SilentlyContinue
if ($OUT -match '"error"' -or $OUT -match "BadRequest") {
    Write-Host "    Settings warning: $OUT" -ForegroundColor Yellow
} else {
    Write-Host "    Settings applied." -ForegroundColor Green
}

# Enable Kudu Basic Auth
az resource update --resource-group $RG --name scm --namespace Microsoft.Web `
    --resource-type basicPublishingCredentialsPolicies `
    --parent "sites/$APP" --set properties.allow=true --output none 2>$null
Write-Host "    Kudu auth enabled." -ForegroundColor Gray

# ── STEP 6: Build zip WITHOUT node_modules ───────────────────────────────────
Write-Host ""
Write-Host "[6] Building zip (SOURCE ONLY - no node_modules)..." -ForegroundColor Yellow
$ZIP = "$env:TEMP\ag-linux-clean.zip"
if (Test-Path $ZIP) { Remove-Item $ZIP -Force }

# Exclude node_modules so Oryx installs fresh on Linux
$SKIP_DIRS  = @(".git", "deploy", ".vscode", "node_modules")
$SKIP_FILES = @(".env", "web.config", ".deployment", "deploy.cmd", "deploy.sh", "iisnode.yml")
$FILES = Get-ChildItem -Path $PROJ -Recurse -File | Where-Object {
    $rel = $_.FullName.Substring($PROJ.Length).TrimStart("\")
    $top = $rel.Split("\")[0]
    ($SKIP_DIRS -notcontains $top) -and ($SKIP_FILES -notcontains $_.Name)
}
Write-Host "    $($FILES.Count) files (no node_modules)" -ForegroundColor Gray

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
$SizeMB = [math]::Round((Get-Item $ZIP).Length / 1MB, 2)
Write-Host "    Zip: $SizeMB MB - uploading..." -ForegroundColor Green

# ── STEP 7: Deploy (Oryx will npm install on Linux) ──────────────────────────
Write-Host ""
Write-Host "[7] Deploying + Oryx npm install (may take 3-5 min)..." -ForegroundColor Yellow
Write-Host "    (watch for 'Running npm install' in the build output)" -ForegroundColor Gray
az webapp deploy --name $APP --resource-group $RG --src-path $ZIP --type zip --output none
$D = $LASTEXITCODE
Remove-Item $ZIP -Force -ErrorAction SilentlyContinue
Write-Host "    Deploy exit: $D" -ForegroundColor $(if ($D -eq 0) {"Green"} else {"Yellow"})

# ── STEP 8: START the app ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "[8] Starting app..." -ForegroundColor Yellow
az webapp start --name $APP --resource-group $RG --output none
Write-Host "    Start sent. Giving it 30s to initialise..." -ForegroundColor Gray
Start-Sleep -Seconds 30

# ── STEP 9: Poll health (up to 10 min) ───────────────────────────────────────
Write-Host ""
Write-Host "[9] Polling /api/health..." -ForegroundColor Yellow
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
        Write-Host "  $(($i+1)*15)s..." -ForegroundColor Gray
    }
}

if (-not $LIVE) {
    Write-Host ""
    Write-Host "Still not up. Fetching container log via REST API..." -ForegroundColor Red

    # Try to get the last 100 lines of the docker log via REST (bypasses SCM/Kudu lock)
    try {
        $logUrl = "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Web/sites/$APP/logs/docker?api-version=2022-03-01"
        $logResult = az rest --method GET --url $logUrl 2>&1
        if ($logResult -and $logResult.Length -gt 10) {
            Write-Host "=== Container log snippet ===" -ForegroundColor Cyan
            Write-Host $logResult -ForegroundColor White
        }
    } catch {}

    Write-Host ""
    Write-Host "Also try these manually:" -ForegroundColor Yellow
    Write-Host "  az webapp log tail --name $APP --resource-group $RG" -ForegroundColor Cyan
    Write-Host "  az webapp log download --name $APP --resource-group $RG --log-file C:\Users\DELL\Desktop\azure-logs.zip" -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "[10] Seed check..." -ForegroundColor Yellow
    Start-Sleep -Seconds 20
    try {
        $PC = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/api/products?limit=1" -TimeoutSec 15
        if ($PC.products -and $PC.products.Count -gt 0) {
            Write-Host "    Products OK - seed ran! ($($PC.count) products total)" -ForegroundColor Green
        } else {
            Write-Host "    Seed still running - wait 60s then visit the site." -ForegroundColor Yellow
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
