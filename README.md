# Todo API

Simple Python FastAPI with three endpoints:

- `GET /api/tasks` - Get all tasks
- `POST /api/tasks` - Create a task
- `DELETE /api/tasks/{id}` - Delete a task

## Run Locally

### With Docker Compose (easiest)

```bash
docker-compose up
```

Access at http://localhost:8000

### Without Docker

```bash
pip install -r requirements.txt
python main.py
```

## API Endpoints

## Authentication (Microsoft Entra ID)

All `/api/*` endpoints require a valid Microsoft Entra ID (Azure AD) access token in the `Authorization` header:

```
Authorization: Bearer <access_token>
```

You must obtain an access token for the API (audience = your API's client_id) and include it in every request.

**Get all tasks:**

```bash
curl http://localhost:8000/api/tasks \
  -H "Authorization: Bearer <access_token>"
```

**Create a task:**

```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"title":"My Task","description":"Task description"}'
```

**Delete a task:**

```bash
curl -X DELETE http://localhost:8000/api/tasks/{id} \
  -H "Authorization: Bearer <access_token>"
```

**View API docs:**
http://localhost:8000/docs

**Freelens Setup**

```bash
az login --tenant d1757f34-71b6-46de-96c4-53d7e63ac048
 az aks get-credentials --resource-group rg-todo-app-centralus --name aks-todoapp --overwrite-existing
```

## These are some Manual steps need to be run after the application is deployed

**Run below command to get key_vault_secrets_provider_client_id and update in git secret KV_SECRETS_PROVIDER_CLIENT_ID**

```bash
az aks show --name aks-todoapp --resource-group rg-todo-app-centralus
```

**Add AKS agentpool managed identity in SQL so that AKS can connect to SQL**

```bash
CREATE USER [aks-todoapp-agentpool] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datareader ADD MEMBER [aks-todoapp-agentpool];
ALTER ROLE db_datawriter ADD MEMBER [aks-todoapp-agentpool];
```
