import sqlite3

# Connect to the database
conn = sqlite3.connect('nutrition.db')
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("Tables in the database:")
for table in tables:
    print(f"- {table[0]}")

# For each table, get schema and row count
for table_name in [t[0] for t in tables]:
    print(f"\n=== {table_name} ===")

    # Get schema
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    print("Columns:")
    for col in columns:
        print(f"  {col[1]} ({col[2]}) {'PRIMARY KEY' if col[5] else ''}")

    # Get row count
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    print(f"Row count: {count}")

    # Show first few rows
    cursor.execute(f"SELECT * FROM {table_name} LIMIT 5")
    rows = cursor.fetchall()
    if rows:
        print("Sample rows:")
        for row in rows:
            print(f"  {row}")

conn.close()