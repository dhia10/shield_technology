# Ange Gardien - Deploy in correct order
# KEY: deploy code FIRST, set startup SECOND
# Setting startup before deploying causes node server.js to crash (file missing)
# which locks the app in stopped state permanently.

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

# STEP 1 - Clean slate: delete app if exists
Write-Host ""
Write-Host "[1] Deleting app if exists..." -ForegroundColor Yellow
az webapp delete --name $APP --resource-group $RG --keep-empty-plan 2>$null
Start-Sleep -Seconds 20

# STEP 2 - Ensure plan exists
Write-Host "[2] Ensuring plan exists..." -ForegroundColor Yellow
az appservice plan show --name $PLAN --resource-group $RG --output none 2>$null
if ($LASTEXITCODE -ne 0) {
    az appservice plan create --name $PLAN --resource-group $RG --location francecentral --sku F1 --is-linux --output none
    Write-Host "    Plan created." -ForegroundColor Green
} else {
    Write-Host "    Plan exists." -ForegroundColor Gray
}

# STEP 3 - Create app WITHOUT touching startup file
Write-Host "[3] Creating app (no startup set yet)..." -ForegroundColor Yellow
az webapp create --name $APP --resource-group $RG --plan $PLAN --runtime "NODE:22-lts" --output none
Write-Host "    App created." -ForegroundColor Green

# STEP 4 - Wait for Kudu to initialise (do NOT set startup yet)
Write-Host "[4] Waiting 30s for Kudu to initialise..." -ForegroundColor Yellow
Start-Sleep -Seconds 30

# STEP 5 - Build and deploy code FIRST
Write-Host "[5] Building zip..." -ForegroundColor Yellow
$ZIP = "$env:TEMP\ag-correct.zip"
if (Test-Path $ZIP) { Remove-Item $ZIP -Force }

$SKIP_DIRS  = @(".git","deploy",".vscode")
$SKIP_FILES = @(".env","web.config",".deployment","deploy.cmd","deploy.sh","iisnode.yml")
$FILES = Get-ChildItem -Path $PROJ -Recurse -File | Where-Object {
    $rel = $_.FullName.Substring($PROJ.Length).TrimStart("\")
    $top = $rel.Split("\")[0]
    ($SKIP_DIRS -notcontains $top) -and ($SKIP_FILES -notcontains $_.Name)
}
Write-Host "    $($FILES.Count) files" -ForegroundColor Gray
Add-Type -AssemblyName System.IO.Compression.FileSystem
$ZS = [System.IO.Compression.ZipFile]::Open($ZIP, "Create")
foreach ($F in $FILES) {
    $E = $F.FullName.Substring($PROJ.Length).TrimStart("\").Replace("\","/")
    try { [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($ZS,$F.FullName,$E,[System.IO.Compression.CompressionLevel]::Optimal)|Out-Null } catch {}
}
$ZS.Dispose()
Write-Host "    Zip: $([math]::Round((Get-Item $ZIP).Length/1MB,1)) MB" -ForegroundColor Green

Write-Host "[5b] Deploying code..." -ForegroundColor Yellow
az webapp deploy --name $APP --resource-group $RG --src-path $ZIP --type zip --output none
$D = $LASTEXITCODE
Remove-Item $ZIP -Force -ErrorAction SilentlyContinue
Write-Host "    Deploy exit: $D" -ForegroundColor $(if ($D -eq 0) {"Green"} else {"Yellow"})

# STEP 6 - NOW set startup command (code exists on disk)
Write-Host "[6] Setting startup command (code is now deployed)..." -ForegroundColor Yellow
az webapp config set --name $APP --resource-group $RG --startup-file "node server.js" --output none
Write-Host "    Startup set." -ForegroundColor Green

# STEP 7 - Apply settings (with retry)
Write-Host "[7] Applying app settings..." -ForegroundColor Yellow
$MONGO = $null
for ($t = 1; $t -le 3; $t++) {
    $MONGO = az cosmosdb keys list --name $DB --resource-group $RG --type connection-strings --query "connectionStrings[0].connectionString" --output tsv 2>$null
    if ($MONGO -and $MONGO.Length -gt 20) { Write-Host "    Cosmos URI: OK" -ForegroundColor Green; break }
    Write-Host "    Attempt $t failed, retrying..." -ForegroundColor Yellow
    Start-Sleep -Seconds 10
}
$BLOB = az storage account show-connection-string --name $ST --resource-group $RG --query connectionString --output tsv
$JWT  = [System.Guid]::NewGuid().ToString("N") + [System.Guid]::NewGuid().ToString("N")

$PROPS = [ordered]@{
    MONGODB_URI                     = if ($MONGO) { $MONGO } else { "" }
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
$FILE = "$env:TEMP\ag-settings-co.json"
[System.IO.File]::WriteAllText($FILE, $BODY, [System.Text.Encoding]::UTF8)
$URL  = "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Web/sites/$APP/config/appsettings?api-version=2022-03-01"
$OUT  = az rest --method PUT --url $URL --body "@$FILE" 2>&1
Remove-Item $FILE -Force -ErrorAction SilentlyContinue
if ($OUT -match '"error"' -or $OUT -match "BadRequest") {
    Write-Host "    Settings warning: $OUT" -ForegroundColor Yellow
} else {
    Write-Host "    Settings applied." -ForegroundColor Green
}

# Enable Basic Auth
az resource update --resource-group $RG --name scm --namespace Microsoft.Web `
    --resource-type basicPublishingCredentialsPolicies `
    --parent "sites/$APP" --set properties.allow=true --output none 2>$null

# STEP 8 - Restart so app picks up new settings + startup
Write-Host "[8] Restarting app..." -ForegroundColor Yellow
az webapp restart --name $APP --resource-group $RG --output none
Write-Host "    Restarted. Polling..." -ForegroundColor Gray

# STEP 9 - Poll health
Write-Host ""
Write-Host "[9] Waiting for site (5 min)..." -ForegroundColor Yellow
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

if (-not $LIVE) {
    Write-Host ""
    Write-Host "Still not up. Download logs:" -ForegroundColor Red
    Write-Host "  az webapp log download --name $APP --resource-group $RG --log-file C:\Users\DELL\Desktop\azure-logs.zip" -ForegroundColor Cyan
    Write-Host "  Then open azure-logs.zip and check the docker log file." -ForegroundColor Gray
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  DONE" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host "Site:   https://$APP.azurewebsites.net" -ForegroundColor Cyan
Write-Host "Admin:  https://$APP.azurewebsites.net/admin" -ForegroundColor Cyan
Write-Host "Login:  admin@shieldtechnology.tn / Shield@2025!" -ForegroundColor Cyan
Write-Host ""
