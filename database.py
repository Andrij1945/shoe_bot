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
        sample_data = [
            ('Nike Air Max', 'Nike', 42.5, 4500, 'https://i.ibb.co/23ZMzTj/image.jpg'),
            ('Adidas Ultraboost', 'Adidas', 39.5, 3800, 'https://i.ibb.co/abc123/adidas.jpg'),
            ('Puma RS-X', 'Puma', 40.5, 3200, 'https://i.ibb.co/xyz456/puma.jpg'),
            ('New Balance 574', 'New Balance', 41.0, 2900, 'https://i.ibb.co/def789/nb.jpg'),
            ('Reebok Classic', 'Reebok', 43.0, 2700, None)
        ]
        cursor.executemany(
            "INSERT INTO shoes (name, brand, size, price, image) VALUES (?, ?, ?, ?, ?)",
            sample_data
        )

    conn.commit()
    conn.close()
    print("✅ Базу даних успішно ініціалізовано!")