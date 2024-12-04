import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, Application, ContextTypes
from datetime import datetime, timedelta
from telegram.error import NetworkError, BadRequest
import asyncio

# Установите ваш токен и ID чата
TOKEN = "7573142030:AAHKtW1Y6qGrnp7qSR6w_5O0DIDdiXX9l88"
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
        self.cs_messages = {}  # Храним все сообщения сборов
        self.user_cooldowns = {}  # Тайм-ауты для каждого пользователя
        self.active_collections = {}  # Храним данные о активных сборах

        # Регистрируем обработчики
        self.application.add_handler(CommandHandler("cs", self.cs_command_handler))
        self.application.add_handler(CallbackQueryHandler(self.button_callback))

    def start(self):
        logger.info("Starting bot...")
        self.application.job_queue.run_once(self.check_and_send_start_message, when=datetime.now() + timedelta(seconds=1))
        # Добавляем задачу для поддержания активности бота
        self.application.job_queue.run_repeating(self.keep_alive_task, interval=30, first=30)
        self.application.run_polling()

    # Проверка и отправка стартового сообщения с кнопками
    async def check_and_send_start_message(self, context: ContextTypes.DEFAULT_TYPE):
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
            logger.info("Start message sent.")
        except NetworkError as e:
            logger.warning(f"Network error while sending start message: {e}")
        except BadRequest as e:
            logger.warning(f"Bad request while sending start message: {e}")

    # Функция для команды /cs
    async def cs_command_handler(self, update, context: ContextTypes.DEFAULT_TYPE):
        try:
            num_people = int(context.args[0])
            if num_people < 1 or num_people > 4:
                await update.message.reply_text("Пожалуйста, введите число от 1 до 4.")
                return
        except (IndexError, ValueError):
            await update.message.reply_text("Пожалуйста, введите число от 1 до 4.")
            return

        await self.create_cs_message(update.message.chat_id, num_people, context)

    # Создание сообщения сбора
    async def create_cs_message(self, chat_id, num_people, context, initiated_by=None):
        # Уникальный ID для сбора (на основе времени и инициатора)
        collection_id = f"{chat_id}_{initiated_by}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self.active_collections[collection_id] = {
            "user_count": num_people,
            "user_list": [],
            "initiator": initiated_by,
            "message_id": None
        }

        initiator_text = f"*{initiated_by}*" if initiated_by else "Кто-то"
        message = (f"{initiator_text} собирает стак на КС. Требуется {num_people} человек.\n"
                   f"Кто будет, жмите на кнопку! (Нажимать только если точно будете)\n\n"
                   f"*Список людей, которые нажимают кнопку:*")

        keyboard = [[InlineKeyboardButton("✅ Я готов!", callback_data=f"join_game_{collection_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            sent_message = await context.bot.send_message(chat_id=chat_id, text=message, reply_markup=reply_markup, parse_mode="Markdown")
            self.active_collections[collection_id]["message_id"] = sent_message.message_id

            self.job_queue.run_once(self.delete_message, timedelta(minutes=30),
                                    data={"chat_id": chat_id, "message_id": sent_message.message_id, "collection_id": collection_id})
        except NetworkError as e:
            logger.warning(f"Network error while creating CS message: {e}")
        except BadRequest as e:
            logger.warning(f"Bad request while creating CS message: {e}")

    # Обработчик нажатий на кнопки
    async def button_callback(self, update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user = query.from_user.username
        data = query.data

        try:
            if data.startswith("start_"):
                num_people = int(data.split("_")[1])

                last_press_time = self.user_cooldowns.get(user)
                if last_press_time and datetime.now() - last_press_time < timedelta(minutes=30):
                    await query.answer("Вы можете создавать сбор раз в 30 минут.", show_alert=True)
                    return

                self.user_cooldowns[user] = datetime.now()
                await self.create_cs_message(query.message.chat_id, num_people, context, initiated_by=user)
                return

            if data.startswith("join_game_"):
                collection_id = data.split("_")[2]
                if collection_id not in self.active_collections:
                    return

                collection = self.active_collections[collection_id]

                if user not in collection["user_list"]:
                    collection["user_list"].append(user)
                    collection["user_count"] -= 1

                message = (f"СРОЧНО собираем стак на КС. Осталось {collection['user_count']} мест.\n"
                           f"Кто будет, жмите на кнопку! (Нажимать только если точно будете)\n\n"
                           f"*Список людей, которые нажимают кнопку:*\n" + "\n".join(collection["user_list"]))

                if collection["user_count"] == 0:
                    message += "\n\n*...СБОР ЗАКРЫТ...*"

                await context.bot.edit_message_text(chat_id=query.message.chat_id,
                                                    message_id=query.message.message_id,
                                                    text=message,
                                                    parse_mode="Markdown",
                                                    reply_markup=InlineKeyboardMarkup(
                                                        [[]] if collection["user_count"] == 0 else [
                                                            [InlineKeyboardButton("✅ Я готов!", callback_data=f"join_game_{collection_id}")]]))
        except NetworkError as e:
            logger.warning(f"Network error during button callback: {e}")
        except BadRequest as e:
            logger.warning(f"Bad request during button callback: {e}")

    # Удаление сообщения через 30 минут
    async def delete_message(self, context: ContextTypes.DEFAULT_TYPE):
        job_data = context.job.data
        chat_id = job_data["chat_id"]
        message_id = job_data["message_id"]
        collection_id = job_data["collection_id"]

        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            del self.active_collections[collection_id]
        except BadRequest as e:
            if "Message to delete not found" in str(e):
                logger.info("Message already deleted or not found.")
            else:
                logger.warning(f"Error deleting message: {e}")

    # Задача для поддержания активности бота
    async def keep_alive_task(self, context: ContextTypes.DEFAULT_TYPE):
        # Просто выполняем незначительное действие для поддержания активности
        logger.info("Performing keep-alive task.")
        await asyncio.sleep(0)  # Просто асинхронная пауза, которая не делает ничего, но поддерживает активность

if __name__ == "__main__":
    bot = CSBot(TOKEN)
    bot.start()
