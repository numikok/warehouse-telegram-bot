from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from models import User, UserRole, Film, Panel, Joint, Glue, Operation, FinishedProduct, Order, CompletedOrder, OrderStatus, JointType, CompletedOrderJoint, CompletedOrderItem, CompletedOrderGlue, CompletedOrderStatus
from database import get_db
import json
import logging
from navigation import MenuState, get_menu_keyboard, go_back
from datetime import datetime, timedelta
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import desc
import re

router = Router()

def get_main_keyboard():
    """Возвращает основную клавиатуру для складовщика"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Остатки на складе")],
            [KeyboardButton(text="📥 Оприходовать материалы")],
            [KeyboardButton(text="📦 Подтвердить отгрузку")],
            [KeyboardButton(text="📋 Мои заказы")]
        ],
        resize_keyboard=True
    )

class WarehouseStates(StatesGroup):
    waiting_for_order_id = State()
    waiting_for_confirmation = State()
    confirming_shipment = State()

@router.message(Command("stock"))
async def cmd_stock(message: Message, state: FSMContext):
    # Не проверяем доступ, так как эта функция теперь может вызываться с разными ролями
    
    db = next(get_db())
    try:
        state_data = await state.get_data()
        is_admin_context = state_data.get("is_admin_context", False)
        
        # Получаем текущую роль пользователя для выбора правильной клавиатуры
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        user_role = user.role if user else UserRole.NONE
        
        # Получаем остатки по всем материалам
        films = db.query(Film).all()
        joints = db.query(Joint).all()
        glue = db.query(Glue).first()
        panels = db.query(Panel).all()  # Получаем все панели вместо одной
        finished_products = db.query(FinishedProduct).join(Film).all()
        
        # Формируем отчет по пленкам
        response = "📊 Остатки на складе:\n\n"
        
        response += "🎞 Пленки:\n"
        for film in films:
            meters_per_roll = film.meters_per_roll or 50.0  # По умолчанию 50 метров в рулоне
            rolls = film.total_remaining / meters_per_roll if meters_per_roll > 0 else 0
            response += (
                f"- {film.code}:\n"
                f"  • Рулонов: {rolls:.1f}\n"
                f"  • Общая длина: {film.total_remaining:.2f} м\n"
                f"  • Можно произвести панелей: {film.calculate_possible_panels()}\n\n"
            )
        
        response += "🔄 Стыки:\n"
        for joint in joints:
            response += (
                f"- {joint.color} ({joint.type.value}, {joint.thickness} мм):\n"
                f"  • Количество: {joint.quantity}\n"
            )
        
        response += "\n📦 Пустые панели:\n"
        if panels:
            for panel in panels:
                response += f"- Толщина {panel.thickness} мм: {panel.quantity} шт.\n"
        else:
            response += "Нет в наличии\n"
            
        response += "\n🧪 Клей:\n"
        if glue:
            response += f"Количество: {glue.quantity}\n"
        else:
            response += "Нет в наличии\n"
            
        response += "\n✅ Готовые панели:\n"
        if finished_products:
            for product in finished_products:
                response += f"- {product.film.code} (толщина {product.thickness} мм): {product.quantity} шт.\n"
        else:
            response += "Нет в наличии\n"
        
        # Выбираем правильную клавиатуру в зависимости от роли пользователя
        if user_role == UserRole.WAREHOUSE:
            keyboard = get_menu_keyboard(MenuState.WAREHOUSE_MAIN, is_admin_context)
        elif user_role == UserRole.PRODUCTION:
            keyboard = get_menu_keyboard(MenuState.PRODUCTION_MAIN)
        else:
            # Для суперадмина и других ролей
            keyboard = get_menu_keyboard(MenuState.SUPER_ADMIN_MAIN) if user_role == UserRole.SUPER_ADMIN else None
        
        await message.answer(response, reply_markup=keyboard)
    finally:
        db.close()

@router.message(Command("income_materials"))
async def cmd_income_materials(message: Message, state: FSMContext):
    if not await check_warehouse_access(message):
        return
    
    await state.set_state(MenuState.WAREHOUSE_MATERIALS)
    await message.answer(
        "Выберите тип материала для оприходования:",
        reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MATERIALS)
    )
    await state.set_state(WarehouseStates.waiting_for_order_id)

@router.message(WarehouseStates.waiting_for_order_id)
async def process_order_id(message: Message, state: FSMContext):
    order_id = message.text
    
    if not order_id.isdigit():
        await message.answer("Пожалуйста, введите корректный номер заказа.")
        return
        
    await state.update_data(order_id=int(order_id))
    
    await message.answer("Подтвердите отгрузку заказа:")
    await state.set_state(WarehouseStates.waiting_for_confirmation)

@router.message(WarehouseStates.waiting_for_confirmation)
async def process_confirmation(message: Message, state: FSMContext):
    confirmation = message.text.lower()
    
    if confirmation not in ["да", "нет"]:
        await message.answer("Пожалуйста, ответьте да или нет.")
        return
        
    data = await state.get_data()
    order_id = data["order_id"]
    
    await process_order_shipment(message, order_id)

@router.message(Command("confirm_order"))
async def cmd_confirm_order(message: Message, state: FSMContext):
    """Обработка команды для просмотра активных заказов"""
    if not await check_warehouse_access(message):
        return
        
    await display_active_orders(message, state)

async def display_active_orders(message: Message, state: FSMContext):
    """Отображает список активных заказов для подтверждения отгрузки"""
    db = next(get_db())
    try:
        # Получаем все активные заказы со статусом NEW или IN_PROGRESS (из handle_my_orders)
        orders_to_ship = db.query(Order).filter(
            Order.status.in_([OrderStatus.NEW, OrderStatus.IN_PROGRESS])
        ).options(
            joinedload(Order.products),
            joinedload(Order.joints),
            joinedload(Order.glues),
            joinedload(Order.manager) # Load manager
        ).order_by(Order.created_at).all() # Added order_by

        if not orders_to_ship:
            await message.answer(
                "📦 Нет активных заказов для отгрузки.",
                # Используем главное меню склада, а не меню заказов, т.к. заказов нет
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
            )
            return

        response = "📦 Активные заказы для отгрузки:\n\n"
        keyboard_buttons = [] # For reply keyboard buttons
        for order in orders_to_ship:
            response += f"---\n"
            response += f"📝 Заказ #{order.id}\n"
            # Используем order.manager т.к. загрузили его через joinedload
            response += f"👤 Менеджер: {order.manager.username if order.manager else 'Неизвестно'}\n"
            response += f"Статус: {order.status.value}\n"
            response += f"Клиент: {order.customer_phone}\n"
            response += f"Адрес: {order.delivery_address}\n"
            # Добавляем дату отгрузки и способ оплаты
            shipment_date_str = order.shipment_date.strftime('%d.%m.%Y') if order.shipment_date else 'Не указана'
            payment_method_str = order.payment_method if order.payment_method else 'Не указан'
            response += f"🗓 Дата отгрузки: {shipment_date_str}\n"
            response += f"💳 Способ оплаты: {payment_method_str}\n"
            response += f"🔧 Монтаж: {'Да' if order.installation_required else 'Нет'}\n"

            # Продукция
            response += "\n🎨 Продукция:\n"
            if order.products:
                 for item in order.products:
                     # Changed formatting slightly to match handle_my_orders
                     response += f"- {item.color} ({item.thickness} мм): {item.quantity} шт.\n"
            else:
                 response += "- нет\n"

            # Стыки
            response += "\n🔗 Стыки:\n"
            if order.joints:
                 for joint in order.joints:
                     joint_type_str = joint.joint_type.name.capitalize() if joint.joint_type else "Неизвестно"
                     # Changed formatting slightly
                     response += f"- {joint_type_str} ({joint.joint_thickness} мм, {joint.joint_color}): {joint.joint_quantity} шт.\n"
            else:
                 response += "- нет\n"

            # Клей
            response += "\n🧴 Клей:\n"
            glue_total = sum(g.quantity for g in order.glues) if order.glues else 0
            if glue_total > 0:
                response += f"- {glue_total} шт.\n"
            else:
                 response += "- нет\n"

            response += f"\n"
            # Добавляем кнопку для подтверждения отгрузки
            keyboard_buttons.append([KeyboardButton(text=f"✅ Отгрузить заказ #{order.id}")])

        # Добавляем кнопку "Назад"
        keyboard_buttons.append([KeyboardButton(text="◀️ Назад")])

        reply_markup = ReplyKeyboardMarkup(
            keyboard=keyboard_buttons,
            resize_keyboard=True
        )

        await message.answer(response, reply_markup=reply_markup)
        await state.set_state(WarehouseStates.confirming_shipment) # Set state for button handler

    finally:
        db.close()

@router.message(F.text == "📦 Мои заказы")
async def handle_orders(message: Message, state: FSMContext):
    """Обработка нажатия на кнопку 'Мои заказы'"""
    if not await check_warehouse_access(message):
        return
    
    # Вызываем функцию для отображения активных заказов, передаем state
    await display_active_orders(message, state) # Pass state

@router.message(F.text == "📦 Остатки")
async def handle_stock(message: Message, state: FSMContext):
    """Показывает меню выбора категорий остатков"""
    if not await check_warehouse_access(message):
        return
    
    await state.set_state(MenuState.INVENTORY_CATEGORIES)
    keyboard = get_menu_keyboard(MenuState.INVENTORY_CATEGORIES)
    await message.answer(
        "Выберите категорию остатков для просмотра:",
        reply_markup=keyboard
    )

@router.message(F.text == "📊 Все остатки")
async def handle_all_stock(message: Message, state: FSMContext):
    """Показывает все остатки на складе"""
    if not await check_warehouse_access(message):
        return
        
    await state.set_state(MenuState.WAREHOUSE_STOCK) # Используем существующее состояние
    db = next(get_db())
    try:
        # Запрос к базе данных для получения остатков
        finished_products = db.query(FinishedProduct).options(joinedload(FinishedProduct.film)).all()
        films = db.query(Film).all()
        panels = db.query(Panel).all()
        joints = db.query(Joint).all()
        glue = db.query(Glue).first()
        
        response = "📦 Все остатки на складе:\n\n"
        
        response += "✅ Готовая продукция:\n"
        if finished_products:
            for product in finished_products:
                 if product.quantity > 0:
                    response += f"- {product.film.code} ({product.thickness} мм): {product.quantity} шт.\n"
        if not any(p.quantity > 0 for p in finished_products):
             response += "- Нет\n"
            
        response += "\n🎞 Пленка:\n"
        if films:
            for f in films:
                 if f.total_remaining > 0:
                    response += f"- {f.code}: {f.total_remaining:.2f} метров\n"
        if not any(f.total_remaining > 0 for f in films):
             response += "- Нет\n"
            
        response += "\n🪵 Панели:\n"
        if panels:
            for p in panels:
                 if p.quantity > 0:
                    response += f"- Толщина {p.thickness} мм: {p.quantity} шт.\n"
        if not any(p.quantity > 0 for p in panels):
             response += "- Нет\n"
            
        response += "\n🔄 Стыки:\n"
        if joints:
            for j in joints:
                 if j.quantity > 0:
                    response += f"- {j.type.name.capitalize()} ({j.thickness} мм, {j.color}): {j.quantity} шт.\n"
        if not any(j.quantity > 0 for j in joints):
             response += "- Нет\n"
            
        response += "\n🧪 Клей:\n"
        if glue and glue.quantity > 0:
            response += f"- {glue.quantity} шт.\n"
        else:
            response += "- Нет\n"
            
        await message.answer(response, reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_STOCK))
    finally:
        db.close()

@router.message(F.text == "✅ Готовая продукция")
async def handle_finished_products(message: Message, state: FSMContext):
    if not await check_warehouse_access(message): return
    await state.set_state(MenuState.INVENTORY_FINISHED_PRODUCTS)
    
    db = next(get_db())
    try:
        finished_products = db.query(FinishedProduct).join(Film).filter(FinishedProduct.quantity > 0).all()
        response = "✅ Готовая продукция на складе:\n\n"
        if finished_products:
            for product in finished_products:
                response += f"- {product.film.code} (толщина {product.thickness} мм): {product.quantity} шт.\n"
        else:
            response += "Нет в наличии\n"
        keyboard = get_menu_keyboard(MenuState.INVENTORY_FINISHED_PRODUCTS)
        await message.answer(response, reply_markup=keyboard)
    finally:
        db.close()

@router.message(F.text == "🎞 Пленка")
async def handle_films(message: Message, state: FSMContext):
    if not await check_warehouse_access(message): return
    await state.set_state(MenuState.INVENTORY_FILMS)
    
    db = next(get_db())
    try:
        films = db.query(Film).filter(Film.total_remaining > 0).all()
        response = "🎞 Пленки на складе:\n\n"
        if films:
            for film in films:
                response += f"- {film.code}: {film.total_remaining:.2f} метров\n"
        else:
            response += "Нет в наличии\n"
        keyboard = get_menu_keyboard(MenuState.INVENTORY_FILMS)
        await message.answer(response, reply_markup=keyboard)
    finally:
        db.close()

@router.message(F.text == "🪵 Панели")
async def handle_panels(message: Message, state: FSMContext):
    if not await check_warehouse_access(message): return
    await state.set_state(MenuState.INVENTORY_PANELS)
    
    db = next(get_db())
    try:
        panels = db.query(Panel).filter(Panel.quantity > 0).all()
        response = "🪵 Пустые панели на складе:\n\n"
        if panels:
            for panel in panels:
                response += f"- Толщина {panel.thickness} мм: {panel.quantity} шт.\n"
        else:
            response += "Нет в наличии\n"
        keyboard = get_menu_keyboard(MenuState.INVENTORY_PANELS)
        await message.answer(response, reply_markup=keyboard)
    finally:
        db.close()

@router.message(F.text == "🔄 Стыки")
async def handle_joints(message: Message, state: FSMContext):
    if not await check_warehouse_access(message): return
    await state.set_state(MenuState.INVENTORY_JOINTS)
    
    db = next(get_db())
    try:
        joints = db.query(Joint).filter(Joint.quantity > 0).all()
        response = "🔄 Стыки на складе:\n\n"
        if joints:
            for joint in joints:
                response += f"- {joint.type.name.capitalize()} ({joint.thickness} мм, {joint.color}): {joint.quantity} шт.\n"
        else:
            response += "Нет в наличии\n"
        keyboard = get_menu_keyboard(MenuState.INVENTORY_JOINTS)
        await message.answer(response, reply_markup=keyboard)
    finally:
        db.close()

@router.message(F.text == "🧪 Клей")
async def handle_glue(message: Message, state: FSMContext):
    if not await check_warehouse_access(message): return
    await state.set_state(MenuState.INVENTORY_GLUE)
    
    db = next(get_db())
    try:
        glue = db.query(Glue).filter(Glue.quantity > 0).first()
        response = "🧪 Клей на складе:\n\n"
        if glue:
            response += f"Количество: {glue.quantity} шт.\n"
        else:
            response += "Нет в наличии\n"
        keyboard = get_menu_keyboard(MenuState.INVENTORY_GLUE)
        await message.answer(response, reply_markup=keyboard)
    finally:
        db.close()

@router.message(WarehouseStates.confirming_shipment, F.text.startswith("✅ Отгрузить заказ #"))
async def confirm_shipment(message: Message, state: FSMContext):
    if not await check_warehouse_access(message):
        return
        
    try:
        order_id = int(message.text.split("#")[-1])
    except (IndexError, ValueError):
        await message.answer("Некорректный формат команды.")
        return
        
    db = next(get_db())
    try:
        # Находим заказ для отгрузки
        order = db.query(Order).filter(
            Order.id == order_id,
            Order.status.in_([OrderStatus.NEW, OrderStatus.IN_PROGRESS])
        ).options(
            joinedload(Order.products),
            joinedload(Order.joints),
            joinedload(Order.glues),
            joinedload(Order.manager) # Загружаем менеджера
        ).first()
        
        if not order:
            await message.answer(f"Заказ #{order_id} не найден или уже отгружен.")
            return
            
        # Получаем пользователя-складовщика
        warehouse_user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not warehouse_user:
            await message.answer("Ошибка: пользователь склада не найден.")
            return
            
        # Проверяем наличие всех компонентов
        # 1. Продукция
        insufficient_items = []
        for item in order.products:
            finished_product = db.query(FinishedProduct).join(Film).filter(
                Film.code == item.color,
                FinishedProduct.thickness == item.thickness
            ).first()
            if not finished_product or finished_product.quantity < item.quantity:
                available = finished_product.quantity if finished_product else 0
                insufficient_items.append(f"- {item.color} ({item.thickness} мм): нужно {item.quantity}, доступно {available}")
        
        # 2. Стыки
        for joint_item in order.joints:
            joint = db.query(Joint).filter(
                Joint.type == joint_item.joint_type,
                Joint.thickness == joint_item.joint_thickness,
                Joint.color == joint_item.joint_color
            ).first()
            if not joint or joint.quantity < joint_item.joint_quantity:
                available = joint.quantity if joint else 0
                insufficient_items.append(f"- Стык {joint_item.joint_type.name.capitalize()} ({joint_item.joint_thickness} мм, {joint_item.joint_color}): нужно {joint_item.joint_quantity}, доступно {available}")
                
        # 3. Клей
        for glue_item in order.glues:
            glue = db.query(Glue).first()
            if not glue or glue.quantity < glue_item.quantity:
                available = glue.quantity if glue else 0
                insufficient_items.append(f"- Клей: нужно {glue_item.quantity}, доступно {available}")
                
        # Если чего-то не хватает
        if insufficient_items:
            await message.answer(
                f"❌ Невозможно отгрузить заказ #{order_id}. Не хватает следующих позиций:\n"
                + "\n".join(insufficient_items),
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN) # Возвращаем в главное меню склада
            )
            await state.set_state(MenuState.WAREHOUSE_MAIN)
            return
            
        # Если всего хватает, списываем со склада и переносим в completed_orders
        # 1. Списываем продукцию
        for item in order.products:
            finished_product = db.query(FinishedProduct).join(Film).filter(
                Film.code == item.color,
                FinishedProduct.thickness == item.thickness
            ).first()
            finished_product.quantity -= item.quantity
            
        # 2. Списываем стыки
        for joint_item in order.joints:
            joint = db.query(Joint).filter(
                Joint.type == joint_item.joint_type,
                Joint.thickness == joint_item.joint_thickness,
                Joint.color == joint_item.joint_color
            ).first()
            joint.quantity -= joint_item.joint_quantity
            
        # 3. Списываем клей
        for glue_item in order.glues:
            glue = db.query(Glue).first()
            glue.quantity -= glue_item.quantity
            
        # Создаем запись в completed_orders, копируя новые поля
        completed_order = CompletedOrder(
            order_id=order.id,
            manager_id=order.manager_id,
            warehouse_user_id=warehouse_user.id,
            installation_required=order.installation_required,
            customer_phone=order.customer_phone,
            delivery_address=order.delivery_address,
            shipment_date=order.shipment_date, # Копируем дату отгрузки
            payment_method=order.payment_method, # Копируем способ оплаты
            completed_at=datetime.utcnow()
        )
        db.add(completed_order)
        db.flush() # Получаем ID для completed_order
        
        # Копируем связанные объекты (items, joints, glues)
        for item in order.products:
            comp_item = CompletedOrderItem(
                order_id=completed_order.id,
                quantity=item.quantity,
                color=item.color,
                thickness=item.thickness
            )
            db.add(comp_item)
            
        for joint_item in order.joints:
            comp_joint = CompletedOrderJoint(
                order_id=completed_order.id,
                joint_type=joint_item.joint_type,
                joint_color=joint_item.joint_color,
                quantity=joint_item.joint_quantity,
                joint_thickness=joint_item.joint_thickness
            )
            db.add(comp_joint)
            
        for glue_item in order.glues:
            comp_glue = CompletedOrderGlue(
                order_id=completed_order.id,
                quantity=glue_item.quantity
            )
            db.add(comp_glue)
            
        # Удаляем исходный заказ из таблицы orders
        db.delete(order)
        
        db.commit()
        
        await message.answer(
            f"✅ Заказ #{order_id} успешно отгружен и перемещен в завершенные.",
            reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
        )
        
        # Переводим обратно в главное меню склада
        await state.set_state(MenuState.WAREHOUSE_MAIN)
        
    except Exception as e:
        db.rollback()
        logging.error(f"Ошибка при отгрузке заказа #{order_id}: {e}", exc_info=True)
        await message.answer(f"Произошла ошибка при отгрузке заказа: {e}")
    finally:
        db.close()

@router.message(F.text == "✅ Завершенные заказы")
async def handle_completed_orders(message: Message, state: FSMContext):
    """Отображает список завершенных заказов и предлагает ввести ID для деталей."""
    if not await check_warehouse_access(message):
        return
    
    await state.set_state(MenuState.WAREHOUSE_COMPLETED_ORDERS)
    db = next(get_db())
    try:
        # Получаем последние 20 завершенных заказов
        completed_orders = db.query(CompletedOrder).options(
            # Eager load related data if needed for the list view, otherwise remove
            # joinedload(CompletedOrder.items), 
            # joinedload(CompletedOrder.joints),
            # joinedload(CompletedOrder.glues),
            joinedload(CompletedOrder.manager),
            joinedload(CompletedOrder.warehouse_user)
        ).order_by(desc(CompletedOrder.completed_at)).limit(20).all()
        
        if not completed_orders:
            await message.answer(
                "Нет завершенных заказов.",
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_COMPLETED_ORDERS)
            )
            return
            
        response = "✅ Завершенные заказы (последние 20):\n\n"
        for order in completed_orders:
            response += f"---\n"
            response += f"Заказ #{order.order_id} (Завершен ID: {order.id})\n"
            response += f"Дата завершения: {order.completed_at.strftime('%Y-%m-%d %H:%M')}\n"
            response += f"Статус: {order.status}\n"
            # Removed the prompt to enter ID here as the next handler handles it
        
        response += f"\nВведите ID завершенного заказа (из поля 'Завершен ID: ...') для просмотра деталей и опций.\n" 
        
        # Ограничиваем длину сообщения, если оно слишком большое
        if len(response) > 4000: # Telegram limit is 4096
            response = response[:4000] + "\n... (список слишком длинный)"
            
        await message.answer(
            response,
            reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_COMPLETED_ORDERS)
        )
            
    except Exception as e:
        logging.error(f"Ошибка при получении завершенных заказов: {e}", exc_info=True)
        await message.answer(
            "Произошла ошибка при загрузке завершенных заказов.",
            reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_COMPLETED_ORDERS)
        )
    finally:
        db.close()

@router.message(StateFilter(MenuState.WAREHOUSE_COMPLETED_ORDERS), F.text.regexp(r'^\d+$'))
async def view_completed_order(message: Message, state: FSMContext):
    """Отображает детали одного завершенного заказа и кнопку запроса на возврат."""
    if not await check_warehouse_access(message):
        return

    try:
        completed_order_id = int(message.text)
    except ValueError:
        await message.answer("Пожалуйста, введите корректный числовой ID.", reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_COMPLETED_ORDERS))
        return

    db = next(get_db())
    try:
        order = db.query(CompletedOrder).options(
            joinedload(CompletedOrder.items),
            joinedload(CompletedOrder.joints),
            joinedload(CompletedOrder.glues),
            joinedload(CompletedOrder.manager),
            joinedload(CompletedOrder.warehouse_user)
        ).filter(CompletedOrder.id == completed_order_id).first()

        if not order:
            await message.answer(f"Завершенный заказ с ID {completed_order_id} не найден.", reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_COMPLETED_ORDERS))
            return

        # Format order details
        response = f"Детали завершенного заказа ID: {order.id} (Исходный: #{order.order_id})\n"
        response += f"Статус: {order.status}\n"
        response += f"Дата завершения: {order.completed_at.strftime('%Y-%m-%d %H:%M')}\n"
        response += f"Клиент: {order.customer_phone}\n"
        response += f"Адрес: {order.delivery_address}\n"
        shipment_date_str = order.shipment_date.strftime('%d.%m.%Y') if order.shipment_date else 'Не указана'
        payment_method_str = order.payment_method if order.payment_method else 'Не указан'
        response += f"🗓 Дата отгрузки: {shipment_date_str}\n"
        response += f"💳 Способ оплаты: {payment_method_str}\n"
        response += f"Монтаж: {'Да' if order.installation_required else 'Нет'}\n"
        response += f"Менеджер: {order.manager.username if order.manager else 'N/A'}\n"
        response += f"Склад: {order.warehouse_user.username if order.warehouse_user else 'N/A'}\n"
        
        response += "\nПродукция:\n"
        if order.items:
            for item in order.items:
                response += f"- {item.color} ({item.thickness} мм): {item.quantity} шт.\n"
        else:
            response += "- нет\n"
        
        response += "\nСтыки:\n"
        if order.joints:
            for joint in order.joints:
                response += f"- {joint.joint_type.name.capitalize()} ({joint.joint_thickness} мм, {joint.joint_color}): {joint.quantity} шт.\n"
        else:
            response += "- нет\n"
        
        response += "\nКлей:\n"
        if order.glues:
            for glue_item in order.glues:
                response += f"- {glue_item.quantity} шт.\n"
        else:
            response += "- нет\n"

        # Create inline keyboard
        keyboard_buttons = []
        if order.status == CompletedOrderStatus.COMPLETED.value:
             keyboard_buttons.append([
                 InlineKeyboardButton(text="♻️ Запрос на возврат", callback_data=f"request_return:{order.id}")
             ])
        
        inline_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons) if keyboard_buttons else None

        # Set state for potential further actions on this order
        await state.set_state(MenuState.WAREHOUSE_VIEW_COMPLETED_ORDER)
        await state.update_data(viewed_completed_order_id=order.id)
        
        await message.answer(
            response,
            reply_markup=inline_keyboard
        )
    except Exception as e:
        logging.error(f"Ошибка при просмотре завершенного заказа {completed_order_id}: {e}", exc_info=True)
        await message.answer("Произошла ошибка при загрузке деталей заказа.", reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_COMPLETED_ORDERS))
    finally:
        db.close()

@router.callback_query(F.data.startswith("request_return:"))
async def process_return_request(callback_query: CallbackQuery, state: FSMContext):
    """Обрабатывает нажатие кнопки 'Запрос на возврат'."""
    completed_order_id = int(callback_query.data.split(":")[1])
    user_id = callback_query.from_user.id
    message = callback_query.message

    db = next(get_db())
    try: # Outer try for DB connection management
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user or user.role not in [UserRole.WAREHOUSE, UserRole.SALES_MANAGER, UserRole.SUPER_ADMIN]:
            await callback_query.answer("У вас нет прав для этого действия.", show_alert=True)
            return 

        order = db.query(CompletedOrder).filter(CompletedOrder.id == completed_order_id).first()

        if not order:
            await callback_query.answer("Заказ не найден.", show_alert=True)
            try:
                await message.edit_text(message.text + "\n\n❌ Ошибка: Заказ не найден.")
            except Exception as edit_err:
                 logging.error(f"Failed to edit message on order not found: {edit_err}")
            return

        if order.status != CompletedOrderStatus.COMPLETED.value:
            await callback_query.answer(f"Нельзя запросить возврат для заказа со статусом '{order.status}'.", show_alert=True)
            return

        # --- Start DB Transaction Logic ---
        try: # Inner try for the actual DB update + commit/rollback
            order.status = CompletedOrderStatus.RETURN_REQUESTED.value
            db.commit()
            logging.info(f"User {user_id} requested return for completed order {completed_order_id}")
            
            await callback_query.answer("✅ Запрос на возврат создан.", show_alert=False)
            
            new_text = message.text.replace(f"Статус: {CompletedOrderStatus.COMPLETED.value}", f"Статус: {CompletedOrderStatus.RETURN_REQUESTED.value}")
            await message.edit_text(new_text, reply_markup=None)
            
        except Exception as db_exc:
            db.rollback()
            logging.error(f"Ошибка при обновлении статуса заказа {completed_order_id}: {db_exc}", exc_info=True)
            await callback_query.answer("❌ Ошибка базы данных при обновлении статуса.", show_alert=True)
        # --- End DB Transaction Logic ---

    except Exception as outer_exc: # Catch exceptions outside the DB transaction logic
        logging.error(f"Ошибка при обработке запроса на возврат (вне транзакции) для заказа {completed_order_id}: {outer_exc}", exc_info=True)
        await callback_query.answer("❌ Произошла общая ошибка при обработке запроса.", show_alert=True)
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

@router.message(lambda message: message.text and message.text.startswith("/confirm_"))
async def confirm_specific_order(message: Message, state: FSMContext):
    """Обработка команды для подтверждения конкретного заказа"""
    if not await check_warehouse_access(message):
        return
    
    try:
        # Извлекаем ID заказа из команды /confirm_123
        order_id = int(message.text.split("_")[1])
        await process_order_shipment(message, order_id)
    except (IndexError, ValueError):
        await message.answer(
            "❌ Неверный формат команды. Используйте /confirm_ID, где ID - номер заказа.",
            reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_ORDERS)
        )

async def process_order_shipment(message: Message, order_id: int):
    """Обрабатывает отгрузку заказа"""
    db = next(get_db())
    try:
        # Получаем заказ по ID
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            await message.answer(
                f"❌ Заказ #{order_id} не найден.",
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
            )
            return
            
        # Проверяем статус заказа
        if order.status == OrderStatus.COMPLETED:
            await message.answer(
                f"❌ Заказ #{order_id} уже выполнен.",
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
            )
            return
        
        # Получаем пользователя склада
        warehouse_user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not warehouse_user:
            await message.answer(
                "❌ Ваша учетная запись не найдена. Обратитесь к администратору.",
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
            )
            return
        
        try:
            # Подготавливаем данные для CompletedOrder с учетом обязательных полей
            completed_order_data = {
                'order_id': order.id,
                'manager_id': order.manager_id,
                'warehouse_user_id': warehouse_user.id,
                'installation_required': getattr(order, 'installation_required', False),
                'customer_phone': getattr(order, 'customer_phone', "") or "Не указан",
                'delivery_address': getattr(order, 'delivery_address', "") or "Не указан"
            }
            
            # Обходим все поля CompletedOrder для проверки
            valid_fields = {}
            for column in CompletedOrder.__table__.columns:
                valid_fields[column.name] = True
            
            # Удаляем неверные поля, если они были добавлены по ошибке
            for field in list(completed_order_data.keys()):
                if field not in valid_fields:
                    logging.warning(f"Удаляем недопустимое поле {field} из данных CompletedOrder")
                    del completed_order_data[field]
            
            # Проверяем, что все обязательные поля включены
            for column in CompletedOrder.__table__.columns:
                if not column.nullable and column.name not in ['id', 'completed_at'] and column.name not in completed_order_data and not column.default:
                    if column.name == 'customer_phone':
                        completed_order_data[column.name] = "Не указан"
                    elif column.name == 'delivery_address':
                        completed_order_data[column.name] = "Не указан"
                    else:
                        logging.warning(f"Добавляем пустое значение для обязательного поля {column.name}")
                        completed_order_data[column.name] = None
            
            # Создаем запись о выполненном заказе
            logging.info(f"Создаем CompletedOrder с данными: {completed_order_data}")
            completed_order = CompletedOrder(**completed_order_data)
            db.add(completed_order)
            db.flush()  # Получаем ID созданного заказа
            
            # Добавляем информацию о продуктах в выполненный заказ
            if hasattr(order, 'products') and order.products:
                for product in order.products:
                    try:
                        # Определяем необходимые атрибуты для CompletedOrderItem
                        item_data = {
                            'order_id': completed_order.id,
                            'quantity': getattr(product, 'quantity', 0),
                            'color': getattr(product, 'color', "Неизвестно"),
                            'thickness': getattr(product, 'thickness', 0.5)
                        }
                        
                        # Вместо поиска по film_id, ищем Film по коду пленки (color) и затем FinishedProduct
                        color = getattr(product, 'color', None)
                        thickness = getattr(product, 'thickness', 0.5)
                        
                        if color and item_data['quantity'] > 0:
                            # Создаем запись о выполненном товаре
                            completed_item = CompletedOrderItem(**item_data)
                            db.add(completed_item)
                            logging.info(f"Добавлен товар в completed_order_items: {item_data}")
                            
                            # Ищем пленку по коду
                            film = db.query(Film).filter(Film.code == color).first()
                            if film:
                                # Ищем готовую продукцию по film_id и толщине
                                finished_product = db.query(FinishedProduct).filter(
                                    FinishedProduct.film_id == film.id,
                                    FinishedProduct.thickness == thickness
                                ).first()
                                
                                if finished_product:
                                    old_quantity = finished_product.quantity
                                    new_quantity = old_quantity - item_data['quantity']
                                    logging.info(f"Списываем продукцию со склада: film_code={color}, film_id={film.id}, thickness={thickness}, было={old_quantity}, станет={new_quantity}")
                                    
                                    finished_product.quantity = new_quantity
                                    db.flush()  # Фиксируем изменения в памяти
                                    
                                    # Проверяем, что изменения применились
                                    updated_product = db.query(FinishedProduct).filter(
                                        FinishedProduct.film_id == film.id,
                                        FinishedProduct.thickness == thickness
                                    ).first()
                                    
                                    if updated_product and updated_product.quantity == new_quantity:
                                        logging.info(f"Успешно списана продукция. Новое количество в базе: {updated_product.quantity}")
                                    else:
                                        logging.error(f"Ошибка списания продукции! Текущее количество в базе: {updated_product.quantity if updated_product else 'не найдено'}")
                                else:
                                    logging.error(f"Готовая продукция не найдена для film_id={film.id}, thickness={thickness}")
                            else:
                                logging.error(f"Пленка с кодом {color} не найдена")
                    except Exception as e:
                        logging.error(f"Ошибка при добавлении продукта в выполненный заказ: {str(e)}")
            else:
                # Для поддержки старой структуры
                try:
                    if hasattr(order, 'film_code') and order.film_code:
                        # Находим пленку по коду
                        film = db.query(Film).filter(Film.code == order.film_code).first()
                        
                        # Создаем запись о выполненном товаре
                        item_data = {
                            'order_id': completed_order.id,
                            'color': order.film_code,
                            'thickness': getattr(order, 'panel_thickness', 0.5),
                            'quantity': getattr(order, 'panel_quantity', 0)
                        }
                        
                        completed_item = CompletedOrderItem(**item_data)
                        db.add(completed_item)
                        logging.info(f"Добавлен товар из старой структуры в completed_order_items: {item_data}")
                        
                        # Списываем со склада
                        if film:
                            finished_product = db.query(FinishedProduct).filter(
                                FinishedProduct.film_id == film.id,
                                FinishedProduct.thickness == item_data['thickness']
                            ).first()
                            
                            if finished_product:
                                old_quantity = finished_product.quantity
                                new_quantity = old_quantity - item_data['quantity']
                                logging.info(f"Списываем продукцию из старой структуры: film_id={film.id}, thickness={item_data['thickness']}, было={old_quantity}, станет={new_quantity}")
                                
                                finished_product.quantity = new_quantity
                                db.flush()
                                
                                # Проверяем, что изменения применились
                                updated_product = db.query(FinishedProduct).filter(
                                    FinishedProduct.film_id == film.id,
                                    FinishedProduct.thickness == item_data['thickness']
                                ).first()
                                
                                if updated_product and updated_product.quantity == new_quantity:
                                    logging.info(f"Успешно списана продукция из старой структуры. Новое количество в базе: {updated_product.quantity}")
                                else:
                                    logging.error(f"Ошибка списания продукции из старой структуры! Текущее количество в базе: {updated_product.quantity if updated_product else 'не найдено'}")
                            else:
                                logging.error(f"Готовая продукция не найдена для film_id={film.id}, thickness={item_data['thickness']}")
                        else:
                            logging.error(f"Пленка с кодом {order.film_code} не найдена")
                except Exception as e:
                    logging.error(f"Ошибка при добавлении продукта из старой структуры: {str(e)}")
            
            # Добавляем информацию о стыках в выполненный заказ
            if hasattr(order, 'joints') and order.joints:
                for joint_item in order.joints:
                    try:
                        joint_type = getattr(joint_item, 'joint_type', None)
                        joint_color = getattr(joint_item, 'joint_color', None)
                        thickness = getattr(joint_item, 'joint_thickness', 0.5)
                        quantity = getattr(joint_item, 'quantity', getattr(joint_item, 'joint_quantity', 0))
                        
                        if joint_type and joint_color and quantity > 0:
                            # Создаем запись о выполненном стыке
                            joint_data = {
                                'order_id': completed_order.id,
                                'joint_type': joint_type,
                                'joint_color': joint_color,
                                'quantity': quantity,
                                'joint_thickness': thickness  # Используем правильное имя поля
                            }
                            
                            completed_joint = CompletedOrderJoint(**joint_data)
                            db.add(completed_joint)
                            logging.info(f"Добавлен стык в completed_order_joints: {joint_data}")
                            
                            # Списываем со склада
                            joint_db = db.query(Joint).filter(
                                Joint.type == joint_type,
                                Joint.color == joint_color,
                                Joint.thickness == thickness
                            ).first()
                            
                            if joint_db:
                                old_quantity = joint_db.quantity
                                new_quantity = old_quantity - quantity
                                logging.info(f"Списываем стык со склада: type={joint_type}, color={joint_color}, thickness={thickness}, было={old_quantity}, станет={new_quantity}")
                                
                                joint_db.quantity = new_quantity
                                db.flush()
                                
                                # Проверяем, что изменения применились
                                updated_joint = db.query(Joint).filter(
                                    Joint.type == joint_type,
                                    Joint.color == joint_color,
                                    Joint.thickness == thickness
                                ).first()
                                
                                if updated_joint and updated_joint.quantity == new_quantity:
                                    logging.info(f"Успешно списан стык. Новое количество в базе: {updated_joint.quantity}")
                                else:
                                    logging.error(f"Ошибка списания стыка! Текущее количество в базе: {updated_joint.quantity if updated_joint else 'не найдено'}")
                    except Exception as e:
                        logging.error(f"Ошибка при добавлении стыка в выполненный заказ: {str(e)}")
            else:
                # Для поддержки старой структуры
                try:
                    # Получаем информацию о стыке из старой структуры
                    joint_type = getattr(order, 'joint_type', None)
                    joint_color = getattr(order, 'joint_color', None)
                    joint_quantity = getattr(order, 'joint_quantity', 0)
                    
                    if joint_type and joint_color and joint_quantity > 0:
                        # Создаем запись о выполненном стыке
                        joint_data = {
                            'order_id': completed_order.id,
                            'joint_type': joint_type,
                            'joint_color': joint_color,
                            'quantity': joint_quantity,
                            'joint_thickness': getattr(order, 'panel_thickness', 0.5)  # Используем правильное имя поля
                        }
                        
                        completed_joint = CompletedOrderJoint(**joint_data)
                        db.add(completed_joint)
                        logging.info(f"Добавлен стык из старой структуры в completed_order_joints: {joint_data}")
                        
                        # Списываем со склада
                        joint_thickness = getattr(order, 'panel_thickness', 0.5)
                        joint_db = db.query(Joint).filter(
                            Joint.type == joint_type,
                            Joint.color == joint_color,
                            Joint.thickness == joint_thickness
                        ).first()
                        
                        if joint_db:
                            old_quantity = joint_db.quantity
                            new_quantity = old_quantity - joint_quantity
                            logging.info(f"Списываем стык из старой структуры: type={joint_type}, color={joint_color}, thickness={joint_thickness}, было={old_quantity}, станет={new_quantity}")
                            
                            joint_db.quantity = new_quantity
                            db.flush()
                            
                            # Проверяем, что изменения применились
                            updated_joint = db.query(Joint).filter(
                                Joint.type == joint_type,
                                Joint.color == joint_color,
                                Joint.thickness == joint_thickness
                            ).first()
                            
                            if updated_joint and updated_joint.quantity == new_quantity:
                                logging.info(f"Успешно списан стык из старой структуры. Новое количество в базе: {updated_joint.quantity}")
                            else:
                                logging.error(f"Ошибка списания стыка из старой структуры! Текущее количество в базе: {updated_joint.quantity if updated_joint else 'не найдено'}")
                except Exception as e:
                    logging.error(f"Ошибка при добавлении стыка из старой структуры: {str(e)}")
            
            # Добавляем информацию о клее в выполненный заказ
            glue_quantity = 0
            if hasattr(order, 'glues') and order.glues:
                try:
                    glue_quantity = sum(getattr(glue, 'quantity', 0) for glue in order.glues)
                except Exception as e:
                    logging.error(f"Ошибка при извлечении данных о клее: {str(e)}")
            else:
                # Если нет glues, пробуем получить атрибуты напрямую из заказа (старая структура)
                glue_quantity = getattr(order, 'glue_quantity', 0)
                
            if glue_quantity > 0:
                try:
                    # Создаем запись о выполненном клее
                    glue_data = {
                        'order_id': completed_order.id,
                        'quantity': glue_quantity
                    }
                    
                    completed_glue = CompletedOrderGlue(**glue_data)
                    db.add(completed_glue)
                    logging.info(f"Добавлен клей в completed_order_glues: {glue_data}")
                    
                    # Списываем клей со склада
                    glue = db.query(Glue).first()
                    if glue:
                        old_quantity = glue.quantity
                        new_quantity = old_quantity - glue_quantity
                        logging.info(f"Списываем клей со склада: было={old_quantity}, станет={new_quantity}")
                        
                        glue.quantity = new_quantity
                        db.flush()
                        
                        # Проверяем, что изменения применились
                        updated_glue = db.query(Glue).first()
                        if updated_glue and updated_glue.quantity == new_quantity:
                            logging.info(f"Успешно списан клей. Новое количество в базе: {updated_glue.quantity}")
                        else:
                            logging.error(f"Ошибка списания клея! Текущее количество в базе: {updated_glue.quantity if updated_glue else 'не найдено'}")
                except Exception as e:
                    logging.error(f"Ошибка при добавлении клея в выполненный заказ: {str(e)}")
            
            # Меняем статус заказа на выполненный
            order.status = OrderStatus.COMPLETED
            order.completed_at = datetime.utcnow()
            
            # Сохраняем изменения в базе данных
            logging.info(f"Применяем все изменения в БД через commit для заказа #{order.id}")
            db.commit()
            logging.info(f"Изменения успешно сохранены в БД для заказа #{order.id}")
            
            # Отправляем сообщение менеджеру о выполнении заказа
            manager = db.query(User).filter(User.id == order.manager_id).first()
            if manager and manager.telegram_id:
                try:
                    await message.bot.send_message(
                        manager.telegram_id,
                        f"✅ Заказ #{order.id} выполнен и отправлен клиенту."
                    )
                except Exception as e:
                    logging.error(f"Ошибка при отправке уведомления менеджеру: {str(e)}")
            
            # Отправляем подтверждение складу
            await message.answer(
                f"✅ Заказ #{order.id} успешно обработан и отмечен как выполненный.",
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
            )
        
        except Exception as e:
            db.rollback()
            logging.error(f"Ошибка при создании CompletedOrder: {str(e)}")
            await message.answer(
                f"❌ Произошла ошибка при обработке заказа: {str(e)}",
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
            )
            return
        
    except Exception as e:
        logging.error(f"Ошибка при подтверждении отгрузки заказа #{order_id}: {str(e)}")
        await message.answer(
            f"❌ Произошла ошибка при обработке заказа: {str(e)}",
            reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
        )
    finally:
        db.close()

@router.message(F.text == "🔙 Назад в админку")
async def handle_back_to_admin(message: Message, state: FSMContext):
    """Обработчик возврата в меню супер-админа"""
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or user.role != UserRole.SUPER_ADMIN:
            await message.answer("У вас нет прав для выполнения этой команды.")
            return
        
        # Очищаем контекст админа
        await state.update_data(is_admin_context=False)
        # Переходим в главное меню супер-админа
        await state.set_state(MenuState.SUPER_ADMIN_MAIN)
        await message.answer(
            "Вы вернулись в меню супер-администратора:",
            reply_markup=get_menu_keyboard(MenuState.SUPER_ADMIN_MAIN)
        )
    finally:
        db.close()

async def check_warehouse_access(message: Message) -> bool:
    """Проверяет, имеет ли пользователь права для роли склада"""
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        # Доступ к остаткам есть у Склада, Производства, Менеджеров по продажам и Суперадмина
        allowed_roles = [UserRole.WAREHOUSE, UserRole.PRODUCTION, UserRole.SUPER_ADMIN, UserRole.SALES_MANAGER]
        if not user or user.role not in allowed_roles:
            await message.answer("У вас нет прав для просмотра остатков.")
            return False
        return True
    finally:
        db.close()

# --- NEW HANDLERS FOR RETURN PROCESSING ---

@router.message(StateFilter(MenuState.WAREHOUSE_MAIN), F.text == "♻️ Запросы на возврат")
async def handle_return_requests(message: Message, state: FSMContext):
    """Displays a list of orders awaiting return confirmation."""
    if not await check_warehouse_access(message):
        return
        
    # Получим роль пользователя для определения правильного состояния для возврата
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        user_role = user.role if user else UserRole.NONE
        return_menu_state = MenuState.WAREHOUSE_MAIN  # По умолчанию для склада
        
        # Установим текущее состояние на просмотр запросов
        await state.set_state(MenuState.WAREHOUSE_RETURN_REQUESTS)
        
        # Запрашиваем запросы на возврат
        return_requests = db.query(CompletedOrder).filter(
            CompletedOrder.status == CompletedOrderStatus.RETURN_REQUESTED.value
        ).options(
            joinedload(CompletedOrder.manager)
        ).order_by(desc(CompletedOrder.completed_at)).limit(30).all() # Limit to 30 requests

        # Определим состояние для возврата в зависимости от роли
        if user_role == UserRole.SALES_MANAGER:
            return_menu_state = MenuState.SALES_MAIN
        elif user_role == UserRole.SUPER_ADMIN:
            # Для суперадмина, проверим, в каком контексте он работает
            state_data = await state.get_data()
            is_admin_context = state_data.get("is_admin_context", False)
            if is_admin_context:
                # Если суперадмин эмулирует склад
                return_menu_state = MenuState.WAREHOUSE_MAIN
            else:
                return_menu_state = MenuState.SUPER_ADMIN_MAIN

        if not return_requests:
            # Если нет запросов, вернемся в соответствующее меню роли
            await message.answer(
                "Нет активных запросов на возврат.",
                reply_markup=get_menu_keyboard(return_menu_state)
            )
            await state.set_state(return_menu_state)
            return

        response = "♻️ Запросы на возврат (последние 30):\n\n"
        for req in return_requests:
            response += f"---\n"
            response += f"Запрос на возврат ID: {req.id} (Исходный заказ #{req.order_id})\n"
            response += f"Дата запроса (примерно): {req.updated_at.strftime('%Y-%m-%d %H:%M') if req.updated_at else 'Неизвестно'}\n"
            response += f"Менеджер: {req.manager.username if req.manager else 'N/A'}\n"

        response += f"\nВведите ID запроса на возврат для просмотра деталей и подтверждения/отклонения.\n"

        if len(response) > 4000:
            response = response[:4000] + "\n... (список слишком длинный)"

        # Сохраним состояние возврата для использования в последующих обработчиках
        await state.update_data(return_menu_state=return_menu_state)

        await message.answer(
            response,
            reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_RETURN_REQUESTS) # Keyboard with Back button
        )

    except Exception as e:
        logging.error(f"Ошибка при получении запросов на возврат: {e}", exc_info=True)
        await message.answer(
            "Произошла ошибка при загрузке запросов на возврат.",
            reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
        )
        await state.set_state(MenuState.WAREHOUSE_MAIN)
    finally:
        db.close()

@router.message(StateFilter(MenuState.WAREHOUSE_RETURN_REQUESTS), F.text.regexp(r'^\d+$'))
async def view_return_request_details(message: Message, state: FSMContext):
    """Displays details of a specific return request with confirmation buttons."""
    if not await check_warehouse_access(message):
        return

    try:
        completed_order_id = int(message.text)
    except ValueError:
        await message.answer("Пожалуйста, введите корректный числовой ID.", reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_RETURN_REQUESTS))
        return

    db = next(get_db())
    try:
        order = db.query(CompletedOrder).options(
            joinedload(CompletedOrder.items),
            joinedload(CompletedOrder.joints),
            joinedload(CompletedOrder.glues),
            joinedload(CompletedOrder.manager),
            joinedload(CompletedOrder.warehouse_user)
        ).filter(
            CompletedOrder.id == completed_order_id,
            CompletedOrder.status == CompletedOrderStatus.RETURN_REQUESTED.value
        ).first()

        if not order:
            await message.answer(f"Запрос на возврат с ID {completed_order_id} не найден или уже обработан.", reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_RETURN_REQUESTS))
            return

        # Format order details (similar to view_completed_order)
        response = f"Детали запроса на возврат ID: {order.id} (Исходный заказ #{order.order_id})\n"
        response += f"Статус: {order.status}\n"
        response += f"Дата завершения заказа: {order.completed_at.strftime('%Y-%m-%d %H:%M')}\n"
        response += f"Клиент: {order.customer_phone}\n"
        response += f"Адрес: {order.delivery_address}\n"
        shipment_date_str = order.shipment_date.strftime('%d.%m.%Y') if order.shipment_date else 'Не указана'
        payment_method_str = order.payment_method if order.payment_method else 'Не указан'
        response += f"🗓 Дата отгрузки: {shipment_date_str}\n"
        response += f"💳 Способ оплаты: {payment_method_str}\n"
        response += f"Монтаж: {'Да' if order.installation_required else 'Нет'}\n"
        response += f"Менеджер: {order.manager.username if order.manager else 'N/A'}\n"
        response += f"Склад (отгрузил): {order.warehouse_user.username if order.warehouse_user else 'N/A'}\n"

        response += "\nВозвращаемая продукция:\n"
        if order.items:
            for item in order.items:
                response += f"- {item.color} ({item.thickness} мм): {item.quantity} шт.\n"
        else: response += "- нет\n"

        response += "\nВозвращаемые стыки:\n"
        if order.joints:
            for joint in order.joints:
                response += f"- {joint.joint_type.name.capitalize()} ({joint.joint_thickness} мм, {joint.joint_color}): {joint.quantity} шт.\n"
        else: response += "- нет\n"

        response += "\nВозвращаемый клей:\n"
        if order.glues:
            for glue_item in order.glues:
                response += f"- {glue_item.quantity} шт.\n"
        else: response += "- нет\n"

        # Create inline keyboard for confirmation/rejection
        keyboard_buttons = [
            InlineKeyboardButton(text="✅ Подтвердить возврат", callback_data=f"confirm_return:{order.id}"),
            InlineKeyboardButton(text="❌ Отклонить возврат", callback_data=f"reject_return:{order.id}")
        ]
        inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[keyboard_buttons])

        # Set state for potential further actions on this order
        await state.set_state(MenuState.VIEW_RETURN_REQUEST)
        await state.update_data(viewed_return_request_id=order.id)

        await message.answer(
            response,
            reply_markup=inline_keyboard
        )
    except Exception as e:
        logging.error(f"Ошибка при просмотре запроса на возврат {completed_order_id}: {e}", exc_info=True)
        await message.answer("Произошла ошибка при загрузке деталей запроса.", reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_RETURN_REQUESTS))
    finally:
        db.close()

@router.callback_query(F.data.startswith("confirm_return:"))
async def process_confirm_return(callback_query: CallbackQuery, state: FSMContext):
    """Handles the confirmation of a return request."""
    completed_order_id = int(callback_query.data.split(":")[1])
    user_id = callback_query.from_user.id
    message = callback_query.message

    db = next(get_db())
    try:
        warehouse_user = db.query(User).filter(User.telegram_id == user_id).first()
        if not warehouse_user or warehouse_user.role not in [UserRole.WAREHOUSE, UserRole.SUPER_ADMIN, UserRole.SALES_MANAGER]:
            await callback_query.answer("У вас нет прав для этого действия.", show_alert=True)
            return

        order = db.query(CompletedOrder).options(
            selectinload(CompletedOrder.items),
            selectinload(CompletedOrder.joints),
            selectinload(CompletedOrder.glues),
            joinedload(CompletedOrder.manager) # Load manager for notification
        ).filter(CompletedOrder.id == completed_order_id).first()

        if not order:
            await callback_query.answer("Запрос на возврат не найден.", show_alert=True)
            return

        if order.status != CompletedOrderStatus.RETURN_REQUESTED.value:
            await callback_query.answer(f"Запрос уже обработан (статус: {order.status}).", show_alert=True)
            return

        # --- Start DB Transaction --- Add items back to stock
        try:
            logging.info(f"Confirming return for CompletedOrder ID: {order.id}. User: {user_id}")
            stock_update_details = []

            # 1. Return Finished Products
            for item in order.items:
                film = db.query(Film).filter(Film.code == item.color).first()
                if film:
                    finished_product = db.query(FinishedProduct).filter(
                        FinishedProduct.film_id == film.id,
                        FinishedProduct.thickness == item.thickness
                    ).first()
                    if finished_product:
                        old_qty = finished_product.quantity
                        finished_product.quantity += item.quantity
                        stock_update_details.append(f"Продукт {item.color} ({item.thickness}мм): +{item.quantity} (было {old_qty})")
                    else:
                        # If product didn't exist, create it (shouldn't happen often)
                        finished_product = FinishedProduct(film_id=film.id, thickness=item.thickness, quantity=item.quantity)
                        db.add(finished_product)
                        stock_update_details.append(f"Продукт {item.color} ({item.thickness}мм): +{item.quantity} (создан)")
                else:
                     logging.warning(f"Film {item.color} not found during return confirmation for order {order.id}")

            # 2. Return Joints
            for joint_item in order.joints:
                joint = db.query(Joint).filter(
                    Joint.type == joint_item.joint_type,
                    Joint.thickness == joint_item.joint_thickness,
                    Joint.color == joint_item.joint_color
                ).first()
                if joint:
                    old_qty = joint.quantity
                    joint.quantity += joint_item.quantity
                    stock_update_details.append(f"Стык {joint_item.joint_type.name} ({joint_item.joint_thickness}мм, {joint_item.joint_color}): +{joint_item.quantity} (было {old_qty})")
                else:
                    # Create if doesn't exist
                    joint = Joint(type=joint_item.joint_type, thickness=joint_item.joint_thickness, color=joint_item.joint_color, quantity=joint_item.quantity)
                    db.add(joint)
                    stock_update_details.append(f"Стык {joint_item.joint_type.name} ({joint_item.joint_thickness}мм, {joint_item.joint_color}): +{joint_item.quantity} (создан)")

            # 3. Return Glue
            for glue_item in order.glues:
                glue = db.query(Glue).first()
                if glue:
                    old_qty = glue.quantity
                    glue.quantity += glue_item.quantity
                    stock_update_details.append(f"Клей: +{glue_item.quantity} (было {old_qty})")
                else:
                    glue = Glue(quantity=glue_item.quantity)
                    db.add(glue)
                    stock_update_details.append(f"Клей: +{glue_item.quantity} (создан)")

            # Update order status
            order.status = CompletedOrderStatus.RETURNED.value
            order.updated_at = datetime.utcnow() # Explicitly update timestamp

            # Log operation (optional but recommended)
            # TODO: Consider adding a specific 'return' operation type?
            operation_details = {
                "completed_order_id": order.id,
                "original_order_id": order.order_id,
                "confirmed_by": warehouse_user.id,
                "stock_updates": stock_update_details
            }
            op = Operation(
                user_id=warehouse_user.id,
                operation_type="order_return_confirmed", 
                quantity=1, # Represents one order return
                details=json.dumps(operation_details)
            )
            db.add(op)

            db.commit()
            logging.info(f"Return confirmed and stock updated for CompletedOrder ID: {order.id}")

            await callback_query.answer("✅ Возврат подтвержден, остатки обновлены.", show_alert=False)

            # Notify manager
            if order.manager and order.manager.telegram_id:
                try:
                    await message.bot.send_message(
                        order.manager.telegram_id,
                        f"♻️ Возврат по заказу #{order.order_id} (Запрос ID: {order.id}) был подтвержден складом."
                    )
                except Exception as e:
                    logging.error(f"Failed to send return confirmation notification to manager {order.manager.telegram_id}: {e}")

            # Update message text
            new_text = message.text.replace(f"Статус: {CompletedOrderStatus.RETURN_REQUESTED.value}", f"Статус: {CompletedOrderStatus.RETURNED.value}")
            new_text += "\n\n✅ Возврат подтвержден складом."
            await message.edit_text(new_text, reply_markup=None)
            
            # Return to the list of return requests or appropriate menu based on user role
            state_data = await state.get_data()
            return_menu_state = state_data.get("return_menu_state", MenuState.WAREHOUSE_MAIN)

            # If returning to main menu of role, go directly there
            if return_menu_state in [MenuState.WAREHOUSE_MAIN, MenuState.SALES_MAIN, MenuState.SUPER_ADMIN_MAIN]:
                await state.set_state(return_menu_state)
                await message.answer("Возврат подтвержден. Возвращаемся в главное меню.", 
                                     reply_markup=get_menu_keyboard(return_menu_state))
            else:
                # Otherwise return to the list of return requests
                await state.set_state(MenuState.WAREHOUSE_RETURN_REQUESTS)
                await handle_return_requests(message, state)

        except Exception as db_exc:
            db.rollback()
            logging.error(f"DB Error during return confirmation for order {order.id}: {db_exc}", exc_info=True)
            await callback_query.answer("❌ Ошибка базы данных при обновлении остатков.", show_alert=True)
        # --- End DB Transaction ---

    except Exception as outer_exc:
        logging.error(f"Outer error during return confirmation processing for order {completed_order_id}: {outer_exc}", exc_info=True)
        await callback_query.answer("❌ Произошла общая ошибка.", show_alert=True)
    finally:
        db.close()

@router.callback_query(F.data.startswith("reject_return:"))
async def process_reject_return(callback_query: CallbackQuery, state: FSMContext):
    """Handles the rejection of a return request."""
    completed_order_id = int(callback_query.data.split(":")[1])
    user_id = callback_query.from_user.id
    message = callback_query.message

    db = next(get_db())
    try:
        warehouse_user = db.query(User).filter(User.telegram_id == user_id).first()
        if not warehouse_user or warehouse_user.role not in [UserRole.WAREHOUSE, UserRole.SUPER_ADMIN, UserRole.SALES_MANAGER]:
            await callback_query.answer("У вас нет прав для этого действия.", show_alert=True)
            return

        order = db.query(CompletedOrder).options(
            joinedload(CompletedOrder.manager) # Load manager for notification
        ).filter(CompletedOrder.id == completed_order_id).first()

        if not order:
            await callback_query.answer("Запрос на возврат не найден.", show_alert=True)
            return

        if order.status != CompletedOrderStatus.RETURN_REQUESTED.value:
            await callback_query.answer(f"Запрос уже обработан (статус: {order.status}).", show_alert=True)
            return

        # --- Start DB Transaction ---
        try:
            logging.info(f"Rejecting return for CompletedOrder ID: {order.id}. User: {user_id}")
            # Change status back to COMPLETED or to RETURN_REJECTED
            order.status = CompletedOrderStatus.RETURN_REJECTED.value # Using the specific rejected status
            order.updated_at = datetime.utcnow()

            # Log operation (optional)
            operation_details = {
                 "completed_order_id": order.id,
                 "original_order_id": order.order_id,
                 "rejected_by": warehouse_user.id
            }
            op = Operation(
                user_id=warehouse_user.id,
                operation_type="order_return_rejected",
                quantity=1, # Represents one order return rejection
                details=json.dumps(operation_details)
            )
            db.add(op)

            db.commit()
            logging.info(f"Return rejected for CompletedOrder ID: {order.id}")

            await callback_query.answer("❌ Возврат отклонен.", show_alert=False)

            # Notify manager
            if order.manager and order.manager.telegram_id:
                try:
                    await message.bot.send_message(
                        order.manager.telegram_id,
                        f"❌ Возврат по заказу #{order.order_id} (Запрос ID: {order.id}) был отклонен складом."
                    )
                except Exception as e:
                    logging.error(f"Failed to send return rejection notification to manager {order.manager.telegram_id}: {e}")

            # Update message text
            new_text = message.text.replace(f"Статус: {CompletedOrderStatus.RETURN_REQUESTED.value}", f"Статус: {CompletedOrderStatus.RETURN_REJECTED.value}")
            new_text += "\n\n❌ Возврат отклонен складом."
            await message.edit_text(new_text, reply_markup=None)
            
            # Return to the list of return requests or appropriate menu based on user role
            state_data = await state.get_data()
            return_menu_state = state_data.get("return_menu_state", MenuState.WAREHOUSE_MAIN)

            # If returning to main menu of role, go directly there
            if return_menu_state in [MenuState.WAREHOUSE_MAIN, MenuState.SALES_MAIN, MenuState.SUPER_ADMIN_MAIN]:
                await state.set_state(return_menu_state)
                await message.answer("Возврат отклонен. Возвращаемся в главное меню.", 
                                     reply_markup=get_menu_keyboard(return_menu_state))
            else:
                # Otherwise return to the list of return requests
                await state.set_state(MenuState.WAREHOUSE_RETURN_REQUESTS)
                await handle_return_requests(message, state)

        except Exception as db_exc:
            db.rollback()
            logging.error(f"DB Error during return rejection for order {order.id}: {db_exc}", exc_info=True)
            await callback_query.answer("❌ Ошибка базы данных при отклонении возврата.", show_alert=True)
        # --- End DB Transaction ---

    except Exception as outer_exc:
        logging.error(f"Outer error during return rejection processing for order {completed_order_id}: {outer_exc}", exc_info=True)
        await callback_query.answer("❌ Произошла общая ошибка.", show_alert=True)
    finally:
        db.close() 

@router.message(F.text == "🔖 Забронированные заказы", StateFilter(MenuState.WAREHOUSE_MAIN))
async def handle_reserved_orders_warehouse(message: Message, state: FSMContext):
    """Отображает список забронированных заказов для складского работника"""
    if not await check_warehouse_access(message):
        return
    
    db = next(get_db())
    try:
        # Получаем все забронированные заказы со статусом RESERVED
        reserved_orders = db.query(Order).filter(
            Order.status == OrderStatus.RESERVED.value
        ).options(
            joinedload(Order.products),
            joinedload(Order.joints),
            joinedload(Order.glues),
            joinedload(Order.manager)
        ).order_by(desc(Order.created_at)).all()
        
        if not reserved_orders:
            await message.answer(
                "🔖 Нет забронированных заказов.",
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
            )
            return
        
        response = "🔖 Забронированные заказы:\n\n"
        keyboard_buttons = []
        
        for order in reserved_orders:
            response += f"---\n"
            response += f"Заказ #{order.id}\n"
            response += f"Дата создания: {order.created_at.strftime('%Y-%m-%d %H:%M')}\n"
            response += f"Менеджер: {order.manager.username if order.manager else 'Неизвестно'}\n"
            response += f"Клиент: {order.customer_phone}\n"
            response += f"Адрес: {order.delivery_address}\n"
            shipment_date_str = order.shipment_date.strftime('%d.%m.%Y') if order.shipment_date else 'Не указана'
            response += f"🗓 Дата отгрузки: {shipment_date_str}\n"
            
            # Добавляем строку с продукцией (кратко)
            products_count = len(order.products) if order.products else 0
            joints_count = len(order.joints) if order.joints else 0
            glue_count = sum(g.quantity for g in order.glues) if order.glues else 0
            
            response += f"📦 Продукция: {products_count} позиций, "
            response += f"🔗 Стыки: {joints_count} позиций, "
            response += f"🧴 Клей: {glue_count} шт.\n\n"
            
            # Добавляем кнопку для просмотра деталей заказа
            keyboard_buttons.append([KeyboardButton(text=f"🔖 Заказ #{order.id}")])
        
        # Добавляем кнопку "Назад"
        keyboard_buttons.append([KeyboardButton(text="◀️ Назад")])
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=keyboard_buttons,
            resize_keyboard=True
        )
        
        await message.answer(response, reply_markup=keyboard)
        await state.set_state(MenuState.WAREHOUSE_RESERVED_ORDERS)
        
    except Exception as e:
        logging.error(f"Ошибка при получении забронированных заказов: {e}", exc_info=True)
        await message.answer(
            "Произошла ошибка при загрузке забронированных заказов.",
            reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
        )
    finally:
        db.close()

@router.message(StateFilter(MenuState.WAREHOUSE_RESERVED_ORDERS), F.text.regexp(r"^🔖 Заказ #(\d+)$"))
async def view_reserved_order_warehouse(message: Message, state: FSMContext):
    """Отображает детали забронированного заказа и предлагает подтвердить его"""
    if not await check_warehouse_access(message):
        return
    
    try:
        # Извлекаем ID заказа из сообщения
        order_id_match = re.search(r"^🔖 Заказ #(\d+)$", message.text)
        if not order_id_match:
            await message.answer(
                "Неверный формат ID заказа.",
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_RESERVED_ORDERS)
            )
            return
        
        order_id = int(order_id_match.group(1))
        
        db = next(get_db())
        try:
            # Получаем заказ
            order = db.query(Order).options(
                joinedload(Order.products),
                joinedload(Order.joints),
                joinedload(Order.glues),
                joinedload(Order.manager)
            ).filter(
                Order.id == order_id,
                Order.status == OrderStatus.RESERVED.value
            ).first()
            
            if not order:
                await message.answer(
                    f"Забронированный заказ с ID {order_id} не найден или уже не имеет статус 'Забронирован'.",
                    reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_RESERVED_ORDERS)
                )
                return
            
            # Формируем детальный ответ с информацией о заказе
            response = f"🔖 Детали забронированного заказа #{order.id}\n\n"
            response += f"Дата создания: {order.created_at.strftime('%Y-%m-%d %H:%M')}\n"
            response += f"Менеджер: {order.manager.username if order.manager else 'Неизвестно'}\n"
            response += f"Клиент: {order.customer_phone}\n"
            response += f"Адрес: {order.delivery_address}\n"
            shipment_date_str = order.shipment_date.strftime('%d.%m.%Y') if order.shipment_date else 'Не указана'
            payment_method_str = order.payment_method if order.payment_method else 'Не указан'
            response += f"🗓 Дата отгрузки: {shipment_date_str}\n"
            response += f"💳 Способ оплаты: {payment_method_str}\n"
            response += f"Монтаж: {'Да' if order.installation_required else 'Нет'}\n\n"
            
            response += "📦 Продукция:\n"
            if order.products:
                for item in order.products:
                    response += f"- {item.color} ({item.thickness} мм): {item.quantity} шт.\n"
            else:
                response += "- нет\n"
            
            response += "\n🔗 Стыки:\n"
            if order.joints:
                for joint in order.joints:
                    joint_type_name = "Другой"
                    if joint.joint_type == JointType.SIMPLE.value:
                        joint_type_name = "Простой"
                    elif joint.joint_type == JointType.BUTTERFLY.value:
                        joint_type_name = "Бабочка"
                    elif joint.joint_type == JointType.CLOSING.value:
                        joint_type_name = "Замыкающий"
                    
                    response += f"- {joint_type_name} ({joint.joint_thickness} мм, {joint.joint_color}): {joint.quantity} шт.\n"
            else:
                response += "- нет\n"
            
            response += "\n🧴 Клей:\n"
            if order.glues:
                for glue in order.glues:
                    response += f"- {glue.quantity} шт.\n"
            else:
                response += "- нет\n"
            
            # Добавляем клавиатуру с кнопками для управления заказом
            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text=f"✅ Подтвердить заказ #{order.id}"), KeyboardButton(text=f"❌ Отклонить заказ #{order.id}")],
                    [KeyboardButton(text="◀️ К списку забронированных")]
                ],
                resize_keyboard=True
            )
            
            await message.answer(response, reply_markup=keyboard)
            await state.set_state(MenuState.WAREHOUSE_VIEW_RESERVED_ORDER)
            await state.update_data(viewed_reserved_order_id=order.id)
            
        except Exception as e:
            logging.error(f"Ошибка при просмотре забронированного заказа {order_id}: {e}", exc_info=True)
            await message.answer(
                "Произошла ошибка при загрузке деталей заказа.",
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_RESERVED_ORDERS)
            )
        finally:
            db.close()
    except ValueError:
        await message.answer(
            "Неверный формат ID заказа.",
            reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_RESERVED_ORDERS)
        )

@router.message(StateFilter(MenuState.WAREHOUSE_VIEW_RESERVED_ORDER), F.text.regexp(r"^✅ Подтвердить заказ #(\d+)$"))
async def confirm_reserved_order_warehouse(message: Message, state: FSMContext):
    """Подтверждает забронированный заказ и меняет его статус на NEW"""
    if not await check_warehouse_access(message):
        return
    
    try:
        # Извлекаем ID заказа из сообщения
        order_id_match = re.search(r"^✅ Подтвердить заказ #(\d+)$", message.text)
        if not order_id_match:
            await message.answer(
                "Неверный формат ID заказа.",
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_RESERVED_ORDERS)
            )
            return
        
        order_id = int(order_id_match.group(1))
        
        db = next(get_db())
        try:
            # Получаем заказ
            order = db.query(Order).filter(
                Order.id == order_id,
                Order.status == OrderStatus.RESERVED.value
            ).first()
            
            if not order:
                await message.answer(
                    f"Забронированный заказ с ID {order_id} не найден или уже не имеет статус 'Забронирован'.",
                    reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_RESERVED_ORDERS)
                )
                return
            
            # Меняем статус заказа на NEW
            order.status = OrderStatus.NEW.value
            db.commit()
            
            # Отправляем уведомление менеджеру
            try:
                manager = db.query(User).filter(User.id == order.manager_id).first()
                if manager and manager.telegram_id:
                    await message.bot.send_message(
                        manager.telegram_id,
                        f"✅ Ваш забронированный заказ #{order.id} подтвержден складом и добавлен в очередь на обработку."
                    )
            except Exception as notify_error:
                logging.error(f"Ошибка при отправке уведомления менеджеру: {notify_error}")
            
            await message.answer(
                f"✅ Заказ #{order_id} успешно подтвержден и добавлен в очередь на обработку.",
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
            )
            await state.set_state(MenuState.WAREHOUSE_MAIN)
            
        except Exception as e:
            db.rollback()
            logging.error(f"Ошибка при подтверждении забронированного заказа {order_id}: {e}", exc_info=True)
            await message.answer(
                f"❌ Произошла ошибка при подтверждении заказа: {str(e)}",
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
            )
            await state.set_state(MenuState.WAREHOUSE_MAIN)
        finally:
            db.close()
    except ValueError:
        await message.answer(
            "Неверный формат ID заказа.",
            reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_RESERVED_ORDERS)
        )

@router.message(StateFilter(MenuState.WAREHOUSE_VIEW_RESERVED_ORDER), F.text.regexp(r"^❌ Отклонить заказ #(\d+)$"))
async def reject_reserved_order_warehouse(message: Message, state: FSMContext):
    """Отклоняет забронированный заказ и меняет его статус на CANCELLED"""
    if not await check_warehouse_access(message):
        return
    
    try:
        # Извлекаем ID заказа из сообщения
        order_id_match = re.search(r"^❌ Отклонить заказ #(\d+)$", message.text)
        if not order_id_match:
            await message.answer(
                "Неверный формат ID заказа.",
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_RESERVED_ORDERS)
            )
            return
        
        order_id = int(order_id_match.group(1))
        
        db = next(get_db())
        try:
            # Получаем заказ
            order = db.query(Order).filter(
                Order.id == order_id,
                Order.status == OrderStatus.RESERVED.value
            ).first()
            
            if not order:
                await message.answer(
                    f"Забронированный заказ с ID {order_id} не найден или уже не имеет статус 'Забронирован'.",
                    reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_RESERVED_ORDERS)
                )
                return
            
            # Меняем статус заказа на CANCELLED
            order.status = OrderStatus.CANCELLED.value
            db.commit()
            
            # Отправляем уведомление менеджеру
            try:
                manager = db.query(User).filter(User.id == order.manager_id).first()
                if manager and manager.telegram_id:
                    await message.bot.send_message(
                        manager.telegram_id,
                        f"❌ Ваш забронированный заказ #{order.id} был отклонен складом."
                    )
            except Exception as notify_error:
                logging.error(f"Ошибка при отправке уведомления менеджеру: {notify_error}")
            
            await message.answer(
                f"❌ Заказ #{order_id} отклонен.",
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
            )
            await state.set_state(MenuState.WAREHOUSE_MAIN)
            
        except Exception as e:
            db.rollback()
            logging.error(f"Ошибка при отклонении забронированного заказа {order_id}: {e}", exc_info=True)
            await message.answer(
                f"❌ Произошла ошибка при отклонении заказа: {str(e)}",
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
            )
            await state.set_state(MenuState.WAREHOUSE_MAIN)
        finally:
            db.close()
    except ValueError:
        await message.answer(
            "Неверный формат ID заказа.",
            reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_RESERVED_ORDERS)
        )

@router.message(StateFilter(MenuState.WAREHOUSE_VIEW_RESERVED_ORDER), F.text == "◀️ К списку забронированных")
async def back_to_reserved_orders_list(message: Message, state: FSMContext):
    """Возвращает к списку забронированных заказов"""
    if not await check_warehouse_access(message):
        return
    
    await handle_reserved_orders_warehouse(message, state)