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

**Get all tasks:**

```bash
curl http://localhost:8000/api/tasks
```

**Create a task:**

```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"My Task","description":"Task description"}'
```

**Delete a task:**

```bash
curl -X DELETE http://localhost:8000/api/tasks/{id}
```

**View API docs:**
http://localhost:8000/docs
