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
    warehouse_callbacks,
)
from handlers.admin import cmd_users, cmd_report, cmd_assign_role
from handlers.sales import handle_warehouse_order, handle_stock, handle_create_order
from handlers.warehouse import cmd_stock, cmd_confirm_order, cmd_income_materials
from navigation import get_role_keyboard, MenuState, go_back, get_menu_keyboard, get_main_menu_state_for_role
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
dp.include_router(warehouse_callbacks.router)
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
                    "Пожалуйста, дождитесь, когда администратор назначит вам роль для доступа к системе.",
                    parse_mode="Markdown"
                )
            elif user.role == UserRole.SUPER_ADMIN:
                await message.answer(
                    f"👋 Добро пожаловать в бот управления складом!\n\n"
                    f"👑 *Супер-администратор*\n\n"
                    f"Вы имеете полный доступ ко всем функциям системы и можете управлять пользователями, просматривать отчеты и работать с любыми ролями.\n\n"
                    f"**Доступные функции:**\n\n"
                    f"👥 **Управление пользователями**\n"
                    f"• Назначение и изменение ролей пользователей\n"
                    f"• Просмотр списка всех пользователей\n"
                    f"• Удаление учетных записей\n\n"
                    f"📊 **Отчеты и статистика**\n"
                    f"• Просмотр актуальных данных о запасах на складе\n"
                    f"• Анализ продаж и производства\n"
                    f"• История операций в системе\n\n"
                    f"📦 **Управление складом**\n"
                    f"• Контроль остатков материалов\n"
                    f"• Управление заказами клиентов\n"
                    f"• Отслеживание отгрузок\n\n"
                    f"🏭 **Управление производством**\n"
                    f"• Создание и контроль заказов на производство\n"
                    f"• Учет брака и расхода материалов\n"
                    f"• Мониторинг производственных процессов\n\n"
                    f"**Эмуляция ролей:**\n"
                    f"Вы можете временно работать от имени любой роли для проверки функционала. Для возврата к меню администратора используйте кнопку 🔙 **Назад в админку**",
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            elif user.role == UserRole.SALES_MANAGER:
                await message.answer(
                    f"👋 Добро пожаловать в бот управления складом!\n\n"
                    f"💼 *Менеджер по продажам*\n\n"
                    f"В вашем распоряжении инструменты для работы с заказами клиентов и контроля доступности товаров.\n\n"
                    f"**Доступные функции:**\n\n"
                    f"📝 **Составить заказ**\n"
                    f"• Создание нового заказа для клиента\n"
                    f"• Выбор цвета и толщины панелей\n"
                    f"• Добавление стыков и клея в заказ\n"
                    f"• Указание контактных данных и адреса доставки\n\n"
                    f"📦 **Количество готовой продукции**\n"
                    f"• Проверка наличия товаров на складе\n"
                    f"• Просмотр всех материалов по категориям\n\n"
                    f"📝 **Заказать**\n"
                    f"• Создание заявки на производство новых панелей\n"
                    f"• Указание нужного цвета, толщины и количества\n\n"
                    f"📋 **Мои заказы**\n"
                    f"• Просмотр истории созданных заказов\n"
                    f"• Отслеживание статуса выполнения\n\n"
                    f"Для возврата в главное меню используйте кнопку ◀️ **Назад**",
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            elif user.role == UserRole.PRODUCTION:
                await message.answer(
                    f"👋 Добро пожаловать в бот управления складом!\n\n"
                    f"🏭 *Производство*\n\n"
                    f"Вы отвечаете за изготовление панелей и учет материалов в производственном процессе.\n\n"
                    f"**Доступные функции:**\n\n"
                    f"📥 **Приход сырья**\n"
                    f"• Регистрация поступления новых материалов\n"
                    f"• Добавление панелей, пленки, стыков и клея\n"
                    f"• Указание параметров и количества\n\n"
                    f"🛠 **Производство**\n"
                    f"• Учет изготовления панелей\n"
                    f"• Списание использованных материалов\n"
                    f"• Добавление готовой продукции на склад\n\n"
                    f"🚫 **Брак**\n"
                    f"• Регистрация бракованной продукции\n"
                    f"• Списание испорченных материалов\n"
                    f"• Учет причин брака\n\n"
                    f"📋 **Заказы на производство**\n"
                    f"• Просмотр новых заявок от менеджеров\n"
                    f"• Отметка о выполнении заказов\n\n"
                    f"📦 **Остатки**\n"
                    f"• Проверка наличия всех материалов\n"
                    f"• Контроль запасов для производства\n\n"
                    f"Для возврата в главное меню используйте кнопку ◀️ **Назад**",
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            elif user.role == UserRole.WAREHOUSE:
                await message.answer(
                    f"👋 Добро пожаловать в бот управления складом!\n\n"
                    f"📦 *Склад*\n\n"
                    f"Ваша задача — управление складскими запасами и обработка заказов клиентов.\n\n"
                    f"**Доступные функции:**\n\n"
                    f"📦 **Остатки**\n"
                    f"• Просмотр текущего наличия всех материалов\n"
                    f"• Контроль готовой продукции на складе\n"
                    f"• Отслеживание доступности сырья\n\n"
                    f"📦 **Мои заказы**\n"
                    f"• Просмотр активных заказов от менеджеров\n"
                    f"• Комплектация и подготовка к отгрузке\n"
                    f"• Отметка о выполнении заказов\n\n"
                    f"✅ **Завершенные заказы**\n"
                    f"• История отгруженных заказов\n"
                    f"• Информация о получателях и составе\n\n"
                    f"Для возврата в главное меню используйте кнопку ◀️ **Назад**",
                    reply_markup=keyboard,
                    parse_mode="Markdown"
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
                    "👋 Добро пожаловать в бот управления складом!\n\n"
                    "⏳ *Ожидание роли*\n\n"
                    "Ваша учетная запись уже зарегистрирована, но роль пока не назначена. "
                    "Пожалуйста, дождитесь, когда администратор назначит вам роль для доступа к системе.",
                    parse_mode="Markdown"
                )
            elif user.role == UserRole.SUPER_ADMIN:
                await message.answer(
                    f"👋 Добро пожаловать в бот управления складом!\n\n"
                    f"👑 *Супер-администратор*\n\n"
                    f"Вы имеете полный доступ ко всем функциям системы. Используйте меню для навигации.\n\n"
                    f"**Доступные функции:**\n"
                    f"• Управление пользователями и ролями\n"
                    f"• Просмотр отчетов и статистики\n"
                    f"• Полный доступ к функциям склада и производства",
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            elif user.role == UserRole.SALES_MANAGER:
                await message.answer(
                    f"👋 Добро пожаловать в бот управления складом!\n\n"
                    f"💼 *Менеджер по продажам*\n\n"
                    f"Используйте меню для создания заказов и проверки наличия товаров.\n\n"
                    f"**Доступные функции:**\n"
                    f"• Создание новых заказов для клиентов\n"
                    f"• Проверка доступности товаров\n"
                    f"• Оформление заявок на производство",
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            elif user.role == UserRole.PRODUCTION:
                await message.answer(
                    f"👋 Добро пожаловать в бот управления складом!\n\n"
                    f"🏭 *Производство*\n\n"
                    f"Используйте меню для регистрации производства и учета материалов.\n\n"
                    f"**Доступные функции:**\n"
                    f"• Регистрация прихода материалов\n"
                    f"• Учет производства панелей\n"
                    f"• Обработка заказов от менеджеров\n"
                    f"• Контроль брака и расхода",
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            elif user.role == UserRole.WAREHOUSE:
                await message.answer(
                    f"👋 Добро пожаловать в бот управления складом!\n\n"
                    f"📦 *Склад*\n\n"
                    f"Используйте меню для управления складом и обработки заказов.\n\n"
                    f"**Доступные функции:**\n"
                    f"• Контроль остатков всех материалов\n"
                    f"• Комплектация заказов клиентов\n"
                    f"• Отметка об отгрузке\n"
                    f"• Учет движения товаров",
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
    except Exception as e:
        logging.error(f"Error in start command: {e}", exc_info=True)
        await message.answer(
            "Произошла ошибка при регистрации. Пожалуйста, попробуйте позже или обратитесь к администратору.",
            parse_mode="Markdown"
        )
    finally:
        db.close()

@dp.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext):
    db = next(get_db())
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if not user:
        await message.answer("Пожалуйста, сначала используйте команду /start для регистрации в системе.", parse_mode="Markdown")
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
    
    await message.answer(commands, reply_markup=get_role_keyboard(user.role), parse_mode="Markdown")

@dp.message(F.text == "📝 Составить заказ")
async def button_order(message: Message, state: FSMContext):
    await handle_create_order(message, state)

@dp.message(F.text == "📦 Количество готовой продукции")
async def button_stock(message: Message, state: FSMContext):
    await sales.handle_stock(message, state)

@dp.message(F.text == "👥 Пользователи")
async def button_users(message: Message, state: FSMContext):
    await cmd_users(message, state)

@dp.message(F.text == "📊 Отчеты")
async def button_reports(message: Message, state: FSMContext):
    await cmd_report(message, state)

@dp.message(F.text == "📦 Остатки")
async def button_warehouse_stock(message: Message, state: FSMContext):
    await warehouse.handle_stock(message, state)

@dp.message(F.text == "📊 Остатки")
async def button_production_stock(message: Message, state: FSMContext):
    logging.info(f"Нажата кнопка 'Остатки' пользователем {message.from_user.id}")
    
    await warehouse.handle_stock(message, state)

@dp.message(F.text == "📦 Мои заказы")
async def button_my_orders(message: Message, state: FSMContext):
    await state.set_state(MenuState.WAREHOUSE_ORDERS)
    await cmd_confirm_order(message, state)

@dp.message(F.text == "✅ Завершенные заказы")
async def button_completed_orders_warehouse(message: Message, state: FSMContext):
    await state.set_state(MenuState.WAREHOUSE_COMPLETED_ORDERS)
    await warehouse.handle_completed_orders(message, state)

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
    logging.info(f"Нажата кнопка 'Заказы на производство' пользователем {message.from_user.id}")
    
    # Проверяем текущую роль пользователя
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        logging.info(f"Пользователь {message.from_user.id} имеет роль {user.role if user else 'None'}")
    finally:
        db.close()
    
    await state.set_state(MenuState.PRODUCTION_ORDERS)
    await production_orders.handle_my_orders(message, state)

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

@dp.message(F.text == "📝 Заказать")
async def button_order_production(message: Message, state: FSMContext):
    await production_orders.handle_production_order(message, state)

@dp.message(F.text == "📦 Заказать на склад")
async def button_order_warehouse(message: Message, state: FSMContext):
    await warehouse.handle_order_warehouse(message, state)

@dp.message(F.text == "🏭 Роль производства")
async def button_production_role(message: Message, state: FSMContext):
    await assign_role(message, state, UserRole.PRODUCTION, "производства", parse_mode="Markdown")

@dp.message(F.text == "📦 Роль склада")
async def button_warehouse_role(message: Message, state: FSMContext):
    await assign_role(message, state, UserRole.WAREHOUSE, "склада", parse_mode="Markdown")

@dp.message(F.text == "💼 Роль менеджера по продажам")
async def button_sales_role(message: Message, state: FSMContext):
    await assign_role(message, state, UserRole.SALES_MANAGER, "менеджера по продажам", parse_mode="Markdown")

@dp.message(F.text == "◀️ Назад")
async def button_back(message: Message, state: FSMContext):
    """Обработчик кнопки Назад для возврата в предыдущее меню."""
    # Определяем роль пользователя
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            await message.answer("Не удалось определить вашу роль. Пожалуйста, начните сначала с /start", parse_mode="Markdown")
            return
            
        current_state = await state.get_state()
        if not current_state:
            # Если текущее состояние не определено, возвращаемся в главное меню для роли
            main_menu_state = get_main_menu_state_for_role(user.role)
            await state.set_state(main_menu_state)
            await message.answer(
                "Вы вернулись в главное меню.",
                reply_markup=get_menu_keyboard(main_menu_state),
                parse_mode="Markdown"
            )
            return
            
        # Пытаемся получить состояние меню из MenuState
        try:
            menu_state = MenuState(current_state)
            # Используем функцию go_back с параметром роли
            next_menu, keyboard = await go_back(state, user.role)
            
            if next_menu:
                await state.set_state(next_menu)
                await message.answer("Вы вернулись в предыдущее меню.", reply_markup=keyboard, parse_mode="Markdown")
            else:
                # Если next_menu None, значит мы уже в главном меню или произошла ошибка
                main_menu_state = get_main_menu_state_for_role(user.role)
                await state.set_state(main_menu_state)
                await message.answer(
                    "Вы вернулись в главное меню.",
                    reply_markup=get_menu_keyboard(main_menu_state),
                    parse_mode="Markdown"
                )
                
        except ValueError:
            # Если текущее состояние не является MenuState, возвращаемся в главное меню роли
            main_menu_state = get_main_menu_state_for_role(user.role)
            await state.set_state(main_menu_state)
            await message.answer(
                "Вы вернулись в главное меню.",
                reply_markup=get_menu_keyboard(main_menu_state),
                parse_mode="Markdown"
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

# Function to create default admin user if not exists
def create_default_user_if_not_exists():
    try:
        admin_id = int(os.getenv("ADMIN_USER_ID", 0))
        if admin_id == 0:
            logging.warning("ADMIN_USER_ID is not set or is 0. Skip creating default admin user.")
            return
        
        db = next(get_db())
        try:
            # Check if admin user already exists
            user = db.query(User).filter(User.telegram_id == admin_id).first()
            if not user:
                # Create new admin user
                logging.info(f"Creating default admin user with ID {admin_id}")
                user = User(
                    telegram_id=admin_id,
                    username="admin",  # Will be updated when admin interacts with bot
                    role=UserRole.SUPER_ADMIN
                )
                db.add(user)
                db.commit()
                logging.info("Default admin user created successfully")
            else:
                # Ensure existing user has SUPER_ADMIN role
                if user.role != UserRole.SUPER_ADMIN:
                    user.role = UserRole.SUPER_ADMIN
                    db.commit()
                    logging.info(f"Updated user {admin_id} role to SUPER_ADMIN")
        finally:
            db.close()
    except Exception as e:
        logging.error(f"Error creating default admin user: {e}")

# Функция для назначения роли пользователю (для кнопок ролей)
async def assign_role(message: Message, state: FSMContext, role: UserRole, role_name: str, **kwargs):
    """Эмуляция роли для супер-администратора"""
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or user.role != UserRole.SUPER_ADMIN:
            await message.answer("У вас нет прав для эмуляции ролей.", **kwargs)
            return
            
        # Устанавливаем флаг контекста админа
        await state.update_data(is_admin_context=True)
        
        # Переключаемся на соответствующее главное меню роли
        main_menu_state = {
            UserRole.SUPER_ADMIN: MenuState.SUPER_ADMIN_MAIN,
            UserRole.SALES_MANAGER: MenuState.SALES_MAIN,
            UserRole.WAREHOUSE: MenuState.WAREHOUSE_MAIN,
            UserRole.PRODUCTION: MenuState.PRODUCTION_MAIN,
            UserRole.NONE: None,  # Для роли NONE нет главного меню
        }[role]
        
        await state.set_state(main_menu_state)
        
        # Получаем клавиатуру для выбранной роли с доп. кнопкой возврата в админку
        keyboard = get_menu_keyboard(main_menu_state, is_admin_context=True)
        
        await message.answer(
            f"✅ Вы временно переключились в режим {role_name}.\n"
            f"Для возврата в меню администратора используйте кнопку 🔙 Назад в админку",
            reply_markup=keyboard,
            **kwargs
        )
    finally:
        db.close()

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