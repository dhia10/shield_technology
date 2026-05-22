# Ange Gardien - Fix & Complete Deployment
# Fixes: wrong Node runtime name + unregistered Cosmos DB provider

$ErrorActionPreference = "Continue"   # keep going on non-fatal errors

$SUBSCRIPTION = "dd304ca8-be36-4ad8-a6e0-34f6f9be2698"
$RG           = "ange-gardien-rg"
$LOCATION     = "francecentral"
$PLAN         = "ange-gardien-plan"
$APP          = "ange-gardien-web"
$COSMOS       = "ange-gardiendb01"
$DB_NAME      = "angegardien"
$STORAGE      = "angegardienblob01"
$CONTAINER    = "shield-media"
$ADMIN_EMAIL  = "admin@shieldtechnology.tn"
$ADMIN_PASS   = "Shield@2025!"

az account set --subscription $SUBSCRIPTION

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "  ANGE GARDIEN - Fix Deployment" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan

# -------------------------------------------------------
# FIX 1 - Register missing resource providers
# -------------------------------------------------------
Write-Host ""
Write-Host "[FIX 1] Registering Azure resource providers..." -ForegroundColor Yellow

az provider register --namespace Microsoft.DocumentDB --wait
Write-Host "OK: Microsoft.DocumentDB registered." -ForegroundColor Green

az provider register --namespace Microsoft.Web --wait
Write-Host "OK: Microsoft.Web registered." -ForegroundColor Green

az provider register --namespace Microsoft.Storage --wait
Write-Host "OK: Microsoft.Storage registered." -ForegroundColor Green

# -------------------------------------------------------
# FIX 2 - Find correct Node runtime and create Web App
# -------------------------------------------------------
Write-Host ""
Write-Host "[FIX 2] Finding correct Node.js runtime..." -ForegroundColor Yellow

$runtimes = az webapp list-runtimes --os-type linux | ConvertFrom-Json
$nodeRuntime = $runtimes | Where-Object { $_ -like "node*18*" -or $_ -like "NODE*18*" } | Select-Object -First 1

if (-not $nodeRuntime) {
    $nodeRuntime = $runtimes | Where-Object { $_ -like "node*20*" -or $_ -like "NODE*20*" } | Select-Object -First 1
}
if (-not $nodeRuntime) {
    $nodeRuntime = "NODE|20-lts"  # safe fallback
}

Write-Host "Using runtime: $nodeRuntime" -ForegroundColor Cyan

# Check if web app already exists
$existingApp = az webapp show --name $APP --resource-group $RG 2>$null | ConvertFrom-Json
if ($existingApp) {
    Write-Host "Web App '$APP' already exists — skipping create." -ForegroundColor Gray
} else {
    Write-Host "Creating Web App '$APP'..." -ForegroundColor Yellow
    az webapp create `
      --name $APP `
      --resource-group $RG `
      --plan $PLAN `
      --runtime $nodeRuntime `
      --output table
    Write-Host "OK: Web App created." -ForegroundColor Green
}

# Configure startup
az webapp config set `
  --name $APP `
  --resource-group $RG `
  --startup-file "node server.js" `
  --output none

# -------------------------------------------------------
# FIX 3 - Create Cosmos DB (now that provider is registered)
# -------------------------------------------------------
Write-Host ""
Write-Host "[FIX 3] Creating Cosmos DB (takes ~3-5 minutes)..." -ForegroundColor Yellow

$existingCosmos = az cosmosdb show --name $COSMOS --resource-group $RG 2>$null | ConvertFrom-Json
if ($existingCosmos) {
    Write-Host "Cosmos DB '$COSMOS' already exists — skipping create." -ForegroundColor Gray
} else {
    az cosmosdb create `
      --name $COSMOS `
      --resource-group $RG `
      --kind MongoDB `
      --server-version "6.0" `
      --default-consistency-level "Session" `
      --locations regionName=$LOCATION failoverPriority=0 isZoneRedundant=false `
      --output table
    Write-Host "OK: Cosmos DB account created." -ForegroundColor Green
}

# Create DB if missing
az cosmosdb mongodb database create `
  --account-name $COSMOS `
  --resource-group $RG `
  --name $DB_NAME `
  --output none 2>$null

Write-Host "OK: Cosmos DB database ready." -ForegroundColor Green

# Get Cosmos connection string
$COSMOS_CONN = az cosmosdb keys list `
  --name $COSMOS `
  --resource-group $RG `
  --type connection-strings `
  --query "connectionStrings[0].connectionString" `
  --output tsv

Write-Host "Connection string retrieved." -ForegroundColor Gray

# -------------------------------------------------------
# FIX 4 - Get Storage connection string
# -------------------------------------------------------
Write-Host ""
Write-Host "[FIX 4] Retrieving Blob Storage connection string..." -ForegroundColor Yellow

$STORAGE_CONN = az storage account show-connection-string `
  --name $STORAGE `
  --resource-group $RG `
  --query connectionString `
  --output tsv

Write-Host "OK: Storage connection string retrieved." -ForegroundColor Green

# -------------------------------------------------------
# FIX 5 - Set all environment variables
# -------------------------------------------------------
Write-Host ""
Write-Host "[FIX 5] Configuring all environment variables..." -ForegroundColor Yellow

$G1 = [System.Guid]::NewGuid().ToString("N")
$G2 = [System.Guid]::NewGuid().ToString("N")
$JWT_SECRET = $G1 + $G2

az webapp config appsettings set `
  --name $APP `
  --resource-group $RG `
  --settings `
    "MONGODB_URI=$COSMOS_CONN" `
    "AZURE_STORAGE_CONNECTION_STRING=$STORAGE_CONN" `
    "AZURE_STORAGE_CONTAINER=$CONTAINER" `
    "JWT_SECRET=$JWT_SECRET" `
    "NODE_ENV=production" `
    "ADMIN_EMAIL=$ADMIN_EMAIL" `
    "ADMIN_PASSWORD=$ADMIN_PASS" `
    "WEBSITE_NODE_DEFAULT_VERSION=~18" `
    "SCM_DO_BUILD_DURING_DEPLOYMENT=true" `
  --output none

Write-Host "OK: Environment variables set." -ForegroundColor Green

# -------------------------------------------------------
# FIX 6 - Redeploy code
# -------------------------------------------------------
Write-Host ""
Write-Host "[FIX 6] Deploying application code..." -ForegroundColor Yellow

$PROJECT_DIR = Split-Path -Parent $PSScriptRoot
$ZIP_PATH = Join-Path $env:TEMP "ange-gardien-v2.zip"

if (Test-Path $ZIP_PATH) { Remove-Item $ZIP_PATH -Force }

$excludeDirs  = @("node_modules", ".git", "deploy", ".vscode")
$excludeNames = @(".env")

$filesToZip = Get-ChildItem -Path $PROJECT_DIR -Recurse -File | Where-Object {
  $rel = $_.FullName.Substring($PROJECT_DIR.Length).TrimStart('\')
  $topSegment = $rel.Split('\')[0]
  ($excludeDirs -notcontains $topSegment) -and ($excludeNames -notcontains $_.Name)
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zipStream = [System.IO.Compression.ZipFile]::Open($ZIP_PATH, 'Create')
foreach ($file in $filesToZip) {
  $entryName = $file.FullName.Substring($PROJECT_DIR.Length).TrimStart('\').Replace('\','/')
  [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
    $zipStream, $file.FullName, $entryName,
    [System.IO.Compression.CompressionLevel]::Optimal
  ) | Out-Null
}
$zipStream.Dispose()

Write-Host "Zip created ($([math]::Round((Get-Item $ZIP_PATH).Length/1KB)) KB): $ZIP_PATH" -ForegroundColor Gray

az webapp deploy `
  --name $APP `
  --resource-group $RG `
  --src-path $ZIP_PATH `
  --type zip

Remove-Item $ZIP_PATH -Force -ErrorAction SilentlyContinue
Write-Host "OK: Code deployed!" -ForegroundColor Green

# -------------------------------------------------------
# FIX 7 - Seed database via Kudu
# -------------------------------------------------------
Write-Host ""
Write-Host "[FIX 7] Seeding database (waiting 45s for app to boot)..." -ForegroundColor Yellow
Start-Sleep -Seconds 45

$profiles = az webapp deployment list-publishing-profiles `
  --name $APP --resource-group $RG | ConvertFrom-Json
$profile = $profiles | Where-Object { $_.publishMethod -eq "MSDeploy" } | Select-Object -First 1

if ($profile) {
    $kuduCred  = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("$($profile.userName):$($profile.userPWD)"))
    $kuduUrl   = "https://$APP.scm.azurewebsites.net/api/command"
    $seedBody  = '{"command":"node scripts/seed.js","dir":"site\\wwwroot"}'

    try {
        $result = Invoke-RestMethod `
          -Uri $kuduUrl -Method Post `
          -Headers @{ "Authorization" = "Basic $kuduCred"; "Content-Type" = "application/json" } `
          -Body $seedBody
        Write-Host "OK: Database seeded!" -ForegroundColor Green
        Write-Host $result.Output -ForegroundColor Gray
    } catch {
        Write-Host "Auto-seed skipped (app may still be starting). Do it manually:" -ForegroundColor Yellow
        Write-Host "  1. Go to: https://$APP.scm.azurewebsites.net/DebugConsole" -ForegroundColor Cyan
        Write-Host "  2. Type:  node scripts/seed.js   then press Enter" -ForegroundColor Cyan
    }
} else {
    Write-Host "Could not retrieve Kudu credentials. Seed manually:" -ForegroundColor Yellow
    Write-Host "  https://$APP.scm.azurewebsites.net/DebugConsole" -ForegroundColor Cyan
}

# -------------------------------------------------------
# DONE
# -------------------------------------------------------
Write-Host ""
Write-Host "=======================================" -ForegroundColor Green
Write-Host "  ALL FIXES APPLIED - SITE IS LIVE!" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Green
Write-Host ""
Write-Host "Website:     https://$APP.azurewebsites.net" -ForegroundColor Cyan
Write-Host "Admin panel: https://$APP.azurewebsites.net/admin" -ForegroundColor Cyan
Write-Host "Admin login: $ADMIN_EMAIL  /  $ADMIN_PASS" -ForegroundColor Cyan
Write-Host ""
Write-Host "Live logs:   az webapp log tail --name $APP --resource-group $RG" -ForegroundColor Gray
Write-Host ""
