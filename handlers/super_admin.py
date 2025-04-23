from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from models import User, UserRole, Operation, Order, CompletedOrder, Film, Joint, Glue, ProductionOrder, OrderStatus, UserSource, Role, Panel, FinishedProduct, OperationType, JointType
from database import get_db
import json
from datetime import datetime, timedelta
from navigation import MenuState, get_menu_keyboard, go_back
import logging
import re
from handlers.warehouse import handle_stock

router = Router()

class SuperAdminStates(StatesGroup):
    waiting_for_report_type = State()
    waiting_for_backup = State()
    waiting_for_notification_settings = State()
    waiting_for_new_user_id = State()
    waiting_for_target_user_id = State()
    waiting_for_role = State()
    waiting_for_film_code = State()
    waiting_for_film_quantity = State()
    waiting_for_joint_type = State()
    waiting_for_joint_color = State()
    waiting_for_joint_quantity = State()
    waiting_for_glue_quantity = State()
    waiting_for_user_to_reset = State()
    waiting_for_user_to_delete = State()

def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Возвращает главную клавиатуру супер-админа"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Управление пользователями")],
            [KeyboardButton(text="📊 Отчеты и статистика")],
            [KeyboardButton(text="⚙️ Настройки системы")],
            [KeyboardButton(text="💼 Роль продажника")],
            [KeyboardButton(text="📦 Роль складовщика")],
            [KeyboardButton(text="🏭 Роль производства")]
        ],
        resize_keyboard=True
    )

@router.message(F.text == "👥 Управление пользователями")
async def handle_user_management(message: Message, state: FSMContext):
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or user.role != UserRole.SUPER_ADMIN:
            await message.answer("У вас нет прав для выполнения этой команды.")
            return
        
        await state.set_state(MenuState.SUPER_ADMIN_USERS)
        await message.answer(
            "Выберите действие:",
            reply_markup=get_menu_keyboard(MenuState.SUPER_ADMIN_USERS)
        )
    finally:
        db.close()

@router.message(F.text == "📊 Отчеты и статистика")
async def handle_reports(message: Message, state: FSMContext):
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or user.role != UserRole.SUPER_ADMIN:
            await message.answer("У вас нет прав для выполнения этой команды.")
            return
        
        await state.set_state(MenuState.SUPER_ADMIN_REPORTS)
        await message.answer(
            "Выберите тип отчета:",
            reply_markup=get_menu_keyboard(MenuState.SUPER_ADMIN_REPORTS)
        )
    finally:
        db.close()

@router.message(F.text == "📦 Роль склада")
async def handle_warehouse_role(message: Message, state: FSMContext):
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or user.role != UserRole.SUPER_ADMIN:
            await message.answer("У вас нет прав для выполнения этой команды.")
            return
        
        # Сохраняем информацию, что это супер-админ в контексте другой роли
        await state.update_data(is_admin_context=True)
        await state.set_state(MenuState.WAREHOUSE_MAIN)
        await message.answer(
            "Переключено на роль склада. Доступные функции:",
            reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN, is_admin_context=True)
        )
    finally:
        db.close()

@router.message(F.text == "🏭 Управление производством")
async def handle_production_management(message: Message, state: FSMContext):
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or user.role != UserRole.SUPER_ADMIN:
            await message.answer("У вас нет прав для выполнения этой команды.")
            return
        
        await state.set_state(MenuState.SUPER_ADMIN_PRODUCTION)
        await message.answer(
            "Управление производством:",
            reply_markup=get_menu_keyboard(MenuState.SUPER_ADMIN_PRODUCTION)
        )
    finally:
        db.close()

@router.message(F.text == "⚙️ Настройки системы")
async def handle_system_settings(message: Message, state: FSMContext):
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or user.role != UserRole.SUPER_ADMIN:
            await message.answer("У вас нет прав для выполнения этой команды.")
            return
        
        await state.set_state(MenuState.SUPER_ADMIN_SETTINGS)
        await message.answer(
            "Настройки системы:",
            reply_markup=get_menu_keyboard(MenuState.SUPER_ADMIN_SETTINGS)
        )
    finally:
        db.close()

@router.message(F.text == "💼 Роль менеджера по продажам")
async def handle_sales_role(message: Message, state: FSMContext):
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or user.role != UserRole.SUPER_ADMIN:
            await message.answer("У вас нет прав для выполнения этой команды.")
            return
        
        # Сохраняем информацию, что это супер-админ в контексте другой роли
        await state.update_data(is_admin_context=True)
        await state.set_state(MenuState.SALES_MAIN)
        await message.answer(
            "Переключено на роль менеджера по продажам. Доступные функции:",
            reply_markup=get_menu_keyboard(MenuState.SALES_MAIN, is_admin_context=True)
        )
    finally:
        db.close()

@router.message(F.text == "🏭 Роль производства")
async def handle_production_role(message: Message, state: FSMContext):
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or user.role != UserRole.SUPER_ADMIN:
            await message.answer("У вас нет прав для выполнения этой команды.")
            return
        
        # Сохраняем информацию, что это супер-админ в контексте другой роли
        await state.update_data(is_admin_context=True)
        await state.set_state(MenuState.PRODUCTION_MAIN)
        await message.answer(
            "Переключено на роль производства. Доступные функции:",
            reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MAIN, is_admin_context=True)
        )
    finally:
        db.close()

@router.message(F.text == "◀️ Назад")
async def handle_back(message: Message, state: FSMContext):
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            await message.answer("Пожалуйста, начните с команды /start")
            return
        
        next_menu, keyboard = await go_back(state, user.role)
        await state.set_state(next_menu)
        await message.answer(
            "Выберите действие:",
            reply_markup=keyboard
        )
    finally:
        db.close()

# Обработчики отчетов
@router.message(F.text == "📦 Остатки материалов")
async def handle_materials_report(message: Message, state: FSMContext):
    # Перенаправляем запрос к новой функции категорий инвентаря
    await handle_stock(message, state)

@router.message(F.text == "💰 Статистика продаж")
async def handle_sales_report(message: Message, state: FSMContext):
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or user.role != UserRole.SUPER_ADMIN:
            await message.answer("У вас нет прав для выполнения этой команды.")
            return
        
        # Получаем статистику за последние 30 дней
        thirty_days_ago = datetime.now() - timedelta(days=30)
        completed_orders = db.query(CompletedOrder).filter(
            CompletedOrder.completed_at >= thirty_days_ago
        ).all()
        
        report = "📊 Статистика продаж за 30 дней:\n\n"
        
        total_panels = sum(order.panel_quantity for order in completed_orders)
        total_joints = sum(order.joint_quantity for order in completed_orders)
        total_glue = sum(order.glue_quantity for order in completed_orders)
        
        report += f"Всего выполнено заказов: {len(completed_orders)}\n"
        report += f"Отгружено панелей: {total_panels} шт.\n"
        report += f"Отгружено стыков: {total_joints} шт.\n"
        report += f"Отгружено клея: {total_glue} шт.\n"
        
        await message.answer(report, reply_markup=get_menu_keyboard(MenuState.SUPER_ADMIN_REPORTS))
    finally:
        db.close()

@router.message(F.text == "🏭 Статистика производства")
async def handle_production_report(message: Message, state: FSMContext):
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or user.role != UserRole.SUPER_ADMIN:
            await message.answer("У вас нет прав для выполнения этой команды.")
            return
        
        # Получаем статистику за последние 30 дней
        thirty_days_ago = datetime.now() - timedelta(days=30)
        production_orders = db.query(ProductionOrder).filter(
            ProductionOrder.created_at >= thirty_days_ago
        ).all()
        
        report = "🏭 Статистика производства за 30 дней:\n\n"
        
        total_panels = sum(order.panel_quantity for order in production_orders)
        completed_orders = [order for order in production_orders if order.status == "completed"]
        completed_panels = sum(order.panel_quantity for order in completed_orders)
        
        report += f"Всего заказов на производство: {len(production_orders)}\n"
        report += f"Выполнено заказов: {len(completed_orders)}\n"
        report += f"Заказано панелей: {total_panels} шт.\n"
        report += f"Произведено панелей: {completed_panels} шт.\n"
        
        await message.answer(report, reply_markup=get_menu_keyboard(MenuState.SUPER_ADMIN_REPORTS))
    finally:
        db.close()

@router.message(F.text == "📝 История операций")
async def handle_operations_history(message: Message, state: FSMContext):
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or user.role != UserRole.SUPER_ADMIN:
            await message.answer("У вас нет прав для выполнения этой команды.")
            return
        
        # Получаем последние 20 операций
        operations = db.query(Operation).order_by(
            Operation.timestamp.desc()
        ).limit(20).all()
        
        report = "📝 История операций:\n\n"
        
        for op in operations:
            performer = db.query(User).filter(User.id == op.user_id).first()
            
            report += (
                f"Операция #{op.id}\n"
                f"📅 {op.timestamp.strftime('%d.%m.%Y %H:%M')}\n"
                f"👤 Пользователь: {performer.username if performer else 'Неизвестный'}\n"
                f"🔄 Тип: {op.operation_type}\n"
                f"📊 Количество: {op.quantity}\n"
                "-------------------\n"
            )
        
        await message.answer(report, reply_markup=get_menu_keyboard(MenuState.SUPER_ADMIN_REPORTS))
    finally:
        db.close()

@router.message(F.text == "✅ Выполненные заказы")
async def handle_completed_orders(message: Message, state: FSMContext):
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or user.role != UserRole.SUPER_ADMIN:
            await message.answer("У вас нет прав для выполнения этой команды.")
            return
        
        # Получаем последние 10 выполненных заказов
        completed_orders = db.query(CompletedOrder).order_by(
            CompletedOrder.completed_at.desc()
        ).limit(10).all()
        
        report = "✅ Последние выполненные заказы:\n\n"
        
        for order in completed_orders:
            manager = db.query(User).filter(User.id == order.manager_id).first()
            warehouse = db.query(User).filter(User.id == order.warehouse_user_id).first()
            
            installation_status = "✅ Да" if order.installation_required else "❌ Нет"
            
            report += (
                f"Заказ #{order.order_id}\n"
                f"📅 {order.completed_at.strftime('%d.%m.%Y %H:%M')}\n"
                f"👤 Менеджер: {manager.username if manager else 'Неизвестный'}\n"
                f"📦 Склад: {warehouse.username if warehouse else 'Неизвестный'}\n"
                f"🎨 Пленка: {order.film_code}\n"
                f"📊 Панели: {order.panel_quantity} шт.\n"
                f"⚙️ Стыки: {order.joint_color} - {order.joint_quantity} шт.\n"
                f"🧪 Клей: {order.glue_quantity} шт.\n"
                f"🔧 Монтаж: {installation_status}\n"
                "-------------------\n"
            )
        
        await message.answer(report, reply_markup=get_menu_keyboard(MenuState.SUPER_ADMIN_REPORTS))
    finally:
        db.close()

@router.message(F.text == "📋 Заказы на производство")
async def handle_production_orders(message: Message, state: FSMContext):
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or user.role != UserRole.SUPER_ADMIN:
            await message.answer("У вас нет прав для выполнения этой команды.")
            return
        
        # Получаем последние 10 заказов на производство
        production_orders = db.query(ProductionOrder).order_by(
            ProductionOrder.created_at.desc()
        ).limit(10).all()
        
        report = "📋 Последние заказы на производство:\n\n"
        
        for order in production_orders:
            manager = db.query(User).filter(User.id == order.manager_id).first()
            
            report += (
                f"Заказ #{order.id}\n"
                f"📅 {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                f"👤 Менеджер: {manager.username if manager else 'Неизвестный'}\n"
                f"🎨 Пленка: {order.film_color}\n"
                f"📊 Панели: {order.panel_quantity} шт.\n"
                f"📦 Статус: {order.status}\n"
                "-------------------\n"
            )
        
        await message.answer(report, reply_markup=get_menu_keyboard(MenuState.SUPER_ADMIN_REPORTS))
    finally:
        db.close()

@router.message(F.text == "📤 Заказы на отгрузку")
async def handle_shipping_orders(message: Message, state: FSMContext):
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or user.role != UserRole.SUPER_ADMIN:
            await message.answer("У вас нет прав для выполнения этой команды.")
            return
        
        # Получаем новые заказы на отгрузку
        orders = db.query(Order).filter(Order.status == OrderStatus.NEW).all()
        
        report = "📤 Заказы на отгрузку:\n\n"
        
        for order in orders:
            manager = db.query(User).filter(User.id == order.manager_id).first()
            
            installation_status = "✅ Да" if order.installation_required else "❌ Нет"
            
            report += (
                f"Заказ #{order.id}\n"
                f"📅 {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                f"👤 Менеджер: {manager.username if manager else 'Неизвестный'}\n"
                f"🎨 Пленка: {order.film_code}\n"
                f"📊 Панели: {order.panel_quantity} шт.\n"
                f"⚙️ Стыки: {order.joint_color} - {order.joint_quantity} шт.\n"
                f"🧪 Клей: {order.glue_quantity} шт.\n"
                f"🔧 Монтаж: {installation_status}\n"
                f"📱 Телефон: {order.customer_phone}\n"
                f"📍 Адрес: {order.delivery_address}\n"
                "-------------------\n"
            )
        
        await message.answer(report, reply_markup=get_menu_keyboard(MenuState.SUPER_ADMIN_REPORTS))
    finally:
        db.close()

# Обработчики управления пользователями
@router.message(F.text == "🔄 Сбросить роль пользователя")
async def handle_reset_role(message: Message, state: FSMContext):
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if user and user.role == UserRole.SUPER_ADMIN:
            # Получаем список всех пользователей
            users = db.query(User).all()
            
            if not users:
                await message.answer("В системе нет пользователей.")
                return
                
            # Создаем клавиатуру с кнопками для каждого пользователя
            keyboard = []
            for u in users:
                # Пропускаем суперадминов и пользователей без роли
                if u.role != UserRole.SUPER_ADMIN and u.role != UserRole.NONE:
                    # Добавляем имя пользователя, роль и ID на кнопку
                    keyboard.append([KeyboardButton(text=f"{u.username} - {u.role.value} (ID: {u.telegram_id})")])
                
            # Добавляем кнопку "Назад"
            keyboard.append([KeyboardButton(text="◀️ Назад")])
                
            await message.answer(
                "Выберите пользователя, роль которого хотите сбросить:",
                reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
            )
            await state.set_state(SuperAdminStates.waiting_for_user_to_reset)
    finally:
        db.close()

@router.message(SuperAdminStates.waiting_for_user_to_reset)
async def process_reset_role(message: Message, state: FSMContext):
    db = next(get_db())
    try:
        admin = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if admin and admin.role == UserRole.SUPER_ADMIN:
            if message.text == "◀️ Назад":
                await state.clear()
                await message.answer(
                    "Операция отменена.",
                    reply_markup=get_menu_keyboard(MenuState.SUPER_ADMIN_USERS)
                )
                return
                
            # Извлекаем ID пользователя из текста кнопки (формат: "имя - роль (ID: числовой_id)")
            try:
                # Находим ID из текста кнопки
                match = re.search(r'ID: (\d+)', message.text)
                if match:
                    target_user_id = int(match.group(1))
                else:
                    await message.answer("Не удалось определить ID пользователя. Пожалуйста, попробуйте еще раз.")
                    return
            except Exception:
                await message.answer("Произошла ошибка при определении ID пользователя. Пожалуйста, попробуйте еще раз.")
                return

            # Проверяем, существует ли пользователь
            target_user = db.query(User).filter(User.telegram_id == target_user_id).first()
            if not target_user:
                await message.answer("Пользователь не найден в системе.")
                await state.clear()
                return
            
            # Запрещаем сбрасывать роль супер-админа
            if target_user.role == UserRole.SUPER_ADMIN:
                await message.answer("⚠️ Невозможно сбросить роль супер-администратора.")
                await state.clear()
                return

            # Сбрасываем роль пользователя на NONE
            target_user.role = UserRole.NONE
            db.commit()

            # Отправляем уведомление пользователю о сбросе роли
            try:
                await message.bot.send_message(
                    chat_id=target_user.telegram_id,
                    text="Ваша роль была сброшена администратором. Ожидайте назначения новой роли.",
                    reply_markup=ReplyKeyboardRemove()
                )
            except Exception as e:
                logging.error(f"Не удалось отправить уведомление пользователю {target_user.telegram_id}: {str(e)}")

            # Возвращаемся в меню управления пользователями
            await message.answer(
                f"Роль пользователя {target_user.username} успешно сброшена.",
                reply_markup=get_menu_keyboard(MenuState.SUPER_ADMIN_USERS)
            )
            await state.clear()
    finally:
        db.close()

@router.message(F.text == "📋 Список пользователей")
async def handle_list_users(message: Message, state: FSMContext):
    """Обработчик для вывода списка пользователей с пагинацией"""
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if user and user.role == UserRole.SUPER_ADMIN:
            # Получаем всех пользователей
            users = db.query(User).all()
            
            # Сохраняем информацию о странице в состоянии
            await state.update_data(user_list_page=1, users_per_page=10, total_users=len(users))
            
            await display_user_page(message, state, users, 1)
    finally:
        db.close()

async def display_user_page(message: Message, state: FSMContext, users, page: int):
    """Отображает страницу списка пользователей"""
    # Получаем данные из состояния
    data = await state.get_data()
    users_per_page = data.get('users_per_page', 10)
    
    # Вычисляем индексы для текущей страницы
    start_idx = (page - 1) * users_per_page
    end_idx = min(start_idx + users_per_page, len(users))
    
    # Формируем сообщение со списком пользователей для текущей страницы
    response = f"📋 Список пользователей (страница {page}):\n\n"
    
    for i in range(start_idx, end_idx):
        user = users[i]
        response += f"ID: {user.telegram_id}\n"
        response += f"Имя: {user.username}\n"
        response += f"Роль: {user.role.value}\n"
        response += f"Дата регистрации: {user.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        response += "---------------------\n"
    
    # Добавляем навигационные кнопки при необходимости
    keyboard = []
    
    if page > 1:
        keyboard.append([KeyboardButton(text="⬅️ Предыдущая страница")])
    
    if end_idx < len(users):
        keyboard.append([KeyboardButton(text="➡️ Следующая страница")])
    
    keyboard.append([KeyboardButton(text="◀️ Назад")])
    
    await message.answer(
        response,
        reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    )

@router.message(F.text == "⬅️ Предыдущая страница")
async def handle_prev_page(message: Message, state: FSMContext):
    """Обработчик для перехода на предыдущую страницу"""
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if user and user.role == UserRole.SUPER_ADMIN:
            # Получаем данные пагинации из состояния
            data = await state.get_data()
            current_page = data.get('user_list_page', 1)
            
            if current_page > 1:
                # Получаем всех пользователей и отображаем предыдущую страницу
                users = db.query(User).all()
                await state.update_data(user_list_page=current_page - 1)
                await display_user_page(message, state, users, current_page - 1)
    finally:
        db.close()

@router.message(F.text == "➡️ Следующая страница")
async def handle_next_page(message: Message, state: FSMContext):
    """Обработчик для перехода на следующую страницу"""
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if user and user.role == UserRole.SUPER_ADMIN:
            # Получаем данные пагинации из состояния
            data = await state.get_data()
            current_page = data.get('user_list_page', 1)
            users_per_page = data.get('users_per_page', 10)
            total_users = data.get('total_users', 0)
            
            # Проверяем, что есть следующая страница
            if (current_page * users_per_page) < total_users:
                # Получаем всех пользователей и отображаем следующую страницу
                users = db.query(User).all()
                await state.update_data(user_list_page=current_page + 1)
                await display_user_page(message, state, users, current_page + 1)
    finally:
        db.close()

@router.message(F.text == "👤 Назначить роль")
async def handle_assign_role(message: Message, state: FSMContext):
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if user and user.role == UserRole.SUPER_ADMIN:
            # Получаем список всех пользователей
            users = db.query(User).all()
            
            if not users:
                await message.answer("В системе нет пользователей.")
                return
                
            # Создаем клавиатуру с кнопками для каждого пользователя
            keyboard = []
            for u in users:
                # Добавляем имя пользователя и ID на кнопку
                keyboard.append([KeyboardButton(text=f"{u.username} (ID: {u.telegram_id})")])
                
            # Добавляем кнопку "Назад"
            keyboard.append([KeyboardButton(text="◀️ Назад")])
                
            await message.answer(
                "Выберите пользователя, которому хотите назначить роль:",
                reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
            )
            await state.set_state(SuperAdminStates.waiting_for_target_user_id)
    finally:
        db.close()

@router.message(SuperAdminStates.waiting_for_target_user_id)
async def process_role_assignment(message: Message, state: FSMContext):
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if user and user.role == UserRole.SUPER_ADMIN:
            if message.text == "◀️ Назад":
                await state.clear()
                await message.answer(
                    "Операция отменена.",
                    reply_markup=get_menu_keyboard(MenuState.SUPER_ADMIN_USERS)
                )
                return
                
            # Извлекаем ID пользователя из текста кнопки (формат: "имя (ID: числовой_id)")
            try:
                # Находим ID из текста кнопки
                match = re.search(r'ID: (\d+)', message.text)
                if match:
                    target_user_id = int(match.group(1))
                else:
                    await message.answer("Не удалось определить ID пользователя. Пожалуйста, попробуйте еще раз.")
                    return
            except Exception:
                await message.answer("Произошла ошибка при определении ID пользователя. Пожалуйста, попробуйте еще раз.")
                return

            # Проверяем, существует ли пользователь
            target_user = db.query(User).filter(User.telegram_id == target_user_id).first()
            if not target_user:
                await message.answer("Пользователь не найден в системе.")
                await state.clear()
                return

            # Сохраняем ID пользователя в состоянии
            await state.update_data(target_user_id=target_user_id)

            # Создаем клавиатуру с ролями (кроме NONE)
            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text=role.value) for role in UserRole if role != UserRole.NONE],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )

            await state.set_state(SuperAdminStates.waiting_for_role)
            await message.answer(
                f"Выберите роль для пользователя {target_user.username}:",
                reply_markup=keyboard
            )
    finally:
        db.close()

@router.message(SuperAdminStates.waiting_for_role)
async def process_role_selection(message: Message, state: FSMContext):
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if user and user.role == UserRole.SUPER_ADMIN:
            if message.text == "◀️ Назад":
                await state.clear()
                await message.answer(
                    "Операция отменена.",
                    reply_markup=get_menu_keyboard(MenuState.SUPER_ADMIN_USERS)
                )
                return

            # Получаем сохраненный ID пользователя
            data = await state.get_data()
            target_user_id = data.get("target_user_id")

            # Находим выбранную роль
            selected_role = None
            for role in UserRole:
                if role.value == message.text:
                    selected_role = role
                    break

            if not selected_role:
                await message.answer("Пожалуйста, выберите роль из списка.")
                return

            # Обновляем роль пользователя
            target_user = db.query(User).filter(User.telegram_id == target_user_id).first()
            if target_user:
                target_user.role = selected_role
                db.commit()
                
                # Отправляем уведомление пользователю о назначении роли
                try:
                    # Определяем клавиатуру в зависимости от роли
                    user_keyboard = get_menu_keyboard(MenuState.SUPER_ADMIN_MAIN if selected_role == UserRole.SUPER_ADMIN else
                                                     MenuState.SALES_MAIN if selected_role == UserRole.SALES_MANAGER else
                                                     MenuState.WAREHOUSE_MAIN if selected_role == UserRole.WAREHOUSE else
                                                     MenuState.PRODUCTION_MAIN)
                    
                    await message.bot.send_message(
                        chat_id=target_user.telegram_id,
                        text=f"Вам назначена роль: {selected_role.value}.\nТеперь вы можете использовать функции бота.",
                        reply_markup=user_keyboard
                    )
                except Exception as e:
                    logging.error(f"Не удалось отправить уведомление пользователю {target_user.telegram_id}: {str(e)}")

                keyboard = ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text="👤 Назначить роль")],
                        [KeyboardButton(text="📋 Список пользователей")],
                        [KeyboardButton(text="🔄 Сбросить роль пользователя")],
                        [KeyboardButton(text="◀️ Назад")]
                    ],
                    resize_keyboard=True
                )
                await message.answer(
                    f"Роль пользователя {target_user.username} успешно обновлена на {selected_role.value}",
                    reply_markup=keyboard
                )
            else:
                await message.answer("Пользователь не найден в системе.")

            await state.clear()
    finally:
        db.close() 