# Ingress Setup for Custom Domain

## Option 1: NGINX Ingress Controller with Let's Encrypt (Recommended for HTTPS)

### Step 1: Install NGINX Ingress Controller

```bash
# Add NGINX Helm repository
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update

# Install NGINX Ingress Controller
helm install nginx-ingress ingress-nginx/ingress-nginx \
  --namespace ingress-nginx \
  --create-namespace \
  --set controller.service.type=LoadBalancer
```

### Step 2: Get the Ingress IP

```bash
kubectl get svc -n ingress-nginx
# Wait for EXTERNAL-IP to be assigned (typically 2-3 minutes)
# Copy the EXTERNAL-IP value
```

### Step 3: Install cert-manager for HTTPS

```bash
# Add Jetstack Helm repository
helm repo add jetstack https://charts.jetstack.io
helm repo update

# Install cert-manager
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --set installCRDs=true
```

### Step 4: Update Ingress Configuration

Replace `yourdomain.com` in `ingress.yml` with your actual domain:

```bash
sed -i 's/yourdomain.com/your-actual-domain.com/g' k8s/ingress.yml
sed -i 's/your-email@example.com/your-email@example.com/g' k8s/cert-issuer.yml
```

### Step 5: Configure DNS

Point your domain to the Ingress Controller's EXTERNAL-IP:

**Option A: Using Azure DNS**

```bash
# Create an Azure DNS Zone
az network dns zone create --resource-group <RG> --name yourdomain.com

# Get the Ingress IP
INGRESS_IP=$(kubectl get svc -n ingress-nginx -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}')

# Create an A record
az network dns record-set a add-record \
  --resource-group <RG> \
  --zone-name yourdomain.com \
  --record-set-name todo-api \
  --ipv4-address $INGRESS_IP
```

**Option B: Using Your Domain Registrar**
Add an A record:

- Name: `todo-api`
- Type: `A`
- Value: `<EXTERNAL-IP from kubectl get svc>`

### Step 6: Deploy Cert Issuer and Ingress

```bash
kubectl apply -f k8s/cert-issuer.yml
kubectl apply -f k8s/ingress.yml
```

### Step 7: Verify

```bash
# Check ingress status
kubectl get ingress

# Check certificate status (may take a few minutes)
kubectl get certificate

# Check cert-manager logs if there are issues
kubectl logs -n cert-manager deploy/cert-manager
```

Once configured, access your API at:

```
https://todo-api.yourdomain.com
```

---

## Option 2: Azure Application Gateway (Alternative)

If you want to use Azure's native application gateway:

```bash
# Install Application Gateway Ingress Controller (AGIC)
helm repo add application-gateway-kubernetes-ingress https://appgwic.blob.core.windows.net/helm
helm repo update

helm install agic application-gateway-kubernetes-ingress/ingress-azure \
  --namespace ingress-azure \
  --create-namespace \
  --set appgw.subscriptionId=<SUBSCRIPTION_ID> \
  --set appgw.resourceGroup=<RESOURCE_GROUP> \
  --set appgw.name=<APP_GATEWAY_NAME> \
  --set rbac.enabled=true
```

Then use the same ingress.yml but adjust annotations:

```yaml
annotations:
  kubernetes.io/ingress.class: "azure/application-gateway"
```

---

## Troubleshooting

### Check ingress status

```bash
kubectl describe ingress todo-api-ingress
kubectl get ingress -o wide
```

### Check certificate

```bash
kubectl describe certificate todo-api-tls
kubectl get certificaterequest
```

### Check cert-manager events

```bash
kubectl get events --sort-by='.lastTimestamp'
```

### View NGINX controller logs

```bash
kubectl logs -n ingress-nginx deploy/nginx-ingress-ingress-nginx-controller
```

### Access via IP temporarily (while DNS propagates)

```bash
# Get the Ingress IP
INGRESS_IP=$(kubectl get svc -n ingress-nginx -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}')

# Test with curl and host header
curl -H "Host: todo-api.yourdomain.com" http://$INGRESS_IP
```

---

## Key Changes

| Before                  | After                         |
| ----------------------- | ----------------------------- |
| Service: `LoadBalancer` | Service: `ClusterIP`          |
| Direct IP access        | Ingress routes traffic        |
| No HTTPS                | Auto HTTPS with Let's Encrypt |
| Any IP from AKS         | Your custom domain            |
