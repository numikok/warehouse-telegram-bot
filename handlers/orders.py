from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_db
from models import User, Film, Joint, JointType, Order, OrderStatus, UserRole, Operation
from sqlalchemy import select
import json

router = Router()

class OrderStates(StatesGroup):
    waiting_for_film_code = State()
    waiting_for_panel_quantity = State()
    waiting_for_joint_type = State()
    waiting_for_joint_color = State()
    waiting_for_joint_quantity = State()
    waiting_for_glue_quantity = State()
    waiting_for_installation = State()
    waiting_for_phone = State()
    waiting_for_address = State()

@router.message(F.text == "📝 Создать заказ")
async def start_order(message: Message, state: FSMContext):
    db = next(get_db())
    try:
        # Получаем список доступных пленок
        films = db.query(Film).all()
        film_codes = [film.code for film in films]
        
        if not film_codes:
            await message.answer("❌ Нет доступных пленок в базе данных.")
            return
            
        # Создаем клавиатуру с кодами пленок
        keyboard = []
        for code in film_codes:
            keyboard.append([KeyboardButton(text=code)])
        keyboard.append([KeyboardButton(text="◀️ Назад")])
        
        await message.answer(
            "Выберите код пленки из списка:",
            reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
        )
        await state.set_state(OrderStates.waiting_for_film_code)
    finally:
        db.close()

@router.message(OrderStates.waiting_for_film_code)
async def process_film_code(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        # Возврат в главное меню
        await message.answer(
            "Выберите действие:",
            reply_markup=get_main_keyboard()  # Нужно импортировать или создать эту функцию
        )
        await state.clear()
        return
        
    db = next(get_db())
    try:
        # Проверяем существование пленки
        film = db.query(Film).filter(Film.code == message.text).first()
        if not film:
            await message.answer("❌ Пленка с таким кодом не найдена. Пожалуйста, выберите код из списка.")
            return
            
        await state.update_data(film_code=message.text)
        await message.answer(
            "Введите количество панелей:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="◀️ Назад")]],
                resize_keyboard=True
            )
        )
        await state.set_state(OrderStates.waiting_for_panel_quantity)
    finally:
        db.close()

@router.message(OrderStates.waiting_for_panel_quantity)
async def process_panel_quantity(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await start_order(message, state)
        return
        
    try:
        quantity = int(message.text)
        if quantity <= 0:
            await message.answer("❌ Количество панелей должно быть положительным числом.")
            return
            
        await state.update_data(panel_quantity=quantity)
        
        # Создаем клавиатуру с типами стыков
        keyboard = []
        for joint_type in JointType:
            keyboard.append([KeyboardButton(text=f"{joint_type.value.capitalize()}")])
        keyboard.append([KeyboardButton(text="◀️ Назад")])
        
        await message.answer(
            "Выберите тип стыка:",
            reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
        )
        await state.set_state(OrderStates.waiting_for_joint_type)
    except ValueError:
        await message.answer("❌ Пожалуйста, введите целое число.")

@router.message(OrderStates.waiting_for_joint_type)
async def process_joint_type(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        data = await state.get_data()
        await message.answer(f"Введите количество панелей:")
        await state.set_state(OrderStates.waiting_for_panel_quantity)
        return
        
    joint_type = message.text.lower()
    if joint_type not in [jt.value for jt in JointType]:
        await message.answer("❌ Пожалуйста, выберите тип стыка из списка.")
        return
        
    await state.update_data(joint_type=joint_type)
    
    db = next(get_db())
    try:
        # Получаем список доступных цветов стыков выбранного типа
        joints = db.query(Joint).filter(Joint.type == JointType(joint_type)).all()
        joint_colors = [joint.color for joint in joints]
        
        if not joint_colors:
            await message.answer("❌ Нет доступных стыков выбранного типа.")
            return
            
        # Создаем клавиатуру с цветами стыков
        keyboard = []
        for color in joint_colors:
            keyboard.append([KeyboardButton(text=f"{color} ({joint_type})")])
        keyboard.append([KeyboardButton(text="◀️ Назад")])
        
        await message.answer(
            "Выберите цвет стыка:",
            reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
        )
        await state.set_state(OrderStates.waiting_for_joint_color)
    finally:
        db.close()

@router.message(OrderStates.waiting_for_joint_color)
async def process_joint_color(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        # Возвращаемся к выбору типа стыка
        keyboard = []
        for joint_type in JointType:
            keyboard.append([KeyboardButton(text=f"{joint_type.value.capitalize()}")])
        keyboard.append([KeyboardButton(text="◀️ Назад")])
        
        await message.answer(
            "Выберите тип стыка:",
            reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
        )
        await state.set_state(OrderStates.waiting_for_joint_type)
        return
        
    # Извлекаем цвет из сообщения (убираем тип стыка в скобках)
    color = message.text.split(" (")[0]
    
    data = await state.get_data()
    joint_type = data.get("joint_type")
    
    db = next(get_db())
    try:
        # Проверяем существование стыка
        joint = db.query(Joint).filter(
            Joint.type == JointType(joint_type),
            Joint.color == color
        ).first()
        
        if not joint:
            await message.answer("❌ Стык с таким цветом не найден. Пожалуйста, выберите цвет из списка.")
            return
            
        await state.update_data(joint_color=color)
        await message.answer(
            "Введите количество стыков:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="◀️ Назад")]],
                resize_keyboard=True
            )
        )
        await state.set_state(OrderStates.waiting_for_joint_quantity)
    finally:
        db.close()

@router.message(OrderStates.waiting_for_joint_quantity)
async def process_joint_quantity(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        data = await state.get_data()
        joint_type = data.get("joint_type")
        
        db = next(get_db())
        try:
            # Получаем список доступных цветов стыков выбранного типа
            joints = db.query(Joint).filter(Joint.type == JointType(joint_type)).all()
            joint_colors = [joint.color for joint in joints]
            
            # Создаем клавиатуру с цветами стыков
            keyboard = []
            for color in joint_colors:
                keyboard.append([KeyboardButton(text=f"{color} ({joint_type})")])
            keyboard.append([KeyboardButton(text="◀️ Назад")])
            
            await message.answer(
                "Выберите цвет стыка:",
                reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
            )
            await state.set_state(OrderStates.waiting_for_joint_color)
        finally:
            db.close()
        return
        
    try:
        quantity = int(message.text)
        if quantity <= 0:
            await message.answer("❌ Количество стыков должно быть положительным числом.")
            return
            
        await state.update_data(joint_quantity=quantity)
        await message.answer(
            "Введите количество клея (в тюбиках):",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="◀️ Назад")]],
                resize_keyboard=True
            )
        )
        await state.set_state(OrderStates.waiting_for_glue_quantity)
    except ValueError:
        await message.answer("❌ Пожалуйста, введите целое число.")

@router.message(OrderStates.waiting_for_glue_quantity)
async def process_glue_quantity(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await message.answer("Введите количество стыков:")
        await state.set_state(OrderStates.waiting_for_joint_quantity)
        return
        
    try:
        quantity = int(message.text)
        if quantity <= 0:
            await message.answer("❌ Количество клея должно быть положительным числом.")
            return
            
        await state.update_data(glue_quantity=quantity)
        
        # Создаем клавиатуру для выбора монтажа
        keyboard = [
            [KeyboardButton(text="Да")],
            [KeyboardButton(text="Нет")],
            [KeyboardButton(text="◀️ Назад")]
        ]
        
        await message.answer(
            "Требуется монтаж?",
            reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
        )
        await state.set_state(OrderStates.waiting_for_installation)
    except ValueError:
        await message.answer("❌ Пожалуйста, введите целое число.")

@router.message(OrderStates.waiting_for_installation)
async def process_installation(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await message.answer("Введите количество клея (в тюбиках):")
        await state.set_state(OrderStates.waiting_for_glue_quantity)
        return
        
    if message.text not in ["Да", "Нет"]:
        await message.answer("❌ Пожалуйста, выберите 'Да' или 'Нет'.")
        return
        
    await state.update_data(installation_required=(message.text == "Да"))
    await message.answer(
        "Введите номер телефона клиента:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Назад")]],
            resize_keyboard=True
        )
    )
    await state.set_state(OrderStates.waiting_for_phone)

@router.message(OrderStates.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        keyboard = [
            [KeyboardButton(text="Да")],
            [KeyboardButton(text="Нет")],
            [KeyboardButton(text="◀️ Назад")]
        ]
        await message.answer(
            "Требуется монтаж?",
            reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
        )
        await state.set_state(OrderStates.waiting_for_installation)
        return
        
    # Здесь можно добавить валидацию номера телефона
    await state.update_data(customer_phone=message.text)
    await message.answer(
        "Введите адрес доставки:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Назад")]],
            resize_keyboard=True
        )
    )
    await state.set_state(OrderStates.waiting_for_address)

@router.message(OrderStates.waiting_for_address)
async def process_address(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await message.answer("Введите номер телефона клиента:")
        await state.set_state(OrderStates.waiting_for_phone)
        return
        
    await state.update_data(delivery_address=message.text)
    data = await state.get_data()
    
    db = next(get_db())
    try:
        # Получаем пользователя из базы данных
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            await message.answer("❌ Ошибка: Пользователь не найден в базе данных.")
            return
            
        # Проверяем наличие готовой продукции
        film = db.query(Film).filter(Film.code == data["film_code"]).first()
        if not film:
            await message.answer("❌ Ошибка: Пленка не найдена в базе данных.")
            return
            
        possible_panels = film.calculate_possible_panels()
        if possible_panels < data["panel_quantity"]:
            await message.answer(
                f"❌ Недостаточно готовой продукции на складе.\n"
                f"Доступно панелей: {possible_panels}\n"
                f"Требуется: {data['panel_quantity']}"
            )
            return
        
        # Создаем новый заказ
        order = Order(
            manager_id=user.id,  # Используем внутренний ID пользователя
            film_code=data["film_code"],
            panel_quantity=data["panel_quantity"],
            joint_type=JointType(data["joint_type"]),
            joint_color=data["joint_color"],
            joint_quantity=data["joint_quantity"],
            glue_quantity=data["glue_quantity"],
            installation_required=data["installation_required"],
            customer_phone=data["customer_phone"],
            delivery_address=data["delivery_address"],
            status=OrderStatus.NEW
        )
        
        db.add(order)
        db.commit()
        
        # Создаем запись об операции
        operation = Operation(
            user_id=user.id,  # Используем внутренний ID пользователя
            operation_type="order",
            quantity=data["panel_quantity"],
            details=json.dumps({
                "order_id": order.id,  # Добавляем ID заказа в детали
                "film_code": data["film_code"],
                "panel_quantity": data["panel_quantity"],
                "joint_color": data["joint_color"],
                "joint_quantity": data["joint_quantity"],
                "glue_quantity": data["glue_quantity"],
                "installation": data["installation_required"],
                "phone": data["customer_phone"],
                "address": data["delivery_address"],
                "status": "new"
            }, ensure_ascii=False)  # Используем ensure_ascii=False для корректной работы с русскими символами
        )
        db.add(operation)
        db.commit()
        
        # Отправляем подтверждение менеджеру
        await message.answer(
            f"✅ Заказ успешно создан!\n\n"
            f"📋 Детали заказа:\n"
            f"Код пленки: {data['film_code']}\n"
            f"Количество панелей: {data['panel_quantity']}\n"
            f"Тип стыка: {data['joint_type'].capitalize()}\n"
            f"Цвет стыка: {data['joint_color']}\n"
            f"Количество стыков: {data['joint_quantity']}\n"
            f"Количество клея: {data['glue_quantity']}\n"
            f"Монтаж: {'Да' if data['installation_required'] else 'Нет'}\n"
            f"Телефон клиента: {data['customer_phone']}\n"
            f"Адрес доставки: {data['delivery_address']}\n\n"
            f"Номер заказа: {order.id}",
            reply_markup=get_main_keyboard()  # Возвращаемся в главное меню
        )
        
        # Отправляем уведомление складу
        await notify_warehouse_about_order(message.bot, order.id, data)
        
    except Exception as e:
        await message.answer(f"❌ Произошла ошибка при создании заказа: {str(e)}")
        # Добавляем логирование для отладки
        print(f"Error creating order: {str(e)}")
    finally:
        db.close()
        
    await state.clear()

async def notify_warehouse_about_order(bot, order_id: int, order_details: dict):
    """Отправляет уведомление складу о новом заказе."""
    db = next(get_db())
    try:
        # Получаем всех пользователей с ролью склада
        warehouse_users = db.query(User).filter(User.role == UserRole.WAREHOUSE).all()
        
        notification_text = (
            f"📦 Новый заказ #{order_id}\n\n"
            f"Детали заказа:\n"
            f"Код пленки: {order_details['film_code']}\n"
            f"Количество панелей: {order_details['panel_quantity']}\n"
            f"Тип стыка: {order_details['joint_type'].capitalize()}\n"
            f"Цвет стыка: {order_details['joint_color']}\n"
            f"Количество стыков: {order_details['joint_quantity']}\n"
            f"Количество клея: {order_details['glue_quantity']}\n"
            f"Монтаж: {'Да' if order_details['installation_required'] else 'Нет'}\n"
            f"Телефон клиента: {order_details['customer_phone']}\n"
            f"Адрес доставки: {order_details['delivery_address']}\n\n"
            f"Для подтверждения выполнения заказа перейдите в раздел 'Мои заказы'"
        )
        
        # Отправляем уведомление каждому складовщику
        for user in warehouse_users:
            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=notification_text
                )
            except Exception as e:
                print(f"Failed to send notification to warehouse user {user.telegram_id}: {e}")
    finally:
        db.close() 