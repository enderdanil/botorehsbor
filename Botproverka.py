import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, Application, ContextTypes
from datetime import datetime, timedelta
from telegram.error import NetworkError, BadRequest
import asyncio
import os
import json

# Установите ваш токен и ID чата
TOKEN = "7936618968:AAH2PIcfjir0a_urLzommIOmG1WCZPvbPMc"
CHAT_ID = "-1002317588357"

# Настроим логирование для отладки
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_FILE = "cs_data.json"  # Файл для хранения ID сообщения и статусов

class CSBot:
    def __init__(self, token):
        # Используем Application.builder() для создания приложения
        self.application = Application.builder().token(token).build()
        self.job_queue = self.application.job_queue

        # Инициализация переменных
        self.start_message_id = None  # ID стартового сообщения с кнопками
        self.cs_message_data = None  # Данные активного сбора (ID сообщения, статус, список пользователей)

        # Загружаем сохраненные данные
        self.load_data()

        # Регистрируем обработчики
        self.application.add_handler(CommandHandler("cs", self.cs_command_handler))
        self.application.add_handler(CallbackQueryHandler(self.button_callback))

    def load_data(self):
        """Загрузка данных из файла."""
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as file:
                data = json.load(file)
                self.start_message_id = data.get("start_message_id")
                self.cs_message_data = data.get("cs_message_data")
                logger.info("Данные загружены.")
        else:
            logger.info("Файл данных не найден, начинаем с чистого состояния.")

    def save_data(self):
        """Сохранение данных в файл."""
        data = {
            "start_message_id": self.start_message_id,
            "cs_message_data": self.cs_message_data,
        }
        with open(DATA_FILE, "w") as file:
            json.dump(data, file)
        logger.info("Данные сохранены.")

    def start(self):
        logger.info("Starting bot...")
        # Задержка в 1 секунду перед запуском первой задачи
        self.application.job_queue.run_once(self.check_and_send_start_message, when=datetime.now() + timedelta(seconds=1))
        # Добавляем задачу для поддержания активности бота
        self.application.job_queue.run_repeating(self.keep_alive_task, interval=30, first=30)
        self.application.run_polling()

    async def check_and_send_start_message(self, context: ContextTypes.DEFAULT_TYPE):
        """Проверка и отправка стартового сообщения с кнопками."""
        if not self.start_message_id:
            start_message_text = "СОЗДАТЬ СБОР НА КС! (Нажать на количество человек. Работает раз в 30 минут для каждого)"
            keyboard = [
                [InlineKeyboardButton("1", callback_data="start_1"),
                 InlineKeyboardButton("2", callback_data="start_2"),
                 InlineKeyboardButton("3", callback_data="start_3"),
                 InlineKeyboardButton("4", callback_data="start_4")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            try:
                sent_message = await context.bot.send_message(chat_id=CHAT_ID, text=start_message_text, reply_markup=reply_markup)
                self.start_message_id = sent_message.message_id
                self.save_data()
                logger.info("Стартовое сообщение отправлено.")
            except Exception as e:
                logger.error(f"Ошибка при отправке стартового сообщения: {e}")

    async def cs_command_handler(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /cs (создание сбора вручную)."""
        await update.message.reply_text("Для создания сбора используйте кнопки в стартовом сообщении.")

    async def create_cs_message(self, chat_id, num_people, context, initiated_by=None):
        """Создание сообщения сбора."""
        if self.cs_message_data and self.cs_message_data.get("status") == "open":
            return  # Если есть открытый сбор, новый не создаем

        self.cs_message_data = {
            "initiated_by": initiated_by,
            "user_count": num_people,
            "users": [],
            "status": "open",
        }

        initiator_text = f"*{initiated_by}*" if initiated_by else "Кто-то"
        message = (f"{initiator_text} запустил СРОЧНЫЙ сбор в КС. Требуется {num_people} человек.\n"
                   f"Кто будет, жмите на кнопку! (Нажимать только если точно будете)\n\n"
                   f"*Список людей, которые нажимают кнопку:*")

        keyboard = [
            [InlineKeyboardButton("✅ Я готов!", callback_data="join_game")],
            [InlineKeyboardButton("❌ X", callback_data="close_game")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            sent_message = await context.bot.send_message(chat_id=chat_id, text=message, reply_markup=reply_markup, parse_mode="Markdown")
            self.cs_message_data["message_id"] = sent_message.message_id
            self.save_data()

            # Удаление через 30 минут
            self.job_queue.run_once(self.delete_message, timedelta(minutes=30),
                                    data={"chat_id": chat_id, "message_id": sent_message.message_id})
        except Exception as e:
            logger.error(f"Ошибка при создании сообщения сбора: {e}")

    async def button_callback(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий на кнопки."""
        query = update.callback_query
        user = query.from_user.username
        data = query.data

        try:
            if data.startswith("start_"):
                num_people = int(data.split("_")[1])
                await self.create_cs_message(query.message.chat_id, num_people, context, initiated_by=user)
                return

            if data == "join_game":
                if not self.cs_message_data or self.cs_message_data.get("status") != "open":
                    await query.answer("Сбор уже закрыт.", show_alert=True)
                    return

                if user == self.cs_message_data.get("initiated_by"):
                    await query.answer("Вы не можете нажать на эту кнопку, так как вы являетесь организатором сбора.", show_alert=True)
                    return

                if user not in self.cs_message_data["users"]:
                    self.cs_message_data["users"].append(user)
                    self.cs_message_data["user_count"] -= 1

                if self.cs_message_data["user_count"] <= 0:
                    self.cs_message_data["status"] = "closed"

                message = (f"*СРОЧНЫЙ сбор в КС.* Осталось {self.cs_message_data['user_count']} мест.\n"
                           f"Кто будет, жмите на кнопку! (Нажимать только если точно будете)\n\n"
                           f"*Список людей:*\n" + "\n".join(self.cs_message_data["users"]))
                if self.cs_message_data["user_count"] <= 0:
                    message += "\n\n*...СБОР ЗАКРЫТ...*"

                await context.bot.edit_message_text(chat_id=query.message.chat_id,
                                                    message_id=self.cs_message_data["message_id"],
                                                    text=message,
                                                    parse_mode="Markdown",
                                                    reply_markup=InlineKeyboardMarkup(
                                                        [[InlineKeyboardButton("❌ X", callback_data="close_game")]]
                                                        if self.cs_message_data["status"] == "closed" else [[
                                                            InlineKeyboardButton("✅ Я готов!", callback_data="join_game"),
                                                            InlineKeyboardButton("❌ X", callback_data="close_game")
                                                        ]])
                                                    )
                self.save_data()

            if data == "close_game":
                await context.bot.delete_message(chat_id=query.message.chat_id,
                                                 message_id=self.cs_message_data["message_id"])
                self.cs_message_data = None
                self.save_data()
                await query.answer("Сбор закрыт и удален.")
        except Exception as e:
            logger.error(f"Ошибка при обработке кнопки: {e}")

    async def delete_message(self, context: ContextTypes.DEFAULT_TYPE):
        """Удаление сообщения через 30 минут."""
        job_data = context.job.data
        chat_id = job_data["chat_id"]
        message_id = job_data["message_id"]

        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            if self.cs_message_data and self.cs_message_data.get("message_id") == message_id:
                self.cs_message_data = None
                self.save_data()
        except Exception as e:
            logger.error(f"Ошибка при удалении сообщения: {e}")

    async def keep_alive_task(self, context: ContextTypes.DEFAULT_TYPE):
        """Задача для поддержания активности бота."""
        logger.info("Keep-alive task.")
        await asyncio.sleep(0)

if __name__ == "__main__":
    bot = CSBot(TOKEN)
    bot.start()
