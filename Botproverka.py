import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, Application, ContextTypes
from datetime import datetime, timedelta
from telegram.error import NetworkError, BadRequest
import asyncio

# Установите ваш токен и ID чата
TOKEN = "7573142030:AAFZeOQHq4roTVkw4rVv1MTKv1_3ShdM3l8"
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
        self.cs_message_id = None  # ID сообщения для сбора людей
        self.start_message_id = None  # ID стартового сообщения с кнопками
        self.start_message_sent = False  # Проверка на отправку стартового сообщения
        self.user_list = []  # Список пользователей, кто нажал на кнопку
        self.user_count = 0  # Сколько людей нужно для игры
        self.old_collection_deleted = False  # Переменная для отслеживания удален ли старый сбор

        # Регистрируем обработчики
        self.application.add_handler(CommandHandler("cs", self.cs_command_handler))
        self.application.add_handler(CallbackQueryHandler(self.button_callback))

    def start(self):
        logger.info("Starting bot...")
        # Задержка в 1 секунду перед запуском первой задачи
        self.application.job_queue.run_once(self.check_and_send_start_message, when=datetime.now() + timedelta(seconds=10)) 
        # Добавляем задачу для поддержания активности бота
        self.application.job_queue.run_repeating(self.keep_alive_task, interval=30, first=30)
        self.application.run_polling()

    # Проверка и отправка стартового сообщения с кнопками
    async def check_and_send_start_message(self, context: ContextTypes.DEFAULT_TYPE):
        if not self.start_message_sent:
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
                self.start_message_sent = True
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

        # Проверка на наличие открытого сбора
        if not await self.is_old_collection_finished(update.message.chat_id):
            await update.message.reply_text("Вы не можете создать новый сбор пока не закроется предыдущий сбор.")
            return

        await self.create_cs_message(update.message.chat_id, num_people, context)

    # Проверка на наличие сообщений о сборе
    async def is_old_collection_finished(self, chat_id):
        # Проверяем, есть ли сообщение о сборе
        if self.cs_message_id:
            # Получаем сообщение, чтобы проверить статус сбора
            message = await self.application.bot.get_message(chat_id=chat_id, message_id=self.cs_message_id)
            
            if message:
                # Если сбор еще не закрыт (людей осталось больше 0), возвращаем False
                if self.user_count > 0:
                    return False
                # Если сбор закрыт (людей 0), разрешаем новый сбор
                elif self.user_count == 0:
                    return True
            return True  # Если нет старого сообщения, разрешаем создание нового сбора
        else:
            return True  # Если нет сообщения, значит сборы не активны, разрешаем новый

    # Создание сообщения сбора
    async def create_cs_message(self, chat_id, num_people, context, initiated_by=None):
        # Если старое сообщение было удалено или закрыто (оставшихся людей 0), разрешаем создание нового сбора
        if self.cs_message_id and self.user_count == 0:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=self.cs_message_id)
                logger.info("Previous CS message deleted because it was closed or removed.")
            except BadRequest as e:
                logger.warning(f"Failed to delete previous message: {e}")

        # Если старое сообщение удалено, можно создавать новый сбор
        if self.cs_message_id and self.old_collection_deleted:
            self.old_collection_deleted = False  # Сбрасываем флаг

        self.user_count = num_people
        self.user_list.clear()

        # Имя инициатора будет всегда отображаться в сообщении
        initiator_text = f"*{initiated_by}*" if initiated_by else "Кто-то"
        message = (f"{initiator_text} собирает стак на КС. Требуется {num_people} человек.\n"
                   f"Кто будет, жмите на кнопку! (Нажимать только если точно будете)\n\n"
                   f"*Список людей, которые нажимают кнопку:*")

        keyboard = [[InlineKeyboardButton("✅ Я готов!", callback_data="join_game")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            sent_message = await context.bot.send_message(chat_id=chat_id, text=message, reply_markup=reply_markup, parse_mode="Markdown")
            self.cs_message_id = sent_message.message_id

            self.job_queue.run_once(self.delete_message, timedelta(minutes=30),
                                    data={"chat_id": chat_id, "message_id": sent_message.message_id})
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

                # Проверка на наличие открытого сбора
                if not await self.is_old_collection_finished(query.message.chat_id):
                    await query.answer("Вы не можете создать новый сбор пока не закроется предыдущий сбор.", show_alert=True)
                    return

                await self.create_cs_message(query.message.chat_id, num_people, context, initiated_by=user)
                return

            if data == "join_game":
                if user not in self.user_list:
                    self.user_list.append(user)
                    self.user_count -= 1

                message = (f"СРОЧНО собираем стак на КС. Осталось {self.user_count} мест.\n"
                           f"Кто будет, жмите на кнопку! (Нажимать только если точно будете)\n\n"
                           f"*Список людей, которые нажимают кнопку:*\n" + "\n".join(self.user_list))

                if self.user_count == 0:
                    message += "\n\n*...СБОР ЗАКРЫТ...*"

                await context.bot.edit_message_text(chat_id=query.message.chat_id,
                                                    message_id=query.message.message_id,
                                                    text=message,
                                                    parse_mode="Markdown",
                                                    reply_markup=InlineKeyboardMarkup(
                                                        [[]] if self.user_count == 0 else [[InlineKeyboardButton("✅ Я готов!", callback_data="join_game")]]))
        except NetworkError as e:
            logger.warning(f"Network error during button callback: {e}")
        except BadRequest as e:
            logger.warning(f"Bad request during button callback: {e}")

    # Удаление сообщения по таймеру
    async def delete_message(self, context: ContextTypes.DEFAULT_TYPE, chat_id, message_id):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            self.user_count = 0  # Закрытие сбора
            self.old_collection_deleted = True  # Устанавливаем флаг удаления старого сбора
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
