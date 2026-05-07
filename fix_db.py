import sqlite3
conn = sqlite3.connect('examination.db')

conn.execute("ALTER TABLE allowed_students RENAME TO allowed_students_old")

conn.execute("""
    CREATE TABLE allowed_students (
        id INTEGER PRIMARY KEY,
        student_name TEXT NOT NULL,
        subject_id INTEGER NOT NULL
    )
""")

conn.execute("""
    INSERT INTO allowed_students (id, student_name, subject_id)
    SELECT id, student_name, subject_id FROM allowed_students_old
""")

conn.execute("DROP TABLE allowed_students_old")

conn.commit()
conn.close()
print("Done! student_number column removed.")