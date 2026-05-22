# Ange Gardien - Check if site is live, retry npm install if needed

$ErrorActionPreference = "Continue"

$SUB = "dd304ca8-be36-4ad8-a6e0-34f6f9be2698"
$RG  = "ange-gardien-rg"
$APP = "ange-gardien-web"
$PROJ = Split-Path -Parent $PSScriptRoot

az account set --subscription $SUB

# -------------------------------------------------------
# STEP 1 - Check if site is already live from previous deploy
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 1: Checking if site is already live ===" -ForegroundColor Cyan

$SITE_OK = $false
try {
    $H = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/api/health" -TimeoutSec 20
    Write-Host "Site is LIVE! $($H | ConvertTo-Json -Compress)" -ForegroundColor Green
    $SITE_OK = $true
} catch {
    $STATUS = $_.Exception.Response.StatusCode.value__
    Write-Host "Site status: $STATUS - not fully up yet." -ForegroundColor Yellow
}

# -------------------------------------------------------
# STEP 2 - npm install with retries (if we need to redeploy)
# -------------------------------------------------------
if (-not $SITE_OK) {
    Write-Host ""
    Write-Host "=== STEP 2: npm install (with retries) ===" -ForegroundColor Cyan

    # Configure npm for slow/unstable connections
    npm config set fetch-retry-mintimeout 20000
    npm config set fetch-retry-maxtimeout 120000
    npm config set fetch-retries 5
    npm config set fetch-timeout 300000

    $NPM_OK = $false
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        Write-Host "Attempt $attempt of 3..." -ForegroundColor Yellow
        Push-Location $PROJ
        npm install --omit=dev --no-audit --no-fund --prefer-offline
        $EXIT = $LASTEXITCODE
        Pop-Location
        if ($EXIT -eq 0) { $NPM_OK = $true; break }
        Write-Host "Attempt $attempt failed. Waiting 15s before retry..." -ForegroundColor Yellow
        Start-Sleep -Seconds 15
    }

    if (-not $NPM_OK) {
        Write-Host ""
        Write-Host "npm install failed after 3 attempts." -ForegroundColor Red
        Write-Host ""
        Write-Host "ALTERNATIVE: Deploy without local npm install" -ForegroundColor Yellow
        Write-Host "Open Azure Cloud Shell at: https://shell.azure.com" -ForegroundColor Cyan
        Write-Host "Then paste these commands:" -ForegroundColor White
        Write-Host ""
        Write-Host '  mkdir /tmp/ag && cd /tmp/ag' -ForegroundColor Gray
        Write-Host "  az storage blob download --account-name angegardienblob01 --container-name shield-media --name app.zip --file app.zip --auth-mode login 2>/dev/null || true" -ForegroundColor Gray
        Write-Host ""
        Write-Host "Or simply run the manual seed command below from your browser:" -ForegroundColor Yellow

        $PROFS = az webapp deployment list-publishing-profiles --name $APP --resource-group $RG | ConvertFrom-Json
        $P = $PROFS | Where-Object { $_.publishMethod -eq "MSDeploy" } | Select-Object -First 1
        if ($P) {
            Write-Host "  Kudu console: https://$APP.scm.azurewebsites.net/DebugConsole" -ForegroundColor Cyan
        }
        exit 1
    }

    Write-Host "npm install succeeded!" -ForegroundColor Green
    $NM_MB = [math]::Round((Get-ChildItem "$PROJ\node_modules" -Recurse -File | Measure-Object -Property Length -Sum).Sum/1MB,1)
    Write-Host "node_modules: $NM_MB MB" -ForegroundColor Gray

    # -------------------------------------------------------
    # STEP 3 - Disable server-side build + deploy full zip
    # -------------------------------------------------------
    Write-Host ""
    Write-Host "=== STEP 3: Deploying ===" -ForegroundColor Cyan

    az webapp config appsettings set --name $APP --resource-group $RG `
        --settings "SCM_DO_BUILD_DURING_DEPLOYMENT=false" --output none
    az webapp start --name $APP --resource-group $RG --output none
    Start-Sleep -Seconds 10

    $ZIP = "$env:TEMP\ag-full2.zip"
    if (Test-Path $ZIP) { Remove-Item $ZIP -Force }

    $SKIP_DIRS  = @(".git","deploy",".vscode")
    $SKIP_FILES = @(".env","web.config",".deployment","deploy.cmd","deploy.sh","iisnode.yml")

    $FILES = Get-ChildItem -Path $PROJ -Recurse -File | Where-Object {
        $rel = $_.FullName.Substring($PROJ.Length).TrimStart("\")
        $top = $rel.Split("\")[0]
        ($SKIP_DIRS -notcontains $top) -and ($SKIP_FILES -notcontains $_.Name)
    }

    Write-Host "Zipping $($FILES.Count) files..." -ForegroundColor Gray
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

    Write-Host "Uploading..." -ForegroundColor Yellow
    az webapp deploy --name $APP --resource-group $RG --src-path $ZIP --type zip --output table
    Remove-Item $ZIP -Force -ErrorAction SilentlyContinue
    Write-Host "Deploy command completed." -ForegroundColor Green
    Start-Sleep -Seconds 45
}

# -------------------------------------------------------
# STEP 4 - Seed database
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 4: Seeding database ===" -ForegroundColor Cyan

$PROFS = az webapp deployment list-publishing-profiles --name $APP --resource-group $RG | ConvertFrom-Json
$P = $PROFS | Where-Object { $_.publishMethod -eq "MSDeploy" } | Select-Object -First 1

if ($P) {
    $CRED = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("$($P.userName):$($P.userPWD)"))
    $SEED = '{"command":"node scripts/seed.js","dir":"site\\wwwroot"}'
    try {
        $R = Invoke-RestMethod -Uri "https://$APP.scm.azurewebsites.net/api/command" -Method Post `
            -Headers @{ "Authorization" = "Basic $CRED"; "Content-Type" = "application/json" } `
            -Body $SEED -TimeoutSec 120
        Write-Host "Database seeded!" -ForegroundColor Green
        Write-Host $R.Output
    } catch {
        Write-Host "Auto-seed failed: $_" -ForegroundColor Yellow
        Write-Host "Seed manually at: https://$APP.scm.azurewebsites.net/DebugConsole" -ForegroundColor Cyan
        Write-Host "Command: node scripts/seed.js" -ForegroundColor Cyan
    }
}

# -------------------------------------------------------
# Final check
# -------------------------------------------------------
Write-Host ""
Write-Host "=== Final: Health check ===" -ForegroundColor Cyan
Start-Sleep -Seconds 10
try {
    $H = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/api/health" -TimeoutSec 30
    Write-Host "LIVE: $($H | ConvertTo-Json -Compress)" -ForegroundColor Green
} catch {
    Write-Host "Site not responding to /api/health yet." -ForegroundColor Yellow
    Write-Host "Check: https://$APP.azurewebsites.net" -ForegroundColor Cyan
    Write-Host "Logs:  az webapp log tail --name $APP --resource-group $RG" -ForegroundColor Gray
}

Write-Host ""
Write-Host "=======================================" -ForegroundColor Green
Write-Host "  DONE!" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Green
Write-Host "Site:   https://$APP.azurewebsites.net" -ForegroundColor Cyan
Write-Host "Admin:  https://$APP.azurewebsites.net/admin" -ForegroundColor Cyan
Write-Host "Login:  admin@shieldtechnology.tn / Shield@2025!" -ForegroundColor Cyan
Write-Host ""
