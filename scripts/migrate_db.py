
import sqlite3
import os

def migrate():
    db_path = "enterprise_bot.db"
    if not os.path.exists(db_path):
        print(f"Database {db_path} not found. Skipping migration (it will be created by app).")
        return

    print(f"Migrating {db_path}...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if columns already exist
    cursor.execute("PRAGMA table_info(messages)")
    columns = [row[1] for row in cursor.fetchall()]

    new_columns = [
        ("node_id", "TEXT"),
        ("parent_id", "TEXT"),
        ("summary", "TEXT"),
        ("similarity_to_parent", "REAL DEFAULT 0.0")
    ]

    for col_name, col_type in new_columns:
        if col_name not in columns:
            print(f"Adding column {col_name} to messages table...")
            cursor.execute(f"ALTER TABLE messages ADD COLUMN {col_name} {col_type}")
    
    # Update existing nodes with a node_id if they don't have one
    cursor.execute("SELECT id FROM messages WHERE node_id IS NULL")
    rows = cursor.fetchall()
    if rows:
        import uuid
        for row in rows:
            cursor.execute("UPDATE messages SET node_id = ? WHERE id = ?", (str(uuid.uuid4()), row[0]))

    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
