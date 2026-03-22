from flask import Flask, request, jsonify
from datetime import datetime
import uuid
import os
from dotenv import load_dotenv
import pyodbc
from contextlib import contextmanager
from azure.identity import DefaultAzureCredential

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Azure SQL Database connection configuration
DB_SERVER = os.getenv('DB_SERVER')
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')  # Optional - for local dev fallback
DB_PASSWORD = os.getenv('DB_PASSWORD')  # Optional - for local dev fallback


def get_connection_string():
    """Build connection string with managed identity authentication"""
    
    # Check if using managed identity (when user/password are not provided)
    if not DB_USER or not DB_PASSWORD:
        # Use managed identity
        credential = DefaultAzureCredential()
        token = credential.get_token('https://database.windows.net/.default').token
        
        # Connection string with AAD token
        connection_string = (
            f'Driver={{ODBC Driver 17 for SQL Server}};'
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
            f'Driver={{ODBC Driver 17 for SQL Server}};'
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
        conn = pyodbc.connect(connection_string, attrs_before={1256: token})
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
            
            # Create tasks table if it doesn't exist
            cursor.execute('''
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='tasks' AND xtype='U')
                CREATE TABLE tasks (
                    id NVARCHAR(36) PRIMARY KEY,
                    title NVARCHAR(255) NOT NULL,
                    description NVARCHAR(MAX),
                    completed BIT DEFAULT 0,
                    createdAt DATETIME DEFAULT GETUTCDATE()
                )
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
            cursor.execute('SELECT id, title, description, completed, createdAt FROM tasks ORDER BY createdAt DESC')
            
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
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO tasks (id, title, description, completed, createdAt)
                VALUES (?, ?, ?, 0, GETUTCDATE())
            ''', (task_id, data["title"], data.get("description", "")))
            
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


@app.route("/api/tasks/<task_id>", methods=["DELETE"])
def delete_task(task_id):
    """Delete a task"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Check if task exists
            cursor.execute('SELECT id FROM tasks WHERE id = ?', (task_id,))
            if not cursor.fetchone():
                return jsonify({"error": "Task not found"}), 404
            
            # Delete the task
            cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
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

