$SUB  = "dd304ca8-be36-4ad8-a6e0-34f6f9be2698"
$RG   = "ange-gardien-rg"
$PLAN = "ange-gardien-plan"
$APP  = "ange-gardien-web"
$DB   = "ange-gardiendb01"
$ST   = "angegardienblob01"
$CTR  = "shield-media"

az account set --subscription $SUB

Write-Host "=== STEP 1: Create Web App ===" -ForegroundColor Cyan
az webapp show --name $APP --resource-group $RG --output none 2>$null
if ($LASTEXITCODE -ne 0) {
    az webapp create --name $APP --resource-group $RG --plan $PLAN --runtime "NODE:20-lts" --output table
}
az webapp config set --name $APP --resource-group $RG --startup-file "node server.js" --output none
Write-Host "Web App ready." -ForegroundColor Green

Write-Host "=== STEP 2: Get Connection Strings ===" -ForegroundColor Cyan
$MONGO = az cosmosdb keys list --name $DB --resource-group $RG --type connection-strings --query "connectionStrings[0].connectionString" --output tsv
$BLOB  = az storage account show-connection-string --name $ST --resource-group $RG --query connectionString --output tsv
Write-Host "Got connection strings." -ForegroundColor Green

Write-Host "=== STEP 3: Set App Settings via REST ===" -ForegroundColor Cyan
$JWT = [System.Guid]::NewGuid().ToString("N") + [System.Guid]::NewGuid().ToString("N")
$PROPS = [ordered]@{
    MONGODB_URI = $MONGO
    AZURE_STORAGE_CONNECTION_STRING = $BLOB
    AZURE_STORAGE_CONTAINER = $CTR
    JWT_SECRET = $JWT
    NODE_ENV = "production"
    ADMIN_EMAIL = "admin@shieldtechnology.tn"
    ADMIN_PASSWORD = "Shield@2025!"
    WEBSITE_NODE_DEFAULT_VERSION = "~20"
    SCM_DO_BUILD_DURING_DEPLOYMENT = "true"
}
$BODY = (@{ properties = $PROPS } | ConvertTo-Json -Depth 5)
$FILE = "$env:TEMP\ag-settings.json"
[System.IO.File]::WriteAllText($FILE, $BODY, [System.Text.Encoding]::UTF8)
$URL = "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Web/sites/$APP/config/appsettings?api-version=2022-03-01"
az rest --method PUT --url $URL --body "@$FILE" --output none
Remove-Item $FILE -Force -ErrorAction SilentlyContinue
Write-Host "Settings applied." -ForegroundColor Green

Write-Host "=== STEP 4: Deploy Code ===" -ForegroundColor Cyan
$PROJ = Split-Path -Parent $PSScriptRoot
$ZIP  = "$env:TEMP\ag-final.zip"
if (Test-Path $ZIP) { Remove-Item $ZIP -Force }
$SKIP_DIRS  = @("node_modules",".git","deploy",".vscode")
$SKIP_FILES = @(".env")
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
Write-Host "Zip: $([math]::Round((Get-Item $ZIP).Length/1KB)) KB" -ForegroundColor Gray
az webapp deploy --name $APP --resource-group $RG --src-path $ZIP --type zip --output table
Remove-Item $ZIP -Force -ErrorAction SilentlyContinue
Write-Host "Code deployed." -ForegroundColor Green

Write-Host "=== STEP 5: Seed Database (waiting 50s) ===" -ForegroundColor Cyan
Start-Sleep -Seconds 50
$PROFS = az webapp deployment list-publishing-profiles --name $APP --resource-group $RG | ConvertFrom-Json
$P = $PROFS | Where-Object { $_.publishMethod -eq "MSDeploy" } | Select-Object -First 1
if ($P) {
    $CRED = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("$($P.userName):$($P.userPWD)"))
    $SEED = '{"command":"node scripts/seed.js","dir":"site\\wwwroot"}'
    try {
        $R = Invoke-RestMethod -Uri "https://$APP.scm.azurewebsites.net/api/command" -Method Post -Headers @{ "Authorization" = "Basic $CRED"; "Content-Type" = "application/json" } -Body $SEED -TimeoutSec 120
        Write-Host "Database seeded!" -ForegroundColor Green
        Write-Host $R.Output
    } catch {
        Write-Host "Seed manually: https://$APP.scm.azurewebsites.net/DebugConsole" -ForegroundColor Yellow
        Write-Host "Command: node scripts/seed.js" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "=== DONE ===" -ForegroundColor Green
Write-Host "Site:  https://$APP.azurewebsites.net" -ForegroundColor Cyan
Write-Host "Admin: https://$APP.azurewebsites.net/admin" -ForegroundColor Cyan
Write-Host "Login: admin@shieldtechnology.tn / Shield@2025!" -ForegroundColor Cyan
