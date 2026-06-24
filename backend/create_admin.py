"""
One-time script to insert the first admin user into the users table.
Run from the backend/ directory:

    python create_admin.py

Delete this file after running it.
"""

import os
import uuid
import sys
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

import mysql.connector

MOBILE_NUMBER = "7358752950"

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

cur.execute("SELECT id, mobile_number, role FROM users WHERE mobile_number = %s", (MOBILE_NUMBER,))
existing = cur.fetchone()
if existing:
    print(f"User {MOBILE_NUMBER} already exists — id={existing[0]}, role={existing[2]}")
else:
    user_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO users (id, mobile_number, role, report) VALUES (%s, %s, 'admin', NULL)",
        (user_id, MOBILE_NUMBER),
    )
    conn.commit()
    print(f"Admin user created — mobile={MOBILE_NUMBER}, id={user_id}")

cur.close()
conn.close()
