# Ange Gardien - Final Deploy 3
# Fix: connectDB() no longer calls process.exit(1)
# It retries 5x with backoff, then continues without DB (no more crash).

$ErrorActionPreference = "Continue"

$SUB = "dd304ca8-be36-4ad8-a6e0-34f6f9be2698"
$RG  = "ange-gardien-rg"
$APP = "ange-gardien-web"
$PROJ = Split-Path -Parent $PSScriptRoot

az account set --subscription $SUB

# -------------------------------------------------------
# STEP 1 - Verify MONGODB_URI is set in app settings
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 1: Verifying app settings ===" -ForegroundColor Cyan

$SETTINGS = az webapp config appsettings list --name $APP --resource-group $RG | ConvertFrom-Json
$MONGO_SET = $SETTINGS | Where-Object { $_.name -eq "MONGODB_URI" }

if ($MONGO_SET -and $MONGO_SET.value) {
    $PREVIEW = $MONGO_SET.value.Substring(0, [Math]::Min(60, $MONGO_SET.value.Length))
    Write-Host "MONGODB_URI is set: $PREVIEW..." -ForegroundColor Green
} else {
    Write-Host "MONGODB_URI is MISSING - re-fetching and setting..." -ForegroundColor Red
    $DB = "ange-gardiendb01"
    $ST = "angegardienblob01"
    $MONGO = az cosmosdb keys list --name $DB --resource-group $RG --type connection-strings --query "connectionStrings[0].connectionString" --output tsv
    $BLOB  = az storage account show-connection-string --name $ST --resource-group $RG --query connectionString --output tsv
    $JWT   = [System.Guid]::NewGuid().ToString("N") + [System.Guid]::NewGuid().ToString("N")

    $PROPS = [ordered]@{
        MONGODB_URI = $MONGO
        AZURE_STORAGE_CONNECTION_STRING = $BLOB
        AZURE_STORAGE_CONTAINER = "shield-media"
        JWT_SECRET = $JWT
        NODE_ENV = "production"
        ADMIN_EMAIL = "admin@shieldtechnology.tn"
        ADMIN_PASSWORD = "Shield@2025!"
        WEBSITE_NODE_DEFAULT_VERSION = "~22"
        SCM_DO_BUILD_DURING_DEPLOYMENT = "false"
    }
    $BODY = (@{ properties = $PROPS } | ConvertTo-Json -Depth 5)
    $FILE = "$env:TEMP\ag-resettings.json"
    [System.IO.File]::WriteAllText($FILE, $BODY, [System.Text.Encoding]::UTF8)
    $URL = "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Web/sites/$APP/config/appsettings?api-version=2022-03-01"
    az rest --method PUT --url $URL --body "@$FILE" --output none
    Remove-Item $FILE -Force -ErrorAction SilentlyContinue
    Write-Host "App settings re-applied." -ForegroundColor Green
}

# -------------------------------------------------------
# STEP 2 - Build zip with fixed config/database.js
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 2: Building zip ===" -ForegroundColor Cyan

$ZIP = "$env:TEMP\ag-final3.zip"
if (Test-Path $ZIP) { Remove-Item $ZIP -Force }

$SKIP_DIRS  = @(".git","deploy",".vscode")
$SKIP_FILES = @(".env","web.config",".deployment","deploy.cmd","deploy.sh","iisnode.yml")

$FILES = Get-ChildItem -Path $PROJ -Recurse -File | Where-Object {
    $rel = $_.FullName.Substring($PROJ.Length).TrimStart("\")
    $top = $rel.Split("\")[0]
    ($SKIP_DIRS -notcontains $top) -and ($SKIP_FILES -notcontains $_.Name)
}

Write-Host "Files: $($FILES.Count)" -ForegroundColor Gray
Add-Type -AssemblyName System.IO.Compression.FileSystem
$ZS = [System.IO.Compression.ZipFile]::Open($ZIP, "Create")
foreach ($F in $FILES) {
    $E = $F.FullName.Substring($PROJ.Length).TrimStart("\").Replace("\","/")
    try {
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($ZS, $F.FullName, $E, [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
    } catch { }
}
$ZS.Dispose()
Write-Host "Zip: $([math]::Round((Get-Item $ZIP).Length/1MB,1)) MB" -ForegroundColor Green

# -------------------------------------------------------
# STEP 3 - Start app + deploy
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 3: Starting app + deploying ===" -ForegroundColor Cyan

az webapp start --name $APP --resource-group $RG --output none
Start-Sleep -Seconds 10

Write-Host "Uploading..." -ForegroundColor Yellow
az webapp deploy --name $APP --resource-group $RG --src-path $ZIP --type zip --output none
$D = $LASTEXITCODE
Remove-Item $ZIP -Force -ErrorAction SilentlyContinue
Write-Host "Deploy exit code: $D" -ForegroundColor Gray

# -------------------------------------------------------
# STEP 4 - Poll health (7 min max - includes DB retry time)
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 4: Waiting for app (7 min max) ===" -ForegroundColor Cyan
Write-Host "DB connect retries up to 5x with backoff - may take 2-3 min." -ForegroundColor Gray

$LIVE = $false
for ($i = 0; $i -lt 28; $i++) {
    Start-Sleep -Seconds 15
    try {
        $H = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/api/health" -TimeoutSec 10
        Write-Host ""
        Write-Host "SITE IS LIVE!" -ForegroundColor Green
        Write-Host "$($H | ConvertTo-Json -Compress)" -ForegroundColor Green
        $LIVE = $true
        break
    } catch {
        $elapsed = ($i + 1) * 15
        Write-Host "  ${elapsed}s - still starting (DB connecting)..." -ForegroundColor Gray
    }
}

# -------------------------------------------------------
# STEP 5 - Seed database via Kudu if live
# -------------------------------------------------------
$PROFS = az webapp deployment list-publishing-profiles --name $APP --resource-group $RG | ConvertFrom-Json
$P = $PROFS | Where-Object { $_.publishMethod -eq "MSDeploy" } | Select-Object -First 1

if ($LIVE -and $P) {
    $CRED = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("$($P.userName):$($P.userPWD)"))
    Write-Host ""
    Write-Host "=== STEP 5: Verifying database seed ===" -ForegroundColor Cyan
    try {
        $PC = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/api/products?limit=1" -TimeoutSec 15
        if ($PC.products -and $PC.products.Count -gt 0) {
            Write-Host "Products found in DB - seed already ran!" -ForegroundColor Green
        } else {
            Write-Host "No products yet - running seed via Kudu..." -ForegroundColor Yellow
            $SEED = '{"command":"node scripts/seed.js","dir":"site\\wwwroot"}'
            $R = Invoke-RestMethod -Uri "https://$APP.scm.azurewebsites.net/api/command" -Method Post `
                -Headers @{ "Authorization" = "Basic $CRED"; "Content-Type" = "application/json" } `
                -Body $SEED -TimeoutSec 120
            Write-Host "Seeded! $($R.Output)" -ForegroundColor Green
        }
    } catch {
        Write-Host "Seed check failed: $_" -ForegroundColor Yellow
        Write-Host "If auto-seed didn't run, open Kudu console:" -ForegroundColor Yellow
        Write-Host "  https://$APP.scm.azurewebsites.net/DebugConsole" -ForegroundColor Cyan
        Write-Host "  node scripts/seed.js" -ForegroundColor White
    }
}

if (-not $LIVE) {
    Write-Host ""
    Write-Host "Site still not responding. Fetch logs with:" -ForegroundColor Red
    Write-Host "  az webapp log tail --name $APP --resource-group $RG" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "=======================================" -ForegroundColor Green
Write-Host "  DONE!" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Green
Write-Host "Site:   https://$APP.azurewebsites.net" -ForegroundColor Cyan
Write-Host "Admin:  https://$APP.azurewebsites.net/admin" -ForegroundColor Cyan
Write-Host "Login:  admin@shieldtechnology.tn / Shield@2025!" -ForegroundColor Cyan
Write-Host ""
