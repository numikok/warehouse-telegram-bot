from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from models import User, UserRole, ProductionOrder, Film, Panel, FinishedProduct, Operation, OrderStatus
from database import get_db
import logging
from datetime import datetime
from navigation import MenuState, get_menu_keyboard

router = Router()

class ProductionOrderStates(StatesGroup):
    waiting_for_panel_thickness = State()
    waiting_for_panel_quantity = State()
    waiting_for_film_color = State()

async def notify_production_users(bot, order_id: int, panel_quantity: int, panel_thickness: float, film_color: str, manager_id: int):
    """Уведомляет всех пользователей с ролью PRODUCTION о новом заказе."""
    db = next(get_db())
    try:
        production_users = db.query(User).filter(User.role == UserRole.PRODUCTION).all()
        
        # Получаем информацию о менеджере
        manager = db.query(User).filter(User.id == manager_id).first()
        manager_name = manager.username if manager else "Неизвестный менеджер"
        
        for user in production_users:
            await bot.send_message(
                user.telegram_id,
                f"📢 Новый заказ на производство #{order_id}!\n"
                f"Менеджер: {manager_name}\n"
                f"Толщина панелей: {panel_thickness} мм\n"
                f"Количество панелей: {panel_quantity}\n"
                f"Цвет пленки: {film_color}"
            )
    finally:
        db.close()

@router.message(F.text == "🏭 Заказать производство")
async def handle_production_order(message: Message, state: FSMContext):
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or user.role != UserRole.SALES_MANAGER:
            await message.answer("У вас нет прав для создания заказов на производство.")
            return
            
        # Запрашиваем толщину панелей для заказа
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="0.5")],
                [KeyboardButton(text="0.8")],
                [KeyboardButton(text="◀️ Назад")]
            ],
            resize_keyboard=True
        )
        
        await message.answer(
            "Выберите толщину панелей для заказа (мм):",
            reply_markup=keyboard
        )
        await state.set_state(ProductionOrderStates.waiting_for_panel_thickness)
    finally:
        db.close()

@router.message(ProductionOrderStates.waiting_for_panel_thickness)
async def process_panel_thickness(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        # Возвращаемся к главному меню
        await state.clear()
        return
    
    try:
        thickness = float(message.text)
        if thickness not in [0.5, 0.8]:
            await message.answer("Пожалуйста, выберите толщину 0.5 или 0.8 мм.")
            return
            
        await state.update_data(panel_thickness=thickness)
        
        await message.answer(
            "Введите количество панелей:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="◀️ Назад")]],
                resize_keyboard=True
            )
        )
        await state.set_state(ProductionOrderStates.waiting_for_panel_quantity)
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число (0.5 или 0.8).")

@router.message(ProductionOrderStates.waiting_for_panel_quantity)
async def process_panel_quantity(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        # Возвращаемся к выбору толщины панели
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="0.5")],
                [KeyboardButton(text="0.8")],
                [KeyboardButton(text="◀️ Назад")]
            ],
            resize_keyboard=True
        )
        
        await message.answer(
            "Выберите толщину панелей для заказа (мм):",
            reply_markup=keyboard
        )
        await state.set_state(ProductionOrderStates.waiting_for_panel_thickness)
        return
        
    try:
        quantity = int(message.text)
        if quantity <= 0:
            await message.answer("Количество должно быть положительным числом.")
            return
            
        await state.update_data(panel_quantity=quantity)
        
        # Получаем список доступных цветов пленки
        db = next(get_db())
        try:
            films = db.query(Film.code).distinct().all()
            film_colors = [film[0] for film in films]
            
            if not film_colors:
                await message.answer("В базе нет доступных цветов пленки.")
                await state.clear()
                return
                
            keyboard = [[KeyboardButton(text=color)] for color in film_colors]
            keyboard.append([KeyboardButton(text="◀️ Назад")])
            
            await message.answer(
                "Выберите цвет пленки:",
                reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
            )
            await state.set_state(ProductionOrderStates.waiting_for_film_color)
        finally:
            db.close()
            
    except ValueError:
        await message.answer("Пожалуйста, введите целое число.")
        return

@router.message(ProductionOrderStates.waiting_for_film_color)
async def process_film_color(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await message.answer("Введите количество панелей:")
        await state.set_state(ProductionOrderStates.waiting_for_panel_quantity)
        return
        
    data = await state.get_data()
    db = next(get_db())
    try:
        # Получаем менеджера
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        
        # Создаем заказ
        order = ProductionOrder(
            manager_id=user.id,
            panel_quantity=data["panel_quantity"],
            panel_thickness=data["panel_thickness"],
            film_color=message.text,
            status="new"
        )
        db.add(order)
        db.commit()
        
        # Уведомляем производство
        await notify_production_users(
            message.bot,
            order.id,
            data["panel_quantity"],
            data["panel_thickness"],
            message.text,
            user.id  # Передаем id менеджера для отображения в уведомлении
        )
        
        await message.answer(
            f"✅ Заказ на производство создан!\n"
            f"Номер заказа: #{order.id}\n"
            f"Толщина панелей: {data['panel_thickness']} мм\n"
            f"Количество панелей: {data['panel_quantity']}\n"
            f"Цвет пленки: {message.text}"
        )
    finally:
        db.close()
    
    await state.clear()

@router.message(F.text == "📋 Мои заказы")
async def handle_my_orders(message: Message, state: FSMContext):
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        
        # Проверяем, имеет ли пользователь нужную роль (либо производство, либо супер-админ)
        if not user or (user.role != UserRole.PRODUCTION and user.role != UserRole.SUPER_ADMIN):
            logging.info(f"Отказ в доступе для пользователя {message.from_user.id} с ролью {user.role if user else 'None'}")
            await message.answer("У вас нет прав для просмотра заказов на производство.")
            return
            
        # Получаем все активные заказы
        orders = db.query(ProductionOrder).filter(
            ProductionOrder.status.in_(["new", "in_progress"])
        ).order_by(ProductionOrder.created_at.desc()).all()
        
        if not orders:
            await message.answer("Нет активных заказов на производство.")
            return
            
        # Создаем клавиатуру с номерами заказов
        keyboard = []
        for order in orders:
            keyboard.append([KeyboardButton(text=f"✅ Заказ #{order.id} готов")])
        keyboard.append([KeyboardButton(text="◀️ Назад")])
        
        # Формируем сообщение со списком заказов
        message_text = "📋 Активные заказы на производство:\n\n"
        for order in orders:
            # Получаем информацию о менеджере
            manager = db.query(User).filter(User.id == order.manager_id).first()
            manager_name = manager.username if manager else "Неизвестный менеджер"
            
            status = "🆕 Новый" if order.status == OrderStatus.NEW else "🔄 В работе"
            message_text += (
                f"Заказ #{order.id} ({status})\n"
                f"Менеджер: {manager_name}\n"
                f"Толщина панелей: {order.panel_thickness} мм\n"
                f"Количество панелей: {order.panel_quantity}\n"
                f"Цвет пленки: {order.film_color}\n"
                f"Создан: {order.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            )
        
        await message.answer(
            message_text,
            reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
        )
    finally:
        db.close()

@router.message(F.text.startswith("✅ Заказ #"))
async def handle_order_completed(message: Message, state: FSMContext):
    try:
        order_id = int(message.text.split("#")[1].split()[0])
        logging.info(f"Попытка подтвердить выполнение заказа #{order_id} пользователем {message.from_user.id}")
    except (IndexError, ValueError):
        await message.answer("Неверный формат номера заказа.")
        return
        
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        logging.info(f"Пользователь {message.from_user.id} с ролью {user.role if user else 'None'} пытается подтвердить выполнение заказа")
        
        # Проверяем, имеет ли пользователь нужную роль (либо производство, либо супер-админ)
        if not user or (user.role != UserRole.PRODUCTION and user.role != UserRole.SUPER_ADMIN):
            logging.warning(f"Отказ в доступе для подтверждения заказа пользователю {message.from_user.id} с ролью {user.role if user else 'None'}")
            await message.answer("У вас нет прав для подтверждения выполнения заказов.")
            return
            
        # Получаем и проверяем заказ
        order = db.query(ProductionOrder).filter(ProductionOrder.id == order_id).first()
        if not order:
            await message.answer("Заказ не найден.")
            return
            
        if order.status == OrderStatus.COMPLETED:
            await message.answer("Этот заказ уже выполнен.")
            return

        # Проверяем наличие пустых панелей
        empty_panel = db.query(Panel).first()
        if not empty_panel or empty_panel.quantity < order.panel_quantity:
            await message.answer("Недостаточно пустых панелей на складе для выполнения заказа.")
            return

        # Проверяем наличие пленки нужного цвета
        film = db.query(Film).filter(Film.code == order.film_color).first()
        if not film:
            await message.answer("Пленка с таким цветом не найдена.")
            return
            
        # Проверяем, достаточно ли метров пленки
        needed_length = order.panel_quantity * film.panel_consumption
        available_length = film.total_remaining
        if available_length < needed_length:
            await message.answer(
                f"Недостаточно пленки на складе для выполнения заказа.\n"
                f"Требуется: {needed_length} м\n"
                f"Доступно: {available_length} м"
            )
            return

        # Уменьшаем количество пустых панелей
        empty_panel.quantity -= order.panel_quantity

        # Уменьшаем количество пленки
        meters_used = order.panel_quantity * film.panel_consumption
        film.total_remaining -= meters_used

        # Добавляем готовую продукцию
        finished_product = db.query(FinishedProduct).filter(
            FinishedProduct.film_id == film.id,
            FinishedProduct.thickness == order.panel_thickness  # Учитываем толщину панелей
        ).first()
        
        if not finished_product:
            finished_product = FinishedProduct(
                film_id=film.id,
                quantity=0,
                thickness=order.panel_thickness  # Указываем толщину панелей
            )
            db.add(finished_product)
            
        finished_product.quantity += order.panel_quantity
        
        # Обновляем статус заказа
        order.status = "completed"
        order.completed_at = datetime.now()
        
        # Создаем запись об операции
        operation = Operation(
            user_id=user.id,
            operation_type="production",
            quantity=order.panel_quantity,
            details=f'{{"film_color": "{order.film_color}"}}'
        )
        db.add(operation)
        
        db.commit()
        
        # Уведомляем менеджера о выполнении заказа
        manager = db.query(User).filter(User.id == order.manager_id).first()
        if manager:
            await message.bot.send_message(
                manager.telegram_id,
                f"✅ Заказ #{order.id} выполнен!\n"
                f"Количество панелей: {order.panel_quantity}\n"
                f"Цвет пленки: {order.film_color}"
            )
        
        await message.answer(
            f"✅ Заказ #{order.id} помечен как выполненный.\n"
            f"• Использовано пустых панелей: {order.panel_quantity}\n"
            f"• Толщина панелей: {order.panel_thickness} мм\n"
            f"• Использовано пленки {order.film_color}: {meters_used:.2f} м\n"
            f"• Добавлено готовых панелей с пленкой {order.film_color}: {order.panel_quantity}"
        )
        
        # Показываем обновленный список заказов без выполненного заказа
        await handle_my_orders(message, state)
    finally:
        db.close() 