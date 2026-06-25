
import os
import uuid
import sys
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

import mysql.connector

USERS = [
    {"mobile_number": "7358752950", "name": "Jeeva",       "role": "admin",  "report": None},
    {"mobile_number": "9876543210", "name": "Dr. Ravi",    "role": "user",   "report": "hla"},
    {"mobile_number": "9123456780", "name": "Priya",       "role": "user",   "report": "pgta"},
    {"mobile_number": "8888888888", "name": "Kumar",       "role": "user",   "report": "nipt"},
]

VALID_REPORTS = {"tera", "pgta", "karyotype", "nipt", "hla", "billing"}

host     = os.getenv("MYSQL_HOST", "localhost")
port     = int(os.getenv("MYSQL_PORT", "3306"))
user     = os.getenv("MYSQL_USER", "")
password = os.getenv("MYSQL_PASSWORD", "")
database = os.getenv("MYSQL_DATABASE", "")

if not host or not user or not database:
    print("ERROR: MYSQL_HOST, MYSQL_USER, MYSQL_DATABASE not set in .env")
    sys.exit(1)

conn = mysql.connector.connect(
    host=host, port=port, user=user, password=password, database=database
)
cur = conn.cursor()

created = skipped = errors = 0

for u in USERS:
    mobile = (u.get("mobile_number") or "").strip()
    name   = (u.get("name") or "").strip() or None
    role   = (u.get("role") or "user").strip()
    report = u.get("report")

    if not mobile:
        print(f"  SKIP   — missing mobile_number in entry: {u}")
        errors += 1
        continue
    if role not in ("admin", "user"):
        print(f"  ERROR  {mobile} — role must be 'admin' or 'user', got '{role}'")
        errors += 1
        continue
    if role == "user" and report not in VALID_REPORTS:
        print(f"  ERROR  {mobile} — report must be one of {VALID_REPORTS}, got '{report}'")
        errors += 1
        continue

    report = None if role == "admin" else report

    cur.execute("SELECT id, name, role FROM users WHERE mobile_number = %s", (mobile,))
    existing = cur.fetchone()
    if existing:
        print(f"  SKIP   {mobile} — already exists (id={existing[0]}, role={existing[2]})")
        skipped += 1
        continue

    user_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO users (id, mobile_number, name, role, report) VALUES (%s, %s, %s, %s, %s)",
        (user_id, mobile, name, role, report),
    )
    conn.commit()
    print(f"  CREATED {mobile} | name={name} | role={role} | report={report} | id={user_id}")
    created += 1

cur.close()
conn.close()

print(f"\nDone — {created} created, {skipped} skipped, {errors} error(s).")
