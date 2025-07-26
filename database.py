import sqlite3

def init_db():
    conn = sqlite3.connect('shoes.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shoes (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            brand TEXT NOT NULL,
            size REAL NOT NULL,  
            price INTEGER NOT NULL,
            image TEXT
        )
    ''')

    cursor.execute("SELECT COUNT(*) FROM shoes")
    if cursor.fetchone()[0] == 0:
        sample_data = []
        cursor.executemany(
            "INSERT INTO shoes (name, brand, size, price, image) VALUES (?, ?, ?, ?, ?)",
            sample_data
        )

    conn.commit()
    conn.close()
    print("✅ Базу даних успішно ініціалізовано!")
