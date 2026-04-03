# AKS Deployment Setup Guide (OIDC with GitHub Actions)

## Prerequisites

- Azure subscription with AKS cluster running
- Azure Container Registry (ACR)
- GitHub repository with this code
- Azure CLI installed locally

## Step 1: Set up GitHub Secrets

Add the following secrets to your GitHub repository (Settings → Secrets and variables → Actions → New repository secret):

| Secret Name             | Description                         | Example                     |
| ----------------------- | ----------------------------------- | --------------------------- |
| `AZURE_CLIENT_ID`       | Service principal client ID         | See Step 2                  |
| `AZURE_TENANT_ID`       | Azure tenant ID                     | See Step 2                  |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID               | See Step 2                  |
| `ACR_NAME`              | Your ACR name (without .azurecr.io) | `mytodoregistry`            |
| `ACR_LOGIN_SERVER`      | Full ACR login server URL           | `mytodoregistry.azurecr.io` |
| `AKS_RESOURCE_GROUP`    | Azure resource group containing AKS | `myresourcegroup`           |
| `AKS_CLUSTER_NAME`      | Your AKS cluster name               | `myakscluster`              |

For DR deployments, add these additional repository secrets:

| Secret Name                        | Description                                     |
| ---------------------------------- | ----------------------------------------------- |
| `AKS_RESOURCE_GROUP_DR`            | Azure resource group containing the DR AKS      |
| `AKS_CLUSTER_NAME_DR`              | DR AKS cluster name                             |
| `KV_SECRETS_PROVIDER_CLIENT_ID_DR` | Client ID for the DR Key Vault CSI provider     |
| `AZURE_CLIENT_ID_DR`               | Optional override if DR uses a different app ID |
| `AZURE_TENANT_ID_DR`               | Optional override if DR uses a different tenant |
| `AZURE_SUBSCRIPTION_ID_DR`         | Optional override if DR uses a different sub    |

## Step 2: Create Service Principal with OIDC Federation

This uses OpenID Connect - no need to store credentials!

```bash
# Login to Azure
az login

# Get your subscription ID
SUBSCRIPTION_ID=$(az account show --query id -o tsv)

# Create a service principal
az ad sp create-for-rbac --name github-aks-deploy \
  --role "Contributor" \
  --scopes /subscriptions/$SUBSCRIPTION_ID
```

Copy the output and extract:

- `appId` → `AZURE_CLIENT_ID`
- `tenant` → `AZURE_TENANT_ID`
- Subscription ID → `AZURE_SUBSCRIPTION_ID`

### Set up OIDC Trust (One-time setup)

```bash
# Set variables
GITHUB_OWNER=<your-github-username>
GITHUB_REPO=<your-repo-name>
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
CLIENT_ID=$(az ad sp list --display-name github-aks-deploy --query '[0].appId' -o tsv)

# Create federated credential for branch main
az identity federated-credential create \
  --name github-federated \
  --identity-name github-aks-deploy \
  --issuer https://token.actions.githubusercontent.com \
  --subject "repo:${GITHUB_OWNER}/${GITHUB_REPO}:ref:refs/heads/main" \
  --resource-group <RESOURCE_GROUP>
```

Or use Azure CLI to set up with service principal:

```bash
# Get the object ID
OBJECT_ID=$(az ad sp show --id <CLIENT_ID> --query id -o tsv)

# Create the federated credential
az rest --method POST \
  --uri "https://graph.microsoft.com/beta/applications/<APP_ID>/federatedIdentityCredentials" \
  --body @- <<EOF
{
  "name": "github-federated",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:${GITHUB_OWNER}/${GITHUB_REPO}:ref:refs/heads/main",
  "description": "GitHub OIDC",
  "audiences": ["api://AzureADTokenExchange"]
}
EOF
```

## Step 3: Create Kubernetes Secrets for Image Pull and Database

First, create the ACR image pull secret:

```bash
# Get your ACR credentials
ACR_USERNAME=$(az acr credential show --name <ACR_NAME> --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name <ACR_NAME> --query passwords[0].value -o tsv)
ACR_LOGIN_SERVER=$(az acr show --name <ACR_NAME> --query loginServer -o tsv)

# Create the image pull secret in your AKS cluster
kubectl create secret docker-registry acr-secret \
  --docker-server=$ACR_LOGIN_SERVER \
  --docker-username=$ACR_USERNAME \
  --docker-password=$ACR_PASSWORD \
  --docker-email=user@example.com

# Verify it was created
kubectl get secret acr-secret
```

Then create the database secrets:

```bash
kubectl create secret generic todo-api-secrets \
  --from-literal=db-server=<YOUR_SQL_SERVER_NAME>.database.windows.net \
  --from-literal=db-name=<DATABASE_NAME> \
  --from-literal=db-user=<DB_USER> \
  --from-literal=db-password=<DB_PASSWORD>

# Verify it was created
kubectl get secret todo-api-secrets
```

**Note:** If using managed identity with Azure SQL, you can leave db-user and db-password empty in your app.

## Step 4: Create ServiceAccount (Optional but Recommended)

```bash
kubectl create serviceaccount todo-api
kubectl create clusterrolebinding todo-api-binding \
  --clusterrole=view \
  --serviceaccount=default:todo-api
```

## Step 5: Add Health Check Endpoint

Update your Flask app to include a health check endpoint:

```python
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy"}), 200
```

## Step 6: Deploy

Push to your main branch to trigger the GitHub Actions workflow:

```bash
git add .
git commit -m "Add AKS deployment configuration"
git push origin main
```

Monitor the workflow in GitHub Actions tab.

## Step 7: Access Your Service

Once deployed, get the external IP:

```bash
kubectl get svc todo-api

# Wait for EXTERNAL-IP to be assigned, then access the API
# Example: http://<EXTERNAL-IP>
```

## Troubleshooting

### Check pod status

```bash
kubectl get pods
kubectl describe pod <POD_NAME>
kubectl logs <POD_NAME>
```

### Check deployment

```bash
kubectl describe deployment todo-api
kubectl get events
```

### Check service

```bash
kubectl get svc
kubectl describe svc todo-api
```

### Rollback to previous version

```bash
kubectl rollout history deployment/todo-api
kubectl rollout undo deployment/todo-api
```
