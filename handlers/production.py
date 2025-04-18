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
    
    # Проверяем, что мы действительно находимся в состоянии ожидания типа брака
    current_state = await state.get_state()
    logging.info(f"Текущее состояние: {current_state}")
    
    if current_state != "production_states:waiting_for_defect_type":
        logging.warning(f"Вызов handle_panel_defect в неправильном состоянии: {current_state}")
        return
    
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
        
        # Запрашиваем метраж бракованной пленки
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Назад")]],
            resize_keyboard=True
        )
        
        await message.answer(
            f"Введите метраж бракованной пленки цвета {film_color}:",
            reply_markup=keyboard
        )
        
        await state.set_state(ProductionStates.waiting_for_defect_film_meters)
    finally:
        db.close()

@router.message(ProductionStates.waiting_for_defect_film_meters)
async def process_defect_film_meters(message: Message, state: FSMContext):
    logging.info(f"Обработка метража бракованной пленки: '{message.text}'")
    
    if message.text == "◀️ Назад":
        logging.info("Пользователь нажал Назад")
        # Получаем сохраненные данные
        data = await state.get_data()
        film_color = data.get('defect_film_color', '')
        
        # Создаем клавиатуру для назад
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Назад")]],
            resize_keyboard=True
        )
        
        await message.answer(
            f"Выберите цвет/код бракованной пленки из списка:",
            reply_markup=keyboard
        )
        await state.set_state(ProductionStates.waiting_for_defect_film_color)
        return
    
    try:
        meters = float(message.text.strip())
        if meters <= 0:
            await message.answer("Метраж должен быть положительным числом.")
            return
        
        # Получаем данные состояния
        data = await state.get_data()
        film_color = data.get('defect_film_color', '')
        
        db = next(get_db())
        try:
            # Получаем пленку из базы данных
            film = db.query(Film).filter(Film.code == film_color).first()
            if not film:
                logging.warning(f"Пленка с цветом '{film_color}' не найдена в базе")
                await message.answer("Пленка с таким цветом не найдена в базе данных.")
                return
            
            # Проверяем достаточность пленки
            if film.total_remaining < meters:
                logging.warning(f"Недостаточно пленки: запрошено {meters}м, доступно {film.total_remaining}м")
                await message.answer(
                    f"Невозможно списать {meters}м пленки, доступно только {film.total_remaining}м."
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
                    "film_color": film_color,
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
                f"Цвет: {film_color}\n"
                f"Остаток: {film.total_remaining}м",
                reply_markup=get_menu_keyboard(MenuState.PRODUCTION_MAIN)
            )
            logging.info("Отправлено сообщение об успешном списании")
            
        finally:
            db.close()
            
    except ValueError:
        logging.warning(f"Введено некорректное значение: '{message.text}'")
        await message.answer("Пожалуйста, введите корректное число.")
        return
    
    logging.info("Сбрасываю состояние")
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
        "Выберите толщину панелей (мм):",
        reply_markup=keyboard
    )
    
    await state.update_data(operation_type="panel_income") # Указываем тип операции явно
    await state.set_state(ProductionStates.waiting_for_panel_thickness)

@router.message(ProductionStates.waiting_for_panel_thickness)
async def process_panel_thickness(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.set_state(MenuState.PRODUCTION_MATERIALS)
        keyboard = await get_role_menu_keyboard(MenuState.PRODUCTION_MATERIALS, message, state)
        await message.answer("Выберите тип материала:", reply_markup=keyboard)
        return
    
    try:
        thickness = float(message.text.strip())
        if thickness not in [0.5, 0.8]:
            await message.answer("Пожалуйста, выберите толщину 0.5 или 0.8 мм.")
            return
        
        # Сохраняем толщину панелей в состоянии
        await state.update_data(panel_thickness=thickness)
        
        # Запрашиваем количество пустых панелей
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="◀️ Назад")]],
            resize_keyboard=True
        )
        
        await message.answer(
            f"Введите количество пустых панелей (толщина: {thickness} мм):",
            reply_markup=keyboard
        )
        
        await state.set_state(ProductionStates.waiting_for_panel_quantity)
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число (0.5 или 0.8).")

@router.message(ProductionStates.waiting_for_panel_quantity)
async def process_panel_quantity(message: Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await message.answer(
            "Выберите толщину панелей (мм):",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="0.5")],
                    [KeyboardButton(text="0.8")],
                    [KeyboardButton(text="◀️ Назад")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(ProductionStates.waiting_for_panel_thickness)
        return
    
    try:
        quantity = int(message.text.strip())
        if quantity <= 0:
            await message.answer("Количество панелей должно быть положительным числом.")
            return
        
        # Проверяем, что мы в правильном контексте обработки прихода
        data = await state.get_data()
        operation_type = data.get("operation_type", "")
        panel_thickness = data.get("panel_thickness", 0.5)
        if operation_type != "panel_income":
            logging.warning(f"Неправильный тип операции: {operation_type}")
            await message.answer("Произошла ошибка. Пожалуйста, начните процесс заново.")
            await state.set_state(MenuState.PRODUCTION_MAIN)
            return
            
        db = next(get_db())
        try:
            # Получаем пользователя из базы данных
            user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
            
            # Получаем текущий запас панелей с указанной толщиной
            panel = db.query(Panel).filter(Panel.thickness == panel_thickness).first()
            
            if not panel:
                # Если записи о панелях с такой толщиной еще нет, создаем ее
                panel = Panel(
                    quantity=quantity, 
                    thickness=panel_thickness
                )
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
                    "panel_thickness": panel_thickness,
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
                f"Толщина: {panel_thickness} мм\n"
                f"Количество: {quantity} шт.\n"
                f"Предыдущий остаток: {previous_quantity} шт.\n"
                f"Текущий остаток: {panel.quantity} шт.",
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

# Обработка брака
@router.message(F.text == "🚫 Брак")
async def handle_defect(message: Message, state: FSMContext):
    logging.info("Нажата кнопка 'Брак'")
    
    if not await check_production_access(message):
        logging.warning("Отказано в доступе к функциональности брака")
        return
    
    # Сбрасываем любые предыдущие данные в состоянии, которые могли остаться
    await state.clear()
    
    logging.info("Устанавливаю состояние ожидания типа брака")
    # Устанавливаем состояние ожидания выбора типа брака
    await state.set_state(ProductionStates.waiting_for_defect_type)
    
    # Формируем клавиатуру для выбора типа брака
    keyboard = get_menu_keyboard(MenuState.PRODUCTION_DEFECT)
    logging.info(f"Сформирована клавиатура: {keyboard}")
    
    await message.answer(
        "Выберите тип брака:",
        reply_markup=keyboard
    )

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
