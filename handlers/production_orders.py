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
import json

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
                f"Цвет пленки: {film_color}",
                parse_mode="Markdown"
            )
    finally:
        db.close()

@router.message(F.text == "📝 Заказать")
async def handle_production_order(message: Message, state: FSMContext):
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or user.role != UserRole.SALES_MANAGER:
            await message.answer("У вас нет прав для создания заказов на производство.", parse_mode="Markdown")
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
            "Для начала выберите толщину панелей для заказа (мм).\n"
            "После этого вам будут доступны цвета пленки для выбранной толщины:",
            reply_markup=keyboard,
            parse_mode="Markdown"
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
            await message.answer("Пожалуйста, выберите толщину 0.5 или 0.8 мм.", parse_mode="Markdown")
            return
            
        await state.update_data(panel_thickness=thickness)
        
        await message.answer(
            "Введите количество панелей:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="◀️ Назад")]],
                resize_keyboard=True
            ),
            parse_mode="Markdown"
        )
        await state.set_state(ProductionOrderStates.waiting_for_panel_quantity)
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число (0.5 или 0.8).", parse_mode="Markdown")

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
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        await state.set_state(ProductionOrderStates.waiting_for_panel_thickness)
        return
        
    try:
        quantity = int(message.text)
        if quantity <= 0:
            await message.answer("Количество должно быть положительным числом.", parse_mode="Markdown")
            return
            
        await state.update_data(panel_quantity=quantity)
        
        # Получаем сохраненные данные
        data = await state.get_data()
        selected_thickness = data["panel_thickness"]
        
        # Получаем список доступных цветов пленки для выбранной толщины
        db = next(get_db())
        try:
            # Ищем цвета, для которых есть готовая продукция с выбранной толщиной
            available_films = db.query(Film.code).join(FinishedProduct).filter(
                FinishedProduct.thickness == selected_thickness
            ).distinct().all()
            
            # Если нет готовой продукции с такой толщиной, показываем все доступные цвета
            if not available_films:
                available_films = db.query(Film.code).distinct().all()
            
            film_colors = [film[0] for film in available_films]
            
            if not film_colors:
                await message.answer("В базе нет доступных цветов пленки.", parse_mode="Markdown")
                await state.clear()
                return
                
            keyboard = [[KeyboardButton(text=color)] for color in film_colors]
            keyboard.append([KeyboardButton(text="◀️ Назад")])
            
            await message.answer(
                f"Выберите цвет пленки для панелей толщиной {selected_thickness} мм:",
                reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True),
                parse_mode="Markdown"
            )
            await state.set_state(ProductionOrderStates.waiting_for_film_color)
        finally:
            db.close()
            
    except ValueError:
        await message.answer("Пожалуйста, введите целое число.", parse_mode="Markdown")
        return

@router.message(ProductionOrderStates.waiting_for_film_color)
async def process_film_color(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await message.answer("Введите количество панелей:", parse_mode="Markdown")
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
            f"Цвет пленки: {message.text}",
            parse_mode="Markdown"
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
            await message.answer("У вас нет прав для просмотра заказов на производство.", parse_mode="Markdown")
            return
            
        # Получаем все активные заказы
        orders = db.query(ProductionOrder).filter(
            ProductionOrder.status.in_(["new", "in_progress"])
        ).order_by(ProductionOrder.created_at.desc()).all()
        
        if not orders:
            await message.answer("Нет активных заказов на производство.", parse_mode="Markdown")
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
            
            status = "🆕 Новый" if order.status == OrderStatus.NEW.value else "🔄 В работе"
            message_text += (
                f"Заказ #{order.id} ({status})\n"
                f"Менеджер: {manager_name}\n"
                f"Толщина панелей: {order.panel_thickness} мм\n"
                f"Количество панелей: {order.panel_quantity}\n"
                f"Цвет пленки: {order.film_color}\n"
                f"Создан: {order.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            )
        
        # Отправляем сообщение с клавиатурой
        await message.answer(
            message_text,
            reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True),
            parse_mode="Markdown"
        )
    finally:
        db.close()

@router.message(F.text.startswith("✅ Заказ #"))
async def handle_order_completed(message: Message, state: FSMContext):
    try:
        order_id_str = message.text.split("#")[1].strip()
        order_id = int(order_id_str.split()[0])  # Получаем только число из строки вида "123 готов"
    except (IndexError, ValueError):
        await message.answer("Неверный формат номера заказа.", parse_mode="Markdown")
        return
        
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        
        # Проверяем, имеет ли пользователь нужную роль (либо производство, либо супер-админ)
        if not user or (user.role != UserRole.PRODUCTION and user.role != UserRole.SUPER_ADMIN):
            await message.answer("У вас нет прав для подтверждения выполнения заказов.", parse_mode="Markdown")
            return
            
        order = db.query(ProductionOrder).filter(ProductionOrder.id == order_id).first()
        if not order:
            await message.answer("Заказ не найден.", parse_mode="Markdown")
            return
            
        if order.status == OrderStatus.COMPLETED.value:
            await message.answer("Этот заказ уже выполнен.", parse_mode="Markdown")
            return
            
        # Проверяем наличие достаточного количества панелей
        panels_available = db.query(Panel).filter(Panel.thickness == order.panel_thickness).first()
        if not panels_available or panels_available.quantity < order.panel_quantity:
            await message.answer("Недостаточно панелей на складе для выполнения заказа.", parse_mode="Markdown")
            return
            
        # Проверяем наличие пленки выбранного цвета
        film = db.query(Film).filter(Film.code == order.film_color).first()
        if not film:
            await message.answer("Пленка с таким цветом не найдена.", parse_mode="Markdown")
            return
            
        # Обновляем статус заказа
        order.status = OrderStatus.COMPLETED.value
        order.completed_at = datetime.now()
        order.completed_by = user.id
        db.commit()
        
        await message.answer(
            f"✅ Заказ #{order.id} отмечен как выполненный!\n"
            f"Производство {order.panel_quantity} панелей с пленкой {order.film_color} завершено.\n\n"
            f"Не забудьте обновить остатки пленки в складской системе.",
            parse_mode="Markdown"
        )
        
        # Уведомляем отдел продаж
        manager = db.query(User).filter(User.id == order.manager_id).first()
        if manager:
            try:
                await message.bot.send_message(
                    manager.telegram_id,
                    f"✅ Заказ #{order.id} на производство выполнен!\n"
                    f"Толщина панелей: {order.panel_thickness} мм\n"
                    f"Количество панелей: {order.panel_quantity}\n"
                    f"Цвет пленки: {order.film_color}\n\n"
                    f"Готовые товары добавлены на склад.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logging.error(f"Ошибка отправки уведомления менеджеру: {e}")
        
        # Уменьшаем количество панелей
        panels_available.quantity -= order.panel_quantity
        
        # Добавляем операцию в журнал
        operation = Operation(
            user_id=user.id,
            operation_type=OperationType.PRODUCTION.value,
            quantity=order.panel_quantity,
            details=json.dumps({
                "order_id": order.id,
                "film_color": order.film_color,
                "panel_thickness": order.panel_thickness
            })
        )
        db.add(operation)
        
        # Добавляем готовую продукцию на склад
        finished_product_exists = db.query(FinishedProduct).filter(
            FinishedProduct.film_id == film.id,
            FinishedProduct.thickness == order.panel_thickness
        ).first()
        
        if finished_product_exists:
            finished_product_exists.quantity += order.panel_quantity
        else:
            finished_product = FinishedProduct(
                film_id=film.id,
                quantity=order.panel_quantity,
                thickness=order.panel_thickness
            )
            db.add(finished_product)
        
        # Обновляем количество оставшейся пленки
        film.total_remaining -= film.panel_consumption * order.panel_quantity
        if film.total_remaining < 0:
            film.total_remaining = 0
            
        db.commit()
        
    finally:
        db.close()