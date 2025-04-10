from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from models import User, UserRole, Film, Panel, Operation, FinishedProduct, Joint, Glue
from database import get_db
import pandas as pd
from datetime import datetime, timedelta
import json

router = Router()

class AdminStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_role = State()
    waiting_for_report_type = State()

@router.message(Command("users"))
async def cmd_users(message: Message, state: FSMContext = None):
    if not await check_super_admin(message):
        return
        
    db = next(get_db())
    try:
        users = db.query(User).all()
        
        response = "Список пользователей:\n\n"
        for user in users:
            response += f"ID: {user.telegram_id}\nПользователь: @{user.username}\nРоль: {user.role.value}\n\n"
        
        await message.answer(response)
        await message.answer(
            "Для назначения роли пользователю используйте команду /assign_role"
        )
    finally:
        db.close()

@router.message(Command("assign_role"))
async def cmd_assign_role(message: Message, state: FSMContext):
    if not await check_super_admin(message):
        return
        
    await message.answer(
        "Введите Telegram ID пользователя, которому хотите назначить роль:"
    )
    await state.set_state(AdminStates.waiting_for_user_id)

@router.message(AdminStates.waiting_for_user_id)
async def process_user_id(message: Message, state: FSMContext):
    try:
        user_id = int(message.text)
        await state.update_data(user_id=user_id)
        
        # Создаем клавиатуру с кнопками для выбора роли
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="👑 Супер-администратор")],
                [KeyboardButton(text="💼 Менеджер по продажам")],
                [KeyboardButton(text="🏭 Производство")],
                [KeyboardButton(text="📦 Роль: Склад")]
            ],
            resize_keyboard=True
        )
        
        roles_text = "Выберите роль для пользователя:"
        await message.answer(roles_text, reply_markup=keyboard)
        await state.set_state(AdminStates.waiting_for_role)
    except ValueError:
        await message.answer("Пожалуйста, введите корректный числовой ID.")

@router.message(AdminStates.waiting_for_role)
async def process_role(message: Message, state: FSMContext):
    # Маппинг текста кнопок на значения ролей
    role_mapping = {
        "👑 Супер-администратор": UserRole.SUPER_ADMIN,
        "💼 Менеджер по продажам": UserRole.SALES_MANAGER,
        "🏭 Производство": UserRole.PRODUCTION,
        "📦 Роль: Склад": UserRole.WAREHOUSE
    }
    
    selected_role = role_mapping.get(message.text)
    
    if not selected_role:
        await message.answer(
            "Пожалуйста, выберите роль, используя кнопки.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="👑 Супер-администратор")],
                    [KeyboardButton(text="💼 Менеджер по продажам")],
                    [KeyboardButton(text="🏭 Производство")],
                    [KeyboardButton(text="📦 Роль: Склад")]
                ],
                resize_keyboard=True
            )
        )
        return
    
    try:
        data = await state.get_data()
        user_id = data['user_id']
        
        db = next(get_db())
        try:
            user = db.query(User).filter(User.telegram_id == user_id).first()
            
            if user:
                # Обновляем роль существующего пользователя
                old_role = user.role.value
                user.role = selected_role
                db.commit()
                
                await message.answer(
                    f"✅ Роль пользователя @{user.username} изменена с {old_role} на {selected_role.value}\n"
                    f"ID пользователя: {user.telegram_id}",
                    reply_markup=ReplyKeyboardRemove()
                )
                
                # Отправляем уведомление пользователю о смене роли
                try:
                    keyboard = get_role_keyboard(selected_role)
                    await message.bot.send_message(
                        user_id,
                        f"🔄 Ваша роль изменена на: {selected_role.value}\n"
                        "Используйте кнопки ниже для работы с ботом:",
                        reply_markup=keyboard
                    )
                except Exception as e:
                    await message.answer(
                        "⚠️ Не удалось отправить уведомление пользователю.\n"
                        "Возможно, пользователь заблокировал бота."
                    )
            else:
                # Создаем нового пользователя с выбранной ролью
                new_user = User(
                    telegram_id=user_id,
                    username="pending",  # Будет обновлено когда пользователь напишет боту
                    role=selected_role
                )
                db.add(new_user)
                db.commit()
                
                await message.answer(
                    f"✅ Создан новый пользователь с ID {user_id} и ролью {selected_role.value}\n"
                    "Username будет обновлен при первом обращении пользователя к боту.",
                    reply_markup=ReplyKeyboardRemove()
                )
                
                # Отправляем сообщение новому пользователю
                try:
                    keyboard = get_role_keyboard(selected_role)
                    await message.bot.send_message(
                        user_id,
                        f"👋 Вам назначена роль: {selected_role.value}\n"
                        "Используйте кнопки ниже для работы с ботом:",
                        reply_markup=keyboard
                    )
                except Exception as e:
                    await message.answer(
                        "⚠️ Пользователь создан, но не удалось отправить ему сообщение.\n"
                        "Возможно, пользователь еще не начал диалог с ботом."
                    )
        finally:
            db.close()
    except Exception as e:
        await message.answer(
            f"❌ Произошла ошибка при назначении роли: {str(e)}",
            reply_markup=ReplyKeyboardRemove()
        )
    finally:
        await state.clear()

def get_role_keyboard(role: UserRole) -> ReplyKeyboardMarkup:
    """Создает клавиатуру с кнопками в зависимости от роли пользователя."""
    buttons = []
    
    if role == UserRole.SUPER_ADMIN:
        buttons = [
            [KeyboardButton(text="👥 Пользователи"), KeyboardButton(text="📊 Отчеты")],
            [KeyboardButton(text="📦 Склад"), KeyboardButton(text="🏭 Производство")],
            [KeyboardButton(text="💼 Продажи")]
        ]
    elif role == UserRole.SALES_MANAGER:
        buttons = [
            [KeyboardButton(text="📝 Составить заказ")],
            [KeyboardButton(text="📦 Количество готовой продукции")]
        ]
    elif role == UserRole.PRODUCTION:
        buttons = [
            [KeyboardButton(text="📥 Приход материалов")],
            [KeyboardButton(text="🏭 Производство")]
        ]
    elif role == UserRole.WAREHOUSE:
        buttons = [
            [KeyboardButton(text="📦 Склад")],
            [KeyboardButton(text="✅ Подтвердить отгрузку")]
        ]
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

@router.message(Command("report"))
async def cmd_report(message: Message, state: FSMContext = None):
    if not await check_super_admin(message):
        return
        
    db = next(get_db())
    try:
        # Получаем остатки готовой продукции
        finished_products = db.query(FinishedProduct).join(Film).all()
        inventory = "Текущие запасы готовой продукции:\n\n"
        for product in finished_products:
            inventory += f"Код панели: {product.film.code}\n"
            inventory += f"Количество: {product.quantity}\n\n"
        
        # Получаем остатки пленки
        films = db.query(Film).all()
        films_inventory = "Запасы пленки:\n\n"
        for film in films:
            films_inventory += f"Код: {film.code}\n"
            films_inventory += f"В наличии рулонов: {film.in_stock}\n"
            films_inventory += f"Толщина рулона: {film.roll_thickness} мм\n"
            films_inventory += f"Остаток в рулоне: {film.remaining_in_roll}\n"
            films_inventory += f"Расход на панель: {film.panel_consumption} м\n"
            films_inventory += f"Можно произвести панелей: {film.calculate_possible_panels()}\n\n"
        
        # Получаем остатки стыков
        joints = db.query(Joint).all()
        joints_inventory = "Запасы стыков:\n\n"
        for joint in joints:
            joints_inventory += f"Цвет: {joint.color}\n"
            joints_inventory += f"Количество: {joint.quantity}\n\n"
        
        # Получаем остатки клея
        glue = db.query(Glue).first()
        glue_inventory = "Запасы клея:\n\n"
        if glue:
            glue_inventory += f"Количество: {glue.quantity}\n\n"
        else:
            glue_inventory += "Нет в наличии\n\n"
        
        # Получаем последние операции
        operations = db.query(Operation).order_by(Operation.timestamp.desc()).limit(10).all()
        recent_ops = "Последние операции:\n\n"
        for op in operations:
            user = db.query(User).filter(User.id == op.user_id).first()
            recent_ops += f"Тип: {op.operation_type}\n"
            recent_ops += f"Количество: {op.quantity}\n"
            recent_ops += f"Дата: {op.timestamp.strftime('%d.%m.%Y %H:%M')}\n"
            recent_ops += f"Пользователь: {user.username}\n"
            if op.details:
                details = json.loads(op.details)
                if op.operation_type == "order":
                    recent_ops += f"Заказ:\n"
                    recent_ops += f"- Панели {details['film_code']}: {details['panel_quantity']} шт.\n"
                    recent_ops += f"- Стыки {details['joint_color']}: {details['joint_quantity']} шт.\n"
                    recent_ops += f"- Клей: {details['glue_quantity']} шт.\n"
                    recent_ops += f"- Монтаж: {'Да' if details['installation'] else 'Нет'}\n"
                elif op.operation_type == "income":
                    recent_ops += f"Приход материалов:\n"
                    recent_ops += f"- Тип: {details.get('material_type', 'Н/Д')}\n"
                    recent_ops += f"- Количество: {details.get('quantity', 'Н/Д')}\n"
            recent_ops += "\n"
        
        await message.answer(inventory)
        await message.answer(films_inventory)
        await message.answer(joints_inventory)
        await message.answer(glue_inventory)
        await message.answer(recent_ops)
    finally:
        db.close()

async def check_super_admin(message: Message) -> bool:
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        
        if not user or user.role != UserRole.SUPER_ADMIN:
            await message.answer("У вас нет прав для выполнения этой команды.")
            return False
        return True
    finally:
        db.close()

@router.message(Command("report"))
async def cmd_report(message: Message, state: FSMContext):
    db = next(get_db())
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    if not user or user.role != UserRole.SUPER_ADMIN:
        await message.answer("У вас нет доступа к этой команде.")
        return
    
    report_text = "Выберите тип отчета:\n\n"
    report_text += "1. Остатки материалов\n"
    report_text += "2. Производство за период\n"
    report_text += "3. История операций\n"
    
    await state.set_state(AdminStates.waiting_for_report_type)
    await message.answer(report_text)

@router.message(AdminStates.waiting_for_report_type)
async def process_report_type(message: Message, state: FSMContext):
    db = next(get_db())
    report_type = message.text
    
    if report_type == "1":
        # Остатки материалов
        colors = db.query(Color).all()
        panels = db.query(Panel).all()
        films = db.query(Film).all()
        finished = db.query(FinishedProduct).all()
        
        report = "📊 Отчет по остаткам:\n\n"
        report += "🎨 Цвета:\n"
        for color in colors:
            report += f"- {color.marking}: {color.length}м (толщина {color.thickness}мм)\n"
        
        report += "\n📦 Панели:\n"
        for panel in panels:
            report += f"- {panel.quantity} шт.\n"
        
        report += "\n🎞 Пленка:\n"
        for film in films:
            report += f"- {film.remaining_length}м из {film.total_length}м\n"
        
        report += "\n✅ Готовая продукция:\n"
        for product in finished:
            color = db.query(Color).filter(Color.id == product.color_id).first()
            report += f"- {color.marking}: {product.quantity} шт.\n"
        
        await message.answer(report)
        
    elif report_type == "2":
        # Производство за период
        today = datetime.now()
        week_ago = today - timedelta(days=7)
        
        production = db.query(Operation).filter(
            Operation.type == "production",
            Operation.created_at >= week_ago
        ).all()
        
        report = "📊 Отчет по производству за неделю:\n\n"
        for op in production:
            color = db.query(Color).filter(Color.id == op.color_id).first()
            report += f"- {op.created_at.strftime('%d.%m.%Y')}: {color.marking} - {op.quantity} шт.\n"
        
        await message.answer(report)
        
    elif report_type == "3":
        # История операций
        operations = db.query(Operation).order_by(Operation.created_at.desc()).limit(20).all()
        
        report = "📊 Последние операции:\n\n"
        for op in operations:
            user = db.query(User).filter(User.id == op.user_id).first()
            report += f"- {op.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            report += f"  Тип: {op.type}\n"
            report += f"  Пользователь: {user.username}\n"
            report += f"  Количество: {op.quantity}\n\n"
        
        await message.answer(report)
    
    else:
        await message.answer("Неверный тип отчета. Пожалуйста, выберите 1, 2 или 3.")
        return
    
    await state.clear() 