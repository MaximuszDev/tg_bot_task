import sqlite3
import time
import telebot
import configure
from telebot import types
import os
import logging
import random

user_data = {}

# Путь к файлу базы данных SQLite
db_file = 'base.db'
survey_started = False

survey_completed = False
previous_question_index = -1  # Объявляем previous_question_index как глобальную переменную

if not os.path.exists(db_file):
    conn = sqlite3.connect(db_file)
    conn.close()

bot = telebot.TeleBot(configure.TOKEN)

send_chat_id = "#"
questions = [
    "1. Количество креативов:",
    "2. Оффер:",
    "3. Тип креативов:",
    "4. Длина видео:",
    "5. Цветовая гамма:",
    "6. Общее описание объектов по крео:",
    "7. Звуковое сопровождение:",
    "8. Заголовок:",
    "9. Язык:",
    "10. Дополнительно:",
    "11. Примеры:(Если отправляете пример обязательно отправляйте ДОКУМЕНТОМ)"
]


user_answers = {}
user_media = {}
tz_info = {}

# Константы для ролей
ADMIN_ROLE = 'Администратор'
DESIGNER_ROLE = 'Дизайнер'
BUYER_ROLE = 'Байер'

survey_in_progress = False

upload_path = "uploads/"
os.makedirs(upload_path, exist_ok=True)

def create_tables():
    conn = sqlite3.connect('base.db')
    cursor = conn.cursor()

    # Создание таблицы user_roles
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_roles (
            user_id INTEGER PRIMARY KEY,
            role TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tz_info (
            tz_id INTEGER PRIMARY KEY,
            user_id INTEGER,
            chat_id INTEGER,
            
            status TEXT,
            created_at TEXT,
            username TEXT,  -- Добавьте столбец для имени пользователя
            FOREIGN KEY (user_id) REFERENCES user_roles (user_id)
        )
    ''')

    # Создание таблицы tz_answers
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tz_answers (
            tz_answer_id INTEGER PRIMARY KEY,
            tz_id INTEGER,
            question_index INTEGER,
            answer TEXT,
            media_type TEXT,
            media_file_id TEXT,
            FOREIGN KEY (tz_id) REFERENCES tz_info (tz_id)
        )
    ''')
    cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks(
                task_id INTEGER PRIMARY KEY,
                status TEXT,
                designer_id INTEGER,
                buyer_name TEXT
            )
        ''')
    conn.commit()
    conn.close()


@bot.message_handler(commands=['start'])
def handle_start(message):
    create_tables()
    chat_id = message.chat.id
    # Создайте словарь ответов для текущего пользователя
    user_answers[chat_id] = {}
    user_question_index[chat_id] = 0  # Начинаем с первого вопроса
    survey_started = True  # Начинаем опрос
    send_question_with_buttons(chat_id, 0)

def delete_table():
    # 1. Установите соединение с базой данных
    conn = sqlite3.connect('base.db')

    try:
        # 2. Создайте объект курсора
        cursor = conn.cursor()

        # 3. Выполните SQL-запрос для удаления всех записей из таблицы task_assignments
        sql_tasks = "DROP TABLE IF EXISTS tasks"
        sql_tz = "DELETE FROM task_assignments"
        cursor.execute(sql_tasks)

        # 4. Завершите транзакцию и закройте соединение
        conn.commit()
    finally:
        conn.close()

# Создаем подключение к базе данных в каждом потоке
def get_connection():
    return sqlite3.connect('base.db')

def add_customer(customer_id, chat_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO customers (customer_id, chat_id) VALUES (?, ?)', (customer_id, chat_id))
    conn.commit()
    conn.close()


# Функция для получения роли пользователя по ID
def get_user_role(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT role FROM user_roles WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    if row:
        return row[0]
    conn.close()
    return None


def send_question_with_buttons(chat_id, question_index):
    question = questions[question_index]
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)

    if question_index == 0:
        keyboard.row("1", "2", "3", "Назад")
    elif question_index == 1:
        keyboard.row("PRO-STRONG", "BECLEAN", "Назад")
        keyboard.row("CARDIO-SEI", "FEMISTON")
    elif question_index == 2:
        keyboard.row("Статика", "Видео", "Назад")
    elif question_index == 3:
        keyboard.row("10 сек", "15 сек", "20 сек", "Назад")
    elif question_index == 8:
        keyboard.row("Каз", "Рус")
    else:
        keyboard = types.ReplyKeyboardRemove()  # Убираем клавиатуру

    bot.send_message(chat_id, question, reply_markup=keyboard)


# Обработчик команды /setrole для установки роли (только для администратора)
@bot.message_handler(commands=['setrole'])
def handle_set_role(message):
    user_id = message.from_user.id
    # Проверка роли пользователя, команду /setrole может выполнить только администратор
    user_role = get_user_role(user_id)
    if user_role != ADMIN_ROLE:
         bot.send_message(user_id, "У вас нет прав для выполнения этой команды.")
         return

    # Парсинг аргументов команды (например, "/setrole @username Дизайнер")
    args = message.text.split()
    if len(args) != 3:
        bot.send_message(user_id, "Используйте команду в формате /setrole @username Роль")
        return

    username = args[1]
    role = args[2]

    # Получение user_id по username
    user = None
    try:
        user = bot.get_chat(username)
    except telebot.apihelper.ApiException as e:
        bot.send_message(user_id, "Пользователь с указанным username не найден.")
        return

    if user is not None:
        user_id = user.id
        set_user_role(user_id, role)
        bot.send_message(user_id, f"Ваша роль установлена как {role}")
        add_customer(user_id, user_id)


def set_user_role(user_id, role):
    conn = get_connection()
    cursor = conn.cursor()

    # Проверяем, существует ли уже запись о роли пользователя
    cursor.execute('SELECT user_id FROM user_roles WHERE user_id = ?', (user_id,))
    existing_row = cursor.fetchone()

    if existing_row:
        # Если запись уже существует, обновляем её
        cursor.execute('UPDATE user_roles SET role = ? WHERE user_id = ?', (role, user_id))
    else:
        # Если записи нет, создаем новую
        cursor.execute('INSERT INTO user_roles (user_id, role) VALUES (?, ?)', (user_id, role))

    conn.commit()
    conn.close()


def create_keyboard_with_back_button():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.row("Назад")
    return keyboard

def create_keyboard_1_2_3():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.row("1", "2", "3")
    return keyboard

def create_keyboard_PRO_STRONG_CARDIO_SEI_BECLEAN_FEMISTON():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.row("PRO-STRONG", "BECLEAN")
    keyboard.row("CARDIO-SEI", "FEMISTON")
    return keyboard

def create_keyboard_static_video():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.row("Статика", "Видео")
    return keyboard

def create_keyboard_10s_15s_20s():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.row("10 сек", "15 сек", "20 сек")
    return keyboard

user_question_index = {}


@bot.message_handler(func=lambda message: message.text == "Назад")
def handle_back(message):
    chat_id = message.chat.id
    current_question = user_question_index.get(chat_id, 0)
    if current_question > 0:
        user_question_index[chat_id] = current_question - 1
        send_question_with_buttons(chat_id, current_question - 1)  # Отправляем предыдущий вопрос
    else:
        bot.send_message(chat_id, "Вы уже на первом вопросе.")


def send_user_answers_with_accept_reject_buttons(chat_id):
    answers = user_answers[chat_id]
    user = bot.get_chat_member(chat_id, chat_id)
    formatted_answers = "\n".join(
        [f"{question}\n{answers.get(i + 1, 'Ответ не предоставлен')}" for i, question in enumerate(questions, -1)])
    messages = f"✉️ | Пользователь @{user.user.username} (отправил ТЗ\n{formatted_answers}"
    bot.send_message(send_chat_id, messages)

    if chat_id in user_media:
        media_files = user_media[chat_id]
        for media_type, file_id in media_files.items():
            if media_type == 'photo':
                bot.send_photo(send_chat_id, file_id)
            elif media_type == 'video':
                bot.send_video(send_chat_id, file_id)
    accept_button = types.InlineKeyboardButton("Принять", callback_data=f"accept_{chat_id}")
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(accept_button)
    bot.send_message(send_chat_id, "Выберите действие:", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith('accept_'))
def handle_accept_callback(call):
    tz_id = ''.join(str(random.randint(0, 9)) for _ in range(10))
    chat_id = call.message.chat.id
    buyer_name = call.data.replace('accept_', '')
    logging.info(f"Accept callback triggered for buyer: {buyer_name}")
    designer_id = call.from_user.id
    print(designer_id, "1")
    name = get_username(chat_id)
    print(chat_id, "2")
    print(designer_id, "3")
    print(name,"4")
    insert_assignment(tz_id, designer_id, 'Принято', buyer_name)
    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
    notification_message = f"ТЗ с ID {tz_id} был одобрен @{name}"
    bot.send_message(designer_id, notification_message)
    bot.send_message(send_chat_id, notification_message)
    id_w = get_buyer_name_from_sql(tz_id)
    designer_id = get_designer_id_from_sql(id_w)
    global current_task_id
    current_task_id = call.data.split("_")[1]
    # Здесь вы можете добавить функцию, которая будет удалять задачу у дизайнера
    delete_task_for_designer(current_task_id)
    bot.send_message(designer_id, "Задача принята и удалена из вашего списка задач.")
    if designer_id:
        bot.send_message(designer_id, f"ТЗ с ID {tz_id} был принят @{call.from_user.username}")
        logger.info(f"Отправлено сообщение дизайнеру {designer_id} о принятии его крео")
    elif id_w:
            bot.send_message(id_w, "Ваш ТЗ  было принято!")
    else:
        bot.send_message(call.message.chat.id, "Не удалось найти информацию о дизайнере.")
    logging.info("Accept callback finished.")
def insert_assignment(task_id, designer_id, status, buyer_name):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO task_assignments (task_id, designer_id, status, buyer_name) VALUES (?, ?, ?, ?)',
                   (task_id, designer_id, status, buyer_name))
    conn.commit()
    conn.close()
def get_username(user_id):
    try:
        user = bot.get_chat(user_id)
        return user.username or user.first_name
    except Exception as e:
        print(f"An error occurred: {e}")
        return None
@bot.message_handler(commands=['assigned_tasks'])
def show_assigned_tasks(message):
    designer_id = message.from_user.id
    assigned_tasks = get_assigned_tasks(designer_id)
    if assigned_tasks:
        for task in assigned_tasks:
            task_id = task[0]
            status = task[1]
            buyer_name = task[2]
            name = get_username(buyer_name)

            response = f"ID задачи: {task_id}\nСтатус: {status}\nЗаказчик: @{name}"
            send_file_button = types.InlineKeyboardButton("Отправить файл", callback_data=f"send_file_{task_id}")
            markup = types.InlineKeyboardMarkup()
            markup.add(send_file_button)
            bot.send_message(message.chat.id, response, reply_markup=markup)
    else:
        response = "У вас нет назначенных задач."
        bot.send_message(message.chat.id, response)
logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
current_task_id = None
@bot.callback_query_handler(func=lambda call: call.data.startswith("send_file_"))
def send_file_callback(call):
    global current_task_id
    current_task_id = call.data.split("_")[2]
    buyer_name = get_buyer_name_from_sql(current_task_id)
    if buyer_name:
        bot.send_message(call.message.chat.id, "Отправьте ваш крео")


@bot.message_handler(content_types=['document'])
def receive_document(message):
    global current_task_id
    buyer_name = get_buyer_name_from_sql(current_task_id)
    document_file_id = message.document.file_id
    caption = "Ваш документ"

    bot.send_document(buyer_name, document_file_id, caption=caption)
    logger.info(f"Отправлен документ покупателю {buyer_name}")

    accept_button = types.InlineKeyboardButton("Принять крео", callback_data=f"accept_{current_task_id}")
    revise_button = types.InlineKeyboardButton("Переделать", callback_data=f"revise_{current_task_id}")
    markup = types.InlineKeyboardMarkup()
    markup.add(accept_button, revise_button)

    bot.send_message(buyer_name, "Пожалуйста, нажмите одну из кнопок ниже.", reply_markup=markup)


def process_revision_comment(message):
    global current_task_id
    designer_name = get_designer_id_from_sql(current_task_id)
    name = get_username(designer_name)
    bot.send_message(designer_name, f"Комментарий для переделки: {message.text} Для ТЗ с ID {current_task_id} Его делает @{name}")
    bot.send_message(send_chat_id, f"Комментарий для переделки: {message.text} Для ТЗ с ID {current_task_id} Его делает @{name}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("revise_"))
def revise_callback(call):
    global current_task_id
    current_task_id = call.data.split("_")[1]
    # Здесь вы можете добавить функцию, которая будет изменять статус задачи на 'переделка'
    change_task_status(current_task_id, 'На переделку')
    msg = bot.send_message(call.message.chat.id, "Пожалуйста, введите комментарий для переделки.")
    bot.register_next_step_handler(msg, process_revision_comment)
def delete_task_for_designer(task_id):
    # Подключение к базе данных
    conn = sqlite3.connect('base.db')
    cursor = conn.cursor()

    # Удаление задачи
    cursor.execute(f"DELETE FROM task_assignments WHERE task_id = {task_id}")

    # Закрытие соединения с базой данных
    conn.commit()
    conn.close()

def change_task_status(task_id, new_status):
    # Подключение к базе данных
    conn = sqlite3.connect('base.db')
    cursor = conn.cursor()

    # Изменение статуса задачи
    cursor.execute(f"UPDATE task_assignments SET status = '{new_status}' WHERE task_id = {task_id}")

    # Закрытие соединения с базой данных
    conn.commit()
    conn.close()
@bot.message_handler(content_types=['photo', 'video'])
def handle_media(message):
    chat_id = message.chat.id

    # Отправляем фото или видео напрямую
    if message.content_type == 'photo':
        bot.send_photo(send_chat_id, message.photo[-1].file_id)
    elif message.content_type == 'video':
        bot.send_video(send_chat_id, message.video.file_id)

    if chat_id in user_question_index:
        current_question = user_question_index[chat_id]

        if current_question < len(questions) - 1:
            user_question_index[chat_id] = current_question + 1
            send_question_with_buttons(chat_id, current_question + 1)  # Отправляем следующий вопрос
        else:
            # Опрос завершен, вы можете обработать ответы пользователя здесь
            send_user_answers_with_accept_reject_buttons(chat_id)

def get_designer_id_from_sql(task_id):
    conn = sqlite3.connect('base.db')  # Подставьте свой путь к базе данных
    cursor = conn.cursor()

    # Выполните SQL-запрос для получения designer_id на основе task_id
    cursor.execute("SELECT designer_id FROM task_assignments WHERE task_id = ?", (task_id,))
    result = cursor.fetchone()

    # Закройте соединение с базой данных
    conn.close()

    if result:
        designer_id = result[0]  # Вернуть designer_id из результата запроса
        return designer_id
    else:
        return None  # Если не удалось найти designer_id, вернуть None или другое значение по умолчанию

def get_buyer_name_from_sql(task_id):
    # Установите соединение с базой данных
    conn = sqlite3.connect('base.db')
    cursor = conn.cursor()

    # Выполните SQL-запрос для получения buyer_name на основе task_id
    cursor.execute("SELECT buyer_name FROM task_assignments WHERE task_id = ?", (task_id,))
    result = cursor.fetchone()

    # Закройте соединение с базой данных
    conn.close()

    if result:
        return result[0]  # Вернуть buyer_name из результата запроса
    else:
        return None
def get_assigned_tasks(designer_id):

    # Запросите базу данных, чтобы получить задачи, назначенные дизайнеру.
    # Эта функция должна вернуть список задач с их подробностями.
    # Приспособьте этот код к вашей структуре базы данных и логике запросов.
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT task_id, status, buyer_name FROM task_assignments WHERE designer_id = ?', (designer_id,))
    assigned_tasks = cursor.fetchall()
    conn.close()
    return assigned_tasks


def generate_unique_tz_id():
    return str(int(time.time()))  # Пример генерации ID на основе временной метки

@bot.message_handler(func=lambda message: True and not survey_completed)
def handle_text(message, tz_id=None):
    chat_id = message.chat.id
    current_question = user_question_index.get(chat_id, 0)
    if current_question >= len(questions) - 1:
        # Survey is completed, add a message to indicate that
        bot.send_message(chat_id, "Опрос завершен. Спасибо за ваши ответы!")
    # Проверяем, существует ли пользователь в user_answers, и если нет, создаем запись для него
    if chat_id not in user_answers:
        user_answers[chat_id] = {}

    user_answers[chat_id][current_question] = message.text  # Сохраняем ответ для теку

    # Проверяем, если есть еще вопросы, отправляем следующий
    if current_question < len(questions) - 1:
        user_question_index[chat_id] = current_question + 1
        send_question_with_buttons(chat_id, current_question + 1)  # Отправляем следующий вопрос
    else:
        # Опрос завершен, вы можете обработать ответы пользователя здесь
        user_answers[chat_id] = user_answers.get(chat_id, {})

        send_user_answers_with_accept_reject_buttons(chat_id)


bot.polling(none_stop=True)
