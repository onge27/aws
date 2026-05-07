import sqlite3
conn = sqlite3.connect('examination.db')
cursor = conn.execute("PRAGMA table_info(allowed_students)")
for row in cursor.fetchall():
    print(row)
conn.close()