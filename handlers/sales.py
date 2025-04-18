from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from models import User, UserRole, Film, Panel, Joint, Glue, FinishedProduct, Operation, JointType, Order, ProductionOrder, OrderStatus
from database import get_db
import json
import logging
from navigation import MenuState, get_menu_keyboard, go_back

router = Router()

class SalesStates(StatesGroup):
    # Состояния для заказа на производство
    waiting_for_film_color = State()
    waiting_for_panel_quantity = State()
    
    # Состояния для заказа на склад
    waiting_for_film_code = State()
    waiting_for_panels_count = State()
    waiting_for_joint_type = State()
    waiting_for_joint_color = State()
    waiting_for_joint_quantity = State()
    waiting_for_glue_quantity = State()
    waiting_for_installation = State()
    waiting_for_phone = State()
    waiting_for_address = State()
    
    # Новые состояния для создания заказа
    waiting_for_order_film_color = State()
    waiting_for_order_panel_quantity = State()
    waiting_for_need_joints = State()
    waiting_for_order_joint_type = State()
    waiting_for_order_joint_thickness = State()
    waiting_for_order_joint_color = State()
    waiting_for_order_joint_quantity = State()
    waiting_for_need_glue = State()
    waiting_for_order_glue_quantity = State()
    waiting_for_order_installation = State()
    waiting_for_order_customer_phone = State()
    waiting_for_order_delivery_address = State()
    waiting_for_order_confirmation = State()

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
async def process_joint_quantity(message: Message, state: FSMContext):
    """Обработка ввода количества стыков"""
    try:
        quantity = int(message.text.strip())
        if quantity <= 0:
            await message.answer(
                "❌ Количество должно быть больше 0",
                reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
            )
            return
        
        # Проверяем наличие достаточного количества стыков
        db = next(get_db())
        try:
            data = await state.get_data()
            joint_type = data.get('joint_type')
            joint_thickness = data.get('joint_thickness')
            joint_color = data.get('joint_color', '')
            
            joint = db.query(Joint).filter(
                Joint.type == joint_type,
                Joint.thickness == joint_thickness,
                Joint.color == joint_color
            ).first()
            
            if not joint or joint.quantity < quantity:
                available = joint.quantity if joint else 0
                await message.answer(
                    f"❌ Недостаточное количество стыков (доступно: {available} шт.)",
                    reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
                )
                return
            
            # Сохраняем количество стыков
            await state.update_data(joint_quantity=quantity)
            
            # Переходим к запросу о необходимости клея
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
        finally:
            db.close()
    except ValueError:
        await message.answer(
            "❌ Пожалуйста, введите число",
            reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
        )

@router.message(SalesStates.waiting_for_glue_quantity)
async def process_glue_quantity(message: Message, state: FSMContext):
    """Обработка ввода количества клея"""
    try:
        quantity = int(message.text.strip())
        if quantity < 0:
            await message.answer(
                "❌ Количество не может быть отрицательным",
                reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
            )
            return
        
        # Проверяем наличие достаточного количества клея
        db = next(get_db())
        try:
            glue = db.query(Glue).first()
            if not glue or glue.quantity < quantity:
                available = glue.quantity if glue else 0
                if quantity > 0:  # Только если пользователь запросил клей
                    await message.answer(
                        f"❌ Недостаточное количество клея (доступно: {available} тюбиков)",
                        reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
                    )
                    return
            
            # Сохраняем количество клея
            await state.update_data(glue_quantity=quantity)
            
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
        finally:
            db.close()
    except ValueError:
        await message.answer(
            "❌ Пожалуйста, введите число",
            reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
        )

@router.message(SalesStates.waiting_for_installation)
async def process_installation(message: Message, state: FSMContext):
    """Обработка выбора монтажа"""
    db = next(get_db())
    try:
        installation = message.text.strip().lower()
        if installation not in ["да", "нет"]:
            await message.answer("Неверный ответ. Пожалуйста, выберите из списка: да/нет")
            return
        
        await state.update_data(installation=installation == "да")
        await message.answer("Введите телефон клиента:")
        await state.set_state(SalesStates.waiting_for_phone)
    except ValueError:
        await message.answer("❌ Пожалуйста, выберите монтаж из списка")

@router.message(SalesStates.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    """Обработка ввода телефона клиента"""
    db = next(get_db())
    try:
        phone = message.text.strip()
        await state.update_data(phone=phone)
        await message.answer("Введите адрес доставки:")
        await state.set_state(SalesStates.waiting_for_address)
    except ValueError:
        await message.answer("❌ Пожалуйста, введите телефон клиента")

@router.message(SalesStates.waiting_for_address)
async def process_address(message: Message, state: FSMContext):
    """Обработка ввода адреса доставки"""
    db = next(get_db())
    try:
        address = message.text.strip()
        await state.update_data(address=address)
        await message.answer("Заказ успешно создан!")
        await state.clear()
    except ValueError:
        await message.answer("❌ Пожалуйста, введите адрес доставки")

@router.message(Command("stock"))
async def cmd_stock(message: Message):
    if not await check_sales_access(message):
        return
        
    db = next(get_db())
    try:
        # Получаем остатки готовой продукции
        finished_products = db.query(FinishedProduct).join(Film).all()
        
        if not finished_products:
            await message.answer("На данный момент нет доступных продуктов на складе.")
            return
            
        response = "Текущие запасы готовой продукции:\n\n"
        
        # Панели
        response += "📦 Готовые панели:\n"
        for product in finished_products:
            response += f"Код панели: {product.film.code}\n"
            response += f"Количество: {product.quantity} шт.\n\n"
        
        # Стыки
        joints = db.query(Joint).all()
        response += "🔄 Стыки:\n"
        for joint in joints:
            # Преобразуем тип стыка в понятный формат
            joint_type_map = {
                "butterfly": "бабочка",
                "simple": "простой",
                "closing": "замыкающий"
            }
            joint_type = joint_type_map.get(joint.type.value, joint.type.value)
            
            response += f"Цвет: {joint.color} ({joint_type})\n"
            response += f"Количество: {joint.quantity} шт.\n\n"
        
        # Клей
        glue = db.query(Glue).first()
        response += "🧪 Клей:\n"
        if glue:
            response += f"Количество: {glue.quantity} шт.\n"
        else:
            response += "Нет в наличии\n"
        
        await message.answer(response)
    finally:
        db.close()

@router.message(F.text == "📝 Составить заказ")
async def handle_create_order(message: Message, state: FSMContext):
    if not await check_sales_access(message):
        return
    
    await state.set_state(MenuState.SALES_CREATE_ORDER)
    db = next(get_db())
    try:
        # Получаем список доступных цветов пленки
        finished_products = db.query(FinishedProduct).join(Film).all()
        films = db.query(Film).all()
        
        # Список готовой продукции
        ready_products = []
        if finished_products:
            for product in finished_products:
                if product.quantity > 0:
                    ready_products.append(f"• {product.film.code} (готовая продукция: {product.quantity} шт.)")
        
        # Список продукции, которую можно произвести
        manufacturable_products = []
        for film in films:
            if film.total_remaining > 0:
                possible_panels = film.calculate_possible_panels()
                if possible_panels > 0:
                    manufacturable_products.append(f"• {film.code} (можно произвести: {possible_panels} панелей)")
        
        # Формируем сообщение с разделением на категории
        message_text = ""
        
        if ready_products:
            message_text += "🎨 Доступные цвета готовой продукции:\n"
            message_text += "\n".join(ready_products)
            message_text += "\n\n"  # Пустая строка для разделения
        
        if manufacturable_products:
            message_text += "🛠 Цвета, которые можно произвести из текущих материалов:\n"
            message_text += "\n".join(manufacturable_products)
        
        if not ready_products and not manufacturable_products:
            await message.answer(
                "В настоящее время нет доступных цветов пленки для заказа.",
                reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
            )
            return
        
        await message.answer(
            message_text,
            reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
        )
        await state.set_state(SalesStates.waiting_for_order_film_color)
    finally:
        db.close()

@router.message(SalesStates.waiting_for_order_film_color)
async def process_order_film_color(message: Message, state: FSMContext):
    """Обработка выбора цвета пленки для заказа"""
    db = next(get_db())
    try:
        film_code = message.text.strip()
        film = db.query(Film).filter(Film.code == film_code).first()
        
        if not film:
            await message.answer(
                "❌ Пленка с таким кодом не найдена. Пожалуйста, выберите из списка:",
                reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
            )
            return
        
        # Сохраняем выбранный цвет пленки
        await state.update_data(film_code=film_code)
        
        # Проверяем наличие готовой продукции
        finished_product = db.query(FinishedProduct).join(Film).filter(Film.code == film_code).first()
        available_quantity = 0
        if finished_product:
            available_quantity = finished_product.quantity
        
        # Запрашиваем количество панелей
        await message.answer(
            f"Введите количество панелей (доступно готовой продукции: {available_quantity} шт.):",
            reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
        )
        await state.set_state(SalesStates.waiting_for_order_panel_quantity)
    finally:
        db.close()

@router.message(SalesStates.waiting_for_order_panel_quantity)
async def process_order_panel_quantity(message: Message, state: FSMContext):
    """Обработка ввода количества панелей для заказа"""
    try:
        quantity = int(message.text.strip())
        if quantity <= 0:
            await message.answer(
                "❌ Количество должно быть больше 0",
                reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
            )
            return
        
        # Сохраняем количество панелей
        await state.update_data(panel_quantity=quantity)
        
        # Запрашиваем необходимость стыков
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                [KeyboardButton(text="◀️ Назад")]
            ],
            resize_keyboard=True
        )
        await message.answer(
            "Требуются ли стыки?",
            reply_markup=keyboard
        )
        await state.set_state(SalesStates.waiting_for_need_joints)
    except ValueError:
        await message.answer(
            "❌ Пожалуйста, введите число",
            reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
        )

@router.message(SalesStates.waiting_for_need_joints)
async def process_need_joints(message: Message, state: FSMContext):
    """Обработка ответа на вопрос о необходимости стыков"""
    response = message.text.strip()
    
    if response == "✅ Да":
        # Пользователь хочет стыки
        await state.update_data(need_joints=True)
        
        # Сразу показываем доступные стыки
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
                joints_info = "❌ Нет доступных стыков на складе"
                # Если нет стыков, переходим к вопросу о клее
                await state.update_data(need_joints=False, joint_type=None, joint_thickness=None, joint_color=None, joint_quantity=0)
                
                # Запрашиваем необходимость клея
                keyboard = ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
                        [KeyboardButton(text="◀️ Назад")]
                    ],
                    resize_keyboard=True
                )
                await message.answer(
                    joints_info + "\n\nТребуется ли клей?",
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
        await state.update_data(need_joints=False, joint_type=None, joint_thickness=None, joint_color=None, joint_quantity=0)
        
        # Переходим к запросу о необходимости клея
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
    else:
        await message.answer(
            "Пожалуйста, выберите один из вариантов: ✅ Да или ❌ Нет",
            reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
        )

@router.message(SalesStates.waiting_for_order_joint_type)
async def process_order_joint_type(message: Message, state: FSMContext):
    """Обработка выбора типа стыка"""
    joint_type_text = message.text.strip()
    
    joint_type_map = {
        "🦋 Бабочка": JointType.BUTTERFLY,
        "🔄 Простые": JointType.SIMPLE,
        "🔒 Замыкающие": JointType.CLOSING
    }
    
    if joint_type_text not in joint_type_map:
        await message.answer(
            "❌ Пожалуйста, выберите тип стыка из предложенных вариантов",
            reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
        )
        return
    
    # Сохраняем тип стыка (сохраняем сам объект enum, а не его строковое значение)
    joint_type = joint_type_map[joint_type_text]
    await state.update_data(joint_type=joint_type)
    
    # Запрашиваем толщину стыка
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="0.5 мм"), KeyboardButton(text="0.8 мм")],
            [KeyboardButton(text="◀️ Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer(
        "Выберите толщину стыка:",
        reply_markup=keyboard
    )
    await state.set_state(SalesStates.waiting_for_order_joint_thickness)

@router.message(SalesStates.waiting_for_order_joint_thickness)
async def process_order_joint_thickness(message: Message, state: FSMContext):
    """Обработка выбора толщины стыка"""
    thickness_text = message.text.strip()
    
    thickness_map = {
        "0.5 мм": 0.5,
        "0.8 мм": 0.8
    }
    
    if thickness_text not in thickness_map:
        await message.answer(
            "❌ Пожалуйста, выберите толщину стыка из предложенных вариантов",
            reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
        )
        return
    
    # Сохраняем толщину стыка
    thickness = thickness_map[thickness_text]
    await state.update_data(joint_thickness=thickness)
    
    # Получаем доступные цвета стыков из базы данных
    db = next(get_db())
    try:
        data = await state.get_data()
        joint_type = data.get('joint_type')
        
        # Получаем уникальные цвета стыков для выбранного типа и толщины
        joints = db.query(Joint).filter(
            Joint.type == joint_type,
            Joint.thickness == thickness,
            Joint.quantity > 0
        ).all()
        
        colors = set(joint.color for joint in joints)
        
        if not colors:
            await message.answer(
                "❌ Нет доступных цветов для выбранного типа и толщины стыка",
                reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
            )
            return
        
        # Создаем клавиатуру с доступными цветами
        keyboard_buttons = []
        for color in colors:
            # Найдем количество для этого цвета
            joint = next((j for j in joints if j.color == color), None)
            quantity = joint.quantity if joint else 0
            keyboard_buttons.append([KeyboardButton(text=f"{color} (остаток: {quantity} шт.)")])
        
        keyboard_buttons.append([KeyboardButton(text="◀️ Назад")])
        keyboard = ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)
        
        await message.answer(
            "Выберите цвет стыка:",
            reply_markup=keyboard
        )
        await state.set_state(SalesStates.waiting_for_order_joint_color)
    finally:
        db.close()

@router.message(SalesStates.waiting_for_order_joint_color)
async def process_order_joint_color(message: Message, state: FSMContext):
    """Обработка выбора цвета стыка"""
    joint_color_text = message.text.strip()
    
    # Извлекаем чистый цвет из текста вида "Белый (остаток: 10 шт.)"
    if "(" in joint_color_text:
        joint_color = joint_color_text.split("(")[0].strip()
    else:
        joint_color = joint_color_text
    
    # Проверяем наличие стыков выбранного цвета
    db = next(get_db())
    try:
        data = await state.get_data()
        joint_type = data.get('joint_type')
        joint_thickness = data.get('joint_thickness')
        
        joint = db.query(Joint).filter(
            Joint.type == joint_type,
            Joint.thickness == joint_thickness,
            Joint.color == joint_color,
            Joint.quantity > 0
        ).first()
        
        if not joint:
            await message.answer(
                "❌ Стыки с выбранными параметрами не найдены",
                reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
            )
            return
        
        # Сохраняем цвет стыка
        await state.update_data(joint_color=joint_color)
        
        # Запрашиваем количество стыков
        available_quantity = joint.quantity
        await message.answer(
            f"Введите количество стыков (доступно: {available_quantity} шт.):",
            reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
        )
        await state.set_state(SalesStates.waiting_for_order_joint_quantity)
    finally:
        db.close()

@router.message(SalesStates.waiting_for_order_joint_quantity)
async def process_order_joint_quantity(message: Message, state: FSMContext):
    """Обработка ввода количества стыков"""
    try:
        quantity = int(message.text.strip())
        if quantity <= 0:
            await message.answer(
                "❌ Количество должно быть больше 0",
                reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
            )
            return
        
        # Проверяем наличие достаточного количества стыков
        db = next(get_db())
        try:
            data = await state.get_data()
            joint_type = data.get('joint_type')
            joint_thickness = data.get('joint_thickness')
            joint_color = data.get('joint_color', '')
            
            joint = db.query(Joint).filter(
                Joint.type == joint_type,
                Joint.thickness == joint_thickness,
                Joint.color == joint_color
            ).first()
            
            if not joint or joint.quantity < quantity:
                available = joint.quantity if joint else 0
                await message.answer(
                    f"❌ Недостаточное количество стыков (доступно: {available} шт.)",
                    reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
                )
                return
            
            # Сохраняем количество стыков
            await state.update_data(joint_quantity=quantity)
            
            # Переходим к запросу о необходимости клея
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
        finally:
            db.close()
    except ValueError:
        await message.answer(
            "❌ Пожалуйста, введите число",
            reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
        )

@router.message(SalesStates.waiting_for_order_glue_quantity)
async def process_order_glue_quantity(message: Message, state: FSMContext):
    """Обработка ввода количества клея"""
    try:
        quantity = int(message.text.strip())
        if quantity < 0:
            await message.answer(
                "❌ Количество не может быть отрицательным",
                reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
            )
            return
        
        # Проверяем наличие достаточного количества клея
        db = next(get_db())
        try:
            glue = db.query(Glue).first()
            if not glue or glue.quantity < quantity:
                available = glue.quantity if glue else 0
                if quantity > 0:  # Только если пользователь запросил клей
                    await message.answer(
                        f"❌ Недостаточное количество клея (доступно: {available} тюбиков)",
                        reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
                    )
                    return
            
            # Сохраняем количество клея
            await state.update_data(glue_quantity=quantity)
            
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
        finally:
            db.close()
    except ValueError:
        await message.answer(
            "❌ Пожалуйста, введите число",
            reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
        )

@router.message(SalesStates.waiting_for_order_installation)
async def process_order_installation(message: Message, state: FSMContext):
    """Обработка ответа на вопрос о монтаже"""
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
    
    film_code = data.get('film_code', '')
    panel_quantity = data.get('panel_quantity', 0)
    need_joints = data.get('need_joints', False)
    joint_type = data.get('joint_type', '')
    joint_thickness = data.get('joint_thickness', 0)
    joint_color = data.get('joint_color', '')
    joint_quantity = data.get('joint_quantity', 0)
    glue_quantity = data.get('glue_quantity', 0)
    installation_required = data.get('installation_required', False)
    customer_phone = data.get('customer_phone', '')
    delivery_address = data.get('delivery_address', '')
    
    # Преобразуем тип стыка из enum в текст
    joint_type_text = ""
    if joint_type:
        if joint_type == JointType.BUTTERFLY.value:
            joint_type_text = "Бабочка"
        elif joint_type == JointType.SIMPLE.value:
            joint_type_text = "Простые"
        elif joint_type == JointType.CLOSING.value:
            joint_type_text = "Замыкающие"
    
    # Формируем текст заказа
    order_summary = f"📝 Сводка заказа:\n\n"
    order_summary += f"🎨 Цвет пленки: {film_code}\n"
    order_summary += f"📏 Количество панелей: {panel_quantity} шт.\n"
    
    if need_joints:
        order_summary += f"🔗 Стыки: {joint_type_text}, {joint_thickness} мм, {joint_color}, {joint_quantity} шт.\n"
    else:
        order_summary += f"🔗 Стыки: Нет\n"
    
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
        # Сохраняем заказ в базе данных
        db = next(get_db())
        try:
            data = await state.get_data()
            user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
            
            # Проверяем наличие стыков, если нет - используем значение по умолчанию
            need_joints = data.get('need_joints', False)
            joint_type = data.get('joint_type') if need_joints else JointType.SIMPLE  # Используем SIMPLE как тип по умолчанию
            joint_color = data.get('joint_color', '') if need_joints else ''
            joint_quantity = data.get('joint_quantity', 0) if need_joints else 0

            # Создаем новый заказ
            new_order = Order(
                manager_id=user.id,
                film_code=data.get('film_code', ''),
                panel_quantity=data.get('panel_quantity', 0),
                joint_type=joint_type,  # Теперь всегда будет иметь значение
                joint_color=joint_color,
                joint_quantity=joint_quantity,
                glue_quantity=data.get('glue_quantity', 0),
                installation_required=data.get('installation_required', False),
                customer_phone=data.get('customer_phone', ''),
                delivery_address=data.get('delivery_address', ''),
                status=OrderStatus.NEW
            )
            
            db.add(new_order)
            db.commit()
            
            # Отправляем подтверждение пользователю
            await message.answer(
                f"✅ Заказ #{new_order.id} успешно создан!\n\n" + data.get('order_summary', ''),
                reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
            )
            await state.set_state(MenuState.SALES_MAIN)
            
            # Уведомляем склад о новом заказе
            warehouse_users = db.query(User).filter(User.role == UserRole.WAREHOUSE).all()
            for wh_user in warehouse_users:
                try:
                    await message.bot.send_message(
                        wh_user.telegram_id,
                        f"📦 Новый заказ #{new_order.id}!\n\n" + data.get('order_summary', '')
                    )
                except Exception as e:
                    logging.error(f"Не удалось отправить уведомление складовщику {wh_user.telegram_id}: {str(e)}")
            
        except Exception as e:
            logging.error(f"Ошибка при создании заказа: {str(e)}")
            await message.answer(
                f"❌ Ошибка при создании заказа: {str(e)}",
                reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
            )
            await state.set_state(MenuState.SALES_MAIN)
        finally:
            db.close()
    elif response == "❌ Отменить":
        # Отменяем заказ
        await message.answer(
            "❌ Заказ отменен",
            reply_markup=get_menu_keyboard(MenuState.SALES_MAIN)
        )
        await state.set_state(MenuState.SALES_MAIN)
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
        
        # Запрашиваем количество клея
        # Проверяем наличие клея в базе
        db = next(get_db())
        try:
            glue = db.query(Glue).first()
            available = glue.quantity if glue else 0
            
            await message.answer(
                f"Введите количество клея (доступно: {available} тюбиков):",
                reply_markup=get_menu_keyboard(MenuState.SALES_CREATE_ORDER)
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