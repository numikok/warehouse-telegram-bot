from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from models import User, UserRole, Film, Panel, Joint, Glue, Operation, FinishedProduct, Order, CompletedOrder, OrderStatus, JointType
from database import get_db
import json
import logging
from navigation import MenuState, get_menu_keyboard, go_back

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
        
    await display_active_orders(message)

async def display_active_orders(message: Message):
    """Отображает список активных заказов для подтверждения отгрузки"""
    db = next(get_db())
    try:
        # Получаем все активные заказы со статусом NEW
        orders = db.query(Order).filter(Order.status == OrderStatus.NEW).all()
        
        if not orders:
            await message.answer(
                "📦 Нет активных заказов для отгрузки.",
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
            )
            return
            
        # Формируем сообщение со списком заказов
        response = "📦 Активные заказы для отгрузки:\n\n"
        
        for order in orders:
            # Получаем имя менеджера
            manager = db.query(User).filter(User.id == order.manager_id).first()
            manager_name = manager.username if manager else "Неизвестный менеджер"
            
            # Формируем информацию о продуктах
            products_info = ""
            if order.products:
                products_info = "🎨 Продукция:\n"
                for product in order.products:
                    film = db.query(Film).filter(Film.id == product.film_id).first()
                    film_code = film.code if film else "Неизвестный"
                    products_info += f"  • {film_code}, толщина {product.thickness} мм: {product.quantity} шт.\n"
            else:
                # Используем старое поле для обратной совместимости
                products_info = f"🎨 Пленка: {order.film_code}, {order.panel_quantity} шт.\n"
            
            # Формируем информацию о стыках
            joints_info = ""
            if order.joints:
                joints_info = "🔗 Стыки:\n"
                for joint in order.joints:
                    joint_type_text = ""
                    if joint.joint_type == JointType.BUTTERFLY:
                        joint_type_text = "Бабочка"
                    elif joint.joint_type == JointType.SIMPLE:
                        joint_type_text = "Простые"
                    elif joint.joint_type == JointType.CLOSING:
                        joint_type_text = "Замыкающие"
                    joints_info += f"  • {joint_type_text}, {joint.joint_color}: {joint.quantity} шт.\n"
            elif order.joint_quantity > 0:
                # Используем старые поля для обратной совместимости
                joint_type_text = ""
                if order.joint_type == JointType.BUTTERFLY:
                    joint_type_text = "Бабочка"
                elif order.joint_type == JointType.SIMPLE:
                    joint_type_text = "Простые"
                elif order.joint_type == JointType.CLOSING:
                    joint_type_text = "Замыкающие"
                joints_info = f"🔗 Стыки: {joint_type_text}, {order.joint_color}: {order.joint_quantity} шт.\n"
            else:
                joints_info = "🔗 Стыки: Нет\n"
            
            response += (
                f"📝 Заказ #{order.id}\n"
                f"📆 Дата: {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                f"👤 Менеджер: {manager_name}\n"
                f"{products_info}"
                f"{joints_info}"
                f"🧴 Клей: {order.glue_quantity} шт.\n"
                f"🔧 Монтаж: {'Требуется' if order.installation_required else 'Не требуется'}\n"
                f"📞 Телефон: {order.customer_phone}\n"
                f"🚚 Адрес: {order.delivery_address}\n"
                f"-----\n"
                f"✅ Для подтверждения отгрузки заказа #{order.id} отправьте:\n/confirm_{order.id}\n\n"
            )
        
        await message.answer(
            response,
            reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_ORDERS)
        )
    finally:
        db.close()

@router.message(F.text == "📦 Мои заказы")
async def handle_orders(message: Message, state: FSMContext):
    if not await check_warehouse_access(message):
        return
        
    db = next(get_db())
    try:
        state_data = await state.get_data()
        is_admin_context = state_data.get("is_admin_context", False)
        
        # Получаем заказы со статусом "pending" или "in_progress"
        orders = db.query(Order).filter(
            Order.status.in_([OrderStatus.NEW, OrderStatus.IN_PROGRESS])
        ).order_by(Order.created_at.desc()).all()
        
        if not orders:
            await message.answer(
                "Нет активных заказов.",
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_ORDERS, is_admin_context)
            )
            return
            
        response = "📦 Активные заказы:\n\n"
        
        for order in orders:
            # Получаем имя менеджера, создавшего заказ
            manager = db.query(User).filter(User.id == order.manager_id).first()
            manager_name = manager.username if manager else "Неизвестный менеджер"
            
            # Формируем информацию о продуктах
            products_info = ""
            if order.products:
                products_info = "- Продукция:\n"
                for product in order.products:
                    film = db.query(Film).filter(Film.id == product.film_id).first()
                    film_code = film.code if film else "Неизвестный"
                    products_info += f"  • {film_code}, толщина {product.thickness} мм: {product.quantity} шт.\n"
            else:
                # Используем старое поле для обратной совместимости
                products_info = f"- Код пленки: {order.film_code}\n- Количество панелей: {order.panel_quantity} шт.\n"
            
            # Формируем информацию о стыках
            joints_info = ""
            if order.joints:
                joints_info = "- Стыки:\n"
                for joint in order.joints:
                    joint_type_text = ""
                    if joint.joint_type == JointType.BUTTERFLY:
                        joint_type_text = "Бабочка"
                    elif joint.joint_type == JointType.SIMPLE:
                        joint_type_text = "Простые"
                    elif joint.joint_type == JointType.CLOSING:
                        joint_type_text = "Замыкающие"
                    joints_info += f"  • {joint_type_text}, {joint.joint_color}: {joint.quantity} шт.\n"
            elif order.joint_quantity > 0:
                # Используем старые поля для обратной совместимости
                joint_type_text = ""
                if order.joint_type == JointType.BUTTERFLY:
                    joint_type_text = "Бабочка"
                elif order.joint_type == JointType.SIMPLE:
                    joint_type_text = "Простые"
                elif order.joint_type == JointType.CLOSING:
                    joint_type_text = "Замыкающие"
                joints_info = f"- Стыки: {joint_type_text}, {order.joint_color}: {order.joint_quantity} шт.\n"
            else:
                joints_info = "- Стыки: Нет\n"
            
            response += (
                f"📝 Заказ #{order.id}\n"
                f"{products_info}"
                f"{joints_info}"
                f"- Клей: {order.glue_quantity} шт.\n"
                f"- Монтаж: {'Требуется' if order.installation_required else 'Не требуется'}\n"
                f"- Телефон клиента: {order.customer_phone}\n"
                f"- Адрес доставки: {order.delivery_address}\n"
                f"- Статус: {order.status.value}\n"
                f"- Дата создания: {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                f"- Менеджер: {manager_name}\n\n"
            )
        
        await message.answer(
            response,
            reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_ORDERS, is_admin_context)
        )
        
        # Запрашиваем номер заказа для подтверждения отгрузки
        await message.answer(
            "Введите номер заказа для подтверждения отгрузки или нажмите 'Назад' для возврата в меню:",
            reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_ORDERS, is_admin_context)
        )
        await state.set_state(WarehouseStates.waiting_for_order_id)
    finally:
        db.close()

@router.message(F.text == "📦 Остатки")
async def handle_stock(message: Message, state: FSMContext):
    await state.set_state(MenuState.WAREHOUSE_STOCK)
    await cmd_stock(message, state)

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    if not await check_warehouse_access(message):
        return
    
    await state.set_state(MenuState.WAREHOUSE_MAIN)
    await message.answer(
        "Выберите действие:",
        reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
    )

@router.message(F.text == "◀️ Назад")
async def handle_back(message: Message, state: FSMContext):
    """Обработка нажатия на кнопку 'Назад'"""
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
    """Обрабатывает подтверждение отгрузки заказа"""
    db = next(get_db())
    try:
        # Получаем заказ из базы данных
        order = db.query(Order).filter(
            Order.id == order_id,
            Order.status == OrderStatus.NEW
        ).first()
        
        if not order:
            await message.answer(
                f"❌ Заказ #{order_id} не найден или уже выполнен.",
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_ORDERS)
            )
            return
        
        # Проверяем наличие материалов
        missing_materials = []
        
        # Проверяем продукты (новый способ через отношения)
        if order.products:
            for product in order.products:
                if product.is_finished:
                    # Проверяем наличие готовой продукции
                    finished_product = db.query(FinishedProduct).filter(
                        FinishedProduct.film_id == product.film_id,
                        FinishedProduct.thickness == product.thickness
                    ).first()
                    
                    film = db.query(Film).filter(Film.id == product.film_id).first()
                    film_code = film.code if film else "Неизвестный"
                    
                    if not finished_product or finished_product.quantity < product.quantity:
                        available = finished_product.quantity if finished_product else 0
                        missing_materials.append(f"Продукция {film_code} (толщина {product.thickness} мм): требуется {product.quantity} шт., доступно {available} шт.")
        else:
            # Поддержка обратной совместимости для старого способа
            finished_product = db.query(FinishedProduct).join(Film).filter(
                Film.code == order.film_code,
                FinishedProduct.thickness == order.panel_thickness
            ).first()
            
            if not finished_product or finished_product.quantity < order.panel_quantity:
                available = finished_product.quantity if finished_product else 0
                missing_materials.append(f"Пленка {order.film_code}: требуется {order.panel_quantity} шт., доступно {available} шт.")
        
        # Проверяем стыки (новый способ через отношения)
        if order.joints:
            for order_joint in order.joints:
                joint = db.query(Joint).filter(
                    Joint.type == order_joint.joint_type,
                    Joint.color == order_joint.joint_color,
                    Joint.thickness == order.panel_thickness  # Используем толщину из заказа
                ).first()
                
                if not joint or joint.quantity < order_joint.quantity:
                    available = joint.quantity if joint else 0
                    joint_type_text = ""
                    if order_joint.joint_type == JointType.BUTTERFLY:
                        joint_type_text = "Бабочка"
                    elif order_joint.joint_type == JointType.SIMPLE:
                        joint_type_text = "Простые"
                    elif order_joint.joint_type == JointType.CLOSING:
                        joint_type_text = "Замыкающие"
                    missing_materials.append(f"Стыки {joint_type_text}, {order_joint.joint_color}: требуется {order_joint.quantity} шт., доступно {available} шт.")
        elif order.joint_quantity > 0:
            # Поддержка обратной совместимости для старого способа
            joint = db.query(Joint).filter(
                Joint.type == order.joint_type,
                Joint.color == order.joint_color,
                Joint.thickness == order.panel_thickness
            ).first()
            
            if not joint or joint.quantity < order.joint_quantity:
                available = joint.quantity if joint else 0
                missing_materials.append(f"Стыки {order.joint_color}: требуется {order.joint_quantity} шт., доступно {available} шт.")
        
        # Проверяем клей
        if order.glue_quantity > 0:
            glue = db.query(Glue).first()
            
            if not glue or glue.quantity < order.glue_quantity:
                available = glue.quantity if glue else 0
                missing_materials.append(f"Клей: требуется {order.glue_quantity} шт., доступно {available} шт.")
        
        # Если не хватает материалов, сообщаем об этом
        if missing_materials:
            await message.answer(
                f"❌ Не хватает материалов для выполнения заказа #{order_id}:\n\n" + "\n".join(missing_materials),
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_ORDERS)
            )
            return
        
        # Получаем пользователя-складовщика
        warehouse_user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        
        # Списываем материалы
        if order.products:
            for product in order.products:
                if product.is_finished:
                    finished_product = db.query(FinishedProduct).filter(
                        FinishedProduct.film_id == product.film_id,
                        FinishedProduct.thickness == product.thickness
                    ).first()
                    
                    if finished_product:
                        finished_product.quantity -= product.quantity
        else:
            # Поддержка обратной совместимости
            finished_product = db.query(FinishedProduct).join(Film).filter(
                Film.code == order.film_code,
                FinishedProduct.thickness == order.panel_thickness
            ).first()
            
            if finished_product:
                finished_product.quantity -= order.panel_quantity
        
        # Списываем стыки
        if order.joints:
            for order_joint in order.joints:
                joint = db.query(Joint).filter(
                    Joint.type == order_joint.joint_type,
                    Joint.color == order_joint.joint_color,
                    Joint.thickness == order.panel_thickness
                ).first()
                
                if joint:
                    joint.quantity -= order_joint.quantity
        elif order.joint_quantity > 0:
            # Поддержка обратной совместимости
            joint = db.query(Joint).filter(
                Joint.type == order.joint_type,
                Joint.color == order.joint_color,
                Joint.thickness == order.panel_thickness
            ).first()
            
            if joint:
                joint.quantity -= order.joint_quantity
        
        # Списываем клей
        if order.glue_quantity > 0:
            glue = db.query(Glue).first()
            if glue:
                glue.quantity -= order.glue_quantity
        
        # Создаем запись о выполненном заказе
        completed_order = CompletedOrder(
            order_id=order.id,
            manager_id=order.manager_id,
            warehouse_user_id=warehouse_user.id,
            film_code=order.film_code,
            panel_quantity=order.panel_quantity,
            panel_thickness=order.panel_thickness,
            joint_type=order.joint_type,
            joint_color=order.joint_color,
            joint_quantity=order.joint_quantity,
            glue_quantity=order.glue_quantity,
            installation_required=order.installation_required,
            customer_phone=order.customer_phone,
            delivery_address=order.delivery_address
        )
        
        # Добавляем все продукты из заказа в выполненный заказ
        if order.products:
            for product in order.products:
                film = db.query(Film).filter(Film.id == product.film_id).first()
                if film:
                    completed_order_film = CompletedOrderFilm(
                        order_id=completed_order.id,
                        film_code=film.code,
                        quantity=product.quantity
                    )
                    db.add(completed_order_film)
        
        # Добавляем все стыки из заказа в выполненный заказ
        if order.joints:
            for order_joint in order.joints:
                completed_order_joint = CompletedOrderJoint(
                    order_id=completed_order.id,
                    joint_type=order_joint.joint_type,
                    joint_color=order_joint.joint_color,
                    quantity=order_joint.quantity
                )
                db.add(completed_order_joint)
        
        # Меняем статус заказа на COMPLETED
        order.status = OrderStatus.COMPLETED
        order.completed_at = completed_order.completed_at  # Устанавливаем дату завершения
        
        # Сохраняем изменения
        db.add(completed_order)
        db.commit()
        
        # Отправляем уведомление менеджеру
        manager = db.query(User).filter(User.id == order.manager_id).first()
        if manager:
            try:
                # Формируем информацию о продуктах
                products_info = ""
                if order.products:
                    for product in order.products:
                        film = db.query(Film).filter(Film.id == product.film_id).first()
                        film_code = film.code if film else "Неизвестный"
                        products_info += f"- {film_code}, толщина {product.thickness} мм: {product.quantity} шт.\n"
                else:
                    products_info = f"- {order.film_code}: {order.panel_quantity} шт.\n"
                
                # Формируем информацию о стыках
                joints_info = ""
                if order.joints:
                    for joint in order.joints:
                        joint_type_text = ""
                        if joint.joint_type == JointType.BUTTERFLY:
                            joint_type_text = "Бабочка"
                        elif joint.joint_type == JointType.SIMPLE:
                            joint_type_text = "Простые"
                        elif joint.joint_type == JointType.CLOSING:
                            joint_type_text = "Замыкающие"
                        joints_info += f"- {joint_type_text}, {joint.joint_color}: {joint.quantity} шт.\n"
                elif order.joint_quantity > 0:
                    joint_type_text = ""
                    if order.joint_type == JointType.BUTTERFLY:
                        joint_type_text = "Бабочка"
                    elif order.joint_type == JointType.SIMPLE:
                        joint_type_text = "Простые"
                    elif order.joint_type == JointType.CLOSING:
                        joint_type_text = "Замыкающие"
                    joints_info = f"- {joint_type_text}, {order.joint_color}: {order.joint_quantity} шт.\n"
                
                await message.bot.send_message(
                    chat_id=manager.telegram_id,
                    text=(
                        f"✅ Заказ #{order_id} отгружен!\n\n"
                        f"Детали заказа:\n"
                        f"🎨 Продукция:\n{products_info}"
                        f"🔗 Стыки:\n{joints_info if joints_info else 'Нет'}\n"
                        f"🧴 Клей: {order.glue_quantity} шт.\n"
                        f"🔧 Монтаж: {'Требуется' if order.installation_required else 'Не требуется'}\n"
                        f"📞 Телефон клиента: {order.customer_phone}\n"
                        f"🚚 Адрес доставки: {order.delivery_address}"
                    )
                )
            except Exception as e:
                logging.error(f"Не удалось отправить уведомление менеджеру {manager.telegram_id}: {str(e)}")
        
        # Отправляем подтверждение складовщику
        await message.answer(
            f"✅ Заказ №{order_id} успешно отгружен и добавлен в список выполненных заказов.",
            reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
        )
        
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
        
        if not user or user.role not in [UserRole.WAREHOUSE, UserRole.SUPER_ADMIN]:
            await message.answer("У вас нет прав для выполнения этой команды.")
            return False
        return True
    finally:
        db.close() 