from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from models import User, UserRole, Film, Panel, Joint, Glue, FinishedProduct, Operation, JointType, Order, ProductionOrder, OrderStatus, OrderJoint, OrderGlue, OperationType, OrderItem
from database import get_db
import json
import logging
from navigation import MenuState, get_menu_keyboard, go_back
import re
from states import SalesStates
from typing import Optional, Dict, List, Any, Union
from sqlalchemy import select

router = Router()

def get_joint_type_keyboard():
    """Возвращает клавиатуру с типами стыков"""
    db = next(get_db())
    try:
        # Группируем стыки по типу и проверяем наличие
        butterfly_joints = db.query(Joint).filter(Joint.type == JointType.BUTTERFLY, Joint.quantity > 0).first()
        simple_joints = db.query(Joint).filter(Joint.type == JointType.SIMPLE, Joint.quantity > 0).first()
        closing_joints = db.query(Joint).filter(Joint.type == JointType.CLOSING, Joint.quantity > 0).first()
        
        keyboard = []
        if butterfly_joints:
            keyboard.append([KeyboardButton(text="🦋 Бабочка")])
        if simple_joints:
            keyboard.append([KeyboardButton(text="🔄 Простые")])
        if closing_joints:
            keyboard.append([KeyboardButton(text="🔒 Замыкающие")])
        
        keyboard.append([KeyboardButton(text="◀️ Назад")])
        
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    finally:
        db.close()

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
    
    # Получаем флаг админ-контекста
    state_data = await state.get_data()
    is_admin_context = state_data.get("is_admin_context", False)
    
    # Очищаем предыдущие данные состояния
    await state.clear()
    
    # Устанавливаем флаг админ-контекста снова
    if is_admin_context:
        await state.update_data(is_admin_context=True)
    
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
        
        # Устанавливаем начальное состояние для сбора продуктов
        await state.update_data(selected_products=[])
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
        # Вместо вызова handle_create_order, напрямую показываем список толщин
        db = next(get_db())
        try:
            # Получаем список всех толщин панелей, для которых есть готовая продукция
            thicknesses = db.query(FinishedProduct.thickness).distinct().all()
            available_thicknesses = [str(thickness[0]) for thickness in thicknesses]
            
            # Если нет доступных толщин, сообщаем об этом
            if not available_thicknesses:
                await message.answer(
                    "На складе нет готовой продукции. Пожалуйста, обратитесь к производству."
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
            
            # Устанавливаем состояние для выбора толщины, но НЕ очищаем selected_products
            await state.set_state(SalesStates.product_thickness)
        finally:
            db.close()
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

@router.message(SalesStates.waiting_for_order_customer_phone)
async def process_order_customer_phone(message: Message, state: FSMContext):
    """Обработка ввода контактного номера клиента"""
    phone = message.text.strip()
    
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
            if joint_type == 'butterfly':
                joint_type_text = "Бабочка"
            elif joint_type == 'simple':
                joint_type_text = "Простые"
            elif joint_type == 'closing':
                joint_type_text = "Замыкающие"
            
            order_summary += f"▪️ Тип: {joint_type_text}, {joint.get('thickness', '')} мм, {joint.get('color', '')}: {joint.get('quantity', 0)} шт.\n"
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
    response = message.text.strip()
    
    if response == "✅ Подтвердить":
        # Получаем все данные состояния
        data = await state.get_data()
        
        # Получаем выбранные продукты из состояния
        selected_products = data.get("selected_products", [])
        
        # Получаем выбранные стыки из состояния
        selected_joints = data.get("selected_joints", [])
        
        need_joints = len(selected_joints) > 0
        need_glue = data.get("need_glue", False)
        customer_phone = data.get("customer_phone", "")
        delivery_address = data.get("delivery_address", "")
        installation_required = data.get("installation_required", False)
        glue_quantity = data.get("glue_quantity", 0)
        
        # Debug logging for glue
        logging.info(f"DEBUG: Order confirmation - need_glue: {need_glue}, glue_quantity: {glue_quantity}")
        
        # Получаем telegram_id пользователя
        telegram_id = message.from_user.id
        
        # Начинаем транзакцию
        db = next(get_db())
        try:
            # Находим пользователя по telegram_id
            user = db.query(User).filter(User.telegram_id == telegram_id).first()
            
            # Если пользователь не найден, прерываем операцию
            if not user:
                logging.error(f"User with telegram_id={telegram_id} not found in database during order confirmation.")
                await message.answer(
                    "❌ Ошибка: Ваш пользователь не найден в системе. Пожалуйста, выполните команду /start и попробуйте снова.",
                    reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
                )
                await state.set_state(MenuState.SALES_MAIN) # Сбрасываем состояние
                return
            
            # Используем user.id для создания заказа
            manager_db_id = user.id
            
            # Создаем заказ
            order = Order(
                manager_id=manager_db_id, # Используем ID пользователя из базы
                customer_phone=customer_phone,
                delivery_address=delivery_address,
                installation_required=installation_required,
                status=OrderStatus.NEW
            )
            db.add(order)
            db.flush()
            
            # Добавляем продукты в заказ
            total_panels = 0
            for product in selected_products:
                film_code = product['film_code']
                thickness = float(product['thickness'])
                qty = product['quantity']
                total_panels += qty
                
                # Если есть хотя бы один продукт, установим толщину панели в заказе
                order.panel_thickness = thickness
                
                film = db.query(Film).filter(Film.code == film_code).first()
                if not film:
                    continue
                
                # Проверяем, есть ли готовая продукция
                finished_product = db.query(FinishedProduct).join(Film).filter(
                    Film.code == film_code,
                    FinishedProduct.thickness == thickness
                ).first()
                
                if finished_product and finished_product.quantity >= qty:
                    # Если есть готовая продукция, используем её
                    order_item = OrderItem(
                        order_id=order.id,
                        quantity=qty,
                        color=product['film_code'],
                        thickness=product['thickness']
                    )
                    
                    # Уменьшаем количество готовой продукции на складе
                    # finished_product.quantity -= qty
                    
                    # Создаем операцию для готовой продукции
                    # operation = Operation(
                    #     operation_type=OperationType.READY_PRODUCT_OUT.value,
                    #     quantity=qty,
                    #     user_id=manager_db_id, # Используем ID из базы
                    #     details=json.dumps({"film_id": film.id, "film_code": film_code, "thickness": thickness})
                    # )
                    # db.add(operation)
                    
                    db.add(order_item)
                else:
                    # Если нет готовой продукции, создаем заказ на производство
                    order_item = OrderItem(
                        order_id=order.id,
                        quantity=qty,
                        color=product['film_code'],
                        thickness=product['thickness']
                    )
                    
                    # Создаем производственный заказ
                    production_order = ProductionOrder(
                        manager_id=manager_db_id,
                        film_id=film.id,
                        panel_thickness=thickness,
                        panel_quantity=qty,
                        status="new"
                    )
                    
                    db.add(production_order)
                
                db.add(order_item)
            
            # Обновляем общее количество панелей в заказе
            
            # Если нужны стыки, добавляем их в заказ
            total_joints = 0
            if need_joints and selected_joints:
                for joint in selected_joints:
                    joint_type_val = joint.get('type')
                    thickness = float(joint.get('thickness'))
                    color = joint.get('color')
                    joint_qty = joint.get('quantity')
                    
                    # Преобразуем строковое значение типа стыка обратно в enum
                    joint_type_enum = None
                    if joint_type_val == "butterfly":
                        joint_type_enum = JointType.BUTTERFLY
                    elif joint_type_val == "simple":
                        joint_type_enum = JointType.SIMPLE
                    elif joint_type_val == "closing":
                        joint_type_enum = JointType.CLOSING
                        
                    if not joint_type_enum:
                        continue
                        
                    # Находим соответствующий стык в базе
                    joint = db.query(Joint).filter(
                        Joint.type == joint_type_enum,
                        Joint.thickness == thickness,
                        Joint.color == color
                    ).first()
                    
                    if joint and joint.quantity >= joint_qty:
                        # Создаем связь между заказом и стыком
                        order_joint = OrderJoint(
                            order_id=order.id,
                            joint_type=joint_type_enum,
                            joint_color=color,
                            quantity=joint_qty,
                            joint_thickness=thickness  # Добавляем параметр joint_thickness
                        )
                        db.add(order_joint)
                        
                        # Уменьшаем количество стыков на складе
                        # joint.quantity -= joint_qty
                        
                        # Создаем операцию
                        # operation = Operation(
                        #     operation_type=OperationType.JOINT_OUT.value,
                        #     quantity=joint_qty,
                        #     user_id=manager_db_id
                        # )
                        # db.add(operation)
            
            # Обновляем общее количество стыков в заказе
            order.joint_quantity = total_joints
            # Если указано количество клея, добавляем в заказ
            glue_quantity = data.get('glue_quantity', 0)
            logging.info(f"DEBUG: Order confirmation - need_glue: {data.get('need_glue', False)}, glue_quantity: {glue_quantity}")
            
            if glue_quantity > 0:  # Было: if need_glue and glue_quantity > 0:
                # Получаем объект клея
                glue = db.query(Glue).first()
                logging.info(f"DEBUG: Checking for glue - found: {glue is not None}, glue_quantity needed: {glue_quantity}")
                
                if glue and glue.quantity >= glue_quantity:
                    # Связываем заказ с клеем
                    order_glue = OrderGlue(
                        order_id=order.id,
                        quantity=glue_quantity
                    )
                    db.add(order_glue)
                    logging.info(f"DEBUG: Created OrderGlue with quantity {glue_quantity} for order {order.id}")
                    
                    # Уменьшаем количество клея на складе
                    # glue.quantity -= glue_quantity
                    
                    # Создаем операцию
                    # operation = Operation(
                    #     operation_type=OperationType.GLUE_OUT.value,
                    #     quantity=glue_quantity,
                    #     user_id=manager_db_id
                    # )
                    # db.add(operation)
                else:
                    logging.warning(f"DEBUG: Not enough glue - required: {glue_quantity}, available: {glue.quantity if glue else 0}")
            
            # Сохраняем изменения в базе данных
            db.commit()
            
            # Формируем информацию о продуктах в заказе
            products_info = "Продукция:\n"
            for product in selected_products:
                products_info += f"▪️ {product['film_code']} (толщина {product['thickness']} мм): {product['quantity']} шт.\n"
            
            # Формируем информацию о стыках в заказе
            joints_info = ""
            if need_joints and selected_joints:
                joints_info = "\nСтыки:\n"
                for joint in selected_joints:
                    joint_type_val = joint.get('type')
                    thickness = joint.get('thickness')
                    color = joint.get('color')
                    quantity = joint.get('quantity')
                    
                    joint_type_text = ""
                    if joint_type_val == "butterfly":
                        joint_type_text = "Бабочка"
                    elif joint_type_val == "simple":
                        joint_type_text = "Простые"
                    elif joint_type_val == "closing":
                        joint_type_text = "Замыкающие"
                    
                    joints_info += f"▪️ Тип: {joint_type_text}, {thickness} мм, {color}: {quantity} шт.\n"
            
            # Формируем итоговое сообщение
            confirmation_message = f"✅ Заказ #{order.id} успешно создан!\n\n"
            confirmation_message += products_info
            
            if joints_info:
                confirmation_message += joints_info
                
            confirmation_message += f"\n🧴 Клей: {glue_quantity} тюбиков"
            confirmation_message += f"\n🔧 Монтаж: {'Требуется' if installation_required else 'Не требуется'}"
            confirmation_message += f"\n📞 Контактный телефон: {customer_phone}"
            confirmation_message += f"\n🚚 Адрес доставки: {delivery_address}"
            
            # Сбрасываем состояние и отправляем подтверждение
            await state.set_state(MenuState.SALES_MAIN)
            await message.answer(
                confirmation_message,
                reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
            )
        except Exception as e:
            db.rollback()
            logging.error(f"Error creating order: {e}")
            await message.answer(
                f"❌ Произошла ошибка при создании заказа: {e}",
                reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
            )
        finally:
            db.close()
    elif response == "❌ Отменить":
        # Отменяем заказ
        await state.set_state(MenuState.SALES_MAIN)
        await message.answer(
            "Заказ отменен.",
            reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
        )
    else:
        await message.answer(
            "Пожалуйста, выберите один из вариантов: ✅ Подтвердить или ❌ Отменить",
            reply_markup=get_menu_keyboard(MenuState.SALES_ORDER_CONFIRM)
        )

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
        logging.info(f"DEBUG: User {message.from_user.id} requested glue (need_glue=True)")
        
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
        logging.info(f"DEBUG: User {message.from_user.id} did not request glue (need_glue=False, glue_quantity=0)")
        
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
        logging.info(f"DEBUG: Saved glue_quantity={glue_quantity} to state for user {message.from_user.id}")
        
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
    else:
        # Некорректный ввод
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")]
                ],
                resize_keyboard=True
            )
        )

@router.message(SalesStates.waiting_for_order_installation)
async def process_order_installation(message: Message, state: FSMContext):
    """Обработка ответа о необходимости монтажа"""
    user_choice = message.text.strip()
    
    if user_choice == "✅ Да":
        # Монтаж требуется
        await state.update_data(installation_required=True)
        
        # Переходим к запросу номера телефона
        await message.answer(
            "Введите контактный номер телефона клиента:",
            reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
        )
        await state.set_state(SalesStates.waiting_for_order_customer_phone)
    elif user_choice == "❌ Нет":
        # Монтаж не требуется
        await state.update_data(installation_required=False)
        
        # Переходим к запросу номера телефона (монтаж не нужен, но контакт клиента все равно нужен)
        await message.answer(
            "Введите контактный номер телефона клиента:",
            reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
        )
        await state.set_state(SalesStates.waiting_for_order_customer_phone)
    else:
        # Некорректный ввод
        await message.answer(
            "Пожалуйста, выберите один из предложенных вариантов.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")]
                ],
                resize_keyboard=True
            )
        )

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
    joint_type_str = ""
    for key in joint_type_map:
        if key.lower() in user_choice.lower():
            joint_type = joint_type_map[key]
            if "бабочка" in key.lower():
                joint_type_str = "butterfly"
            elif "простые" in key.lower():
                joint_type_str = "simple"
            elif "замыкающие" in key.lower():
                joint_type_str = "closing"
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
    
    # Сохраняем выбранный тип стыка и его строковое представление
    await state.update_data(joint_type=joint_type, joint_type_str=joint_type_str)
    
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
    """Обработка выбора толщины стыка"""
    user_choice = message.text.strip()
    
    if user_choice == "◀️ Назад":
        # Возвращаемся к выбору типа стыка
        db = next(get_db())
        try:
            # Группируем стыки по типу и показываем количество
            butterfly_joints = db.query(Joint).filter(Joint.type == JointType.BUTTERFLY, Joint.quantity > 0).all()
            simple_joints = db.query(Joint).filter(Joint.type == JointType.SIMPLE, Joint.quantity > 0).all()
            closing_joints = db.query(Joint).filter(Joint.type == JointType.CLOSING, Joint.quantity > 0).all()
            
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
                "Выберите тип стыка:",
                reply_markup=keyboard
            )
        finally:
            db.close()
        
        await state.set_state(SalesStates.waiting_for_order_joint_type)
        return
    
    # Проверяем корректность введенной толщины
    valid_thicknesses = ["0.5", "0.8"]
    if user_choice not in valid_thicknesses:
        await message.answer(
            "Пожалуйста, выберите толщину из предложенных вариантов: 0.5 или 0.8 мм.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="0.5"), KeyboardButton(text="0.8")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        return
    
    # Сохраняем выбранную толщину
    thickness = float(user_choice)
    await state.update_data(joint_thickness=thickness)
    
    # Получаем выбранный тип стыка
    data = await state.get_data()
    joint_type = data.get('joint_type')
    
    # Запрашиваем цвет стыка
    db = next(get_db())
    try:
        # Получаем доступные цвета для выбранного типа и толщины
        available_joints = db.query(Joint).filter(
            Joint.type == joint_type,
            Joint.thickness == thickness,
            Joint.quantity > 0
        ).all()
        
        if not available_joints:
            await message.answer(
                f"К сожалению, нет доступных стыков типа {joint_type} с толщиной {thickness} мм.",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text="0.5"), KeyboardButton(text="0.8")],
                        [KeyboardButton(text="◀️ Назад")]
                    ],
                    resize_keyboard=True
                )
            )
            return
        
        # Создаем клавиатуру с доступными цветами
        keyboard = []
        row = []
        for joint in available_joints:
            if len(row) < 3:  # Максимум 3 кнопки в ряду
                row.append(KeyboardButton(text=f"{joint.color} ({joint.quantity} шт.)"))
            else:
                keyboard.append(row)
                row = [KeyboardButton(text=f"{joint.color} ({joint.quantity} шт.)")]
        
        if row:  # Добавляем оставшиеся кнопки
            keyboard.append(row)
        
        # Добавляем кнопку "Назад"
        keyboard.append([KeyboardButton(text="◀️ Назад")])
        
        await message.answer(
            f"Выберите цвет стыка:",
            reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
        )
        await state.set_state(SalesStates.waiting_for_order_joint_color)
    finally:
        db.close()

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
    user_choice = message.text.strip()
    
    if user_choice == "◀️ Назад":
        # Возвращаемся к выбору цвета стыка
        data = await state.get_data()
        joint_type = data.get('joint_type')
        thickness = data.get('joint_thickness')
        
        db = next(get_db())
        try:
            available_joints = db.query(Joint).filter(
                Joint.type == joint_type,
                Joint.thickness == thickness,
                Joint.quantity > 0
            ).all()
            
            if not available_joints:
                await message.answer(
                    "Нет доступных стыков данного типа и толщины.",
                    reply_markup=get_joint_type_keyboard()
                )
                await state.set_state(SalesStates.waiting_for_order_joint_type)
                return
            
            # Создаем клавиатуру с доступными цветами
            keyboard = []
            row = []
            for joint in available_joints:
                if len(row) < 3:  # Максимум 3 кнопки в ряду
                    row.append(KeyboardButton(text=f"{joint.color} ({joint.quantity} шт.)"))
                else:
                    keyboard.append(row)
                    row = [KeyboardButton(text=f"{joint.color} ({joint.quantity} шт.)")]
            
            if row:  # Добавляем оставшиеся кнопки
                keyboard.append(row)
            
            # Добавляем кнопку "Назад"
            keyboard.append([KeyboardButton(text="◀️ Назад")])
            
            await message.answer(
                f"Выберите цвет стыка ({joint_type}, {thickness} мм):",
                reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
            )
            await state.set_state(SalesStates.waiting_for_order_joint_color)
        finally:
            db.close()
        return
    
    try:
        quantity = int(user_choice)
        if quantity <= 0:
            await message.answer("Количество должно быть положительным числом.")
            return
        
        # Проверяем доступное количество стыков
        data = await state.get_data()
        joint_type = data.get('joint_type')
        joint_type_str = data.get('joint_type_str', '')  # Получаем строковое представление
        thickness = data.get('joint_thickness')
        color = data.get('joint_color')
        
        db = next(get_db())
        try:
            # Находим стык в базе
            joint = db.query(Joint).filter(
                Joint.type == joint_type,
                Joint.thickness == thickness,
                Joint.color == color
            ).first()
            
            if not joint or joint.quantity < quantity:
                max_quantity = joint.quantity if joint else 0
                await message.answer(
                    f"К сожалению, недостаточно стыков. Доступно: {max_quantity} шт.",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[[KeyboardButton(text="◀️ Назад")]],
                        resize_keyboard=True
                    )
                )
                return
            
            # Сохраняем выбранные стыки в состоянии
            selected_joints = data.get('selected_joints', [])
            
            joint_data = {
                "type": joint_type_str,  # Используем строковое представление типа стыка
                "color": color,
                "thickness": thickness,
                "quantity": quantity
            }
            
            # Сохраняем последний выбранный стык для возможности вернуться назад
            await state.update_data(last_joint=joint_data)
            
            # Добавляем новый стык
            selected_joints.append(joint_data)
            await state.update_data(selected_joints=selected_joints)
            
            # Формируем список выбранных стыков для отображения
            joints_text = "\n".join([
                f"• {j['type']}, {j['thickness']} мм, {j['color']}, {j['quantity']} шт."
                for j in selected_joints
            ])
            
            # Спрашиваем, нужны ли еще стыки
            await message.answer(
                f"✅ Стык добавлен в заказ\n\nВыбранные стыки:\n{joints_text}\n\nДобавить еще стыки?",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                        [KeyboardButton(text="◀️ Назад")]
                    ],
                    resize_keyboard=True
                )
            )
            await state.set_state(SalesStates.waiting_for_order_more_joints)
        finally:
            db.close()
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число.")

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

@router.message(F.text == "📝 Заказать производство")
async def handle_production_order(message: Message, state: FSMContext):
    if not await check_sales_access(message):
        return
    
    # Получаем флаг админ-контекста
    state_data = await state.get_data()
    is_admin_context = state_data.get("is_admin_context", False)
    
    await state.set_state(MenuState.SALES_ORDER)
    db = next(get_db())
    try:
        films = db.query(Film).all()
        if not films:
            await message.answer(
                "В базе нет пленки.",
                reply_markup=get_menu_keyboard(MenuState.SALES_MAIN, is_admin_context=is_admin_context)
            )
            return
        
        films_info = [f"- {film.code}" for film in films]
        await message.answer(
            "Введите код пленки.\n\nДоступные варианты:\n" + "\n".join(films_info),
            reply_markup=get_menu_keyboard(MenuState.SALES_ORDER, is_admin_context=is_admin_context)
        )
        await state.set_state(SalesStates.waiting_for_film_color)
    finally:
        db.close()

@router.message(F.text == "📦 Заказать на склад")
async def handle_warehouse_order(message: Message, state: FSMContext):
    if not await check_sales_access(message):
        return
    
    await state.set_state(MenuState.SALES_ORDER)
    db = next(get_db())
    try:
        # Получаем список готовой продукции
        finished_products = db.query(FinishedProduct).join(Film).all()
        if not finished_products:
            await message.answer(
                "На складе нет готовой продукции.",
                reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
            )
            return
        
        # Формируем сообщение о доступной продукции
        products_info = []
        for product in finished_products:
            products_info.append(
                f"• Панели с пленкой {product.film.code} (толщина: {product.thickness} мм): {product.quantity} шт."
            )
        
        if not products_info:
            await message.answer(
                "На складе нет готовой продукции.",
                reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
            )
            return
        
        await message.answer(
            "Введите код пленки.\n\nДоступные варианты:\n" + "\n".join(products_info),
            reply_markup=get_menu_keyboard(MenuState.SALES_ORDER)
        )
        await state.set_state(SalesStates.waiting_for_film_code)
    finally:
        db.close()

@router.message(F.text == "📦 Количество готовой продукции")
async def handle_stock(message: Message, state: FSMContext):
    if not await check_sales_access(message):
        return
    
    state_data = await state.get_data()
    is_admin_context = state_data.get("is_admin_context", False)
    
    await state.set_state(MenuState.SALES_STOCK)
    db = next(get_db())
    try:
        # Получаем список готовой продукции
        finished_products = db.query(FinishedProduct).join(Film).all()
        if not finished_products:
            await message.answer(
                "На складе нет готовой продукции.",
                reply_markup=get_menu_keyboard(MenuState.SALES_MAIN, is_admin_context)
            )
            return
        
        # Формируем список доступной продукции
        response = "📦 Готовая продукция на складе:\n\n"
        for product in finished_products:
            if product.quantity > 0:
                response += f"- {product.film.code}: {product.quantity} шт.\n"
        
        await message.answer(
            response,
            reply_markup=get_menu_keyboard(MenuState.SALES_STOCK, is_admin_context)
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

@router.message(SalesStates.waiting_for_film_color)
async def process_film_color(message: Message, state: FSMContext):
    """Обработка ввода кода пленки"""
    db = next(get_db())
    try:
        film = db.query(Film).filter(Film.code == message.text.strip()).first()
        if not film:
            await message.answer("❌ Пленка с таким кодом не найдена. Пожалуйста, выберите из списка:")
            return
            
        # Сохраняем код пленки
        await state.update_data(film_color=film.code)
        
        # Запрашиваем количество панелей
        await message.answer("Введите количество панелей:")
        await state.set_state(SalesStates.waiting_for_panel_quantity)
    finally:
        db.close()

@router.message(SalesStates.waiting_for_panel_quantity)
async def process_panel_quantity(message: Message, state: FSMContext):
    """Обработка ввода количества панелей и создание заказа"""
    try:
        quantity = int(message.text.strip())
        if quantity <= 0:
            await message.answer("❌ Количество должно быть больше 0")
            return
            
        # Получаем сохраненные данные
        data = await state.get_data()
        
        db = next(get_db())
        try:
            # Получаем пользователя
            user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
            if not user:
                await message.answer("❌ Ошибка: пользователь не найден")
                return
                
            # Создаем заказ на производство
            production_order = ProductionOrder(
                manager_id=user.id,
                film_color=data['film_color'],
                panel_quantity=quantity,
                status="new"
            )
            
            db.add(production_order)
            db.commit()
            
            # Формируем сообщение о созданном заказе
            order_text = (
                f"✅ Заказ на производство #{production_order.id} успешно создан!\n\n"
                f"Пленка: {production_order.film_color}\n"
                f"Количество панелей: {production_order.panel_quantity}"
            )
            
            await message.answer(order_text)
            
            # Возвращаем клавиатуру менеджера
            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="📝 Заказать производство")],
                    [KeyboardButton(text="📦 Заказать на склад")],
                    [KeyboardButton(text="📦 Количество готовой продукции")]
                ],
                resize_keyboard=True
            )
            await message.answer("Выберите действие:", reply_markup=keyboard)
            
        except Exception as e:
            await message.answer(f"❌ Ошибка при создании заказа: {str(e)}")
        finally:
            db.close()
            await state.clear()
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число")

@router.message(SalesStates.waiting_for_film_code)
async def process_film_code(message: Message, state: FSMContext):
    """Обработка ввода кода пленки"""
    db = next(get_db())
    try:
        film = db.query(Film).filter(Film.code == message.text.strip()).first()
        if not film:
            await message.answer("❌ Пленка с таким кодом не найдена. Пожалуйста, выберите из списка:")
            return
            
        # Сохраняем код пленки
        await state.update_data(film_code=film.code)
        
        # Запрашиваем количество панелей
        await message.answer("Введите количество панелей:")
        await state.set_state(SalesStates.waiting_for_panels_count)
    finally:
        db.close()

@router.message(SalesStates.waiting_for_panels_count)
async def process_panels_count(message: Message, state: FSMContext):
    """Обработка ввода количества панелей и создание заказа"""
    try:
        quantity = int(message.text.strip())
        if quantity <= 0:
            await message.answer("❌ Количество должно быть больше 0")
            return
            
        # Получаем сохраненные данные
        data = await state.get_data()
        
        db = next(get_db())
        try:
            # Получаем пользователя
            user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
            if not user:
                await message.answer("❌ Ошибка: пользователь не найден")
                return
                
            # Создаем заказ на производство
            production_order = ProductionOrder(
                manager_id=user.id,
                film_color=data['film_code'],
                panel_quantity=quantity,
                status="new"
            )
            
            db.add(production_order)
            db.commit()
            
            # Формируем сообщение о созданном заказе
            order_text = (
                f"✅ Заказ на производство #{production_order.id} успешно создан!\n\n"
                f"Пленка: {production_order.film_color}\n"
                f"Количество панелей: {production_order.panel_quantity}"
            )
            
            await message.answer(order_text)
            
            # Возвращаем клавиатуру менеджера
            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="📝 Заказать производство")],
                    [KeyboardButton(text="📦 Заказать на склад")],
                    [KeyboardButton(text="📦 Количество готовой продукции")]
                ],
                resize_keyboard=True
            )
            await message.answer("Выберите действие:", reply_markup=keyboard)
            
        except Exception as e:
            await message.answer(f"❌ Ошибка при создании заказа: {str(e)}")
        finally:
            db.close()
            await state.clear()
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число")

@router.message(SalesStates.waiting_for_joint_type)
async def process_joint_type(message: Message, state: FSMContext):
    """Обработка выбора типа стыка"""
    db = next(get_db())
    try:
        joint_type_str = message.text.strip().lower()
        joint_type_map = {
            "простой": JointType.SIMPLE,
            "бабочка": JointType.BUTTERFLY,
            "замыкающий": JointType.CLOSING
        }
        if joint_type_str not in joint_type_map:
            await message.answer("Неверный тип стыка. Допустимые значения: простой, бабочка, замыкающий")
            return
        
        await state.update_data(joint_type=joint_type_map[joint_type_str])
        await message.answer("Введите цвет стыка:")
        await state.set_state(SalesStates.waiting_for_joint_color)
    except ValueError:
        await message.answer("❌ Пожалуйста, выберите тип стыка из списка")

@router.message(SalesStates.waiting_for_joint_color)
async def process_joint_color(message: Message, state: FSMContext):
    """Обработка ввода цвета стыка"""
    db = next(get_db())
    try:
        joint_color = message.text.strip()
        await state.update_data(joint_color=joint_color)
        await message.answer("Введите количество стыков:")
        await state.set_state(SalesStates.waiting_for_joint_quantity)
    except ValueError:
        await message.answer("❌ Пожалуйста, введите цвет стыка")

@router.message(SalesStates.waiting_for_joint_quantity)
async def process_order_joint_quantity(message: Message, state: FSMContext):
    """Обработка количества стыков"""
    user_choice = message.text.strip()
    
    if user_choice == "◀️ Назад":
        # Возвращаемся к выбору цвета стыка
        data = await state.get_data()
        joint_type = data.get('joint_type')
        thickness = data.get('joint_thickness')
        
        db = next(get_db())
        try:
            available_joints = db.query(Joint).filter(
                Joint.type == joint_type,
                Joint.thickness == thickness,
                Joint.quantity > 0
            ).all()
            
            if not available_joints:
                await message.answer(
                    "Нет доступных стыков данного типа и толщины.",
                    reply_markup=get_joint_type_keyboard()
                )
                await state.set_state(SalesStates.waiting_for_order_joint_type)
                return
            
            # Создаем клавиатуру с доступными цветами
            keyboard = []
            row = []
            for joint in available_joints:
                if len(row) < 3:  # Максимум 3 кнопки в ряду
                    row.append(KeyboardButton(text=f"{joint.color} ({joint.quantity} шт.)"))
                else:
                    keyboard.append(row)
                    row = [KeyboardButton(text=f"{joint.color} ({joint.quantity} шт.)")]
            
            if row:  # Добавляем оставшиеся кнопки
                keyboard.append(row)
            
            # Добавляем кнопку "Назад"
            keyboard.append([KeyboardButton(text="◀️ Назад")])
            
            await message.answer(
                f"Выберите цвет стыка ({joint_type}, {thickness} мм):",
                reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
            )
            await state.set_state(SalesStates.waiting_for_order_joint_color)
        finally:
            db.close()
        return
    
    try:
        quantity = int(user_choice)
        if quantity <= 0:
            await message.answer("Количество должно быть положительным числом.")
            return
        
        # Проверяем доступное количество стыков
        data = await state.get_data()
        joint_type = data.get('joint_type')
        joint_type_str = data.get('joint_type_str', '')  # Получаем строковое представление
        thickness = data.get('joint_thickness')
        color = data.get('joint_color')
        
        db = next(get_db())
        try:
            # Находим стык в базе
            joint = db.query(Joint).filter(
                Joint.type == joint_type,
                Joint.thickness == thickness,
                Joint.color == color
            ).first()
            
            if not joint or joint.quantity < quantity:
                max_quantity = joint.quantity if joint else 0
                await message.answer(
                    f"К сожалению, недостаточно стыков. Доступно: {max_quantity} шт.",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[[KeyboardButton(text="◀️ Назад")]],
                        resize_keyboard=True
                    )
                )
                return
            
            # Сохраняем выбранные стыки в состоянии
            selected_joints = data.get('selected_joints', [])
            
            joint_data = {
                "type": joint_type_str,  # Используем строковое представление типа стыка
                "color": color,
                "thickness": thickness,
                "quantity": quantity
            }
            
            # Сохраняем последний выбранный стык для возможности вернуться назад
            await state.update_data(last_joint=joint_data)
            
            # Добавляем новый стык
            selected_joints.append(joint_data)
            await state.update_data(selected_joints=selected_joints)
            
            # Формируем список выбранных стыков для отображения
            joints_text = "\n".join([
                f"• {j['type']}, {j['thickness']} мм, {j['color']}, {j['quantity']} шт."
                for j in selected_joints
            ])
            
            # Спрашиваем, нужны ли еще стыки
            await message.answer(
                f"✅ Стык добавлен в заказ\n\nВыбранные стыки:\n{joints_text}\n\nДобавить еще стыки?",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                        [KeyboardButton(text="◀️ Назад")]
                    ],
                    resize_keyboard=True
                )
            )
            await state.set_state(SalesStates.waiting_for_order_more_joints)
        finally:
            db.close()
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число.")

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

async def process_order_customer_phone(message: Message, state: FSMContext):
    """Обработка ввода контактного номера клиента"""
    phone = message.text.strip()
    
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
            if joint_type == 'butterfly':
                joint_type_text = "Бабочка"
            elif joint_type == 'simple':
                joint_type_text = "Простые"
            elif joint_type == 'closing':
                joint_type_text = "Замыкающие"
            
            order_summary += f"▪️ Тип: {joint_type_text}, {joint.get('thickness', '')} мм, {joint.get('color', '')}: {joint.get('quantity', 0)} шт.\n"
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
