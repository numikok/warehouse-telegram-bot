import asyncio
import logging
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from database import get_db, engine
from models import Base, User, UserRole, Operation, OrderStatus
from handlers import (
    admin,
    production,
    sales,
    warehouse,
    production_orders,
    orders,
    super_admin,
    back_handler,
)
from handlers.admin import cmd_users, cmd_report, cmd_assign_role
from handlers.sales import handle_warehouse_order, handle_stock, handle_create_order
from handlers.warehouse import cmd_stock, cmd_confirm_order, cmd_income_materials
from navigation import get_role_keyboard, MenuState
import http.server
import socketserver
import threading
from flask import Flask

# Load environment variables
load_dotenv()

# Get token from environment
TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL", "")  # URL приложения Heroku, если используются webhooks

# Enable logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Register all handlers
dp.include_router(super_admin.router)
dp.include_router(admin.router)
dp.include_router(production.router)
dp.include_router(sales.router)
dp.include_router(warehouse.router)
dp.include_router(production_orders.router)
dp.include_router(orders.router)
dp.include_router(back_handler.router)

# Создаем Flask приложение
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот запущен и работает!"

def run_flask():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    try:
        logging.info(f"Starting user registration process for user {message.from_user.id}")
        db = next(get_db())
        
        # Получаем информацию о пользователе из сообщения
        telegram_id = message.from_user.id
        username = message.from_user.username or "unknown"
        
        # Получаем ADMIN_USER_ID из переменных окружения
        admin_id = int(os.getenv("ADMIN_USER_ID", 0))
        
        logging.info(f"Checking if user {telegram_id} exists in database")
        # Проверяем, существует ли пользователь
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        
        if not user:
            logging.info(f"Creating new user with telegram_id={telegram_id} and username={username}")
            # Создаем нового пользователя с ролью по умолчанию
            user = User(
                telegram_id=telegram_id,
                username=username,
                role=UserRole.SUPER_ADMIN if telegram_id == admin_id else UserRole.NONE
            )
            db.add(user)
            db.commit()
            logging.info("New user successfully created and committed to database")
            
            # Устанавливаем начальное состояние меню
            await state.set_state(MenuState.SUPER_ADMIN_MAIN if telegram_id == admin_id else None)
            
            # Создаем клавиатуру в зависимости от роли
            keyboard = get_role_keyboard(user.role) if user.role != UserRole.NONE else ReplyKeyboardRemove()
            
            if user.role == UserRole.NONE:
                await message.answer(
                    "👋 Добро пожаловать в бот управления складом!\n\n"
                    "⏳ *Ожидание роли*\n\n"
                    "Ваша учетная запись зарегистрирована, но роль пока не назначена. "
                    "Пожалуйста, дождитесь, когда администратор назначит вам роль для доступа к системе."
                )
            elif user.role == UserRole.SUPER_ADMIN:
                await message.answer(
                    f"👋 Добро пожаловать в бот управления складом!\n\n"
                    f"👑 *Супер-администратор*\n\n"
                    f"Вы имеете полный доступ ко всем функциям системы и можете управлять пользователями, просматривать отчеты и работать с любыми ролями.\n\n"
                    f"**Основное меню:**\n"
                    f"- 👥 **Управление пользователями** — назначение ролей, просмотр списка пользователей, удаление пользователей, сброс ролей\n"
                    f"- 📊 **Отчеты и статистика** — просмотр данных о запасах, продажах и производстве\n"
                    f"- 📦 **Управление складом** — проверка остатков, работа с заказами и материалами\n"
                    f"- 🏭 **Управление производством** — контроль производственных процессов, работа с заказами\n\n"
                    f"**Эмуляция ролей:**\n"
                    f"- 💼 **Менеджер по продажам** — временное переключение для работы от имени менеджера\n"
                    f"- 🏭 **Производство** — временное переключение для работы от имени производства\n"
                    f"- 📦 **Склад** — временное переключение для работы от имени склада\n\n"
                    f"При работе в других ролях у вас всегда будет кнопка 🔙 **Назад в админку** для возврата в меню администратора",
                    reply_markup=keyboard
                )
            elif user.role == UserRole.SALES_MANAGER:
                await message.answer(
                    f"👋 Добро пожаловать в бот управления складом!\n\n"
                    f"💼 *Менеджер по продажам*\n\n"
                    f"Ваша задача — создавать заказы для клиентов, проверять наличие товаров на складе и оформлять заказы на производство новой продукции.\n\n"
                    f"**Основное меню:**\n"
                    f"- 📝 **Составить заказ** — создание нового заказа для клиента с выбором цвета пленки, количества панелей и дополнительных материалов\n"
                    f"- 📦 **Количество готовой продукции** — проверка наличия готовых панелей по цветам для оформления заказа клиенту\n"
                    f"- 📝 **Заказать производство** — оформление запроса на изготовление новых панелей нужного цвета и количества\n"
                    f"- 📋 **Мои заказы** — просмотр списка ваших заказов с информацией о статусе и деталях\n\n"
                    f"Для возврата в главное меню из любого раздела используйте кнопку ◀️ **Назад**",
                    reply_markup=keyboard
                )
            elif user.role == UserRole.PRODUCTION:
                await message.answer(
                    f"👋 Добро пожаловать в бот управления складом!\n\n"
                    f"🏭 *Производство*\n\n"
                    f"Ваша задача — регистрировать поступление материалов, производить панели и учитывать брак в процессе работы.\n\n"
                    f"**Основное меню:**\n"
                    f"- 📥 **Приход сырья** — добавление в систему новых материалов (панелей, пленки, стыков, клея) с указанием количества и параметров\n"
                    f"- 🛠 **Производство** — регистрация изготовления новых панелей с указанием использованных материалов\n"
                    f"- 🚫 **Брак** — учет бракованных материалов и готовой продукции с указанием типа и количества\n"
                    f"- 📋 **Заказы на производство** — просмотр и выполнение заказов от менеджеров на изготовление панелей определенного цвета\n"
                    f"- 📦 **Мои заказы** — просмотр активных и завершенных заказов производства\n\n"
                    f"Для возврата в главное меню из любого раздела используйте кнопку ◀️ **Назад**",
                    reply_markup=keyboard
                )
            elif user.role == UserRole.WAREHOUSE:
                await message.answer(
                    f"👋 Добро пожаловать в бот управления складом!\n\n"
                    f"📦 *Склад*\n\n"
                    f"Ваша задача — контролировать остатки, комплектовать заказы и отмечать их отгрузку.\n\n"
                    f"**Основное меню:**\n"
                    f"- 📦 **Остатки** — просмотр текущего наличия всех материалов и готовой продукции на складе, включая панели, пленку, стыки и клей\n"
                    f"- 📦 **Мои заказы** — просмотр заказов от менеджеров, которые нужно укомплектовать и отгрузить\n\n"
                    f"При обработке заказа вы сможете проверить наличие всех необходимых материалов и подтвердить отгрузку.\n"
                    f"Для возврата в главное меню из любого раздела используйте кнопку ◀️ **Назад**",
                    reply_markup=keyboard
                )
        else:
            logging.info(f"Existing user found: {user.telegram_id}")
            # Проверяем, является ли пользователь админом и обновляем роль при необходимости
            if telegram_id == admin_id and user.role != UserRole.SUPER_ADMIN:
                user.role = UserRole.SUPER_ADMIN
                db.commit()
                logging.info(f"Updated user role to SUPER_ADMIN for admin user")
            
            # Обновляем username пользователя, если он изменился
            if user.username != username and username != "unknown":
                user.username = username
                db.commit()
                logging.info(f"Updated username to {username}")
            
            # Устанавливаем начальное состояние меню
            main_menu_state = MenuState.SUPER_ADMIN_MAIN if user.role == UserRole.SUPER_ADMIN else \
                            MenuState.SALES_MAIN if user.role == UserRole.SALES_MANAGER else \
                            MenuState.WAREHOUSE_MAIN if user.role == UserRole.WAREHOUSE else \
                            MenuState.PRODUCTION_MAIN if user.role == UserRole.PRODUCTION else \
                            None
            
            # Если у пользователя нет роли, не устанавливаем состояние
            if main_menu_state:
                await state.set_state(main_menu_state)
            
            # Создаем клавиатуру в зависимости от роли или убираем её для роли NONE
            keyboard = get_role_keyboard(user.role) if user.role != UserRole.NONE else ReplyKeyboardRemove()
            
            if user.role == UserRole.NONE:
                await message.answer(
                    "👋 С возвращением в бот управления складом!\n\n"
                    "⏳ *Ожидание роли*\n\n"
                    "Ваша учетная запись зарегистрирована, но роль пока не назначена. "
                    "Пожалуйста, дождитесь, когда администратор назначит вам роль для доступа к системе."
                )
            elif user.role == UserRole.SUPER_ADMIN:
                await message.answer(
                    f"👋 С возвращением в бот управления складом!\n\n"
                    f"👑 *Супер-администратор*\n\n"
                    f"Вы имеете полный доступ ко всем функциям системы и можете управлять пользователями, просматривать отчеты и работать с любыми ролями.\n\n"
                    f"**Основное меню:**\n"
                    f"- 👥 **Управление пользователями** — назначение ролей, просмотр списка пользователей, удаление пользователей, сброс ролей\n"
                    f"- 📊 **Отчеты и статистика** — просмотр данных о запасах, продажах и производстве\n"
                    f"- 📦 **Управление складом** — проверка остатков, работа с заказами и материалами\n"
                    f"- 🏭 **Управление производством** — контроль производственных процессов, работа с заказами\n\n"
                    f"**Эмуляция ролей:**\n"
                    f"- 💼 **Менеджер по продажам** — временное переключение для работы от имени менеджера\n"
                    f"- 🏭 **Производство** — временное переключение для работы от имени производства\n"
                    f"- 📦 **Склад** — временное переключение для работы от имени склада\n\n"
                    f"При работе в других ролях у вас всегда будет кнопка 🔙 **Назад в админку** для возврата в меню администратора",
                    reply_markup=keyboard
                )
            elif user.role == UserRole.SALES_MANAGER:
                await message.answer(
                    f"👋 С возвращением в бот управления складом!\n\n"
                    f"💼 *Менеджер по продажам*\n\n"
                    f"Ваша задача — создавать заказы для клиентов, проверять наличие товаров на складе и оформлять заказы на производство новой продукции.\n\n"
                    f"**Основное меню:**\n"
                    f"- 📝 **Составить заказ** — создание нового заказа для клиента с выбором цвета пленки, количества панелей и дополнительных материалов\n"
                    f"- 📦 **Количество готовой продукции** — проверка наличия готовых панелей по цветам для оформления заказа клиенту\n"
                    f"- 📝 **Заказать производство** — оформление запроса на изготовление новых панелей нужного цвета и количества\n"
                    f"- 📋 **Мои заказы** — просмотр списка ваших заказов с информацией о статусе и деталях\n\n"
                    f"Для возврата в главное меню из любого раздела используйте кнопку ◀️ **Назад**",
                    reply_markup=keyboard
                )
            elif user.role == UserRole.PRODUCTION:
                await message.answer(
                    f"👋 С возвращением в бот управления складом!\n\n"
                    f"🏭 *Производство*\n\n"
                    f"Ваша задача — регистрировать поступление материалов, производить панели и учитывать брак в процессе работы.\n\n"
                    f"**Основное меню:**\n"
                    f"- 📥 **Приход сырья** — добавление в систему новых материалов (панелей, пленки, стыков, клея) с указанием количества и параметров\n"
                    f"- 🛠 **Производство** — регистрация изготовления новых панелей с указанием использованных материалов\n"
                    f"- 🚫 **Брак** — учет бракованных материалов и готовой продукции с указанием типа и количества\n"
                    f"- 📋 **Заказы на производство** — просмотр и выполнение заказов от менеджеров на изготовление панелей определенного цвета\n"
                    f"- 📦 **Мои заказы** — просмотр активных и завершенных заказов производства\n\n"
                    f"Для возврата в главное меню из любого раздела используйте кнопку ◀️ **Назад**",
                    reply_markup=keyboard
                )
            elif user.role == UserRole.WAREHOUSE:
                await message.answer(
                    f"👋 С возвращением в бот управления складом!\n\n"
                    f"📦 *Склад*\n\n"
                    f"Ваша задача — контролировать остатки, комплектовать заказы и отмечать их отгрузку.\n\n"
                    f"**Основное меню:**\n"
                    f"- 📦 **Остатки** — просмотр текущего наличия всех материалов и готовой продукции на складе, включая панели, пленку, стыки и клей\n"
                    f"- 📦 **Мои заказы** — просмотр заказов от менеджеров, которые нужно укомплектовать и отгрузить\n\n"
                    f"При обработке заказа вы сможете проверить наличие всех необходимых материалов и подтвердить отгрузку.\n"
                    f"Для возврата в главное меню из любого раздела используйте кнопку ◀️ **Назад**",
                    reply_markup=keyboard
                )
    except Exception as e:
        logging.error(f"Error in cmd_start: {str(e)}", exc_info=True)
        await message.answer("Произошла ошибка при регистрации. Пожалуйста, попробуйте позже или обратитесь к администратору.")

@dp.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext):
    db = next(get_db())
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if not user:
        await message.answer("Пожалуйста, сначала используйте команду /start для регистрации в системе.")
        return
    
    # Обновим текущее состояние меню в соответствии с ролью
    main_menu_state = MenuState.SUPER_ADMIN_MAIN if user.role == UserRole.SUPER_ADMIN else \
                       MenuState.SALES_MAIN if user.role == UserRole.SALES_MANAGER else \
                       MenuState.WAREHOUSE_MAIN if user.role == UserRole.WAREHOUSE else \
                       MenuState.PRODUCTION_MAIN
    await state.set_state(main_menu_state)
    
    commands = "Доступные команды:\n\n"
    
    if user.role == UserRole.SUPER_ADMIN:
        commands += "🔑 Команды супер-администратора:\n"
        commands += "/users - Управление пользователями\n"
        commands += "/assign_role - Назначить роль пользователю\n"
        commands += "/report - Создание отчетов\n\n"
        
        commands += "🏭 Команды производства:\n"
        commands += "📥 Приход сырья - Запись прихода материалов\n"
        commands += "🛠 Производство - Запись производства\n\n"
        
        commands += "💼 Команды менеджера:\n"
        commands += "📝 Составить заказ - Создание заказа на продажу\n"
        commands += "📊 Склад - Просмотр остатков\n\n"
        
        commands += "📦 Команды склада:\n"
        commands += "/stock - Просмотр состояния склада\n"
        commands += "/confirm_order - Подтверждение заказов\n"
        commands += "/income_materials - Приход материалов\n\n"
    
    elif user.role == UserRole.PRODUCTION:
        commands += "Команды производства:\n"
        commands += "📥 Приход сырья - Запись прихода материалов\n"
        commands += "🛠 Производство - Запись производства\n\n"
    
    elif user.role == UserRole.SALES_MANAGER:
        commands += "Команды менеджера:\n"
        commands += "📝 Составить заказ - Создание заказа на продажу\n"
        commands += "📊 Склад - Просмотр остатков\n\n"
    
    elif user.role == UserRole.WAREHOUSE:
        commands += "Команды склада:\n"
        commands += "/stock - Просмотр состояния склада\n"
        commands += "/confirm_order - Подтверждение заказов\n"
        commands += "/income_materials - Приход материалов\n\n"
    
    await message.answer(commands, reply_markup=get_role_keyboard(user.role))

@dp.message(F.text == "📝 Составить заказ")
async def button_order(message: Message, state: FSMContext):
    await handle_create_order(message, state)

@dp.message(F.text == "📦 Количество готовой продукции")
async def button_stock(message: Message, state: FSMContext):
    await handle_stock(message, state)

@dp.message(F.text == "👥 Пользователи")
async def button_users(message: Message, state: FSMContext):
    await cmd_users(message, state)

@dp.message(F.text == "📊 Отчеты")
async def button_reports(message: Message, state: FSMContext):
    await cmd_report(message, state)

@dp.message(F.text == "📦 Остатки")
async def button_warehouse_stock(message: Message, state: FSMContext):
    await state.set_state(MenuState.WAREHOUSE_STOCK)
    await cmd_stock(message, state)

@dp.message(F.text == "📦 Мои заказы")
async def button_my_orders(message: Message, state: FSMContext):
    await state.set_state(MenuState.WAREHOUSE_ORDERS)
    await cmd_confirm_order(message, state)

@dp.message(F.text == "📥 Приход сырья")
async def button_income_materials(message: Message, state: FSMContext):
    await state.set_state(MenuState.PRODUCTION_MATERIALS)
    await production.handle_materials_income(message, state)

@dp.message(F.text == "🛠 Производство")
async def button_production(message: Message, state: FSMContext):
    await state.set_state(MenuState.PRODUCTION_PROCESS)
    await production.handle_production(message, state)

@dp.message(F.text == "🚫 Брак")
async def button_defect(message: Message, state: FSMContext):
    await state.set_state(MenuState.PRODUCTION_DEFECT)
    await production.handle_defect(message, state)

@dp.message(F.text == "📋 Заказы на производство")
async def button_production_orders(message: Message, state: FSMContext):
    await state.set_state(MenuState.PRODUCTION_ORDERS)
    await production.handle_production_orders(message, state)

@dp.message(F.text == "📦 Склад")
async def button_warehouse(message: Message, state: FSMContext):
    await state.set_state(MenuState.WAREHOUSE_STOCK)
    await cmd_stock(message, state)

@dp.message(F.text == "💼 Продажи")
async def button_sales(message: Message, state: FSMContext):
    await handle_stock(message, state)

@dp.message(F.text.in_({"👑 Супер-администратор", "💼 Менеджер по продажам", "🏭 Производство", "📦 Склад"}))
async def button_role_selection(message: Message, state: FSMContext):
    await admin.process_role(message, state)

@dp.message(F.text == "👥 Управление пользователями")
async def button_user_management(message: Message, state: FSMContext):
    await super_admin.handle_user_management(message, state)

@dp.message(F.text == "📊 Отчеты и статистика")
async def button_reports_and_stats(message: Message, state: FSMContext):
    await super_admin.handle_reports(message, state)

@dp.message(F.text == "📦 Управление складом")
async def button_warehouse_management(message: Message, state: FSMContext):
    await super_admin.handle_warehouse_management(message, state)

@dp.message(F.text == "🏭 Управление производством")
async def button_production_management(message: Message, state: FSMContext):
    await super_admin.handle_production_management(message, state)

@dp.message(F.text == "⚙️ Настройки системы")
async def button_system_settings(message: Message, state: FSMContext):
    await super_admin.handle_system_settings(message, state)

@dp.message(F.text == "📝 Заказать производство")
async def button_order_production(message: Message, state: FSMContext):
    await sales.handle_production_order(message, state)

@dp.message(F.text == "📦 Заказать на склад")
async def button_order_warehouse(message: Message, state: FSMContext):
    await handle_warehouse_order(message, state)

@dp.message(F.text == "🏭 Роль производства")
async def button_production_role(message: Message, state: FSMContext):
    await super_admin.handle_production_role(message, state)

@dp.message(F.text == "📦 Роль склада")
async def button_warehouse_role(message: Message, state: FSMContext):
    await super_admin.handle_warehouse_role(message, state)

@dp.message(F.text == "💼 Роль менеджера по продажам")
async def button_sales_role(message: Message, state: FSMContext):
    await super_admin.handle_sales_role(message, state)

@dp.message(F.text == "◀️ Назад")
async def button_back(message: Message, state: FSMContext):
    """Универсальный обработчик кнопки Назад"""
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            await message.answer("Пожалуйста, начните с команды /start")
            return
        
        current_role = user.role
        if current_role == UserRole.SALES_MANAGER:
            await sales.handle_back(message, state)
        elif current_role == UserRole.WAREHOUSE:
            await warehouse.handle_back(message, state)
        elif current_role == UserRole.PRODUCTION:
            await production.handle_back(message, state)
        elif current_role == UserRole.SUPER_ADMIN:
            await super_admin.handle_back(message, state)
        else:
            # Если роль не определена, сбрасываем состояние и выводим клавиатуру для роли
            main_menu = MenuState.SALES_MAIN
            await state.set_state(main_menu)
            await message.answer(
                "Выберите действие:",
                reply_markup=get_role_keyboard(current_role)
            )
    finally:
        db.close()

@dp.message(F.text == "📦 Остатки материалов")
async def button_materials_report(message: Message, state: FSMContext):
    await super_admin.handle_materials_report(message, state)

@dp.message(F.text == "💰 Статистика продаж")
async def button_sales_report(message: Message, state: FSMContext):
    await super_admin.handle_sales_report(message, state)

@dp.message(F.text == "🏭 Статистика производства")
async def button_production_report(message: Message, state: FSMContext):
    await super_admin.handle_production_report(message, state)

@dp.message(F.text == "📝 История операций")
async def button_operations_history(message: Message, state: FSMContext):
    await super_admin.handle_operations_history(message, state)

@dp.message(F.text == "✅ Выполненные заказы")
async def button_completed_orders(message: Message, state: FSMContext):
    await super_admin.handle_completed_orders(message, state)

@dp.message(F.text == "📤 Заказы на отгрузку")
async def button_shipping_orders(message: Message, state: FSMContext):
    await super_admin.handle_shipping_orders(message, state)

# Основная функция запуска бота
async def main():
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    # Создание таблиц, если они не существуют
    Base.metadata.create_all(engine)
    
    # Создание дефолтного пользователя-админа
    create_default_user_if_not_exists()
    
    # Запускаем Flask-сервер в отдельном потоке, если мы на Heroku
    if os.getenv("HEROKU", "0") == "1":
        flask_thread = threading.Thread(target=run_flask)
        flask_thread.daemon = True
        flask_thread.start()
        logging.info("Запущен веб-сервер Flask для Heroku")
    
    # Запускаем бота
    asyncio.run(main()) 