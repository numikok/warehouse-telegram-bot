from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from models import User, UserRole, ProductionOrder, Film, Panel, FinishedProduct, Operation, OrderStatus
from database import get_db
import logging
from datetime import datetime

router = Router()

class ProductionOrderStates(StatesGroup):
    waiting_for_panel_quantity = State()
    waiting_for_film_color = State()

async def notify_production_users(bot, order_id: int, panel_quantity: int, film_color: str):
    """Уведомляет всех пользователей с ролью PRODUCTION о новом заказе."""
    db = next(get_db())
    try:
        production_users = db.query(User).filter(User.role == UserRole.PRODUCTION).all()
        
        for user in production_users:
            await bot.send_message(
                user.telegram_id,
                f"📢 Новый заказ на производство #{order_id}!\n"
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
            
        await message.answer(
            "Введите количество панелей:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="◀️ Назад")]],
                resize_keyboard=True
            )
        )
        await state.set_state(ProductionOrderStates.waiting_for_panel_quantity)
    finally:
        db.close()

@router.message(ProductionOrderStates.waiting_for_panel_quantity)
async def process_panel_quantity(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        # Возвращаемся к главному меню
        await state.clear()
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
            message.text
        )
        
        await message.answer(
            f"✅ Заказ на производство создан!\n"
            f"Номер заказа: #{order.id}\n"
            f"Количество панелей: {data['panel_quantity']}\n"
            f"Цвет пленки: {message.text}"
        )
    finally:
        db.close()
    
    await state.clear()

@router.message(F.text == "📋 Мои заказы")
async def handle_my_orders(message: Message):
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or user.role != UserRole.PRODUCTION:
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
            status = "🆕 Новый" if order.status == OrderStatus.NEW else "🔄 В работе"
            message_text += (
                f"Заказ #{order.id} ({status})\n"
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
async def handle_order_completed(message: Message):
    try:
        order_id = int(message.text.split("#")[1].split()[0])
    except (IndexError, ValueError):
        await message.answer("Неверный формат номера заказа.")
        return
        
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or user.role != UserRole.PRODUCTION:
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
            f"• Использовано пленки {order.film_color}: {meters_used:.2f} м\n"
            f"• Добавлено готовых панелей с пленкой {order.film_color}: {order.panel_quantity}"
        )
        
        # Показываем обновленный список заказов без выполненного заказа
        await handle_my_orders(message)
    finally:
        db.close() 