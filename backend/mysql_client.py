import os
import uuid
import mysql.connector
from mysql.connector import pooling

_pool = None

USER_REPORT_KEYS = ["tera", "pgta", "karyotype", "nipt", "hla", "billing"]


def _is_configured():
    return bool(os.getenv("MYSQL_HOST") and os.getenv("MYSQL_USER") and os.getenv("MYSQL_DATABASE"))

def _get_pool():
    global _pool
    if _pool is None:
        host     = os.getenv("MYSQL_HOST", "localhost")
        port     = int(os.getenv("MYSQL_PORT", "3306"))
        user     = os.getenv("MYSQL_USER", "")
        password = os.getenv("MYSQL_PASSWORD", "")
        database = os.getenv("MYSQL_DATABASE", "")

        if not host or not user or not database:
            raise RuntimeError(
                "MYSQL_HOST, MYSQL_USER, and MYSQL_DATABASE must be set in your .env file."
            )
        _pool = pooling.MySQLConnectionPool(
            pool_name="report_pool",
            pool_size=5,
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
        )
        _init_schema()
    return _pool


def _init_schema():
    conn = _pool.get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id          INT AUTO_INCREMENT PRIMARY KEY,
                user_id     VARCHAR(255),
                file_url    VARCHAR(500),
                report_type VARCHAR(100),
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            VARCHAR(36) PRIMARY KEY,
                mobile_number VARCHAR(255) UNIQUE NOT NULL,
                password      VARCHAR(255),
                name          VARCHAR(255),
                role          VARCHAR(10) NOT NULL,
                report        VARCHAR(50),
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cur.execute("ALTER TABLE users MODIFY password VARCHAR(255) NULL")
        conn.commit()
        try:
            cur.execute("ALTER TABLE users ADD COLUMN name VARCHAR(255) NULL")
            conn.commit()
        except Exception:
            pass  # column already exists
        cur.execute("SELECT COUNT(*) FROM users")
        if cur.fetchone()[0] == 0:
            
            print(
                "[mysql_client] `users` table is empty — no admin configured. "
                "Insert one manually with a real IT-provisioned mobile number; "
                "see the comment above this line for the SQL."
            )
        cur.close()
    finally:
        conn.close()


mysql_enabled = _is_configured()


# ── User / access-control helpers ──────────────────────────────────────────

def _row_to_user(row: dict) -> dict:
    return {k: v for k, v in row.items() if k != "password"}


def list_users():
    conn = _get_pool().get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users ORDER BY mobile_number")
        rows = cur.fetchall()
        cur.close()
        return [_row_to_user(r) for r in rows]
    finally:
        conn.close()


def get_user_by_mobile_number(mobile_number: str):
    """Looks up role/report by mobile number only — identity is verified
    upstream by the genetics auth gateway, not by a local password."""
    conn = _get_pool().get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE mobile_number = %s", (mobile_number,))
        row = cur.fetchone()
        cur.close()
        return _row_to_user(row) if row else None
    finally:
        conn.close()


def create_user(mobile_number: str, role: str, report: str | None, password: str | None = None, name: str | None = None):
    conn = _get_pool().get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT 1 FROM users WHERE mobile_number = %s", (mobile_number,))
        if cur.fetchone():
            cur.close()
            raise ValueError("That mobile number already exists.")
        user_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO users (id, mobile_number, password, name, role, report) VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, mobile_number, password, name, role, None if role == "admin" else report),
        )
        conn.commit()
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
        return _row_to_user(row)
    finally:
        conn.close()


def update_user(user_id: str, **fields):
    conn = _get_pool().get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        existing = cur.fetchone()
        if not existing:
            cur.close()
            raise LookupError("User not found.")

        mobile_number = fields.get("mobile_number", existing["mobile_number"]) or existing["mobile_number"]
        password = fields.get("password") or existing["password"]
        name = fields.get("name") if "name" in fields else existing.get("name")
        role = fields.get("role", existing["role"]) or existing["role"]
        report = fields["report"] if "report" in fields else existing["report"]
        if role == "admin":
            report = None

        if mobile_number != existing["mobile_number"]:
            cur.execute("SELECT 1 FROM users WHERE mobile_number = %s AND id != %s", (mobile_number, user_id))
            if cur.fetchone():
                cur.close()
                raise ValueError("That mobile number already exists.")

        cur.execute(
            "UPDATE users SET mobile_number=%s, password=%s, name=%s, role=%s, report=%s WHERE id=%s",
            (mobile_number, password, name, role, report, user_id),
        )
        conn.commit()
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
        return _row_to_user(row)
    finally:
        conn.close()


def delete_user(user_id: str):
    conn = _get_pool().get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT role FROM users WHERE id = %s", (user_id,))
        existing = cur.fetchone()
        if not existing:
            cur.close()
            raise LookupError("User not found.")
        if existing["role"] == "admin":
            cur.execute("SELECT COUNT(*) AS n FROM users WHERE role = 'admin' AND id != %s", (user_id,))
            if cur.fetchone()["n"] == 0:
                cur.close()
                raise ValueError("Cannot delete the last remaining admin account.")
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        cur.close()
    finally:
        conn.close()


def upload_pdf(file_path: str, file_name: str) -> str:
    local_url = f"/reports/{os.path.basename(file_path)}"
    if _is_configured():
        try:
            save_report(None, local_url, "TERA")
        except Exception as e:
            print(f"[db] save_report: {e}")
    return local_url


def upload_pgta_file(file_path: str, file_name: str) -> str:
    local_url = f"/reports-pgta/{os.path.basename(file_path)}"
    if _is_configured():
        try:
            save_report(None, local_url, "PGTA")
        except Exception as e:
            print(f"[db] save_report: {e}")
    return local_url


def save_report(user_id, file_url, report_type):
    conn = _get_pool().get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO reports (user_id, file_url, report_type) VALUES (%s, %s, %s)",
            (user_id, file_url, report_type),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()
