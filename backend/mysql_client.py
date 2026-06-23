import os
import uuid
import mysql.connector
from mysql.connector import pooling

_pool = None

# Report keys must match each app's own identifier (used by the per-page
# access guard script embedded in tera.html / pgta.html / nipt.html /
# karyotype.html / hla.html).
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
        # Per-report access-control table — each non-admin user is locked
        # to exactly one report (matches the "3 users per report" access
        # model). Identity itself is verified by IT's genetics auth
        # gateway (see genetics_auth_client.py); this table only maps an
        # already-verified username to a role + report, so `password` is
        # unused going forward (kept nullable for old rows).
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id         VARCHAR(36) PRIMARY KEY,
                username   VARCHAR(255) UNIQUE NOT NULL,
                password   VARCHAR(255),
                role       VARCHAR(10) NOT NULL,
                report     VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cur.execute("ALTER TABLE users MODIFY password VARCHAR(255) NULL")
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM users")
        if cur.fetchone()[0] == 0:
            # Login is now delegated to IT's genetics auth gateway (see
            # genetics_auth_client.py) — there's no local password check
            # left to seed a usable default admin with. The first admin
            # row must be inserted manually using a real IT-provisioned
            # username, e.g.:
            #   INSERT INTO users (id, username, role, report)
            #   VALUES (UUID(), '<it-provisioned-username>', 'admin', NULL);
            print(
                "[mysql_client] `users` table is empty — no admin configured. "
                "Insert one manually with a real IT-provisioned username; "
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
        cur.execute("SELECT * FROM users ORDER BY username")
        rows = cur.fetchall()
        cur.close()
        return [_row_to_user(r) for r in rows]
    finally:
        conn.close()


def get_user_by_username(username: str):
    """Looks up role/report by username only — identity is verified
    upstream by the genetics auth gateway, not by a local password."""
    conn = _get_pool().get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
        cur.close()
        return _row_to_user(row) if row else None
    finally:
        conn.close()


def create_user(username: str, role: str, report: str | None, password: str | None = None):
    conn = _get_pool().get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT 1 FROM users WHERE username = %s", (username,))
        if cur.fetchone():
            cur.close()
            raise ValueError("That username already exists.")
        user_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO users (id, username, password, role, report) VALUES (%s, %s, %s, %s, %s)",
            (user_id, username, password, role, None if role == "admin" else report),
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

        username = fields.get("username", existing["username"]) or existing["username"]
        password = fields.get("password") or existing["password"]
        role = fields.get("role", existing["role"]) or existing["role"]
        report = fields["report"] if "report" in fields else existing["report"]
        if role == "admin":
            report = None

        if username != existing["username"]:
            cur.execute("SELECT 1 FROM users WHERE username = %s AND id != %s", (username, user_id))
            if cur.fetchone():
                cur.close()
                raise ValueError("That username already exists.")

        cur.execute(
            "UPDATE users SET username=%s, password=%s, role=%s, report=%s WHERE id=%s",
            (username, password, role, report, user_id),
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
