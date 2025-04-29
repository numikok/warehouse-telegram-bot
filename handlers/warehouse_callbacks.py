from aiogram import Router, F
from aiogram.types import CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from models import User, UserRole, FinishedProduct
from database import get_db
from navigation import MenuState, get_menu_keyboard
from states import SalesStates
import logging

router = Router()

@router.callback_query(F.data.startswith("order_finished:"))
async def process_order_finished(callback_query: CallbackQuery, state: FSMContext):
    """Обработка выбора товара со склада по callback-запросу"""
    # Получаем ID выбранного товара
    product_id = int(callback_query.data.split(":")[1])
    
    db = next(get_db())
    try:
        # Получаем продукт по ID
        product = db.query(FinishedProduct).filter(FinishedProduct.id == product_id).first()
        
        if not product or product.quantity <= 0:
            await callback_query.answer("Товар не найден или недоступен на складе")
            await callback_query.message.answer("Пожалуйста, выберите другой товар или вернитесь в меню")
            return
        
        # Сохраняем выбранный товар в состоянии
        await state.update_data(selected_product_id=product_id)
        
        # Запрашиваем количество
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="◀️ Назад")]
            ],
            resize_keyboard=True
        )
        
        await callback_query.message.answer(
            f"Выбран товар: {product.film_color} (толщина {product.thickness} мм)\n"
            f"Доступно на складе: {product.quantity} шт.\n\n"
            f"Введите необходимое количество (максимум {product.quantity}):",
            reply_markup=keyboard
        )
        
        # Переходим к вводу количества
        await state.set_state(SalesStates.waiting_for_panel_quantity)
    finally:
        db.close()
    
    # Отвечаем на callback, чтобы убрать индикатор загрузки
    await callback_query.answer()

@router.callback_query(F.data == "cancel_order")
async def process_cancel_order(callback_query: CallbackQuery, state: FSMContext):
    """Обработка отмены заказа со склада"""
    # Получаем данные состояния
    data = await state.get_data()
    is_admin_context = data.get("is_admin_context", False)
    
    # Возвращаемся в главное меню
    await state.set_state(MenuState.SALES_MAIN)
    
    await callback_query.message.answer(
        "Заказ отменен. Выберите действие:",
        reply_markup=get_menu_keyboard(MenuState.SALES_MAIN, is_admin_context=is_admin_context)
    )
    
    # Отвечаем на callback, чтобы убрать индикатор загрузки
    await callback_query.answer() 