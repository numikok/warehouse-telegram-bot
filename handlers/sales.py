from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from models import User, UserRole, Film, Panel, Joint, Glue, FinishedProduct, Operation, JointType, Order, ProductionOrder, OrderStatus, OrderJoint, OrderGlue, OperationType, OrderItem, CompletedOrder, CompletedOrderStatus
from database import get_db
import json
import logging
from navigation import MenuState, get_menu_keyboard, go_back
import re
from states import SalesStates
from typing import Optional, Dict, List, Any, Union
from sqlalchemy import select, desc
from datetime import datetime, date
from sqlalchemy.orm import joinedload
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()

def has_sales_access(telegram_id: int) -> bool:
    """Проверяет, имеет ли пользователь доступ к функциям продаж"""
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        return user and (user.role == UserRole.SALES_MANAGER or user.role == UserRole.SUPER_ADMIN)
    finally:
        db.close()

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
    """Обработка ввода адреса доставки и переход к дате отгрузки"""
    address = message.text.strip()
    
    if address.lower() == "нет":
        address = "Самовывоз"
    
    # Сохраняем адрес доставки
    await state.update_data(delivery_address=address)
    
    # Запрашиваем дату отгрузки
    await message.answer(
        "Введите дату отгрузки (формат: ДД.ММ.ГГГГ):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Отмена")]],
            resize_keyboard=True
        )
    )
    await state.set_state(SalesStates.waiting_for_shipment_date)

@router.message(SalesStates.waiting_for_shipment_date)
async def process_shipment_date(message: Message, state: FSMContext):
    """Обработка ввода даты отгрузки и переход к способу оплаты"""
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Создание заказа отменено.", reply_markup=get_menu_keyboard(MenuState.SALES_MAIN))
        return

    shipment_date_str = message.text.strip()
    try:
        # Проверяем формат ДД.ММ.ГГГГ
        shipment_date = datetime.strptime(shipment_date_str, "%d.%m.%Y").date()
        
        # Проверка, что дата не в прошлом
        today = datetime.now().date()
        if shipment_date < today:
            await message.answer(
                "❌ Дата отгрузки не может быть в прошлом. Пожалуйста, введите сегодняшнюю или будущую дату (ДД.ММ.ГГГГ):",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="❌ Отмена")]],
                    resize_keyboard=True
                )
            )
            return # Остаемся в том же состоянии, чтобы пользователь ввел дату снова
            
        await state.update_data(shipment_date=shipment_date)
        
        # Запрашиваем способ оплаты
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Юр. Комп.")],
                [KeyboardButton(text="Наличные")],
                [KeyboardButton(text="Kaspi")],
                [KeyboardButton(text="❌ Отмена")]
            ],
            resize_keyboard=True
        )
        await message.answer("Выберите способ оплаты:", reply_markup=keyboard)
        await state.set_state(SalesStates.waiting_for_payment_method)
        
    except ValueError:
        await message.answer(
            "❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ (например, 31.12.2024):",
             reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="❌ Отмена")]],
                resize_keyboard=True
            )
        )

@router.message(SalesStates.waiting_for_payment_method)
async def process_payment_method(message: Message, state: FSMContext):
    """Обработка выбора способа оплаты и переход к подтверждению заказа"""
    payment_method = message.text.strip()
    allowed_methods = ["Юр. Комп.", "Наличные", "Kaspi"]

    if payment_method == "❌ Отмена":
        await state.clear()
        await message.answer("Создание заказа отменено.", reply_markup=get_menu_keyboard(MenuState.SALES_MAIN))
        return
        
    if payment_method not in allowed_methods:
        await message.answer(
            f"Пожалуйста, выберите способ оплаты из предложенных кнопок: {', '.join(allowed_methods)}",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="Юр. Комп.")],
                    [KeyboardButton(text="Наличные")],
                    [KeyboardButton(text="Kaspi")],
                    [KeyboardButton(text="❌ Отмена")]
                ],
                resize_keyboard=True
            )
        )
        return
        
    await state.update_data(payment_method=payment_method)
    
    # Показываем сводку заказа и запрашиваем подтверждение
    data = await state.get_data()
    
    selected_products = data.get('selected_products', [])
    selected_joints = data.get('selected_joints', [])
    need_joints = len(selected_joints) > 0 # Проверяем по факту наличия стыков в списке
    glue_quantity = data.get('glue_quantity', 0)
    installation_required = data.get('installation_required', False)
    customer_phone = data.get('customer_phone', '')
    delivery_address = data.get('delivery_address', '')
    shipment_date = data.get('shipment_date')
    shipment_date_str = shipment_date.strftime('%d.%m.%Y') if shipment_date else 'Не указана'
    payment_method = data.get('payment_method', 'Не указан')
    
    # Формируем текст заказа
    order_summary = f"📝 Сводка заказа:\n\n"
    
    if selected_products:
        order_summary += f"📦 Выбранные продукты:\n"
        total_panels = 0
        for product in selected_products:
            order_summary += f"▪️ {product['film_code']} (толщина {product['thickness']} мм): {product['quantity']} шт.\n"
            total_panels += product['quantity']
        order_summary += f"Всего панелей: {total_panels} шт.\n\n"
    else:
        order_summary += "Продукты не выбраны\n\n"
    
    if need_joints and selected_joints:
        order_summary += f"🔗 Стыки:\n"
        for joint in selected_joints:
            joint_type = joint.get('type', '')
            joint_type_text = ''
            if joint_type == 'butterfly': joint_type_text = "Бабочка"
            elif joint_type == 'simple': joint_type_text = "Простые"
            elif joint_type == 'closing': joint_type_text = "Замыкающие"
            order_summary += f"▪️ Тип: {joint_type_text}, {joint.get('thickness', '')} мм, {joint.get('color', '')}: {joint.get('quantity', 0)} шт.\n"
        order_summary += "\n"
    else:
        order_summary += f"🔗 Стыки: Нет\n\n"
    
    order_summary += f"🧴 Клей: {glue_quantity} тюбиков\n"
    order_summary += f"🔧 Монтаж: {'Требуется' if installation_required else 'Не требуется'}\n"
    order_summary += f"📞 Контактный телефон: {customer_phone}\n"
    order_summary += f"🚚 Адрес доставки: {delivery_address}\n"
    order_summary += f"🗓 Дата отгрузки: {shipment_date_str}\n" # Новое поле
    order_summary += f"💳 Способ оплаты: {payment_method}\n" # Новое поле
    
    await state.update_data(order_summary=order_summary)
    # Используем состояние из navigation.py для подтверждения
    await state.set_state(MenuState.SALES_ORDER_CONFIRM) 
    
    await message.answer(
        order_summary + "\n\nПожалуйста, подтвердите заказ:",
        reply_markup=get_menu_keyboard(MenuState.SALES_ORDER_CONFIRM) # Клавиатура с Подтвердить/Отменить/Назад
    )
    # Устанавливаем состояние ожидания подтверждения
    await state.set_state(SalesStates.waiting_for_order_confirmation) 

@router.message(StateFilter(SalesStates.waiting_for_order_confirmation))
async def process_order_confirmation(message: Message, state: FSMContext):
    """Обработка подтверждения заказа"""
    user_id = message.from_user.id
    
    if message.text not in ["✅ Оформить заказ", "❌ Отменить заказ"]:
        await message.answer(
            "❌ Неверный выбор. Пожалуйста, используйте кнопки для подтверждения или отмены заказа."
        )
        return
        
    if message.text == "❌ Отменить заказ":
        await state.clear()
        await message.answer(
            "🚫 Заказ отменен.",
            reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
        )
        await state.set_state(MenuState.SALES_MAIN)
        return
        
    # Создание заказа
    data = await state.get_data()
    
    db = next(get_db())
    try:
        # Проверяем существование пользователя в базе
        manager = db.query(User).filter(User.telegram_id == user_id).first()
        if not manager:
            await message.answer("⚠️ Произошла ошибка: ваш аккаунт не найден в системе.")
            return
            
        # Создаем заказ (всегда со статусом NEW)
        order = Order(
            customer_name=data.get("customer_name", ""),
            customer_phone=data.get("customer_phone", ""),
            delivery_address=data.get("delivery_address", ""),
            shipment_date=data.get("shipment_date"),
            payment_method=data.get("payment_method", ""),
            status=OrderStatus.NEW,
            created_at=datetime.now(),
            need_installation=data.get("need_installation", False),
            manager_id=manager.id
        )
        
        db.add(order)
        db.flush()  # Получаем id заказа
        
        # Добавляем продукты к заказу
        products = data.get("products", [])
        for product in products:
            order_product = OrderProduct(
                order_id=order.id,
                product_id=product["id"],
                quantity=product["quantity"]
            )
            db.add(order_product)
            
        # Добавляем стыки, если они есть
        joints = data.get("joints", [])
        for joint in joints:
            order_joint = OrderJoint(
                order_id=order.id,
                joint_type=joint["type"],
                color=joint["color"],
                thickness=joint.get("thickness", ""),
                quantity=joint["quantity"]
            )
            db.add(order_joint)
            
        # Добавляем клей, если он есть
        glue_needed = data.get("glue_needed", False)
        if glue_needed:
            glue_quantity = data.get("glue_quantity", 0)
            order_glue = OrderGlue(
                order_id=order.id,
                quantity=glue_quantity
            )
            db.add(order_glue)
            
        db.commit()
        
        success_message = f"✅ Заказ #{order.id} успешно создан!"
        
        await state.clear()
        await message.answer(
            success_message,
            reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
        )
        await state.set_state(MenuState.SALES_MAIN)
        
    except Exception as e:
        db.rollback()
        logger.error(f"Ошибка при создании заказа: {e}")
        await message.answer(
            f"⚠️ Произошла ошибка при создании заказа: {e}",
            reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
        )
        await state.set_state(MenuState.SALES_MAIN)
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

@router.message(F.text == "📝 Заказать")
async def handle_production_order(message: Message, state: FSMContext):
    if not await check_sales_access(message):
        return
    
    # Получаем флаг админ-контекста
    state_data = await state.get_data()
    is_admin_context = state_data.get("is_admin_context", False)
    
    await state.set_state(MenuState.SALES_ORDER)
    
    # Сначала предлагаем выбрать толщину панели
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="0.5")],
            [KeyboardButton(text="0.8")],
            [KeyboardButton(text="◀️ Назад")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "Для начала выберите толщину панелей для заказа (мм).\n\n"
        "После этого вам будут доступны цвета пленки для выбранной толщины:",
        reply_markup=keyboard
    )
    
    # Создаем новое состояние для выбора толщины
    await state.set_state(SalesStates.waiting_for_panel_thickness)

# Новый обработчик для выбора толщины панели
@router.message(SalesStates.waiting_for_panel_thickness)
async def process_panel_thickness(message: Message, state: FSMContext):
    """Обработка выбора толщины панели"""
    if message.text == "◀️ Назад":
        # Возвращаемся к главному меню
        next_menu, keyboard = await go_back(state, UserRole.SALES_MANAGER)
        await state.set_state(next_menu)
        await message.answer(
            "Выберите действие:",
            reply_markup=keyboard
        )
        return
    
    try:
        thickness = float(message.text)
        if thickness not in [0.5, 0.8]:
            await message.answer("Пожалуйста, выберите толщину 0.5 или 0.8 мм.")
            return
            
        # Сохраняем выбранную толщину
        await state.update_data(panel_thickness=thickness)
        
        # Показываем все доступные цвета пленки, независимо от толщины
        db = next(get_db())
        try:
            # Получаем все доступные цвета пленки
            films = db.query(Film).all()
            
            if not films:
                await message.answer(
                    "В базе нет пленки.",
                    reply_markup=get_menu_keyboard(MenuState.SALES_MAIN, is_admin_context=False)
                )
                return
            
            # Создаем клавиатуру с кодами пленки и кнопкой назад
            keyboard = []
            # Размещаем по 2 кнопки в ряд для кодов пленки
            for i in range(0, len(films), 2):
                row = []
                row.append(KeyboardButton(text=films[i].code))
                if i + 1 < len(films):
                    row.append(KeyboardButton(text=films[i + 1].code))
                keyboard.append(row)
            
            # Добавляем кнопку назад
            keyboard.append([KeyboardButton(text="◀️ Назад")])
            
            reply_markup = ReplyKeyboardMarkup(
                keyboard=keyboard,
                resize_keyboard=True
            )
            
            await message.answer(
                f"Выберите цвет пленки для панелей толщиной {thickness} мм:",
                reply_markup=reply_markup
            )
            await state.set_state(SalesStates.waiting_for_film_color)
        finally:
            db.close()
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число (0.5 или 0.8).")

@router.message(F.text == "📦 Заказать на склад")
async def handle_warehouse_order(message: Message, state: FSMContext):
    """Обработка нажатия кнопки 'Заказать на склад'"""
    
    # Проверяем доступ
    if not has_sales_access(message.from_user.id):
        return
    
    db = next(get_db())
    try:
        # Получаем готовую продукцию
        finished_products = db.query(FinishedProduct).all()
        
        if finished_products:
            data = await state.get_data()
            is_admin_context = data.get("is_admin_context", False)
            
            # Формируем сообщение с доступными товарами
            product_text = "Доступные товары:\n\n"
            
            # Создаем клавиатуру с доступными товарами
            keyboard = InlineKeyboardMarkup(row_width=1)
            
            for product in finished_products:
                product_text += f"ID: {product.id}, Пленка: {product.film_color}, Количество: {product.quantity}\n"
                keyboard.add(InlineKeyboardButton(
                    text=f"{product.film_color} (доступно: {product.quantity})",
                    callback_data=f"order_finished:{product.id}"
                ))
            
            keyboard.add(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_order"))
            
            await message.answer(product_text, reply_markup=keyboard)
            await state.set_state(SalesStates.waiting_for_warehouse_selection)
        else:
            await message.answer("⚠️ На складе нет доступной продукции")
            
            # Устанавливаем состояние меню и возвращаем соответствующую клавиатуру
            data = await state.get_data()
            is_admin_context = data.get("is_admin_context", False)
            await state.set_state(MenuState.SALES_MAIN)
            await message.answer(
                "Выберите действие:", 
                reply_markup=get_menu_keyboard(MenuState.SALES_MAIN, is_admin_context=is_admin_context)
            )
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
                response += f"- {product.film.code} (толщина {product.thickness} мм): {product.quantity} шт.\n"
        
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
        await state.set_state(SalesStates.waiting_for_panel_thickness)
        return
    
    db = next(get_db())
    try:
        # Получаем данные из состояния
        data = await state.get_data()
        panel_thickness = data.get("panel_thickness", 0.5)  # По умолчанию 0.5 если не указано
        
        film = db.query(Film).filter(Film.code == message.text.strip()).first()
        if not film:
            await message.answer("❌ Пленка с таким кодом не найдена. Пожалуйста, выберите из списка:")
            return
            
        # Сохраняем код пленки
        await state.update_data(film_color=film.code)
        
        # Расчет возможного количества панелей
        possible_panels = film.calculate_possible_panels()
        remaining_meters = film.total_remaining
        
        # Формируем сообщение с информацией о пленке и возможном производстве
        info_text = (
            f"📋 Информация о выбранном цвете {film.code}:\n\n"
            f"• Толщина панелей: {panel_thickness} мм\n"
            f"• Возможно произвести: {possible_panels} шт.\n\n"
            f"Введите количество:"
        )
        
        # Запрашиваем количество панелей
        await message.answer(info_text)
        await state.set_state(SalesStates.waiting_for_panel_quantity)
    finally:
        db.close()

@router.message(SalesStates.waiting_for_panel_quantity)
async def process_panel_quantity(message: Message, state: FSMContext):
    """Обработка ввода количества панелей и создание заказа"""
    if message.text == "◀️ Назад":
        # Возвращаемся к выбору цвета пленки
        data = await state.get_data()
        thickness = data.get("panel_thickness", 0.5)  # По умолчанию 0.5 если не указано
        
        # Показываем все доступные цвета пленки
        db = next(get_db())
        try:
            # Получаем все цвета пленки
            films = db.query(Film).all()
            
            if not films:
                await message.answer(
                    "В базе нет пленки.",
                    reply_markup=get_menu_keyboard(MenuState.SALES_MAIN, is_admin_context=False)
                )
                return
            
            # Создаем клавиатуру с кодами пленки и кнопкой назад
            keyboard = []
            # Размещаем по 2 кнопки в ряд для кодов пленки
            for i in range(0, len(films), 2):
                row = []
                row.append(KeyboardButton(text=films[i].code))
                if i + 1 < len(films):
                    row.append(KeyboardButton(text=films[i + 1].code))
                keyboard.append(row)
            
            # Добавляем кнопку назад
            keyboard.append([KeyboardButton(text="◀️ Назад")])
            
            reply_markup = ReplyKeyboardMarkup(
                keyboard=keyboard,
                resize_keyboard=True
            )
            
            await message.answer(
                f"Выберите цвет пленки для панелей толщиной {thickness} мм:",
                reply_markup=reply_markup
            )
            await state.set_state(SalesStates.waiting_for_film_color)
        finally:
            db.close()
        return
    
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
            
            # Получаем пленку и проверяем возможное количество панелей
            film = db.query(Film).filter(Film.code == data['film_color']).first()
            if not film:
                await message.answer("❌ Ошибка: пленка не найдена")
                return
                
            # Проверяем, достаточно ли пленки для производства запрошенного количества панелей
            possible_panels = film.calculate_possible_panels()
            if quantity > possible_panels:
                await message.answer(
                    f"❌ Недостаточно пленки для производства {quantity} панелей.\n"
                    f"Максимально возможное количество: {possible_panels} панелей.\n"
                    f"Пожалуйста, введите другое количество:"
                )
                return
                
            # Получаем толщину панели из данных состояния
            panel_thickness = data.get("panel_thickness", 0.5)  # По умолчанию 0.5 если не указано
                
            # Создаем заказ на производство
            production_order = ProductionOrder(
                manager_id=user.id,
                film_color=data['film_color'],
                panel_quantity=quantity,
                panel_thickness=panel_thickness,  # Добавляем толщину панели в заказ
                status="new"
            )
            
            db.add(production_order)
            db.commit()
            
            # Формируем сообщение о созданном заказе
            order_text = (
                f"✅ Заказ #{production_order.id} успешно создан!\n\n"
                f"Толщина панелей: {panel_thickness} мм\n"  # Добавляем информацию о толщине
                f"Цвет: {production_order.film_color}\n"
                f"Количество панелей: {production_order.panel_quantity}"
            )
            
            await message.answer(order_text)
            
            # Возвращаем клавиатуру менеджера и устанавливаем состояние SALES_MAIN
            is_admin_context = data.get("is_admin_context", False)
            await state.set_state(MenuState.SALES_MAIN)
            await message.answer(
                "Выберите действие:",
                reply_markup=get_menu_keyboard(MenuState.SALES_MAIN, is_admin_context=is_admin_context)
            )
            
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
        is_admin_context = data.get("is_admin_context", False)
        
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
            
            # Устанавливаем состояние меню и возвращаем соответствующую клавиатуру
            await state.set_state(MenuState.SALES_MAIN)
            await message.answer(
                "Выберите действие:", 
                reply_markup=get_menu_keyboard(MenuState.SALES_MAIN, is_admin_context=is_admin_context)
            )
        except Exception as e:
            await message.answer(f"❌ Ошибка при создании заказа: {str(e)}")
        finally:
            db.close()
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

@router.message(F.text == "✅ Завершенные заказы", StateFilter(MenuState.SALES_MAIN))
async def handle_completed_orders_sales(message: Message, state: FSMContext):
    """(Sales) Отображает список завершенных заказов и предлагает ввести ID."""
    if not await check_sales_access(message): # Reuse existing access check
        return
    
    await state.set_state(MenuState.SALES_COMPLETED_ORDERS)
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            await message.answer("Ошибка: пользователь не найден.")
            return
            
        # Option 1: Show only orders managed by this manager
        # completed_orders = db.query(CompletedOrder).filter(CompletedOrder.manager_id == user.id)
        
        # Option 2: Show all completed orders (like warehouse view)
        completed_orders = db.query(CompletedOrder).options(
            joinedload(CompletedOrder.manager),
            joinedload(CompletedOrder.warehouse_user)
        ).order_by(desc(CompletedOrder.completed_at)).limit(20).all()
        
        if not completed_orders:
            await message.answer(
                "Нет завершенных заказов.",
                reply_markup=get_menu_keyboard(MenuState.SALES_COMPLETED_ORDERS)
            )
            return
            
        response = "✅ Завершенные заказы (последние 20):\n\n"
        for order in completed_orders:
            response += f"---\n"
            response += f"Заказ #{order.order_id} (Завершен ID: {order.id})\n"
            response += f"Дата завершения: {order.completed_at.strftime('%Y-%m-%d %H:%M')}\n"
            response += f"Статус: {order.status}\n"
            response += f"Менеджер: {order.manager.username if order.manager else 'N/A'}\n"
            response += f"\n"
            
        response += "\nВведите ID завершенного заказа (из поля 'Завершен ID: ...') для просмотра деталей и опций."
        
        if len(response) > 4000:
            response = response[:4000] + "\n... (список слишком длинный)"
            
        await message.answer(
            response,
            reply_markup=get_menu_keyboard(MenuState.SALES_COMPLETED_ORDERS)
        )
            
    except Exception as e:
        logging.error(f"(Sales) Ошибка при получении завершенных заказов: {e}", exc_info=True)
        await message.answer(
            "Произошла ошибка при загрузке завершенных заказов.",
            reply_markup=get_menu_keyboard(MenuState.SALES_COMPLETED_ORDERS)
        )
    finally:
        db.close()

@router.message(StateFilter(MenuState.SALES_COMPLETED_ORDERS), F.text.regexp(r'^\d+$'))
async def view_completed_order_sales(message: Message, state: FSMContext):
    """(Sales) Отображает детали одного завершенного заказа и кнопку возврата."""
    if not await check_sales_access(message):
        return

    try:
        completed_order_id = int(message.text)
    except ValueError:
        await message.answer("Пожалуйста, введите корректный числовой ID.", reply_markup=get_menu_keyboard(MenuState.SALES_COMPLETED_ORDERS))
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
            await message.answer(f"Завершенный заказ с ID {completed_order_id} не найден.", reply_markup=get_menu_keyboard(MenuState.SALES_COMPLETED_ORDERS))
            return

        # Format order details (same as warehouse view)
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
        # ... (copy product/joint/glue formatting from warehouse.py view_completed_order) ...
        if order.items:
            for item in order.items:
                response += f"- {item.color} ({item.thickness} мм): {item.quantity} шт.\n"
        else: response += "- нет\n"
        response += "\nСтыки:\n"
        if order.joints:
            for joint in order.joints:
                response += f"- {joint.joint_type.name.capitalize()} ({joint.joint_thickness} мм, {joint.joint_color}): {joint.quantity} шт.\n"
        else: response += "- нет\n"
        response += "\nКлей:\n"
        if order.glues:
            for glue_item in order.glues:
                response += f"- {glue_item.quantity} шт.\n"
        else: response += "- нет\n"

        # Create inline keyboard (same callback as warehouse)
        keyboard_buttons = []
        if order.status == CompletedOrderStatus.COMPLETED.value:
             keyboard_buttons.append([
                 InlineKeyboardButton(text="♻️ Запрос на возврат", callback_data=f"request_return:{order.id}")
             ])
        
        inline_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons) if keyboard_buttons else None

        # Set state 
        await state.set_state(MenuState.SALES_VIEW_COMPLETED_ORDER)
        await state.update_data(viewed_completed_order_id=order.id)
        
        await message.answer(
            response,
            reply_markup=inline_keyboard
        )

    except Exception as e:
        logging.error(f"(Sales) Ошибка при просмотре завершенного заказа {completed_order_id}: {e}", exc_info=True)
        await message.answer("Произошла ошибка при загрузке деталей заказа.", reply_markup=get_menu_keyboard(MenuState.SALES_COMPLETED_ORDERS))
    finally:
        db.close()

    await state.set_state(MenuState.SALES_RESERVED_ORDERS)
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            await message.answer("Ошибка: пользователь не найден.")
            return
        
        # Получаем забронированные заказы этого менеджера
        reserved_orders = db.query(Order).filter(
            Order.status == OrderStatus.RESERVED,
            Order.manager_id == user.id
        ).order_by(desc(Order.created_at)).all()
        
        if not reserved_orders:
            await message.answer(
                "У вас нет забронированных заказов.",
                reply_markup=get_menu_keyboard(MenuState.SALES_RESERVED_ORDERS)
            )
            return
        
        response = "🔖 Ваши забронированные заказы:\n\n"
        for order in reserved_orders:
            response += f"Заказ #{order.id}\n"
            response += f"Дата создания: {order.created_at.strftime('%Y-%m-%d %H:%M')}\n"
            response += f"Клиент: {order.customer_phone}\n"
            response += f"Адрес: {order.delivery_address}\n"
            response += "\n---\n"
        
        response += "\nВведите ID заказа для просмотра деталей и управления."
        
        if len(response) > 4000:
            response = response[:4000] + "\n... (список слишком длинный)"
        
        await message.answer(
            response,
            reply_markup=get_menu_keyboard(MenuState.SALES_RESERVED_ORDERS)
        )
        
    except Exception as e:
        logging.error(f"Ошибка при получении забронированных заказов: {e}", exc_info=True)
        await message.answer(
            "Произошла ошибка при загрузке забронированных заказов.",
            reply_markup=get_menu_keyboard(MenuState.SALES_RESERVED_ORDERS)
        )
    finally:
        db.close()

@router.message(StateFilter(MenuState.SALES_RESERVED_ORDERS), F.text.regexp(r'^\d+$'))
async def view_reserved_order_sales(message: Message, state: FSMContext):
    """Отображает детали одного забронированного заказа"""
    if not await check_sales_access(message):
        return
    
    try:
        order_id = int(message.text)
    except ValueError:
        await message.answer(
            "Пожалуйста, введите корректный числовой ID.",
            reply_markup=get_menu_keyboard(MenuState.SALES_RESERVED_ORDERS)
        )
        return
    
    db = next(get_db())
    try:
        order = db.query(Order).options(
            joinedload(Order.products),
            joinedload(Order.joints),
            joinedload(Order.glues)
        ).filter(
            Order.id == order_id,
            Order.status == OrderStatus.RESERVED
        ).first()
        
        if not order:
            await message.answer(
                f"Забронированный заказ с ID {order_id} не найден или не имеет статус 'Забронирован'.",
                reply_markup=get_menu_keyboard(MenuState.SALES_RESERVED_ORDERS)
            )
            return
        
        # Формируем подробную информацию о заказе
        order_details = f"🔖 Заказ #{order.id} - Забронирован\n\n"
        
        # Информация о заказчике
        order_details += f"📱 Телефон клиента: {order.customer_phone or 'Не указан'}\n"
        order_details += f"🏠 Адрес доставки: {order.delivery_address or 'Не указан'}\n"
        
        # Дата создания
        if order.created_at:
            order_details += f"📅 Создан: {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        
        # Дата отгрузки, если указана
        if order.shipment_date:
            order_details += f"🚚 Дата отгрузки: {order.shipment_date.strftime('%d.%m.%Y')}\n"
            
        # Способ оплаты
        if order.payment_method:
            order_details += f"💳 Способ оплаты: {order.payment_method}\n"
            
        # Монтаж
        order_details += f"🔧 Монтаж: {'Требуется' if order.installation_required else 'Не требуется'}\n\n"
        
        # Информация о товарах
        if order.products:
            order_details += "📋 Товары в заказе:\n"
            for i, item in enumerate(order.products, 1):
                order_details += f"  {i}. Плёнка: {item.color}, толщина: {item.thickness} мм, количество: {item.quantity} шт.\n"
        
        # Информация о стыках
        if order.joints:
            order_details += "\n🔄 Стыки в заказе:\n"
            for i, joint in enumerate(order.joints, 1):
                joint_type_name = "Бабочка" if joint.joint_type == JointType.BUTTERFLY else "Простой" if joint.joint_type == JointType.SIMPLE else "Замыкающий"
                order_details += f"  {i}. Тип: {joint_type_name}, цвет: {joint.joint_color}, толщина: {joint.joint_thickness} мм, количество: {joint.quantity} шт.\n"
        
        # Информация о клее
        if order.glues:
            total_glue = sum(glue.quantity for glue in order.glues)
            order_details += f"\n🧴 Клей: {total_glue} шт.\n"
        
        # Добавляем кнопки для подтверждения или отмены бронирования
        order_details += "\nДля подтверждения или отмены бронирования используйте кнопки ниже:"
        
        # Создаем инлайн клавиатуру
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Оформить заказ", callback_data=f"confirm_reserved:{order.id}")
        kb.button(text="❌ Отменить", callback_data=f"cancel_reserved:{order.id}")
        kb.adjust(2)  # 2 кнопки в ряд
        
        await message.answer(
            order_details,
            reply_markup=kb.as_markup()
        )
        
    except Exception as e:
        logging.error(f"Ошибка при просмотре забронированного заказа: {e}", exc_info=True)
        await message.answer(
            "Произошла ошибка при загрузке деталей заказа.",
            reply_markup=get_menu_keyboard(MenuState.SALES_RESERVED_ORDERS)
        )
    finally:
        db.close()

@router.callback_query(lambda c: c.data.startswith("confirm_reserved:"))
async def process_confirm_reserved_order(callback_query: CallbackQuery, state: FSMContext):
    """Обработка подтверждения забронированного заказа"""
    await callback_query.answer()
    
    # Извлекаем ID заказа из callback_data
    order_id = int(callback_query.data.split(":")[1])
    
    db = next(get_db())
    try:
        # Получаем заказ
        order = db.query(Order).filter(
            Order.id == order_id,
            Order.status == OrderStatus.RESERVED
        ).first()
        
        if not order:
            await callback_query.message.answer(
                "Заказ не найден или уже не имеет статус 'Забронирован'.",
                reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
            )
            await state.set_state(MenuState.SALES_MAIN)
            return
        
        # Проверяем права доступа
        user = db.query(User).filter(User.telegram_id == callback_query.from_user.id).first()
        if not user or (order.manager_id != user.id and user.role != UserRole.SUPER_ADMIN.value):
            await callback_query.message.answer(
                "У вас нет прав для управления этим заказом.",
                reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
            )
            await state.set_state(MenuState.SALES_MAIN)
            return
        
        # Меняем статус заказа на PENDING
        order.status = OrderStatus.PENDING
        db.commit()
        
        await callback_query.message.answer(
            f"✅ Заказ #{order_id} подтвержден и отправлен в производство.",
            reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
        )
        await state.set_state(MenuState.SALES_MAIN)
        
    except Exception as e:
        db.rollback()
        logging.error(f"Ошибка при подтверждении забронированного заказа {order_id}: {e}", exc_info=True)
        await callback_query.message.answer(
            f"❌ Произошла ошибка при подтверждении заказа: {str(e)}",
            reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
        )
        await state.set_state(MenuState.SALES_MAIN)
    finally:
        db.close()

@router.callback_query(lambda c: c.data.startswith("cancel_reserved:"))
async def process_cancel_reserved_order(callback_query: CallbackQuery, state: FSMContext):
    """Обработка отмены забронированного заказа"""
    await callback_query.answer()
    
    # Извлекаем ID заказа из callback_data
    order_id = int(callback_query.data.split(":")[1])
    
    db = next(get_db())
    try:
        # Получаем заказ
        order = db.query(Order).filter(
            Order.id == order_id,
            Order.status == OrderStatus.RESERVED
        ).first()
        
        if not order:
            await callback_query.message.answer(
                "Заказ не найден или уже не имеет статус 'Забронирован'.",
                reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
            )
            await state.set_state(MenuState.SALES_MAIN)
            return
        
        # Проверяем права доступа
        user = db.query(User).filter(User.telegram_id == callback_query.from_user.id).first()
        if not user or (order.manager_id != user.id and user.role != UserRole.SUPER_ADMIN.value):
            await callback_query.message.answer(
                "У вас нет прав для управления этим заказом.",
                reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
            )
            await state.set_state(MenuState.SALES_MAIN)
            return
        
        # Меняем статус заказа на CANCELLED
        order.status = OrderStatus.CANCELLED
        db.commit()
        
        await callback_query.message.answer(
            f"❌ Заказ #{order_id} отменен.",
            reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
        )
        await state.set_state(MenuState.SALES_MAIN)
        
    except Exception as e:
        db.rollback()
        logging.error(f"Ошибка при отмене забронированного заказа {order_id}: {e}", exc_info=True)
        await callback_query.message.answer(
            f"❌ Произошла ошибка при отмене заказа: {str(e)}",
            reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
        )
        await state.set_state(MenuState.SALES_MAIN)
    finally:
        db.close()

@router.message(F.text == "🔖 Бронь", StateFilter(MenuState.SALES_MAIN))
async def handle_booking(message: Message, state: FSMContext):
    """Обработчик для бронирования существующих заказов"""
    if not await check_sales_access(message):
        return
    
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            await message.answer("❌ Ошибка: пользователь не найден в системе.")
            return
        
        # Получаем список всех заказов со статусом NEW
        available_orders = db.query(Order).filter(
            Order.status == OrderStatus.NEW,
            Order.manager_id == user.id  # Только заказы этого менеджера
        ).order_by(desc(Order.created_at)).all()
        
        if not available_orders:
            await message.answer(
                "ℹ️ У вас нет доступных заказов для бронирования.",
                reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
            )
            return
        
        response = "📋 Выберите заказ для бронирования:\n\n"
        for order in available_orders:
            # Формируем краткую информацию о заказе
            response += f"🔹 Заказ #{order.id}\n"
            response += f"   Дата создания: {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            
            # Получаем информацию о продуктах в заказе
            order_products = db.query(OrderProduct).filter(OrderProduct.order_id == order.id).all()
            if order_products:
                response += f"   Товаров: {len(order_products)}\n"
                
            # Проверяем наличие клиентской информации
            if order.customer_phone:
                response += f"   Телефон: {order.customer_phone}\n"
                
            response += "   ---\n"
        
        response += "\nВведите номер заказа, который хотите забронировать:"
        
        await message.answer(
            response,
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="◀️ Назад")]],
                resize_keyboard=True
            )
        )
        
        # Устанавливаем состояние ожидания выбора заказа для бронирования
        await state.set_state(SalesStates.waiting_for_booking_order_selection)
        
    except Exception as e:
        logger.error(f"Ошибка при получении списка заказов для бронирования: {e}")
        await message.answer(
            f"⚠️ Произошла ошибка при получении списка заказов: {e}",
            reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
        )
    finally:
        db.close()

@router.message(StateFilter(SalesStates.waiting_for_booking_order_selection), F.text.regexp(r'^\d+$'))
async def process_booking_order_selection(message: Message, state: FSMContext):
    """Обработка выбора заказа для бронирования"""
    order_id = int(message.text)
    
    db = next(get_db())
    try:
        # Получаем данные пользователя
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            await message.answer("❌ Ошибка: пользователь не найден в системе.")
            return
        
        # Проверяем существование заказа и его статус
        order = db.query(Order).filter(
            Order.id == order_id,
            Order.manager_id == user.id  # Только заказы этого менеджера
        ).first()
        
        if not order:
            await message.answer(
                f"❌ Заказ #{order_id} не найден или не принадлежит вам.",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="◀️ Назад")]],
                    resize_keyboard=True
                )
            )
            return
        
        if order.status != OrderStatus.NEW:
            if order.status == OrderStatus.RESERVED:
                await message.answer(
                    f"⚠️ Заказ #{order_id} уже забронирован.",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[[KeyboardButton(text="◀️ Назад")]],
                        resize_keyboard=True
                    )
                )
            else:
                await message.answer(
                    f"⚠️ Заказ #{order_id} имеет статус '{order.status}' и не может быть забронирован.",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[[KeyboardButton(text="◀️ Назад")]],
                        resize_keyboard=True
                    )
                )
            return
        
        # Формируем детальную информацию о заказе для подтверждения
        order_details = f"🔹 Заказ #{order.id}\n\n"
        
        # Основная информация о заказе
        order_details += f"📅 Дата создания: {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        if order.customer_phone:
            order_details += f"📞 Телефон клиента: {order.customer_phone}\n"
        if order.delivery_address:
            order_details += f"🚚 Адрес доставки: {order.delivery_address}\n"
        if order.shipment_date:
            order_details += f"📆 Дата отгрузки: {order.shipment_date.strftime('%d.%m.%Y')}\n"
        order_details += f"🔧 Монтаж: {'Требуется' if order.need_installation else 'Не требуется'}\n"
        
        # Продукты в заказе
        order_products = db.query(OrderProduct).filter(OrderProduct.order_id == order.id).all()
        if order_products:
            order_details += "\n📦 Товары в заказе:\n"
            for i, product in enumerate(order_products, 1):
                product_info = db.query(Product).filter(Product.id == product.product_id).first()
                if product_info:
                    order_details += f"  {i}. {product_info.name}, количество: {product.quantity}\n"
                else:
                    order_details += f"  {i}. Продукт ID: {product.product_id}, количество: {product.quantity}\n"
        
        # Стыки в заказе
        order_joints = db.query(OrderJoint).filter(OrderJoint.order_id == order.id).all()
        if order_joints:
            order_details += "\n🔄 Стыки в заказе:\n"
            for i, joint in enumerate(order_joints, 1):
                order_details += f"  {i}. Тип: {joint.joint_type}, цвет: {joint.color}, толщина: {joint.thickness}, количество: {joint.quantity}\n"
        
        # Клей в заказе
        order_glue = db.query(OrderGlue).filter(OrderGlue.order_id == order.id).first()
        if order_glue:
            order_details += f"\n🧴 Клей: {order_glue.quantity} тюбиков\n"
        
        order_details += "\nВы уверены, что хотите забронировать этот заказ?"
        
        # Сохраняем ID заказа в контексте состояния
        await state.update_data(booking_order_id=order_id)
        
        # Отправляем детальную информацию и запрашиваем подтверждение
        await message.answer(
            order_details,
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Да, забронировать")],
                    [KeyboardButton(text="❌ Нет, отменить")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        
        # Устанавливаем состояние ожидания подтверждения бронирования
        await state.set_state(SalesStates.waiting_for_booking_confirmation)
        
    except Exception as e:
        logger.error(f"Ошибка при выборе заказа для бронирования: {e}")
        await message.answer(
            f"⚠️ Произошла ошибка при выборе заказа: {e}",
            reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
        )
        await state.set_state(MenuState.SALES_MAIN)
    finally:
        db.close()

@router.message(StateFilter(SalesStates.waiting_for_booking_order_selection), F.text == "◀️ Назад")
async def booking_back_to_main(message: Message, state: FSMContext):
    """Возврат из выбора заказа в главное меню"""
    await state.set_state(MenuState.SALES_MAIN)
    await message.answer(
        "Вы вернулись в главное меню.",
        reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
    )

@router.message(StateFilter(SalesStates.waiting_for_booking_confirmation), F.text == "✅ Да, забронировать")
async def confirm_booking(message: Message, state: FSMContext):
    """Обработка подтверждения бронирования заказа"""
    # Получаем ID заказа из контекста состояния
    data = await state.get_data()
    order_id = data.get("booking_order_id")
    
    if not order_id:
        await message.answer(
            "❌ Ошибка: ID заказа не найден в контексте.",
            reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
        )
        await state.set_state(MenuState.SALES_MAIN)
        return
    
    db = next(get_db())
    try:
        # Получаем заказ
        order = db.query(Order).filter(Order.id == order_id).first()
        
        if not order:
            await message.answer(
                f"❌ Заказ #{order_id} не найден.",
                reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
            )
            await state.set_state(MenuState.SALES_MAIN)
            return
        
        if order.status != OrderStatus.NEW:
            await message.answer(
                f"⚠️ Заказ #{order_id} не может быть забронирован, так как его статус: {order.status}",
                reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
            )
            await state.set_state(MenuState.SALES_MAIN)
            return
        
        # Меняем статус заказа на RESERVED
        order.status = OrderStatus.RESERVED
        db.commit()
        
        await message.answer(
            f"✅ Заказ #{order_id} успешно переведен в статус 'Reserved'.",
            reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
        )
        await state.set_state(MenuState.SALES_MAIN)
        
    except Exception as e:
        db.rollback()
        logger.error(f"Ошибка при бронировании заказа {order_id}: {e}")
        await message.answer(
            f"⚠️ Произошла ошибка при бронировании заказа: {e}",
            reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
        )
        await state.set_state(MenuState.SALES_MAIN)
    finally:
        db.close()

@router.message(StateFilter(SalesStates.waiting_for_booking_confirmation), F.text.in_(["❌ Нет, отменить", "◀️ Назад"]))
async def cancel_booking(message: Message, state: FSMContext):
    """Отмена бронирования и возврат к выбору заказа"""
    await message.answer(
        "Бронирование отменено. Выберите другой заказ или вернитесь в главное меню.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Назад")]],
            resize_keyboard=True
        )
    )
    await state.set_state(SalesStates.waiting_for_booking_order_selection)

@router.message(StateFilter(SalesStates.waiting_for_booking_order_selection))
async def invalid_booking_order_input(message: Message, state: FSMContext):
    """Обработка некорректного ввода при выборе заказа для бронирования"""
    await message.answer(
        "Пожалуйста, введите числовой ID заказа или нажмите 'Назад' для возврата в главное меню."
    )

@router.message(StateFilter(SalesStates.waiting_for_booking_confirmation))
async def invalid_booking_confirmation_input(message: Message, state: FSMContext):
    """Обработка некорректного ввода при подтверждении бронирования"""
    await message.answer(
        "Пожалуйста, используйте кнопки для подтверждения или отмены бронирования."
    )
