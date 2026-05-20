import sqlite3
import pandas as pd

# Connect to the database
db_path = 'nutrition.db'
conn = sqlite3.connect(db_path)

print("=" * 60)
print("SQLite Database Interactive Shell")
print("=" * 60)
print(f"\nConnected to: {db_path}\n")

# Show available tables
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [t[0] for t in cursor.fetchall()]

print("Available Tables:")
for i, table in enumerate(tables, 1):
    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    count = cursor.fetchone()[0]
    print(f"  {i}. {table} ({count} rows)")

print("\n" + "=" * 60)
print("Commands:")
print("  - Type 'exit' to quit")
print("  - Type 'tables' to see all tables")
print("  - Type 'analyze' to see a full summary of all tables")
print("  - Type 'schema <table_name>' to see table structure")
print("  - Type 'select * from <table_name>' to query")
print("=" * 60 + "\n")

# Interactive loop
while True:
    try:
        query = input("SQL> ").strip()
        
        if not query:
            continue
        
        if query.lower() == 'exit':
            print("Closing connection...")
            break
        
        if query.lower() == 'tables':
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [t[0] for t in cursor.fetchall()]
            print("Tables:")
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"  - {table} ({count} rows)")
            continue

        if query.lower() == 'analyze':
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            all_tables = [t[0] for t in cursor.fetchall()]
            for table_name in all_tables:
                print(f"\n=== {table_name} ===")
                # Schema
                cursor.execute(f"PRAGMA table_info({table_name})")
                cols = cursor.fetchall()
                print(f"Columns: {', '.join([c[1] for c in cols])}")
                # Row count
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                print(f"Row count: {cursor.fetchone()[0]}")
                # Samples
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 5")
                samples = cursor.fetchall()
                if samples:
                    col_names = [desc[0] for desc in cursor.description]
                    print(pd.DataFrame(samples, columns=col_names).to_string(index=False))
            print()
            continue
        
        if query.lower().startswith('schema '):
            table_name = query.split('schema ')[1].strip()
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            print(f"\nSchema for {table_name}:")
            print(f"{'Column':<20} {'Type':<15} {'NotNull':<10} {'PK':<5}")
            print("-" * 50)
            for col in columns:
                print(f"{col[1]:<20} {col[2]:<15} {str(col[3]):<10} {str(col[5]):<5}")
            print()
            continue
        
        # Execute query
        cursor.execute(query)
        results = cursor.fetchall()
        
        if results:
            # Get column names
            cursor.execute(query)
            col_names = [desc[0] for desc in cursor.description]
            
            # Create DataFrame for nice display
            df = pd.DataFrame(results, columns=col_names)
            print(f"\n{len(results)} rows returned:\n")
            print(df.to_string(index=False))
            print()
        else:
            print("Query executed successfully (no rows returned)\n")
            
    except sqlite3.Error as e:
        print(f"Database Error: {e}\n")
    except Exception as e:
        print(f"Error: {e}\n")

conn.close()
print("Connection closed.")
