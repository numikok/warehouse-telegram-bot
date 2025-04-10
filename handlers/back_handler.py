from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from models import User, UserRole
from database import get_db
from navigation import MenuState, get_menu_keyboard, go_back

router = Router()

@router.message(F.text == "◀️ Назад")
async def handle_back(message: Message, state: FSMContext):
    """Общий обработчик для кнопки 'Назад' во всех меню"""
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            await message.answer("Пожалуйста, начните с команды /start")
            return
        
        # Получаем данные из состояния, включая флаг контекста админа
        state_data = await state.get_data()
        is_admin_context = state_data.get("is_admin_context", False)
        
        next_menu, keyboard = await go_back(state, user.role)
        await state.set_state(next_menu)
        
        # Если есть флаг контекста админа и перешли в главное меню роли,
        # добавляем кнопку возврата в админку
        if is_admin_context and next_menu in [
            MenuState.SALES_MAIN, MenuState.WAREHOUSE_MAIN, MenuState.PRODUCTION_MAIN
        ]:
            keyboard = get_menu_keyboard(next_menu, is_admin_context=True)
        
        await message.answer(
            "Выберите действие:",
            reply_markup=keyboard
        )
    finally:
        db.close() 