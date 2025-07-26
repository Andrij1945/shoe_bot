import os # Додано для роботи зі змінними середовища
import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

# Імпортуємо psycopg2 для роботи з PostgreSQL
import psycopg2
from urllib.parse import urlparse # Допомагає розібрати URL бази даних

# Ініціалізація бази даних
# Важливо: файл database.py повинен бути в тій же директорії, що і цей файл
from database import init_db

# --- Налаштування ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константи
ITEMS_PER_PAGE = 3

# Отримуємо ID адміністратора та токен бота зі змінних середовища для безпеки
# Це необхідно налаштувати на Render у розділі "Environment" для вашого сервісу
YOUR_ADMIN_ID = int(os.environ.get('YOUR_ADMIN_ID', '0')) # Поставте 0 або ваш ID за замовчуванням для локальної розробки
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

# Перевірка наявності токену та ID
if not TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN environment variable is not set. Bot cannot start.")
    exit(1) # Завершуємо роботу, якщо токену немає
if YOUR_ADMIN_ID == 0:
    logger.warning("⚠️ YOUR_ADMIN_ID environment variable is not set or is 0. Admin features might not work.")


# --- Глобальні змінні ---
user_filters = {}
adding_shoe_state = {}  # Для відстеження стану додавання нового товару
user_menu_stack = {}    # Для відстеження історії меню

# Емодзі для інтерфейсу
EMOJI = {
    "shoes": "👟", "filter": "🔍", "size": "📏", "brand": "🏷️",
    "admin": "🛠️", "add": "➕", "remove": "🗑️", "list": "📋",
    "back": "🔙", "apply": "✅", "reset": "❌", "cart": "🛒",
    "home": "🏠", "next": "➡️", "prev": "⬅️", "money": "💵",
    "info": "ℹ️", "success": "✅", "error": "❌"
}

# --- Допоміжна функція для отримання з'єднання з БД ---
def get_db_connection():
    """Повертає з'єднання з базою даних PostgreSQL."""
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if not DATABASE_URL:
        logger.error("DATABASE_URL environment variable is not set.")
        raise ValueError("DATABASE_URL environment variable is not set. Cannot establish database connection.")
    
    result = urlparse(DATABASE_URL)
    return psycopg2.connect(
        database=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port
    )

# --- Функції бота ---

# Функція для форматування розміру
def format_size(size):
    """Форматує розмір для відображення, видаляючи зайві нулі"""
    if isinstance(size, (int, float)):
        # Якщо це число, перевіряємо, чи є воно цілим
        if size == int(size): # Використовуємо пряме порівняння з int(size)
            return str(int(size))
    return str(size).rstrip('0').rstrip('.') if '.' in str(size) else str(size)


# Відправка деталей товару
async def send_shoe_details(context, chat_id, item):
    shoe_id, name, brand, size, price, image_url = item
    display_size = format_size(size)
    telegram_contact_url = "tg://resolve?domain=takar28"
    
    caption = (
        f"{EMOJI['shoes']} <b>{name}</b>\n"
        f"{EMOJI['brand']} <b>Бренд:</b> {brand}\n"
        f"{EMOJI['size']} <b>Розмір:</b> {display_size}\n"
        f"{EMOJI['money']} <b>Ціна:</b> {price} грн\n"
        f"🆔 ID: {shoe_id}\n\n"
        f"Для замовлення писати: <a href='{telegram_contact_url}'>@takar28</a>"
    )

    try:
        if image_url and image_url.startswith('http'):
            return await context.bot.send_photo(
                chat_id=chat_id,
                photo=image_url,
                caption=caption,
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Помилка відправки фото {image_url}: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=caption + f"\n\n{EMOJI['error']} Не вдалося завантажити зображення.",
            parse_mode="HTML"
        )
        return None

    return await context.bot.send_message(
        chat_id=chat_id,
        text=caption,
        parse_mode="HTML"
    )

# Зберігаємо поточне меню для користувача
def save_menu_state(user_id, menu_name):
    if user_id not in user_menu_stack:
        user_menu_stack[user_id] = []
    if not user_menu_stack[user_id] or user_menu_stack[user_id][-1] != menu_name:
        user_menu_stack[user_id].append(menu_name)

# Повертаємося до попереднього меню
async def back_to_previous_menu(update, context):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id in user_menu_stack and len(user_menu_stack[user_id]) > 1:
        user_menu_stack[user_id].pop()
        previous_menu = user_menu_stack[user_id][-1]

        # Переходимо до попереднього меню
        if previous_menu == "main":
            await show_main_menu(update, context)
        elif previous_menu == "filters":
            await show_filter_menu(update, context)
        elif previous_menu == "admin":
            await show_admin_menu(update, context)
        elif previous_menu == "brands":
            await show_brand_menu(update, context)
        elif previous_menu == "sizes":
            await show_size_menu(update, context)
        elif previous_menu == "remove_shoes":
            await remove_shoe_menu(update, context)
        elif previous_menu == "admin_list_shoes":
            await list_shoes(update, context)
    else:
        await show_main_menu(update, context)

### Меню користувача

#### Головне меню
async def show_main_menu(update, context):
    save_menu_state(update.effective_user.id, "main")

    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['shoes']} Усі товари", callback_data="show_all")],
        [InlineKeyboardButton(f"{EMOJI['filter']} Фільтр товарів", callback_data="filter_options")],
    ]

    if update.effective_user.id == YOUR_ADMIN_ID:
        keyboard.append([InlineKeyboardButton(f"{EMOJI['admin']} Адмін-панель", callback_data="admin_panel")])

    # Визначаємо, яке повідомлення редагувати/відповідати
    if update.callback_query:
        await update.callback_query.message.edit_text(
            "👟 <b>Магазин взуття DoomerSneakers</b>\nОберіть опцію:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
    elif update.message:
        await update.message.reply_text(
            "👟 <b>Магазин взуття DoomerSneakers</b>\nОберіть опцію:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )

### Фільтри

#### Меню фільтрів
async def show_filter_menu(update, context):
    save_menu_state(update.effective_user.id, "filters")
    user_id = update.effective_user.id

    if user_id not in user_filters:
        user_filters[user_id] = {'brands': [], 'sizes': []}

    filters_data = user_filters[user_id]
    filter_info = ""
    if filters_data['brands']:
        filter_info += f"{EMOJI['brand']} <b>Бренди:</b> {', '.join(filters_data['brands'])}\n"
    if filters_data['sizes']:
        formatted_sizes = [format_size(s) for s in filters_data['sizes']]
        filter_info += f"{EMOJI['size']} <b>Розміри:</b> {', '.join(formatted_sizes)}\n"

    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['brand']} Фільтр по бренду", callback_data="brand_filter")],
        [InlineKeyboardButton(f"{EMOJI['size']} Фільтр по розміру", callback_data="size_filter")],
        [InlineKeyboardButton(f"{EMOJI['apply']} Застосувати фільтри", callback_data="apply_filters")],
        [InlineKeyboardButton(f"{EMOJI['reset']} Скинути фільтри", callback_data="reset_filters")],
        [InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="back_menu")]
    ]

    await update.callback_query.message.edit_text(
        f"⚙️ <b>Фільтрація товарів</b>\n\n"
        f"{'🔍 <b>Поточні фільтри:</b>\n' + filter_info if filter_info else ''}"
        f"Оберіть параметри фільтрації:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

#### Меню брендів
async def show_brand_menu(update, context):
    save_menu_state(update.effective_user.id, "brands")
    user_id = update.effective_user.id

    conn = None
    try:
        conn = get_db_connection() # Отримуємо з'єднання з PostgreSQL
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT brand FROM shoes ORDER BY brand") # Додав ORDER BY
        brands = [row[0] for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Помилка при отриманні брендів: {e}")
        await update.callback_query.message.reply_text(f"{EMOJI['error']} Помилка завантаження брендів.")
        brands = [] # Забезпечуємо порожній список, щоб не було помилок
    finally:
        if conn:
            conn.close()

    keyboard = []
    for brand in brands:
        is_selected = brand in user_filters.get(user_id, {}).get('brands', [])
        text = f"{'✅' if is_selected else '◻️'} {brand}"
        keyboard.append([InlineKeyboardButton(text, callback_data=f"toggle_brand_{brand}")])

    keyboard.append([InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="back_menu")])

    await update.callback_query.message.edit_text(
        f"{EMOJI['brand']} <b>Оберіть бренди:</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

#### Меню розмірів
async def show_size_menu(update, context):
    save_menu_state(update.effective_user.id, "sizes")
    user_id = update.effective_user.id

    conn = None
    try:
        conn = get_db_connection() # Отримуємо з'єднання з PostgreSQL
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT size FROM shoes ORDER BY size")
        sizes = [row[0] for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Помилка при отриманні розмірів: {e}")
        await update.callback_query.message.reply_text(f"{EMOJI['error']} Помилка завантаження розмірів.")
        sizes = []
    finally:
        if conn:
            conn.close()

    keyboard = []
    for size_val in sizes:
        # Для порівняння розмірів у фільтрі використовуємо float
        is_selected = float(size_val) in user_filters.get(user_id, {}).get('sizes', [])
        display_size = format_size(size_val)
        text = f"{'✅' if is_selected else '◻️'} Розмір {display_size}"
        keyboard.append([InlineKeyboardButton(text, callback_data=f"toggle_size_{size_val}")])

    keyboard.append([InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="back_menu")])

    await update.callback_query.message.edit_text(
        f"{EMOJI['size']} <b>Оберіть розміри:</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

#### Увімкнення/вимкнення фільтра
async def toggle_filter(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    if user_id not in user_filters:
        user_filters[user_id] = {'brands': [], 'sizes': []}

    if data.startswith("toggle_brand_"):
        brand = data.replace("toggle_brand_", "")
        if brand in user_filters[user_id]['brands']:
            user_filters[user_id]['brands'].remove(brand)
        else:
            user_filters[user_id]['brands'].append(brand)
        await show_brand_menu(update, context)

    elif data.startswith("toggle_size_"):
        size_str = data.replace("toggle_size_", "")
        try:
            size_float = float(size_str)
            if size_float in user_filters[user_id]['sizes']:
                user_filters[user_id]['sizes'].remove(size_float)
            else:
                user_filters[user_id]['sizes'].append(size_float)
            await show_size_menu(update, context)
        except ValueError:
            logger.error(f"Невірний формат розміру в callback_data: {size_str}")
            await query.answer(f"{EMOJI['error']} Помилка формату розміру.", show_alert=True)

#### Скидання фільтрів
async def reset_filters(update, context):
    user_id = update.effective_user.id
    user_filters[user_id] = {'brands': [], 'sizes': []}
    await show_filter_menu(update, context)
    await update.callback_query.answer("Фільтри скинуто!", show_alert=True)

### Адмін-панель

#### Адмін-меню
async def show_admin_menu(update, context):
    if update.callback_query:
        user_id = update.callback_query.from_user.id
        message_to_edit = update.callback_query.message
    elif update.message:
        user_id = update.message.from_user.id
        message_to_edit = update.message
    else:
        logger.error("show_admin_menu викликано без update.callback_query або update.message")
        return

    if user_id != YOUR_ADMIN_ID:
        if update.callback_query:
            await update.callback_query.answer("У вас немає доступу до цієї функції.", show_alert=True)
        else: # Якщо це текстове повідомлення
            await update.message.reply_text("У вас немає доступу до цієї функції.")
        return

    save_menu_state(user_id, "admin")

    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['add']} Додати товар", callback_data="add_shoe_prompt")],
        [InlineKeyboardButton(f"{EMOJI['remove']} Видалити товар", callback_data="remove_shoe_menu")],
        [InlineKeyboardButton(f"{EMOJI['list']} Список товарів", callback_data="admin_list_shoes")],
        [InlineKeyboardButton(f"{EMOJI['back']} Головне меню", callback_data="back_menu")]
    ]

    if update.callback_query:
        await message_to_edit.edit_text(
            f"{EMOJI['admin']} <b>Адмін-панель</b>\nОберіть дію:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
    elif update.message:
        await message_to_edit.reply_text(
            f"{EMOJI['admin']} <b>Адмін-панель</b>\nОберіть дію:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )

#### Запит на додавання товару (початок процесу)
async def add_shoe_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_ADMIN_ID:
        if update.callback_query:
            await update.callback_query.answer("У вас немає доступу до цієї функції.", show_alert=True)
        return

    user_id = update.effective_user.id
    adding_shoe_state[user_id] = {'step': 1, 'data': {}}
    
    # Видаляємо попереднє повідомлення адмін-меню, якщо воно було викликано з кнопки
    if update.callback_query:
        try:
            await update.callback_query.message.delete()
        except Exception as e:
            logger.warning(f"Не вдалося видалити повідомлення після add_shoe_prompt: {e}")

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Будь ласка, введіть <b>назву</b> товару:",
        parse_mode="HTML"
    )

#### Обробник повідомлень для додавання товару
async def add_shoe_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Перевірка, чи користувач є адміном і чи він у процесі додавання товару
    if user_id != YOUR_ADMIN_ID or user_id not in adding_shoe_state:
        # Ігноруємо повідомлення або відповідаємо, якщо це не адмін
        if user_id != YOUR_ADMIN_ID:
            await update.message.reply_text("У вас немає доступу до цієї функції. Будь ласка, використовуйте кнопки меню.")
        return

    state = adding_shoe_state[user_id]
    text = update.message.text

    conn = None # Ініціалізуємо conn тут
    try:
        if state['step'] == 1:
            state['data']['name'] = text
            state['step'] = 2
            await update.message.reply_text("Тепер введіть <b>бренд</b> товару:", parse_mode="HTML")
        elif state['step'] == 2:
            state['data']['brand'] = text
            state['step'] = 3
            await update.message.reply_text("Введіть <b>розмір</b> товару (наприклад 42.5 або 43):", parse_mode="HTML")
        elif state['step'] == 3:
            try:
                text = text.replace(',', '.').strip()
                size = float(text)
                if size <= 0:
                    raise ValueError("Розмір повинен бути додатнім числом.")
                state['data']['size'] = size
                state['step'] = 4
                await update.message.reply_text("Введіть <b>ціну</b> товару (ціле число):", parse_mode="HTML")
            except ValueError as e:
                await update.message.reply_text(f"{EMOJI['error']} Некоректний розмір. Будь ласка, введіть число (наприклад 42.5): {str(e)}")
        elif state['step'] == 4:
            try:
                price = int(text)
                if price <= 0:
                    raise ValueError("Ціна повинна бути додатнім числом.")
                state['data']['price'] = price
                state['step'] = 5
                await update.message.reply_text("Надішліть <b>URL зображення</b> товару (або напишіть 'ні', якщо немає):", parse_mode="HTML")
            except ValueError as e:
                await update.message.reply_text(f"{EMOJI['error']} Некоректна ціна. Будь ласка, введіть ціле число: {str(e)}")
        elif state['step'] == 5:
            image_url = text if text.lower() != 'ні' else None
            state['data']['image'] = image_url

            conn = get_db_connection() # Отримуємо з'єднання з PostgreSQL
            cursor = conn.cursor()
            
            cursor.execute(
                # Змінено ? на %s
                "INSERT INTO shoes (name, brand, size, price, image) VALUES (%s, %s, %s, %s, %s)",
                (state['data']['name'], state['data']['brand'], state['data']['size'],
                 state['data']['price'], state['data']['image'])
            )
            conn.commit()
            await update.message.reply_text(f"{EMOJI['success']} Товар успішно додано!")
            logger.info(f"Товар додано: {state['data']}")
            del adding_shoe_state[user_id]  # Завершуємо стан додавання
            
            # Після додавання товару, повертаємося до адмін-меню
            await show_admin_menu(update, context) # Це буде викликано через update.message

    except Exception as e:
        if conn: conn.rollback() # Відкат у випадку помилки
        await update.message.reply_text(f"{EMOJI['error']} Виникла внутрішня помилка при додаванні товару: {e}")
        logger.error(f"Помилка при додаванні товару: {e}")
    finally:
        if conn: conn.close()


#### Меню видалення товарів (список з кнопками видалення)
async def remove_shoe_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_ADMIN_ID:
        await update.callback_query.answer("У вас немає доступу до цієї функції.", show_alert=True)
        return

    save_menu_state(update.effective_user.id, "remove_shoes")

    conn = None
    try:
        conn = get_db_connection() # Отримуємо з'єднання з PostgreSQL
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, brand, size, price FROM shoes ORDER BY id DESC")
        shoes = cursor.fetchall()
    except Exception as e:
        logger.error(f"Помилка при отриманні списку товарів для видалення: {e}")
        await update.callback_query.message.reply_text(f"{EMOJI['error']} Помилка завантаження товарів для видалення.")
        shoes = []
    finally:
        if conn:
            conn.close()

    keyboard = []
    if not shoes:
        message = f"{EMOJI['info']} Наразі немає товарів для видалення."
    else:
        message = f"{EMOJI['remove']} <b>Оберіть товар для видалення:</b>"
        for shoe_id, name, brand, size, price in shoes:
            display_size = format_size(size)
            btn_text = f"🗑️ {name} ({brand}, {display_size}, {price} грн) - ID: {shoe_id}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"remove_{shoe_id}")])

    keyboard.append([InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="back_menu")])

    await update.callback_query.message.edit_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

#### Видалення товару
async def remove_shoe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_ADMIN_ID:
        await update.callback_query.answer("У вас немає доступу до цієї функції.", show_alert=True)
        return

    query = update.callback_query
    shoe_id = int(query.data.replace("remove_", ""))

    conn = None
    try:
        conn = get_db_connection() # Отримуємо з'єднання з PostgreSQL
        cursor = conn.cursor()
        cursor.execute("DELETE FROM shoes WHERE id = %s", (shoe_id,)) # Змінено ? на %s
        conn.commit()
        await query.answer(f"{EMOJI['success']} Товар ID:{shoe_id} успішно видалено!", show_alert=True)
        logger.info(f"Товар ID:{shoe_id} видалено.")
    except Exception as e:
        if conn: conn.rollback()
        await query.answer(f"{EMOJI['error']} Помилка при видаленні товару: {e}", show_alert=True)
        logger.error(f"Помилка при видаленні товару ID:{shoe_id}: {e}")
    finally:
        if conn:
            conn.close()

    await remove_shoe_menu(update, context) # Оновлюємо список після видалення

#### Список товарів (для адміна, без пагінації, простіший список)
async def list_shoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_ADMIN_ID:
        await update.callback_query.answer("У вас немає доступу до цієї функції.", show_alert=True)
        return

    save_menu_state(update.effective_user.id, "admin_list_shoes")

    conn = None
    try:
        conn = get_db_connection() # Отримуємо з'єднання з PostgreSQL
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, brand, size, price FROM shoes ORDER BY id") # Додав ORDER BY
        shoes = cursor.fetchall()
    except Exception as e:
        logger.error(f"Помилка при отриманні списку товарів: {e}")
        await update.callback_query.message.reply_text(f"{EMOJI['error']} Помилка завантаження списку товарів.")
        shoes = []
    finally:
        if conn:
            conn.close()

    message = f"{EMOJI['list']} <b>Список усіх товарів:</b>\n\n"
    if not shoes:
        message += "Наразі немає доданих товарів."
    else:
        for shoe_id, name, brand, size, price in shoes:
            display_size = format_size(size)
            message += f"🆔 {shoe_id}: {name} ({brand}, {display_size} розмір, {price} грн)\n"

    keyboard = [[InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="back_menu")]]

    await update.callback_query.message.edit_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

### Пагінація та відображення товарів

async def show_shoes_page(update, context, page=0):
    user_id = update.effective_user.id
    filters_data = user_filters.get(user_id, {})

    conn = None
    all_items = []
    try:
        conn = get_db_connection() # Отримуємо з'єднання з PostgreSQL
        cursor = conn.cursor()

        query = "SELECT id, name, brand, size, price, image FROM shoes WHERE 1=1"
        params = []

        # Фільтр по брендам
        if 'brands' in filters_data and filters_data['brands']:
            # Використовуємо IN з %s для кожного елемента
            query += f" AND brand IN ({','.join(['%s']*len(filters_data['brands']))})"
            params.extend(filters_data['brands'])

        # Фільтр по розмірам
        if 'sizes' in filters_data and filters_data['sizes']:
            # Використовуємо IN з %s для кожного елемента
            query += f" AND size IN ({','.join(['%s']*len(filters_data['sizes']))})"
            params.extend(filters_data['sizes'])

        # Додаємо сортування, якщо потрібно, наприклад, за ID або назвою
        query += " ORDER BY id" 

        cursor.execute(query, params)
        all_items = cursor.fetchall()
    except Exception as e:
        logger.error(f"Помилка при отриманні товарів для сторінки: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"{EMOJI['error']} Виникла помилка при завантаженні товарів. Будь ласка, спробуйте пізніше.",
            parse_mode="HTML"
        )
        all_items = [] # Забезпечуємо порожній список
    finally:
        if conn:
            conn.close()

    total_items = len(all_items)
    total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE if total_items > 0 else 1
    current_page = max(0, min(page, total_pages - 1))

    start_idx = current_page * ITEMS_PER_PAGE
    end_idx = min(start_idx + ITEMS_PER_PAGE, total_items)

    # Видаляємо попереднє повідомлення меню
    if update.callback_query:
        try:
            await update.callback_query.message.delete()
        except Exception as e:
            logger.warning(f"Не вдалося видалити повідомлення (можливо, вже видалено або не існує): {e}")

    # Відправляємо товари
    if not all_items:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🙁 <b>На жаль, товарів за вашим запитом не знайдено.</b>",
            parse_mode="HTML"
        )
    elif not all_items[start_idx:end_idx]: # Додаткова перевірка, якщо сторінка виходить за межі
         await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🙁 <b>На цій сторінці немає товарів.</b>",
            parse_mode="HTML"
        )
    else:
        for item in all_items[start_idx:end_idx]:
            await send_shoe_details(context, update.effective_chat.id, item)

    # Кнопки пагінації
    pagination_buttons = []
    if current_page > 0:
        pagination_buttons.append(InlineKeyboardButton(f"{EMOJI['prev']} Попередні", callback_data=f"page_{current_page-1}"))
    if end_idx < total_items:
        pagination_buttons.append(InlineKeyboardButton(f"Наступні {EMOJI['next']}", callback_data=f"page_{current_page+1}"))

    menu_buttons = [
        InlineKeyboardButton(f"{EMOJI['back']} Головне меню", callback_data="back_menu"),
        InlineKeyboardButton(f"{EMOJI['filter']} Змінити фільтри", callback_data="filter_options")
    ]

    keyboard = []
    if pagination_buttons:
        keyboard.append(pagination_buttons)
    keyboard.append(menu_buttons)

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"📄 <b>Сторінка {current_page+1}/{total_pages} | Знайдено товарів: {total_items}</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

### Обробники Telegram API

#### Обробка команди /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_main_menu(update, context)

#### Обробка кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back_menu":
        await back_to_previous_menu(update, context)
    elif data == "show_all":
        user_id = update.effective_user.id
        user_filters[user_id] = {'brands': [], 'sizes': []}
        await show_shoes_page(update, context, page=0)
    elif data == "filter_options":
        await show_filter_menu(update, context)
    elif data == "brand_filter":
        await show_brand_menu(update, context)
    elif data == "size_filter":
        await show_size_menu(update, context)
    elif data.startswith("toggle_"):
        await toggle_filter(update, context)
    elif data == "apply_filters":
        await show_shoes_page(update, context, page=0)
    elif data == "reset_filters":
        await reset_filters(update, context)
    elif data == "admin_panel":
        await show_admin_menu(update, context)
    elif data == "add_shoe_prompt":
        await add_shoe_prompt(update, context)
    elif data == "remove_shoe_menu":
        await remove_shoe_menu(update, context)
    elif data.startswith("remove_"):
        await remove_shoe(update, context)
    elif data == "admin_list_shoes":
        await list_shoes(update, context)
    elif data.startswith("page_"):
        page = int(data.split("_")[1])
        await show_shoes_page(update, context, page)

# Основна функція
def main():
    # Викликаємо ініціалізацію БД тут, після того, як всі імпорти та змінні середовища готові
    # або переконайтеся, що init_db() виконується першим
    try:
        init_db()
    except ValueError as e:
        logger.critical(f"Fatal error during database initialization: {e}")
        # Якщо база даних не може бути ініціалізована, бот не може працювати.
        # Тож ми виходимо.
        exit(1)

    # Перевіряємо, чи є токен після ініціалізації БД
    if not TOKEN:
        logger.critical("❌ Bot token is not available. Exiting.")
        exit(1)

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    # Обробник текстових повідомлень, але тільки якщо користувач знаходиться в стані додавання товару
    # та є адміном. Переконайтесь, що `filters.User(YOUR_ADMIN_ID)` спрацює коректно.
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(user_id=YOUR_ADMIN_ID), add_shoe_message_handler))
    application.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Бот запускається...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Бот запущений")

if __name__ == "__main__":
    main()
