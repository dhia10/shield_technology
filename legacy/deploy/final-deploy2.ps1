# Ange Gardien - Final Deploy 2
# Fix: app.listen() BEFORE auto-seed so health check passes immediately.
# Also fetches crash logs before redeploying.

$ErrorActionPreference = "Continue"

$SUB = "dd304ca8-be36-4ad8-a6e0-34f6f9be2698"
$RG  = "ange-gardien-rg"
$APP = "ange-gardien-web"
$PROJ = Split-Path -Parent $PSScriptRoot

az account set --subscription $SUB

# -------------------------------------------------------
# STEP 1 - Fetch crash logs to understand what failed
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 1: Fetching crash logs ===" -ForegroundColor Cyan

$PROFS = az webapp deployment list-publishing-profiles --name $APP --resource-group $RG | ConvertFrom-Json
$P = $PROFS | Where-Object { $_.publishMethod -eq "MSDeploy" } | Select-Object -First 1

if ($P) {
    $CRED = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("$($P.userName):$($P.userPWD)"))
    try {
        $LOGS = Invoke-RestMethod -Uri "https://$APP.scm.azurewebsites.net/api/logs/docker" `
            -Headers @{ "Authorization" = "Basic $CRED" } -TimeoutSec 20
        Write-Host "Log files found:" -ForegroundColor Gray
        $LOGS | Select-Object -First 5 | ForEach-Object { Write-Host "  $($_.href)" -ForegroundColor Gray }

        # Get the latest log file content
        $LATEST = $LOGS | Sort-Object lastModified -Descending | Select-Object -First 1
        if ($LATEST) {
            Write-Host ""
            Write-Host "--- Latest log: $($LATEST.href) ---" -ForegroundColor Yellow
            try {
                $CONTENT = Invoke-RestMethod -Uri $LATEST.href `
                    -Headers @{ "Authorization" = "Basic $CRED" } -TimeoutSec 20
                $CONTENT -split "`n" | Select-Object -Last 40 | ForEach-Object { Write-Host $_ -ForegroundColor Gray }
            } catch { Write-Host "(could not read log content)" -ForegroundColor Gray }
        }
    } catch {
        Write-Host "Could not fetch logs: $_" -ForegroundColor Yellow
        Write-Host "Manual log URL: https://$APP.scm.azurewebsites.net/api/logs/docker" -ForegroundColor Cyan
    }
} else {
    Write-Host "No publishing profile yet." -ForegroundColor Yellow
}

# -------------------------------------------------------
# STEP 2 - Rebuild zip with fixed server.js
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 2: Building zip (fixed startup order) ===" -ForegroundColor Cyan

$ZIP = "$env:TEMP\ag-final2.zip"
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
# STEP 3 - Restart + redeploy
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 3: Restarting and deploying ===" -ForegroundColor Cyan

az webapp start --name $APP --resource-group $RG --output none
Start-Sleep -Seconds 10

Write-Host "Uploading zip..." -ForegroundColor Yellow
az webapp deploy --name $APP --resource-group $RG --src-path $ZIP --type zip --output none
$D = $LASTEXITCODE
Remove-Item $ZIP -Force -ErrorAction SilentlyContinue
Write-Host "Deploy exit code: $D" -ForegroundColor Gray

# -------------------------------------------------------
# STEP 4 - Poll for site to come up (5 min max)
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 4: Waiting for site (up to 5 min) ===" -ForegroundColor Cyan

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
        $elapsed = ($i + 1) * 15
        Write-Host "  ${elapsed}s - waiting..." -ForegroundColor Gray
    }
}

# -------------------------------------------------------
# STEP 5 - Seed if live but products missing
# -------------------------------------------------------
if ($LIVE -and $P) {
    $CRED = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("$($P.userName):$($P.userPWD)"))
    Write-Host ""
    Write-Host "=== STEP 5: Checking if seed ran ===" -ForegroundColor Cyan
    try {
        $PC = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/api/products?limit=1" -TimeoutSec 15
        if ($PC.products.Count -gt 0) {
            Write-Host "Products exist - seed already ran!" -ForegroundColor Green
        } else {
            Write-Host "No products - triggering seed via Kudu..." -ForegroundColor Yellow
            $SEED = '{"command":"node scripts/seed.js","dir":"site\\wwwroot"}'
            $R = Invoke-RestMethod -Uri "https://$APP.scm.azurewebsites.net/api/command" -Method Post `
                -Headers @{ "Authorization" = "Basic $CRED"; "Content-Type" = "application/json" } `
                -Body $SEED -TimeoutSec 120
            Write-Host "Seeded!" -ForegroundColor Green
            Write-Host $R.Output
        }
    } catch {
        Write-Host "Could not verify products: $_" -ForegroundColor Yellow
    }
}

if (-not $LIVE) {
    Write-Host ""
    Write-Host "Site did not come up. Check logs:" -ForegroundColor Red
    Write-Host "  az webapp log tail --name $APP --resource-group $RG" -ForegroundColor Cyan
    Write-Host "  https://$APP.scm.azurewebsites.net/api/logs/docker" -ForegroundColor Cyan
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
