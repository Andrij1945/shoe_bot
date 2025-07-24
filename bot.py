import sqlite3
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

# Ініціалізація бази даних
# Важливо: файл database.py повинен бути в тій же директорії, що і цей файл
from database import init_db
# Ініціалізація при запуску
init_db()

# Налаштування
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константи
ITEMS_PER_PAGE = 3
YOUR_ADMIN_ID = 1634618032  # Замініть на свій Telegram ID
TOKEN = "8047320199:AAF2B6pyxk8vWMp0RZxT75Oy43uWki-Ykhg"  # Ваш токен бота

# Глобальні змінні
user_filters = {}
adding_shoe_state = {}  # Для відстеження стану додавання нового товару
user_menu_stack = {}    # Для відстеження історії меню

# Емодзі для інтерфейсу
EMOJI = {
    "shoes": "👟",
    "filter": "🔍",
    "size": "📏",
    "brand": "🏷️",
    "admin": "🛠️",
    "add": "➕",
    "remove": "🗑️",
    "list": "📋",
    "back": "🔙",
    "apply": "✅",
    "reset": "❌",
    "cart": "🛒",
    "home": "🏠",
    "next": "➡️",
    "prev": "⬅️",
    "money": "💵",
    "info": "ℹ️",
    "success": "✅",
    "error": "❌"
}

# Функція для форматування розміру
def format_size(size):
    """Форматує розмір для відображення, видаляючи зайві нулі"""
    if isinstance(size, (int, float)):
        if size.is_integer():
            return str(int(size))
    return str(size).rstrip('0').rstrip('.') if '.' in str(size) else str(size)

# Відправка деталей товару
async def send_shoe_details(context, chat_id, item):
    shoe_id, name, brand, size, price, image_url = item
    display_size = format_size(size)
    caption = (
        f"{EMOJI['shoes']} <b>{name}</b>\n"
        f"{EMOJI['brand']} <b>Бренд:</b> {brand}\n"
        f"{EMOJI['size']} <b>Розмір:</b> {display_size}\n"
        f"{EMOJI['money']} <b>Ціна:</b> {price} грн\n"
        f"🆔 ID: {shoe_id}"
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
        logger.error(f"Помилка відправки фото: {e}")
        # Якщо фото не відправилось, відправляємо без фото
        await context.bot.send_message(
            chat_id=chat_id,
            text=caption + f"\n\n{EMOJI['error']} Не вдалося завантажити зображення.",
            parse_mode="HTML"
        )
        return None # Повертаємо None, якщо фото не відправилось

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
        user_menu_stack[user_id].pop()  # Видаляємо поточне меню зі стеку
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
        elif previous_menu == "remove_shoes": # Якщо повертаємось з видалення
            await remove_shoe_menu(update, context)
        elif previous_menu == "admin_list_shoes": # Якщо повертаємось зі списку адміна
            await list_shoes(update, context)
    else:
        # Якщо стек порожній або містить лише одне меню, повертаємося до головного
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
        # Форматуємо розміри для відображення
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

    conn = sqlite3.connect('shoes.db')
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT brand FROM shoes")
    brands = [row[0] for row in cursor.fetchall()]
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

    conn = sqlite3.connect('shoes.db')
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT size FROM shoes ORDER BY size")
    sizes = [row[0] for row in cursor.fetchall()]
    conn.close()

    keyboard = []
    for size_val in sizes:
        # Порівнюємо float значення
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
        await show_brand_menu(update, context)  # Оновлюємо меню брендів

    elif data.startswith("toggle_size_"):
        size_str = data.replace("toggle_size_", "")
        try:
            size_float = float(size_str)
            if size_float in user_filters[user_id]['sizes']:
                user_filters[user_id]['sizes'].remove(size_float)
            else:
                user_filters[user_id]['sizes'].append(size_float)
            await show_size_menu(update, context)  # Оновлюємо меню розмірів
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
    # Визначаємо, чи це виклик з callback_query чи з message
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
        return

    save_menu_state(user_id, "admin")

    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['add']} Додати товар", callback_data="add_shoe_prompt")],
        [InlineKeyboardButton(f"{EMOJI['remove']} Видалити товар", callback_data="remove_shoe_menu")],
        [InlineKeyboardButton(f"{EMOJI['list']} Список товарів", callback_data="admin_list_shoes")],
        [InlineKeyboardButton(f"{EMOJI['back']} Головне меню", callback_data="back_menu")]
    ]

    # Редагуємо або надсилаємо нове повідомлення залежно від типу update
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
        await update.callback_query.answer("У вас немає доступу до цієї функції.", show_alert=True)
        return

    user_id = update.effective_user.id
    adding_shoe_state[user_id] = {'step': 1, 'data': {}}
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Будь ласка, введіть <b>назву</b> товару:",
        parse_mode="HTML"
    )
    if update.callback_query:
        try:
            # Видалити попереднє повідомлення адмін-меню, якщо воно було викликано з кнопки
            await update.callback_query.message.delete()
        except Exception as e:
            logger.warning(f"Не вдалося видалити повідомлення після add_shoe_prompt: {e}")


#### Обробник повідомлень для додавання товару
async def add_shoe_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != YOUR_ADMIN_ID or user_id not in adding_shoe_state:
        # Ігноруємо повідомлення, якщо не в процесі додавання товару або не адмін
        return

    state = adding_shoe_state[user_id]
    text = update.message.text

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
            # Обробка дробових розмірів, заміна коми на крапку
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

        conn = sqlite3.connect('shoes.db')
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO shoes (name, brand, size, price, image) VALUES (?, ?, ?, ?, ?)",
                (state['data']['name'], state['data']['brand'], state['data']['size'],
                 state['data']['price'], state['data']['image'])
            )
            conn.commit()
            await update.message.reply_text(f"{EMOJI['success']} Товар успішно додано!")
            logger.info(f"Товар додано: {state['data']}")
        except Exception as e:
            conn.rollback()
            await update.message.reply_text(f"{EMOJI['error']} Помилка при додаванні товару: {e}")
            logger.error(f"Помилка при додаванні товару: {e}")
        finally:
            conn.close()
            del adding_shoe_state[user_id]  # Завершуємо стан додавання
        # Після додавання товару, повертаємося до адмін-меню, використовуючи update.message
        await show_admin_menu(update, context)

#### Меню видалення товарів (список з кнопками видалення)
async def remove_shoe_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_ADMIN_ID:
        await update.callback_query.answer("У вас немає доступу до цієї функції.", show_alert=True)
        return

    save_menu_state(update.effective_user.id, "remove_shoes")

    conn = sqlite3.connect('shoes.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, brand, size, price FROM shoes ORDER BY id DESC")
    shoes = cursor.fetchall()
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

    conn = sqlite3.connect('shoes.db')
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM shoes WHERE id = ?", (shoe_id,))
        conn.commit()
        await query.answer(f"{EMOJI['success']} Товар ID:{shoe_id} успішно видалено!", show_alert=True)
        logger.info(f"Товар ID:{shoe_id} видалено.")
    except Exception as e:
        conn.rollback()
        await query.answer(f"{EMOJI['error']} Помилка при видаленні товару: {e}", show_alert=True)
        logger.error(f"Помилка при видаленні товару ID:{shoe_id}: {e}")
    finally:
        conn.close()

    await remove_shoe_menu(update, context)  # Оновлюємо список після видалення

#### Список товарів (для адміна, без пагінації, простіший список)
async def list_shoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_ADMIN_ID:
        await update.callback_query.answer("У вас немає доступу до цієї функції.", show_alert=True)
        return

    save_menu_state(update.effective_user.id, "admin_list_shoes")

    conn = sqlite3.connect('shoes.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, brand, size, price FROM shoes")
    shoes = cursor.fetchall()
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

    conn = sqlite3.connect('shoes.db')
    cursor = conn.cursor()

    query = "SELECT * FROM shoes WHERE 1=1"
    params = []

    if 'brands' in filters_data and filters_data['brands']:
        query += f" AND brand IN ({','.join(['?']*len(filters_data['brands']))})"
        params.extend(filters_data['brands'])

    if 'sizes' in filters_data and filters_data['sizes']:
        # Розміри вже зберігаються як float, тому просто використовуємо їх
        size_params = filters_data['sizes']
        query += f" AND size IN ({','.join(['?']*len(size_params))})"
        params.extend(size_params)

    cursor.execute(query, params)
    all_items = cursor.fetchall()
    conn.close()

    total_items = len(all_items)
    total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    current_page = max(0, min(page, total_pages - 1)) if total_pages > 0 else 0

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
    elif not all_items[start_idx:end_idx]:
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
        text=f"📄 <b>Сторінка {current_page+1}/{total_pages if total_pages > 0 else 1} | Знайдено товарів: {total_items}</b>",
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
    await query.answer()  # Завжди відповідаємо на callback_query, щоб прибрати "годинник"
    data = query.data

    if data == "back_menu":
        await back_to_previous_menu(update, context)
    elif data == "show_all":
        # Перед показом всіх товарів, скидаємо фільтри, щоб показувати ДІЙСНО ВСІ
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
    # init_db() # Цей виклик перенесено на початок файлу після імпорту
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    # Обробник текстових повідомлень, але тільки якщо користувач знаходиться в стані додавання товару
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(YOUR_ADMIN_ID), add_shoe_message_handler))
    application.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Бот запускається...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Бот запущений")

if __name__ == "__main__":
    main()