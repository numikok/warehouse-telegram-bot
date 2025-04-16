import json
import logging
from typing import List, Dict, Any, Optional, Union, Tuple
from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import func

from models import User, UserRole, Film, Panel, Joint, Glue, FinishedProduct, Operation, JointType, Order, OrderStatus, ProductionOrder
from database import get_db
from navigation import MenuState, get_menu_keyboard, go_back, get_back_keyboard, get_cancel_keyboard
from states import ProductionStates
from utils import check_production_access, get_role_menu_keyboard
from handlers.sales import handle_warehouse_order, handle_stock

logging.basicConfig(level=logging.INFO)

router = Router()

class ProductionStates(StatesGroup):
    # Состояния для прихода пустых панелей
    waiting_for_panel_quantity = State()
    
    # Состояния для прихода пленки
    waiting_for_film_color = State()
    waiting_for_film_code = State()
    waiting_for_film_quantity = State()
    waiting_for_film_meters = State()
    waiting_for_film_thickness = State()
    waiting_for_roll_count = State()
    waiting_for_roll_length = State()
    waiting_for_panel_consumption = State()
    
    # Состояния для прихода стыков
    waiting_for_joint_type = State()
    waiting_for_joint_color = State()
    waiting_for_joint_thickness = State()
    waiting_for_joint_quantity = State()
    
    # Состояния для прихода клея
    waiting_for_glue_quantity = State()
    
    # Состояния для производства
    waiting_for_production_film_color = State()
    waiting_for_production_quantity = State()

    # Состояния для управления заказами
    waiting_for_order_id_to_complete = State()

    # Состояния для учета брака
    waiting_for_defect_type = State()  # Выбор типа брака (панель/пленка/стык/клей)
    waiting_for_defect_joint_type = State()  # Тип стыка для брака
    waiting_for_defect_joint_color = State()  # Цвет стыка для брака
    waiting_for_defect_joint_thickness = State()  # Толщина стыка для брака
    waiting_for_defect_joint_quantity = State()  # Количество бракованных стыков
    waiting_for_defect_panel_quantity = State()  # Количество бракованных панелей
    waiting_for_defect_film_color = State()  # Цвет бракованной пленки
    waiting_for_defect_film_meters = State()  # Метраж бракованной пленки
    waiting_for_defect_glue_quantity = State()  # Количество бракованного клея

    # Новое состояние для обработки выбора наличия дополнительных метров
    waiting_for_extra_meters_choice = State()
    waiting_for_loose_meters = State()

async def check_production_access(message: Message) -> bool:
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or (user.role != UserRole.PRODUCTION and user.role != UserRole.SUPER_ADMIN):
            await message.answer("У вас нет прав для выполнения этой команды.")
            return False
        return True
    finally:
        db.close()

def get_joint_type_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Бабочка")],
            [KeyboardButton(text="Простой")],
            [KeyboardButton(text="Замыкающий")],
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

def get_roll_length_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="200")],
            [KeyboardButton(text="150")],
            [KeyboardButton(text="350")],
            [KeyboardButton(text="◀️ Назад")]
        ],
        resize_keyboard=True
    )

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    if not await check_production_access(message):
        return
    
    await state.set_state(MenuState.PRODUCTION_MAIN)
    await message.answer(
        "Выберите действие:",
        reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MAIN)
    )

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

@router.message(F.text == "📥 Приход сырья")
async def handle_materials_income(message: Message, state: FSMContext):
    if not await check_production_access(message):
        return
    
    await state.set_state(MenuState.PRODUCTION_MATERIALS)
    await message.answer(
        "Выберите тип материала:",
        reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MATERIALS)
    )

# Обработка брака
@router.message(F.text == "🚫 Брак")
async def handle_defect(message: Message, state: FSMContext):
    logging.info("Нажата кнопка 'Брак'")
    
    if not await check_production_access(message):
        logging.warning("Отказано в доступе к функциональности брака")
        return
    
    # Сбрасываем любые предыдущие данные в состоянии, которые могли остаться
    await state.clear()
    
    logging.info("Устанавливаю состояние waiting_for_defect_type")
    await state.set_state(ProductionStates.waiting_for_defect_type)
    
    # Формируем клавиатуру для выбора типа брака
    keyboard = get_menu_keyboard(MenuState.PRODUCTION_DEFECT)
    logging.info(f"Сформирована клавиатура брака: {keyboard}")
    
    await message.answer(
        "Выберите тип брака:",
        reply_markup=keyboard
    )

# Специальный обработчик для брака панелей - перемещен выше для приоритета
@router.message(ProductionStates.waiting_for_defect_type, F.text == "🪵 Панель")
async def handle_panel_defect(message: Message, state: FSMContext):
    logging.info("Специальный обработчик для брака панелей вызван")
    
    # Проверяем, что мы действительно находимся в состоянии ожидания типа брака
    current_state = await state.get_state()
    logging.info(f"Текущее состояние в handle_panel_defect: {current_state}")
    
    db = next(get_db())
    try:
        # Получаем текущий остаток панелей
        panel = db.query(Panel).first()
        if not panel or panel.quantity <= 0:
            logging.warning("В базе нет панелей")
            await message.answer(
                "В базе нет панелей.",
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MAIN)
            )
            return
        
        logging.info(f"Установка waiting_for_defect_panel_quantity, доступно панелей: {panel.quantity}")
        await message.answer(
            f"Введите количество бракованных панелей:\n\nДоступно: {panel.quantity} шт.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="◀️ Назад")]],
                resize_keyboard=True
            )
        )
    finally:
        db.close()
    
    # Четко указываем, что это панель для дефекта
    await state.update_data(defect_type="panel_defect")
    await state.set_state(ProductionStates.waiting_for_defect_panel_quantity)
    logging.info("Состояние изменено на waiting_for_defect_panel_quantity")

# Обработка прихода пустых панелей
@router.message(F.text == "🪵 Панель")
async def handle_panel(message: Message, state: FSMContext):
    if not await check_production_access(message):
        return
    
    # Проверяем, что мы находимся в состоянии добавления материалов
    current_state = await state.get_state()
    logging.info(f"Нажата кнопка 'Панель' в handle_panel, текущее состояние: {current_state}")
    
    # Если мы в меню выбора типа брака, пропускаем эту обработку
    if current_state == ProductionStates.waiting_for_defect_type:
        logging.info("Пропускаем обработку в handle_panel, так как находимся в меню брака")
        return
    
    # Если мы не в меню материалов, пропускаем обработку
    if current_state != MenuState.PRODUCTION_MATERIALS:
        logging.info(f"Пропускаем обработку, так как не в режиме добавления материалов")
        return
    
    # Запрашиваем количество пустых панелей
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="◀️ Назад")]],
        resize_keyboard=True
    )
    
    await message.answer(
        "Введите количество пустых панелей:",
        reply_markup=keyboard
    )
    
    await state.update_data(operation_type="panel_income") # Указываем тип операции явно
    await state.set_state(ProductionStates.waiting_for_panel_quantity)

@router.message(ProductionStates.waiting_for_panel_quantity)
async def process_panel_quantity(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.set_state(MenuState.PRODUCTION_MATERIALS)
        keyboard = await get_role_menu_keyboard(MenuState.PRODUCTION_MATERIALS, message, state)
        await message.answer("Выберите тип материала:", reply_markup=keyboard)
        return
    
    try:
        quantity = int(message.text.strip())
        if quantity <= 0:
            await message.answer("Количество панелей должно быть положительным числом.")
            return
        
        # Проверяем, что мы в правильном контексте обработки прихода
        data = await state.get_data()
        operation_type = data.get("operation_type", "")
        if operation_type != "panel_income":
            logging.warning(f"Неправильный тип операции: {operation_type}")
            await message.answer("Произошла ошибка. Пожалуйста, начните процесс заново.")
            await state.set_state(MenuState.PRODUCTION_MAIN)
            return
            
        db = next(get_db())
        try:
            # Получаем пользователя из базы данных
            user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
            
            # Получаем текущий запас панелей
            panel = db.query(Panel).first()
            
            if not panel:
                # Если записи о панелях еще нет, создаем ее
                panel = Panel(quantity=quantity)
                db.add(panel)
                previous_quantity = 0
            else:
                # Иначе обновляем существующую запись
                previous_quantity = panel.quantity
                panel.quantity += quantity
            
            # Создаем запись об операции
            operation = Operation(
                user_id=user.id,
                operation_type="panel_income",
                quantity=quantity,
                details=json.dumps({
                    "previous_quantity": previous_quantity,
                    "new_quantity": panel.quantity,
                    "is_income": True  # Указываем, что это операция прихода
                })
            )
            
            # Добавляем операцию в базу данных
            db.add(operation)
            
            # Сохраняем изменения
            db.commit()
            
            # Возвращаемся в меню материалов с учетом контекста админа
            await state.set_state(MenuState.PRODUCTION_MATERIALS)
            keyboard = await get_role_menu_keyboard(MenuState.PRODUCTION_MATERIALS, message, state)
            
            await message.answer(
                f"✅ Приход панелей зарегистрирован!\n"
                f"Количество: {quantity} шт.\n"
                f"Предыдущий остаток: {previous_quantity} шт.\n"
                f"Текущий остаток: {panel.quantity} шт.",
                reply_markup=keyboard
            )
        finally:
            db.close()
    except ValueError:
        await message.answer("Пожалуйста, введите целое число.")

# Специальный обработчик для брака стыков
@router.message(ProductionStates.waiting_for_defect_type, F.text == "⚙️ Стык")
async def handle_joint_defect(message: Message, state: FSMContext):
    logging.info("Специальный обработчик для брака стыков вызван")
    
    db = next(get_db())
    try:
        # Получаем все доступные стыки
        joints = db.query(Joint).all()
        if not joints:
            logging.warning("В базе нет стыков")
            await message.answer(
                "В базе нет стыков.",
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MAIN)
            )
            return
        
        # Создаем словарь для группировки стыков по типу, цвету и толщине
        joint_info = {}
        for joint in joints:
            joint_type_name = {
                JointType.BUTTERFLY: "Бабочка",
                JointType.SIMPLE: "Простой", 
                JointType.CLOSING: "Замыкающий"
            }[joint.type]
            
            key = f"{joint_type_name} - {joint.color} - {joint.thickness} мм"
            joint_info[key] = joint.quantity
        
        # Формируем список доступных стыков
        joints_info = [f"- {key} (остаток: {qty} шт.)" for key, qty in joint_info.items()]
        
        if joints_info:
            await message.answer(
                "Выберите тип бракованного стыка:\n\nДоступные варианты:\n" + "\n".join(joints_info),
                reply_markup=get_joint_type_keyboard()
            )
        else:
            await message.answer(
                "В базе нет стыков с положительным остатком.",
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MAIN)
            )
            return
    finally:
        db.close()
    
    await state.update_data(defect_type="joint")
    await state.set_state(ProductionStates.waiting_for_defect_joint_type)


# Специальный обработчик для брака клея
@router.message(ProductionStates.waiting_for_defect_type, F.text == "🧴 Клей")
async def handle_glue_defect(message: Message, state: FSMContext):
    logging.info("Специальный обработчик для брака клея вызван")
    
    db = next(get_db())
    try:
        # Получаем текущий остаток клея
        glue = db.query(Glue).first()
        if not glue or glue.quantity <= 0:
            logging.warning("В базе нет клея")
            await message.answer(
                "В базе нет клея.",
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MAIN)
            )
            return
        
        await message.answer(
            f"Введите количество бракованного клея (в штуках):\n\nДоступно: {glue.quantity} шт.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="◀️ Назад")]],
                resize_keyboard=True
            )
        )
    finally:
        db.close()
    
    await state.update_data(defect_type="glue")
    await state.set_state(ProductionStates.waiting_for_defect_glue_quantity)

# Обработка прихода пленки
@router.message(F.text == "🎨 Пленка")
async def handle_film(message: Message, state: FSMContext):
    if not await check_production_access(message):
        return
    
    # Проверяем, что мы находимся в состоянии добавления материалов
    current_state = await state.get_state()
    logging.info(f"Нажата кнопка 'Пленка', текущее состояние: {current_state}")
    
    # Если мы в меню выбора типа брака, пропускаем эту обработку
    if current_state == ProductionStates.waiting_for_defect_type:
        logging.info("Пропускаем обработку в handle_film, так как находимся в меню брака. Будет вызван handle_film_defect.")
        return
    
    # Если мы не в меню материалов, пропускаем обработку
    if current_state != MenuState.PRODUCTION_MATERIALS:
        logging.info(f"Пропускаем обработку, так как не в режиме добавления материалов")
        return
        
    # Запрашиваем код пленки
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="◀️ Назад")]],
        resize_keyboard=True
    )
    
    # Получаем список существующих пленок
    db = next(get_db())
    try:
        # Получаем список доступных пленок
        films = db.query(Film).all()
        
        # Формируем список пленок, если они есть
        film_info_text = ""
        if films:
            film_info = []
            for film in films:
                panel_count = film.calculate_possible_panels()
                film_info.append(
                    f"- {film.code}: {film.total_remaining:.2f}м (хватит на ~{panel_count} панелей)"
                )
            film_info_text = "\n\nИмеющиеся пленки:\n" + "\n".join(film_info)
        
        await message.answer(
            f"Введите код пленки, которую хотите добавить:{film_info_text}",
            reply_markup=keyboard
        )
        
        await state.set_state(ProductionStates.waiting_for_film_code)
    finally:
        db.close()

@router.message(ProductionStates.waiting_for_film_code)
async def process_film_code(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.set_state(MenuState.PRODUCTION_MATERIALS)
        keyboard = await get_role_menu_keyboard(MenuState.PRODUCTION_MATERIALS, message, state)
        await message.answer("Выберите тип материала:", reply_markup=keyboard)
        return
    
    film_code = message.text.strip()
    
    db = next(get_db())
    try:
        # Проверяем существование пленки
        film = db.query(Film).filter(Film.code == film_code).first()
        
        # Если пленки с таким кодом нет, создаем новую запись
        if not film:
            # Создаем новую запись пленки с указанным кодом и нулевым остатком
            # НЕ указываем значения по умолчанию - они будут заданы пользователем
            film = Film(
                code=film_code,
                total_remaining=0.0     # Только нулевой остаток для начала
            )
            db.add(film)
            db.commit()
            
            # Уведомляем, что добавлен новый цвет
            await message.answer(
                f"👍 Добавлен новый цвет пленки: {film_code}"
            )
        
        # Сохраняем код пленки
        await state.update_data(film_code=film_code)
        
        # Запрашиваем количество рулонов
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Назад")]],
            resize_keyboard=True
        )
        
        await message.answer(
            f"Введите количество рулонов пленки {film_code}:",
            reply_markup=keyboard
        )
        
        await state.set_state(ProductionStates.waiting_for_film_quantity)
    finally:
        db.close()

@router.message(ProductionStates.waiting_for_film_quantity)
async def process_film_quantity(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await handle_film(message, state)
        return
    
    try:
        quantity = float(message.text.strip())
        if quantity <= 0:
            await message.answer("Количество должно быть положительным числом.")
            return
        
        # Сохраняем количество рулонов
        await state.update_data(film_quantity=quantity)
        
        # Спрашиваем, есть ли дополнительные метры
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Да")],
                [KeyboardButton(text="Нет")],
                [KeyboardButton(text="◀️ Назад")]
            ],
            resize_keyboard=True
        )
        
        await message.answer(
            f"Вы указали {quantity} рулонов пленки. Есть ли дополнительные метры (не целые рулоны)?",
            reply_markup=keyboard
        )
        
        # Новое состояние для выбора наличия дополнительных метров
        await state.set_state(ProductionStates.waiting_for_extra_meters_choice)
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число.")

# Новое состояние для обработки выбора наличия дополнительных метров
@router.message(ProductionStates.waiting_for_extra_meters_choice)
async def process_extra_meters_choice(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        # Возвращаемся к вводу количества рулонов
        data = await state.get_data()
        film_code = data.get('film_code')
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Назад")]],
            resize_keyboard=True
        )
        
        await message.answer(
            f"Введите количество рулонов пленки {film_code}:",
            reply_markup=keyboard
        )
        
        await state.set_state(ProductionStates.waiting_for_film_quantity)
        return
    
    if message.text == "Да":
        # Запрашиваем количество дополнительных метров
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Назад")]],
            resize_keyboard=True
        )
        
        await message.answer(
            "Введите количество дополнительных метров пленки:",
            reply_markup=keyboard
        )
        
        await state.set_state(ProductionStates.waiting_for_loose_meters)
    elif message.text == "Нет":
        # Переходим к вводу метража в рулоне
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Назад")]],
            resize_keyboard=True
        )
        
        await message.answer(
            "Введите метраж одного рулона (например, 50):",
            reply_markup=keyboard
        )
        
        # Сохраняем 0 дополнительных метров
        await state.update_data(loose_meters=0)
        await state.set_state(ProductionStates.waiting_for_film_meters)
    else:
        await message.answer("Пожалуйста, выберите 'Да' или 'Нет'")

# Новое состояние для ввода дополнительных метров
@router.message(ProductionStates.waiting_for_loose_meters)
async def process_loose_meters(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        # Возвращаемся к выбору наличия дополнительных метров
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Да")],
                [KeyboardButton(text="Нет")],
                [KeyboardButton(text="◀️ Назад")]
            ],
            resize_keyboard=True
        )
        
        data = await state.get_data()
        quantity = data.get('film_quantity')
        
        await message.answer(
            f"Вы указали {quantity} рулонов пленки. Есть ли дополнительные метры (не целые рулоны)?",
            reply_markup=keyboard
        )
        
        await state.set_state(ProductionStates.waiting_for_extra_meters_choice)
        return
    
    try:
        loose_meters = float(message.text.strip())
        if loose_meters < 0:
            await message.answer("Количество метров не может быть отрицательным.")
            return
        
        # Сохраняем количество дополнительных метров
        await state.update_data(loose_meters=loose_meters)
        
        # Переходим к вводу метража в рулоне
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Назад")]],
            resize_keyboard=True
        )
        
        await message.answer(
            "Введите метраж одного рулона (например, 50):",
            reply_markup=keyboard
        )
        
        await state.set_state(ProductionStates.waiting_for_film_meters)
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число.")

@router.message(ProductionStates.waiting_for_film_meters)
async def process_film_meters(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        # Проверяем, откуда мы пришли - с дополнительными метрами или без
        data = await state.get_data()
        if "loose_meters" in data:
            # Если есть параметр loose_meters, значит пришли после его ввода
            keyboard = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="◀️ Назад")]],
                resize_keyboard=True
            )
            
            await message.answer(
                "Введите количество дополнительных метров пленки:",
                reply_markup=keyboard
            )
            
            await state.set_state(ProductionStates.waiting_for_loose_meters)
        else:
            # Иначе возвращаемся к вопросу о наличии дополнительных метров
            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="Да")],
                    [KeyboardButton(text="Нет")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
            
            film_quantity = data.get('film_quantity')
            
            await message.answer(
                f"Вы указали {film_quantity} рулонов пленки. Есть ли дополнительные метры (не целые рулоны)?",
                reply_markup=keyboard
            )
            
            await state.set_state(ProductionStates.waiting_for_extra_meters_choice)
        
        return
    
    try:
        meters = float(message.text.strip())
        if meters <= 0:
            await message.answer("Количество метров должно быть положительным числом.")
            return
        
        data = await state.get_data()
        film_color = data.get('defect_film_color')
        
        db = next(get_db())
        try:
            # Получаем пользователя из базы данных
            user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
            
            # Получаем пленку из базы данных
            film = db.query(Film).filter(Film.code == film_color).first()
            
            if not film:
                await message.answer(f"Ошибка: пленка с цветом {film_color} не найдена в базе данных.")
                return
            
            # Если указано больше метров, чем есть в наличии, сообщаем об этом
            if meters > film.total_remaining:
                await message.answer(
                    f"❗ Внимание: вы указали {meters} м брака, но в наличии всего {film.total_remaining:.1f} м пленки."
                )
            
            # Учитываем брак
            previous_remaining = film.total_remaining
            film.total_remaining = max(0, film.total_remaining - meters)
            
            # Создаем запись об операции
            operation = Operation(
                user_id=user.id,
                operation_type="film_defect",
                quantity=meters,
                details=json.dumps({
                    "film_color": film_color,
                    "previous_remaining": previous_remaining,
                    "new_remaining": film.total_remaining
                })
            )
            
            # Добавляем операцию в базу данных
            db.add(operation)
            
            # Сохраняем изменения
            db.commit()
            
            # Возвращаемся в меню брака
            keyboard = await get_role_menu_keyboard(MenuState.PRODUCTION_MAIN, message, state)
            
            await message.answer(
                f"✅ Брак учтен!\n"
                f"Пленка: {film_color}\n"
                f"Списано: {meters} м\n"
                f"Осталось: {film.total_remaining:.1f} м",
                reply_markup=keyboard
            )
            
            # Сбрасываем состояние
            await state.set_state(MenuState.PRODUCTION_MAIN)
        finally:
            db.close()
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число.")

@router.message(ProductionStates.waiting_for_defect_glue_quantity)
async def process_defect_glue_quantity(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await message.answer(
            "Выберите тип брака:",
            reply_markup=get_menu_keyboard(MenuState.PRODUCTION_DEFECT)
        )
        await state.set_state(ProductionStates.waiting_for_defect_type)
        return

    try:
        quantity = int(message.text)
        if quantity <= 0:
            await message.answer("Количество должно быть положительным числом.")
            return
        
        db = next(get_db())
        try:
            glue = db.query(Glue).first()
            if not glue:
                await message.answer("В базе нет клея.")
                return
            
            if glue.quantity < quantity:
                await message.answer(
                    f"Невозможно списать {quantity} шт. клея, доступно только {glue.quantity}."
                )
                return
            
            # Получаем пользователя из базы данных
            user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
            
            # Создаем запись операции
            operation = Operation(
                user_id=user.id,
                operation_type="glue_defect",
                quantity=quantity,
                details=json.dumps({
                    "previous_quantity": glue.quantity
                })
            )
            db.add(operation)
            
            # Уменьшаем количество клея
            glue.quantity -= quantity
            db.commit()
            
            await message.answer(
                f"✅ Списано {quantity} шт. бракованного клея\n"
                f"Остаток: {glue.quantity} шт.",
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MAIN)
            )
            
        finally:
            db.close()
            
    except ValueError:
        await message.answer("Пожалуйста, введите целое число.")
        return
    
    await state.clear()

@router.message(F.text == "📝 Заказать производство")
async def button_order_production(message: Message, state: FSMContext):
    await handle_stock(message, state)

@router.message(F.text == "📦 Заказать на склад")
async def button_order_warehouse(message: Message, state: FSMContext):
    await handle_warehouse_order(message, state)

@router.message(F.text == "📦 Мои заказы")
async def handle_my_production_orders(message: Message, state: FSMContext):
    if not await check_production_access(message):
        return
    
    await state.set_state(MenuState.PRODUCTION_ORDERS)
    
    db = next(get_db())
    try:
        # Получаем все заказы, сортированные по статусу и дате создания
        orders = (
            db.query(ProductionOrder)
            .order_by(
                ProductionOrder.status.asc(),  # Сначала new, потом completed
                ProductionOrder.created_at.desc()
            )
            .all()
        )
        
        if not orders:
            await message.answer(
                "Нет текущих или выполненных заказов на производство.",
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION)
            )
            return
        
        # Группируем заказы по статусу
        new_orders = []
        completed_orders = []
        
        for order in orders:
            if order.status == "new":
                new_orders.append(order)
            elif order.status == "completed":
                completed_orders.append(order)
        
        # Формируем сообщение со списком заказов
        response = "📋 Заказы на производство:\n\n"
        
        # Новые заказы
        if new_orders:
            response += "🆕 НОВЫЕ ЗАКАЗЫ:\n"
            for order in new_orders:
                response += (
                    f"Заказ #{order.id}\n"
                    f"Дата создания: {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                    f"Менеджер: {order.manager.username}\n"
                    f"Детали:\n"
                    f"- Код пленки: {order.film_color}\n"
                    f"- Количество панелей: {order.panel_quantity}\n\n"
                )
        
        # Выполненные заказы (последние 5)
        if completed_orders:
            response += "✅ ВЫПОЛНЕННЫЕ ЗАКАЗЫ (последние 5):\n"
            for order in completed_orders[:5]:
                completion_date = order.completed_at.strftime('%d.%m.%Y %H:%M') if order.completed_at else "Нет данных"
                response += (
                    f"Заказ #{order.id}\n"
                    f"Дата создания: {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                    f"Дата выполнения: {completion_date}\n"
                    f"Менеджер: {order.manager.username}\n"
                    f"Детали:\n"
                    f"- Код пленки: {order.film_color}\n"
                    f"- Количество панелей: {order.panel_quantity}\n\n"
                )
        
        await message.answer(
            response,
            reply_markup=get_menu_keyboard(MenuState.PRODUCTION)
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

@router.message(ProductionStates.waiting_for_panel_consumption)
async def process_panel_consumption(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.set_state(ProductionStates.waiting_for_film_color)
        await message.answer("Введите код (цвет) пленки:")
        return
    
    try:
        # Parse the panel quantity
        quantity = float(message.text.strip())
        if quantity <= 0:
            await message.answer("Количество панелей должно быть положительным числом.")
            return
        
        # Get data from state
        data = await state.get_data()
        film_color = data.get("film_color")
        
        # Ask for loose meters
        await message.answer(
            "Введите количество неполных метров (только цифра, без текста):",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="◀️ Назад")]],
                resize_keyboard=True
            )
        )
        await state.update_data(panel_quantity=quantity)
        await state.set_state(ProductionStates.waiting_for_loose_meters)
        
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число панелей.")

@router.message(ProductionStates.waiting_for_loose_meters)
async def process_loose_meters(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.set_state(ProductionStates.waiting_for_panel_consumption)
        await message.answer("Введите количество панелей:")
        return
    
    try:
        # Parse the loose meters
        loose_meters = float(message.text.strip())
        if loose_meters < 0:
            await message.answer("Количество неполных метров не может быть отрицательным.")
            return
        
        # Get data from state
        data = await state.get_data()
        film_color = data.get("film_color")
        panel_quantity = data.get("panel_quantity")
        
        # Calculate total meters: panel_quantity * 6 + loose_meters
        total_meters = panel_quantity * 6 + loose_meters
        
        db = next(get_db())
        try:
            # Get film from database
            film = db.query(Film).filter(Film.code == film_color).first()
            
            if not film:
                await message.answer(f"Пленка с цветом '{film_color}' не найдена.")
                return
            
            if film.total_remaining < total_meters:
                await message.answer(
                    f"Невозможно списать {total_meters:.1f} метров пленки, доступно только {film.total_remaining:.1f}."
                )
                return
            
            # Get user from database
            user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
            
            # Create operation record
            operation = Operation(
                user_id=user.id,
                operation_type="film_consumption",
                quantity=total_meters,
                details=json.dumps({
                    "film_code": film_color,
                    "panel_quantity": panel_quantity,
                    "loose_meters": loose_meters,
                    "total_meters": total_meters,
                    "previous_remaining": film.total_remaining
                })
            )
            db.add(operation)
            
            # Update film remaining quantity
            film.total_remaining -= total_meters
            db.commit()
            
            await message.answer(
                f"✅ Списано {total_meters:.1f} метров пленки цвета {film_color}\n"
                f"Панелей: {panel_quantity}\n"
                f"Неполных метров: {loose_meters}\n"
                f"Остаток: {film.total_remaining:.1f} м",
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MAIN)
            )
            
            # Reset state
            await state.clear()
            
        finally:
            db.close()
            
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число для неполных метров.")

@router.message(ProductionStates.waiting_for_defect_film_meters)
async def process_defect_film_meters(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        # Возвращаемся к вводу цвета пленки
        await message.answer(
            "Выберите тип брака:",
            reply_markup=get_menu_keyboard(MenuState.PRODUCTION_DEFECT)
        )
        await state.set_state(ProductionStates.waiting_for_defect_type)
        return
    
    try:
        meters = float(message.text.strip())
        if meters <= 0:
            await message.answer("Количество метров должно быть положительным числом.")
            return
        
        # Достаем сохраненные данные из состояния
        data = await state.get_data()
        film_color = data.get("defect_film_color")
        
        db = next(get_db())
        try:
            # Получаем пленку из базы данных
            film = db.query(Film).filter(Film.code == film_color).first()
            
            if not film:
                await message.answer(f"Пленка с цветом '{film_color}' не найдена.")
                return
            
            if film.total_remaining < meters:
                await message.answer(
                    f"Невозможно списать {meters} метров пленки, доступно только {film.total_remaining:.1f}."
                )
                return
            
            # Получаем пользователя из базы данных
            user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
            
            # Создаем запись операции
            operation = Operation(
                user_id=user.id,
                operation_type="film_defect",
                quantity=meters,
                details=json.dumps({
                    "film_code": film_color,
                    "previous_remaining": film.total_remaining
                })
            )
            db.add(operation)
            
            # Уменьшаем количество пленки
            film.total_remaining -= meters
            db.commit()
            
            await message.answer(
                f"✅ Списано {meters} метров бракованной пленки цвета {film_color}\n"
                f"Остаток: {film.total_remaining:.1f} м",
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MAIN)
            )
            
            # Сбрасываем состояние
            await state.clear()
            
        finally:
            db.close()
            
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число.")
        return 