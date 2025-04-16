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

# Специальный обработчик для брака панелей - перемещен выше для приоритета
@router.message(ProductionStates.waiting_for_defect_type, F.text == "🪵 Панель")
async def handle_panel_defect(message: Message, state: FSMContext):
    logging.info("Специальный обработчик для брака панелей вызван")
    
    # Проверяем, что мы действительно находимся в состоянии ожидания типа брака
    current_state = await state.get_state()
    logging.info(f"Текущее состояние: {current_state}")
    
    if current_state != ProductionStates.waiting_for_defect_type:
        logging.warning(f"Вызов handle_panel_defect в неправильном состоянии: {current_state}")
        return
    
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

# Специальный обработчик для брака пленки с высоким приоритетом - перемещен выше для приоритета
@router.message(ProductionStates.waiting_for_defect_type, F.text == "🎨 Пленка")
async def handle_film_defect(message: Message, state: FSMContext):
    logging.info("Специальный обработчик для брака пленки вызван")
    
    # Проверяем, что мы действительно находимся в состоянии ожидания типа брака
    current_state = await state.get_state()
    logging.info(f"Текущее состояние при обработке брака пленки: {current_state}")
    
    if current_state != ProductionStates.waiting_for_defect_type:
        logging.warning(f"Вызов handle_film_defect в неправильном состоянии: {current_state}")
        return
    
    db = next(get_db())
    try:
        # Получаем список всех цветов пленки
        films = db.query(Film).all()
        films_list = [f"- {film.code} (остаток: {film.total_remaining} м)" for film in films]
        logging.info(f"Доступные пленки: {films_list}")
        
        await state.update_data(defect_type="film")
        await state.set_state(ProductionStates.waiting_for_defect_film_color)
        
        # Запрашиваем цвет пленки
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Назад")]],
            resize_keyboard=True
        )
        
        # Если нет пленок в системе, сообщаем что нельзя добавить брак
        if not films:
            await message.answer(
                "В системе нет ни одной пленки. Сначала добавьте пленку через меню 'Приход сырья'.",
                reply_markup=keyboard
            )
            return
        
        films_text = "\n".join(films_list)
        await message.answer(
            f"Выберите цвет/код бракованной пленки из списка:\n\nДоступные варианты:\n{films_text}",
            reply_markup=keyboard
        )
    finally:
        db.close()

# Обработка прихода пустых панелей
@router.message(F.text == "🪵 Панель")
async def handle_panel(message: Message, state: FSMContext):
    if not await check_production_access(message):
        return
    
    # Проверяем, что мы находимся в состоянии добавления материалов
    current_state = await state.get_state()
    logging.info(f"Нажата кнопка 'Панель', текущее состояние: {current_state}")
    
    # Если мы в меню выбора типа брака, пропускаем эту обработку
    if current_state == ProductionStates.waiting_for_defect_type:
        logging.info("Пропускаем обработку в handle_panel, так как находимся в меню брака. Будет вызван handle_panel_defect.")
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

# Специальный обработчик для брака панелей - УДАЛЯЕМ ЭТОТ ДУБЛИКАТ
    # Четко указываем, что это панель для дефекта
    await state.update_data(defect_type="panel_defect")
    await state.set_state(ProductionStates.waiting_for_defect_panel_quantity)

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
        
        # Запрашиваем метраж одного рулона
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
    
    try:
        meters = float(message.text.strip())
        if meters <= 0:
            await message.answer("Метраж должен быть положительным числом.")
            return
        
        # Сохраняем метраж в состоянии
        await state.update_data(film_meters=meters)
        
        # Запрашиваем расход на одну панель
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="2.5")],
                [KeyboardButton(text="3.0")],
                [KeyboardButton(text="3.5")],
                [KeyboardButton(text="◀️ Назад")]
            ],
            resize_keyboard=True
        )
        
        await message.answer(
            "Укажите расход пленки на одну панель (в метрах):",
            reply_markup=keyboard
        )
        
        # Устанавливаем новое состояние для ожидания расхода на панель
        await state.set_state(ProductionStates.waiting_for_panel_consumption)
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число.")

@router.message(ProductionStates.waiting_for_panel_consumption)
async def process_panel_consumption(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        # Возвращаемся к вводу метража
        data = await state.get_data()
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Назад")]],
            resize_keyboard=True
        )
        
        await message.answer(
            "Введите метраж одного рулона (например, 50):",
            reply_markup=keyboard
        )
        
        await state.set_state(ProductionStates.waiting_for_film_meters)
        return
    
    try:
        panel_consumption = float(message.text.strip())
        if panel_consumption <= 0:
            await message.answer("Расход на панель должен быть положительным числом.")
            return
        
        # Получаем сохраненные данные
        data = await state.get_data()
        film_code = data.get('film_code')
        film_quantity = data.get('film_quantity')
        meters = data.get('film_meters')
        
        # Расчитываем общий метраж
        total_meters = film_quantity * meters
        
        db = next(get_db())
        try:
            # Получаем пользователя из базы данных
            user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
            
            # Получаем пленку из базы данных
            film = db.query(Film).filter(Film.code == film_code).first()
            
            if not film:
                # Если запись о пленке не найдена, создаем ее
                film = Film(
                    code=film_code,
                    panel_consumption=panel_consumption,  # Используем введенное значение расхода
                    meters_per_roll=meters,               # Используем введенное значение метража в рулоне
                    total_remaining=total_meters
                )
                db.add(film)
            else:
                # Обновляем метраж пленки
                film.total_remaining += total_meters
                
                # Всегда используем введенное значение для метража в рулоне
                film.meters_per_roll = meters
                
                # Обновляем расход на панель, принимая новое значение
                film.panel_consumption = panel_consumption
            
            # Создаем запись об операции
            operation = Operation(
                user_id=user.id,
                operation_type="film_income",
                quantity=film_quantity,
                details=json.dumps({
                    "film_code": film_code,
                    "rolls": film_quantity,
                    "meters_per_roll": meters,
                    "panel_consumption": panel_consumption,
                    "total_meters": total_meters
                })
            )
            
            # Добавляем операцию в базу данных
            db.add(operation)
            
            # Сохраняем изменения
            db.commit()
            
            # Возвращаемся в меню материалов
            await state.set_state(MenuState.PRODUCTION_MATERIALS)
            keyboard = await get_role_menu_keyboard(MenuState.PRODUCTION_MATERIALS, message, state)
            
            await message.answer(
                f"✅ Приход оформлен!\n"
                f"Пленка: {film_code}\n"
                f"Количество рулонов: {film_quantity}\n"
                f"Метраж одного рулона: {meters}м\n"
                f"Расход на панель: {panel_consumption}м\n"
                f"Общий метраж: {total_meters}м\n\n"
                f"Теперь у вас {film.total_remaining}м пленки {film_code}",
                reply_markup=keyboard
            )
        finally:
            db.close()
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число.")

# Обработка прихода стыков
@router.message(F.text == "⚙️ Стык")
async def handle_joint_income(message: Message, state: FSMContext):
    # Проверяем, что мы в состоянии приема материалов
    current_state = await state.get_state()
    logging.info(f"Нажата кнопка 'Стык', текущее состояние: {current_state}")
    
    # Пропускаем обработку, если мы в любом состоянии, кроме меню материалов
    if current_state != MenuState.PRODUCTION_MATERIALS:
        logging.info(f"Пропускаем обработку, так как не в режиме добавления материалов")
        return
        
    await message.answer(
        "Выберите тип стыка:",
        reply_markup=get_joint_type_keyboard()
    )
    await state.set_state(ProductionStates.waiting_for_joint_type)

@router.message(ProductionStates.waiting_for_joint_type)
async def process_joint_type(message: Message, state: FSMContext):
    # Маппинг русских названий на значения enum
    joint_type_mapping = {
        "Бабочка": JointType.BUTTERFLY,
        "Простой": JointType.SIMPLE,
        "Замыкающий": JointType.CLOSING
    }
    
    if message.text not in ["Бабочка", "Простой", "Замыкающий"]:
        await message.answer("Пожалуйста, выберите тип стыка из предложенных вариантов.")
        return
        
    await state.update_data(joint_type=joint_type_mapping[message.text])
    await message.answer(
        "Введите цвет стыка:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Назад")]],
            resize_keyboard=True
        )
    )
    await state.set_state(ProductionStates.waiting_for_joint_color)

@router.message(ProductionStates.waiting_for_joint_color)
async def process_joint_color(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await message.answer(
            "Выберите тип стыка:",
            reply_markup=get_joint_type_keyboard()
        )
        await state.set_state(ProductionStates.waiting_for_joint_type)
        return
    
    await state.update_data(joint_color=message.text)
    await message.answer(
        "Выберите толщину стыка:",
        reply_markup=get_joint_thickness_keyboard()
    )
    await state.set_state(ProductionStates.waiting_for_joint_thickness)

@router.message(ProductionStates.waiting_for_joint_thickness)
async def process_joint_thickness(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await message.answer(
            "Введите цвет стыка:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="◀️ Назад")]],
                resize_keyboard=True
            )
        )
        await state.set_state(ProductionStates.waiting_for_joint_color)
        return
    
    if message.text not in ["0.5", "0.8"]:
        await message.answer("Пожалуйста, выберите толщину из предложенных вариантов.")
        return
    
    await state.update_data(joint_thickness=float(message.text))
    await message.answer(
        "Введите количество стыков для добавления:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Назад")]],
            resize_keyboard=True
        )
    )
    await state.set_state(ProductionStates.waiting_for_joint_quantity)

@router.message(ProductionStates.waiting_for_joint_quantity)
async def process_joint_quantity(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await message.answer(
            "Выберите толщину стыка:",
            reply_markup=get_joint_thickness_keyboard()
        )
        await state.set_state(ProductionStates.waiting_for_joint_thickness)
        return

    try:
        quantity = int(message.text)
        if quantity <= 0:
            await message.answer("Количество должно быть положительным числом.")
            return
        
        data = await state.get_data()
        db = next(get_db())
        try:
            # Получаем пользователя из базы данных
            user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
            
            # Получаем русское название типа стыка для отображения
            joint_type_names = {
                "butterfly": "Бабочка",
                "simple": "Простой",
                "closing": "Замыкающий"
            }
            
            # Проверяем существующий стык с такими параметрами
            joint = db.query(Joint).filter(
                Joint.type == data["joint_type"],
                Joint.color == data["joint_color"],
                Joint.thickness == data["joint_thickness"]
            ).first()
            
            if joint:
                # Если такой стык уже есть, обновляем его количество
                previous_quantity = joint.quantity
                joint.quantity += quantity
                
                # Создаем запись операции
                operation = Operation(
                    user_id=user.id,
                    operation_type="joint_income",
                    quantity=quantity,
                    details=json.dumps({
                        "joint_type": data["joint_type"].value,
                        "joint_color": data["joint_color"],
                        "joint_thickness": data["joint_thickness"],
                        "previous_quantity": previous_quantity,
                        "new_quantity": joint.quantity
                    })
                )
            else:
                # Если стыка еще нет, создаем новую запись
                joint = Joint(
                    type=data["joint_type"],
                    color=data["joint_color"],
                    thickness=data["joint_thickness"],
                    quantity=quantity
                )
                db.add(joint)
                
                # Создаем запись операции
                operation = Operation(
                    user_id=user.id,
                    operation_type="joint_income",
                    quantity=quantity,
                    details=json.dumps({
                        "joint_type": data["joint_type"].value,
                        "joint_color": data["joint_color"],
                        "joint_thickness": data["joint_thickness"],
                        "previous_quantity": 0,
                        "new_quantity": quantity
                    })
                )
            
            # Добавляем операцию в базу данных
            db.add(operation)
            
            # Сохраняем изменения
            db.commit()
            
            # Возвращаемся в меню материалов
            await state.set_state(MenuState.PRODUCTION_MATERIALS)
            keyboard = await get_role_menu_keyboard(MenuState.PRODUCTION_MATERIALS, message, state)
            
            # Получаем русское название типа стыка для отображения
            joint_type_name = joint_type_names.get(data["joint_type"].value, data["joint_type"].value)
            
            await message.answer(
                f"✅ Приход стыков зарегистрирован!\n"
                f"Тип: {joint_type_name}\n"
                f"Цвет: {data['joint_color']}\n"
                f"Толщина: {data['joint_thickness']} мм\n"
                f"Количество: {quantity} шт.\n"
                f"Общий остаток: {joint.quantity} шт.",
                reply_markup=keyboard
            )
            
        finally:
            db.close()
    except ValueError:
        await message.answer("Пожалуйста, введите целое число.")
        return

# Обработка прихода клея
@router.message(F.text == "🧴 Клей")
async def handle_glue_income(message: Message, state: FSMContext):
    # Проверяем, что мы в состоянии приема материалов
    current_state = await state.get_state()
    logging.info(f"Нажата кнопка 'Клей', текущее состояние: {current_state}")
    
    # Пропускаем обработку, если мы в любом состоянии, кроме меню материалов
    if current_state != MenuState.PRODUCTION_MATERIALS:
        logging.info(f"Пропускаем обработку, так как не в режиме добавления материалов")
        return
        
    await message.answer(
        "Введите количество клея (в штуках):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Назад")]],
            resize_keyboard=True
        )
    )
    await state.set_state(ProductionStates.waiting_for_glue_quantity)

@router.message(ProductionStates.waiting_for_glue_quantity)
async def process_glue_quantity(message: Message, state: FSMContext):
    try:
        quantity = int(message.text)
        if quantity <= 0:
            await message.answer("Количество должно быть положительным числом.")
            return
            
        db = next(get_db())
        try:
            # Получаем текущий остаток
            glue = db.query(Glue).first()
            if not glue:
                glue = Glue(quantity=0)
                db.add(glue)
            
            # Добавляем новый клей
            previous_quantity = glue.quantity
            glue.quantity += quantity
            
            # Получаем пользователя из базы данных
            user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
            
            # Создаем запись операции
            operation = Operation(
                user_id=user.id,  # Используем id из базы данных
                operation_type="glue_income",
                quantity=quantity,
                details=json.dumps({"previous_quantity": previous_quantity})
            )
            db.add(operation)
            
            db.commit()
            
            await message.answer(
                f"✅ Добавлено {quantity} шт. клея\n"
                f"Общий остаток: {glue.quantity} шт.",
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MATERIALS)
            )
        finally:
            db.close()
            
    except ValueError:
        await message.answer("Пожалуйста, введите целое число.")
        return
        
    await state.clear()

# Обработка производства
@router.message(F.text == "🛠 Производство")
async def handle_production(message: Message, state: FSMContext):
    if not await check_production_access(message):
        return
    
    await state.set_state(MenuState.PRODUCTION_PROCESS)
    
    db = next(get_db())
    try:
        # Проверяем наличие пустых панелей
        panel = db.query(Panel).first()
        if not panel or panel.quantity <= 0:
            await message.answer(
                "⚠️ Нет доступных пустых панелей для производства.",
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION_PROCESS)
            )
            return
            
        # Получаем список доступных пленок
        films = db.query(Film).all()
        if not films:
            await message.answer(
                "⚠️ Нет доступных пленок для производства.",
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION_PROCESS)
            )
            return
            
        # Формируем список доступных пленок с их остатками
        films_info = []
        for film in films:
            possible_panels = int(film.total_remaining / film.panel_consumption)
            if possible_panels > 0:
                films_info.append(
                    f"- {film.code} (можно произвести {possible_panels} панелей)"
                )
        
        if not films_info:
            await message.answer(
                "⚠️ Недостаточно пленки для производства панелей.",
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION_PROCESS)
            )
            return
            
        await message.answer(
            "Введите цвет пленки, из которой будут сделаны панели.\n\n"
            "Доступные варианты:\n" + "\n".join(films_info),
            reply_markup=get_menu_keyboard(MenuState.PRODUCTION_PROCESS)
        )
        await state.set_state(ProductionStates.waiting_for_production_film_color)
    finally:
        db.close()

@router.message(ProductionStates.waiting_for_production_film_color)
async def process_production_film_color(message: Message, state: FSMContext):
    film_code = message.text
    
    db = next(get_db())
    try:
        # Проверяем наличие пленки
        film = db.query(Film).filter(Film.code == film_code).first()
        if not film:
            await message.answer(
                "Пленка с таким цветом не найдена. Пожалуйста, выберите из списка доступных."
            )
            return
            
        # Проверяем достаточность пленки
        possible_panels = int(film.total_remaining / film.panel_consumption)
        if possible_panels <= 0:
            await message.answer(
                f"Недостаточно пленки цвета {film_code} для производства."
            )
            return
            
        # Проверяем наличие пустых панелей
        panel = db.query(Panel).first()
        max_panels = min(possible_panels, panel.quantity if panel else 0)
        
        await state.update_data(film_code=film_code)
        await message.answer(
            f"Выбрана пленка: {film_code}\n"
            f"Можно произвести максимум {max_panels} панелей\n\n"
            "Введите количество панелей для производства:"
        )
        await state.set_state(ProductionStates.waiting_for_production_quantity)
    finally:
        db.close()

@router.message(ProductionStates.waiting_for_production_quantity)
async def process_production_quantity(message: Message, state: FSMContext):
    try:
        quantity = int(message.text)
        if quantity <= 0:
            await message.answer("Количество должно быть положительным числом.")
            return
            
        data = await state.get_data()
        db = next(get_db())
        try:
            # Проверяем наличие пленки
            film = db.query(Film).filter(Film.code == data["film_code"]).first()
            if not film:
                await message.answer(
                    "Пленка с таким цветом не найдена."
                )
                return
                
            # Проверяем достаточность пленки
            required_film = quantity * film.panel_consumption
            if film.total_remaining < required_film:
                await message.answer(
                    f"Недостаточно пленки для производства {quantity} панелей.\n"
                    f"Доступно: {film.total_remaining:.1f} м\n"
                    f"Требуется: {required_film:.1f} м"
                )
                return
                
            # Проверяем наличие пустых панелей
            panel = db.query(Panel).first()
            if not panel or panel.quantity < quantity:
                await message.answer(
                    "Недостаточно пустых панелей для производства."
                )
                return
                
            # Уменьшаем количество пленки
            film.total_remaining -= required_film
            
            # Уменьшаем количество пустых панелей
            panel.quantity -= quantity
            
            # Добавляем готовый продукт
            finished_product = db.query(FinishedProduct).filter(
                FinishedProduct.film_id == film.id
            ).first()
            
            if finished_product:
                finished_product.quantity += quantity
            else:
                finished_product = FinishedProduct(
                    film_id=film.id,
                    quantity=quantity
                )
                db.add(finished_product)
            
            # Получаем пользователя из базы данных
            user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
            
            # Создаем запись операции
            operation = Operation(
                user_id=user.id,  # Используем id из базы данных
                operation_type="production",
                quantity=quantity,
                details=json.dumps({
                    "film_code": data["film_code"],
                    "film_used": required_film,
                    "remaining_film": film.total_remaining,
                    "remaining_panels": panel.quantity
                })
            )
            db.add(operation)
            
            db.commit()
            
            await message.answer(
                f"✅ Произведено {quantity} панелей\n"
                f"Цвет: {data['film_code']}\n"
                f"Остаток пленки: {film.total_remaining:.1f} метров\n"
                f"Остаток пустых панелей: {panel.quantity} шт.\n"
                f"Всего готовых панелей: {finished_product.quantity} шт.",
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MAIN)
            )
        finally:
            db.close()
            
    except ValueError:
        await message.answer("Пожалуйста, введите целое число.")
        return
        
    await state.clear()

@router.message(F.text == "📋 Заказы на производство")
async def handle_production_orders(message: Message, state: FSMContext):
    if not await check_production_access(message):
        return
    
    state_data = await state.get_data()
    is_admin_context = state_data.get("is_admin_context", False)
    
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
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION_ORDERS, is_admin_context)
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
            reply_markup=get_menu_keyboard(MenuState.PRODUCTION_ORDERS, is_admin_context)
        )
    finally:
        db.close()

@router.message(F.text == "✨ Завершить заказ")
async def handle_complete_order(message: Message, state: FSMContext):
    if not await check_production_access(message):
        return
    
    # Запрашиваем номер заказа
    await message.answer(
        "Введите номер заказа, который необходимо завершить:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Назад")]],
            resize_keyboard=True
        )
    )
    
    await state.set_state(ProductionStates.waiting_for_order_id_to_complete)

@router.message(ProductionStates.waiting_for_order_id_to_complete)
async def process_complete_production(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await handle_production_orders(message, state)
        await state.clear()
        return
    
    try:
        order_id = int(message.text)
        db = next(get_db())
        try:
            # Получаем заказ из базы данных
            order = db.query(ProductionOrder).filter(ProductionOrder.id == order_id).first()
            
            if not order:
                await message.answer("Заказ с таким номером не найден.")
                return
            
            if order.status != "new":
                await message.answer(
                    "Этот заказ уже завершен."
                )
                return
            
            # Получаем информацию о пленке по коду
            film = db.query(Film).filter(Film.code == order.film_color).first()
            if not film:
                await message.answer(
                    f"❌ Ошибка: пленка с кодом {order.film_color} не найдена в базе данных."
                )
                return
            
            # Получаем информацию о доступных панелях
            panels = db.query(Panel).first()
            if not panels:
                await message.answer(
                    "❌ Ошибка: нет данных о панелях в базе данных."
                )
                return
            
            # Рассчитываем расход пленки на основе переменных параметров для этого цвета
            film_consumption = film.panel_consumption * order.panel_quantity
            
            # Проверяем наличие достаточного количества материалов
            if film.total_remaining < film_consumption:
                await message.answer(
                    f"❌ Недостаточно пленки цвета {order.film_color}!\n"
                    f"Требуется: {film_consumption:.1f} м\n"
                    f"Доступно: {film.total_remaining:.1f} м"
                )
                return
            
            if panels.quantity < order.panel_quantity:
                await message.answer(
                    f"❌ Недостаточно пустых панелей!\n"
                    f"Требуется: {order.panel_quantity} шт.\n"
                    f"Доступно: {panels.quantity} шт."
                )
                return
            
            # Получаем пользователя из базы данных
            user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
            
            # Списываем материалы
            # 1. Списываем пленку
            film.total_remaining -= film_consumption
            
            # 2. Списываем пустые панели
            panels.quantity -= order.panel_quantity
            
            # 3. Добавляем готовую продукцию
            finished_product = db.query(FinishedProduct).filter(FinishedProduct.film_id == film.id).first()
            
            if not finished_product:
                # Если такой готовой продукции еще нет, создаем запись
                logging.info(f"Создаем новую запись готовой продукции для пленки id={film.id}, цвет={film.code}")
                finished_product = FinishedProduct(
                    film_id=film.id,
                    quantity=order.panel_quantity
                )
                db.add(finished_product)
                db.flush()  # Применяем изменения без коммита для получения ID
                logging.info(f"Создана запись готовой продукции id={finished_product.id}, количество={finished_product.quantity}")
            else:
                # Увеличиваем количество готовой продукции
                logging.info(f"Обновляем существующую запись готовой продукции id={finished_product.id}, старое количество={finished_product.quantity}")
                finished_product.quantity += order.panel_quantity
                logging.info(f"Новое количество готовой продукции={finished_product.quantity}")
            
            # Создаем запись об операции производства
            operation = Operation(
                user_id=user.id,
                operation_type="production",
                quantity=order.panel_quantity,
                details=json.dumps({
                    "order_id": order.id,
                    "film_code": order.film_color,
                    "film_consumption": film_consumption,
                    "panels_used": order.panel_quantity,
                    "finished_product_id": finished_product.id
                })
            )
            db.add(operation)
            
            # Обновляем статус заказа
            order.status = "completed"
            order.completed_at = func.now()
            
            # Сохраняем все изменения в базе данных
            db.commit()
            logging.info(f"Заказ {order.id} завершен, готовая продукция обновлена, film_id={film.id}, количество={finished_product.quantity}")
            
            # Отправляем уведомление пользователю
            await message.answer(
                f"✅ Производство завершено!\n"
                f"Цвет: {order.film_color}\n"
                f"Произведено панелей: {order.panel_quantity} шт.\n"
                f"Списано пленки: {film_consumption:.1f} м\n"
                f"Списано пустых панелей: {order.panel_quantity} шт.\n"
                f"Информация сохранена в finished_products, текущий остаток: {finished_product.quantity} шт."
            )
            
            # Отправляем уведомление менеджеру, создавшему заказ
            manager = db.query(User).filter(User.id == order.manager_id).first()
            if manager:
                try:
                    await message.bot.send_message(
                        chat_id=manager.telegram_id,
                        text=(
                            f"✅ Заказ №{order.id} на производство выполнен!\n"
                            f"Произведено: {order.panel_quantity} панелей цвета {order.film_color}"
                        )
                    )
                except Exception as e:
                    logging.error(f"Не удалось отправить уведомление менеджеру {manager.telegram_id}: {str(e)}")
            
            # Показываем обновленный список заказов с учетом контекста админа
            await handle_production_orders(message, state)
            await state.clear()
            
        except Exception as e:
            logging.error(f"Ошибка при завершении производства: {str(e)}")
            await message.answer(f"❌ Произошла ошибка: {str(e)}")
        finally:
            db.close()
    except ValueError:
        await message.answer("Пожалуйста, введите корректный номер заказа.")

# Обработка брака
@router.message(F.text == "🚫 Брак")
async def handle_defect(message: Message, state: FSMContext):
    logging.info("Нажата кнопка 'Брак'")
    
    if not await check_production_access(message):
        logging.warning("Отказано в доступе к функциональности брака")
        return
    
    # Сбрасываем любые предыдущие данные в состоянии, которые могли остаться
    await state.clear()
    
    logging.info("Устанавливаю состояние PRODUCTION_DEFECT")
    await state.set_state(MenuState.PRODUCTION_DEFECT)
    
    # Формируем клавиатуру для выбора типа брака
    keyboard = get_menu_keyboard(MenuState.PRODUCTION_DEFECT)
    logging.info(f"Сформирована клавиатура: {keyboard}")
    
    await message.answer(
        "Выберите тип брака:",
        reply_markup=keyboard
    )
    
    logging.info("Устанавливаю состояние waiting_for_defect_type")
    await state.set_state(ProductionStates.waiting_for_defect_type)
    
    # Сохраняем информацию о том, что мы в режиме обработки брака
    await state.update_data(context="defect_processing")
    
    logging.info(f"Текущее состояние после всех изменений: {await state.get_state()}")

# Обработчик для кнопки "Назад" и других нераспознанных сообщений в состоянии waiting_for_defect_type
@router.message(ProductionStates.waiting_for_defect_type)
async def process_defect_type_back(message: Message, state: FSMContext):
    logging.info(f"Обработка кнопки в меню брака: '{message.text}'")
    
    if message.text == "◀️ Назад":
        await message.answer(
            "Выберите действие:",
            reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MAIN)
        )
        await state.clear()
        return
    
    # Если нажата какая-то другая кнопка, сообщаем что её нет в списке
    if message.text not in ["🎨 Пленка", "🪵 Панель", "⚙️ Стык", "🧴 Клей", "◀️ Назад"]:
        await message.answer("Пожалуйста, выберите тип брака из предложенных вариантов.")

@router.message(ProductionStates.waiting_for_defect_joint_type)
async def process_defect_joint_type(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await message.answer(
            "Выберите тип брака:",
            reply_markup=get_menu_keyboard(MenuState.PRODUCTION_DEFECT)
        )
        await state.set_state(ProductionStates.waiting_for_defect_type)
        return

    joint_type_mapping = {
        "Бабочка": JointType.BUTTERFLY,
        "Простой": JointType.SIMPLE,
        "Замыкающий": JointType.CLOSING
    }
    
    if message.text not in joint_type_mapping:
        await message.answer("Пожалуйста, выберите тип стыка из предложенных вариантов.")
        return
    
    await state.update_data(joint_type=joint_type_mapping[message.text])
    await message.answer(
        "Введите цвет бракованного стыка:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Назад")]],
            resize_keyboard=True
        )
    )
    await state.set_state(ProductionStates.waiting_for_defect_joint_color)

@router.message(ProductionStates.waiting_for_defect_joint_color)
async def process_defect_joint_color(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await message.answer(
            "Выберите тип стыка:",
            reply_markup=get_joint_type_keyboard()
        )
        await state.set_state(ProductionStates.waiting_for_defect_joint_type)
        return
    
    await state.update_data(joint_color=message.text)
    await message.answer(
        "Выберите толщину бракованного стыка:",
        reply_markup=get_joint_thickness_keyboard()
    )
    await state.set_state(ProductionStates.waiting_for_defect_joint_thickness)

@router.message(ProductionStates.waiting_for_defect_joint_thickness)
async def process_defect_joint_thickness(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await message.answer(
            "Введите цвет бракованного стыка:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="◀️ Назад")]],
                resize_keyboard=True
            )
        )
        await state.set_state(ProductionStates.waiting_for_defect_joint_color)
        return
    
    if message.text not in ["0.5", "0.8"]:
        await message.answer("Пожалуйста, выберите толщину из предложенных вариантов.")
        return
    
    await state.update_data(joint_thickness=float(message.text))
    await message.answer(
        "Введите количество бракованных стыков:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Назад")]],
            resize_keyboard=True
        )
    )
    await state.set_state(ProductionStates.waiting_for_defect_joint_quantity)

@router.message(ProductionStates.waiting_for_defect_joint_quantity)
async def process_defect_joint_quantity(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await message.answer(
            "Выберите толщину бракованного стыка:",
            reply_markup=get_joint_thickness_keyboard()
        )
        await state.set_state(ProductionStates.waiting_for_defect_joint_thickness)
        return

    try:
        quantity = int(message.text)
        if quantity <= 0:
            await message.answer("Количество должно быть положительным числом.")
            return
        
        data = await state.get_data()
        db = next(get_db())
        try:
            joint = db.query(Joint).filter(
                Joint.type == data["joint_type"],
                Joint.color == data["joint_color"],
                Joint.thickness == data["joint_thickness"]
            ).first()
            
            if not joint:
                await message.answer("Стык с такими параметрами не найден.")
                return
            
            if joint.quantity < quantity:
                await message.answer(
                    f"Невозможно списать {quantity} стыков, доступно только {joint.quantity}."
                )
                return
            
            # Получаем пользователя из базы данных
            user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
            
            # Создаем запись операции
            operation = Operation(
                user_id=user.id,
                operation_type="joint_defect",
                quantity=quantity,
                details=json.dumps({
                    "joint_type": data["joint_type"].value,
                    "joint_color": data["joint_color"],
                    "joint_thickness": data["joint_thickness"],
                    "previous_quantity": joint.quantity
                })
            )
            db.add(operation)
            
            # Уменьшаем количество стыков
            joint.quantity -= quantity
            db.commit()
            
            # Получаем русское название типа стыка для отображения
            joint_type_names = {
                "butterfly": "Бабочка",
                "simple": "Простой",
                "closing": "Замыкающий"
            }
            
            await message.answer(
                f"✅ Списано {quantity} бракованных стыков\n"
                f"Тип: {joint_type_names[data['joint_type'].value]}\n"
                f"Цвет: {data['joint_color']}\n"
                f"Толщина: {data['joint_thickness']} мм\n"
                f"Остаток: {joint.quantity} шт.",
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MAIN)
            )
            
            # Возвращаемся в главное меню
            await state.set_state(MenuState.PRODUCTION_MAIN)
            
        finally:
            db.close()
            
    except ValueError:
        await message.answer("Пожалуйста, введите целое число.")
        return

@router.message(ProductionStates.waiting_for_defect_panel_quantity)
async def process_defect_panel_quantity(message: Message, state: FSMContext):
    logging.info(f"Обработка количества бракованных панелей: '{message.text}'")
    
    if message.text == "◀️ Назад":
        logging.info("Пользователь нажал Назад")
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
        
        # Проверяем, что мы в правильном контексте обработки брака
        data = await state.get_data()
        logging.info(f"Текущие данные состояния: {data}")
        
        defect_type = data.get("defect_type", "")
        if defect_type != "panel_defect":
            logging.warning(f"Неправильный тип дефекта: {defect_type}")
            await message.answer("Произошла ошибка. Пожалуйста, начните процесс заново.")
            await state.set_state(MenuState.PRODUCTION_MAIN)
            return
            
        db = next(get_db())
        try:
            panel = db.query(Panel).first()
            if not panel:
                logging.warning("В базе не найдены панели")
                await message.answer("В базе нет панелей.")
                return
            
            if panel.quantity < quantity:
                logging.warning(f"Недостаточно панелей: запрошено {quantity}, доступно {panel.quantity}")
                await message.answer(
                    f"Невозможно списать {quantity} панелей, доступно только {panel.quantity}."
                )
                return
            
            # Получаем пользователя из базы данных
            user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
            
            # Уменьшаем количество панелей
            previous_quantity = panel.quantity
            panel.quantity -= quantity
            logging.info(f"Списываем {quantity} панелей. Было: {previous_quantity}, стало: {panel.quantity}")
            
            # Создаем запись операции
            operation = Operation(
                user_id=user.id,
                operation_type="panel_defect_subtract",  # Явно указываем, что это вычитание для брака
                quantity=quantity,
                details=json.dumps({
                    "previous_quantity": previous_quantity,
                    "new_quantity": panel.quantity,
                    "is_defect": True  # Указываем, что это операция брака
                })
            )
            logging.info(f"Создаю запись операции: {operation.operation_type}, количество: {operation.quantity}")
            
            db.add(operation)
            db.commit()
            logging.info("Операция успешно записана в БД")
            
            await message.answer(
                f"✅ Списано {quantity} бракованных панелей\n"
                f"Остаток: {panel.quantity} шт.",
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MAIN)
            )
            logging.info("Отправлено сообщение об успешном списании")
            
        finally:
            db.close()
            
    except ValueError:
        logging.warning(f"Введено некорректное значение: '{message.text}'")
        await message.answer("Пожалуйста, введите целое число.")
        return
    
    logging.info("Сбрасываю состояние")
    await state.clear()

@router.message(ProductionStates.waiting_for_defect_film_color)
async def process_defect_film_color(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await handle_defect(message, state)
        return
    
    film_color = message.text.strip()
    logging.info(f"Получен цвет пленки для брака: '{film_color}'")
    
    db = next(get_db())
    try:
        # Проверяем существование пленки
        film = db.query(Film).filter(Film.code == film_color).first()
        
        # Если пленки с таким кодом нет, сообщаем об ошибке
        if not film:
            logging.warning(f"Пленка с цветом '{film_color}' не найдена в базе")
            await message.answer(
                f"Пленка с цветом '{film_color}' не найдена в базе данных. "
                f"Пожалуйста, выберите из списка доступных цветов или сначала добавьте "
                f"этот цвет пленки через меню 'Приход сырья'.",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="◀️ Назад")]],
                    resize_keyboard=True
                )
            )
            return
        
        logging.info(f"Найдена пленка: {film.code}, остаток: {film.total_remaining} м")
        
        # Сохраняем цвет в состоянии
        await state.update_data(defect_film_color=film_color)
        
        # Запрашиваем метраж брака
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Назад")]],
            resize_keyboard=True
        )
        
        await message.answer(
            f"Введите количество метров бракованной пленки цвета {film_color}:\n\n"
            f"Доступно: {film.total_remaining:.1f} м",
            reply_markup=keyboard
        )
        
        await state.set_state(ProductionStates.waiting_for_defect_film_meters)
    finally:
        db.close()

@router.message(ProductionStates.waiting_for_defect_film_meters)
async def process_defect_film_meters(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        # Возвращаемся к вводу цвета пленки
        await handle_film_defect(message, state)
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