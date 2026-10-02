# Ange Gardien - Fix3: Auto-discover runtime + deploy
# All previous Azure resources exist. Only the Web App is missing.

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
# STEP 1 - Discover correct Node.js runtime string
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 1: Discovering Node.js runtime ===" -ForegroundColor Cyan

$RAW = az webapp list-runtimes --os-type linux 2>&1
Write-Host "Available runtimes (raw):" -ForegroundColor Gray
Write-Host $RAW -ForegroundColor Gray

# Try to parse as JSON array
try {
    $RUNTIMES = $RAW | ConvertFrom-Json
} catch {
    # Might already be plain text lines
    $RUNTIMES = $RAW -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
}

Write-Host ""
Write-Host "Parsed runtime count: $($RUNTIMES.Count)" -ForegroundColor Gray

# Find best Node.js runtime (prefer 20, then 18, then any node)
$RUNTIME = $null
foreach ($pref in @("20-lts","20","18-lts","18","16-lts","16")) {
    $match = $RUNTIMES | Where-Object { $_ -match "(?i)node.*$pref" } | Select-Object -First 1
    if ($match) { $RUNTIME = $match.Trim(); break }
}
if (-not $RUNTIME) {
    $match = $RUNTIMES | Where-Object { $_ -match "(?i)node" } | Select-Object -First 1
    if ($match) { $RUNTIME = $match.Trim() }
}
if (-not $RUNTIME) {
    Write-Host "ERROR: No Node.js runtime found. Full list above. Exiting." -ForegroundColor Red
    exit 1
}

Write-Host "Selected runtime: '$RUNTIME'" -ForegroundColor Cyan

# -------------------------------------------------------
# STEP 2 - Create Web App
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 2: Creating Web App ===" -ForegroundColor Cyan

$EXISTS = az webapp show --name $APP --resource-group $RG --output none 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "Web App already exists, skipping create." -ForegroundColor Gray
} else {
    Write-Host "Creating Web App with runtime: $RUNTIME" -ForegroundColor Yellow
    az webapp create --name $APP --resource-group $RG --plan $PLAN --runtime $RUNTIME --output table
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "Runtime '$RUNTIME' failed. Trying alternative formats..." -ForegroundColor Yellow

        # Try with pipe separator if colon was used, or vice versa
        if ($RUNTIME -match ":") {
            $ALT = $RUNTIME.Replace(":", "|")
        } else {
            $ALT = $RUNTIME.Replace("|", ":")
        }
        Write-Host "Trying: $ALT" -ForegroundColor Yellow
        az webapp create --name $APP --resource-group $RG --plan $PLAN --runtime $ALT --output table

        if ($LASTEXITCODE -ne 0) {
            Write-Host "Both formats failed. Trying NODE|20-lts and NODE|18-lts directly..." -ForegroundColor Yellow
            az webapp create --name $APP --resource-group $RG --plan $PLAN --runtime "NODE|20-lts" --output table
            if ($LASTEXITCODE -ne 0) {
                az webapp create --name $APP --resource-group $RG --plan $PLAN --runtime "NODE|18-lts" --output table
            }
        }
    }
}

# Verify creation
$CHECK = az webapp show --name $APP --resource-group $RG --query "name" --output tsv 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "FATAL: Web App could not be created after all attempts." -ForegroundColor Red
    Write-Host "Please create it manually in Azure Portal:" -ForegroundColor Yellow
    Write-Host "  1. Go to https://portal.azure.com" -ForegroundColor White
    Write-Host "  2. Search 'App Services' -> Create" -ForegroundColor White
    Write-Host "  3. Resource Group: ange-gardien-rg" -ForegroundColor White
    Write-Host "  4. Name: ange-gardien-web" -ForegroundColor White
    Write-Host "  5. Runtime: Node.js 20 LTS, Linux" -ForegroundColor White
    Write-Host "  6. Plan: ange-gardien-plan (existing)" -ForegroundColor White
    Write-Host "  Then re-run this script (STEP 2 will be skipped)." -ForegroundColor Yellow
    exit 1
}
Write-Host "Web App '$CHECK' is ready." -ForegroundColor Green

# Configure startup
az webapp config set --name $APP --resource-group $RG --startup-file "node server.js" --output none
Write-Host "Startup command set." -ForegroundColor Green

# -------------------------------------------------------
# STEP 3 - Get connection strings
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 3: Getting connection strings ===" -ForegroundColor Cyan

$MONGO = az cosmosdb keys list --name $DB --resource-group $RG --type connection-strings --query "connectionStrings[0].connectionString" --output tsv
if (-not $MONGO) {
    Write-Host "ERROR: Could not get Cosmos DB connection string." -ForegroundColor Red
    exit 1
}
Write-Host "Cosmos DB connection string: OK" -ForegroundColor Green

$BLOB = az storage account show-connection-string --name $ST --resource-group $RG --query connectionString --output tsv
if (-not $BLOB) {
    Write-Host "ERROR: Could not get Storage connection string." -ForegroundColor Red
    exit 1
}
Write-Host "Storage connection string: OK" -ForegroundColor Green

# -------------------------------------------------------
# STEP 4 - Set App Settings via REST (avoids & parsing issue)
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 4: Setting environment variables ===" -ForegroundColor Cyan

$JWT = [System.Guid]::NewGuid().ToString("N") + [System.Guid]::NewGuid().ToString("N")

$PROPS = [ordered]@{
    MONGODB_URI = $MONGO
    AZURE_STORAGE_CONNECTION_STRING = $BLOB
    AZURE_STORAGE_CONTAINER = $CTR
    JWT_SECRET = $JWT
    NODE_ENV = "production"
    ADMIN_EMAIL = "admin@shieldtechnology.tn"
    ADMIN_PASSWORD = "Shield@2025!"
    WEBSITE_NODE_DEFAULT_VERSION = "~20"
    SCM_DO_BUILD_DURING_DEPLOYMENT = "true"
}

$BODY = (@{ properties = $PROPS } | ConvertTo-Json -Depth 5)
$FILE = "$env:TEMP\ag-settings3.json"
[System.IO.File]::WriteAllText($FILE, $BODY, [System.Text.Encoding]::UTF8)
$URL = "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Web/sites/$APP/config/appsettings?api-version=2022-03-01"
az rest --method PUT --url $URL --body "@$FILE" --output none
Remove-Item $FILE -Force -ErrorAction SilentlyContinue
Write-Host "Environment variables set." -ForegroundColor Green

# -------------------------------------------------------
# STEP 5 - Deploy code
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 5: Deploying code ===" -ForegroundColor Cyan

$PROJ = Split-Path -Parent $PSScriptRoot
$ZIP  = "$env:TEMP\ag-fix3.zip"
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
# STEP 6 - Seed database
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 6: Seeding database (waiting 50s) ===" -ForegroundColor Cyan
Start-Sleep -Seconds 50

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
        Write-Host "  1. Open: https://$APP.scm.azurewebsites.net/DebugConsole" -ForegroundColor Cyan
        Write-Host "  2. Run:  node scripts/seed.js" -ForegroundColor Cyan
    }
} else {
    Write-Host "Could not get Kudu credentials. Seed manually:" -ForegroundColor Yellow
    Write-Host "  https://$APP.scm.azurewebsites.net/DebugConsole" -ForegroundColor Cyan
}

# -------------------------------------------------------
# DONE
# -------------------------------------------------------
Write-Host ""
Write-Host "=======================================" -ForegroundColor Green
Write-Host "  DONE!" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Green
Write-Host ""
Write-Host "Site:   https://$APP.azurewebsites.net" -ForegroundColor Cyan
Write-Host "Admin:  https://$APP.azurewebsites.net/admin" -ForegroundColor Cyan
Write-Host "Login:  admin@shieldtechnology.tn / Shield@2025!" -ForegroundColor Cyan
Write-Host ""
Write-Host "Logs:   az webapp log tail --name $APP --resource-group $RG" -ForegroundColor Gray
Write-Host ""
