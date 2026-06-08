import os
import mysql.connector
from mysql.connector import pooling

_pool = None


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
        cur.close()
    finally:
        conn.close()


mysql_enabled = _is_configured()


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
