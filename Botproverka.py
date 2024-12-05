import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, Application, ContextTypes
from datetime import timedelta
import asyncio
from collections import defaultdict

# Настройки
TOKEN = "7936618968:AAH2PIcfjir0a_urLzommIOmG1WCZPvbPMc"
CHAT_ID = "-1002317588357"

# Логирование
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

class CSBot:
    def __init__(self, token):
        self.application = Application.builder().token(token).build()
        self.cs_sessions = []  # Массив для хранения всех сборов
        self.current_session = None  # Текущий сбор, который активен
        self.last_closed_session_id = None  # ID последнего закрытого сбора
        self.user_request_flags = defaultdict(lambda: False)  # Флаг блокировки для каждого пользователя

        # Регистрируем обработчики
        self.application.add_handler(CommandHandler("start", self.start_command_handler))
        self.application.add_handler(CallbackQueryHandler(self.button_callback))

    def start(self):
        """Запуск бота."""
        logger.info("Запуск бота...")
        self.application.job_queue.run_once(self.check_start_message, when=0)  # Проверка старта
        self.application.run_polling()

    async def check_start_message(self, context: ContextTypes.DEFAULT_TYPE):
        """Проверка и удаление сообщений от бота, создание стартового сообщения."""
        logger.info("Проверка и удаление старых сообщений...")
        try:
            # Создаем стартовое сообщение
            await self.create_start_message(context)
        except Exception as e:
            logger.error(f"Ошибка при проверке стартового сообщения: {e}")

    async def create_start_message(self, context: ContextTypes.DEFAULT_TYPE):
        """Создание стартового сообщения с кнопками."""
        text = "СОЗДАТЬ СБОР НА КС. (Выберите количество нужных людей, кроме себя)"
        keyboard = [
            [InlineKeyboardButton("1", callback_data="start_1"),
             InlineKeyboardButton("2", callback_data="start_2"),
             InlineKeyboardButton("3", callback_data="start_3"),
             InlineKeyboardButton("4", callback_data="start_4")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            # Попытка отправить сообщение
            await self.try_send_message(context, text, reply_markup)
        except Exception as e:
            logger.error(f"Ошибка при создании стартового сообщения: {e}")

    async def try_send_message(self, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup: InlineKeyboardMarkup):
        """Попытка отправки сообщения с повтором в случае ошибки."""
        try:
            await context.bot.send_message(chat_id=CHAT_ID, text=text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения: {e}")
            # Попробуем снова через 5 секунд
            await asyncio.sleep(5)
            try:
                await context.bot.send_message(chat_id=CHAT_ID, text=text, reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Повторная ошибка при отправке сообщения: {e}")

    async def start_command_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /start."""
        await update.message.reply_text("Бот уже работает. Используйте кнопки для взаимодействия.")

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий на кнопки."""
        query = update.callback_query
        data = query.data
        user = query.from_user.username
        try:
            # Если пользователь уже нажимал кнопку, заблокировать повторные запросы
            if self.user_request_flags[user]:
                await query.answer("Подождите, ваш предыдущий запрос еще обрабатывается.", show_alert=True)
                return

            # Блокируем запрос от пользователя
            self.user_request_flags[user] = True

            if data.startswith("start_"):
                # Проверка, существует ли открытый сбор
                if self.current_session and self.current_session.cs_status == "open":
                    await query.answer("Вы не можете создать сбор, пока есть открытый сбор.", show_alert=True)
                    self.user_request_flags[user] = False  # Разблокируем пользователя
                    return

                # Удаление старого закрытого сбора
                if self.last_closed_session_id:
                    old_session = next((session for session in self.cs_sessions if session.message_id == self.last_closed_session_id), None)
                    if old_session:
                        await old_session.delete_cs_message(context)
                        logger.info(f"Старый закрытый сбор с ID {self.last_closed_session_id} удален.")
                        self.last_closed_session_id = None  # Обнуляем ID старого сбора после удаления

                # Получаем количество человек для сбора
                num_people_required = int(data.split("_")[1])

                # Создаем новый сбор
                new_session = CSGameSession(user, num_people_required)
                self.cs_sessions.append(new_session)
                self.current_session = new_session
                await new_session.create_cs_message(context)

                # Сохраняем ID нового сбора
                self.last_closed_session_id = new_session.message_id
                self.user_request_flags[user] = False  # Разблокируем пользователя
                return

            if data == "join_game" and self.current_session and self.current_session.cs_status == "open":
                # Логика для обработки нажатия "Я буду"
                # Проверка, что создатель не нажал кнопку "Я буду"
                if user == self.current_session.creator:
                    await query.answer("Вы не можете нажать эту кнопку в сборе который и так создали.", show_alert=True)
                    self.user_request_flags[user] = False
                    return

                await self.current_session.join_cs(update, context)

            if data == "close_game" and self.current_session:
                # Логика для закрытия сбора и его удаления
                await self.current_session.close_and_delete_cs(context, update.callback_query.message.message_id)

            # Разблокируем пользователя после обработки запроса
            self.user_request_flags[user] = False

        except Exception as e:
            logger.error(f"Ошибка при обработке нажатия кнопки: {e}")
            # Разблокируем пользователя в случае ошибки
            self.user_request_flags[user] = False

class CSGameSession:
    def __init__(self, creator, num_people_required):
        self.cs_status = "open"  # Статус сбора: "open" или "closed"
        self.creator = creator  # Создатель сбора
        self.num_people_required = num_people_required  # Количество людей, нужных для сбора
        self.current_players = []  # Список участников
        self.message_id = None  # ID сообщения, связанного с этим сбором

    async def create_cs_message(self, context: ContextTypes.DEFAULT_TYPE):
        """Создание сообщения о сборе."""
        text = (f"*{self.creator}* собирает стак на КС. Нужно {self.num_people_required} человек.\n"
                f"Нажмите зеленую кнопку, если ТОЧНО будете!\n\n"
                f"*Список тех, кто будет:*\n")
        keyboard = [
            [InlineKeyboardButton("✅ Я буду", callback_data="join_game")],
            [InlineKeyboardButton("❌ Закрыть и удалить сбор", callback_data="close_game")]  # Эта кнопка не должна исчезать
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            sent_message = await context.bot.send_message(chat_id=CHAT_ID, text=text, reply_markup=reply_markup, parse_mode="Markdown")
            self.message_id = sent_message.message_id
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения о сборе: {e}")

    async def join_cs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Добавление игрока в сбор."""
        user = update.callback_query.from_user.username
        if user not in self.current_players:
            self.current_players.append(user)
            self.num_people_required -= 1  # Уменьшаем количество необходимых людей

            # Если все люди записались, обновляем сообщение с пометкой "Сбор закрыт"
            if self.num_people_required == 0:
                await self.update_message(context)

            await self.update_message(context)
        else:
            await update.callback_query.answer("Вы уже записались на сбор!")

    async def update_message(self, context: ContextTypes.DEFAULT_TYPE):
        """Обновление сообщения о сборе."""
        text = (f"*{self.creator}* собирает стак на КС. Нужно {self.num_people_required} человек.\n"
                f"Нажмите зеленую кнопку, если ТОЧНО будете!\n\n"
                f"*Список тех, кто будет:*\n" + "\n".join(self.current_players))
        if self.num_people_required == 0:
            text += "\n\n*Сбор закрыт!*"
            self.cs_status = "closed"

        keyboard = [
            [InlineKeyboardButton("✅ Я буду", callback_data="join_game")] if self.num_people_required > 0 else [],
            [InlineKeyboardButton("❌ Закрыть и удалить сбор", callback_data="close_game")]  # Эта кнопка остается
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await context.bot.edit_message_text(
                chat_id=CHAT_ID, message_id=self.message_id, text=text, reply_markup=reply_markup, parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Ошибка при обновлении сообщения: {e}")

    async def close_and_delete_cs(self, context: ContextTypes.DEFAULT_TYPE, message_id=None):
        """Закрытие сбора и удаление его из чата и памяти."""
        try:
            if self.cs_status == "open":
                self.cs_status = "closed"  # Закрываем сбор
            if message_id:
                await context.bot.delete_message(chat_id=CHAT_ID, message_id=message_id)
            self.current_players.clear()  # Очищаем список участников
            self.message_id = None
            logger.info(f"Сбор '{self.creator}' закрыт и удален.")
        except Exception as e:
            logger.error(f"Ошибка при закрытии сбора: {e}")

# Запуск бота
if __name__ == "__main__":
    bot = CSBot(TOKEN)
    bot.start()
