# Ange Gardien - Diagnose: test platform, apply settings, deploy
# Step A: deploy a 1-file minimal server to prove Azure can start Node.js
# Step B: apply settings + deploy real code

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

# -------------------------------------------------------
# PHASE A - Minimal server: prove Azure can run Node at all
# -------------------------------------------------------
Write-Host ""
Write-Host "=== PHASE A: Minimal server test ===" -ForegroundColor Cyan

# Write a zero-dependency server.js to a temp folder
$TMP = "$env:TEMP\ag-minimal"
if (Test-Path $TMP) { Remove-Item $TMP -Recurse -Force }
New-Item -ItemType Directory -Path $TMP | Out-Null

@'
const http = require('http');
const PORT = process.env.PORT || 8080;
http.createServer(function(req, res) {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: true, port: PORT, path: req.url }));
}).listen(PORT, function() {
    console.log('[minimal] listening on ' + PORT);
});
'@ | Set-Content -Path "$TMP\server.js" -Encoding UTF8

# Zip it
$MZIP = "$env:TEMP\ag-minimal.zip"
if (Test-Path $MZIP) { Remove-Item $MZIP -Force }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$ZS = [System.IO.Compression.ZipFile]::Open($MZIP, "Create")
[System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($ZS, "$TMP\server.js", "server.js", [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
$ZS.Dispose()

# Make sure app plan and app exist
az appservice plan show --name $PLAN --resource-group $RG --output none 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Creating App Service Plan..." -ForegroundColor Yellow
    az appservice plan create --name $PLAN --resource-group $RG --location francecentral --sku F1 --is-linux --output none
}
az webapp show --name $APP --resource-group $RG --output none 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Creating Web App..." -ForegroundColor Yellow
    az webapp create --name $APP --resource-group $RG --plan $PLAN --runtime "NODE:22-lts" --output none
}
az webapp config set --name $APP --resource-group $RG --startup-file "node server.js" --output none
az webapp start --name $APP --resource-group $RG --output none

Write-Host "Deploying minimal server (no npm, no DB)..." -ForegroundColor Yellow
az webapp deploy --name $APP --resource-group $RG --src-path $MZIP --type zip --output none
Remove-Item $MZIP -Force -ErrorAction SilentlyContinue

Write-Host "Polling for minimal server (1 min max)..." -ForegroundColor Gray
$MINIMAL_OK = $false
for ($i = 0; $i -lt 8; $i++) {
    Start-Sleep -Seconds 10
    try {
        $R = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/" -TimeoutSec 8
        Write-Host "Minimal server LIVE: $($R | ConvertTo-Json -Compress)" -ForegroundColor Green
        $MINIMAL_OK = $true
        break
    } catch { Write-Host "  $(($i+1)*10)s..." -ForegroundColor Gray }
}

if (-not $MINIMAL_OK) {
    Write-Host ""
    Write-Host "PLATFORM ISSUE: Even a zero-dependency server won't start." -ForegroundColor Red
    Write-Host "This is an Azure F1 platform problem, not a code problem." -ForegroundColor Red
    Write-Host "Run this to get app logs:" -ForegroundColor Yellow
    Write-Host "  az webapp log download --name $APP --resource-group $RG --log-file C:\logs.zip" -ForegroundColor Cyan
    exit 1
}

# -------------------------------------------------------
# PHASE B - Apply settings properly (with retries)
# -------------------------------------------------------
Write-Host ""
Write-Host "=== PHASE B: Applying app settings ===" -ForegroundColor Cyan

$MONGO = $null
for ($t = 1; $t -le 3; $t++) {
    $MONGO = az cosmosdb keys list --name $DB --resource-group $RG --type connection-strings --query "connectionStrings[0].connectionString" --output tsv 2>$null
    if ($MONGO -and $MONGO.Length -gt 20) { Write-Host "Cosmos URI: OK ($($MONGO.Length) chars)" -ForegroundColor Green; break }
    Write-Host "Cosmos key fetch attempt $t failed. Retrying in 10s..." -ForegroundColor Yellow
    Start-Sleep -Seconds 10
}
if (-not $MONGO -or $MONGO.Length -lt 20) {
    Write-Host "Could not get Cosmos connection string after 3 attempts." -ForegroundColor Red
    Write-Host "Check Cosmos DB is running: az cosmosdb show --name $DB --resource-group $RG" -ForegroundColor Yellow
    exit 1
}

$BLOB = az storage account show-connection-string --name $ST --resource-group $RG --query connectionString --output tsv
$JWT  = [System.Guid]::NewGuid().ToString("N") + [System.Guid]::NewGuid().ToString("N")

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
$FILE = "$env:TEMP\ag-diag-settings.json"
[System.IO.File]::WriteAllText($FILE, $BODY, [System.Text.Encoding]::UTF8)
$URL  = "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Web/sites/$APP/config/appsettings?api-version=2022-03-01"
$RESULT = az rest --method PUT --url $URL --body "@$FILE" 2>&1
Remove-Item $FILE -Force -ErrorAction SilentlyContinue

if ($RESULT -match "error" -or $RESULT -match "Bad Request") {
    Write-Host "Settings apply failed: $RESULT" -ForegroundColor Red
    exit 1
}
Write-Host "Settings applied successfully." -ForegroundColor Green

# -------------------------------------------------------
# PHASE C - Deploy real code
# -------------------------------------------------------
Write-Host ""
Write-Host "=== PHASE C: Deploying real app ===" -ForegroundColor Cyan

$ZIP = "$env:TEMP\ag-real.zip"
if (Test-Path $ZIP) { Remove-Item $ZIP -Force }

$SKIP_DIRS  = @(".git","deploy",".vscode")
$SKIP_FILES = @(".env","web.config",".deployment","deploy.cmd","deploy.sh","iisnode.yml")
$FILES = Get-ChildItem -Path $PROJ -Recurse -File | Where-Object {
    $rel = $_.FullName.Substring($PROJ.Length).TrimStart("\")
    $top = $rel.Split("\")[0]
    ($SKIP_DIRS -notcontains $top) -and ($SKIP_FILES -notcontains $_.Name)
}
Write-Host "Files: $($FILES.Count)" -ForegroundColor Gray
$ZS = [System.IO.Compression.ZipFile]::Open($ZIP, "Create")
foreach ($F in $FILES) {
    $E = $F.FullName.Substring($PROJ.Length).TrimStart("\").Replace("\","/")
    try { [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($ZS,$F.FullName,$E,[System.IO.Compression.CompressionLevel]::Optimal)|Out-Null } catch {}
}
$ZS.Dispose()
Write-Host "Zip: $([math]::Round((Get-Item $ZIP).Length/1MB,1)) MB" -ForegroundColor Green

Write-Host "Deploying real code..." -ForegroundColor Yellow
az webapp deploy --name $APP --resource-group $RG --src-path $ZIP --type zip --output none
Remove-Item $ZIP -Force -ErrorAction SilentlyContinue

Write-Host "Restarting app..." -ForegroundColor Gray
az webapp restart --name $APP --resource-group $RG --output none

Write-Host ""
Write-Host "=== Polling health (5 min) ===" -ForegroundColor Cyan
$LIVE = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 15
    try {
        $H = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/api/health" -TimeoutSec 10
        Write-Host ""
        Write-Host "LIVE: $($H | ConvertTo-Json -Compress)" -ForegroundColor Green
        $LIVE = $true
        break
    } catch { Write-Host "  $(($i+1)*15)s..." -ForegroundColor Gray }
}

if (-not $LIVE) {
    Write-Host "Still not up. Download logs:" -ForegroundColor Red
    Write-Host "  az webapp log download --name $APP --resource-group $RG --log-file C:\Users\DELL\Desktop\azure-logs.zip" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  DONE" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host "Site:   https://$APP.azurewebsites.net" -ForegroundColor Cyan
Write-Host "Admin:  https://$APP.azurewebsites.net/admin" -ForegroundColor Cyan
Write-Host "Login:  admin@shieldtechnology.tn / Shield@2025!" -ForegroundColor Cyan
Write-Host ""
