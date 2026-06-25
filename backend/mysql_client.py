import os
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
        conn.commit()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS pgta_autosave (
                id          INT AUTO_INCREMENT PRIMARY KEY,
                draft_key   VARCHAR(255) NOT NULL,
                mode        VARCHAR(20) NOT NULL,
                data        LONGTEXT NOT NULL,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uniq_draft_key_mode (draft_key, mode)
            )
        """)
        conn.commit()

        cur.execute("""
            SELECT DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME   = 'users'
              AND COLUMN_NAME  = 'id'
        """)
        id_type_row = cur.fetchone()
        if id_type_row and id_type_row[0].lower() == 'varchar':
            print("[mysql_client] Migrating users table from UUID/VARCHAR to INT/BIGINT schema...")
            cur.execute("SELECT mobile_number, name, role, report FROM users")
            old_users = cur.fetchall()
            cur.execute("DROP TABLE users")
            conn.commit()
            cur.execute("""
                CREATE TABLE users (
                    id            INT AUTO_INCREMENT PRIMARY KEY,
                    mobile_number BIGINT UNIQUE NOT NULL,
                    name          VARCHAR(255),
                    role          VARCHAR(10) NOT NULL,
                    report        VARCHAR(50),
                    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            for (mobile, uname, urole, ureport) in old_users:
                try:
                    cur.execute(
                        "INSERT INTO users (mobile_number, name, role, report) VALUES (%s, %s, %s, %s)",
                        (int(str(mobile).strip()), uname, urole, ureport),
                    )
                except Exception as e:
                    print(f"[mysql_client] Could not re-insert {mobile}: {e}")
            conn.commit()
            print(f"[mysql_client] Migration done - {len(old_users)} user(s) preserved.")
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id            INT AUTO_INCREMENT PRIMARY KEY,
                    mobile_number BIGINT UNIQUE NOT NULL,
                    name          VARCHAR(255),
                    role          VARCHAR(10) NOT NULL,
                    report        VARCHAR(50),
                    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            try:
                cur.execute("ALTER TABLE users MODIFY mobile_number BIGINT NOT NULL")
                conn.commit()
            except Exception:
                pass
            try:
                cur.execute("ALTER TABLE users DROP COLUMN password")
                conn.commit()
            except Exception:
                pass

        cur.execute("SELECT COUNT(*) FROM users")
        if cur.fetchone()[0] == 0:
            print(
                "[mysql_client] `users` table is empty - no admin configured. "
                "Run seed_users.py or insert a user via the Admin page."
            )
        cur.close()
    finally:
        conn.close()


mysql_enabled = _is_configured()



def _row_to_user(row: dict) -> dict:
    return dict(row)


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
        cur.execute(
            "INSERT INTO users (mobile_number, name, role, report) VALUES (%s, %s, %s, %s)",
            (mobile_number, name, role, None if role == "admin" else report),
        )
        conn.commit()
        user_id = cur.lastrowid
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
        return _row_to_user(row)
    finally:
        conn.close()


def update_user(user_id: int, **fields):
    conn = _get_pool().get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        existing = cur.fetchone()
        if not existing:
            cur.close()
            raise LookupError("User not found.")

        mobile_number = fields.get("mobile_number", existing["mobile_number"]) or existing["mobile_number"]
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
            "UPDATE users SET mobile_number=%s, name=%s, role=%s, report=%s WHERE id=%s",
            (mobile_number, name, role, report, user_id),
        )
        conn.commit()
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
        return _row_to_user(row)
    finally:
        conn.close()


def delete_user(user_id: int):
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



def pgta_autosave_save(draft_key: str, mode: str, data: str) -> dict:
    conn = _get_pool().get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO pgta_autosave (draft_key, mode, data) VALUES (%s, %s, %s)
               ON DUPLICATE KEY UPDATE data = VALUES(data), updated_at = CURRENT_TIMESTAMP""",
            (draft_key, mode, data),
        )
        conn.commit()
        cur.execute(
            "SELECT updated_at FROM pgta_autosave WHERE draft_key = %s AND mode = %s",
            (draft_key, mode),
        )
        row = cur.fetchone()
        cur.close()
        return {"updated_at": row[0].isoformat() if row else None}
    finally:
        conn.close()


def pgta_autosave_get(draft_key: str, mode: str):
    conn = _get_pool().get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT data, updated_at FROM pgta_autosave WHERE draft_key = %s AND mode = %s",
            (draft_key, mode),
        )
        row = cur.fetchone()
        cur.close()
        if not row:
            return None
        return {"data": row["data"], "updated_at": row["updated_at"].isoformat()}
    finally:
        conn.close()
