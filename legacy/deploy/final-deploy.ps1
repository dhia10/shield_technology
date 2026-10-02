# Ange Gardien - Final Deploy
# - Enables Kudu Basic Auth
# - Ships node_modules in zip (no server-side build)
# - server.js auto-seeds DB on first boot

$ErrorActionPreference = "Continue"

$SUB = "dd304ca8-be36-4ad8-a6e0-34f6f9be2698"
$RG  = "ange-gardien-rg"
$APP = "ange-gardien-web"
$PROJ = Split-Path -Parent $PSScriptRoot

az account set --subscription $SUB

# -------------------------------------------------------
# STEP 1 - Enable Basic Auth for Kudu (SCM site)
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 1: Enabling Kudu Basic Auth ===" -ForegroundColor Cyan

az resource update `
    --resource-group $RG `
    --name scm `
    --namespace Microsoft.Web `
    --resource-type basicPublishingCredentialsPolicies `
    --parent "sites/$APP" `
    --set properties.allow=true `
    --output none

az resource update `
    --resource-group $RG `
    --name ftp `
    --namespace Microsoft.Web `
    --resource-type basicPublishingCredentialsPolicies `
    --parent "sites/$APP" `
    --set properties.allow=true `
    --output none

Write-Host "Basic Auth enabled." -ForegroundColor Green

# -------------------------------------------------------
# STEP 2 - Make sure node_modules exists
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 2: Verifying node_modules ===" -ForegroundColor Cyan

if (-not (Test-Path "$PROJ\node_modules")) {
    Write-Host "node_modules missing - running npm install..." -ForegroundColor Yellow
    Push-Location $PROJ
    npm install --omit=dev --no-audit --no-fund
    Pop-Location
    if ($LASTEXITCODE -ne 0) {
        Write-Host "npm install failed." -ForegroundColor Red; exit 1
    }
}
$NM_MB = [math]::Round((Get-ChildItem "$PROJ\node_modules" -Recurse -File | Measure-Object -Property Length -Sum).Sum/1MB,1)
Write-Host "node_modules: $NM_MB MB - OK" -ForegroundColor Green

# -------------------------------------------------------
# STEP 3 - Disable server-side build, start app
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 3: Configuring app ===" -ForegroundColor Cyan

az webapp config appsettings set --name $APP --resource-group $RG `
    --settings "SCM_DO_BUILD_DURING_DEPLOYMENT=false" --output none

az webapp start --name $APP --resource-group $RG --output none
Write-Host "App started. Waiting 15s..." -ForegroundColor Gray
Start-Sleep -Seconds 15

# -------------------------------------------------------
# STEP 4 - Build and upload zip
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 4: Building zip ===" -ForegroundColor Cyan

$ZIP = "$env:TEMP\ag-final.zip"
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
$ZIP_MB = [math]::Round((Get-Item $ZIP).Length/1MB,1)
Write-Host "Zip: $ZIP_MB MB" -ForegroundColor Green

Write-Host ""
Write-Host "=== STEP 5: Deploying ===" -ForegroundColor Cyan
Write-Host "Uploading $ZIP_MB MB... (may show 502/504 - that is OK, deploy continues on Azure)" -ForegroundColor Yellow

az webapp deploy --name $APP --resource-group $RG --src-path $ZIP --type zip --output none
$D = $LASTEXITCODE
Remove-Item $ZIP -Force -ErrorAction SilentlyContinue

if ($D -eq 0) {
    Write-Host "Deploy returned success." -ForegroundColor Green
} else {
    Write-Host "Deploy returned code $D (timeout expected on F1 - checking if it landed anyway)..." -ForegroundColor Yellow
}

# -------------------------------------------------------
# STEP 6 - Wait for app to boot (includes auto-seed)
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 6: Waiting for app boot + auto-seed (90s) ===" -ForegroundColor Cyan
Write-Host "server.js will auto-seed the database on first boot." -ForegroundColor Gray

for ($i = 90; $i -gt 0; $i -= 15) {
    Write-Host "  $i seconds..." -ForegroundColor Gray
    Start-Sleep -Seconds 15
    try {
        $H = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/api/health" -TimeoutSec 8
        Write-Host "  Site is UP!" -ForegroundColor Green
        Write-Host "  $($H | ConvertTo-Json -Compress)" -ForegroundColor Green
        break
    } catch { }
}

# -------------------------------------------------------
# STEP 7 - Final health check + fallback manual seed info
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 7: Final status ===" -ForegroundColor Cyan

$LIVE = $false
try {
    $H = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/api/health" -TimeoutSec 20
    Write-Host "LIVE: $($H | ConvertTo-Json -Compress)" -ForegroundColor Green
    $LIVE = $true
} catch {
    Write-Host "Site not responding. Getting logs..." -ForegroundColor Yellow
    az webapp log tail --name $APP --resource-group $RG --provider application 2>&1 | Select-Object -Last 30
}

if (-not $LIVE) {
    Write-Host ""
    Write-Host "If the site is still down, check the Kudu console:" -ForegroundColor Yellow
    Write-Host "  https://$APP.scm.azurewebsites.net/DebugConsole" -ForegroundColor Cyan
    Write-Host "  cd site/wwwroot && node server.js" -ForegroundColor White
}

Write-Host ""
Write-Host "=======================================" -ForegroundColor Green
Write-Host "  DONE!" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Green
Write-Host "Site:   https://$APP.azurewebsites.net" -ForegroundColor Cyan
Write-Host "Admin:  https://$APP.azurewebsites.net/admin" -ForegroundColor Cyan
Write-Host "Login:  admin@shieldtechnology.tn / Shield@2025!" -ForegroundColor Cyan
Write-Host "Logs:   az webapp log tail --name $APP --resource-group $RG" -ForegroundColor Gray
Write-Host ""
