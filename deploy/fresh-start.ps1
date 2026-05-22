# Ange Gardien - Fresh Start
# Delete crashed web app, recreate clean, deploy fixed code.
# Cosmos DB and Blob Storage are NOT touched.

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
# STEP 1 - Delete crashed web app
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 1: Deleting crashed web app ===" -ForegroundColor Cyan
az webapp delete --name $APP --resource-group $RG --output none
Write-Host "Deleted. Waiting 20s for Azure to clean up..." -ForegroundColor Gray
Start-Sleep -Seconds 20

# -------------------------------------------------------
# STEP 2 - Recreate fresh web app
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 2: Recreating web app ===" -ForegroundColor Cyan
az webapp create --name $APP --resource-group $RG --plan $PLAN --runtime "NODE:22-lts" --output table
az webapp config set --name $APP --resource-group $RG --startup-file "node server.js" --output none
Write-Host "Web app recreated." -ForegroundColor Green

# -------------------------------------------------------
# STEP 3 - Enable Basic Auth for Kudu
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 3: Enabling Kudu Basic Auth ===" -ForegroundColor Cyan
az resource update --resource-group $RG --name scm --namespace Microsoft.Web `
    --resource-type basicPublishingCredentialsPolicies `
    --parent "sites/$APP" --set properties.allow=true --output none
Write-Host "Basic Auth enabled." -ForegroundColor Green

# -------------------------------------------------------
# STEP 4 - Get connection strings and set all app settings
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 4: Applying app settings ===" -ForegroundColor Cyan

$MONGO = az cosmosdb keys list --name $DB --resource-group $RG --type connection-strings --query "connectionStrings[0].connectionString" --output tsv
$BLOB  = az storage account show-connection-string --name $ST --resource-group $RG --query connectionString --output tsv
$JWT   = [System.Guid]::NewGuid().ToString("N") + [System.Guid]::NewGuid().ToString("N")

Write-Host "Cosmos DB URI: $($MONGO.Substring(0, [Math]::Min(50,$MONGO.Length)))..." -ForegroundColor Gray

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
$FILE = "$env:TEMP\ag-fresh-settings.json"
[System.IO.File]::WriteAllText($FILE, $BODY, [System.Text.Encoding]::UTF8)
$URL = "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Web/sites/$APP/config/appsettings?api-version=2022-03-01"
az rest --method PUT --url $URL --body "@$FILE" --output none
Remove-Item $FILE -Force -ErrorAction SilentlyContinue
Write-Host "App settings applied." -ForegroundColor Green

# -------------------------------------------------------
# STEP 5 - Build zip and deploy (Kudu is fresh/clean)
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 5: Building zip ===" -ForegroundColor Cyan

$ZIP = "$env:TEMP\ag-fresh.zip"
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

Write-Host ""
Write-Host "=== STEP 6: Deploying ===" -ForegroundColor Cyan
Write-Host "Uploading to fresh Kudu..." -ForegroundColor Yellow
az webapp deploy --name $APP --resource-group $RG --src-path $ZIP --type zip --output none
$D = $LASTEXITCODE
Remove-Item $ZIP -Force -ErrorAction SilentlyContinue
Write-Host "Deploy exit: $D" -ForegroundColor Gray

# -------------------------------------------------------
# STEP 7 - Poll for health (port binds in <1s with new server.js)
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 7: Waiting for site to come up ===" -ForegroundColor Cyan
Write-Host "server.js binds port immediately, DB connects in background." -ForegroundColor Gray

$LIVE = $false
for ($i = 0; $i -lt 24; $i++) {
    Start-Sleep -Seconds 15
    try {
        $H = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/api/health" -TimeoutSec 10
        Write-Host ""
        Write-Host "SITE IS LIVE!" -ForegroundColor Green
        Write-Host "$($H | ConvertTo-Json -Compress)" -ForegroundColor Green
        $LIVE = $true
        break
    } catch {
        Write-Host "  $(($i+1)*15)s - starting..." -ForegroundColor Gray
    }
}

# -------------------------------------------------------
# STEP 8 - Check seed
# -------------------------------------------------------
if ($LIVE) {
    Write-Host ""
    Write-Host "=== STEP 8: Checking seed (auto-seed runs in background) ===" -ForegroundColor Cyan
    Start-Sleep -Seconds 30
    try {
        $PC = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/api/products?limit=1" -TimeoutSec 15
        if ($PC.products -and $PC.products.Count -gt 0) {
            Write-Host "Products exist - seed complete!" -ForegroundColor Green
        } else {
            Write-Host "Products not yet in DB (auto-seed running in background)." -ForegroundColor Yellow
            Write-Host "Wait 2 minutes then check the site." -ForegroundColor Gray
            Write-Host "Or seed manually: https://$APP.scm.azurewebsites.net/DebugConsole" -ForegroundColor Cyan
            Write-Host "  node scripts/seed.js" -ForegroundColor White
        }
    } catch {
        Write-Host "Could not check products: $_" -ForegroundColor Yellow
    }
} else {
    Write-Host ""
    Write-Host "Site not up. Get logs:" -ForegroundColor Red
    Write-Host "  az webapp log tail --name $APP --resource-group $RG" -ForegroundColor Cyan
    Write-Host "  https://$APP.scm.azurewebsites.net/api/logs/docker" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "=======================================" -ForegroundColor Green
Write-Host "  DONE!" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Green
Write-Host "Site:   https://$APP.azurewebsites.net" -ForegroundColor Cyan
Write-Host "Admin:  https://$APP.azurewebsites.net/admin" -ForegroundColor Cyan
Write-Host "Login:  admin@shieldtechnology.tn / Shield@2025!" -ForegroundColor Cyan
Write-Host ""
