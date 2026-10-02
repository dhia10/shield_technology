# Ange Gardien - Redeploy2: exclude web.config + .deployment, deploy via Kudu API
# These Windows/IIS files cause 400 on Linux App Service.

$ErrorActionPreference = "Continue"

$SUB = "dd304ca8-be36-4ad8-a6e0-34f6f9be2698"
$RG  = "ange-gardien-rg"
$APP = "ange-gardien-web"

az account set --subscription $SUB

# -------------------------------------------------------
# STEP 1 - Build clean zip (exclude Windows artifacts)
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 1: Building clean zip ===" -ForegroundColor Cyan

$PROJ = Split-Path -Parent $PSScriptRoot
$ZIP  = "$env:TEMP\ag-linux.zip"
if (Test-Path $ZIP) { Remove-Item $ZIP -Force }

$SKIP_DIRS  = @("node_modules",".git","deploy",".vscode")
$SKIP_FILES = @(".env","web.config",".deployment","deploy.cmd","deploy.sh","iisnode.yml")

$FILES = Get-ChildItem -Path $PROJ -Recurse -File | Where-Object {
    $rel = $_.FullName.Substring($PROJ.Length).TrimStart("\")
    $top = $rel.Split("\")[0]
    ($SKIP_DIRS -notcontains $top) -and ($SKIP_FILES -notcontains $_.Name)
}

Write-Host "Zipping $($FILES.Count) files (excluding web.config, .deployment):" -ForegroundColor Gray
$FILES | ForEach-Object {
    $rel = $_.FullName.Substring($PROJ.Length).TrimStart("\")
    Write-Host "  $rel" -ForegroundColor Gray
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$ZS = [System.IO.Compression.ZipFile]::Open($ZIP, "Create")
foreach ($F in $FILES) {
    $E = $F.FullName.Substring($PROJ.Length).TrimStart("\").Replace("\","/")
    [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($ZS, $F.FullName, $E, [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
}
$ZS.Dispose()

$SIZE = [math]::Round((Get-Item $ZIP).Length/1KB)
Write-Host "Zip: $SIZE KB" -ForegroundColor Green

# -------------------------------------------------------
# STEP 2 - Deploy via Kudu zipdeploy REST API directly
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 2: Deploying via Kudu REST API ===" -ForegroundColor Cyan

$PROFS = az webapp deployment list-publishing-profiles --name $APP --resource-group $RG | ConvertFrom-Json
$P = $PROFS | Where-Object { $_.publishMethod -eq "MSDeploy" } | Select-Object -First 1

if (-not $P) {
    Write-Host "No publishing profile. Falling back to az webapp deploy..." -ForegroundColor Yellow
    az webapp deploy --name $APP --resource-group $RG --src-path $ZIP --type zip --output table
} else {
    $CRED = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("$($P.userName):$($P.userPWD)"))
    $KUDU = "https://$APP.scm.azurewebsites.net/api/zipdeploy?isAsync=false&SCM_DO_BUILD_DURING_DEPLOYMENT=true"

    Write-Host "Uploading to Kudu zipdeploy endpoint..." -ForegroundColor Yellow
    try {
        $BYTES = [System.IO.File]::ReadAllBytes($ZIP)
        $RESP = Invoke-RestMethod -Uri $KUDU -Method Post `
            -Headers @{ "Authorization" = "Basic $CRED" } `
            -ContentType "application/octet-stream" `
            -Body $BYTES `
            -TimeoutSec 300
        Write-Host "Kudu deploy response: $RESP" -ForegroundColor Green
        Write-Host "Deployment submitted!" -ForegroundColor Green
    } catch {
        $STATUS = $_.Exception.Response.StatusCode.value__
        Write-Host "Kudu deploy error $STATUS : $_" -ForegroundColor Yellow
        Write-Host "Falling back to az webapp deploy..." -ForegroundColor Yellow
        az webapp deploy --name $APP --resource-group $RG --src-path $ZIP --type zip --output table
    }
}

Remove-Item $ZIP -Force -ErrorAction SilentlyContinue

# -------------------------------------------------------
# STEP 3 - Wait for build + Seed database
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 3: Waiting 90s for npm install + app boot ===" -ForegroundColor Cyan

for ($i = 90; $i -gt 0; $i -= 10) {
    Write-Host "  $i seconds remaining..." -ForegroundColor Gray
    Start-Sleep -Seconds 10
}

$PROFS = az webapp deployment list-publishing-profiles --name $APP --resource-group $RG | ConvertFrom-Json
$P = $PROFS | Where-Object { $_.publishMethod -eq "MSDeploy" } | Select-Object -First 1

if ($P) {
    $CRED = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("$($P.userName):$($P.userPWD)"))
    $SEED = '{"command":"node scripts/seed.js","dir":"site\\wwwroot"}'
    try {
        Write-Host "Running: node scripts/seed.js" -ForegroundColor Yellow
        $R = Invoke-RestMethod -Uri "https://$APP.scm.azurewebsites.net/api/command" -Method Post `
            -Headers @{ "Authorization" = "Basic $CRED"; "Content-Type" = "application/json" } `
            -Body $SEED -TimeoutSec 120
        Write-Host "Database seeded!" -ForegroundColor Green
        Write-Host $R.Output
    } catch {
        Write-Host "Auto-seed failed: $_" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Seed manually at: https://$APP.scm.azurewebsites.net/DebugConsole" -ForegroundColor Cyan
        Write-Host "  cd site/wwwroot" -ForegroundColor White
        Write-Host "  node scripts/seed.js" -ForegroundColor White
    }
}

# -------------------------------------------------------
# STEP 4 - Health check
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 4: Health check ===" -ForegroundColor Cyan
try {
    $H = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/api/health" -TimeoutSec 30
    Write-Host "LIVE: $($H | ConvertTo-Json -Compress)" -ForegroundColor Green
} catch {
    Write-Host "Health check failed - checking logs:" -ForegroundColor Yellow
    az webapp log tail --name $APP --resource-group $RG --provider http 2>&1 | Select-Object -First 20
}

Write-Host ""
Write-Host "=======================================" -ForegroundColor Green
Write-Host "  DONE!" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Green
Write-Host "Site:   https://$APP.azurewebsites.net" -ForegroundColor Cyan
Write-Host "Admin:  https://$APP.azurewebsites.net/admin" -ForegroundColor Cyan
Write-Host "Login:  admin@shieldtechnology.tn / Shield@2025!" -ForegroundColor Cyan
Write-Host ""
