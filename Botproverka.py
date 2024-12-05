import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, Application, ContextTypes
from datetime import datetime, timedelta
from telegram.error import NetworkError, BadRequest
import asyncio
import os

# Установите ваш токен и ID чата
TOKEN = "7936618968:AAH2PIcfjir0a_urLzommIOmG1WCZPvbPMc"
CHAT_ID = "-1002317588357"

# Настроим логирование для отладки
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

class CSBot:
    def __init__(self, token):
        # Используем Application.builder() для создания приложения
        self.application = Application.builder().token(token).build()
        self.job_queue = self.application.job_queue

        # Инициализация переменных
        self.start_message_id = None  # ID стартового сообщения с кнопками

        # Регистрируем обработчики
        self.application.add_handler(CommandHandler("cs", self.cs_command_handler))
        self.application.add_handler(CallbackQueryHandler(self.button_callback))

    def start(self):
        logger.info("Starting bot...")
        self.application.job_queue.run_once(self.delete_old_messages, when=datetime.now() + timedelta(seconds=1))
        self.application.job_queue.run_once(self.check_and_send_start_message, when=datetime.now() + timedelta(seconds=5))
        self.application.job_queue.run_repeating(self.keep_alive_task, interval=30, first=30)
        self.application.run_polling()

    async def delete_old_messages(self, context: ContextTypes.DEFAULT_TYPE):
        """Удаление всех старых сообщений бота в группе."""
        try:
            # Получение всех сообщений в чате (можно ограничить поиск по времени)
            messages = await context.bot.get_chat_administrators(CHAT_ID)
            for message in messages:
                if message.user.id == context.bot.id:
                    await context.bot.delete_message(chat_id=CHAT_ID, message_id=message.message_id)
                    logger.info(f"Удалено сообщение ID: {message.message_id}")
        except Exception as e:
            logger.error(f"Ошибка при удалении старых сообщений: {e}")

    async def check_and_send_start_message(self, context: ContextTypes.DEFAULT_TYPE):
        """Проверка и отправка стартового сообщения с кнопками."""
        start_message_text = "СОЗДАТЬ СБОР НА КС! (Нажать на количество человек)"
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
            logger.info("Стартовое сообщение отправлено.")
        except Exception as e:
            logger.error(f"Ошибка при отправке стартового сообщения: {e}")

    async def cs_command_handler(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /cs (создание сбора вручную)."""
        await update.message.reply_text("Для создания сбора используйте кнопки в стартовом сообщении.")

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

        except Exception as e:
            logger.error(f"Ошибка при обработке кнопки: {e}")

    async def create_cs_message(self, chat_id, num_people, context, initiated_by=None):
        """Создание сообщения сбора."""
        message = (f"{initiated_by} запустил СРОЧНЫЙ сбор в КС. Требуется {num_people} человек.\n"
                   f"Кто будет, жмите на кнопку! (Нажимать только если точно будете)\n\n"
                   f"*Список людей, которые нажимают кнопку:*")

        keyboard = [
            [InlineKeyboardButton("✅ Я готов!", callback_data="join_game")],
            [InlineKeyboardButton("Закрыть сбор принудительно", callback_data="close_game")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            sent_message = await context.bot.send_message(chat_id=chat_id, text=message, reply_markup=reply_markup, parse_mode="Markdown")
            logger.info("Сообщение сбора отправлено.")

            # Удаление через 30 минут
            self.job_queue.run_once(self.delete_message, timedelta(minutes=30),
                                    data={"chat_id": chat_id, "message_id": sent_message.message_id})
        except Exception as e:
            logger.error(f"Ошибка при создании сообщения сбора: {e}")

    async def delete_message(self, context: ContextTypes.DEFAULT_TYPE):
        """Удаление сообщения через 30 минут."""
        job_data = context.job.data
        chat_id = job_data["chat_id"]
        message_id = job_data["message_id"]

        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            logger.info(f"Сообщение с ID {message_id} удалено.")
        except Exception as e:
            logger.error(f"Ошибка при удалении сообщения: {e}")

    async def keep_alive_task(self, context: ContextTypes.DEFAULT_TYPE):
        """Задача для поддержания активности бота."""
        logger.info("Keep-alive task.")
        await asyncio.sleep(0)

if __name__ == "__main__":
    bot = CSBot(TOKEN)
    bot.start()
