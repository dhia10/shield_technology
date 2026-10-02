# Ange Gardien - Fix4: Use confirmed runtime NODE:22-lts
# Runtime list confirmed: NODE:24-lts, NODE:22-lts are available.
# Using NODE:22-lts (stable LTS).

$ErrorActionPreference = "Continue"

$SUB  = "dd304ca8-be36-4ad8-a6e0-34f6f9be2698"
$RG   = "ange-gardien-rg"
$PLAN = "ange-gardien-plan"
$APP  = "ange-gardien-web"
$DB   = "ange-gardiendb01"
$ST   = "angegardienblob01"
$CTR  = "shield-media"

az account set --subscription $SUB
Write-Host "Subscription set." -ForegroundColor Green

# -------------------------------------------------------
# STEP 1 - Create Web App with confirmed runtime
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 1: Creating Web App ===" -ForegroundColor Cyan

az webapp show --name $APP --resource-group $RG --output none 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Web App already exists, skipping create." -ForegroundColor Gray
} else {
    Write-Host "Creating with NODE:22-lts..." -ForegroundColor Yellow
    az webapp create --name $APP --resource-group $RG --plan $PLAN --runtime "NODE:22-lts" --output table
    if ($LASTEXITCODE -ne 0) {
        Write-Host "NODE:22-lts failed, trying NODE:24-lts..." -ForegroundColor Yellow
        az webapp create --name $APP --resource-group $RG --plan $PLAN --runtime "NODE:24-lts" --output table
    }
}

az webapp show --name $APP --resource-group $RG --output none 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "FATAL: Web App still not created. Create it manually:" -ForegroundColor Red
    Write-Host "  Portal -> App Services -> Create" -ForegroundColor Yellow
    Write-Host "  Name: ange-gardien-web  |  RG: ange-gardien-rg" -ForegroundColor Yellow
    Write-Host "  Runtime: Node 22 LTS, Linux  |  Plan: ange-gardien-plan" -ForegroundColor Yellow
    Write-Host "  Then re-run this script." -ForegroundColor Yellow
    exit 1
}
Write-Host "Web App ready." -ForegroundColor Green

az webapp config set --name $APP --resource-group $RG --startup-file "node server.js" --output none
Write-Host "Startup command set." -ForegroundColor Green

# -------------------------------------------------------
# STEP 2 - Get connection strings
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 2: Getting connection strings ===" -ForegroundColor Cyan

$MONGO = az cosmosdb keys list --name $DB --resource-group $RG --type connection-strings --query "connectionStrings[0].connectionString" --output tsv
Write-Host "Cosmos DB: OK" -ForegroundColor Green

$BLOB = az storage account show-connection-string --name $ST --resource-group $RG --query connectionString --output tsv
Write-Host "Storage:   OK" -ForegroundColor Green

# -------------------------------------------------------
# STEP 3 - Set App Settings via REST (avoids & parse issue)
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 3: Setting environment variables ===" -ForegroundColor Cyan

$JWT = [System.Guid]::NewGuid().ToString("N") + [System.Guid]::NewGuid().ToString("N")

$PROPS = [ordered]@{
    MONGODB_URI = $MONGO
    AZURE_STORAGE_CONNECTION_STRING = $BLOB
    AZURE_STORAGE_CONTAINER = $CTR
    JWT_SECRET = $JWT
    NODE_ENV = "production"
    ADMIN_EMAIL = "admin@shieldtechnology.tn"
    ADMIN_PASSWORD = "Shield@2025!"
    WEBSITE_NODE_DEFAULT_VERSION = "~22"
    SCM_DO_BUILD_DURING_DEPLOYMENT = "true"
}

$BODY = (@{ properties = $PROPS } | ConvertTo-Json -Depth 5)
$FILE = "$env:TEMP\ag-s4.json"
[System.IO.File]::WriteAllText($FILE, $BODY, [System.Text.Encoding]::UTF8)
$URL = "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Web/sites/$APP/config/appsettings?api-version=2022-03-01"
az rest --method PUT --url $URL --body "@$FILE" --output none
Remove-Item $FILE -Force -ErrorAction SilentlyContinue
Write-Host "Environment variables set." -ForegroundColor Green

# -------------------------------------------------------
# STEP 4 - Deploy code
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 4: Deploying code ===" -ForegroundColor Cyan

$PROJ = Split-Path -Parent $PSScriptRoot
$ZIP  = "$env:TEMP\ag-fix4.zip"
if (Test-Path $ZIP) { Remove-Item $ZIP -Force }

$SKIP_DIRS  = @("node_modules",".git","deploy",".vscode")
$SKIP_FILES = @(".env")

$FILES = Get-ChildItem -Path $PROJ -Recurse -File | Where-Object {
    $rel = $_.FullName.Substring($PROJ.Length).TrimStart("\")
    $top = $rel.Split("\")[0]
    ($SKIP_DIRS -notcontains $top) -and ($SKIP_FILES -notcontains $_.Name)
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$ZS = [System.IO.Compression.ZipFile]::Open($ZIP, "Create")
foreach ($F in $FILES) {
    $E = $F.FullName.Substring($PROJ.Length).TrimStart("\").Replace("\","/")
    [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($ZS, $F.FullName, $E, [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
}
$ZS.Dispose()
Write-Host "Zip: $([math]::Round((Get-Item $ZIP).Length/1KB)) KB" -ForegroundColor Gray

az webapp deploy --name $APP --resource-group $RG --src-path $ZIP --type zip --output table
Remove-Item $ZIP -Force -ErrorAction SilentlyContinue
Write-Host "Code deployed." -ForegroundColor Green

# -------------------------------------------------------
# STEP 5 - Seed database
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 5: Seeding database (waiting 55s for app boot) ===" -ForegroundColor Cyan
Start-Sleep -Seconds 55

$PROFS = az webapp deployment list-publishing-profiles --name $APP --resource-group $RG | ConvertFrom-Json
$P = $PROFS | Where-Object { $_.publishMethod -eq "MSDeploy" } | Select-Object -First 1

if ($P) {
    $CRED = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("$($P.userName):$($P.userPWD)"))
    $SEED = '{"command":"node scripts/seed.js","dir":"site\\wwwroot"}'
    try {
        $R = Invoke-RestMethod -Uri "https://$APP.scm.azurewebsites.net/api/command" -Method Post -Headers @{ "Authorization" = "Basic $CRED"; "Content-Type" = "application/json" } -Body $SEED -TimeoutSec 120
        Write-Host "Database seeded!" -ForegroundColor Green
        Write-Host $R.Output
    } catch {
        Write-Host "Auto-seed skipped. Seed manually:" -ForegroundColor Yellow
        Write-Host "  1. https://$APP.scm.azurewebsites.net/DebugConsole" -ForegroundColor Cyan
        Write-Host "  2. node scripts/seed.js" -ForegroundColor Cyan
    }
} else {
    Write-Host "No Kudu credentials. Seed manually:" -ForegroundColor Yellow
    Write-Host "  https://$APP.scm.azurewebsites.net/DebugConsole" -ForegroundColor Cyan
}

# -------------------------------------------------------
# DONE
# -------------------------------------------------------
Write-Host ""
Write-Host "=======================================" -ForegroundColor Green
Write-Host "  ALL DONE!" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Green
Write-Host ""
Write-Host "Site:   https://$APP.azurewebsites.net" -ForegroundColor Cyan
Write-Host "Admin:  https://$APP.azurewebsites.net/admin" -ForegroundColor Cyan
Write-Host "Login:  admin@shieldtechnology.tn / Shield@2025!" -ForegroundColor Cyan
Write-Host ""
Write-Host "Logs:   az webapp log tail --name $APP --resource-group $RG" -ForegroundColor Gray
Write-Host ""
