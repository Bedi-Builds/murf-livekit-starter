
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "analytics.db"

def init_analytics_db():
    """Create analytics tables if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS calls (
            call_id TEXT PRIMARY KEY,
            participant_name TEXT,
            start_time TEXT,
            end_time TEXT,
            duration_seconds INTEGER,
            status TEXT,
            created_at TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_date TEXT,
            total_calls INTEGER,
            total_duration INTEGER,
            avg_duration REAL,
            updated_at TEXT
        )
    """)
    
    conn.commit()
    conn.close()

def log_call(call_id: str, participant_name: str, start_time: str, end_time: str, duration_seconds: int, status: str):
    """Log a call to the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT OR REPLACE INTO calls 
        (call_id, participant_name, start_time, end_time, duration_seconds, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (call_id, participant_name, start_time, end_time, duration_seconds, status, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()

def get_analytics():
    """Fetch all analytics for the dashboard."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM calls ORDER BY start_time DESC LIMIT 100")
    calls = cursor.fetchall()
    
    cursor.execute("""
        SELECT COUNT(*) as total_calls, 
               COALESCE(SUM(duration_seconds), 0) as total_duration,
               COALESCE(AVG(duration_seconds), 0) as avg_duration
        FROM calls
    """)
    summary = cursor.fetchone()
    
    conn.close()
    
    return {
        "calls": [dict(c) for c in calls],
        "summary": dict(summary) if summary else {}
    }

# Initialize on import
init_analytics_db()
