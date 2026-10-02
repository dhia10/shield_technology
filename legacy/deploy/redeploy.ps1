# Ange Gardien - Redeploy: fetch error details, retry deploy, seed DB
# Web App exists. This script only handles deploy + seed.

$ErrorActionPreference = "Continue"

$SUB = "dd304ca8-be36-4ad8-a6e0-34f6f9be2698"
$RG  = "ange-gardien-rg"
$APP = "ange-gardien-web"

az account set --subscription $SUB

# -------------------------------------------------------
# STEP 1 - Fetch last deployment error from Kudu
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 1: Checking last deployment error ===" -ForegroundColor Cyan

$PROFS = az webapp deployment list-publishing-profiles --name $APP --resource-group $RG | ConvertFrom-Json
$P = $PROFS | Where-Object { $_.publishMethod -eq "MSDeploy" } | Select-Object -First 1

if ($P) {
    $CRED = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("$($P.userName):$($P.userPWD)"))
    try {
        $DLOG = Invoke-RestMethod -Uri "https://$APP.scm.azurewebsites.net/api/deployments/latest" -Method Get -Headers @{ "Authorization" = "Basic $CRED" }
        Write-Host "Status:  $($DLOG.status)" -ForegroundColor Yellow
        Write-Host "Message: $($DLOG.message)" -ForegroundColor Yellow
        Write-Host "Log URL: $($DLOG.log_url)" -ForegroundColor Gray
        if ($DLOG.log_url) {
            try {
                $LDETAIL = Invoke-RestMethod -Uri $DLOG.log_url -Method Get -Headers @{ "Authorization" = "Basic $CRED" }
                Write-Host "--- Log entries ---" -ForegroundColor Gray
                $LDETAIL | Select-Object -First 20 | ForEach-Object { Write-Host $_.message -ForegroundColor Gray }
            } catch { Write-Host "(Could not fetch log detail)" -ForegroundColor Gray }
        }
    } catch {
        Write-Host "Could not fetch deployment log: $_" -ForegroundColor Yellow
    }
} else {
    Write-Host "No publishing profile found." -ForegroundColor Yellow
}

# -------------------------------------------------------
# STEP 2 - Restart app, then redeploy
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 2: Restarting app ===" -ForegroundColor Cyan
az webapp restart --name $APP --resource-group $RG --output none
Write-Host "Restarted. Waiting 15s..." -ForegroundColor Gray
Start-Sleep -Seconds 15

Write-Host ""
Write-Host "=== STEP 3: Rebuilding zip and redeploying ===" -ForegroundColor Cyan

$PROJ = Split-Path -Parent $PSScriptRoot
$ZIP  = "$env:TEMP\ag-redeploy.zip"
if (Test-Path $ZIP) { Remove-Item $ZIP -Force }

$SKIP_DIRS  = @("node_modules",".git","deploy",".vscode")
$SKIP_FILES = @(".env")

$FILES = Get-ChildItem -Path $PROJ -Recurse -File | Where-Object {
    $rel = $_.FullName.Substring($PROJ.Length).TrimStart("\")
    $top = $rel.Split("\")[0]
    ($SKIP_DIRS -notcontains $top) -and ($SKIP_FILES -notcontains $_.Name)
}

Write-Host "Files to zip: $($FILES.Count)" -ForegroundColor Gray
$FILES | Select-Object -First 10 | ForEach-Object {
    $rel = $_.FullName.Substring($PROJ.Length).TrimStart("\")
    Write-Host "  $rel" -ForegroundColor Gray
}
if ($FILES.Count -gt 10) { Write-Host "  ... and $($FILES.Count - 10) more" -ForegroundColor Gray }

Add-Type -AssemblyName System.IO.Compression.FileSystem
$ZS = [System.IO.Compression.ZipFile]::Open($ZIP, "Create")
foreach ($F in $FILES) {
    $E = $F.FullName.Substring($PROJ.Length).TrimStart("\").Replace("\","/")
    [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($ZS, $F.FullName, $E, [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
}
$ZS.Dispose()

$SIZE = [math]::Round((Get-Item $ZIP).Length/1KB)
Write-Host "Zip: $SIZE KB at $ZIP" -ForegroundColor Gray

if ($SIZE -lt 1) {
    Write-Host "ERROR: Zip is empty. Check project path: $PROJ" -ForegroundColor Red
    exit 1
}

az webapp deploy --name $APP --resource-group $RG --src-path $ZIP --type zip --output table
$DEPLOY_EXIT = $LASTEXITCODE
Remove-Item $ZIP -Force -ErrorAction SilentlyContinue

if ($DEPLOY_EXIT -ne 0) {
    Write-Host ""
    Write-Host "Deployment returned error code $DEPLOY_EXIT." -ForegroundColor Yellow
    Write-Host "The app may still have deployed partially. Continuing to seed..." -ForegroundColor Yellow
} else {
    Write-Host "Deployment succeeded." -ForegroundColor Green
}

# -------------------------------------------------------
# STEP 4 - Seed database
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 4: Seeding database (waiting 60s for app boot) ===" -ForegroundColor Cyan
Start-Sleep -Seconds 60

$PROFS = az webapp deployment list-publishing-profiles --name $APP --resource-group $RG | ConvertFrom-Json
$P = $PROFS | Where-Object { $_.publishMethod -eq "MSDeploy" } | Select-Object -First 1

if ($P) {
    $CRED = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("$($P.userName):$($P.userPWD)"))
    $SEED = '{"command":"node scripts/seed.js","dir":"site\\wwwroot"}'
    try {
        Write-Host "Running seed..." -ForegroundColor Yellow
        $R = Invoke-RestMethod -Uri "https://$APP.scm.azurewebsites.net/api/command" -Method Post -Headers @{ "Authorization" = "Basic $CRED"; "Content-Type" = "application/json" } -Body $SEED -TimeoutSec 120
        Write-Host "Database seeded!" -ForegroundColor Green
        Write-Host $R.Output
    } catch {
        Write-Host "Auto-seed failed: $_" -ForegroundColor Yellow
        Write-Host "Seed manually:" -ForegroundColor Yellow
        Write-Host "  1. https://$APP.scm.azurewebsites.net/DebugConsole" -ForegroundColor Cyan
        Write-Host "  2. cd site/wwwroot && node scripts/seed.js" -ForegroundColor Cyan
    }
}

# -------------------------------------------------------
# STEP 5 - Check app is live
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 5: Checking site health ===" -ForegroundColor Cyan
try {
    $HEALTH = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/api/health" -TimeoutSec 30
    Write-Host "Health: $($HEALTH | ConvertTo-Json -Compress)" -ForegroundColor Green
} catch {
    Write-Host "Health check failed (app may still be starting): $_" -ForegroundColor Yellow
    Write-Host "Check logs:" -ForegroundColor Gray
    Write-Host "  az webapp log tail --name $APP --resource-group $RG" -ForegroundColor Gray
}

Write-Host ""
Write-Host "=======================================" -ForegroundColor Green
Write-Host "  DONE!" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Green
Write-Host ""
Write-Host "Site:   https://$APP.azurewebsites.net" -ForegroundColor Cyan
Write-Host "Admin:  https://$APP.azurewebsites.net/admin" -ForegroundColor Cyan
Write-Host "Login:  admin@shieldtechnology.tn / Shield@2025!" -ForegroundColor Cyan
Write-Host ""
