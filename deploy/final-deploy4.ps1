# Ange Gardien - Final Deploy 4
# Critical fix: app.listen() fires BEFORE connectDB()
# Port binds in <1s, Azure health check passes immediately.

$ErrorActionPreference = "Continue"

$SUB = "dd304ca8-be36-4ad8-a6e0-34f6f9be2698"
$RG  = "ange-gardien-rg"
$APP = "ange-gardien-web"
$PROJ = Split-Path -Parent $PSScriptRoot

az account set --subscription $SUB

# -------------------------------------------------------
# STEP 1 - Build zip with fixed server.js
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 1: Building zip ===" -ForegroundColor Cyan

$ZIP = "$env:TEMP\ag-final4.zip"
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

# -------------------------------------------------------
# STEP 2 - Start + deploy
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 2: Starting app + deploying ===" -ForegroundColor Cyan

az webapp start --name $APP --resource-group $RG --output none
Start-Sleep -Seconds 10

Write-Host "Uploading..." -ForegroundColor Yellow
az webapp deploy --name $APP --resource-group $RG --src-path $ZIP --type zip --output none
$D = $LASTEXITCODE
Remove-Item $ZIP -Force -ErrorAction SilentlyContinue
Write-Host "Deploy exit: $D" -ForegroundColor Gray

# -------------------------------------------------------
# STEP 3 - Poll health - port binds in <1s now
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 3: Polling health (port binds in <1s now) ===" -ForegroundColor Cyan

$LIVE = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 15
    try {
        $H = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/api/health" -TimeoutSec 10
        Write-Host ""
        Write-Host "SITE IS LIVE!" -ForegroundColor Green
        Write-Host "$($H | ConvertTo-Json -Compress)" -ForegroundColor Green
        $LIVE = $true
        break
    } catch {
        Write-Host "  $(($i+1)*15)s..." -ForegroundColor Gray
    }
}

# -------------------------------------------------------
# STEP 4 - Seed via Kudu or auto-seed already ran
# -------------------------------------------------------
if ($LIVE) {
    Write-Host ""
    Write-Host "=== STEP 4: Checking database seed ===" -ForegroundColor Cyan
    Start-Sleep -Seconds 30

    $PROFS = az webapp deployment list-publishing-profiles --name $APP --resource-group $RG | ConvertFrom-Json
    $P = $PROFS | Where-Object { $_.publishMethod -eq "MSDeploy" } | Select-Object -First 1

    try {
        $PC = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/api/products?limit=1" -TimeoutSec 15
        if ($PC.products -and $PC.products.Count -gt 0) {
            Write-Host "Products found - auto-seed ran successfully!" -ForegroundColor Green
        } elseif ($P) {
            Write-Host "No products yet - running seed via Kudu..." -ForegroundColor Yellow
            $CRED = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("$($P.userName):$($P.userPWD)"))
            $SEED = '{"command":"node scripts/seed.js","dir":"site\\wwwroot"}'
            $R = Invoke-RestMethod -Uri "https://$APP.scm.azurewebsites.net/api/command" -Method Post `
                -Headers @{ "Authorization" = "Basic $CRED"; "Content-Type" = "application/json" } `
                -Body $SEED -TimeoutSec 120
            Write-Host "Seeded! $($R.Output)" -ForegroundColor Green
        }
    } catch {
        Write-Host "Check seed: $_" -ForegroundColor Yellow
        Write-Host "If products are missing, open: https://$APP.scm.azurewebsites.net/DebugConsole" -ForegroundColor Cyan
        Write-Host "  node scripts/seed.js" -ForegroundColor White
    }
} else {
    Write-Host ""
    Write-Host "Site still not up. Fetch crash logs:" -ForegroundColor Red
    Write-Host "  az webapp log tail --name $APP --resource-group $RG" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "=======================================" -ForegroundColor Green
Write-Host "  DONE!" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Green
Write-Host "Site:   https://$APP.azurewebsites.net" -ForegroundColor Cyan
Write-Host "Admin:  https://$APP.azurewebsites.net/admin" -ForegroundColor Cyan
Write-Host "Login:  admin@shieldtechnology.tn / Shield@2025!" -ForegroundColor Cyan
Write-Host ""
