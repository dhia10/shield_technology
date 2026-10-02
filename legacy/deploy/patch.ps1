# Ange Gardien - Patch Deploy
# Deploys source only. Oryx runs npm install on the Linux server.
# The CLI will show "Starting the site..." for ~17 min then timeout -
# that is normal. The site WILL come up. The script waits separately.

$ErrorActionPreference = "Continue"
$SUB  = "dd304ca8-be36-4ad8-a6e0-34f6f9be2698"
$RG   = "ange-gardien-rg"
$APP  = "ange-gardien-web"
$PROJ = Split-Path -Parent $PSScriptRoot

az account set --subscription $SUB

Write-Host ""
Write-Host "=== Patch Deploy ===" -ForegroundColor Cyan

# Zip source only (no node_modules - Oryx installs them on Linux)
Write-Host "[1] Zipping source files..." -ForegroundColor Yellow
$ZIP = "$env:TEMP\ag-patch.zip"
if (Test-Path $ZIP) { Remove-Item $ZIP -Force }

$SKIP_DIRS  = @(".git", "deploy", ".vscode", "node_modules")
$SKIP_FILES = @(".env", "web.config", ".deployment", "deploy.cmd", "deploy.sh", "iisnode.yml")
$FILES = Get-ChildItem -Path $PROJ -Recurse -File | Where-Object {
    $rel = $_.FullName.Substring($PROJ.Length).TrimStart("\")
    $top = $rel.Split("\")[0]
    ($SKIP_DIRS -notcontains $top) -and ($SKIP_FILES -notcontains $_.Name)
}
Write-Host "    $($FILES.Count) files" -ForegroundColor Gray

Add-Type -AssemblyName System.IO.Compression.FileSystem
$ZS = [System.IO.Compression.ZipFile]::Open($ZIP, "Create")
foreach ($F in $FILES) {
    $E = $F.FullName.Substring($PROJ.Length).TrimStart("\").Replace("\", "/")
    try {
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $ZS, $F.FullName, $E, [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
    } catch {}
}
$ZS.Dispose()
Write-Host "    Zip: $([math]::Round((Get-Item $ZIP).Length/1KB,0)) KB" -ForegroundColor Green

# Deploy - will timeout after ~17 min (normal), site starts after
Write-Host "[2] Deploying (CLI may timeout - that is OK, keep waiting)..." -ForegroundColor Yellow
az webapp deploy --name $APP --resource-group $RG --src-path $ZIP --type zip --async --output none
Remove-Item $ZIP -Force -ErrorAction SilentlyContinue
Write-Host "    Deploy command done (timeout is normal)." -ForegroundColor Gray

# Restart to pick up new code
Write-Host "[3] Restarting app..." -ForegroundColor Yellow
az webapp restart --name $APP --resource-group $RG --output none
Write-Host "    Restart sent." -ForegroundColor Gray

# Poll health - up to 10 min
Write-Host "[4] Polling health (up to 10 min)..." -ForegroundColor Yellow
$LIVE = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 15
    try {
        $H = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/api/health" -TimeoutSec 8
        Write-Host ""
        Write-Host "LIVE: $($H | ConvertTo-Json -Compress)" -ForegroundColor Green
        $LIVE = $true
        break
    } catch {
        Write-Host "  $(($i+1)*15)s..." -ForegroundColor Gray
    }
}

if (-not $LIVE) {
    Write-Host "Not responding yet." -ForegroundColor Red
    Write-Host "  az webapp log tail --name $APP --resource-group $RG" -ForegroundColor Cyan
} else {
    Start-Sleep -Seconds 5
    try {
        $PC = Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/api/products" -TimeoutSec 10
        Write-Host "Products: $($PC.count) items in DB" -ForegroundColor Green
    } catch {
        Write-Host "Products: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Site:   https://$APP.azurewebsites.net" -ForegroundColor Cyan
Write-Host "Admin:  https://$APP.azurewebsites.net/admin" -ForegroundColor Cyan
