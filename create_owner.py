import sqlite3
from contextlib import closing
from getpass import getpass

from werkzeug.security import generate_password_hash

DATABASE = "quotetrack.db"


def main():
    username = input("Owner username: ").strip()
    password = getpass("Owner password (hidden): ")
    confirm = getpass("Confirm password: ")

    if not username:
        print("Username cannot be empty.")
        return
    if len(password) < 8:
        print("Password must be at least 8 characters.")
        return
    if password != confirm:
        print("Passwords do not match.")
        return

    with closing(sqlite3.connect(DATABASE)) as conn, conn:
        # Creates the table on older databases without wiping existing requests
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS owners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            INSERT INTO owners (username, password_hash) VALUES (?, ?)
            ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash
            """,
            (username, generate_password_hash(password)),
        )

    print(f"Owner account '{username}' is ready.")


if __name__ == "__main__":
    main()