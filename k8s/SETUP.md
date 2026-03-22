# AKS Deployment Setup Guide

## Prerequisites

- Azure subscription with AKS cluster running
- Azure Container Registry (ACR)
- GitHub repository with this code
- Azure CLI installed locally

## Step 1: Set up GitHub Secrets

Add the following secrets to your GitHub repository (Settings → Secrets and variables → Actions → New repository secret):

| Secret Name          | Description                                  | Example                     |
| -------------------- | -------------------------------------------- | --------------------------- |
| `AZURE_CREDENTIALS`  | Service principal credentials in JSON format | See Step 2                  |
| `ACR_NAME`           | Your ACR name (without .azurecr.io)          | `mytodoregistry`            |
| `ACR_LOGIN_SERVER`   | Full ACR login server URL                    | `mytodoregistry.azurecr.io` |
| `AKS_RESOURCE_GROUP` | Azure resource group containing AKS          | `myresourcegroup`           |
| `AKS_CLUSTER_NAME`   | Your AKS cluster name                        | `myakscluster`              |

## Step 2: Create Service Principal and AZURE_CREDENTIALS

Run these commands in your terminal:

```bash
# Login to Azure
az login

# Create a service principal
az ad sp create-for-rbac --name github-aks-deploy \
  --role "Contributor" \
  --scopes /subscriptions/<SUBSCRIPTION_ID>
```

Copy the output JSON and use it as the value for the `AZURE_CREDENTIALS` secret.

## Step 3: Configure ACR Image Pull

The workflow needs to pull images from ACR. Create an image pull secret:

```bash
# Get your ACR admin credentials
az acr credential show --name <ACR_NAME> --query passwords[0].value -o tsv

# Create the image pull secret in your AKS cluster
kubectl create secret docker-registry acr-secret \
  --docker-server=<ACR_LOGIN_SERVER> \
  --docker-username=<ACR_USERNAME> \
  --docker-password=<ACR_PASSWORD> \
  --docker-email=user@example.com

# Verify it was created
kubectl get secret acr-secret
```

## Step 4: Create Kubernetes Secrets for Database

Create a Kubernetes secret for database credentials:

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

## Step 5: Create ServiceAccount (Optional but Recommended)

```bash
kubectl create serviceaccount todo-api
kubectl create clusterrolebinding todo-api-binding \
  --clusterrole=view \
  --serviceaccount=default:todo-api
```

## Step 6: Add Health Check Endpoint

Update your Flask app to include a health check endpoint:

```python
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy"}), 200
```

## Step 7: Deploy

Push to your main branch to trigger the GitHub Actions workflow:

```bash
git add .
git commit -m "Add AKS deployment configuration"
git push origin main
```

Monitor the workflow in GitHub Actions tab.

## Step 8: Access Your Service

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
