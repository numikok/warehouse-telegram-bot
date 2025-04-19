from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from models import User, UserRole, Film, Panel, Joint, Glue, FinishedProduct, Operation, JointType, Order, ProductionOrder, OrderStatus, OrderJoint, OrderGlue, OperationType, OrderItem
from database import get_db
import json
import logging
from navigation import MenuState, get_menu_keyboard, go_back
import re
from states import SalesStates
from database import get_db
import json
import logging
from navigation import MenuState, get_menu_keyboard, go_back
import re
from states import SalesStates

router = Router()

def get_joint_type_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🦋 Бабочка")],
            [KeyboardButton(text="🔄 Простые")],
            [KeyboardButton(text="🔒 Замыкающие")],
            [KeyboardButton(text="◀️ Назад")]
        ],
        resize_keyboard=True
    )

def get_joint_thickness_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="0.5")],
            [KeyboardButton(text="0.8")],
            [KeyboardButton(text="◀️ Назад")]
        ],
        resize_keyboard=True
    )

async def check_sales_access(message: Message) -> bool:
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or (user.role != UserRole.SALES_MANAGER and user.role != UserRole.SUPER_ADMIN):
            await message.answer("У вас нет прав для выполнения этой команды.")
            return False
        return True
    finally:
        db.close()

@router.message(F.text == "📝 Составить заказ")
async def handle_create_order(message: Message, state: FSMContext):
    """Обработчик для создания нового заказа с выбором продуктов"""
    if not await check_sales_access(message):
        return
    
    # Получаем флаг админ-контекста и сохраняем ранее выбранные продукты
    state_data = await state.get_data()
    is_admin_context = state_data.get("is_admin_context", False)
    selected_products = state_data.get("selected_products", [])
    selected_joints = state_data.get("selected_joints", [])
    
    # Очищаем предыдущие данные состояния
    await state.clear()
    
    # Устанавливаем флаг админ-контекста снова
    if is_admin_context:
        await state.update_data(is_admin_context=True)
    
    # Восстанавливаем ранее выбранные продукты и стыки
    await state.update_data(selected_products=selected_products)
    await state.update_data(selected_joints=selected_joints)
    
    db = next(get_db())
    try:
        # Получаем список всех толщин панелей, для которых есть готовая продукция
        thicknesses = db.query(FinishedProduct.thickness).distinct().all()
        available_thicknesses = [str(thickness[0]) for thickness in thicknesses]
        
        # Если нет доступных толщин, сообщаем об этом
        if not available_thicknesses:
            await message.answer(
                "На складе нет готовой продукции. Пожалуйста, обратитесь к производству.",
                reply_markup=get_menu_keyboard(MenuState.SALES_MAIN, is_admin_context=is_admin_context)
            )
            return
        
        # Формируем клавиатуру с доступными толщинами
        keyboard_rows = []
        for thickness in available_thicknesses:
            keyboard_rows.append([KeyboardButton(text=thickness)])
        keyboard_rows.append([KeyboardButton(text="◀️ Назад")])
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=keyboard_rows,
            resize_keyboard=True
        )
        
        await message.answer(
            "Выберите толщину панелей (мм):",
            reply_markup=keyboard
        )
        
        # Устанавливаем начальное состояние для сбора продуктов, только если это первый вызов
        if not selected_products:
            await state.update_data(selected_products=[])
        if not selected_joints:
            await state.update_data(selected_joints=[])
            
        await state.set_state(SalesStates.product_thickness)
    finally:
        db.close()

@router.message(SalesStates.product_thickness)
async def process_product_thickness(message: Message, state: FSMContext):
    """Обработка выбора толщины панелей"""
    thickness_text = message.text.strip()
    
    if thickness_text == "◀️ Назад":
        # Возвращаемся в главное меню
        state_data = await state.get_data()
        is_admin_context = state_data.get("is_admin_context", False)
        
        await state.set_state(MenuState.SALES_MAIN)
        await message.answer(
            "Выберите действие:",
            reply_markup=get_menu_keyboard(MenuState.SALES_MAIN, is_admin_context=is_admin_context)
        )
        return
    
    try:
        thickness = float(thickness_text)
        
        # Сохраняем выбранную толщину
        await state.update_data(current_thickness=thickness)
        
        db = next(get_db())
        try:
            # Получаем список готовой продукции для выбранной толщины
            finished_products = db.query(FinishedProduct).join(Film).filter(
                FinishedProduct.thickness == thickness,
                FinishedProduct.quantity > 0
            ).all()
            
            if not finished_products:
                await message.answer(
                    f"Для толщины {thickness} мм нет доступной продукции на складе.",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[[KeyboardButton(text="◀️ Назад")]],
                        resize_keyboard=True
                    )
                )
                return
            
            # Формируем клавиатуру с доступными цветами пленки для этой толщины
            keyboard_rows = []
            for product in finished_products:
                keyboard_rows.append([KeyboardButton(
                    text=f"{product.film.code} (остаток: {product.quantity} шт.)"
                )])
            
            keyboard_rows.append([KeyboardButton(text="◀️ Назад")])
            keyboard = ReplyKeyboardMarkup(keyboard=keyboard_rows, resize_keyboard=True)
            
            # Отображаем доступные цвета
            products_info = "\n".join([
                f"- {product.film.code}: {product.quantity} шт."
                for product in finished_products
            ])
            
            await message.answer(
                f"Выберите цвет пленки (толщина {thickness} мм):\n\n{products_info}",
                reply_markup=keyboard
            )
            
            # Переходим к выбору цвета
            await state.set_state(SalesStates.selecting_products)
            
        finally:
            db.close()
    except ValueError:
        await message.answer(
            "Пожалуйста, выберите корректную толщину панелей из предложенных вариантов.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="◀️ Назад")]],
                resize_keyboard=True
            )
        )

@router.message(SalesStates.selecting_products)
async def process_selecting_products(message: Message, state: FSMContext):
    """Обработка выбора цвета пленки для продукта"""
    film_text = message.text.strip()
    
    if film_text == "◀️ Назад":
        # Возвращаемся к выбору толщины
        await handle_create_order(message, state)
        return
    
    # Извлекаем код пленки из текста вида "Код (остаток: X шт.)"
    if "(" in film_text:
        film_code = film_text.split("(")[0].strip()
    else:
        film_code = film_text
    
    # Сохраняем выбранный код пленки
    await state.update_data(current_film_code=film_code)
    
    # Получаем выбранную толщину
    data = await state.get_data()
    thickness = data.get('current_thickness')
    
    # Проверяем наличие продукта
    db = next(get_db())
    try:
        product = db.query(FinishedProduct).join(Film).filter(
            Film.code == film_code,
            FinishedProduct.thickness == thickness,
            FinishedProduct.quantity > 0
        ).first()
        
        if not product:
            await message.answer(
                f"Продукт с кодом {film_code} и толщиной {thickness} мм не найден или закончился на складе.",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="◀️ Назад")]],
                    resize_keyboard=True
                )
            )
            return
        
        # Запрашиваем количество
        await message.answer(
            f"Введите количество панелей (доступно: {product.quantity} шт.):",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="◀️ Назад")]],
                resize_keyboard=True
            )
        )
        
        # Переходим к вводу количества
        await state.set_state(SalesStates.product_quantity)
        
    finally:
        db.close()

@router.message(SalesStates.product_quantity)
async def process_product_quantity(message: Message, state: FSMContext):
    """Обработка ввода количества панелей"""
    quantity_text = message.text.strip()
    
    if quantity_text == "◀️ Назад":
        # Возвращаемся к выбору цвета
        data = await state.get_data()
        thickness = data.get('current_thickness')
        
        # Показываем снова список продуктов для выбранной толщины
        db = next(get_db())
        try:
            finished_products = db.query(FinishedProduct).join(Film).filter(
                FinishedProduct.thickness == thickness,
                FinishedProduct.quantity > 0
            ).all()
            
            keyboard_rows = []
            for product in finished_products:
                keyboard_rows.append([KeyboardButton(
                    text=f"{product.film.code} (остаток: {product.quantity} шт.)"
                )])
            
            keyboard_rows.append([KeyboardButton(text="◀️ Назад")])
            keyboard = ReplyKeyboardMarkup(keyboard=keyboard_rows, resize_keyboard=True)
            
            products_info = "\n".join([
                f"- {product.film.code}: {product.quantity} шт."
                for product in finished_products
            ])
            
            await message.answer(
                f"Выберите цвет пленки (толщина {thickness} мм):\n\n{products_info}",
                reply_markup=keyboard
            )
            
            await state.set_state(SalesStates.selecting_products)
        finally:
            db.close()
        return
    
    try:
        quantity = int(quantity_text)
        if quantity <= 0:
            await message.answer(
                "Количество должно быть положительным числом.",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="◀️ Назад")]],
                    resize_keyboard=True
                )
            )
            return
        
        # Получаем данные о выбранном продукте
        data = await state.get_data()
        film_code = data.get('current_film_code')
        thickness = data.get('current_thickness')
        
        # Проверяем наличие достаточного количества продукта
        db = next(get_db())
        try:
            product = db.query(FinishedProduct).join(Film).filter(
                Film.code == film_code,
                FinishedProduct.thickness == thickness
            ).first()
            
            if not product or product.quantity < quantity:
                available = product.quantity if product else 0
                await message.answer(
                    f"Недостаточное количество продукта (запрошено: {quantity} шт., доступно: {available} шт.)",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[[KeyboardButton(text="◀️ Назад")]],
                        resize_keyboard=True
                    )
                )
                return
            
            # Добавляем продукт в корзину
            selected_products = data.get('selected_products', [])
            product_key = f"{film_code}|{thickness}"
            
            # Проверяем, есть ли уже такой продукт в корзине
            for i, product_data in enumerate(selected_products):
                if product_data.get('key') == product_key:
                    # Обновляем количество
                    selected_products[i]['quantity'] = quantity
                    break
            else:
                # Добавляем новый продукт
                selected_products.append({
                    'key': product_key,
                    'film_code': film_code,
                    'thickness': thickness,
                    'quantity': quantity
                })
            
            # Обновляем данные в состоянии
            await state.update_data(selected_products=selected_products)
            
            # Спрашиваем, хочет ли пользователь добавить еще продукты
            await message.answer(
                f"✅ Добавлено в заказ: панели с пленкой {film_code}, толщина {thickness} мм - {quantity} шт.\n\n"
                f"Хотите добавить еще продукцию в заказ?",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                        [KeyboardButton(text="◀️ Назад")]
                    ],
                    resize_keyboard=True
                )
            )
            
            # Переходим к состоянию выбора добавления еще продуктов
            await state.set_state(SalesStates.add_more_products)
            
        finally:
            db.close()
    except ValueError:
        await message.answer(
            "Пожалуйста, введите корректное число.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="◀️ Назад")]],
                resize_keyboard=True
            )
        )

@router.message(SalesStates.add_more_products)
async def process_add_more_products(message: Message, state: FSMContext):
    """Обработка выбора добавления еще продуктов"""
    response = message.text.strip()
    
    if response == "✅ Да":
        # Пользователь хочет добавить еще продукты
        # Возвращаемся к выбору толщины
        await handle_create_order(message, state)
        return
    elif response == "❌ Нет":
        # Пользователь закончил добавлять продукты
        # Переходим к следующему шагу (стыки)
        data = await state.get_data()
        selected_products = data.get('selected_products', [])
        
        if not selected_products:
            # Если нет выбранных продуктов, возвращаемся к выбору продуктов
            await message.answer(
                "Вы не добавили ни одного продукта в заказ. Пожалуйста, выберите продукцию."
            )
            await handle_create_order(message, state)
            return
        
        # Формируем сообщение с выбранными продуктами
        products_info = "Выбранные продукты:\n"
        for product in selected_products:
            products_info += f"▪️ {product['film_code']} (толщина {product['thickness']} мм): {product['quantity']} шт.\n"
        
        # Спрашиваем о необходимости стыков
        await message.answer(
            f"{products_info}\n\nТребуются ли стыки?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        
        # Переходим к выбору стыков
        await state.set_state(SalesStates.waiting_for_need_joints)
        
    elif response == "◀️ Назад":
        # Возвращаемся к вводу количества
        data = await state.get_data()
        film_code = data.get('current_film_code')
        thickness = data.get('current_thickness')
        
        db = next(get_db())
        try:
            product = db.query(FinishedProduct).join(Film).filter(
                Film.code == film_code,
                FinishedProduct.thickness == thickness
            ).first()
            
            available = product.quantity if product else 0
            
            await message.answer(
                f"Введите количество панелей (доступно: {available} шт.):",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="◀️ Назад")]],
                    resize_keyboard=True
                )
            )
            
            await state.set_state(SalesStates.product_quantity)
        finally:
            db.close()
    else:
        await message.answer(
            "Пожалуйста, выберите один из вариантов: ✅ Да, ❌ Нет или ◀️ Назад",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )

@router.message(SalesStates.waiting_for_need_joints)
async def process_need_joints(message: Message, state: FSMContext):
    """Обработка ответа на вопрос о необходимости стыков"""
    response = message.text.strip()
    
    if response == "✅ Да":
        # Пользователь хочет стыки
        await state.update_data(need_joints=True)
        
        # Получаем доступные стыки из базы данных
        db = next(get_db())
        try:
            # Группируем стыки по типу и показываем количество
            butterfly_joints = db.query(Joint).filter(Joint.type == JointType.BUTTERFLY, Joint.quantity > 0).all()
            simple_joints = db.query(Joint).filter(Joint.type == JointType.SIMPLE, Joint.quantity > 0).all()
            closing_joints = db.query(Joint).filter(Joint.type == JointType.CLOSING, Joint.quantity > 0).all()
            
            # Формируем сообщение о доступных стыках
            joints_info = "Доступные стыки:\n\n"
            
            if butterfly_joints:
                joints_info += "🦋 Бабочка:\n"
                for thickness in [0.5, 0.8]:
                    thickness_joints = [j for j in butterfly_joints if j.thickness == thickness]
                    if thickness_joints:
                        joints_info += f"  {thickness} мм: "
                        joints_info += ", ".join([f"{j.color} ({j.quantity} шт.)" for j in thickness_joints])
                        joints_info += "\n"
            
            if simple_joints:
                joints_info += "🔄 Простые:\n"
                for thickness in [0.5, 0.8]:
                    thickness_joints = [j for j in simple_joints if j.thickness == thickness]
                    if thickness_joints:
                        joints_info += f"  {thickness} мм: "
                        joints_info += ", ".join([f"{j.color} ({j.quantity} шт.)" for j in thickness_joints])
                        joints_info += "\n"
            
            if closing_joints:
                joints_info += "🔒 Замыкающие:\n"
                for thickness in [0.5, 0.8]:
                    thickness_joints = [j for j in closing_joints if j.thickness == thickness]
                    if thickness_joints:
                        joints_info += f"  {thickness} мм: "
                        joints_info += ", ".join([f"{j.color} ({j.quantity} шт.)" for j in thickness_joints])
                        joints_info += "\n"
            
            if not butterfly_joints and not simple_joints and not closing_joints:
                # Если нет стыков, сообщаем об этом и переходим к следующему шагу
                await message.answer("К сожалению, на складе нет доступных стыков.")
                await state.update_data(need_joints=False)
                
                # Переходим к запросу о клее
                keyboard = ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                        [KeyboardButton(text="◀️ Назад")]
                    ],
                    resize_keyboard=True
                )
                await message.answer(
                    "Требуется ли клей?",
                    reply_markup=keyboard
                )
                await state.set_state(SalesStates.waiting_for_need_glue)
                return
            
            # Запрашиваем тип стыка
            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="🦋 Бабочка")] if butterfly_joints else [],
                    [KeyboardButton(text="🔄 Простые")] if simple_joints else [],
                    [KeyboardButton(text="🔒 Замыкающие")] if closing_joints else [],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
            
            await message.answer(
                joints_info + "\n\nВыберите тип стыка:",
                reply_markup=keyboard
            )
            await state.set_state(SalesStates.waiting_for_order_joint_type)
        finally:
            db.close()
    elif response == "❌ Нет":
        # Пользователь не хочет стыки
        await state.update_data(need_joints=False)
        
        # Переходим к запросу о клее
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                [KeyboardButton(text="◀️ Назад")]
            ],
            resize_keyboard=True
        )
        await message.answer(
            "Требуется ли клей?",
            reply_markup=keyboard
        )
        await state.set_state(SalesStates.waiting_for_order_installation)
    elif response == "◀️ Назад":
        # Возвращаемся к вопросу о добавлении продуктов
        data = await state.get_data()
        selected_products = data.get('selected_products', [])
        
        # Формируем список выбранных продуктов
        products_info = "Выбранные продукты:\n"
        for product in selected_products:
            products_info += f"▪️ {product['film_code']} (толщина {product['thickness']} мм): {product['quantity']} шт.\n"
        
        await message.answer(
            f"{products_info}\n\nХотите добавить еще продукцию в заказ?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.add_more_products)
    else:
        await message.answer(
            "Пожалуйста, выберите один из вариантов: ✅ Да, ❌ Нет или ◀️ Назад",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )

@router.message(SalesStates.waiting_for_add_more_joints)
async def process_add_more_joints(message: Message, state: FSMContext):
    """Обработка ответа на вопрос о добавлении еще стыков"""
    response = message.text.strip()
    
    if response == "✅ Да":
        installation_required = True
    elif response == "❌ Нет":
        installation_required = False
    else:
        await message.answer(
            "Пожалуйста, выберите один из вариантов: ✅ Да или ❌ Нет",
            reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
        )
        return
    
    # Сохраняем информацию о монтаже
    await state.update_data(installation_required=installation_required)
    
    # Запрашиваем контакты клиента
    await message.answer(
        "Введите контактный номер телефона клиента:",
        reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
    )
    await state.set_state(SalesStates.waiting_for_order_customer_phone)

@router.message(SalesStates.waiting_for_order_delivery_address)
async def process_order_delivery_address(message: Message, state: FSMContext):
    """Обработка ввода адреса доставки"""
    address = message.text.strip()
    
    # Если адрес не указан, считаем самовывозом
    if address.lower() == "нет":
        address = "Самовывоз"
    
    # Сохраняем адрес доставки
    await state.update_data(delivery_address=address)
    
    # Показываем сводку заказа и запрашиваем подтверждение
    data = await state.get_data()
    
    # Получаем данные о выбранных продуктах
    selected_products = data.get('selected_products', [])
    
    # Получаем данные о выбранных стыках
    selected_joints = data.get('selected_joints', [])
    
    need_joints = data.get('need_joints', False)
    need_glue = data.get('need_glue', False)
    glue_quantity = data.get('glue_quantity', 0)
    installation_required = data.get('installation_required', False)
    customer_phone = data.get('customer_phone', '')
    delivery_address = data.get('delivery_address', '')
    
    # Формируем текст заказа
    order_summary = f"📝 Сводка заказа:\n\n"
    
    # Добавляем информацию о выбранных продуктах
    if selected_products:
        order_summary += f"📦 Выбранные продукты:\n"
        total_panels = 0
        for product in selected_products:
            order_summary += f"▪️ {product['film_code']} (толщина {product['thickness']} мм): {product['quantity']} шт.\n"
            total_panels += product['quantity']
        order_summary += f"Всего панелей: {total_panels} шт.\n\n"
    else:
        order_summary += "Продукты не выбраны\n\n"
    
    # Добавляем информацию о стыках
    if need_joints and selected_joints:
        order_summary += f"🔗 Стыки:\n"
        for joint in selected_joints:
            joint_type = joint.get('type', '')
            joint_type_text = ''
            if joint_type == 'butterfly' or joint_type == JointType.BUTTERFLY:
                joint_type_text = "Бабочка"
            elif joint_type == 'simple' or joint_type == JointType.SIMPLE:
                joint_type_text = "Простые"
            elif joint_type == 'closing' or joint_type == JointType.CLOSING:
                joint_type_text = "Замыкающие"
            
            thickness = joint.get('thickness', '0.5')
            order_summary += f"▪️ {joint_type_text}, {thickness} мм, {joint.get('color', '')}: {joint.get('quantity', 0)} шт.\n"
        order_summary += "\n"
    else:
        order_summary += f"🔗 Стыки: Нет\n\n"
    
    # Добавляем остальную информацию
    order_summary += f"🧴 Клей: {glue_quantity} тюбиков\n"
    order_summary += f"🔧 Монтаж: {'Требуется' if installation_required else 'Не требуется'}\n"
    order_summary += f"📞 Контактный телефон: {customer_phone}\n"
    order_summary += f"🚚 Адрес доставки: {delivery_address}\n"
    
    # Запрашиваем подтверждение
    await state.update_data(order_summary=order_summary)
    await state.set_state(MenuState.SALES_ORDER_CONFIRM)
    
    await message.answer(
        order_summary + "\n\nПожалуйста, подтвердите заказ:",
        reply_markup=get_menu_keyboard(MenuState.SALES_ORDER_CONFIRM)
    )
    await state.set_state(SalesStates.waiting_for_order_confirmation)

@router.message(SalesStates.waiting_for_order_confirmation)
async def process_order_confirmation(message: Message, state: FSMContext):
    """Обработка подтверждения заказа"""
    if message.text.lower() != "подтвердить":
        await message.answer("Заказ не подтвержден. Вы можете вернуться к оформлению заказа позже.")
        await go_back(message, state)
        return
    
    # Получаем данные из состояния
    data = await state.get_data()
    
    # Получаем выбранные продукты из состояния
    selected_products = data.get("selected_products", [])
    
    # Получаем выбранные стыки из состояния
    selected_joints = data.get("selected_joints", [])
    
    need_joints = selected_joints and len(selected_joints) > 0
    need_glue = data.get("need_glue", False)
    customer_phone = data.get("customer_phone", "")
    delivery_address = data.get("delivery_address", "")
    installation_required = data.get("installation_required", False)
    glue_quantity = data.get("glue_quantity", 0)
    
    # Определяем тип заказа (готовая продукция или производство)
    db = next(get_db())
    
    try:
        # Получаем пользователя по telegram_id для получения корректного ID в базе
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        
        if not user:
            await message.answer("❌ Ошибка: пользователь не найден")
            db.close()
            return
        
        # Создаем заказ
        order = Order(
            manager_id=user.id,  # Используем ID пользователя из базы данных, а не telegram_id
            customer_phone=customer_phone,
            delivery_address=delivery_address,
            installation_required=installation_required,
            status=OrderStatus.NEW
        )
        db.add(order)
        db.flush()
        
        # Добавляем продукты в заказ через OrderItem
        for product in selected_products:
            film_code = product['film_code']
            thickness = float(product['thickness'])
            qty = product['quantity']
            
            film = db.query(Film).filter(Film.code == film_code).first()
            if not film:
                continue
            
            # Проверяем, есть ли готовая продукция
            finished_product = db.query(FinishedProduct).join(Film).filter(
                Film.code == film_code,
                FinishedProduct.thickness == thickness
            ).first()
            
            # Создаем запись OrderItem
            order_item = OrderItem(
                order_id=order.id,
                color=film_code,
                thickness=thickness,
                quantity=qty
            )
            db.add(order_item)
            
            if finished_product and finished_product.quantity >= qty:
                # Если есть готовая продукция, уменьшаем ее количество
                finished_product.quantity -= qty
                
                # Создаем операцию для готовой продукции
                operation = Operation(
                    operation_type=OperationType.READY_PRODUCT_OUT.value,
                    quantity=qty,
                    user_id=user.id  # Используем ID пользователя из базы
                )
                db.add(operation)
            else:
                # Если нет готовой продукции, создаем заказ на производство
                production_order = ProductionOrder(
                    manager_id=user.id,  # Используем ID пользователя из базы
                    panel_quantity=qty,
                    film_color=film_code,
                    panel_thickness=thickness,
                    status="new"
                )
                db.add(production_order)
        
        # Если нужны стыки, добавляем их в заказ
        if need_joints:
            if isinstance(selected_joints, list):
                # Новый формат - список объектов стыков
                for joint_data in selected_joints:
                    joint_type_val = joint_data.get('type')
                    thickness = joint_data.get('thickness')
                    color = joint_data.get('color')
                    quantity = joint_data.get('quantity')
                    
                    joint_type_text = ""
                    if joint_type_val == JointType.BUTTERFLY or joint_type_val == "butterfly":
                        joint_type_text = "Бабочка"
                    elif joint_type_val == JointType.SIMPLE or joint_type_val == "simple":
                        joint_type_text = "Простые"
                    elif joint_type_val == JointType.CLOSING or joint_type_val == "closing":
                        joint_type_text = "Замыкающие"
                    
                    joints_info += f"▪️ {joint_type_text}, {thickness} мм, {color}: {quantity} шт.\n"
            elif isinstance(selected_joints, dict):
                # Словарь (старый формат)
                for joint_key, quantity in selected_joints.items():
                    joint_type_val, thickness, color = joint_key.split('|')
                    joint_type_text = ""
                    if joint_type_val == "butterfly":
                        joint_type_text = "Бабочка"
                    elif joint_type_val == "simple":
                        joint_type_text = "Простые"
                    elif joint_type_val == "closing":
                        joint_type_text = "Замыкающие"
                    
                    joints_info += f"▪️ {joint_type_text}, {thickness} мм, {color}: {quantity} шт.\n"

        # Добавляем информацию о клее если он нужен
        glue_info = ""
        if need_glue and glue_quantity > 0:
            glue_info = f"\nКлей: {glue_quantity} шт.\n"
        
        # Сборка итогового сообщения
        installation_text = "Да" if installation_required else "Нет"
        
        # Создаем сообщение с информацией о заказе
        confirmation_message = (
            f"✅ Заказ #{order.id} успешно оформлен!\n\n"
            f"{products_info}"
            f"{joints_info}"
            f"{glue_info}"
            f"Монтаж: {installation_text}\n"
            f"Телефон: {customer_phone}\n"
            f"Адрес доставки: {delivery_address}\n\n"
            f"Статус заказа: {order.status.value}"
        )
        
        await message.answer(confirmation_message)
        
        # Возвращаемся в главное меню
        await go_back(message, state)
    
    except Exception as e:
        # В случае ошибки откатываем изменения
        db.rollback()
        logging.error(f"Ошибка при оформлении заказа: {e}")
        await message.answer(f"❌ Произошла ошибка при оформлении заказа: {e}")
    
    finally:
        # Закрываем соединение с БД
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

@router.message(SalesStates.waiting_for_need_glue)
async def process_need_glue(message: Message, state: FSMContext):
    """Обработка ответа на вопрос о необходимости клея"""
    response = message.text.strip()
    
    if response == "✅ Да":
        # Пользователь хочет клей
        await state.update_data(need_glue=True)
        
        # Запрашиваем количество клея
        # Проверяем наличие клея в базе
        db = next(get_db())
        try:
            glue = db.query(Glue).filter(Glue.quantity > 0).first()
            
            if not glue:
                await message.answer(
                    "❌ К сожалению, клей отсутствует на складе.",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[
                            [KeyboardButton(text="◀️ Назад")]
                        ],
                        resize_keyboard=True
                    )
                )
                return
            
            await message.answer(
                f"Введите количество тюбиков клея (доступно: {glue.quantity} шт.):",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text="◀️ Назад")]
                    ],
                    resize_keyboard=True
                )
            )
            await state.set_state(SalesStates.waiting_for_order_glue_quantity)
        finally:
            db.close()
    elif response == "❌ Нет":
        # Пользователь не хочет клей
        await state.update_data(need_glue=False, glue_quantity=0)
        
        # Переходим к запросу о монтаже
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                [KeyboardButton(text="◀️ Назад")]
            ],
            resize_keyboard=True
        )
        await message.answer(
            "Требуется ли монтаж?",
            reply_markup=keyboard
        )
        await state.set_state(SalesStates.waiting_for_order_installation)
    else:
        await message.answer(
            "Пожалуйста, выберите один из вариантов: ✅ Да или ❌ Нет",
            reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
        )

@router.message(SalesStates.waiting_for_order_glue_quantity)
async def process_order_glue_quantity(message: Message, state: FSMContext):
    """Обработка ввода количества клея"""
    try:
        quantity = int(message.text.strip())
        if quantity <= 0:
            await message.answer("❌ Количество должно быть больше 0")
            return
            
        # Получаем данные о выбранном клее
        data = await state.get_data()
        glue_quantity = quantity
        
        # Сохраняем количество клея
        await state.update_data(glue_quantity=glue_quantity)
        
        # Переходим к запросу о монтаже
        await message.answer(
            "Требуется ли монтаж?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_installation)
    except ValueError:
        await message.answer(
            "Пожалуйста, введите корректное число.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )

@router.message(SalesStates.waiting_for_order_glue_needed)
async def process_order_glue_needed(message: Message, state: FSMContext):
    """Обработка ответа о необходимости клея для стыков"""
    user_choice = message.text.strip()
    
    if user_choice == "✅ Да":
        # Проверяем наличие клея в базе данных
        db = next(get_db())
        try:
            glue = db.query(Glue).filter(Glue.quantity > 0).first()
            
            if not glue:
                await message.answer(
                    "❌ К сожалению, клей отсутствует на складе.",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[
                            [KeyboardButton(text="◀️ Назад")]
                        ],
                        resize_keyboard=True
                    )
                )
                return
            
            await message.answer(
                f"Введите количество тюбиков клея (доступно: {glue.quantity} шт.):",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text="◀️ Назад")]
                    ],
                    resize_keyboard=True
                )
            )
            await state.set_state(SalesStates.waiting_for_order_glue_quantity)
        finally:
            db.close()
    elif user_choice == "❌ Нет":
        # Клей не нужен, сохраняем нулевое количество
        await state.update_data(glue_quantity=0)
        
        # Переходим к запросу о монтаже
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                [KeyboardButton(text="◀️ Назад")]
            ],
            resize_keyboard=True
        )
        await message.answer(
            "Требуется ли монтаж?",
            reply_markup=keyboard
        )
        await state.set_state(SalesStates.waiting_for_order_installation)
    else:
        # Некорректный ввод
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )

@router.message(SalesStates.waiting_for_order_installation)
async def process_order_installation(message: Message, state: FSMContext):
    """Обработка выбора монтажа"""
    response = message.text.strip()
    
    if response == "◀️ Назад":
        # Возвращаемся к предыдущему шагу - запросу о клее
        await message.answer(
            "Вам нужен клей?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_glue_needed)
        return

    installation_required = False
    if response == "✅ Да":
        installation_required = True
    elif response == "❌ Нет":
        installation_required = False
    else:
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        return

    # Сохраняем выбор установки
    await state.update_data(installation_required=installation_required)

    # Запрашиваем контактный номер телефона
    await message.answer(
        "Введите контактный номер телефона клиента:",
        reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
    )
    await state.set_state(SalesStates.waiting_for_order_customer_phone)

@router.message(SalesStates.waiting_for_order_customer_phone)
async def process_order_customer_phone(message: Message, state: FSMContext):
    """Обработка ввода контактного номера клиента"""
    phone = message.text.strip()
    
    if message.text == "◀️ Назад":
        # Возвращаемся к предыдущему шагу - запросу о монтаже
        await message.answer(
            "Требуется ли монтаж?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_installation)
        return
    
    # Простая проверка на формат телефона
    if not phone or len(phone) < 5:  # Минимальная длина для телефона
        await message.answer(
            "❌ Пожалуйста, введите корректный номер телефона",
            reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
        )
        return
    
    # Сохраняем номер телефона
    await state.update_data(customer_phone=phone)
    
    # Запрашиваем адрес доставки
    await message.answer(
        "Введите адрес доставки (или напишите 'нет' если самовывоз):",
        reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
    )
    await state.set_state(SalesStates.waiting_for_order_delivery_address)

@router.message(SalesStates.waiting_for_order_joint_type)
async def process_order_joint_type(message: Message, state: FSMContext):
    """Обработка выбора типа стыка"""
    user_choice = message.text.strip()
    
    if user_choice == "◀️ Назад":
        # Возвращаемся к вопросу о необходимости стыков
        await message.answer(
            "Нужны ли стыки?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_need_joints)
        return
    
    joint_type_map = {
        "🦋 бабочка": JointType.BUTTERFLY,
        "🔄 простые": JointType.SIMPLE,
        "🔒 замыкающие": JointType.CLOSING,
        "🦋 бабочка": JointType.BUTTERFLY,
        "🔄 простые": JointType.SIMPLE,
        "🔒 замыкающие": JointType.CLOSING
    }
    
    joint_type = None
    for key in joint_type_map:
        if key.lower() in user_choice.lower():
            joint_type = joint_type_map[key]
            break
    
    if not joint_type:
        await message.answer(
            "Пожалуйста, выберите тип стыка из предложенных вариантов.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="🦋 Бабочка")],
                    [KeyboardButton(text="🔄 Простые")],
                    [KeyboardButton(text="🔒 Замыкающие")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        return
    
    # Сохраняем выбранный тип стыка
    await state.update_data(joint_type=joint_type)
    
    # Запрашиваем толщину стыка
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="0.5"), KeyboardButton(text="0.8")],
            [KeyboardButton(text="◀️ Назад")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        f"Выберите толщину стыка (мм):",
        reply_markup=keyboard
    )
    await state.set_state(SalesStates.waiting_for_order_joint_thickness)

@router.message(SalesStates.waiting_for_order_joint_thickness)
async def process_order_joint_thickness(message: Message, state: FSMContext):
    """Обработка ввода толщины стыков"""
    if message.text == "◀️ Назад":
        await state.set_state(SalesStates.waiting_for_order_joint_type)
        await message.answer(
            "Выберите тип стыка:",
            reply_markup=get_joint_type_keyboard()
        )
        return
    
    try:
        # Проверяем, что толщина является числом
        thickness = float(message.text)
        if thickness <= 0:
            raise ValueError("Толщина должна быть положительным числом")
        
        # Получаем тип стыка из состояния
        data = await state.get_data()
        joint_type = data.get("joint_type")
        
        db = next(get_db())
        
        # Проверяем наличие стыков указанной толщины
        joints = db.query(Joint).filter(
            Joint.type == joint_type,
            Joint.thickness == thickness,
            Joint.quantity > 0
        ).all()
        
        if not joints:
            db.close()
            await message.answer(
                f"❌ Ошибка: стыки типа {joint_type.value} толщиной {thickness} мм отсутствуют на складе.\n"
                f"Пожалуйста, введите другую толщину:",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text="◀️ Назад")]
                    ],
                    resize_keyboard=True
                )
            )
            return
        
        # Сохраняем толщину в состоянии
        await state.update_data(joint_thickness=thickness)
        
        # Получаем доступные цвета для выбранного типа и толщины стыка
        available_colors = set()
        for joint in joints:
            available_colors.add(joint.color)
        
        # Создаем клавиатуру с доступными цветами
        keyboard = []
        for color in available_colors:
            keyboard.append([KeyboardButton(text=color)])
        
        keyboard.append([KeyboardButton(text="◀️ Назад")])
        
        # Переходим к выбору цвета стыка
        await state.set_state(SalesStates.waiting_for_order_joint_color)
        await message.answer(
            f"Выберите цвет стыка:",
            reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
        )
        
        db.close()
    except ValueError:
        await message.answer(
            "❌ Ошибка: введите корректное число для толщины стыка.\nПопробуйте снова:"
        )
    except Exception as e:
        logging.error(f"Ошибка при обработке толщины стыка: {e}")
        await message.answer(
            f"❌ Произошла ошибка: {e}\nПопробуйте снова:"
        )

@router.message(SalesStates.waiting_for_order_joint_color)
async def process_order_joint_color(message: Message, state: FSMContext):
    """Обработка выбора цвета стыка"""
    user_choice = message.text.strip()
    
    if user_choice == "◀️ Назад":
        # Возвращаемся к выбору толщины
        await message.answer(
            "Выберите толщину стыка (мм):",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="0.5"), KeyboardButton(text="0.8")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_joint_thickness)
        return
    
    # Извлекаем цвет (убираем информацию о количестве)
    color = user_choice.split(" (")[0]
    
    # Сохраняем выбранный цвет
    await state.update_data(joint_color=color)
    
    # Запрашиваем количество стыков
    await message.answer(
        "Введите количество стыков:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Назад")]],
            resize_keyboard=True
        )
    )
    await state.set_state(SalesStates.waiting_for_order_joint_quantity)

@router.message(SalesStates.waiting_for_order_joint_quantity)
async def process_order_joint_quantity(message: Message, state: FSMContext):
    """Обработка количества стыков"""
    if message.text == "◀️ Назад":
        await state.set_state(SalesStates.waiting_for_order_joint_color)
        await message.answer(
            "Выберите цвет стыка:",
            reply_markup=await get_colors_keyboard()
        )
        return
    
    try:
        # Проверяем, что количество является числом
        quantity = int(message.text)
        if quantity <= 0:
            raise ValueError("Количество должно быть положительным числом")
        
        # Получаем данные из состояния
        data = await state.get_data()
        joint_type = data.get("joint_type")
        joint_color = data.get("joint_color")
        joint_thickness = data.get("joint_thickness")
        
        db = next(get_db())
        
        # Проверяем наличие стыков в базе
        joint = db.query(Joint).filter(
            Joint.type == joint_type,
            Joint.color == joint_color,
            Joint.thickness == joint_thickness
        ).first()
        
        if not joint or joint.quantity < quantity:
            db.close()
            await message.answer(
                f"❌ Ошибка: недостаточно стыков типа {joint_type.value}, цвета {joint_color}, толщиной {joint_thickness} мм на складе.\n"
                f"Доступно: {joint.quantity if joint else 0} шт.\n"
                f"Пожалуйста, введите другое количество:"
            )
            return
        
        # Добавляем стык в список стыков
        selected_joints = data.get("selected_joints", [])
        
        # Создаем объект стыка
        joint_data = {
            "type": joint_type.value,
            "color": joint_color,
            "thickness": joint_thickness,
            "quantity": quantity
        }
        
        # Проверяем, есть ли уже стык такого типа, цвета и толщины
        found = False
        for i, existing_joint in enumerate(selected_joints):
            if (existing_joint.get("type") == joint_type.value and 
                existing_joint.get("color") == joint_color and
                existing_joint.get("thickness") == joint_thickness):
                # Обновляем количество существующего стыка
                selected_joints[i]["quantity"] = quantity
                found = True
                break
        
        # Если стыка такого типа нет, добавляем новый
        if not found:
            selected_joints.append(joint_data)
        
        # Обновляем состояние
        await state.update_data(selected_joints=selected_joints)
        
        # Спрашиваем, хочет ли пользователь добавить еще стыки
        await state.set_state(SalesStates.waiting_for_order_more_joints)
        
        # Получаем все выбранные стыки для отображения
        joints_info = ""
        for joint_item in selected_joints:
            joint_type_val = joint_item.get("type")
            joint_color_val = joint_item.get("color")
            joint_thickness_val = joint_item.get("thickness")
            joint_quantity_val = joint_item.get("quantity")
            
            joint_type_text = ""
            if joint_type_val == JointType.BUTTERFLY.value:
                joint_type_text = "Бабочка"
            elif joint_type_val == JointType.SIMPLE.value:
                joint_type_text = "Простые"
            elif joint_type_val == JointType.CLOSING.value:
                joint_type_text = "Замыкающие"
            
            joints_info += f"▪️ {joint_type_text}, {joint_thickness_val} мм, {joint_color_val}: {joint_quantity_val} шт.\n"
        
        # Формируем клавиатуру для выбора
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ Да, добавить еще стыки")],
                [KeyboardButton(text="❌ Нет, перейти дальше")],
                [KeyboardButton(text="◀️ Назад")]
            ],
            resize_keyboard=True
        )
        
        await message.answer(
            f"Выбранные стыки:\n{joints_info}\n\nХотите добавить еще стыки?",
            reply_markup=keyboard
        )
        
        db.close()
    except ValueError:
        await message.answer(
            "❌ Ошибка: введите целое положительное число.\nПопробуйте снова:"
        )
    except Exception as e:
        logging.error(f"Ошибка при обработке количества стыков: {e}")
        await message.answer(
            f"❌ Произошла ошибка: {e}\nПопробуйте снова:"
        )

@router.message(SalesStates.waiting_for_order_more_joints)
async def process_order_more_joints(message: Message, state: FSMContext):
    """Обработка ответа о добавлении дополнительных стыков"""
    user_choice = message.text.strip()
    
    if user_choice == "◀️ Назад":
        # Отменяем последний добавленный стык
        data = await state.get_data()
        selected_joints = data.get('selected_joints', [])
        
        if selected_joints:
            # Удаляем последний добавленный стык
            selected_joints.pop()
            await state.update_data(selected_joints=selected_joints)
            
            # Возвращаемся к выбору количества
            last_joint = data.get('last_joint', {})
            joint_type = last_joint.get('type', data.get('joint_type'))
            thickness = last_joint.get('thickness', data.get('joint_thickness'))
            color = last_joint.get('color', data.get('joint_color'))
            
            await message.answer(
                f"Введите количество стыков ({joint_type}, {thickness} мм, {color}):",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text="◀️ Назад")]
                    ],
                    resize_keyboard=True
                )
            )
            await state.set_state(SalesStates.waiting_for_order_joint_quantity)
            return
        else:
            # Если стыков нет, возвращаемся к выбору типа стыка
            await message.answer(
                "Выберите тип стыка:",
                reply_markup=get_joint_type_keyboard()
            )
            await state.set_state(SalesStates.waiting_for_order_joint_type)
            return
    
    if user_choice == "✅ Да":
        # Пользователь хочет добавить еще стыки, возвращаемся к выбору типа
        await message.answer(
            "Выберите тип стыка:",
            reply_markup=get_joint_type_keyboard()
        )
        await state.set_state(SalesStates.waiting_for_order_joint_type)
    elif user_choice == "❌ Нет":
        # Пользователь закончил выбор стыков, переходим к вопросу о клее
        await message.answer(
            "Нужен ли клей для стыков?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_glue_needed)
    else:
        # Некорректный ввод
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )

@router.message(SalesStates.waiting_for_add_more_joints)
async def process_add_more_joints(message: Message, state: FSMContext):
    """Обработка ответа на вопрос о добавлении еще стыков"""
    response = message.text.strip()
    
    if response == "✅ Да":
        installation_required = True
    elif response == "❌ Нет":
        installation_required = False
    else:
        await message.answer(
            "Пожалуйста, выберите один из вариантов: ✅ Да или ❌ Нет",
            reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
        )
        return
    
    # Сохраняем информацию о монтаже
    await state.update_data(installation_required=installation_required)
    
    # Запрашиваем контакты клиента
    await message.answer(
        "Введите контактный номер телефона клиента:",
        reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
    )
    await state.set_state(SalesStates.waiting_for_order_customer_phone)

@router.message(SalesStates.waiting_for_order_delivery_address)
async def process_order_delivery_address(message: Message, state: FSMContext):
    """Обработка ввода адреса доставки"""
    address = message.text.strip()
    
    # Если адрес не указан, считаем самовывозом
    if address.lower() == "нет":
        address = "Самовывоз"
    
    # Сохраняем адрес доставки
    await state.update_data(delivery_address=address)
    
    # Показываем сводку заказа и запрашиваем подтверждение
    data = await state.get_data()
    
    # Получаем данные о выбранных продуктах
    selected_products = data.get('selected_products', [])
    
    # Получаем данные о выбранных стыках
    selected_joints = data.get('selected_joints', [])
    
    need_joints = data.get('need_joints', False)
    need_glue = data.get('need_glue', False)
    glue_quantity = data.get('glue_quantity', 0)
    installation_required = data.get('installation_required', False)
    customer_phone = data.get('customer_phone', '')
    delivery_address = data.get('delivery_address', '')
    
    # Формируем текст заказа
    order_summary = f"📝 Сводка заказа:\n\n"
    
    # Добавляем информацию о выбранных продуктах
    if selected_products:
        order_summary += f"📦 Выбранные продукты:\n"
        total_panels = 0
        for product in selected_products:
            order_summary += f"▪️ {product['film_code']} (толщина {product['thickness']} мм): {product['quantity']} шт.\n"
            total_panels += product['quantity']
        order_summary += f"Всего панелей: {total_panels} шт.\n\n"
    else:
        order_summary += "Продукты не выбраны\n\n"
    
    # Добавляем информацию о стыках
    if need_joints and selected_joints:
        order_summary += f"🔗 Стыки:\n"
        for joint in selected_joints:
            joint_type = joint.get('type', '')
            joint_type_text = ''
            if joint_type == 'butterfly' or joint_type == JointType.BUTTERFLY:
                joint_type_text = "Бабочка"
            elif joint_type == 'simple' or joint_type == JointType.SIMPLE:
                joint_type_text = "Простые"
            elif joint_type == 'closing' or joint_type == JointType.CLOSING:
                joint_type_text = "Замыкающие"
            
            thickness = joint.get('thickness', '0.5')
            order_summary += f"▪️ {joint_type_text}, {thickness} мм, {joint.get('color', '')}: {joint.get('quantity', 0)} шт.\n"
        order_summary += "\n"
    else:
        order_summary += f"🔗 Стыки: Нет\n\n"
    
    # Добавляем остальную информацию
    order_summary += f"🧴 Клей: {glue_quantity} тюбиков\n"
    order_summary += f"🔧 Монтаж: {'Требуется' if installation_required else 'Не требуется'}\n"
    order_summary += f"📞 Контактный телефон: {customer_phone}\n"
    order_summary += f"🚚 Адрес доставки: {delivery_address}\n"
    
    # Запрашиваем подтверждение
    await state.update_data(order_summary=order_summary)
    await state.set_state(MenuState.SALES_ORDER_CONFIRM)
    
    await message.answer(
        order_summary + "\n\nПожалуйста, подтвердите заказ:",
        reply_markup=get_menu_keyboard(MenuState.SALES_ORDER_CONFIRM)
    )
    await state.set_state(SalesStates.waiting_for_order_confirmation)

@router.message(SalesStates.waiting_for_order_confirmation)
async def process_order_confirmation(message: Message, state: FSMContext):
    """Обработка подтверждения заказа"""
    if message.text.lower() != "подтвердить":
        await message.answer("Заказ не подтвержден. Вы можете вернуться к оформлению заказа позже.")
        await go_back(message, state)
        return
    
    # Получаем данные из состояния
    data = await state.get_data()
    
    # Получаем выбранные продукты из состояния
    selected_products = data.get("selected_products", [])
    
    # Получаем выбранные стыки из состояния
    selected_joints = data.get("selected_joints", [])
    
    need_joints = selected_joints and len(selected_joints) > 0
    need_glue = data.get("need_glue", False)
    customer_phone = data.get("customer_phone", "")
    delivery_address = data.get("delivery_address", "")
    installation_required = data.get("installation_required", False)
    glue_quantity = data.get("glue_quantity", 0)
    
    # Определяем тип заказа (готовая продукция или производство)
    db = next(get_db())
    
    try:
        # Получаем пользователя по telegram_id для получения корректного ID в базе
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        
        if not user:
            await message.answer("❌ Ошибка: пользователь не найден")
            db.close()
            return
        
        # Создаем заказ
        order = Order(
            manager_id=user.id,  # Используем ID пользователя из базы данных, а не telegram_id
            customer_phone=customer_phone,
            delivery_address=delivery_address,
            installation_required=installation_required,
            status=OrderStatus.NEW
        )
        db.add(order)
        db.flush()
        
        # Добавляем продукты в заказ через OrderItem
        for product in selected_products:
            film_code = product['film_code']
            thickness = float(product['thickness'])
            qty = product['quantity']
            
            film = db.query(Film).filter(Film.code == film_code).first()
            if not film:
                continue
            
            # Проверяем, есть ли готовая продукция
            finished_product = db.query(FinishedProduct).join(Film).filter(
                Film.code == film_code,
                FinishedProduct.thickness == thickness
            ).first()
            
            # Создаем запись OrderItem
            order_item = OrderItem(
                order_id=order.id,
                color=film_code,
                thickness=thickness,
                quantity=qty
            )
            db.add(order_item)
            
            if finished_product and finished_product.quantity >= qty:
                # Если есть готовая продукция, уменьшаем ее количество
                finished_product.quantity -= qty
                
                # Создаем операцию для готовой продукции
                operation = Operation(
                    operation_type=OperationType.READY_PRODUCT_OUT.value,
                    quantity=qty,
                    user_id=user.id  # Используем ID пользователя из базы
                )
                db.add(operation)
            else:
                # Если нет готовой продукции, создаем заказ на производство
                production_order = ProductionOrder(
                    manager_id=user.id,  # Используем ID пользователя из базы
                    panel_quantity=qty,
                    film_color=film_code,
                    panel_thickness=thickness,
                    status="new"
                )
                db.add(production_order)
        
        # Если нужны стыки, добавляем их в заказ
        if need_joints:
            if isinstance(selected_joints, list):
                # Новый формат - список объектов стыков
                for joint_data in selected_joints:
                    joint_type_val = joint_data.get('type')
                    thickness = joint_data.get('thickness')
                    color = joint_data.get('color')
                    quantity = joint_data.get('quantity')
                    
                    joint_type_text = ""
                    if joint_type_val == JointType.BUTTERFLY or joint_type_val == "butterfly":
                        joint_type_text = "Бабочка"
                    elif joint_type_val == JointType.SIMPLE or joint_type_val == "simple":
                        joint_type_text = "Простые"
                    elif joint_type_val == JointType.CLOSING or joint_type_val == "closing":
                        joint_type_text = "Замыкающие"
                    
                    joints_info += f"▪️ {joint_type_text}, {thickness} мм, {color}: {quantity} шт.\n"
            elif isinstance(selected_joints, dict):
                # Словарь (старый формат)
                for joint_key, quantity in selected_joints.items():
                    joint_type_val, thickness, color = joint_key.split('|')
                    joint_type_text = ""
                    if joint_type_val == "butterfly":
                        joint_type_text = "Бабочка"
                    elif joint_type_val == "simple":
                        joint_type_text = "Простые"
                    elif joint_type_val == "closing":
                        joint_type_text = "Замыкающие"
                    
                    joints_info += f"▪️ {joint_type_text}, {thickness} мм, {color}: {quantity} шт.\n"

        # Добавляем информацию о клее если он нужен
        glue_info = ""
        if need_glue and glue_quantity > 0:
            glue_info = f"\nКлей: {glue_quantity} шт.\n"
        
        # Сборка итогового сообщения
        installation_text = "Да" if installation_required else "Нет"
        
        # Создаем сообщение с информацией о заказе
        confirmation_message = (
            f"✅ Заказ #{order.id} успешно оформлен!\n\n"
            f"{products_info}"
            f"{joints_info}"
            f"{glue_info}"
            f"Монтаж: {installation_text}\n"
            f"Телефон: {customer_phone}\n"
            f"Адрес доставки: {delivery_address}\n\n"
            f"Статус заказа: {order.status.value}"
        )
        
        await message.answer(confirmation_message)
        
        # Возвращаемся в главное меню
        await go_back(message, state)
    
    except Exception as e:
        # В случае ошибки откатываем изменения
        db.rollback()
        logging.error(f"Ошибка при оформлении заказа: {e}")
        await message.answer(f"❌ Произошла ошибка при оформлении заказа: {e}")
    
    finally:
        # Закрываем соединение с БД
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

@router.message(SalesStates.waiting_for_order_joint_quantity)
async def process_order_joint_quantity(message: Message, state: FSMContext):
    """Обработка количества стыков"""
    if message.text == "◀️ Назад":
        await state.set_state(SalesStates.waiting_for_order_joint_color)
        await message.answer(
            "Выберите цвет стыка:",
            reply_markup=await get_colors_keyboard()
        )
        return
    
    try:
        # Проверяем, что количество является числом
        quantity = int(message.text)
        if quantity <= 0:
            raise ValueError("Количество должно быть положительным числом")
        
        # Получаем данные из состояния
        data = await state.get_data()
        joint_type = data.get("joint_type")
        joint_color = data.get("joint_color")
        joint_thickness = data.get("joint_thickness")
        
        db = next(get_db())
        
        # Проверяем наличие стыков в базе
        joint = db.query(Joint).filter(
            Joint.type == joint_type,
            Joint.color == joint_color,
            Joint.thickness == joint_thickness
        ).first()
        
        if not joint or joint.quantity < quantity:
            db.close()
            await message.answer(
                f"❌ Ошибка: недостаточно стыков типа {joint_type.value}, цвета {joint_color}, толщиной {joint_thickness} мм на складе.\n"
                f"Доступно: {joint.quantity if joint else 0} шт.\n"
                f"Пожалуйста, введите другое количество:"
            )
            return
        
        # Добавляем стык в список стыков
        selected_joints = data.get("selected_joints", [])
        
        # Создаем объект стыка
        joint_data = {
            "type": joint_type.value,
            "color": joint_color,
            "thickness": joint_thickness,
            "quantity": quantity
        }
        
        # Проверяем, есть ли уже стык такого типа, цвета и толщины
        found = False
        for i, existing_joint in enumerate(selected_joints):
            if (existing_joint.get("type") == joint_type.value and 
                existing_joint.get("color") == joint_color and
                existing_joint.get("thickness") == joint_thickness):
                # Обновляем количество существующего стыка
                selected_joints[i]["quantity"] = quantity
                found = True
                break
        
        # Если стыка такого типа нет, добавляем новый
        if not found:
            selected_joints.append(joint_data)
        
        # Обновляем состояние
        await state.update_data(selected_joints=selected_joints)
        
        # Спрашиваем, хочет ли пользователь добавить еще стыки
        await state.set_state(SalesStates.waiting_for_order_more_joints)
        
        # Получаем все выбранные стыки для отображения
        joints_info = ""
        for joint_item in selected_joints:
            joint_type_val = joint_item.get("type")
            joint_color_val = joint_item.get("color")
            joint_thickness_val = joint_item.get("thickness")
            joint_quantity_val = joint_item.get("quantity")
            
            joint_type_text = ""
            if joint_type_val == JointType.BUTTERFLY.value:
                joint_type_text = "Бабочка"
            elif joint_type_val == JointType.SIMPLE.value:
                joint_type_text = "Простые"
            elif joint_type_val == JointType.CLOSING.value:
                joint_type_text = "Замыкающие"
            
            joints_info += f"▪️ {joint_type_text}, {joint_thickness_val} мм, {joint_color_val}: {joint_quantity_val} шт.\n"
        
        # Формируем клавиатуру для выбора
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ Да, добавить еще стыки")],
                [KeyboardButton(text="❌ Нет, перейти дальше")],
                [KeyboardButton(text="◀️ Назад")]
            ],
            resize_keyboard=True
        )
        
        await message.answer(
            f"Выбранные стыки:\n{joints_info}\n\nХотите добавить еще стыки?",
            reply_markup=keyboard
        )
        
        db.close()
    except ValueError:
        await message.answer(
            "❌ Ошибка: введите целое положительное число.\nПопробуйте снова:"
        )
    except Exception as e:
        logging.error(f"Ошибка при обработке количества стыков: {e}")
        await message.answer(
            f"❌ Произошла ошибка: {e}\nПопробуйте снова:"
        )

@router.message(SalesStates.waiting_for_order_more_joints)
async def process_order_more_joints(message: Message, state: FSMContext):
    """Обработка ответа о добавлении дополнительных стыков"""
    user_choice = message.text.strip()
    
    if user_choice == "◀️ Назад":
        # Отменяем последний добавленный стык
        data = await state.get_data()
        selected_joints = data.get('selected_joints', [])
        
        if selected_joints:
            # Удаляем последний добавленный стык
            selected_joints.pop()
            await state.update_data(selected_joints=selected_joints)
            
            # Возвращаемся к выбору количества
            last_joint = data.get('last_joint', {})
            joint_type = last_joint.get('type', data.get('joint_type'))
            thickness = last_joint.get('thickness', data.get('joint_thickness'))
            color = last_joint.get('color', data.get('joint_color'))
            
            await message.answer(
                f"Введите количество стыков ({joint_type}, {thickness} мм, {color}):",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text="◀️ Назад")]
                    ],
                    resize_keyboard=True
                )
            )
            await state.set_state(SalesStates.waiting_for_order_joint_quantity)
            return
        else:
            # Если стыков нет, возвращаемся к выбору типа стыка
            await message.answer(
                "Выберите тип стыка:",
                reply_markup=get_joint_type_keyboard()
            )
            await state.set_state(SalesStates.waiting_for_order_joint_type)
            return
    
    if user_choice == "✅ Да":
        # Пользователь хочет добавить еще стыки, возвращаемся к выбору типа
        await message.answer(
            "Выберите тип стыка:",
            reply_markup=get_joint_type_keyboard()
        )
        await state.set_state(SalesStates.waiting_for_order_joint_type)
    elif user_choice == "❌ Нет":
        # Пользователь закончил выбор стыков, переходим к вопросу о клее
        await message.answer(
            "Нужен ли клей для стыков?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_glue_needed)
    else:
        # Некорректный ввод
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )

@router.message(SalesStates.waiting_for_order_delivery_address)
async def process_order_delivery_address(message: Message, state: FSMContext):
    """Обработка ввода адреса доставки"""
    address = message.text.strip()
    
    # Если адрес не указан, считаем самовывозом
    if address.lower() == "нет":
        address = "Самовывоз"
    
    # Сохраняем адрес доставки
    await state.update_data(delivery_address=address)
    
    # Показываем сводку заказа и запрашиваем подтверждение
    data = await state.get_data()
    
    # Получаем данные о выбранных продуктах
    selected_products = data.get('selected_products', [])
    
    # Получаем данные о выбранных стыках
    selected_joints = data.get('selected_joints', [])
    
    need_joints = data.get('need_joints', False)
    need_glue = data.get('need_glue', False)
    glue_quantity = data.get('glue_quantity', 0)
    installation_required = data.get('installation_required', False)
    customer_phone = data.get('customer_phone', '')
    delivery_address = data.get('delivery_address', '')
    
    # Формируем текст заказа
    order_summary = f"📝 Сводка заказа:\n\n"
    
    # Добавляем информацию о выбранных продуктах
    if selected_products:
        order_summary += f"📦 Выбранные продукты:\n"
        total_panels = 0
        for product in selected_products:
            order_summary += f"▪️ {product['film_code']} (толщина {product['thickness']} мм): {product['quantity']} шт.\n"
            total_panels += product['quantity']
        order_summary += f"Всего панелей: {total_panels} шт.\n\n"
    else:
        order_summary += "Продукты не выбраны\n\n"
    
    # Добавляем информацию о стыках
    if need_joints and selected_joints:
        order_summary += f"🔗 Стыки:\n"
        for joint in selected_joints:
            joint_type = joint.get('type', '')
            joint_type_text = ''
            if joint_type == 'butterfly' or joint_type == JointType.BUTTERFLY:
                joint_type_text = "Бабочка"
            elif joint_type == 'simple' or joint_type == JointType.SIMPLE:
                joint_type_text = "Простые"
            elif joint_type == 'closing' or joint_type == JointType.CLOSING:
                joint_type_text = "Замыкающие"
            
            thickness = joint.get('thickness', '0.5')
            order_summary += f"▪️ {joint_type_text}, {thickness} мм, {joint.get('color', '')}: {joint.get('quantity', 0)} шт.\n"
        order_summary += "\n"
    else:
        order_summary += f"🔗 Стыки: Нет\n\n"
    
    # Добавляем остальную информацию
    order_summary += f"🧴 Клей: {glue_quantity} тюбиков\n"
    order_summary += f"🔧 Монтаж: {'Требуется' if installation_required else 'Не требуется'}\n"
    order_summary += f"📞 Контактный телефон: {customer_phone}\n"
    order_summary += f"🚚 Адрес доставки: {delivery_address}\n"
    
    # Запрашиваем подтверждение
    await state.update_data(order_summary=order_summary)
    await state.set_state(MenuState.SALES_ORDER_CONFIRM)
    
    await message.answer(
        order_summary + "\n\nПожалуйста, подтвердите заказ:",
        reply_markup=get_menu_keyboard(MenuState.SALES_ORDER_CONFIRM)
    )
    await state.set_state(SalesStates.waiting_for_order_confirmation)

@router.message(SalesStates.waiting_for_order_confirmation)
async def process_order_confirmation(message: Message, state: FSMContext):
    """Обработка подтверждения заказа"""
    if message.text.lower() != "подтвердить":
        await message.answer("Заказ не подтвержден. Вы можете вернуться к оформлению заказа позже.")
        await go_back(message, state)
        return
    
    # Получаем данные из состояния
    data = await state.get_data()
    
    # Получаем выбранные продукты из состояния
    selected_products = data.get("selected_products", [])
    
    # Получаем выбранные стыки из состояния
    selected_joints = data.get('selected_joints', [])
    
    need_joints = selected_joints and len(selected_joints) > 0
    need_glue = data.get("need_glue", False)
    customer_phone = data.get("customer_phone", "")
    delivery_address = data.get("delivery_address", "")
    installation_required = data.get("installation_required", False)
    glue_quantity = data.get("glue_quantity", 0)
    
    # Определяем тип заказа (готовая продукция или производство)
    db = next(get_db())
    
    try:
        # Получаем пользователя по telegram_id для получения корректного ID в базе
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        
        if not user:
            await message.answer("❌ Ошибка: пользователь не найден")
            db.close()
            return
        
        # Создаем заказ
        order = Order(
            manager_id=user.id,  # Используем ID пользователя из базы данных, а не telegram_id
            customer_phone=customer_phone,
            delivery_address=delivery_address,
            installation_required=installation_required,
            status=OrderStatus.NEW
        )
        db.add(order)
        db.flush()
        
        # Добавляем продукты в заказ через OrderItem
        for product in selected_products:
            film_code = product['film_code']
            thickness = float(product['thickness'])
            qty = product['quantity']
            
            film = db.query(Film).filter(Film.code == film_code).first()
            if not film:
                continue
            
            # Проверяем, есть ли готовая продукция
            finished_product = db.query(FinishedProduct).join(Film).filter(
                Film.code == film_code,
                FinishedProduct.thickness == thickness
            ).first()
            
            # Создаем запись OrderItem
            order_item = OrderItem(
                order_id=order.id,
                color=film_code,
                thickness=thickness,
                quantity=qty
            )
            db.add(order_item)
            
            if finished_product and finished_product.quantity >= qty:
                # Если есть готовая продукция, уменьшаем ее количество
                finished_product.quantity -= qty
                
                # Создаем операцию для готовой продукции
                operation = Operation(
                    operation_type=OperationType.READY_PRODUCT_OUT.value,
                    quantity=qty,
                    user_id=user.id  # Используем ID пользователя из базы
                )
                db.add(operation)
            else:
                # Если нет готовой продукции, создаем заказ на производство
                production_order = ProductionOrder(
                    manager_id=user.id,  # Используем ID пользователя из базы
                    panel_quantity=qty,
                    film_color=film_code,
                    panel_thickness=thickness,
                    status="new"
                )
                db.add(production_order)
        
        # Если нужны стыки, добавляем их в заказ
        if need_joints:
            if isinstance(selected_joints, list):
                # Новый формат - список объектов стыков
                for joint_data in selected_joints:
                    joint_type_val = joint_data.get('type')
                    thickness = joint_data.get('thickness')
                    color = joint_data.get('color')
                    quantity = joint_data.get('quantity')
                    
                    joint_type_text = ""
                    if joint_type_val == JointType.BUTTERFLY or joint_type_val == "butterfly":
                        joint_type_text = "Бабочка"
                    elif joint_type_val == JointType.SIMPLE or joint_type_val == "simple":
                        joint_type_text = "Простые"
                    elif joint_type_val == JointType.CLOSING or joint_type_val == "closing":
                        joint_type_text = "Замыкающие"
                    
                    joints_info += f"▪️ {joint_type_text}, {thickness} мм, {color}: {quantity} шт.\n"
            elif isinstance(selected_joints, dict):
                # Словарь (старый формат)
                for joint_key, quantity in selected_joints.items():
                    joint_type_val, thickness, color = joint_key.split('|')
                    joint_type_text = ""
                    if joint_type_val == "butterfly":
                        joint_type_text = "Бабочка"
                    elif joint_type_val == "simple":
                        joint_type_text = "Простые"
                    elif joint_type_val == "closing":
                        joint_type_text = "Замыкающие"
                    
                    joints_info += f"▪️ {joint_type_text}, {thickness} мм, {color}: {quantity} шт.\n"

        # Добавляем информацию о клее если он нужен
        glue_info = ""
        if need_glue and glue_quantity > 0:
            glue_info = f"\nКлей: {glue_quantity} шт.\n"
        
        # Сборка итогового сообщения
        installation_text = "Да" if installation_required else "Нет"
        
        # Создаем сообщение с информацией о заказе
        confirmation_message = (
            f"✅ Заказ #{order.id} успешно оформлен!\n\n"
            f"{products_info}"
            f"{joints_info}"
            f"{glue_info}"
            f"Монтаж: {installation_text}\n"
            f"Телефон: {customer_phone}\n"
            f"Адрес доставки: {delivery_address}\n\n"
            f"Статус заказа: {order.status.value}"
        )
        
        await message.answer(confirmation_message)
        
        # Возвращаемся в главное меню
        await go_back(message, state)
    
    except Exception as e:
        # В случае ошибки откатываем изменения
        db.rollback()
        logging.error(f"Ошибка при оформлении заказа: {e}")
        await message.answer(f"❌ Произошла ошибка при оформлении заказа: {e}")
    
    finally:
        # Закрываем соединение с БД
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

@router.message(SalesStates.waiting_for_order_glue_needed)
async def process_order_glue_needed(message: Message, state: FSMContext):
    """Обработка ответа о необходимости клея для стыков"""
    user_choice = message.text.strip()
    
    if user_choice == "✅ Да":
        # Проверяем наличие клея в базе данных
        db = next(get_db())
        try:
            glue = db.query(Glue).filter(Glue.quantity > 0).first()
            
            if not glue:
                await message.answer(
                    "❌ К сожалению, клей отсутствует на складе.",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[
                            [KeyboardButton(text="◀️ Назад")]
                        ],
                        resize_keyboard=True
                    )
                )
                return
            
            await message.answer(
                f"Введите количество тюбиков клея (доступно: {glue.quantity} шт.):",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text="◀️ Назад")]
                    ],
                    resize_keyboard=True
                )
            )
            await state.set_state(SalesStates.waiting_for_order_glue_quantity)
        finally:
            db.close()
    elif user_choice == "❌ Нет":
        # Клей не нужен, сохраняем нулевое количество
        await state.update_data(glue_quantity=0)
        
        # Переходим к запросу о монтаже
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                [KeyboardButton(text="◀️ Назад")]
            ],
            resize_keyboard=True
        )
        await message.answer(
            "Требуется ли монтаж?",
            reply_markup=keyboard
        )
        await state.set_state(SalesStates.waiting_for_order_installation)
    else:
        # Некорректный ввод
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )

@router.message(SalesStates.waiting_for_order_installation)
async def process_order_installation(message: Message, state: FSMContext):
    """Обработка выбора монтажа"""
    response = message.text.strip()
    
    if response == "◀️ Назад":
        # Возвращаемся к предыдущему шагу - запросу о клее
        await message.answer(
            "Вам нужен клей?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_glue_needed)
        return

    installation_required = False
    if response == "✅ Да":
        installation_required = True
    elif response == "❌ Нет":
        installation_required = False
    else:
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        return

    # Сохраняем выбор установки
    await state.update_data(installation_required=installation_required)

    # Запрашиваем контактный номер телефона
    await message.answer(
        "Введите контактный номер телефона клиента:",
        reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
    )
    await state.set_state(SalesStates.waiting_for_order_customer_phone)

@router.message(SalesStates.waiting_for_order_customer_phone)
async def process_order_customer_phone(message: Message, state: FSMContext):
    """Обработка ввода контактного номера клиента"""
    phone = message.text.strip()
    
    if message.text == "◀️ Назад":
        # Возвращаемся к предыдущему шагу - запросу о монтаже
        await message.answer(
            "Требуется ли монтаж?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_installation)
        return
    
    # Простая проверка на формат телефона
    if not phone or len(phone) < 5:  # Минимальная длина для телефона
        await message.answer(
            "❌ Пожалуйста, введите корректный номер телефона",
            reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
        )
        return
    
    # Сохраняем номер телефона
    await state.update_data(customer_phone=phone)
    
    # Запрашиваем адрес доставки
    await message.answer(
        "Введите адрес доставки (или напишите 'нет' если самовывоз):",
        reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
    )
    await state.set_state(SalesStates.waiting_for_order_delivery_address)

@router.message(SalesStates.waiting_for_order_glue_quantity)
async def process_order_glue_quantity(message: Message, state: FSMContext):
    """Обработка ввода количества клея"""
    try:
        quantity = int(message.text.strip())
        if quantity <= 0:
            await message.answer("❌ Количество должно быть больше 0")
            return
            
        # Получаем данные о выбранном клее
        data = await state.get_data()
        glue_quantity = quantity
        
        # Сохраняем количество клея
        await state.update_data(glue_quantity=glue_quantity)
        
        # Переходим к запросу о монтаже
        await message.answer(
            "Требуется ли монтаж?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_installation)
    except ValueError:
        await message.answer(
            "Пожалуйста, введите корректное число.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )

@router.message(SalesStates.waiting_for_order_glue_needed)
async def process_order_glue_needed(message: Message, state: FSMContext):
    """Обработка ответа о необходимости клея для стыков"""
    user_choice = message.text.strip()
    
    if user_choice == "✅ Да":
        # Проверяем наличие клея в базе данных
        db = next(get_db())
        try:
            glue = db.query(Glue).filter(Glue.quantity > 0).first()
            
            if not glue:
                await message.answer(
                    "❌ К сожалению, клей отсутствует на складе.",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[
                            [KeyboardButton(text="◀️ Назад")]
                        ],
                        resize_keyboard=True
                    )
                )
                return
            
            await message.answer(
                f"Введите количество тюбиков клея (доступно: {glue.quantity} шт.):",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text="◀️ Назад")]
                    ],
                    resize_keyboard=True
                )
            )
            await state.set_state(SalesStates.waiting_for_order_glue_quantity)
        finally:
            db.close()
    elif user_choice == "❌ Нет":
        # Клей не нужен, сохраняем нулевое количество
        await state.update_data(glue_quantity=0)
        
        # Переходим к запросу о монтаже
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                [KeyboardButton(text="◀️ Назад")]
            ],
            resize_keyboard=True
        )
        await message.answer(
            "Требуется ли монтаж?",
            reply_markup=keyboard
        )
        await state.set_state(SalesStates.waiting_for_order_installation)
    else:
        # Некорректный ввод
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )

@router.message(SalesStates.waiting_for_order_installation)
async def process_order_installation(message: Message, state: FSMContext):
    """Обработка выбора монтажа"""
    response = message.text.strip()
    
    if response == "◀️ Назад":
        # Возвращаемся к предыдущему шагу - запросу о клее
        await message.answer(
            "Вам нужен клей?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_glue_needed)
        return

    installation_required = False
    if response == "✅ Да":
        installation_required = True
    elif response == "❌ Нет":
        installation_required = False
    else:
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        return

    # Сохраняем выбор установки
    await state.update_data(installation_required=installation_required)

    # Запрашиваем контактный номер телефона
    await message.answer(
        "Введите контактный номер телефона клиента:",
        reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
    )
    await state.set_state(SalesStates.waiting_for_order_customer_phone)

@router.message(SalesStates.waiting_for_order_delivery_address)
async def process_order_delivery_address(message: Message, state: FSMContext):
    """Обработка ввода адреса доставки"""
    address = message.text.strip()
    
    # Если адрес не указан, считаем самовывозом
    if address.lower() == "нет":
        address = "Самовывоз"
    
    # Сохраняем адрес доставки
    await state.update_data(delivery_address=address)
    
    # Показываем сводку заказа и запрашиваем подтверждение
    data = await state.get_data()
    
    # Получаем данные о выбранных продуктах
    selected_products = data.get('selected_products', [])
    
    # Получаем данные о выбранных стыках
    selected_joints = data.get('selected_joints', [])
    
    need_joints = data.get('need_joints', False)
    need_glue = data.get('need_glue', False)
    glue_quantity = data.get('glue_quantity', 0)
    installation_required = data.get('installation_required', False)
    customer_phone = data.get('customer_phone', '')
    delivery_address = data.get('delivery_address', '')
    
    # Формируем текст заказа
    order_summary = f"📝 Сводка заказа:\n\n"
    
    # Добавляем информацию о выбранных продуктах
    if selected_products:
        order_summary += f"📦 Выбранные продукты:\n"
        total_panels = 0
        for product in selected_products:
            order_summary += f"▪️ {product['film_code']} (толщина {product['thickness']} мм): {product['quantity']} шт.\n"
            total_panels += product['quantity']
        order_summary += f"Всего панелей: {total_panels} шт.\n\n"
    else:
        order_summary += "Продукты не выбраны\n\n"
    
    # Добавляем информацию о стыках
    if need_joints and selected_joints:
        order_summary += f"🔗 Стыки:\n"
        for joint in selected_joints:
            joint_type = joint.get('type', '')
            joint_type_text = ''
            if joint_type == 'butterfly' or joint_type == JointType.BUTTERFLY:
                joint_type_text = "Бабочка"
            elif joint_type == 'simple' or joint_type == JointType.SIMPLE:
                joint_type_text = "Простые"
            elif joint_type == 'closing' or joint_type == JointType.CLOSING:
                joint_type_text = "Замыкающие"
            
            thickness = joint.get('thickness', '0.5')
            order_summary += f"▪️ {joint_type_text}, {thickness} мм, {joint.get('color', '')}: {joint.get('quantity', 0)} шт.\n"
        order_summary += "\n"
    else:
        order_summary += f"🔗 Стыки: Нет\n\n"
    
    # Добавляем остальную информацию
    order_summary += f"🧴 Клей: {glue_quantity} тюбиков\n"
    order_summary += f"🔧 Монтаж: {'Требуется' if installation_required else 'Не требуется'}\n"
    order_summary += f"📞 Контактный телефон: {customer_phone}\n"
    order_summary += f"🚚 Адрес доставки: {delivery_address}\n"
    
    # Запрашиваем подтверждение
    await state.update_data(order_summary=order_summary)
    await state.set_state(MenuState.SALES_ORDER_CONFIRM)
    
    await message.answer(
        order_summary + "\n\nПожалуйста, подтвердите заказ:",
        reply_markup=get_menu_keyboard(MenuState.SALES_ORDER_CONFIRM)
    )
    await state.set_state(SalesStates.waiting_for_order_confirmation)

@router.message(SalesStates.waiting_for_order_confirmation)
async def process_order_confirmation(message: Message, state: FSMContext):
    """Обработка подтверждения заказа"""
    if message.text.lower() != "подтвердить":
        await message.answer("Заказ не подтвержден. Вы можете вернуться к оформлению заказа позже.")
        await go_back(message, state)
        return
    
    # Получаем данные из состояния
    data = await state.get_data()
    
    # Получаем выбранные продукты из состояния
    selected_products = data.get("selected_products", [])
    
    # Получаем выбранные стыки из состояния
    selected_joints = data.get('selected_joints', [])
    
    need_joints = selected_joints and len(selected_joints) > 0
    need_glue = data.get("need_glue", False)
    customer_phone = data.get("customer_phone", "")
    delivery_address = data.get("delivery_address", "")
    installation_required = data.get("installation_required", False)
    glue_quantity = data.get("glue_quantity", 0)
    
    # Определяем тип заказа (готовая продукция или производство)
    db = next(get_db())
    
    try:
        # Получаем пользователя по telegram_id для получения корректного ID в базе
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        
        if not user:
            await message.answer("❌ Ошибка: пользователь не найден")
            db.close()
            return
        
        # Создаем заказ
        order = Order(
            manager_id=user.id,  # Используем ID пользователя из базы данных, а не telegram_id
            customer_phone=customer_phone,
            delivery_address=delivery_address,
            installation_required=installation_required,
            status=OrderStatus.NEW
        )
        db.add(order)
        db.flush()
        
        # Добавляем продукты в заказ через OrderItem
        for product in selected_products:
            film_code = product['film_code']
            thickness = float(product['thickness'])
            qty = product['quantity']
            
            film = db.query(Film).filter(Film.code == film_code).first()
            if not film:
                continue
            
            # Проверяем, есть ли готовая продукция
            finished_product = db.query(FinishedProduct).join(Film).filter(
                Film.code == film_code,
                FinishedProduct.thickness == thickness
            ).first()
            
            # Создаем запись OrderItem
            order_item = OrderItem(
                order_id=order.id,
                color=film_code,
                thickness=thickness,
                quantity=qty
            )
            db.add(order_item)
            
            if finished_product and finished_product.quantity >= qty:
                # Если есть готовая продукция, уменьшаем ее количество
                finished_product.quantity -= qty
                
                # Создаем операцию для готовой продукции
                operation = Operation(
                    operation_type=OperationType.READY_PRODUCT_OUT.value,
                    quantity=qty,
                    user_id=user.id  # Используем ID пользователя из базы
                )
                db.add(operation)
            else:
                # Если нет готовой продукции, создаем заказ на производство
                production_order = ProductionOrder(
                    manager_id=user.id,  # Используем ID пользователя из базы
                    panel_quantity=qty,
                    film_color=film_code,
                    panel_thickness=thickness,
                    status="new"
                )
                db.add(production_order)
        
        # Если нужны стыки, добавляем их в заказ
        if need_joints:
            if isinstance(selected_joints, list):
                # Новый формат - список объектов стыков
                for joint_data in selected_joints:
                    joint_type_val = joint_data.get('type')
                    thickness = joint_data.get('thickness')
                    color = joint_data.get('color')
                    quantity = joint_data.get('quantity')
                    
                    joint_type_text = ""
                    if joint_type_val == JointType.BUTTERFLY or joint_type_val == "butterfly":
                        joint_type_text = "Бабочка"
                    elif joint_type_val == JointType.SIMPLE or joint_type_val == "simple":
                        joint_type_text = "Простые"
                    elif joint_type_val == JointType.CLOSING or joint_type_val == "closing":
                        joint_type_text = "Замыкающие"
                    
                    joints_info += f"▪️ {joint_type_text}, {thickness} мм, {color}: {quantity} шт.\n"
            elif isinstance(selected_joints, dict):
                # Словарь (старый формат)
                for joint_key, quantity in selected_joints.items():
                    joint_type_val, thickness, color = joint_key.split('|')
                    joint_type_text = ""
                    if joint_type_val == "butterfly":
                        joint_type_text = "Бабочка"
                    elif joint_type_val == "simple":
                        joint_type_text = "Простые"
                    elif joint_type_val == "closing":
                        joint_type_text = "Замыкающие"
                    
                    joints_info += f"▪️ {joint_type_text}, {thickness} мм, {color}: {quantity} шт.\n"

        # Добавляем информацию о клее если он нужен
        glue_info = ""
        if need_glue and glue_quantity > 0:
            glue_info = f"\nКлей: {glue_quantity} шт.\n"
        
        # Сборка итогового сообщения
        installation_text = "Да" if installation_required else "Нет"
        
        # Создаем сообщение с информацией о заказе
        confirmation_message = (
            f"✅ Заказ #{order.id} успешно оформлен!\n\n"
            f"{products_info}"
            f"{joints_info}"
            f"{glue_info}"
            f"Монтаж: {installation_text}\n"
            f"Телефон: {customer_phone}\n"
            f"Адрес доставки: {delivery_address}\n\n"
            f"Статус заказа: {order.status.value}"
        )
        
        await message.answer(confirmation_message)
        
        # Возвращаемся в главное меню
        await go_back(message, state)
    
    except Exception as e:
        # В случае ошибки откатываем изменения
        db.rollback()
        logging.error(f"Ошибка при оформлении заказа: {e}")
        await message.answer(f"❌ Произошла ошибка при оформлении заказа: {e}")
    
    finally:
        # Закрываем соединение с БД
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

@router.message(SalesStates.waiting_for_order_glue_needed)
async def process_order_glue_needed(message: Message, state: FSMContext):
    """Обработка ответа о необходимости клея для стыков"""
    user_choice = message.text.strip()
    
    if user_choice == "✅ Да":
        # Проверяем наличие клея в базе данных
        db = next(get_db())
        try:
            glue = db.query(Glue).filter(Glue.quantity > 0).first()
            
            if not glue:
                await message.answer(
                    "❌ К сожалению, клей отсутствует на складе.",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[
                            [KeyboardButton(text="◀️ Назад")]
                        ],
                        resize_keyboard=True
                    )
                )
                return
            
            await message.answer(
                f"Введите количество тюбиков клея (доступно: {glue.quantity} шт.):",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text="◀️ Назад")]
                    ],
                    resize_keyboard=True
                )
            )
            await state.set_state(SalesStates.waiting_for_order_glue_quantity)
        finally:
            db.close()
    elif user_choice == "❌ Нет":
        # Клей не нужен, сохраняем нулевое количество
        await state.update_data(glue_quantity=0)
        
        # Переходим к запросу о монтаже
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                [KeyboardButton(text="◀️ Назад")]
            ],
            resize_keyboard=True
        )
        await message.answer(
            "Требуется ли монтаж?",
            reply_markup=keyboard
        )
        await state.set_state(SalesStates.waiting_for_order_installation)
    else:
        # Некорректный ввод
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )

@router.message(SalesStates.waiting_for_order_installation)
async def process_order_installation(message: Message, state: FSMContext):
    """Обработка выбора монтажа"""
    response = message.text.strip()
    
    if response == "◀️ Назад":
        # Возвращаемся к предыдущему шагу - запросу о клее
        await message.answer(
            "Вам нужен клей?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_glue_needed)
        return

    installation_required = False
    if response == "✅ Да":
        installation_required = True
    elif response == "❌ Нет":
        installation_required = False
    else:
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        return

    # Сохраняем выбор установки
    await state.update_data(installation_required=installation_required)

    # Запрашиваем контактный номер телефона
    await message.answer(
        "Введите контактный номер телефона клиента:",
        reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
    )
    await state.set_state(SalesStates.waiting_for_order_customer_phone)

@router.message(SalesStates.waiting_for_order_customer_phone)
async def process_order_customer_phone(message: Message, state: FSMContext):
    """Обработка ввода контактного номера клиента"""
    phone = message.text.strip()
    
    if message.text == "◀️ Назад":
        # Возвращаемся к предыдущему шагу - запросу о монтаже
        await message.answer(
            "Требуется ли монтаж?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_installation)
        return
    
    # Простая проверка на формат телефона
    if not phone or len(phone) < 5:  # Минимальная длина для телефона
        await message.answer(
            "❌ Пожалуйста, введите корректный номер телефона",
            reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
        )
        return
    
    # Сохраняем номер телефона
    await state.update_data(customer_phone=phone)
    
    # Запрашиваем адрес доставки
    await message.answer(
        "Введите адрес доставки (или напишите 'нет' если самовывоз):",
        reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
    )
    await state.set_state(SalesStates.waiting_for_order_delivery_address)

@router.message(SalesStates.waiting_for_order_glue_quantity)
async def process_order_glue_quantity(message: Message, state: FSMContext):
    """Обработка ввода количества клея"""
    try:
        quantity = int(message.text.strip())
        if quantity <= 0:
            await message.answer("❌ Количество должно быть больше 0")
            return
            
        # Получаем данные о выбранном клее
        data = await state.get_data()
        glue_quantity = quantity
        
        # Сохраняем количество клея
        await state.update_data(glue_quantity=glue_quantity)
        
        # Переходим к запросу о монтаже
        await message.answer(
            "Требуется ли монтаж?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_installation)
    except ValueError:
        await message.answer(
            "Пожалуйста, введите корректное число.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )

@router.message(SalesStates.waiting_for_order_glue_needed)
async def process_order_glue_needed(message: Message, state: FSMContext):
    """Обработка ответа о необходимости клея для стыков"""
    user_choice = message.text.strip()
    
    if user_choice == "✅ Да":
        # Проверяем наличие клея в базе данных
        db = next(get_db())
        try:
            glue = db.query(Glue).filter(Glue.quantity > 0).first()
            
            if not glue:
                await message.answer(
                    "❌ К сожалению, клей отсутствует на складе.",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[
                            [KeyboardButton(text="◀️ Назад")]
                        ],
                        resize_keyboard=True
                    )
                )
                return
            
            await message.answer(
                f"Введите количество тюбиков клея (доступно: {glue.quantity} шт.):",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text="◀️ Назад")]
                    ],
                    resize_keyboard=True
                )
            )
            await state.set_state(SalesStates.waiting_for_order_glue_quantity)
        finally:
            db.close()
    elif user_choice == "❌ Нет":
        # Клей не нужен, сохраняем нулевое количество
        await state.update_data(glue_quantity=0)
        
        # Переходим к запросу о монтаже
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                [KeyboardButton(text="◀️ Назад")]
            ],
            resize_keyboard=True
        )
        await message.answer(
            "Требуется ли монтаж?",
            reply_markup=keyboard
        )
        await state.set_state(SalesStates.waiting_for_order_installation)
    else:
        # Некорректный ввод
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )

@router.message(SalesStates.waiting_for_order_installation)
async def process_order_installation(message: Message, state: FSMContext):
    """Обработка выбора монтажа"""
    response = message.text.strip()
    
    if response == "◀️ Назад":
        # Возвращаемся к предыдущему шагу - запросу о клее
        await message.answer(
            "Вам нужен клей?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_glue_needed)
        return

    installation_required = False
    if response == "✅ Да":
        installation_required = True
    elif response == "❌ Нет":
        installation_required = False
    else:
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        return

    # Сохраняем выбор установки
    await state.update_data(installation_required=installation_required)

    # Запрашиваем контактный номер телефона
    await message.answer(
        "Введите контактный номер телефона клиента:",
        reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
    )
    await state.set_state(SalesStates.waiting_for_order_customer_phone)

@router.message(SalesStates.waiting_for_order_customer_phone)
async def process_order_customer_phone(message: Message, state: FSMContext):
    """Обработка ввода контактного номера клиента"""
    phone = message.text.strip()
    
    if message.text == "◀️ Назад":
        # Возвращаемся к предыдущему шагу - запросу о монтаже
        await message.answer(
            "Требуется ли монтаж?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_installation)
        return
    
    # Простая проверка на формат телефона
    if not phone or len(phone) < 5:  # Минимальная длина для телефона
        await message.answer(
            "❌ Пожалуйста, введите корректный номер телефона",
            reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
        )
        return
    
    # Сохраняем номер телефона
    await state.update_data(customer_phone=phone)
    
    # Запрашиваем адрес доставки
    await message.answer(
        "Введите адрес доставки (или напишите 'нет' если самовывоз):",
        reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
    )
    await state.set_state(SalesStates.waiting_for_order_delivery_address)

@router.message(SalesStates.waiting_for_order_joint_quantity)
async def process_order_joint_quantity(message: Message, state: FSMContext):
    """Обработка количества стыков"""
    if message.text == "◀️ Назад":
        await state.set_state(SalesStates.waiting_for_order_joint_color)
    await message.answer(
            "Выберите цвет стыка:",
            reply_markup=await get_colors_keyboard()
        )
        return
    
    try:
        # Проверяем, что количество является числом
        quantity = int(message.text)
        if quantity <= 0:
            raise ValueError("Количество должно быть положительным числом")
    
    # Получаем данные из состояния
    data = await state.get_data()
        joint_type = data.get("joint_type")
        joint_color = data.get("joint_color")
        joint_thickness = data.get("joint_thickness")
        
    db = next(get_db())
    
        # Проверяем наличие стыков в базе
        joint = db.query(Joint).filter(
            Joint.type == joint_type,
            Joint.color == joint_color,
            Joint.thickness == joint_thickness
        ).first()
        
        if not joint or joint.quantity < quantity:
            db.close()
            await message.answer(
                f"❌ Ошибка: недостаточно стыков типа {joint_type.value}, цвета {joint_color}, толщиной {joint_thickness} мм на складе.\n"
                f"Доступно: {joint.quantity if joint else 0} шт.\n"
                f"Пожалуйста, введите другое количество:"
            )
            return
        
        # Добавляем стык в список стыков
        selected_joints = data.get("selected_joints", [])
        
        # Создаем объект стыка
        joint_data = {
            "type": joint_type.value,
            "color": joint_color,
            "thickness": joint_thickness,
            "quantity": quantity
        }
        
        # Проверяем, есть ли уже стык такого типа, цвета и толщины
        found = False
        for i, existing_joint in enumerate(selected_joints):
            if (existing_joint.get("type") == joint_type.value and 
                existing_joint.get("color") == joint_color and
                existing_joint.get("thickness") == joint_thickness):
                # Обновляем количество существующего стыка
                selected_joints[i]["quantity"] = quantity
                found = True
                break
        
        # Если стыка такого типа нет, добавляем новый
        if not found:
            selected_joints.append(joint_data)
        
        # Обновляем состояние
        await state.update_data(selected_joints=selected_joints)
        
        # Спрашиваем, хочет ли пользователь добавить еще стыки
        await state.set_state(SalesStates.waiting_for_order_more_joints)
        
        # Получаем все выбранные стыки для отображения
        joints_info = ""
        for joint_item in selected_joints:
            joint_type_val = joint_item.get("type")
            joint_color_val = joint_item.get("color")
            joint_thickness_val = joint_item.get("thickness")
            joint_quantity_val = joint_item.get("quantity")
                    
                    joint_type_text = ""
            if joint_type_val == JointType.BUTTERFLY.value:
                        joint_type_text = "Бабочка"
            elif joint_type_val == JointType.SIMPLE.value:
                        joint_type_text = "Простые"
            elif joint_type_val == JointType.CLOSING.value:
                        joint_type_text = "Замыкающие"
                    
            joints_info += f"▪️ {joint_type_text}, {joint_thickness_val} мм, {joint_color_val}: {joint_quantity_val} шт.\n"
        
        # Формируем клавиатуру для выбора
        keyboard = ReplyKeyboardMarkup(
                        keyboard=[
                [KeyboardButton(text="✅ Да, добавить еще стыки")],
                [KeyboardButton(text="❌ Нет, перейти дальше")],
                            [KeyboardButton(text="◀️ Назад")]
                        ],
                        resize_keyboard=True
                    )
            
            await message.answer(
            f"Выбранные стыки:\n{joints_info}\n\nХотите добавить еще стыки?",
            reply_markup=keyboard
        )
        
            db.close()
    except ValueError:
        await message.answer(
            "❌ Ошибка: введите целое положительное число.\nПопробуйте снова:"
        )
    except Exception as e:
        logging.error(f"Ошибка при обработке количества стыков: {e}")
        await message.answer(
            f"❌ Произошла ошибка: {e}\nПопробуйте снова:"
        )

@router.message(SalesStates.waiting_for_order_more_joints)
async def process_order_more_joints(message: Message, state: FSMContext):
    """Обработка ответа о добавлении дополнительных стыков"""
    user_choice = message.text.strip()
    
    if user_choice == "◀️ Назад":
        # Отменяем последний добавленный стык
        data = await state.get_data()
        selected_joints = data.get('selected_joints', [])
        
        if selected_joints:
            # Удаляем последний добавленный стык
            selected_joints.pop()
            await state.update_data(selected_joints=selected_joints)
            
            # Возвращаемся к выбору количества
            last_joint = data.get('last_joint', {})
            joint_type = last_joint.get('type', data.get('joint_type'))
            thickness = last_joint.get('thickness', data.get('joint_thickness'))
            color = last_joint.get('color', data.get('joint_color'))
            
    await message.answer(
                f"Введите количество стыков ({joint_type}, {thickness} мм, {color}):",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
            await state.set_state(SalesStates.waiting_for_order_joint_quantity)
        return
        else:
            # Если стыков нет, возвращаемся к выбору типа стыка
        await message.answer(
                "Выберите тип стыка:",
                reply_markup=get_joint_type_keyboard()
        )
            await state.set_state(SalesStates.waiting_for_order_joint_type)
        return
    
    if user_choice == "✅ Да":
        # Пользователь хочет добавить еще стыки, возвращаемся к выбору типа
    await message.answer(
            "Выберите тип стыка:",
            reply_markup=get_joint_type_keyboard()
        )
        await state.set_state(SalesStates.waiting_for_order_joint_type)
    elif user_choice == "❌ Нет":
        # Пользователь закончил выбор стыков, переходим к вопросу о клее
        await message.answer(
            "Нужен ли клей для стыков?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_glue_needed)
    else:
        # Некорректный ввод
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )

@router.message(SalesStates.waiting_for_order_delivery_address)
async def process_order_delivery_address(message: Message, state: FSMContext):
    """Обработка ввода адреса доставки"""
    address = message.text.strip()
    
    # Если адрес не указан, считаем самовывозом
    if address.lower() == "нет":
        address = "Самовывоз"
    
    # Сохраняем адрес доставки
    await state.update_data(delivery_address=address)
    
    # Показываем сводку заказа и запрашиваем подтверждение
    data = await state.get_data()
    
    # Получаем данные о выбранных продуктах
    selected_products = data.get('selected_products', [])
    
    # Получаем данные о выбранных стыках
    selected_joints = data.get('selected_joints', [])
    
    need_joints = data.get('need_joints', False)
    need_glue = data.get('need_glue', False)
    glue_quantity = data.get('glue_quantity', 0)
    installation_required = data.get('installation_required', False)
    customer_phone = data.get('customer_phone', '')
    delivery_address = data.get('delivery_address', '')
    
    # Формируем текст заказа
    order_summary = f"📝 Сводка заказа:\n\n"
    
    # Добавляем информацию о выбранных продуктах
    if selected_products:
        order_summary += f"📦 Выбранные продукты:\n"
        total_panels = 0
        for product in selected_products:
            order_summary += f"▪️ {product['film_code']} (толщина {product['thickness']} мм): {product['quantity']} шт.\n"
            total_panels += product['quantity']
        order_summary += f"Всего панелей: {total_panels} шт.\n\n"
    else:
        order_summary += "Продукты не выбраны\n\n"
    
    # Добавляем информацию о стыках
    if need_joints and selected_joints:
        order_summary += f"🔗 Стыки:\n"
        for joint in selected_joints:
            joint_type = joint.get('type', '')
            joint_type_text = ''
            if joint_type == 'butterfly' or joint_type == JointType.BUTTERFLY:
                joint_type_text = "Бабочка"
            elif joint_type == 'simple' or joint_type == JointType.SIMPLE:
                joint_type_text = "Простые"
            elif joint_type == 'closing' or joint_type == JointType.CLOSING:
                joint_type_text = "Замыкающие"
            
            thickness = joint.get('thickness', '0.5')
            order_summary += f"▪️ {joint_type_text}, {thickness} мм, {joint.get('color', '')}: {joint.get('quantity', 0)} шт.\n"
        order_summary += "\n"
    else:
        order_summary += f"🔗 Стыки: Нет\n\n"
    
    # Добавляем остальную информацию
    order_summary += f"🧴 Клей: {glue_quantity} тюбиков\n"
    order_summary += f"🔧 Монтаж: {'Требуется' if installation_required else 'Не требуется'}\n"
    order_summary += f"📞 Контактный телефон: {customer_phone}\n"
    order_summary += f"🚚 Адрес доставки: {delivery_address}\n"
    
    # Запрашиваем подтверждение
    await state.update_data(order_summary=order_summary)
    await state.set_state(MenuState.SALES_ORDER_CONFIRM)
    
    await message.answer(
        order_summary + "\n\nПожалуйста, подтвердите заказ:",
        reply_markup=get_menu_keyboard(MenuState.SALES_ORDER_CONFIRM)
    )
    await state.set_state(SalesStates.waiting_for_order_confirmation)

@router.message(SalesStates.waiting_for_order_confirmation)
async def process_order_confirmation(message: Message, state: FSMContext):
    """Обработка подтверждения заказа"""
    if message.text.lower() != "подтвердить":
        await message.answer("Заказ не подтвержден. Вы можете вернуться к оформлению заказа позже.")
        await go_back(message, state)
        return
    
    # Получаем данные из состояния
    data = await state.get_data()
    
    # Получаем выбранные продукты из состояния
    selected_products = data.get("selected_products", [])
    
    # Получаем выбранные стыки из состояния
    selected_joints = data.get('selected_joints', [])
    
    need_joints = selected_joints and len(selected_joints) > 0
    need_glue = data.get("need_glue", False)
    customer_phone = data.get("customer_phone", "")
    delivery_address = data.get("delivery_address", "")
    installation_required = data.get("installation_required", False)
    glue_quantity = data.get("glue_quantity", 0)
    
    # Определяем тип заказа (готовая продукция или производство)
    db = next(get_db())
    
    try:
        # Получаем пользователя по telegram_id для получения корректного ID в базе
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        
        if not user:
            await message.answer("❌ Ошибка: пользователь не найден")
            db.close()
            return
        
        # Создаем заказ
        order = Order(
            manager_id=user.id,  # Используем ID пользователя из базы данных, а не telegram_id
            customer_phone=customer_phone,
            delivery_address=delivery_address,
            installation_required=installation_required,
            status=OrderStatus.NEW
        )
        db.add(order)
        db.flush()
        
        # Добавляем продукты в заказ через OrderItem
        for product in selected_products:
            film_code = product['film_code']
            thickness = float(product['thickness'])
            qty = product['quantity']
            
            film = db.query(Film).filter(Film.code == film_code).first()
            if not film:
                continue
            
            # Проверяем, есть ли готовая продукция
            finished_product = db.query(FinishedProduct).join(Film).filter(
                Film.code == film_code,
                FinishedProduct.thickness == thickness
            ).first()
            
            # Создаем запись OrderItem
            order_item = OrderItem(
                order_id=order.id,
                color=film_code,
                thickness=thickness,
                quantity=qty
            )
            db.add(order_item)
            
            if finished_product and finished_product.quantity >= qty:
                # Если есть готовая продукция, уменьшаем ее количество
                finished_product.quantity -= qty
                
                # Создаем операцию для готовой продукции
                operation = Operation(
                    operation_type=OperationType.READY_PRODUCT_OUT.value,
                    quantity=qty,
                    user_id=user.id  # Используем ID пользователя из базы
                )
                db.add(operation)
            else:
                # Если нет готовой продукции, создаем заказ на производство
                production_order = ProductionOrder(
                    manager_id=user.id,  # Используем ID пользователя из базы
                    panel_quantity=qty,
                    film_color=film_code,
                    panel_thickness=thickness,
                    status="new"
                )
                db.add(production_order)
        
        # Если нужны стыки, добавляем их в заказ
        if need_joints:
            if isinstance(selected_joints, list):
                # Новый формат - список объектов стыков
                for joint_data in selected_joints:
                    joint_type_val = joint_data.get('type')
                    thickness = joint_data.get('thickness')
                    color = joint_data.get('color')
                    quantity = joint_data.get('quantity')
                    
                    joint_type_text = ""
                    if joint_type_val == JointType.BUTTERFLY or joint_type_val == "butterfly":
                        joint_type_text = "Бабочка"
                    elif joint_type_val == JointType.SIMPLE or joint_type_val == "simple":
                        joint_type_text = "Простые"
                    elif joint_type_val == JointType.CLOSING or joint_type_val == "closing":
                        joint_type_text = "Замыкающие"
                    
                    joints_info += f"▪️ {joint_type_text}, {thickness} мм, {color}: {quantity} шт.\n"
            elif isinstance(selected_joints, dict):
                # Словарь (старый формат)
                for joint_key, quantity in selected_joints.items():
                    joint_type_val, thickness, color = joint_key.split('|')
                    joint_type_text = ""
                    if joint_type_val == "butterfly":
                        joint_type_text = "Бабочка"
                    elif joint_type_val == "simple":
                        joint_type_text = "Простые"
                    elif joint_type_val == "closing":
                        joint_type_text = "Замыкающие"
                    
                    joints_info += f"▪️ {joint_type_text}, {thickness} мм, {color}: {quantity} шт.\n"

        # Добавляем информацию о клее если он нужен
        glue_info = ""
        if need_glue and glue_quantity > 0:
            glue_info = f"\nКлей: {glue_quantity} шт.\n"
        
        # Сборка итогового сообщения
        installation_text = "Да" if installation_required else "Нет"
        
        # Создаем сообщение с информацией о заказе
        confirmation_message = (
            f"✅ Заказ #{order.id} успешно оформлен!\n\n"
            f"{products_info}"
            f"{joints_info}"
            f"{glue_info}"
            f"Монтаж: {installation_text}\n"
            f"Телефон: {customer_phone}\n"
            f"Адрес доставки: {delivery_address}\n\n"
            f"Статус заказа: {order.status.value}"
        )
        
        await message.answer(confirmation_message)
        
        # Возвращаемся в главное меню
        await go_back(message, state)
    
    except Exception as e:
        # В случае ошибки откатываем изменения
        db.rollback()
        logging.error(f"Ошибка при оформлении заказа: {e}")
        await message.answer(f"❌ Произошла ошибка при оформлении заказа: {e}")
    
    finally:
        # Закрываем соединение с БД
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

@router.message(SalesStates.waiting_for_order_glue_needed)
async def process_order_glue_needed(message: Message, state: FSMContext):
    """Обработка ответа о необходимости клея для стыков"""
    user_choice = message.text.strip()
    
    if user_choice == "✅ Да":
        # Проверяем наличие клея в базе данных
        db = next(get_db())
        try:
            glue = db.query(Glue).filter(Glue.quantity > 0).first()
            
            if not glue:
                await message.answer(
                    "❌ К сожалению, клей отсутствует на складе.",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[
                            [KeyboardButton(text="◀️ Назад")]
                        ],
                        resize_keyboard=True
                    )
                )
                return
            
            await message.answer(
                f"Введите количество тюбиков клея (доступно: {glue.quantity} шт.):",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text="◀️ Назад")]
                    ],
                    resize_keyboard=True
                )
            )
            await state.set_state(SalesStates.waiting_for_order_glue_quantity)
        finally:
            db.close()
    elif user_choice == "❌ Нет":
        # Клей не нужен, сохраняем нулевое количество
        await state.update_data(glue_quantity=0)
        
        # Переходим к запросу о монтаже
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                [KeyboardButton(text="◀️ Назад")]
            ],
            resize_keyboard=True
        )
        await message.answer(
            "Требуется ли монтаж?",
            reply_markup=keyboard
        )
        await state.set_state(SalesStates.waiting_for_order_installation)
    else:
        # Некорректный ввод
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )

@router.message(SalesStates.waiting_for_order_installation)
async def process_order_installation(message: Message, state: FSMContext):
    """Обработка выбора монтажа"""
    response = message.text.strip()
    
    if response == "◀️ Назад":
        # Возвращаемся к предыдущему шагу - запросу о клее
        await message.answer(
            "Вам нужен клей?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_glue_needed)
        return

    installation_required = False
    if response == "✅ Да":
        installation_required = True
    elif response == "❌ Нет":
        installation_required = False
    else:
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        return

    # Сохраняем выбор установки
    await state.update_data(installation_required=installation_required)

    # Запрашиваем контактный номер телефона
    await message.answer(
        "Введите контактный номер телефона клиента:",
        reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
    )
    await state.set_state(SalesStates.waiting_for_order_customer_phone)

@router.message(SalesStates.waiting_for_order_customer_phone)
async def process_order_customer_phone(message: Message, state: FSMContext):
    """Обработка ввода контактного номера клиента"""
    phone = message.text.strip()
    
    if message.text == "◀️ Назад":
        # Возвращаемся к предыдущему шагу - запросу о монтаже
        await message.answer(
            "Требуется ли монтаж?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_installation)
        return
    
    # Простая проверка на формат телефона
    if not phone or len(phone) < 5:  # Минимальная длина для телефона
        await message.answer(
            "❌ Пожалуйста, введите корректный номер телефона",
            reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
        )
        return
    
    # Сохраняем номер телефона
    await state.update_data(customer_phone=phone)
    
    # Запрашиваем адрес доставки
    await message.answer(
        "Введите адрес доставки (или напишите 'нет' если самовывоз):",
        reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
    )
    await state.set_state(SalesStates.waiting_for_order_delivery_address)

@router.message(SalesStates.waiting_for_order_glue_quantity)
async def process_order_glue_quantity(message: Message, state: FSMContext):
    """Обработка ввода количества клея"""
    try:
        quantity = int(message.text.strip())
        if quantity <= 0:
            await message.answer("❌ Количество должно быть больше 0")
            return
            
        # Получаем данные о выбранном клее
        data = await state.get_data()
        glue_quantity = quantity
        
        # Сохраняем количество клея
        await state.update_data(glue_quantity=glue_quantity)
        
        # Переходим к запросу о монтаже
        await message.answer(
            "Требуется ли монтаж?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_installation)
    except ValueError:
        await message.answer(
            "Пожалуйста, введите корректное число.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )

@router.message(SalesStates.waiting_for_order_glue_needed)
async def process_order_glue_needed(message: Message, state: FSMContext):
    """Обработка ответа о необходимости клея для стыков"""
    user_choice = message.text.strip()
    
    if user_choice == "✅ Да":
        # Проверяем наличие клея в базе данных
        db = next(get_db())
        try:
            glue = db.query(Glue).filter(Glue.quantity > 0).first()
            
            if not glue:
                await message.answer(
                    "❌ К сожалению, клей отсутствует на складе.",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[
                            [KeyboardButton(text="◀️ Назад")]
                        ],
                        resize_keyboard=True
                    )
                )
                return
            
            await message.answer(
                f"Введите количество тюбиков клея (доступно: {glue.quantity} шт.):",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text="◀️ Назад")]
                    ],
                    resize_keyboard=True
                )
            )
            await state.set_state(SalesStates.waiting_for_order_glue_quantity)
        finally:
            db.close()
    elif user_choice == "❌ Нет":
        # Клей не нужен, сохраняем нулевое количество
        await state.update_data(glue_quantity=0)
        
        # Переходим к запросу о монтаже
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                [KeyboardButton(text="◀️ Назад")]
            ],
            resize_keyboard=True
        )
        await message.answer(
            "Требуется ли монтаж?",
            reply_markup=keyboard
        )
        await state.set_state(SalesStates.waiting_for_order_installation)
    else:
        # Некорректный ввод
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )

@router.message(SalesStates.waiting_for_order_installation)
async def process_order_installation(message: Message, state: FSMContext):
    """Обработка выбора монтажа"""
    response = message.text.strip()
    
    if response == "◀️ Назад":
        # Возвращаемся к предыдущему шагу - запросу о клее
        await message.answer(
            "Вам нужен клей?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_glue_needed)
        return

    installation_required = False
    if response == "✅ Да":
        installation_required = True
    elif response == "❌ Нет":
        installation_required = False
    else:
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        return

    # Сохраняем выбор установки
    await state.update_data(installation_required=installation_required)

    # Запрашиваем контактный номер телефона
    await message.answer(
        "Введите контактный номер телефона клиента:",
        reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
    )
    await state.set_state(SalesStates.waiting_for_order_customer_phone)

@router.message(SalesStates.waiting_for_order_customer_phone)
async def process_order_customer_phone(message: Message, state: FSMContext):
    """Обработка ввода контактного номера клиента"""
    phone = message.text.strip()
    
    if message.text == "◀️ Назад":
        # Возвращаемся к предыдущему шагу - запросу о монтаже
        await message.answer(
            "Требуется ли монтаж?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_installation)
        return
    
    # Простая проверка на формат телефона
    if not phone or len(phone) < 5:  # Минимальная длина для телефона
        await message.answer(
            "❌ Пожалуйста, введите корректный номер телефона",
            reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
        )
        return
    
    # Сохраняем номер телефона
    await state.update_data(customer_phone=phone)
    
    # Запрашиваем адрес доставки
    await message.answer(
        "Введите адрес доставки (или напишите 'нет' если самовывоз):",
        reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
    )
    await state.set_state(SalesStates.waiting_for_order_delivery_address)

@router.message(SalesStates.waiting_for_order_delivery_address)
async def process_order_delivery_address(message: Message, state: FSMContext):
    """Обработка ввода адреса доставки"""
    address = message.text.strip()
    
    # Если адрес не указан, считаем самовывозом
    if address.lower() == "нет":
        address = "Самовывоз"
    
    # Сохраняем адрес доставки
    await state.update_data(delivery_address=address)
    
    # Показываем сводку заказа и запрашиваем подтверждение
    data = await state.get_data()
    
    # Получаем данные о выбранных продуктах
    selected_products = data.get('selected_products', [])
    
    # Получаем данные о выбранных стыках
    selected_joints = data.get('selected_joints', [])
    
    need_joints = data.get('need_joints', False)
    need_glue = data.get('need_glue', False)
    glue_quantity = data.get('glue_quantity', 0)
    installation_required = data.get('installation_required', False)
    customer_phone = data.get('customer_phone', '')
    delivery_address = data.get('delivery_address', '')
    
    # Формируем текст заказа
    order_summary = f"📝 Сводка заказа:\n\n"
    
    # Добавляем информацию о выбранных продуктах
    if selected_products:
        order_summary += f"📦 Выбранные продукты:\n"
        total_panels = 0
        for product in selected_products:
            order_summary += f"▪️ {product['film_code']} (толщина {product['thickness']} мм): {product['quantity']} шт.\n"
            total_panels += product['quantity']
        order_summary += f"Всего панелей: {total_panels} шт.\n\n"
    else:
        order_summary += "Продукты не выбраны\n\n"
    
    # Добавляем информацию о стыках
    if need_joints and selected_joints:
        order_summary += f"🔗 Стыки:\n"
        for joint in selected_joints:
            joint_type = joint.get('type', '')
            joint_type_text = ''
            if joint_type == 'butterfly' or joint_type == JointType.BUTTERFLY:
                joint_type_text = "Бабочка"
            elif joint_type == 'simple' or joint_type == JointType.SIMPLE:
                joint_type_text = "Простые"
            elif joint_type == 'closing' or joint_type == JointType.CLOSING:
                joint_type_text = "Замыкающие"
            
            thickness = joint.get('thickness', '0.5')
            order_summary += f"▪️ {joint_type_text}, {thickness} мм, {joint.get('color', '')}: {joint.get('quantity', 0)} шт.\n"
        order_summary += "\n"
    else:
        order_summary += f"🔗 Стыки: Нет\n\n"
    
    # Добавляем остальную информацию
    order_summary += f"🧴 Клей: {glue_quantity} тюбиков\n"
    order_summary += f"🔧 Монтаж: {'Требуется' if installation_required else 'Не требуется'}\n"
    order_summary += f"📞 Контактный телефон: {customer_phone}\n"
    order_summary += f"🚚 Адрес доставки: {delivery_address}\n"
    
    # Запрашиваем подтверждение
    await state.update_data(order_summary=order_summary)
    await state.set_state(MenuState.SALES_ORDER_CONFIRM)
    
    await message.answer(
        order_summary + "\n\nПожалуйста, подтвердите заказ:",
        reply_markup=get_menu_keyboard(MenuState.SALES_ORDER_CONFIRM)
    )
    await state.set_state(SalesStates.waiting_for_order_confirmation)

@router.message(SalesStates.waiting_for_order_confirmation)
async def process_order_confirmation(message: Message, state: FSMContext):
    """Обработка подтверждения заказа"""
    if message.text.lower() != "подтвердить":
        await message.answer("Заказ не подтвержден. Вы можете вернуться к оформлению заказа позже.")
        await go_back(message, state)
        return
    
    # Получаем данные из состояния
    data = await state.get_data()
    
    # Получаем выбранные продукты из состояния
    selected_products = data.get("selected_products", [])
    
    # Получаем выбранные стыки из состояния
    selected_joints = data.get('selected_joints', [])
    
    need_joints = selected_joints and len(selected_joints) > 0
    need_glue = data.get("need_glue", False)
    customer_phone = data.get("customer_phone", "")
    delivery_address = data.get("delivery_address", "")
    installation_required = data.get("installation_required", False)
    glue_quantity = data.get("glue_quantity", 0)
    
    # Определяем тип заказа (готовая продукция или производство)
    db = next(get_db())
    
    try:
        # Получаем пользователя по telegram_id для получения корректного ID в базе
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        
        if not user:
            await message.answer("❌ Ошибка: пользователь не найден")
            db.close()
            return
        
        # Создаем заказ
        order = Order(
            manager_id=user.id,  # Используем ID пользователя из базы данных, а не telegram_id
            customer_phone=customer_phone,
            delivery_address=delivery_address,
            installation_required=installation_required,
            status=OrderStatus.NEW
        )
        db.add(order)
        db.flush()
        
        # Добавляем продукты в заказ через OrderItem
        for product in selected_products:
            film_code = product['film_code']
            thickness = float(product['thickness'])
            qty = product['quantity']
            
            film = db.query(Film).filter(Film.code == film_code).first()
            if not film:
                continue
            
            # Проверяем, есть ли готовая продукция
            finished_product = db.query(FinishedProduct).join(Film).filter(
                Film.code == film_code,
                FinishedProduct.thickness == thickness
            ).first()
            
            # Создаем запись OrderItem
            order_item = OrderItem(
                order_id=order.id,
                color=film_code,
                thickness=thickness,
                quantity=qty
            )
            db.add(order_item)
            
            if finished_product and finished_product.quantity >= qty:
                # Если есть готовая продукция, уменьшаем ее количество
                finished_product.quantity -= qty
                
                # Создаем операцию для готовой продукции
                operation = Operation(
                    operation_type=OperationType.READY_PRODUCT_OUT.value,
                    quantity=qty,
                    user_id=user.id  # Используем ID пользователя из базы
                )
                db.add(operation)
            else:
                # Если нет готовой продукции, создаем заказ на производство
                production_order = ProductionOrder(
                    manager_id=user.id,  # Используем ID пользователя из базы
                    panel_quantity=qty,
                    film_color=film_code,
                    panel_thickness=thickness,
                    status="new"
                )
                db.add(production_order)
        
        # Если нужны стыки, добавляем их в заказ
        if need_joints:
            if isinstance(selected_joints, list):
                # Новый формат - список объектов стыков
                for joint_data in selected_joints:
                    joint_type_val = joint_data.get('type')
                    thickness = joint_data.get('thickness')
                    color = joint_data.get('color')
                    quantity = joint_data.get('quantity')
                    
                    joint_type_text = ""
                    if joint_type_val == JointType.BUTTERFLY or joint_type_val == "butterfly":
                        joint_type_text = "Бабочка"
                    elif joint_type_val == JointType.SIMPLE or joint_type_val == "simple":
                        joint_type_text = "Простые"
                    elif joint_type_val == JointType.CLOSING or joint_type_val == "closing":
                        joint_type_text = "Замыкающие"
                    
                    joints_info += f"▪️ {joint_type_text}, {thickness} мм, {color}: {quantity} шт.\n"
            elif isinstance(selected_joints, dict):
                # Словарь (старый формат)
                for joint_key, quantity in selected_joints.items():
                    joint_type_val, thickness, color = joint_key.split('|')
                    joint_type_text = ""
                    if joint_type_val == "butterfly":
                        joint_type_text = "Бабочка"
                    elif joint_type_val == "simple":
                        joint_type_text = "Простые"
                    elif joint_type_val == "closing":
                        joint_type_text = "Замыкающие"
                    
                    joints_info += f"▪️ {joint_type_text}, {thickness} мм, {color}: {quantity} шт.\n"

        # Добавляем информацию о клее если он нужен
        glue_info = ""
        if need_glue and glue_quantity > 0:
            glue_info = f"\nКлей: {glue_quantity} шт.\n"
        
        # Сборка итогового сообщения
        installation_text = "Да" if installation_required else "Нет"
        
        # Создаем сообщение с информацией о заказе
        confirmation_message = (
            f"✅ Заказ #{order.id} успешно оформлен!\n\n"
            f"{products_info}"
            f"{joints_info}"
            f"{glue_info}"
            f"Монтаж: {installation_text}\n"
            f"Телефон: {customer_phone}\n"
            f"Адрес доставки: {delivery_address}\n\n"
            f"Статус заказа: {order.status.value}"
        )
        
        await message.answer(confirmation_message)
        
        # Возвращаемся в главное меню
        await go_back(message, state)
    
    except Exception as e:
        # В случае ошибки откатываем изменения
        db.rollback()
        logging.error(f"Ошибка при оформлении заказа: {e}")
        await message.answer(f"❌ Произошла ошибка при оформлении заказа: {e}")
    
    finally:
        # Закрываем соединение с БД
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

@router.message(SalesStates.waiting_for_order_glue_needed)
async def process_order_glue_needed(message: Message, state: FSMContext):
    """Обработка ответа о необходимости клея для стыков"""
    user_choice = message.text.strip()
    
    if user_choice == "✅ Да":
        # Проверяем наличие клея в базе данных
        db = next(get_db())
        try:
            glue = db.query(Glue).filter(Glue.quantity > 0).first()
            
            if not glue:
                await message.answer(
                    "❌ К сожалению, клей отсутствует на складе.",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[
                            [KeyboardButton(text="◀️ Назад")]
                        ],
                        resize_keyboard=True
                    )
                )
                return
            
            await message.answer(
                f"Введите количество тюбиков клея (доступно: {glue.quantity} шт.):",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text="◀️ Назад")]
                    ],
                    resize_keyboard=True
                )
            )
            await state.set_state(SalesStates.waiting_for_order_glue_quantity)
        finally:
            db.close()
    elif user_choice == "❌ Нет":
        # Клей не нужен, сохраняем нулевое количество
        await state.update_data(glue_quantity=0)
        
        # Переходим к запросу о монтаже
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                [KeyboardButton(text="◀️ Назад")]
            ],
            resize_keyboard=True
        )
        await message.answer(
            "Требуется ли монтаж?",
            reply_markup=keyboard
        )
        await state.set_state(SalesStates.waiting_for_order_installation)
    else:
        # Некорректный ввод
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )

@router.message(SalesStates.waiting_for_order_installation)
async def process_order_installation(message: Message, state: FSMContext):
    """Обработка выбора монтажа"""
    response = message.text.strip()
    
    if response == "◀️ Назад":
        # Возвращаемся к предыдущему шагу - запросу о клее
        await message.answer(
            "Вам нужен клей?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_glue_needed)
        return

    installation_required = False
    if response == "✅ Да":
        installation_required = True
    elif response == "❌ Нет":
        installation_required = False
    else:
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        return

    # Сохраняем выбор установки
    await state.update_data(installation_required=installation_required)

    # Запрашиваем контактный номер телефона
    await message.answer(
        "Введите контактный номер телефона клиента:",
        reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
    )
    await state.set_state(SalesStates.waiting_for_order_customer_phone)

@router.message(SalesStates.waiting_for_order_customer_phone)
async def process_order_customer_phone(message: Message, state: FSMContext):
    """Обработка ввода контактного номера клиента"""
    phone = message.text.strip()
    
    if message.text == "◀️ Назад":
        # Возвращаемся к предыдущему шагу - запросу о монтаже
        await message.answer(
            "Требуется ли монтаж?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_installation)
        return
    
    # Простая проверка на формат телефона
    if not phone or len(phone) < 5:  # Минимальная длина для телефона
        await message.answer(
            "❌ Пожалуйста, введите корректный номер телефона",
            reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
        )
        return
    
    # Сохраняем номер телефона
    await state.update_data(customer_phone=phone)
    
    # Запрашиваем адрес доставки
    await message.answer(
        "Введите адрес доставки (или напишите 'нет' если самовывоз):",
        reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
    )
    await state.set_state(SalesStates.waiting_for_order_delivery_address)

@router.message(SalesStates.waiting_for_order_glue_quantity)
async def process_order_glue_quantity(message: Message, state: FSMContext):
    """Обработка ввода количества клея"""
    try:
        quantity = int(message.text.strip())
        if quantity <= 0:
            await message.answer("❌ Количество должно быть больше 0")
            return
            
        # Получаем данные о выбранном клее
        data = await state.get_data()
        glue_quantity = quantity
        
        # Сохраняем количество клея
        await state.update_data(glue_quantity=glue_quantity)
        
        # Переходим к запросу о монтаже
        await message.answer(
            "Требуется ли монтаж?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_installation)
    except ValueError:
        await message.answer(
            "Пожалуйста, введите корректное число.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )

@router.message(SalesStates.waiting_for_order_glue_needed)
async def process_order_glue_needed(message: Message, state: FSMContext):
    """Обработка ответа о необходимости клея для стыков"""
    user_choice = message.text.strip()
    
    if user_choice == "✅ Да":
        # Проверяем наличие клея в базе данных
        db = next(get_db())
        try:
            glue = db.query(Glue).filter(Glue.quantity > 0).first()
            
            if not glue:
                await message.answer(
                    "❌ К сожалению, клей отсутствует на складе.",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[
                            [KeyboardButton(text="◀️ Назад")]
                        ],
                        resize_keyboard=True
                    )
                )
                return
            
            await message.answer(
                f"Введите количество тюбиков клея (доступно: {glue.quantity} шт.):",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text="◀️ Назад")]
                    ],
                    resize_keyboard=True
                )
            )
            await state.set_state(SalesStates.waiting_for_order_glue_quantity)
        finally:
            db.close()
    elif user_choice == "❌ Нет":
        # Клей не нужен, сохраняем нулевое количество
        await state.update_data(glue_quantity=0)
        
        # Переходим к запросу о монтаже
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                [KeyboardButton(text="◀️ Назад")]
            ],
            resize_keyboard=True
        )
        await message.answer(
            "Требуется ли монтаж?",
            reply_markup=keyboard
        )
        await state.set_state(SalesStates.waiting_for_order_installation)
    else:
        # Некорректный ввод
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )

@router.message(SalesStates.waiting_for_order_installation)
async def process_order_installation(message: Message, state: FSMContext):
    """Обработка выбора монтажа"""
    response = message.text.strip()
    
    if response == "◀️ Назад":
        # Возвращаемся к предыдущему шагу - запросу о клее
        await message.answer(
            "Вам нужен клей?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_glue_needed)
        return

    installation_required = False
    if response == "✅ Да":
        installation_required = True
    elif response == "❌ Нет":
        installation_required = False
    else:
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        return

    # Сохраняем выбор установки
    await state.update_data(installation_required=installation_required)

    # Запрашиваем контактный номер телефона
    await message.answer(
        "Введите контактный номер телефона клиента:",
        reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
    )
    await state.set_state(SalesStates.waiting_for_order_customer_phone)

@router.message(SalesStates.waiting_for_order_customer_phone)
async def process_order_customer_phone(message: Message, state: FSMContext):
    """Обработка ввода контактного номера клиента"""
    phone = message.text.strip()
    
    if message.text == "◀️ Назад":
        # Возвращаемся к предыдущему шагу - запросу о монтаже
        await message.answer(
            "Требуется ли монтаж?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да")],
                    [KeyboardButton(text="❌ Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SalesStates.waiting_for_order_installation)
        return
    
    # Простая проверка на формат телефона
    if not phone or len(phone) < 5:  # Минимальная длина для телефона
        await message.answer(
            "❌ Пожалуйста, введите корректный номер телефона",
            reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
        )
        return
    
    # Сохраняем номер телефона
    await state.update_data(customer_phone=phone)
    
    # Запрашиваем адрес доставки
    await message.answer(
        "Введите адрес доставки (или напишите 'нет' если самовывоз):",
        reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
    )
    await state.set_state(SalesStates.waiting_for_order_delivery_address)

@router.message(SalesStates.waiting_for_order_delivery_address)
async def process_order_delivery_address(message: Message, state: FSMContext):
    """Обработка ввода адреса доставки"""
    address = message.text.strip()
    
    # Если адрес не указан, считаем самовывозом
    if address.lower() == "нет":
        address = "Самовывоз"
    
    # Сохраняем адрес доставки
    await state.update_data(delivery_address=address)
    
    # Показываем сводку заказа и запрашиваем подтверждение
    data = await state.get_data()
    
    # Получаем данные о выбранных продуктах
    selected_products = data.get('selected_products', [])
    
    # Получаем данные о выбранных стыках
    selected_joints = data.get('selected_joints', [])
    
    need_joints = data.get('need_joints', False)
    need_glue = data.get('need_glue', False)
    glue_quantity = data.get('glue_quantity', 0)
    installation_required = data.get('installation_required', False)
    customer_phone = data.get('customer_phone', '')
    delivery_address = data.get('delivery_address', '')
    
    # Формируем текст заказа
    order_summary = f"📝 Сводка заказа:\n\n"
    
    # Добавляем информацию о выбранных продуктах
    if selected_products:
        order_summary += f"📦 Выбранные продукты:\n"
        total_panels = 0
        for product in selected_products:
            order_summary += f"▪️ {product['film_code']} (толщина {product['thickness']} мм): {product['quantity']} шт.\n"
            total_panels += product['quantity']
        order_summary += f"Всего панелей: {total_panels} шт.\n\n"
    else:
        order_summary += "Продукты не выбраны\n\n"
    
    # Добавляем информацию о стыках
    if need_joints and selected_joints:
        order_summary += f"🔗 Стыки:\n"
        for joint in selected_joints:
            joint_type = joint.get('type', '')
            joint_type_text = ''
            if joint_type == 'butterfly' or joint_type == JointType.BUTTERFLY:
                joint_type_text = "Бабочка"
            elif joint_type == 'simple' or joint_type == JointType.SIMPLE:
                joint_type_text = "Простые"
            elif joint_type == 'closing' or joint_type == JointType.CLOSING:
                joint_type_text = "Замыкающие"
            
            thickness = joint.get('thickness', '0.5')
            order_summary += f"▪️ {joint_type_text}, {thickness} мм, {joint.get('color', '')}: {joint.get('quantity', 0)} шт.\n"
        order_summary += "\n"
    else:
        order_summary += f"🔗 Стыки: Нет\n\n"
    
    # Добавляем остальную информацию
    order_summary += f"🧴 Клей: {glue_quantity} тюбиков\n"
    order_summary += f"🔧 Монтаж: {'Требуется' if installation_required else 'Не требуется'}\n"
    order_summary += f"📞 Контактный телефон: {customer_phone}\n"
    order_summary += f"🚚 Адрес доставки: {delivery_address}\n"
    
    # Запрашиваем подтверждение
    await state.update_data(order_summary=order_summary)
    await state.set_state(MenuState.SALES_ORDER_CONFIRM)
    
    await message.answer(
        order_summary + "\n\nПожалуйста, подтвердите заказ:",
        reply_markup=get_menu_keyboard(MenuState.SALES_ORDER_CONFIRM)
    )
    await state.set_state(SalesStates.waiting_for_order_confirmation)

@router.message(SalesStates.waiting_for_order_confirmation)
async def process_order_confirmation(message: Message, state: FSMContext):
    """Обработка подтверждения заказа"""
    if message.text.lower() != "подтвердить":
        await message.answer("Заказ не подтвержден. Вы можете вернуться к оформлению заказа позже.")
        await go_back(message, state)
        return
    
    # Получаем данные из состояния
    data = await state.get_data()
    
    # Получаем выбранные продукты из состояния
    selected_products = data.get("selected_products", [])
    
    # Получаем выбранные стыки из состояния
    selected_joints = data.get('selected_joints', [])
    
    need_joints = selected_joints and len(selected_joints) > 0
    need_glue = data.get("need_glue", False)
    customer_phone = data.get("customer_phone", "")
    delivery_address = data.get("delivery_address", "")
    installation_required = data.get("installation_required", False)
    glue_quantity = data.get("glue_quantity", 0)
    
    # Определяем тип заказа (готовая продукция или производство)
    db = next(get_db())
    
    try:
        # Получаем пользователя по telegram_id для получения корректного ID в базе
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        
        if not user:
            await message.answer("❌ Ошибка: пользователь не найден")
            db.close()
            return
        
        # Создаем заказ
        order = Order(
            manager_id=user.id,  # Используем ID пользователя из базы данных, а не telegram_id
            customer_phone=customer_phone,
            delivery_address=delivery_address,
            installation_required=installation_required,
            status=OrderStatus.NEW
        )
        db.add(order)
        db.flush()
        
        # Добавляем продукты в заказ через OrderItem
        for product in selected_products:
            film_code = product['film_code']
            thickness = float(product['thickness'])
            qty = product['quantity']
            
            film = db.query(Film).filter(Film.code == film_code).first()
            if not film:
                continue
            
            # Проверяем, есть ли готовая продукция
            finished_product = db.query(FinishedProduct).join(Film).filter(
                Film.code == film_code,
                FinishedProduct.thickness == thickness
            ).first()
            
            # Создаем запись OrderItem
            order_item = OrderItem(
                order_id=order.id,
                color=film_code,
                thickness=thickness,
                quantity=qty
            )
            db.add(order_item)
            
            if finished_product and finished_product.quantity >= qty:
                # Если есть готовая продукция, уменьшаем ее количество
                finished_product.quantity -= qty
                
                # Создаем операцию для готовой продукции
                operation = Operation(
                    operation_type=OperationType.READY_PRODUCT_OUT.value,
                    quantity=qty,
                    user_id=user.id  # Используем ID пользователя из базы
                )
                db.add(operation)
            else:
                # Если нет готовой продукции, создаем заказ на производство
                production_order = ProductionOrder(
                    manager_id=user.id,  # Используем ID пользователя из базы
                    panel_quantity=qty,
                    film_color=film_code,
                    panel_thickness=thickness,
                    status="new"
                )
                db.add(production_order)
        
        # Если нужны стыки, добавляем их в заказ
        if need_joints:
            if isinstance(selected_joints, list):
                # Новый формат - список объектов стыков
                for joint_data in selected_joints:
                    joint_type_val = joint_data.get('type')
                    thickness = joint_data.get('thickness')
                    color = joint_data.get('color')
                    quantity = joint_data.get('quantity')
                    
                    joint_type_text = ""
                    if joint_type_val == JointType.BUTTERFLY or joint_type_val == "butterfly":
                        joint_type_text = "Бабочка"
                    elif joint_type_val == JointType.SIMPLE or joint_type_val == "simple":
                        joint_type_text = "Простые"
                    elif joint_type_val == JointType.CLOSING or joint_type_val == "closing":
                        joint_type_text = "Замыкающие"
                    
                    joints_info += f"▪️ {joint_type_text}, {thickness} мм, {color}: {quantity} шт.\n"
            elif isinstance(selected_joints, dict):
                # Словарь (старый формат)
                for joint_key, quantity in selected_joints.items():
                    joint_type_val, thickness, color = joint_key.split('|')
                    joint_type_text = ""
                    if joint_type_val == "butterfly":
                        joint_type_text = "Бабочка"
                    elif joint_type_val == "simple":
                        joint_type_text = "Простые"
                    elif joint_type_val == "closing":
                        joint_type_text = "Замыкающие"
                    
                    joints_info += f"▪️ {joint_type_text}, {thickness} мм, {color}: {quantity} шт.\n"

        # Добавляем информацию о клее если он нужен
        glue_info = ""
        if need_glue and glue_quantity > 0:
            glue_info = f"\nКлей: {glue_quantity} шт.\n"
        
        # Сборка итогового сообщения
        installation_text = "Да" if installation_required else "Нет"
        
        # Создаем сообщение с информацией о заказе
        confirmation_message = (
            f"✅ Заказ #{order.id} успешно оформлен!\n\n"
            f"{products_info}"
            f"{joints_info}"
            f"{glue_info}"
            f"Монтаж: {installation_text}\n"
            f"Телефон: {customer_phone}\n"
            f"Адрес доставки: {delivery_address}\n\n"
            f"Статус заказа: {order.status.value}"
        )
        
        await message.answer(confirmation_message)
        
        # Возвращаемся в главное меню
        await go_back(message, state)
    
    except Exception as e:
        # В случае ошибки откатываем изменения
        db.rollback()
        logging.error(f"Ошибка при оформлении заказа: {e}")
        await message.answer(f"❌ Произошла ошибка при оформлении заказа: {e}")
    
    finally:
        # Закрываем соединение с БД
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

@router.message(SalesStates.waiting_for_order_glue_needed)
async def process_order_glue_needed(message: Message, state: FSMContext):
    """Обработка ответа о необходимости клея для стыков"""
    user_choice = message.text.strip()
    
    if user_choice == "✅ Да":
        # Проверяем наличие клея в базе данных
        db = next(get_db())
        try:
            glue = db.query(Glue).filter(Glue.quantity > 0).first()
            
            if not glue:
                await message.answer(
                    "❌ К сожалению, клей отсутствует на складе.",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[
                            [KeyboardButton(text="◀️ Назад")]
                        ],
                        resize_keyboard=True
                    )
                )
                return
            
            await message.answer(
                f"Введите количество тюбиков клея (доступно: {glue.quantity} шт.):",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text="◀️ Назад")]
                    ],
                    resize_keyboard=True
                )
            )
            await state.set_state(SalesStates.waiting_for_order_glue_quantity)
        finally:
            db.close()
    elif user_choice == "❌ Нет":
        # Клей не нужен, сохраняем нулевое количество
        await state.update_data(glue_quantity=0)
        
        # Переходим к запросу о монтаже
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                [KeyboardButton(text="◀️ Назад")]
            ],
            resize_keyboard=True
        )
        await message.answer(
            "Требуется ли монтаж?",
            reply_markup=keyboard
        )
        await state.set_state(SalesStates.waiting_for_order_installation)
    else:
        # Некорректный ввод
        await message.answer(
        await state.update_