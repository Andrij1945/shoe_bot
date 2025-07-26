import os
import psycopg2 # Імпортуємо бібліотеку для PostgreSQL
from urllib.parse import urlparse # Допомагає розібрати URL бази даних
import logging # Для логування

# Налаштування логування (можна перенести в основний файл, якщо вже є)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def init_db():
    """
    Ініціалізує базу даних PostgreSQL.
    Підключається до БД за допомогою DATABASE_URL зі змінних середовища.
    Створює таблицю 'shoes' та додає тестові дані, якщо таблиця порожня.
    """
    # Отримуємо URL бази даних зі змінних середовища Render
    DATABASE_URL = os.environ.get('DATABASE_URL')
    
    # Перевіряємо, чи встановлена змінна середовища
    if not DATABASE_URL:
        logger.error("❌ DATABASE_URL environment variable is not set. Cannot connect to PostgreSQL.")
        # Важливо: якщо ви хочете, щоб бот не запускався без БД, розкоментуйте наступний рядок:
        raise ValueError("DATABASE_URL environment variable is not set.")
        # return # Або поверніть, якщо ви хочете, щоб бот все одно запускався, але без БД

    conn = None # Змінна для об'єкта з'єднання з базою даних
    try:
        # Розбираємо URL бази даних на складові частини (користувач, пароль, хост, порт, назва БД)
        result = urlparse(DATABASE_URL)
        
        # Встановлюємо з'єднання з PostgreSQL
        conn = psycopg2.connect(
            database=result.path[1:],  # result.path[1:] дає назву БД без першого '/'
            user=result.username,
            password=result.password,
            host=result.hostname,
            port=result.port,
            # sslmode='require' може бути потрібен, якщо ви підключаєтесь ззовні Render
            # Але для внутрішніх сервісів Render зазвичай не потрібен або за замовчуванням
        )
        cursor = conn.cursor() # Створюємо курсор для виконання SQL-запитів

        # Створення таблиці 'shoes', якщо вона ще не існує
        # Зверніть увагу:
        # - SERIAL PRIMARY KEY для автоінкременту в PostgreSQL (замість INTEGER PRIMARY KEY)
        # - REAL для дробових чисел (size)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS shoes (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                brand TEXT NOT NULL,
                size REAL NOT NULL,  
                price INTEGER NOT NULL,
                image TEXT
            )
        ''')
        conn.commit() # Підтверджуємо зміни в базі даних (створення таблиці)

        # Перевіряємо, чи таблиця порожня, і додаємо зразки даних, якщо так
        cursor.execute("SELECT COUNT(*) FROM shoes")
        if cursor.fetchone()[0] == 0:
            sample_data = [
                ('Nike Air Max', 'Nike', 42.5, 4500, 'https://i.ibb.co/23ZMzTj/image.jpg'),
                ('Adidas Ultraboost', 'Adidas', 39.5, 3800, 'https://i.ibb.co/abc123/adidas.jpg'),
                ('Puma RS-X', 'Puma', 40.5, 3200, 'https://i.ibb.co/xyz456/puma.jpg'),
                ('New Balance 574', 'New Balance', 41.0, 2900, 'https://i.ibb.co/def789/nb.jpg'),
                ('Reebok Classic', 'Reebok', 43.0, 2700, None)
            ]
            # У psycopg2 плейсхолдери для значень - це %s, а не ? як в SQLite
            cursor.executemany(
                "INSERT INTO shoes (name, brand, size, price, image) VALUES (%s, %s, %s, %s, %s)",
                sample_data
            )
            conn.commit() # Підтверджуємо вставку зразків даних
            logger.info("Sample data inserted into shoes table.")

        logger.info("✅ Database successfully initialized and connected to PostgreSQL!")

    except Exception as e:
        logger.error(f"❌ Error initializing database: {e}")
        if conn:
            conn.rollback() # Відкочуємо всі зміни, якщо сталася помилка
        # Прокидаємо виняток, щоб основний додаток знав про проблему з БД
        raise e 
    finally:
        if conn:
            conn.close() # Завжди закриваємо з'єднання, незалежно від результату
