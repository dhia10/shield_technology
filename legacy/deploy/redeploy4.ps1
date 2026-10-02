# Ange Gardien - Redeploy4
# Strategy: npm install locally, ship node_modules in zip.
# No server-side build = no timeout on F1 free tier.

$ErrorActionPreference = "Continue"

$SUB = "dd304ca8-be36-4ad8-a6e0-34f6f9be2698"
$RG  = "ange-gardien-rg"
$APP = "ange-gardien-web"

az account set --subscription $SUB

$PROJ = Split-Path -Parent $PSScriptRoot

# -------------------------------------------------------
# STEP 1 - npm install --production locally
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 1: npm install --production ===" -ForegroundColor Cyan
Write-Host "Project: $PROJ" -ForegroundColor Gray

Push-Location $PROJ
npm install --production --no-audit --no-fund
$NPM_EXIT = $LASTEXITCODE
Pop-Location

if ($NPM_EXIT -ne 0) {
    Write-Host "npm install failed (exit $NPM_EXIT). Is Node.js installed?" -ForegroundColor Red
    Write-Host "Install from https://nodejs.org then re-run this script." -ForegroundColor Yellow
    exit 1
}

$NM_SIZE = [math]::Round((Get-ChildItem "$PROJ\node_modules" -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1MB, 1)
Write-Host "node_modules: $NM_SIZE MB" -ForegroundColor Green

# -------------------------------------------------------
# STEP 2 - Disable server-side build (not needed now)
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 2: Disabling server-side build ===" -ForegroundColor Cyan
az webapp config appsettings set --name $APP --resource-group $RG `
    --settings "SCM_DO_BUILD_DURING_DEPLOYMENT=false" --output none
Write-Host "SCM_DO_BUILD_DURING_DEPLOYMENT=false" -ForegroundColor Green

# -------------------------------------------------------
# STEP 3 - Build zip WITH node_modules
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 3: Building zip with node_modules ===" -ForegroundColor Cyan

$ZIP = "$env:TEMP\ag-full.zip"
if (Test-Path $ZIP) { Remove-Item $ZIP -Force }

$SKIP_DIRS  = @(".git","deploy",".vscode")
$SKIP_FILES = @(".env","web.config",".deployment","deploy.cmd","deploy.sh","iisnode.yml")

$FILES = Get-ChildItem -Path $PROJ -Recurse -File | Where-Object {
    $rel = $_.FullName.Substring($PROJ.Length).TrimStart("\")
    $top = $rel.Split("\")[0]
    ($SKIP_DIRS -notcontains $top) -and ($SKIP_FILES -notcontains $_.Name)
}

Write-Host "Total files: $($FILES.Count)" -ForegroundColor Gray
Write-Host "Creating zip (this may take a moment)..." -ForegroundColor Gray

Add-Type -AssemblyName System.IO.Compression.FileSystem
$ZS = [System.IO.Compression.ZipFile]::Open($ZIP, "Create")
foreach ($F in $FILES) {
    $E = $F.FullName.Substring($PROJ.Length).TrimStart("\").Replace("\","/")
    try {
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($ZS, $F.FullName, $E, [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
    } catch {
        Write-Host "  Skipped: $E" -ForegroundColor Gray
    }
}
$ZS.Dispose()

$SIZE_MB = [math]::Round((Get-Item $ZIP).Length / 1MB, 1)
Write-Host "Zip: $SIZE_MB MB" -ForegroundColor Green

# -------------------------------------------------------
# STEP 4 - Start app + deploy
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 4: Start app + deploy ===" -ForegroundColor Cyan

az webapp start --name $APP --resource-group $RG --output none
Write-Host "App started. Waiting 20s..." -ForegroundColor Gray
Start-Sleep -Seconds 20

Write-Host "Deploying $SIZE_MB MB zip..." -ForegroundColor Yellow
az webapp deploy --name $APP --resource-group $RG --src-path $ZIP --type zip --output table
$DEPLOY_EXIT = $LASTEXITCODE

Remove-Item $ZIP -Force -ErrorAction SilentlyContinue

if ($DEPLOY_EXIT -eq 0) {
    Write-Host "Deployment succeeded!" -ForegroundColor Green
} else {
    Write-Host "az webapp deploy returned $DEPLOY_EXIT - checking if it went through anyway..." -ForegroundColor Yellow
}

# -------------------------------------------------------
# STEP 5 - Seed database
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 5: Waiting 45s then seeding database ===" -ForegroundColor Cyan
Start-Sleep -Seconds 45

$PROFS = az webapp deployment list-publishing-profiles --name $APP --resource-group $RG | ConvertFrom-Json
$P = $PROFS | Where-Object { $_.publishMethod -eq "MSDeploy" } | Select-Object -First 1

if ($P) {
    $CRED = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("$($P.userName):$($P.userPWD)"))
    $SEED = '{"command":"node scripts/seed.js","dir":"site\\wwwroot"}'
    try {
        Write-Host "Running seed..." -ForegroundColor Yellow
        $R = Invoke-RestMethod -Uri "https://$APP.scm.azurewebsites.net/api/command" -Method Post `
            -Headers @{ "Authorization" = "Basic $CRED"; "Content-Type" = "application/json" } `
            -Body $SEED -TimeoutSec 120
        Write-Host "Database seeded!" -ForegroundColor Green
        Write-Host $R.Output
    } catch {
        Write-Host "Auto-seed failed: $_" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Seed manually at Kudu console:" -ForegroundColor Yellow
        Write-Host "  https://$APP.scm.azurewebsites.net/DebugConsole" -ForegroundColor Cyan
        Write-Host "  Command: node scripts/seed.js" -ForegroundColor Cyan
    }
}

# -------------------------------------------------------
# STEP 6 - Health check
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 6: Health check ===" -ForegroundColor Cyan
Start-Sleep -Seconds 15
try {
    $H = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/api/health" -TimeoutSec 30
    Write-Host "LIVE! $($H | ConvertTo-Json -Compress)" -ForegroundColor Green
} catch {
    Write-Host "Site not responding yet. Check logs:" -ForegroundColor Yellow
    Write-Host "  az webapp log tail --name $APP --resource-group $RG" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Or open the site directly:" -ForegroundColor Gray
    Write-Host "  https://$APP.azurewebsites.net" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "=======================================" -ForegroundColor Green
Write-Host "  DONE!" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Green
Write-Host "Site:   https://$APP.azurewebsites.net" -ForegroundColor Cyan
Write-Host "Admin:  https://$APP.azurewebsites.net/admin" -ForegroundColor Cyan
Write-Host "Login:  admin@shieldtechnology.tn / Shield@2025!" -ForegroundColor Cyan
Write-Host ""
