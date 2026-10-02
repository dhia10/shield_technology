# 🛡️ Ange Gardien — Azure Deployment Guide

## Prerequisites
- Azure CLI installed: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli
- Node.js 18+ installed
- Git (optional)

---

## Step 1 — Login to Azure

```bash
az login
```
A browser window will open. Sign in with your student account.

---

## Step 2 — Navigate to project folder

```bash
cd "C:\Users\DELL\Desktop\tarek\shield-technology"
```

---

## Step 3 — Copy and configure .env

```bash
copy .env.example .env
```
Then edit `.env` — the deployment script will fill in most values automatically.

---

## Step 4 — Run the deployment script

**On Windows (Git Bash / WSL):**
```bash
bash deploy/deploy.sh
```

**On Windows (PowerShell) — manual steps:**

```powershell
# Variables
$rg = "ange-gardien-rg"
$loc = "francecentral"
$plan = "ange-gardien-plan"
$app = "ange-gardien-app"        # Change if name taken
$cosmos = "ange-gardien-db"      # Change if name taken
$storage = "angegardienstore"    # Change if name taken

# 1. Resource Group
az group create --name $rg --location $loc

# 2. App Service Plan (Free)
az appservice plan create --name $plan --resource-group $rg --sku F1 --is-linux

# 3. Web App
az webapp create --name $app --resource-group $rg --plan $plan --runtime "NODE:18-lts"
az webapp config set --name $app --resource-group $rg --startup-file "node server.js"

# 4. Cosmos DB
az cosmosdb create --name $cosmos --resource-group $rg --kind MongoDB --server-version 6.0 --locations regionName=$loc failoverPriority=0
az cosmosdb mongodb database create --account-name $cosmos --resource-group $rg --name angegardien

# 5. Storage
az storage account create --name $storage --resource-group $rg --location $loc --sku Standard_LRS
az storage container create --name shield-media --account-name $storage --public-access blob

# 6. Get connection strings
$cosmosConn = az cosmosdb keys list --name $cosmos --resource-group $rg --type connection-strings --query "connectionStrings[0].connectionString" -o tsv
$storageConn = az storage account show-connection-string --name $storage --resource-group $rg --query connectionString -o tsv
$jwt = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes([System.Guid]::NewGuid().ToString() + [System.Guid]::NewGuid().ToString()))

# 7. App settings
az webapp config appsettings set --name $app --resource-group $rg --settings `
  "MONGODB_URI=$cosmosConn" `
  "AZURE_STORAGE_CONNECTION_STRING=$storageConn" `
  "AZURE_STORAGE_CONTAINER=shield-media" `
  "JWT_SECRET=$jwt" `
  "NODE_ENV=production" `
  "ADMIN_EMAIL=admin@shieldtechnology.tn" `
  "ADMIN_PASSWORD=Shield@2025!" `
  "WEBSITE_NODE_DEFAULT_VERSION=~18" `
  "SCM_DO_BUILD_DURING_DEPLOYMENT=true"

# 8. Deploy code (zip deploy)
Compress-Archive -Path * -DestinationPath deploy.zip -Force
az webapp deploy --name $app --resource-group $rg --src-path deploy.zip --type zip
Remove-Item deploy.zip
```

---

## Step 5 — Seed the database

After deployment, open Azure Portal → your App Service → **SSH / Console** and run:

```bash
node scripts/seed.js
```

Or use the Kudu console:
`https://ange-gardien-app.scm.azurewebsites.net/DebugConsole`

---

## Step 6 — Configure custom domain (shieldtechnology.tn)

### DNS Records to add at your domain registrar:

| Type  | Host | Value                              |
|-------|------|------------------------------------|
| CNAME | www  | ange-gardien-app.azurewebsites.net |
| TXT   | asuid.www | (value from Azure verification) |

Then in Azure CLI:
```bash
az webapp config hostname add \
  --webapp-name ange-gardien-app \
  --resource-group ange-gardien-rg \
  --hostname www.shieldtechnology.tn
```

### Enable Free SSL Certificate:
```bash
bash deploy/ssl-custom-domain.sh
```

---

## Access Points After Deployment

| URL | Description |
|-----|-------------|
| `https://ange-gardien-app.azurewebsites.net` | Main website |
| `https://ange-gardien-app.azurewebsites.net/admin` | Admin dashboard |
| `https://ange-gardien-app.azurewebsites.net/api/health` | Health check |
| `https://www.shieldtechnology.tn` | After DNS (24-48h) |

---

## Admin Credentials

| Field | Value |
|-------|-------|
| Email | `admin@shieldtechnology.tn` |
| Password | `Shield@2025!` |
| Role | superadmin |

⚠️ **Change the password immediately after first login!**

---

## Monitoring & Management

```bash
# View live logs
az webapp log tail --name ange-gardien-app --resource-group ange-gardien-rg

# Restart app
az webapp restart --name ange-gardien-app --resource-group ange-gardien-rg

# Scale up (if needed)
az appservice plan update --name ange-gardien-plan --resource-group ange-gardien-rg --sku B1
```

---

## Azure Cost Estimate (Student Subscription)

| Service | Tier | Monthly Cost |
|---------|------|-------------|
| App Service | F1 Free | **$0** |
| Cosmos DB | Serverless | ~$0-5 |
| Blob Storage | LRS | ~$0-2 |
| SSL Certificate | App Service Managed | **$0** |
| **Total** | | **~$0-7/month** |

✅ Well within the $100 student credit!
