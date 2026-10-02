# Ange Gardien - Redeploy3: Start stopped app, then deploy clean zip + seed

$ErrorActionPreference = "Continue"

$SUB = "dd304ca8-be36-4ad8-a6e0-34f6f9be2698"
$RG  = "ange-gardien-rg"
$APP = "ange-gardien-web"

az account set --subscription $SUB

# -------------------------------------------------------
# STEP 1 - Start the stopped app
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 1: Starting app ===" -ForegroundColor Cyan
az webapp start --name $APP --resource-group $RG --output none
Write-Host "Start command sent. Waiting 30s for Kudu to come online..." -ForegroundColor Gray
Start-Sleep -Seconds 30

# Confirm Kudu is up
$PROFS = az webapp deployment list-publishing-profiles --name $APP --resource-group $RG | ConvertFrom-Json
$P = $PROFS | Where-Object { $_.publishMethod -eq "MSDeploy" } | Select-Object -First 1
if (-not $P) {
    Write-Host "Still no publishing profile. Waiting 30s more..." -ForegroundColor Yellow
    Start-Sleep -Seconds 30
    $PROFS = az webapp deployment list-publishing-profiles --name $APP --resource-group $RG | ConvertFrom-Json
    $P = $PROFS | Where-Object { $_.publishMethod -eq "MSDeploy" } | Select-Object -First 1
}

if (-not $P) {
    Write-Host "ERROR: Cannot get publishing credentials. Check Azure Portal." -ForegroundColor Red
    exit 1
}
Write-Host "Kudu is online." -ForegroundColor Green

# -------------------------------------------------------
# STEP 2 - Build clean zip (no web.config, no .deployment)
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 2: Building zip ===" -ForegroundColor Cyan

$PROJ = Split-Path -Parent $PSScriptRoot
$ZIP  = "$env:TEMP\ag-linux2.zip"
if (Test-Path $ZIP) { Remove-Item $ZIP -Force }

$SKIP_DIRS  = @("node_modules",".git","deploy",".vscode")
$SKIP_FILES = @(".env","web.config",".deployment","deploy.cmd","deploy.sh","iisnode.yml")

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
Write-Host "Zip: $([math]::Round((Get-Item $ZIP).Length/1KB)) KB  ($($FILES.Count) files)" -ForegroundColor Green

# -------------------------------------------------------
# STEP 3 - Deploy via Kudu zipdeploy
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 3: Deploying via Kudu zipdeploy ===" -ForegroundColor Cyan

$CRED = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("$($P.userName):$($P.userPWD)"))
$KUDU = "https://$APP.scm.azurewebsites.net/api/zipdeploy?SCM_DO_BUILD_DURING_DEPLOYMENT=true"
$BYTES = [System.IO.File]::ReadAllBytes($ZIP)

try {
    Write-Host "Uploading..." -ForegroundColor Yellow
    $RESP = Invoke-WebRequest -Uri $KUDU -Method Post `
        -Headers @{ "Authorization" = "Basic $CRED" } `
        -ContentType "application/octet-stream" `
        -Body $BYTES `
        -TimeoutSec 300 `
        -UseBasicParsing
    Write-Host "HTTP $($RESP.StatusCode) - Deployment accepted!" -ForegroundColor Green
} catch {
    $SC = $_.Exception.Response.StatusCode.value__
    Write-Host "HTTP $SC error: $_" -ForegroundColor Red
    Write-Host "Trying az webapp deploy as fallback..." -ForegroundColor Yellow
    az webapp deploy --name $APP --resource-group $RG --src-path $ZIP --type zip --output table
}

Remove-Item $ZIP -Force -ErrorAction SilentlyContinue

# -------------------------------------------------------
# STEP 4 - Poll deployment status
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 4: Waiting for build to finish (npm install) ===" -ForegroundColor Cyan
Write-Host "Polling every 15s..." -ForegroundColor Gray

$DEPLOYED = $false
for ($i = 0; $i -lt 12; $i++) {
    Start-Sleep -Seconds 15
    try {
        $STATUS = Invoke-RestMethod -Uri "https://$APP.scm.azurewebsites.net/api/deployments/latest" `
            -Headers @{ "Authorization" = "Basic $CRED" } -TimeoutSec 15
        $S = $STATUS.status
        $M = $STATUS.message
        Write-Host "  [$([int](($i+1)*15))s] status=$S  $M" -ForegroundColor Gray
        if ($S -eq 4) { $DEPLOYED = $true; break }  # 4 = Success
        if ($S -eq 3) { Write-Host "DEPLOYMENT FAILED" -ForegroundColor Red; break }  # 3 = Failed
    } catch {
        Write-Host "  [$([int](($i+1)*15))s] (status check failed)" -ForegroundColor Gray
    }
}

if ($DEPLOYED) {
    Write-Host "Build complete!" -ForegroundColor Green
} else {
    Write-Host "Build may still be running. Continuing..." -ForegroundColor Yellow
}

Start-Sleep -Seconds 20

# -------------------------------------------------------
# STEP 5 - Seed database
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 5: Seeding database ===" -ForegroundColor Cyan

$SEED = '{"command":"node scripts/seed.js","dir":"site\\wwwroot"}'
try {
    $R = Invoke-RestMethod -Uri "https://$APP.scm.azurewebsites.net/api/command" -Method Post `
        -Headers @{ "Authorization" = "Basic $CRED"; "Content-Type" = "application/json" } `
        -Body $SEED -TimeoutSec 120
    Write-Host "Database seeded!" -ForegroundColor Green
    Write-Host $R.Output
} catch {
    Write-Host "Auto-seed failed: $_" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Seed manually:" -ForegroundColor Yellow
    Write-Host "  https://$APP.scm.azurewebsites.net/DebugConsole" -ForegroundColor Cyan
    Write-Host "  cd site/wwwroot && node scripts/seed.js" -ForegroundColor Cyan
}

# -------------------------------------------------------
# STEP 6 - Health check
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 6: Health check ===" -ForegroundColor Cyan
Start-Sleep -Seconds 10
try {
    $H = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/api/health" -TimeoutSec 30
    Write-Host "LIVE: $($H | ConvertTo-Json -Compress)" -ForegroundColor Green
} catch {
    Write-Host "Health endpoint not responding yet." -ForegroundColor Yellow
    Write-Host "Check live logs:" -ForegroundColor Gray
    Write-Host "  az webapp log tail --name $APP --resource-group $RG" -ForegroundColor Gray
}

Write-Host ""
Write-Host "=======================================" -ForegroundColor Green
Write-Host "  DONE!" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Green
Write-Host "Site:   https://$APP.azurewebsites.net" -ForegroundColor Cyan
Write-Host "Admin:  https://$APP.azurewebsites.net/admin" -ForegroundColor Cyan
Write-Host "Login:  admin@shieldtechnology.tn / Shield@2025!" -ForegroundColor Cyan
Write-Host ""
