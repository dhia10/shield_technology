# Ange Gardien - Azure Deployment Script (PowerShell)
# Run from: C:\Users\DELL\Desktop\tarek\shield-technology\
# Prerequisite: az login already done

$ErrorActionPreference = "Stop"

# --- CONFIG ---
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

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "  ANGE GARDIEN - Azure Deployment" -ForegroundColor Cyan
Write-Host "  Subscription: $SUBSCRIPTION" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

# --- Set subscription ---
Write-Host "[0/8] Setting subscription..." -ForegroundColor Yellow
az account set --subscription $SUBSCRIPTION
Write-Host "OK: Subscription set." -ForegroundColor Green

# --- STEP 1: Resource Group ---
Write-Host ""
Write-Host "[1/8] Creating Resource Group '$RG'..." -ForegroundColor Yellow
az group create --name $RG --location $LOCATION --output table
Write-Host "OK: Resource group ready." -ForegroundColor Green

# --- STEP 2: App Service Plan ---
Write-Host ""
Write-Host "[2/8] Creating App Service Plan (Free F1)..." -ForegroundColor Yellow
az appservice plan create `
  --name $PLAN `
  --resource-group $RG `
  --sku F1 `
  --is-linux `
  --output table
Write-Host "OK: App Service Plan ready." -ForegroundColor Green

# --- STEP 3: Web App ---
Write-Host ""
Write-Host "[3/8] Creating Web App '$APP'..." -ForegroundColor Yellow

az webapp create `
  --name $APP `
  --resource-group $RG `
  --plan $PLAN `
  --runtime "NODE:18-lts" `
  --output table

az webapp config set `
  --name $APP `
  --resource-group $RG `
  --startup-file "node server.js" `
  --output none

az webapp config appsettings set `
  --name $APP `
  --resource-group $RG `
  --settings "WEBSITE_NODE_DEFAULT_VERSION=~18" "SCM_DO_BUILD_DURING_DEPLOYMENT=true" `
  --output none

Write-Host "OK: Web App created: https://$APP.azurewebsites.net" -ForegroundColor Green

# --- STEP 4: Cosmos DB (MongoDB API) ---
Write-Host ""
Write-Host "[4/8] Creating Cosmos DB '$COSMOS' (takes ~3 minutes)..." -ForegroundColor Yellow

az cosmosdb create `
  --name $COSMOS `
  --resource-group $RG `
  --kind MongoDB `
  --server-version "6.0" `
  --default-consistency-level "Session" `
  --locations regionName=$LOCATION failoverPriority=0 isZoneRedundant=false `
  --output table

az cosmosdb mongodb database create `
  --account-name $COSMOS `
  --resource-group $RG `
  --name $DB_NAME `
  --output table

Write-Host "OK: Cosmos DB ready." -ForegroundColor Green

$COSMOS_CONN = az cosmosdb keys list `
  --name $COSMOS `
  --resource-group $RG `
  --type connection-strings `
  --query "connectionStrings[0].connectionString" `
  --output tsv

# --- STEP 5: Blob Storage ---
Write-Host ""
Write-Host "[5/8] Creating Blob Storage '$STORAGE'..." -ForegroundColor Yellow

az storage account create `
  --name $STORAGE `
  --resource-group $RG `
  --location $LOCATION `
  --sku Standard_LRS `
  --kind StorageV2 `
  --output table

az storage container create `
  --name $CONTAINER `
  --account-name $STORAGE `
  --public-access blob `
  --output table

$STORAGE_CONN = az storage account show-connection-string `
  --name $STORAGE `
  --resource-group $RG `
  --query connectionString `
  --output tsv

Write-Host "OK: Blob Storage ready." -ForegroundColor Green

# --- STEP 6: App Settings ---
Write-Host ""
Write-Host "[6/8] Configuring environment variables..." -ForegroundColor Yellow

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
  --output none

Write-Host "OK: Environment variables configured." -ForegroundColor Green

# --- STEP 7: Deploy Code ---
Write-Host ""
Write-Host "[7/8] Zipping and deploying code..." -ForegroundColor Yellow

$PROJECT_DIR = Split-Path -Parent $PSScriptRoot
$ZIP_PATH = Join-Path $env:TEMP "ange-gardien-deploy.zip"

if (Test-Path $ZIP_PATH) { Remove-Item $ZIP_PATH -Force }

# Collect files to zip (exclude node_modules, .git, deploy folder, .env)
$excludeDirs  = @("node_modules", ".git", "deploy", ".vscode")
$excludeNames = @(".env", "deploy.zip")

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
    $zipStream,
    $file.FullName,
    $entryName,
    [System.IO.Compression.CompressionLevel]::Optimal
  ) | Out-Null
}

$zipStream.Dispose()
Write-Host "Zip created: $ZIP_PATH" -ForegroundColor Gray

az webapp deploy `
  --name $APP `
  --resource-group $RG `
  --src-path $ZIP_PATH `
  --type zip `
  --output table

Remove-Item $ZIP_PATH -Force -ErrorAction SilentlyContinue
Write-Host "OK: Code deployed!" -ForegroundColor Green

# --- STEP 8: Seed Database ---
Write-Host ""
Write-Host "[8/8] Seeding database (waiting 40s for app to start)..." -ForegroundColor Yellow
Start-Sleep -Seconds 40

$profiles = az webapp deployment list-publishing-profiles `
  --name $APP `
  --resource-group $RG | ConvertFrom-Json

$profile = $profiles | Where-Object { $_.publishMethod -eq "MSDeploy" } | Select-Object -First 1

$kuduCred   = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("$($profile.userName):$($profile.userPWD)"))
$kuduUrl    = "https://$APP.scm.azurewebsites.net/api/command"
$seedBody   = '{"command":"node scripts/seed.js","dir":"site\\wwwroot"}'

try {
  $result = Invoke-RestMethod `
    -Uri $kuduUrl `
    -Method Post `
    -Headers @{ "Authorization" = "Basic $kuduCred"; "Content-Type" = "application/json" } `
    -Body $seedBody

  Write-Host "OK: Database seeded!" -ForegroundColor Green
  Write-Host $result.Output -ForegroundColor Gray
} catch {
  Write-Host "NOTE: Auto-seed skipped. Run manually in 2 minutes:" -ForegroundColor Yellow
  Write-Host "  1. Open: https://$APP.scm.azurewebsites.net/DebugConsole" -ForegroundColor Cyan
  Write-Host "  2. Run command: node scripts/seed.js" -ForegroundColor Cyan
}

# --- SUMMARY ---
Write-Host ""
Write-Host "=======================================" -ForegroundColor Green
Write-Host "  DEPLOYMENT COMPLETE!" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Green
Write-Host ""
Write-Host "Website:      https://$APP.azurewebsites.net" -ForegroundColor Cyan
Write-Host "Admin panel:  https://$APP.azurewebsites.net/admin" -ForegroundColor Cyan
Write-Host "Admin login:  $ADMIN_EMAIL" -ForegroundColor Cyan
Write-Host "Password:     $ADMIN_PASS" -ForegroundColor Cyan
Write-Host ""
Write-Host "DNS for shieldtechnology.tn:" -ForegroundColor Yellow
Write-Host "  Add CNAME record: www -> $APP.azurewebsites.net" -ForegroundColor White
Write-Host ""
Write-Host "Monitor logs:" -ForegroundColor Yellow
Write-Host "  az webapp log tail --name $APP --resource-group $RG" -ForegroundColor White
Write-Host ""
