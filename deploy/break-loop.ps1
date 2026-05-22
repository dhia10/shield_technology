# Ange Gardien - Break crash loop and redeploy
# Strategy:
#   1. Set startup to a minimal 1-line HTTP server (no MongoDB, no crash)
#   2. Start the app - it responds immediately to health checks
#   3. Deploy the real fixed code via Kudu
#   4. Restore startup to "node server.js"
#   5. Restart

$ErrorActionPreference = "Continue"

$SUB = "dd304ca8-be36-4ad8-a6e0-34f6f9be2698"
$RG  = "ange-gardien-rg"
$APP = "ange-gardien-web"
$PROJ = Split-Path -Parent $PSScriptRoot

az account set --subscription $SUB

# -------------------------------------------------------
# STEP 1 - Set minimal startup command (no crash)
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 1: Setting minimal startup (breaks crash loop) ===" -ForegroundColor Cyan

$MINIMAL = "node -e `"require('http').createServer(function(q,r){r.writeHead(200);r.end('ok')}).listen(process.env.PORT||8080,function(){console.log('ready on '+process.env.PORT)})`""

az webapp config set --name $APP --resource-group $RG --startup-file $MINIMAL --output none
Write-Host "Startup set to minimal HTTP server." -ForegroundColor Green

# -------------------------------------------------------
# STEP 2 - Start app and wait for it to respond
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 2: Starting app ===" -ForegroundColor Cyan
az webapp start --name $APP --resource-group $RG --output none
Write-Host "Waiting for minimal server to respond..." -ForegroundColor Gray

$KUDU_UP = $false
for ($i = 0; $i -lt 12; $i++) {
    Start-Sleep -Seconds 10
    try {
        $CHECK = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net" -TimeoutSec 8 -ErrorAction SilentlyContinue
        Write-Host "App is responding!" -ForegroundColor Green
        $KUDU_UP = $true
        break
    } catch {
        Write-Host "  $(($i+1)*10)s..." -ForegroundColor Gray
    }
}

if (-not $KUDU_UP) {
    Write-Host "App didn't respond yet, proceeding with deploy anyway..." -ForegroundColor Yellow
}

# -------------------------------------------------------
# STEP 3 - Deploy real code via az webapp deploy
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 3: Deploying real code ===" -ForegroundColor Cyan

$ZIP = "$env:TEMP\ag-breakloop.zip"
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

Write-Host "Uploading real code..." -ForegroundColor Yellow
az webapp deploy --name $APP --resource-group $RG --src-path $ZIP --type zip --output none
$D = $LASTEXITCODE
Remove-Item $ZIP -Force -ErrorAction SilentlyContinue
Write-Host "Deploy exit: $D" -ForegroundColor Gray

# -------------------------------------------------------
# STEP 4 - Restore real startup command
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 4: Restoring real startup ===" -ForegroundColor Cyan
az webapp config set --name $APP --resource-group $RG --startup-file "node server.js" --output none
Write-Host "Startup restored to: node server.js" -ForegroundColor Green

# -------------------------------------------------------
# STEP 5 - Restart with real code
# -------------------------------------------------------
Write-Host ""
Write-Host "=== STEP 5: Restarting with real server.js ===" -ForegroundColor Cyan
az webapp restart --name $APP --resource-group $RG --output none
Write-Host "Restarted. Waiting for boot (port binds in <1s now)..." -ForegroundColor Gray

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
        Write-Host "  $(($i+1)*15)s - starting..." -ForegroundColor Gray
    }
}

# -------------------------------------------------------
# STEP 6 - Check seed
# -------------------------------------------------------
if ($LIVE) {
    Write-Host ""
    Write-Host "=== STEP 6: Checking seed ===" -ForegroundColor Cyan
    Start-Sleep -Seconds 20
    try {
        $PC = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/api/products?limit=1" -TimeoutSec 15
        if ($PC.products -and $PC.products.Count -gt 0) {
            Write-Host "Products found - auto-seed ran!" -ForegroundColor Green
        } else {
            Write-Host "No products yet (auto-seed may still be running in background)." -ForegroundColor Yellow
            Write-Host "Wait 60s then check: https://$APP.azurewebsites.net" -ForegroundColor Gray
            Write-Host "Or run seed manually: https://$APP.scm.azurewebsites.net/DebugConsole" -ForegroundColor Cyan
            Write-Host "  node scripts/seed.js" -ForegroundColor White
        }
    } catch {
        Write-Host "Product check failed: $_" -ForegroundColor Yellow
    }
}

if (-not $LIVE) {
    Write-Host ""
    Write-Host "Still not up. Get logs:" -ForegroundColor Red
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
