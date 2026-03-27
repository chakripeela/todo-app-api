from flask import Flask, request, jsonify, g
import msal
import jwt
from datetime import datetime
import uuid
import os
import struct
from dotenv import load_dotenv
import pyodbc
from contextlib import contextmanager
from azure.identity import DefaultAzureCredential

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Microsoft Entra ID (Azure AD) configuration
TENANT_ID = "d1757f34-71b6-46de-96c4-53d7e63ac048"
CLIENT_ID = "44ac30db-086a-4b08-8baf-1ec3bc4cb43e"
API_AUDIENCE = CLIENT_ID  # Usually the client_id of the API app registration
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
ISSUER = f"https://login.microsoftonline.com/{TENANT_ID}/"

def validate_access_token(token):
    """Validate the JWT access token from Microsoft Entra ID (Azure AD)."""
    # Get public keys from Microsoft
    import requests
    openid_config_url = f"{AUTHORITY}/v2.0/.well-known/openid-configuration"
    resp = requests.get(openid_config_url)
    jwks_uri = resp.json().get("jwks_uri")
    keys = requests.get(jwks_uri).json()["keys"]

    # Decode and validate token
    try:
        unverified_header = jwt.get_unverified_header(token)
        for key in keys:
            if key["kid"] == unverified_header["kid"]:
                public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
                break
        else:
            return False, "Public key not found"

        payload = jwt.decode(
            token,
            public_key,
            algorithms=[unverified_header["alg"]],
            audience=API_AUDIENCE,
            issuer=ISSUER,
            options={"verify_exp": True, "verify_aud": True, "verify_iss": True}
        )
        return True, payload
    except Exception as e:
        return False, str(e)

# Protect all /api/* endpoints
@app.before_request
def check_jwt_token():
    if request.path.startswith("/api/"):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401
        token = auth_header.split(" ", 1)[1]
        valid, result = validate_access_token(token)
        if not valid:
            return jsonify({"error": f"Invalid access token: {result}"}), 401
        g.user = result  # Optionally store user info for use in endpoints

# Mount path where the CSI driver places Key Vault secrets as files
SECRETS_MOUNT_PATH = os.getenv('SECRETS_MOUNT_PATH', '/mnt/secrets-store')


def get_secret(name, default=None):
    """Read a secret from the CSI-mounted volume, falling back to env vars."""
    secret_file = os.path.join(SECRETS_MOUNT_PATH, name)
    if os.path.isfile(secret_file):
        with open(secret_file, 'r') as f:
            return f.read().strip()
    # Fallback: env var (upper-cased, hyphens to underscores)
    env_key = name.upper().replace('-', '_')
    return os.getenv(env_key, default)


# Azure SQL Database connection configuration
DB_SERVER = get_secret('db-server')
DB_NAME = get_secret('db-name')
DB_USER = get_secret('db-user')      # Optional - for local dev fallback
DB_PASSWORD = get_secret('db-password')  # Optional - for local dev fallback
MANAGED_IDENTITY_CLIENT_ID = get_secret('managed-identity-client-id')  # Required in AKS with multiple identities


def get_connection_string():
    """Build connection string with managed identity authentication"""
    
    # Check if using managed identity (when user/password are not provided)
    if not DB_USER or not DB_PASSWORD:
        # Use managed identity
        credential = DefaultAzureCredential(
            managed_identity_client_id=MANAGED_IDENTITY_CLIENT_ID
        )
        token = credential.get_token('https://database.windows.net/.default').token
        
        # Connection string with AAD token
        connection_string = (
            f'Driver={{ODBC Driver 18 for SQL Server}};'
            f'Server=tcp:{DB_SERVER},1433;'
            f'Database={DB_NAME};'
            f'Encrypt=yes;'
            f'TrustServerCertificate=no;'
            f'Connection Timeout=30;'
        )
        return connection_string, token
    else:
        # Use SQL authentication (for local development)
        connection_string = (
            f'Driver={{ODBC Driver 18 for SQL Server}};'
            f'Server=tcp:{DB_SERVER},1433;'
            f'Database={DB_NAME};'
            f'Uid={DB_USER};'
            f'Pwd={DB_PASSWORD};'
            f'Encrypt=yes;'
            f'TrustServerCertificate=no;'
            f'Connection Timeout=30;'
        )
        return connection_string, None


@contextmanager
def get_db_connection():
    """Get a database connection"""
    connection_string, token = get_connection_string()
    
    if token:
        # For managed identity, use token-based connection
        # Token must be encoded as a byte struct for pyodbc (required on ARM64)
        token_bytes = token.encode('UTF-16-LE')
        token_struct = struct.pack(f'<I{len(token_bytes)}s', len(token_bytes), token_bytes)
        conn = pyodbc.connect(connection_string, attrs_before={1256: token_struct})
    else:
        # For SQL auth, use standard connection
        conn = pyodbc.connect(connection_string)
    
    conn.setencoding(encoding='utf-8')
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Initialize database tables if they don't exist"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Add user_id column if not exists, or create table with user_id
            cursor.execute('''
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='tasks' AND xtype='U')
                CREATE TABLE tasks (
                    id NVARCHAR(36) PRIMARY KEY,
                    user_id NVARCHAR(128) NOT NULL,
                    title NVARCHAR(255) NOT NULL,
                    description NVARCHAR(MAX),
                    completed BIT DEFAULT 0,
                    createdAt DATETIME DEFAULT GETUTCDATE()
                )
                ELSE IF NOT EXISTS (SELECT * FROM syscolumns WHERE id=OBJECT_ID('tasks') AND name='user_id')
                ALTER TABLE tasks ADD user_id NVARCHAR(128) NOT NULL DEFAULT ''
            ''')
            
            conn.commit()
            print("Database initialized successfully")
    except Exception as e:
        print(f"Error initializing database: {e}")
        raise


@app.route("/api/tasks", methods=["GET"])
def get_tasks():
    """Get all tasks from database"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            user_id = g.user.get("oid")
            cursor.execute('SELECT id, title, description, completed, createdAt FROM tasks WHERE user_id = ? ORDER BY createdAt DESC', (user_id,))
            tasks = []
            for row in cursor.fetchall():
                tasks.append({
                    "id": row[0],
                    "title": row[1],
                    "description": row[2],
                    "completed": bool(row[3]),
                    "createdAt": row[4].isoformat() if row[4] else None
                })
            return jsonify(tasks)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/tasks", methods=["POST"])
def create_task():
    """Create a new task"""
    data = request.json
    
    if not data or "title" not in data:
        return jsonify({"error": "title is required"}), 400
    
    task_id = str(uuid.uuid4())
    
    try:
        user_id = g.user.get("oid")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO tasks (id, user_id, title, description, completed, createdAt)
                VALUES (?, ?, ?, ?, 0, GETUTCDATE())
            ''', (task_id, user_id, data["title"], data.get("description", "")))
            conn.commit()
            # Fetch the created task
            cursor.execute('SELECT id, title, description, completed, createdAt FROM tasks WHERE id = ?', (task_id,))
            row = cursor.fetchone()
            return jsonify({
                "id": row[0],
                "title": row[1],
                "description": row[2],
                "completed": bool(row[3]),
                "createdAt": row[4].isoformat() if row[4] else None
            }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/tasks/<task_id>", methods=["PUT"])
def update_task(task_id):
    """Update an existing task"""
    data = request.json

    if not data:
        return jsonify({"error": "Request body is required"}), 400

    try:
        user_id = g.user.get("oid")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Check if task exists and belongs to user
            cursor.execute('SELECT id FROM tasks WHERE id = ? AND user_id = ?', (task_id, user_id))
            if not cursor.fetchone():
                return jsonify({"error": "Task not found or not owned by user"}), 404
            # Build dynamic SET clause
            fields = []
            values = []
            if "title" in data:
                fields.append("title = ?")
                values.append(data["title"])
            if "description" in data:
                fields.append("description = ?")
                values.append(data["description"])
            if "completed" in data:
                fields.append("completed = ?")
                values.append(1 if data["completed"] else 0)
            if not fields:
                return jsonify({"error": "No valid fields to update"}), 400
            values.append(task_id)
            values.append(user_id)
            cursor.execute(f'''
                UPDATE tasks SET {', '.join(fields)} WHERE id = ? AND user_id = ?
            ''', values)
            conn.commit()
            # Fetch the updated task
            cursor.execute('SELECT id, title, description, completed, createdAt FROM tasks WHERE id = ?', (task_id,))
            row = cursor.fetchone()
            return jsonify({
                "id": row[0],
                "title": row[1],
                "description": row[2],
                "completed": bool(row[3]),
                "createdAt": row[4].isoformat() if row[4] else None
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/tasks/<task_id>", methods=["DELETE"])
def delete_task(task_id):
    """Delete a task"""
    try:
        user_id = g.user.get("oid")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Check if task exists and belongs to user
            cursor.execute('SELECT id FROM tasks WHERE id = ? AND user_id = ?', (task_id, user_id))
            if not cursor.fetchone():
                return jsonify({"error": "Task not found or not owned by user"}), 404
            # Delete the task
            cursor.execute('DELETE FROM tasks WHERE id = ? AND user_id = ?', (task_id, user_id))
            conn.commit()
            return "", 204
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    """Health check"""
    return jsonify({"status": "ok"})


@app.route("/", methods=["GET"])
def root():
    """Root endpoint"""
    return jsonify({"message": "Todo API", "docs": "/docs"})


if __name__ == "__main__":
    # Initialize database
    init_db()
    app.run(host="0.0.0.0", port=8000, debug=True)

