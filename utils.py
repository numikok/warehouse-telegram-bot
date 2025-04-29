from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from sqlalchemy.orm import Session
from models import User, UserRole
from database import get_db
from navigation import MenuState
from aiogram.fsm.context import FSMContext

async def check_production_access(message: Message) -> bool:
    """
    Проверяет, имеет ли пользователь доступ к функциям производства
    (должен иметь роль PRODUCTION или SUPER_ADMIN)
    """
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or (user.role != UserRole.PRODUCTION and user.role != UserRole.SUPER_ADMIN):
            await message.answer("У вас нет прав для выполнения этой команды.")
            return False
        return True
    finally:
        db.close()

async def check_warehouse_access(message: Message) -> bool:
    """
    Проверяет, имеет ли пользователь доступ к функциям склада
    (должен иметь роль WAREHOUSE, SALES_MANAGER или SUPER_ADMIN)
    """
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or (user.role != UserRole.WAREHOUSE and user.role != UserRole.SUPER_ADMIN and user.role != UserRole.SALES_MANAGER):
            await message.answer("У вас нет прав для выполнения этой команды.")
            return False
        return True
    finally:
        db.close()

async def check_super_admin_access(message: Message) -> bool:
    """
    Проверяет, имеет ли пользователь права супер-администратора
    """
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or user.role != UserRole.SUPER_ADMIN:
            await message.answer("У вас нет прав для выполнения этой команды.")
            return False
        return True
    finally:
        db.close()

def format_quantity(quantity: float) -> str:
    """
    Форматирует число для отображения (убирает .0 если число целое)
    """
    if quantity == int(quantity):
        return str(int(quantity))
    return str(quantity)

async def get_role_menu_keyboard(menu_state: MenuState, message: Message, state: FSMContext):
    """
    Получает клавиатуру для заданного состояния меню, учитывая, является ли
    пользователь супер-админом, временно работающим в роли.
    
    Возвращает клавиатуру с кнопкой "Назад в админку", если это супер-админ,
    работающий в контексте другой роли.
    """
    # Избегаем циклического импорта
    from navigation import get_menu_keyboard
    
    # Проверяем, является ли пользователь супер-админом
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        is_admin = user and user.role == UserRole.SUPER_ADMIN
        
        # Получаем данные из состояния
        state_data = await state.get_data()
        is_admin_context = state_data.get("is_admin_context", False)
        
        # Если пользователь - супер-админ и находится в контексте другой роли,
        # возвращаем клавиатуру с кнопкой "Назад"
        if is_admin and is_admin_context:
            return get_menu_keyboard(menu_state, is_admin_context=True)
        else:
            return get_menu_keyboard(menu_state)
    finally:
        db.close() 