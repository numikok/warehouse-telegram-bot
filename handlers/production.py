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

logging.basicConfig(level=logging.INFO)

router = Router()

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

# Специальный обработчик для брака панелей
@router.message(ProductionStates.waiting_for_defect_type, F.text == "🪵 Панель")
async def handle_panel_defect(message: Message, state: FSMContext):
    logging.info("Специальный обработчик для брака панелей вызван")
    
    # Запрашиваем толщину бракованных панелей
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="0.5")],
            [KeyboardButton(text="0.8")],
            [KeyboardButton(text="◀️ Назад")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "Выберите толщину бракованных панелей (мм):",
        reply_markup=keyboard
    )
    
    # Четко указываем, что это панель для дефекта
    await state.update_data(defect_type="panel_defect")
    logging.info("Установлен тип дефекта: panel_defect")
    
    await state.set_state(ProductionStates.waiting_for_defect_panel_thickness)
    logging.info("Установлено состояние: waiting_for_defect_panel_thickness")

@router.message(ProductionStates.waiting_for_defect_panel_thickness)
async def process_defect_panel_thickness(message: Message, state: FSMContext):
    logging.info(f"Обработка выбора толщины бракованных панелей: '{message.text}'")
    
    if message.text == "◀️ Назад":
        logging.info("Пользователь нажал Назад")
        await message.answer(
            "Выберите тип брака:",
            reply_markup=get_menu_keyboard(MenuState.PRODUCTION_DEFECT)
        )
        await state.set_state(ProductionStates.waiting_for_defect_type)
        return
    
    try:
        thickness = float(message.text.strip())
        if thickness not in [0.5, 0.8]:
            await message.answer("Пожалуйста, выберите толщину 0.5 или 0.8 мм.")
            return
        
        # Сохраняем толщину в состоянии
        await state.update_data(panel_thickness=thickness)
        
        db = next(get_db())
        try:
            # Получаем текущий остаток панелей с указанной толщиной
            panel = db.query(Panel).filter(Panel.thickness == thickness).first()
            
            if not panel or panel.quantity <= 0:
                logging.warning(f"В базе нет панелей толщиной {thickness} мм")
                await message.answer(
                    f"В базе нет панелей толщиной {thickness} мм.",
                    reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MAIN)
                )
                return
            
            logging.info(f"Найдены панели толщиной {thickness} мм, остаток: {panel.quantity} шт.")
            
            await message.answer(
                f"Введите количество бракованных панелей толщиной {thickness} мм:\n\nДоступно: {panel.quantity} шт.",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="◀️ Назад")]],
                    resize_keyboard=True
                )
            )
            
            logging.info("Запрошено количество бракованных панелей")
        finally:
            db.close()
            
        await state.set_state(ProductionStates.waiting_for_defect_panel_quantity)
        logging.info("Установлено состояние: waiting_for_defect_panel_quantity")
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число (0.5 или 0.8).")

@router.message(ProductionStates.waiting_for_defect_panel_quantity)
async def process_defect_panel_quantity(message: Message, state: FSMContext):
    logging.info(f"Обработка количества бракованных панелей: '{message.text}'")
    
    if message.text == "◀️ Назад":
        logging.info("Пользователь нажал Назад")
        await message.answer(
            "Выберите толщину бракованных панелей (мм):",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="0.5")],
                    [KeyboardButton(text="0.8")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(ProductionStates.waiting_for_defect_panel_thickness)
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
        panel_thickness = data.get("panel_thickness", 0.5)
        
        if defect_type != "panel_defect":
            logging.warning(f"Неправильный тип дефекта: {defect_type}")
            await message.answer("Произошла ошибка. Пожалуйста, начните процесс заново.")
            await state.set_state(MenuState.PRODUCTION_MAIN)
            return
            
        db = next(get_db())
        try:
            # Ищем панель по толщине
            panel = db.query(Panel).filter(Panel.thickness == panel_thickness).first()
            
            if not panel:
                logging.warning(f"В базе не найдены панели толщиной {panel_thickness} мм")
                await message.answer(f"В базе нет панелей толщиной {panel_thickness} мм.")
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
                    "panel_thickness": panel_thickness,
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
                f"✅ Списано {quantity} бракованных панелей толщиной {panel_thickness} мм\n"
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
    
    await state.clear()

@router.message(ProductionStates.waiting_for_defect_film_color)
async def process_defect_film_color(message: Message, state: FSMContext):
    logging.info(f"Обработка выбора цвета бракованной пленки: '{message.text}'")
    
    if message.text == "◀️ Назад":
        logging.info("Пользователь нажал Назад")
        await handle_defect(message, state)
        return
    
    db = next(get_db())
    try:
        # Ищем пленку по коду
        film = db.query(Film).filter(Film.code == message.text).first()
        
        if not film:
            # Проверяем, может быть пользователь ввел не код, а описание 
            # или часть кода, пытаемся найти подходящую пленку
            films = db.query(Film).filter(Film.code.ilike(f"%{message.text}%")).all()
            
            if not films:
                await message.answer(
                    "Пленка с таким кодом не найдена. Пожалуйста, введите корректный код из списка."
                )
                return
                
            if len(films) > 1:
                films_list = [f"- {film.code} (остаток: {film.total_remaining} м)" for film in films]
                films_text = "\n".join(films_list)
                await message.answer(
                    f"Найдено несколько вариантов пленки, уточните код:\n\n{films_text}"
                )
                return
                
            film = films[0]  # Если нашли ровно одну подходящую пленку
        
        # Проверяем, что есть остаток пленки
        if film.total_remaining <= 0:
            await message.answer(
                f"Пленка с кодом {film.code} имеет нулевой остаток, нельзя списать брак."
            )
            return
        
        # Сохраняем код пленки в состоянии
        await state.update_data(film_code=film.code)
        
        logging.info(f"Выбрана пленка с кодом: {film.code}, остаток: {film.total_remaining} м")
        
        # Запрашиваем метраж пленки (пропускаем шаг с толщиной)
        await state.set_state(ProductionStates.waiting_for_defect_film_meters)
        
        await message.answer(
            f"Введите количество бракованной пленки в метрах:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="◀️ Назад")]],
                resize_keyboard=True
            )
        )
        logging.info("Запрошен метраж бракованной пленки")
        
    finally:
        db.close()

@router.message(ProductionStates.waiting_for_defect_film_meters)
async def process_defect_film_meters(message: Message, state: FSMContext):
    logging.info(f"Обработка ввода количества бракованной пленки: '{message.text}'")
    
    if message.text == "◀️ Назад":
        logging.info("Пользователь нажал Назад при вводе метража пленки")
        
        # Возвращаемся к выбору цвета пленки
        db = next(get_db())
        try:
            films = db.query(Film).all()
            films_list = [f"- {film.code} (остаток: {film.total_remaining} м)" for film in films]
            films_text = "\n".join(films_list)
            
            await message.answer(
                f"Выберите цвет/код бракованной пленки из списка:\n\nДоступные варианты:\n{films_text}",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="◀️ Назад")]],
                    resize_keyboard=True
                )
            )
        finally:
            db.close()
            
        await state.set_state(ProductionStates.waiting_for_defect_film_color)
        return
    
    try:
        meters = float(message.text.strip())
        if meters <= 0:
            await message.answer(
                "Метраж должен быть положительным числом.",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="◀️ Назад")]],
                    resize_keyboard=True
                )
            )
            return
        
        # Получаем данные состояния
        data = await state.get_data()
        film_code = data.get('film_code', '')
        
        db = next(get_db())
        try:
            # Получаем пленку из базы данных
            film = db.query(Film).filter(Film.code == film_code).first()
            if not film:
                logging.warning(f"Пленка с кодом '{film_code}' не найдена в базе")
                await message.answer("Пленка с таким кодом не найдена в базе данных.")
                return
            
            # Проверяем достаточность пленки
            if film.total_remaining < meters:
                logging.warning(f"Недостаточно пленки: запрошено {meters}м, доступно {film.total_remaining}м")
                await message.answer(
                    f"Невозможно списать {meters}м пленки, доступно только {film.total_remaining}м.",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[[KeyboardButton(text="◀️ Назад")]],
                        resize_keyboard=True
                    )
                )
                return
            
            # Получаем пользователя из базы данных
            user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
            
            # Уменьшаем метраж пленки
            previous_remaining = film.total_remaining
            film.total_remaining -= meters
            logging.info(f"Списываем {meters}м пленки. Было: {previous_remaining}м, стало: {film.total_remaining}м")
            
            # Создаем запись операции
            operation = Operation(
                user_id=user.id,
                operation_type="film_defect",
                quantity=meters,
                details=json.dumps({
                    "film_code": film_code,
                    "previous_remaining": previous_remaining,
                    "new_remaining": film.total_remaining,
                    "is_defect": True
                })
            )
            logging.info(f"Создаю запись операции: {operation.operation_type}, количество: {operation.quantity}")
            
            db.add(operation)
            db.commit()
            logging.info("Операция успешно записана в БД")
            
            await message.answer(
                f"✅ Списано {meters}м бракованной пленки\n"
                f"Код: {film_code}\n"
                f"Остаток: {film.total_remaining}м",
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MAIN)
            )
            logging.info("Отправлено сообщение об успешном списании")
            
        finally:
            db.close()
            
    except ValueError:
        logging.warning(f"Введено некорректное значение метража: '{message.text}'")
        await message.answer(
            "Пожалуйста, введите корректное число для метража.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="◀️ Назад")]],
                resize_keyboard=True
            )
        )
        return
    
    await state.clear()

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
        film_thickness = data.get('film_thickness', 0.5)  # Получаем толщину пленки, по умолчанию 0.5
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
                    thickness=film_thickness,             # Используем введенное значение толщины
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
                
                # Обновляем толщину пленки, если она изменилась
                film.thickness = film_thickness
            
            # Создаем запись об операции
            operation = Operation(
                user_id=user.id,
                operation_type="film_income",
                quantity=film_quantity,
                details=json.dumps({
                    "film_code": film_code,
                    "film_thickness": film_thickness,
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
                f"Толщина: {film_thickness} мм\n"
                f"Количество рулонов: {film_quantity}\n"
                f"Метраж одного рулона: {meters}м\n"
                f"Расход на панель: {panel_consumption}м\n"
                f"Общий метраж: {total_meters}м\n\n"
                f"Теперь у вас {film.total_remaining}м пленки {film_code}"
                f" (толщина: {film_thickness} мм)",
                reply_markup=keyboard
            )
        finally:
            db.close()
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число.")

# Обработка прихода стыков
@router.message(F.text == "⚙️ Стык")
async def handle_joint_button(message: Message, state: FSMContext):
    # Получаем текущее состояние
    current_state = await state.get_state()
    logging.info(f"Нажата кнопка 'Стык', текущее состояние: {current_state}")
    
    # Проверяем, что мы в состоянии приема материалов
    if current_state == MenuState.PRODUCTION_MATERIALS:
        logging.info("Обработка нажатия Стык в режиме приема материалов")
        await message.answer(
            "Выберите тип стыка:",
            reply_markup=get_joint_type_keyboard()
        )
        await state.set_state(ProductionStates.waiting_for_joint_type)
        return
        
    # Если мы в меню брака
    if current_state == ProductionStates.waiting_for_defect_type:
        logging.info("Обработка нажатия Стык в режиме брака")
        await process_joint_defect(message, state)
        return
        
    logging.info(f"Пропускаем обработку, так как состояние {current_state} не подходит")

@router.message(ProductionStates.waiting_for_joint_type)
async def process_joint_type(message: Message, state: FSMContext):
    # Маппинг русских названий на значения enum
    joint_type_mapping = {
        "Бабочка": JointType.BUTTERFLY,
        "Простой": JointType.SIMPLE,
        "Замыкающий": JointType.CLOSING
    }
    
    selected_type_enum = joint_type_mapping.get(message.text)

    if not selected_type_enum:
        await message.answer("Пожалуйста, выберите тип стыка из предложенных вариантов.")
        return
        
    await state.update_data(joint_type=selected_type_enum)

    # Получаем существующие цвета для данного типа
    db = next(get_db())
    try:
        existing_colors = db.query(Joint.color).filter(
            Joint.type == selected_type_enum
        ).distinct().all()
        existing_colors = sorted([c[0] for c in existing_colors]) # Сортируем для порядка

        # Создаем кнопки для цветов
        keyboard_buttons = []
        row = []
        if existing_colors:
            for color in existing_colors:
                row.append(KeyboardButton(text=color))
                if len(row) == 2:
                    keyboard_buttons.append(row)
                    row = []
            if row:
                keyboard_buttons.append(row)

        # Добавляем кнопку Назад
        keyboard_buttons.append([KeyboardButton(text="◀️ Назад")])
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=keyboard_buttons,
            resize_keyboard=True,
            input_field_placeholder="Выберите цвет или введите новый"
        )

        if existing_colors:
            colors_text = "\n".join([f"- {c}" for c in existing_colors])
            await message.answer(
                f"Выберите цвет стыка для типа '{message.text}' или введите новый:\n\nСуществующие цвета:\n{colors_text}",
                reply_markup=keyboard
            )
        else:
             await message.answer(
                f"Введите цвет нового стыка (тип: '{message.text}'):",
                 reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="◀️ Назад")]],
                    resize_keyboard=True,
                    input_field_placeholder="Введите новый цвет"
                )
            )

    finally:
        db.close()
        
    await state.set_state(ProductionStates.waiting_for_joint_color)

@router.message(ProductionStates.waiting_for_joint_color)
async def process_joint_color(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        # Возвращаемся к выбору типа
        await message.answer(
            "Выберите тип стыка:",
            reply_markup=get_joint_type_keyboard()
        )
        await state.set_state(ProductionStates.waiting_for_joint_type)
        return
    
    selected_color = message.text.strip()
    if not selected_color:
        await message.answer("Цвет стыка не может быть пустым. Попробуйте снова.")
        return
        
    await state.update_data(joint_color=selected_color)
    
    # Толщину всегда выбираем из стандартных кнопок
    await message.answer(
        f"Выберите толщину стыка (цвет: {selected_color}):",
        reply_markup=get_joint_thickness_keyboard() # Используем стандартную клавиатуру толщин
    )
    await state.set_state(ProductionStates.waiting_for_joint_thickness)

@router.message(ProductionStates.waiting_for_joint_thickness)
async def process_joint_thickness(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        # Возвращаемся к выбору/вводу цвета
        data = await state.get_data()
        selected_type_enum = data.get('joint_type')
        type_display_names = {
            JointType.BUTTERFLY: "Бабочка",
            JointType.SIMPLE: "Простой",
            JointType.CLOSING: "Замыкающий"
        }
        type_name = type_display_names.get(selected_type_enum, "Unknown")
        
        # Пересоздаем клавиатуру для цветов
        db = next(get_db())
        try:
            existing_colors = db.query(Joint.color).filter(
                Joint.type == selected_type_enum
            ).distinct().all()
            existing_colors = sorted([c[0] for c in existing_colors])

            keyboard_buttons = []
            row = []
            if existing_colors:
                for color in existing_colors:
                    row.append(KeyboardButton(text=color))
                    if len(row) == 2:
                        keyboard_buttons.append(row)
                        row = []
                if row:
                    keyboard_buttons.append(row)
            keyboard_buttons.append([KeyboardButton(text="◀️ Назад")])
            
            keyboard = ReplyKeyboardMarkup(
                keyboard=keyboard_buttons,
                resize_keyboard=True,
                input_field_placeholder="Выберите цвет или введите новый"
            )
            
            if existing_colors:
                colors_text = "\n".join([f"- {c}" for c in existing_colors])
                await message.answer(
                    f"Выберите цвет стыка для типа '{type_name}' или введите новый:\n\nСуществующие цвета:\n{colors_text}",
                    reply_markup=keyboard
                )
            else:
                await message.answer(
                    f"Введите цвет нового стыка (тип: '{type_name}'):",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[[KeyboardButton(text="◀️ Назад")]],
                        resize_keyboard=True,
                        input_field_placeholder="Введите новый цвет"
                    )
                )
        finally:
            db.close()

        await state.set_state(ProductionStates.waiting_for_joint_color)
        return
    
    if message.text not in ["0.5", "0.8"]:
        await message.answer("Пожалуйста, выберите толщину из предложенных вариантов (0.5 или 0.8).")
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
        quantity = int(message.text.strip())
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
async def handle_glue_button(message: Message, state: FSMContext):
    # Получаем текущее состояние
    current_state = await state.get_state()
    logging.info(f"Нажата кнопка 'Клей', текущее состояние: {current_state}")
    
    # Проверяем, что мы в состоянии приема материалов
    if current_state == MenuState.PRODUCTION_MATERIALS:
        logging.info("Обработка нажатия Клей в режиме приема материалов")
        # Копируем логику из handle_glue_income
        await message.answer(
            "Введите количество клея (в штуках) для добавления:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="◀️ Назад")]],
                resize_keyboard=True
            )
        )
        await state.set_state(ProductionStates.waiting_for_glue_quantity)
        return
        
    # Если мы в меню брака
    if current_state == ProductionStates.waiting_for_defect_type:
        logging.info("Обработка нажатия Клей в режиме брака")
        await process_glue_defect(message, state)
        return
        
    logging.info(f"Пропускаем обработку, так как состояние {current_state} не подходит")

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
    
    # Сбрасываем старые данные состояния
    await state.clear()
    
    # Запрашиваем толщину панелей для производства
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="0.5")],
            [KeyboardButton(text="0.8")],
            [KeyboardButton(text="◀️ Назад")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "Выберите толщину панелей для производства (мм):",
        reply_markup=keyboard
    )
    
    # Явно указываем, что мы в режиме производства, а не добавления материалов
    await state.update_data(operation_type="production")
    await state.set_state(ProductionStates.waiting_for_production_panel_thickness)

@router.message(ProductionStates.waiting_for_production_panel_thickness)
async def process_production_panel_thickness(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.set_state(MenuState.PRODUCTION_MAIN)
        keyboard = await get_role_menu_keyboard(MenuState.PRODUCTION_MAIN, message, state)
        await message.answer("Выберите действие:", reply_markup=keyboard)
        return
    
    try:
        thickness = float(message.text.strip())
        if thickness not in [0.5, 0.8]:
            await message.answer("Пожалуйста, выберите толщину 0.5 или 0.8 мм.")
            return
        
        # Проверяем, есть ли в базе пустые панели с указанной толщиной
        db = next(get_db())
        try:
            panel = db.query(Panel).filter(Panel.thickness == thickness).first()
            
            if not panel or panel.quantity <= 0:
                await message.answer(
                    f"В базе нет панелей толщиной {thickness} мм для производства.\n"
                    f"Сначала добавьте панели через меню 'Приход сырья'.",
                    reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MAIN)
                )
                return
            
            # Сохраняем толщину панелей в состоянии
            await state.update_data(panel_thickness=thickness)
            
            # Получаем список доступных пленок
            films = db.query(Film).all()
            
            if not films:
                await message.answer(
                    "В базе нет пленок для производства.\n"
                    "Сначала добавьте пленку через меню 'Приход сырья'.",
                    reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MAIN)
                )
                return
                
            # Формируем кнопки для выбора цвета пленки
            keyboard_rows = []
            for film in films:
                # Рассчитываем, сколько панелей можно произвести из доступной пленки
                possible_panels = film.calculate_possible_panels()
                if possible_panels > 0:  # Показываем только те цвета, для которых хватает пленки
                    keyboard_rows.append([KeyboardButton(text=film.code)])
            
            # Добавляем кнопку "Назад"
            keyboard_rows.append([KeyboardButton(text="◀️ Назад")])
            
            keyboard = ReplyKeyboardMarkup(
                keyboard=keyboard_rows,
                resize_keyboard=True
            )
            
            # Формируем список доступных пленок с информацией
            film_info = []
            for film in films:
                possible_panels = film.calculate_possible_panels()
                film_info.append(
                    f"- {film.code}: {film.total_remaining:.2f}м (хватит на ~{possible_panels} панелей)"
                )
            
            film_info_text = "\n".join(film_info)
            
            await message.answer(
                f"Выберите цвет пленки для производства:\n\n"
                f"Доступные пленки:\n{film_info_text}",
                reply_markup=keyboard
            )
            
            await state.set_state(ProductionStates.waiting_for_production_film_color)
            
        finally:
            db.close()
            
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число (0.5 или 0.8).")

@router.message(ProductionStates.waiting_for_production_film_color)
async def process_production_film_color(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        # Возвращаемся к выбору толщины панелей
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="0.5")],
                [KeyboardButton(text="0.8")],
                [KeyboardButton(text="◀️ Назад")]
            ],
            resize_keyboard=True
        )
        
        await message.answer(
            "Выберите толщину панелей для производства (мм):",
            reply_markup=keyboard
        )
        
        await state.set_state(ProductionStates.waiting_for_production_panel_thickness)
        return
    
    film_color = message.text.strip()
    
    # Проверяем, что такая пленка существует
    db = next(get_db())
    try:
        film = db.query(Film).filter(Film.code == film_color).first()
        
        if not film:
            await message.answer(
                f"Пленка с кодом {film_color} не найдена в базе данных.\n"
                f"Пожалуйста, выберите из списка доступных цветов.",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="◀️ Назад")]],
                    resize_keyboard=True
                )
            )
            return
        
        # Проверяем, что пленки достаточно хотя бы для одной панели
        if film.total_remaining < film.panel_consumption:
            await message.answer(
                f"Доступного количества пленки {film_color} недостаточно даже для одной панели.\n"
                f"Необходимо: {film.panel_consumption}м на панель\n"
                f"Доступно: {film.total_remaining}м\n\n"
                f"Пожалуйста, выберите другой цвет пленки или добавьте пленку через меню 'Приход сырья'.",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="◀️ Назад")]],
                    resize_keyboard=True
                )
            )
            return
        
        # Сохраняем выбранный цвет пленки
        await state.update_data(film_color=film_color)
        
        # Получаем данные о толщине панелей
        data = await state.get_data()
        panel_thickness = data.get("panel_thickness", 0.5)
        
        # Получаем информацию о доступных панелях
        panel = db.query(Panel).filter(Panel.thickness == panel_thickness).first()
        panel_quantity = panel.quantity if panel else 0
        
        # Рассчитываем, сколько панелей можно произвести из доступной пленки
        possible_panels = film.calculate_possible_panels()
        max_possible = min(panel_quantity, possible_panels)
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Назад")]],
            resize_keyboard=True
        )
        
        await message.answer(
            f"Введите количество панелей для производства с пленкой {film_color}:\n\n"
            f"Доступно панелей толщиной {panel_thickness} мм: {panel_quantity} шт.\n"
            f"Доступно пленки {film_color}: {film.total_remaining:.2f}м (хватит на ~{possible_panels} панелей)\n"
            f"Вы можете произвести максимум {max_possible} панелей.",
            reply_markup=keyboard
        )
        
        await state.set_state(ProductionStates.waiting_for_production_quantity)
        
    finally:
        db.close()

@router.message(ProductionStates.waiting_for_production_quantity)
async def process_production_quantity(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        # Возвращаемся к выбору цвета пленки
        db = next(get_db())
        try:
            # Получаем список доступных пленок
            films = db.query(Film).all()
            
            # Формируем кнопки для выбора цвета пленки
            keyboard_rows = []
            for film in films:
                # Рассчитываем, сколько панелей можно произвести из доступной пленки
                possible_panels = film.calculate_possible_panels()
                if possible_panels > 0:  # Показываем только те цвета, для которых хватает пленки
                    keyboard_rows.append([KeyboardButton(text=film.code)])
            
            # Добавляем кнопку "Назад"
            keyboard_rows.append([KeyboardButton(text="◀️ Назад")])
            
            keyboard = ReplyKeyboardMarkup(
                keyboard=keyboard_rows,
                resize_keyboard=True
            )
            
            # Формируем список доступных пленок с информацией
            film_info = []
            for film in films:
                possible_panels = film.calculate_possible_panels()
                film_info.append(
                    f"- {film.code}: {film.total_remaining:.2f}м (хватит на ~{possible_panels} панелей)"
                )
            
            film_info_text = "\n".join(film_info)
            
            await message.answer(
                f"Выберите цвет пленки для производства:\n\n"
                f"Доступные пленки:\n{film_info_text}",
                reply_markup=keyboard
            )
        finally:
            db.close()
            
        await state.set_state(ProductionStates.waiting_for_production_film_color)
        return
    
    try:
        quantity = int(message.text.strip())
        if quantity <= 0:
            await message.answer("Количество панелей должно быть положительным числом.")
            return
        
        # Получаем сохраненные данные
        data = await state.get_data()
        film_color = data.get("film_color", "")
        panel_thickness = data.get("panel_thickness", 0.5)
        operation_type = data.get("operation_type", "")
        
        if operation_type != "production":
            logging.warning(f"Неправильный тип операции: {operation_type}")
            await message.answer("Произошла ошибка. Пожалуйста, начните процесс заново.")
            await state.set_state(MenuState.PRODUCTION_MAIN)
            return
        
        db = next(get_db())
        try:
            # Получаем пользователя
            user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
            
            # Получаем информацию о пленке
            film = db.query(Film).filter(Film.code == film_color).first()
            if not film:
                await message.answer(f"Пленка с кодом {film_color} не найдена в базе данных.")
                return
            
            # Получаем информацию о панелях
            panel = db.query(Panel).filter(Panel.thickness == panel_thickness).first()
            if not panel:
                await message.answer(f"Панели толщиной {panel_thickness} мм не найдены в базе данных.")
                return
            
            # Рассчитываем необходимое количество материалов
            required_film = quantity * film.panel_consumption
            
            # Проверяем достаточность материалов
            if panel.quantity < quantity:
                await message.answer(
                    f"Недостаточно панелей. Запрошено: {quantity}, доступно: {panel.quantity}."
                )
                return
            
            if film.total_remaining < required_film:
                await message.answer(
                    f"Недостаточно пленки. Необходимо: {required_film:.2f}м, доступно: {film.total_remaining:.2f}м."
                )
                return
            
            # Списываем материалы
            panel.quantity -= quantity
            film.total_remaining -= required_film
            
            # Добавляем готовую продукцию
            finished_product = db.query(FinishedProduct).filter(
                FinishedProduct.film_id == film.id,
                FinishedProduct.thickness == panel_thickness
            ).first()
            
            if not finished_product:
                finished_product = FinishedProduct(
                    film_id=film.id,
                    quantity=0,
                    thickness=panel_thickness
                )
                db.add(finished_product)
            
            # Увеличиваем количество готовой продукции
            previous_quantity = finished_product.quantity
            finished_product.quantity += quantity
            
            # Создаем запись об операции
            operation = Operation(
                user_id=user.id,
                operation_type="production",
                quantity=quantity,
                details=json.dumps({
                    "film_color": film_color,
                    "film_consumption": required_film,
                    "panel_thickness": panel_thickness,
                    "previous_quantity": previous_quantity,
                    "new_quantity": finished_product.quantity
                })
            )
            db.add(operation)
            
            # Сохраняем изменения
            db.commit()
            
            # Возвращаемся в главное меню
            await state.set_state(MenuState.PRODUCTION_MAIN)
            keyboard = await get_role_menu_keyboard(MenuState.PRODUCTION_MAIN, message, state)
            
            await message.answer(
                f"✅ Производство выполнено!\n\n"
                f"Использовано:\n"
                f"- Панелей толщиной {panel_thickness} мм: {quantity} шт.\n"
                f"- Пленки {film_color}: {required_film:.2f}м\n\n"
                f"Произведено:\n"
                f"- Готовых панелей с пленкой {film_color}: {quantity} шт.\n\n"
                f"Остатки:\n"
                f"- Панелей толщиной {panel_thickness} мм: {panel.quantity} шт.\n"
                f"- Пленки {film_color}: {film.total_remaining:.2f}м\n"
                f"- Всего готовых панелей с пленкой {film_color}: {finished_product.quantity} шт.",
                reply_markup=keyboard
            )
            
        finally:
            db.close()
            
    except ValueError:
        await message.answer("Пожалуйста, введите целое число.")

# Обработка прихода пленки
@router.message(F.text == "🎨 Пленка")
async def handle_film(message: Message, state: FSMContext):
    if not await check_production_access(message):
        return
    
    current_state = await state.get_state()
    logging.info(f"Нажата кнопка 'Пленка', текущее состояние: {current_state}")
    
    if current_state == "ProductionStates:waiting_for_defect_type":
        logging.info("Перенаправляем в handle_film_defect, так как находимся в меню брака.")
        await handle_film_defect(message, state)
        return
    
    if current_state != MenuState.PRODUCTION_MATERIALS:
        logging.info(f"Пропускаем обработку, так как не в режиме добавления материалов")
        return
        
    db = next(get_db())
    try:
        films = db.query(Film).order_by(Film.code).all()
        
        keyboard_buttons = []
        row = []
        films_text_list = []
        
        if films:
            for film in films:
                button_text = film.code
                row.append(KeyboardButton(text=button_text))
                films_text_list.append(f"- {film.code} (остаток: {film.total_remaining} м)")
                if len(row) == 2:
                    keyboard_buttons.append(row)
                    row = []
            if row:
                keyboard_buttons.append(row)
        
        # Добавляем кнопку Назад
        keyboard_buttons.append([KeyboardButton(text="◀️ Назад")])
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=keyboard_buttons,
            resize_keyboard=True,
            input_field_placeholder="Выберите код или введите новый"
        )
        
        if films:
            films_text = "\n".join(films_text_list)
            await message.answer(
                f"Выберите код пленки для добавления или введите новый:\n\nТекущие коды в системе:\n{films_text}",
                reply_markup=keyboard
            )
        else:
            await message.answer(
                "Введите код новой пленки для добавления:",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="◀️ Назад")]],
                    resize_keyboard=True,
                    input_field_placeholder="Введите код новой пленки"
                )
            )
            
    finally:
        db.close()
        
    await state.set_state(ProductionStates.waiting_for_film_code)

@router.message(ProductionStates.waiting_for_film_code)
async def process_film_code(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.set_state(MenuState.PRODUCTION_MATERIALS)
        keyboard = await get_role_menu_keyboard(MenuState.PRODUCTION_MATERIALS, message, state)
        await message.answer("Выберите тип материала:", reply_markup=keyboard)
        return
    
    film_code = message.text.strip()
    if not film_code:
        await message.answer("Код пленки не может быть пустым. Попробуйте снова.")
        return

    db = next(get_db())
    try:
        film = db.query(Film).filter(Film.code == film_code).first()
        
        if not film:
            # Создаем новую запись пленки, если код не найден
            film = Film(
                code=film_code,
                total_remaining=0.0, # Начальный остаток 0
                # panel_consumption, meters_per_roll, thickness будут запрошены позже
            )
            db.add(film)
            db.commit()
            logging.info(f"Добавлен новый цвет пленки: {film_code}")
            await message.answer(f"👍 Добавлен новый цвет пленки: {film_code}")
        else:
            logging.info(f"Выбран существующий код пленки: {film_code}")

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

@router.message(ProductionStates.waiting_for_defect_type, F.text == "🎨 Пленка")
async def handle_film_defect(message: Message, state: FSMContext):
    logging.info("Специальный обработчик для брака пленки вызван")
    
    db = next(get_db())
    try:
        # Получаем список всех пленок, у которых есть остаток
        films = db.query(Film).filter(Film.total_remaining > 0).all()
        logging.info(f"Доступные пленки для брака: {[f.code for f in films]}")
        
        await state.update_data(defect_type="film")
        await state.set_state(ProductionStates.waiting_for_defect_film_color)
        
        # Если нет пленок в системе с остатком, сообщаем об этом
        if not films:
            await message.answer(
                "В системе нет ни одной пленки с положительным остатком. Сначала добавьте пленку через меню 'Приход сырья'.",
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION_DEFECT) # Возврат в меню брака
            )
            return

        # Формируем кнопки
        keyboard_buttons = []
        row = []
        films_text_list = [] # Список для текстового описания
        for film in films:
            button_text = film.code
            row.append(KeyboardButton(text=button_text))
            films_text_list.append(f"- {film.code} (остаток: {film.total_remaining} м)")
            # Группируем по 2 кнопки в ряду
            if len(row) == 2:
                keyboard_buttons.append(row)
                row = []
        if row: # Добавляем последний неполный ряд, если он есть
            keyboard_buttons.append(row)

        # Добавляем кнопку "Назад"
        keyboard_buttons.append([KeyboardButton(text="◀️ Назад")])

        keyboard = ReplyKeyboardMarkup(
            keyboard=keyboard_buttons,
            resize_keyboard=True
        )
        
        films_text = "\n".join(films_text_list)
        await message.answer(
            f"Выберите код бракованной пленки:\n\nДоступные варианты:\n{films_text}",
            reply_markup=keyboard
        )
    finally:
        db.close()

# Обработка брака
@router.message(F.text == "🚫 Брак")
async def handle_defect(message: Message, state: FSMContext):
    logging.info("Нажата кнопка 'Брак'")
    
    if not await check_production_access(message):
        logging.warning("Отказано в доступе к функциональности брака")
        return
    
    # Сбрасываем любые предыдущие данные в состоянии, которые могли остаться
    await state.clear()
    logging.info("Состояние очищено")
    
    # Логируем состояние перед установкой
    previous_state = await state.get_state()
    logging.info(f"Предыдущее состояние: {previous_state}")
    
    # Устанавливаем состояние ожидания выбора типа брака
    await state.set_state(ProductionStates.waiting_for_defect_type)
    
    # Проверяем, что состояние действительно установилось
    current_state = await state.get_state()
    logging.info(f"Установлено состояние: {current_state}")
    
    # Формируем клавиатуру для выбора типа брака
    keyboard = get_menu_keyboard(MenuState.PRODUCTION_DEFECT)
    logging.info(f"Сформирована клавиатура: {keyboard}")
    
    # Создаем дамп данных клавиатуры для отладки
    keyboard_data = []
    for row in keyboard.keyboard:
        keyboard_row = []
        for button in row:
            keyboard_row.append(button.text)
        keyboard_data.append(keyboard_row)
    logging.info(f"Кнопки клавиатуры: {keyboard_data}")
    
    await message.answer(
        "Выберите тип брака:",
        reply_markup=keyboard
    )
    logging.info("Отправлено сообщение с запросом типа брака")

# Обработчик для панелей в меню материалов
@router.message(F.text == "🪵 Панель")
async def handle_panel(message: Message, state: FSMContext):
    logging.info("Нажата кнопка 'Панель'")
    
    # Получаем текущее состояние
    current_state = await state.get_state()
    logging.info(f"Текущее состояние при нажатии кнопки 'Панель': {current_state}")
    
    # Проверяем, что мы находимся в режиме добавления материалов
    if current_state != MenuState.PRODUCTION_MATERIALS:
        logging.info("Пропускаем обработку обычной панели, так как находимся не в меню материалов")
        return
    
    # Устанавливаем тип операции (приход панелей)
    await state.update_data(operation_type="panel_income")
    
    # Запрашиваем толщину панелей
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="0.5")],
            [KeyboardButton(text="0.8")],
            [KeyboardButton(text="◀️ Назад")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "Выберите толщину панелей (мм):",
        reply_markup=keyboard
    )
    
    await state.set_state(ProductionStates.waiting_for_panel_thickness)
    logging.info(f"Установлено состояние waiting_for_panel_thickness")

@router.message(ProductionStates.waiting_for_defect_type, F.text == "⚙️ Стык")
async def process_joint_defect(message: Message, state: FSMContext):
    logging.info("Специальный обработчик для брака стыков вызван")
    
    db = next(get_db())
    try:
        # Получаем типы стыков, которые есть в наличии
        existing_types = db.query(Joint.type).filter(Joint.quantity > 0).distinct().all()
        existing_types = [t[0] for t in existing_types] # Распаковываем кортежи
        
        if not existing_types:
            await message.answer(
                "В базе нет ни одного типа стыков с положительным остатком.",
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION_DEFECT)
            )
            return
        
        # Маппинг enum на русские названия
        type_display_names = {
            JointType.BUTTERFLY: "Бабочка",
            JointType.SIMPLE: "Простой",
            JointType.CLOSING: "Замыкающий"
        }
        
        # Создаем кнопки только для существующих типов
        keyboard_buttons = []
        for joint_type in existing_types:
            display_name = type_display_names.get(joint_type, str(joint_type))
            keyboard_buttons.append([KeyboardButton(text=display_name)])
        
        keyboard_buttons.append([KeyboardButton(text="◀️ Назад")])
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=keyboard_buttons,
            resize_keyboard=True
        )
        
        await state.update_data(defect_type="joint_defect")
        await state.set_state(ProductionStates.waiting_for_defect_joint_type)
        
        await message.answer(
            "Выберите тип бракованных стыков:",
            reply_markup=keyboard
        )
        logging.info("Установлено состояние: waiting_for_defect_joint_type")
    finally:
        db.close()

@router.message(ProductionStates.waiting_for_defect_type, F.text == "🧴 Клей")
async def process_glue_defect(message: Message, state: FSMContext):
    logging.info("Специальный обработчик для брака клея вызван")
    
    # Сразу запрашиваем количество бракованного клея
    await state.update_data(defect_type="glue_defect")
    await state.set_state(ProductionStates.waiting_for_defect_glue_quantity)
    
    await message.answer(
        "Введите количество бракованного клея (в штуках):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Назад")]],
            resize_keyboard=True
        )
    )
    logging.info("Установлено состояние: waiting_for_defect_glue_quantity")

# Обработчик для количества бракованного клея
@router.message(ProductionStates.waiting_for_defect_glue_quantity)
async def process_defect_glue_quantity(message: Message, state: FSMContext):
    logging.info(f"Обработка количества бракованного клея: '{message.text}'")
    
    if message.text == "◀️ Назад":
        logging.info("Пользователь нажал Назад")
        await handle_defect(message, state)
        return
    
    try:
        quantity = int(message.text.strip())
        if quantity <= 0:
            await message.answer("Количество должно быть положительным числом.")
            return
        
        db = next(get_db())
        try:
            # Получаем текущее количество клея
            glue = db.query(Glue).first()
            if not glue:
                await message.answer(
                    "В системе не зарегистрирован клей. Сначала добавьте клей через меню 'Приход сырья'.",
                    reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MAIN)
                )
                return
            
            # Проверяем достаточность клея
            if glue.quantity < quantity:
                await message.answer(
                    f"Невозможно списать {quantity} шт. клея, доступно только {glue.quantity} шт."
                )
                return
            
            # Получаем пользователя из базы данных
            user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
            
            # Уменьшаем количество клея
            previous_quantity = glue.quantity
            glue.quantity -= quantity
            
            # Создаем запись операции
            operation = Operation(
                user_id=user.id,
                operation_type="glue_defect",
                quantity=quantity,
                details=json.dumps({
                    "previous_quantity": previous_quantity,
                    "new_quantity": glue.quantity,
                    "is_defect": True
                })
            )
            
            db.add(operation)
            db.commit()
            
            await message.answer(
                f"✅ Списано {quantity} шт. бракованного клея\n"
                f"Остаток: {glue.quantity} шт.",
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MAIN)
            )
            
        finally:
            db.close()
            
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число.")
        return
    
    await state.clear()

@router.message(ProductionStates.waiting_for_defect_joint_type)
async def process_defect_joint_type(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await handle_defect(message, state) # Возврат в меню выбора типа брака
        return
    
    # Маппинг русских названий обратно на enum
    type_reverse_mapping = {
        "Бабочка": JointType.BUTTERFLY,
        "Простой": JointType.SIMPLE,
        "Замыкающий": JointType.CLOSING
    }
    
    selected_type_enum = type_reverse_mapping.get(message.text)
    
    if not selected_type_enum:
        await message.answer("Пожалуйста, выберите тип стыка из предложенных кнопок.")
        # Можно переотправить клавиатуру с типами, если нужно
        # await handle_joint_defect(message, state)
        return
        
    await state.update_data(defect_joint_type=selected_type_enum)
    
    # Получаем доступные цвета для выбранного типа
    db = next(get_db())
    try:
        existing_colors = db.query(Joint.color).filter(
            Joint.type == selected_type_enum,
            Joint.quantity > 0
        ).distinct().all()
        existing_colors = [c[0] for c in existing_colors]
        
        if not existing_colors:
            await message.answer(
                f"Для типа стыка '{message.text}' нет доступных цветов с положительным остатком.",
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION_DEFECT)
            )
            await state.clear() # Сбрасываем состояние, т.к. дальше идти некуда
            return

        # Создаем кнопки для цветов
        keyboard_buttons = []
        row = []
        for color in existing_colors:
            row.append(KeyboardButton(text=color))
            if len(row) == 2:
                keyboard_buttons.append(row)
                row = []
        if row:
            keyboard_buttons.append(row)
            
        keyboard_buttons.append([KeyboardButton(text="◀️ Назад")])
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=keyboard_buttons,
            resize_keyboard=True
        )
        
        await message.answer(
            f"Выберите цвет бракованных стыков типа '{message.text}':",
            reply_markup=keyboard
        )
        await state.set_state(ProductionStates.waiting_for_defect_joint_color)
        
    finally:
        db.close()

# Обработчик для цвета бракованных стыков
@router.message(ProductionStates.waiting_for_defect_joint_color)
async def process_defect_joint_color(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        # Возвращаемся к выбору типа стыка
        await handle_joint_defect(message, state) 
        return
    
    selected_color = message.text
    data = await state.get_data()
    selected_type = data.get('defect_joint_type')
    
    if not selected_type:
        await message.answer("Произошла ошибка, не найден тип стыка. Попробуйте снова.")
        await handle_defect(message, state)
        return
        
    # Проверяем, что такой цвет существует для данного типа
    db = next(get_db())
    try:
        # Получаем доступные толщины для выбранного типа и цвета
        existing_thicknesses = db.query(Joint.thickness).filter(
            Joint.type == selected_type,
            Joint.color == selected_color,
            Joint.quantity > 0
        ).distinct().all()
        existing_thicknesses = [str(t[0]) for t in existing_thicknesses]
        
        if not existing_thicknesses:
            await message.answer(
                f"Для стыка типа '{selected_type.name}' цвета '{selected_color}' нет доступных толщин с положительным остатком.",
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION_DEFECT)
            )
            await state.clear()
            return
        
        await state.update_data(defect_joint_color=selected_color)
        
        # Создаем кнопки для толщины
        keyboard_buttons = []
        if "0.5" in existing_thicknesses:
            keyboard_buttons.append([KeyboardButton(text="0.5")])
        if "0.8" in existing_thicknesses:
             keyboard_buttons.append([KeyboardButton(text="0.8")])

        keyboard_buttons.append([KeyboardButton(text="◀️ Назад")])

        keyboard = ReplyKeyboardMarkup(
            keyboard=keyboard_buttons,
            resize_keyboard=True
        )

        await message.answer(
            f"Выберите толщину бракованных стыков (цвет: {selected_color}):",
            reply_markup=keyboard
        )
        await state.set_state(ProductionStates.waiting_for_defect_joint_thickness)
        
    finally:
        db.close()

# Обработчик для толщины бракованных стыков
@router.message(ProductionStates.waiting_for_defect_joint_thickness)
async def process_defect_joint_thickness(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        # Возвращаемся к выбору цвета
        data = await state.get_data()
        selected_type_enum = data.get('defect_joint_type')
        
        # Переотправляем клавиатуру с цветами для выбранного типа
        db = next(get_db())
        try:
            existing_colors = db.query(Joint.color).filter(
                Joint.type == selected_type_enum,
                Joint.quantity > 0
            ).distinct().all()
            existing_colors = [c[0] for c in existing_colors]

            keyboard_buttons = []
            row = []
            for color in existing_colors:
                row.append(KeyboardButton(text=color))
                if len(row) == 2:
                    keyboard_buttons.append(row)
                    row = []
            if row:
                keyboard_buttons.append(row)
            keyboard_buttons.append([KeyboardButton(text="◀️ Назад")])
            
            keyboard = ReplyKeyboardMarkup(
                keyboard=keyboard_buttons,
                resize_keyboard=True
            )
            
            # Получаем русское название типа
            type_display_names = {
                JointType.BUTTERFLY: "Бабочка",
                JointType.SIMPLE: "Простой",
                JointType.CLOSING: "Замыкающий"
            }
            type_name = type_display_names.get(selected_type_enum, str(selected_type_enum))

            await message.answer(
                f"Выберите цвет бракованных стыков типа '{type_name}':",
                reply_markup=keyboard
            )
        finally:
            db.close()
            
        await state.set_state(ProductionStates.waiting_for_defect_joint_color)
        return
    
    if message.text not in ["0.5", "0.8"]:
        await message.answer("Пожалуйста, выберите толщину из предложенных кнопок (0.5 или 0.8).")
        return
    
    selected_thickness = float(message.text)
    
    # Проверяем, существует ли стык с такими параметрами и положительным остатком
    data = await state.get_data()
    selected_type = data.get('defect_joint_type')
    selected_color = data.get('defect_joint_color')
    
    db = next(get_db())
    try:
        joint = db.query(Joint).filter(
            Joint.type == selected_type,
            Joint.color == selected_color,
            Joint.thickness == selected_thickness,
            Joint.quantity > 0
        ).first()
        
        if not joint:
             await message.answer(
                f"Стык с параметрами (Тип: {selected_type.name}, Цвет: {selected_color}, Толщина: {selected_thickness}) не найден или его остаток равен 0.",
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION_DEFECT)
            )
             await state.clear()
             return

        await state.update_data(defect_joint_thickness=selected_thickness)
        
        # Запрашиваем количество
        await message.answer(
            f"Введите количество бракованных стыков (доступно: {joint.quantity} шт.):",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="◀️ Назад")]],
                resize_keyboard=True
            )
        )
        await state.set_state(ProductionStates.waiting_for_defect_joint_quantity)
    finally:
        db.close()

# Обработчик для количества бракованных стыков
@router.message(ProductionStates.waiting_for_defect_joint_quantity)
async def process_defect_joint_quantity(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await message.answer(
            "Выберите толщину бракованных стыков:",
            reply_markup=get_joint_thickness_keyboard()
        )
        await state.set_state(ProductionStates.waiting_for_defect_joint_thickness)
        return
    
    try:
        quantity = int(message.text.strip())
        if quantity <= 0:
            await message.answer("Количество должно быть положительным числом.")
            return
        
        # Получаем данные состояния
        data = await state.get_data()
        
        db = next(get_db())
        try:
            # Получаем стык с заданными параметрами
            joint = db.query(Joint).filter(
                Joint.type == data["defect_joint_type"],
                Joint.color == data["defect_joint_color"],
                Joint.thickness == data["defect_joint_thickness"]
            ).first()
            
            if not joint:
                await message.answer(
                    "Стык с такими параметрами не найден в базе данных. Сначала добавьте такой стык через меню 'Приход сырья'.",
                    reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MAIN)
                )
                return
            
            # Проверяем достаточность стыков
            if joint.quantity < quantity:
                await message.answer(
                    f"Невозможно списать {quantity} шт. стыков, доступно только {joint.quantity} шт."
                )
                return
            
            # Получаем пользователя из базы данных
            user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
            
            # Получаем русское название типа стыка для отображения
            joint_type_names = {
                "butterfly": "Бабочка",
                "simple": "Простой",
                "closing": "Замыкающий"
            }
            joint_type_name = joint_type_names.get(data["defect_joint_type"].value, data["defect_joint_type"].value)
            
            # Уменьшаем количество стыков
            previous_quantity = joint.quantity
            joint.quantity -= quantity
            
            # Создаем запись операции
            operation = Operation(
                user_id=user.id,
                operation_type="joint_defect",
                quantity=quantity,
                details=json.dumps({
                    "joint_type": data["defect_joint_type"].value,
                    "joint_color": data["defect_joint_color"],
                    "joint_thickness": data["defect_joint_thickness"],
                    "previous_quantity": previous_quantity,
                    "new_quantity": joint.quantity,
                    "is_defect": True
                })
            )
            
            db.add(operation)
            db.commit()
            
            await message.answer(
                f"✅ Списано {quantity} шт. бракованных стыков\n"
                f"Тип: {joint_type_name}\n"
                f"Цвет: {data['defect_joint_color']}\n"
                f"Толщина: {data['defect_joint_thickness']} мм\n"
                f"Остаток: {joint.quantity} шт.",
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MAIN)
            )
            
        finally:
            db.close()
            
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число.")
        return
    
    await state.clear()

# Отладочный обработчик для всех сообщений в состоянии waiting_for_defect_type
# Этот обработчик должен быть ПОСЛЕДНИМ в файле
@router.message(ProductionStates.waiting_for_defect_type)
async def debug_defect_type_handler(message: Message, state: FSMContext):
    logging.info(f"Обработчик по умолчанию для кнопок типа брака, получено: '{message.text}'")
    
    # Проверяем что у нас запрос на брак с выбором типа
    if message.text == "🪵 Панель":
        # Этот случай должен быть перехвачен специфическим обработчиком, но на всякий случай:
        logging.info("Вызываем обработку для панели")
        await handle_panel_defect(message, state)
    elif message.text == "🎨 Пленка":
        # Вызываем обработчик для пленки
        logging.info("Вызываем обработку для пленки")
        try:
            await handle_film_defect(message, state)
        except Exception as e:
            logging.error(f"Ошибка при обработке брака пленки: {str(e)}")
            db = next(get_db())
            try:
                await message.answer(
                    "Произошла ошибка при обработке брака пленки. Пожалуйста, попробуйте снова.",
                    reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MAIN)
                )
            finally:
                db.close()
    elif message.text == "⚙️ Стык":
        logging.info("Обнаружена кнопка 'Стык', вызываем обработчик вручную")
        await process_joint_defect(message, state)
    elif message.text == "🧴 Клей":
        logging.info("Обнаружена кнопка 'Клей', вызываем обработчик вручную")
        await process_glue_defect(message, state)
    else:
        logging.info(f"Неизвестная кнопка: '{message.text}'")
        await message.answer("Пожалуйста, выберите тип брака из предложенных вариантов.")

@router.message(ProductionStates.waiting_for_panel_thickness)
async def process_panel_thickness(message: Message, state: FSMContext):
    logging.info(f"Обработка выбора толщины панелей: {message.text}")
    
    if message.text == "◀️ Назад":
        logging.info("Пользователь вернулся в меню материалов")
        await state.set_state(MenuState.PRODUCTION_MATERIALS)
        await message.answer(
            "Выберите тип материала:",
            reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MATERIALS)
        )
        return
    
    try:
        thickness = float(message.text.strip())
        if thickness not in [0.5, 0.8]:
            logging.warning(f"Указана некорректная толщина панели: {thickness}")
            await message.answer("Пожалуйста, выберите толщину 0.5 или 0.8 мм.")
            return
        
        # Сохраняем толщину в состоянии
        await state.update_data(panel_thickness=thickness)
        logging.info(f"Установлена толщина панели: {thickness}")
        
        # Запрашиваем количество панелей
        await message.answer(
            f"Введите количество панелей толщиной {thickness} мм:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="◀️ Назад")]],
                resize_keyboard=True
            )
        )
        await state.set_state(ProductionStates.waiting_for_panel_quantity)
        logging.info("Установлено состояние: waiting_for_panel_quantity")
    except ValueError:
        logging.error(f"Ошибка при обработке толщины панели: {message.text}")
        await message.answer("Пожалуйста, введите корректное число (0.5 или 0.8).")

@router.message(ProductionStates.waiting_for_panel_quantity)
async def process_panel_quantity(message: Message, state: FSMContext):
    logging.info(f"Обработка ввода количества панелей: {message.text}")
    
    if message.text == "◀️ Назад":
        logging.info("Возврат к выбору толщины панелей")
        
        # Возвращаемся к выбору толщины
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="0.5")],
                [KeyboardButton(text="0.8")],
                [KeyboardButton(text="◀️ Назад")]
            ],
            resize_keyboard=True
        )
        
        await message.answer(
            "Выберите толщину панелей (мм):",
            reply_markup=keyboard
        )
        await state.set_state(ProductionStates.waiting_for_panel_thickness)
        return
    
    try:
        quantity = int(message.text.strip())
        if quantity <= 0:
            logging.warning(f"Указано некорректное количество панелей: {quantity}")
            await message.answer("Пожалуйста, введите положительное число.")
            return
        
        # Получаем данные из состояния
        data = await state.get_data()
        thickness = data.get("panel_thickness", 0.5)
        
        logging.info(f"Добавление {quantity} панелей толщиной {thickness} мм")
        
        db = next(get_db())
        try:
            # Проверяем, есть ли уже панели с такой толщиной
            panel = db.query(Panel).filter(Panel.thickness == thickness).first()
            
            if panel:
                # Если панели существуют, увеличиваем их количество
                previous_quantity = panel.quantity
                panel.quantity += quantity
                logging.info(f"Обновлено количество панелей толщиной {thickness} мм: было {previous_quantity}, стало {panel.quantity}")
            else:
                # Если панелей с такой толщиной нет, создаем новую запись
                panel = Panel(thickness=thickness, quantity=quantity)
                db.add(panel)
                logging.info(f"Создана новая запись для панелей толщиной {thickness} мм с количеством {quantity}")
            
            # Получаем пользователя из базы данных
            user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
            
            # Создаем запись операции
            operation = Operation(
                user_id=user.id,
                operation_type="panel_income",
                quantity=quantity,
                details=json.dumps({
                    "panel_thickness": thickness,
                    "previous_quantity": previous_quantity if panel else 0,
                    "new_quantity": panel.quantity
                })
            )
            db.add(operation)
            
            # Сохраняем изменения
            db.commit()
            logging.info("Изменения сохранены в базе данных")
            
            # Возвращаемся в меню материалов
            await state.set_state(MenuState.PRODUCTION_MATERIALS)
            
            await message.answer(
                f"✅ Добавлено {quantity} панелей толщиной {thickness} мм.\n"
                f"Теперь у вас {panel.quantity} панелей толщиной {thickness} мм.",
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MATERIALS)
            )
            logging.info(f"Отправлено сообщение о добавлении панелей")
            
        finally:
            db.close()
            
    except ValueError:
        logging.error(f"Ошибка при обработке количества панелей: {message.text}")
        await message.answer("Пожалуйста, введите целое число.")

@router.message(F.text == "📦 Остатки")
async def handle_stock(message: Message, state: FSMContext):
    # Вместо прямого вызова cmd_stock используем новую функцию из warehouse
    # Добавляем импорт здесь, так как он больше не глобальный
    from handlers.warehouse import cmd_stock 
    logging.info(f"Production handle_stock вызван, вызываем cmd_stock из warehouse")
    await cmd_stock(message, state) # Передаем state
