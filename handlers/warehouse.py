from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from models import User, UserRole, Film, Panel, Joint, Glue, Operation, FinishedProduct, Order, CompletedOrder, OrderStatus, JointType, CompletedOrderJoint, CompletedOrderItem, CompletedOrderGlue
from database import get_db
import json
import logging
from navigation import MenuState, get_menu_keyboard, go_back
from datetime import datetime

router = Router()

def get_main_keyboard():
    """Возвращает основную клавиатуру для складовщика"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Остатки на складе")],
            [KeyboardButton(text="📥 Оприходовать материалы")],
            [KeyboardButton(text="📦 Подтвердить отгрузку")],
            [KeyboardButton(text="📋 Мои заказы")]
        ],
        resize_keyboard=True
    )

class WarehouseStates(StatesGroup):
    waiting_for_order_id = State()
    waiting_for_confirmation = State()

@router.message(Command("stock"))
async def cmd_stock(message: Message, state: FSMContext):
    # Не проверяем доступ, так как эта функция теперь может вызываться с разными ролями
    
    db = next(get_db())
    try:
        state_data = await state.get_data()
        is_admin_context = state_data.get("is_admin_context", False)
        
        # Получаем текущую роль пользователя для выбора правильной клавиатуры
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        user_role = user.role if user else UserRole.NONE
        
        # Получаем остатки по всем материалам
        films = db.query(Film).all()
        joints = db.query(Joint).all()
        glue = db.query(Glue).first()
        panels = db.query(Panel).all()  # Получаем все панели вместо одной
        finished_products = db.query(FinishedProduct).join(Film).all()
        
        # Формируем отчет по пленкам
        response = "📊 Остатки на складе:\n\n"
        
        response += "🎞 Пленки:\n"
        for film in films:
            meters_per_roll = film.meters_per_roll or 50.0  # По умолчанию 50 метров в рулоне
            rolls = film.total_remaining / meters_per_roll if meters_per_roll > 0 else 0
            response += (
                f"- {film.code}:\n"
                f"  • Рулонов: {rolls:.1f}\n"
                f"  • Общая длина: {film.total_remaining:.2f} м\n"
                f"  • Можно произвести панелей: {film.calculate_possible_panels()}\n\n"
            )
        
        response += "🔄 Стыки:\n"
        for joint in joints:
            response += (
                f"- {joint.color} ({joint.type.value}, {joint.thickness} мм):\n"
                f"  • Количество: {joint.quantity}\n"
            )
        
        response += "\n📦 Пустые панели:\n"
        if panels:
            for panel in panels:
                response += f"- Толщина {panel.thickness} мм: {panel.quantity} шт.\n"
        else:
            response += "Нет в наличии\n"
            
        response += "\n🧪 Клей:\n"
        if glue:
            response += f"Количество: {glue.quantity}\n"
        else:
            response += "Нет в наличии\n"
            
        response += "\n✅ Готовые панели:\n"
        if finished_products:
            for product in finished_products:
                response += f"- {product.film.code} (толщина {product.thickness} мм): {product.quantity} шт.\n"
        else:
            response += "Нет в наличии\n"
        
        # Выбираем правильную клавиатуру в зависимости от роли пользователя
        if user_role == UserRole.WAREHOUSE:
            keyboard = get_menu_keyboard(MenuState.WAREHOUSE_MAIN, is_admin_context)
        elif user_role == UserRole.PRODUCTION:
            keyboard = get_menu_keyboard(MenuState.PRODUCTION_MAIN)
        else:
            # Для суперадмина и других ролей
            keyboard = get_menu_keyboard(MenuState.SUPER_ADMIN_MAIN) if user_role == UserRole.SUPER_ADMIN else None
        
        await message.answer(response, reply_markup=keyboard)
    finally:
        db.close()

@router.message(Command("income_materials"))
async def cmd_income_materials(message: Message, state: FSMContext):
    if not await check_warehouse_access(message):
        return
    
    await state.set_state(MenuState.WAREHOUSE_MATERIALS)
    await message.answer(
        "Выберите тип материала для оприходования:",
        reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MATERIALS)
    )
    await state.set_state(WarehouseStates.waiting_for_order_id)

@router.message(WarehouseStates.waiting_for_order_id)
async def process_order_id(message: Message, state: FSMContext):
    order_id = message.text
    
    if not order_id.isdigit():
        await message.answer("Пожалуйста, введите корректный номер заказа.")
        return
        
    await state.update_data(order_id=int(order_id))
    
    await message.answer("Подтвердите отгрузку заказа:")
    await state.set_state(WarehouseStates.waiting_for_confirmation)

@router.message(WarehouseStates.waiting_for_confirmation)
async def process_confirmation(message: Message, state: FSMContext):
    confirmation = message.text.lower()
    
    if confirmation not in ["да", "нет"]:
        await message.answer("Пожалуйста, ответьте да или нет.")
        return
        
    data = await state.get_data()
    order_id = data["order_id"]
    
    await process_order_shipment(message, order_id)

@router.message(Command("confirm_order"))
async def cmd_confirm_order(message: Message, state: FSMContext):
    """Обработка команды для просмотра активных заказов"""
    if not await check_warehouse_access(message):
        return
        
    await display_active_orders(message)

async def display_active_orders(message: Message):
    """Отображает список активных заказов для подтверждения отгрузки"""
    db = next(get_db())
    try:
        # Получаем все активные заказы со статусом NEW
        orders = db.query(Order).filter(Order.status == OrderStatus.NEW).all()
        
        if not orders:
            await message.answer(
                "📦 Нет активных заказов для отгрузки.",
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
            )
            return
            
        # Формируем сообщение со списком заказов
        response = "📦 Активные заказы для отгрузки:\n\n"
        
        for order in orders:
            # Получаем имя менеджера
            manager = db.query(User).filter(User.id == order.manager_id).first()
            manager_name = manager.username if manager else "Неизвестный менеджер"
            
            # Формируем информацию о продуктах
            products_info = ""
            if hasattr(order, 'products') and order.products:
                products_info = "🎨 Продукция:\n"
                for product in order.products:
                    try:
                        # Извлекаем всю доступную информацию о продукте
                        product_desc = []
                        
                        # Проверяем каждый атрибут, используя безопасные методы доступа
                        color = getattr(product, 'color', "Не указан")
                        if color:
                            product_desc.append(f"цвет: {color}")
                            
                        thickness = getattr(product, 'thickness', None)
                        if thickness is not None:
                            product_desc.append(f"толщина: {thickness} мм")
                            
                        quantity = getattr(product, 'quantity', None)
                        if quantity is not None:
                            product_desc.append(f"кол-во: {quantity} шт")
                        
                        if product_desc:
                            products_info += f"  • {', '.join(product_desc)}\n"
                        else:
                            products_info += "  • Продукция (данные недоступны)\n"
                    except Exception as e:
                        logging.error(f"Error displaying product: {str(e)}")
                        products_info += "  • Продукция (ошибка чтения данных)\n"
            else:
                # Для поддержки старой структуры
                try:
                    if hasattr(order, 'film_code') and order.film_code:
                        products_info = "🎨 Продукция:\n"
                        
                        # Собираем информацию о продукте из старой структуры
                        product_desc = []
                        
                        if order.film_code:
                            product_desc.append(f"цвет: {order.film_code}")
                            
                        if hasattr(order, 'panel_thickness'):
                            product_desc.append(f"толщина: {order.panel_thickness} мм")
                            
                        if hasattr(order, 'panel_quantity'):
                            product_desc.append(f"кол-во: {order.panel_quantity} шт")
                            
                        if product_desc:
                            products_info += f"  • {', '.join(product_desc)}\n"
                        else:
                            products_info += "  • Продукция (данные недоступны)\n"
                except Exception as e:
                    logging.error(f"Ошибка при отображении продукта из старой структуры: {str(e)}")
                    products_info += "  • Продукция (ошибка чтения данных)\n"
            
            # Формируем информацию о стыках
            joints_info = ""
            if hasattr(order, 'joints') and order.joints:
                joints_info = "🔗 Стыки:\n"
                for joint in order.joints:
                    try:
                        # Извлекаем всю доступную информацию о стыке
                        joint_desc = []
                        
                        # Тип стыка
                        joint_type_text = "Не указан"
                        if hasattr(joint, 'joint_type'):
                            try:
                                if joint.joint_type == JointType.BUTTERFLY:
                                    joint_type_text = "Бабочка"
                                elif joint.joint_type == JointType.SIMPLE:
                                    joint_type_text = "Простые"
                                elif joint.joint_type == JointType.CLOSING:
                                    joint_type_text = "Замыкающие"
                                else:
                                    joint_type_text = str(joint.joint_type)
                                joint_desc.append(joint_type_text)
                            except Exception as e:
                                logging.error(f"Error processing joint type: {str(e)}")
                                joint_desc.append("тип: Не удалось определить")
                        
                        # Цвет стыка
                        joint_color = getattr(joint, 'joint_color', None)
                        if joint_color:
                            joint_desc.append(f"цвет: {joint_color}")
                            
                        # Толщина стыка
                        thickness = getattr(joint, 'joint_thickness', None)
                        if thickness is not None:
                            joint_desc.append(f"толщина: {thickness} мм")
                            
                        # Количество стыков
                        quantity = getattr(joint, 'quantity', None)
                        if quantity is None:
                            quantity = getattr(joint, 'joint_quantity', 0)
                        if quantity:
                            joint_desc.append(f"кол-во: {quantity} шт")
                        
                        if joint_desc:
                            joints_info += f"  • {', '.join(joint_desc)}\n"
                        else:
                            joints_info += "  • Стык (данные недоступны)\n"
                    except Exception as e:
                        logging.error(f"Error displaying joint: {str(e)}")
                        joints_info += "  • Стык (ошибка чтения данных)\n"
            else:
                # Пытаемся использовать устаревшие свойства, если они есть
                try:
                    if hasattr(order, 'joint_quantity') and order.joint_quantity and order.joint_quantity > 0:
                        joint_type_text = "Не указан"
                        try:
                            if hasattr(order, 'joint_type'):
                                if order.joint_type == JointType.BUTTERFLY:
                                    joint_type_text = "Бабочка"
                                elif order.joint_type == JointType.SIMPLE:
                                    joint_type_text = "Простые"
                                elif order.joint_type == JointType.CLOSING:
                                    joint_type_text = "Замыкающие"
                        except:
                            pass
                            
                        joint_color = "Не указан"
                        try:
                            if hasattr(order, 'joint_color'):
                                joint_color = order.joint_color
                        except:
                            pass
                            
                        joints_info = f"🔗 Стыки: {joint_type_text}, {joint_color}: {order.joint_quantity} шт.\n"
                    else:
                        joints_info = "🔗 Стыки: Нет\n"
                except:
                    joints_info = "🔗 Стыки: Нет\n"
            
            # Получаем информацию о количестве клея
            glue_quantity = 0
            if hasattr(order, 'glues') and order.glues:
                try:
                    glue_quantity = sum(getattr(glue, 'quantity', 0) for glue in order.glues)
                except Exception as e:
                    logging.error(f"Ошибка при извлечении данных о клее: {str(e)}")
            else:
                # Если нет glues, пробуем получить атрибуты напрямую из заказа (старая структура)
                glue_quantity = getattr(order, 'glue_quantity', 0)
                
            response += (
                f"📝 Заказ #{order.id}\n"
                f"📆 Дата: {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                f"👤 Менеджер: {manager_name}\n"
                f"{products_info}"
                f"{joints_info}"
                f"🧴 Клей: {glue_quantity} шт.\n"
                f"🔧 Монтаж: {'Требуется' if order.installation_required else 'Не требуется'}\n"
                f"📞 Телефон: {order.customer_phone}\n"
                f"🚚 Адрес: {order.delivery_address}\n"
                f"-----\n"
                f"✅ Для подтверждения отгрузки заказа #{order.id} отправьте:\n/confirm_{order.id}\n\n"
            )
        
        await message.answer(
            response,
            reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_ORDERS)
        )
    finally:
        db.close()

@router.message(F.text == "📦 Мои заказы")
async def handle_orders(message: Message, state: FSMContext):
    """Обработка нажатия на кнопку 'Мои заказы'"""
    if not await check_warehouse_access(message):
        return
    
    # Вызываем функцию для отображения активных заказов
    await display_active_orders(message)

@router.message(F.text == "📦 Остатки")
async def handle_stock(message: Message, state: FSMContext):
    # Вместо вызова cmd_stock, переходим в меню категорий остатков
    await state.set_state(MenuState.INVENTORY_CATEGORIES)
    
    # Получаем текущую роль пользователя
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        user_role = user.role if user else UserRole.NONE
        
        # Сохраняем роль и исходное меню, чтобы знать, куда возвращаться
        if user_role == UserRole.WAREHOUSE:
            await state.update_data(source_menu=MenuState.WAREHOUSE_MAIN)
        elif user_role == UserRole.PRODUCTION:
            await state.update_data(source_menu=MenuState.PRODUCTION_MAIN)
        elif user_role == UserRole.SUPER_ADMIN:
            await state.update_data(source_menu=MenuState.SUPER_ADMIN_MAIN)
        else:
            await state.update_data(source_menu=MenuState.WAREHOUSE_MAIN)  # По умолчанию
        
        # Получаем клавиатуру для меню категорий
        keyboard = get_menu_keyboard(MenuState.INVENTORY_CATEGORIES)
        
        await message.answer(
            "Выберите категорию остатков для просмотра:",
            reply_markup=keyboard
        )
    finally:
        db.close()

# Обработчик для всех остатков сразу
@router.message(F.text == "📊 Все остатки")
async def handle_all_stock(message: Message, state: FSMContext):
    # Вызываем старую функцию показа всех остатков
    await cmd_stock(message, state)

# Обработчик для готовой продукции
@router.message(F.text == "✅ Готовая продукция")
async def handle_finished_products(message: Message, state: FSMContext):
    await state.set_state(MenuState.INVENTORY_FINISHED_PRODUCTS)
    
    db = next(get_db())
    try:
        # Получаем список готовой продукции
        finished_products = db.query(FinishedProduct).join(Film).all()
        
        response = "✅ Готовая продукция на складе:\n\n"
        if finished_products:
            for product in finished_products:
                if product.quantity > 0:
                    response += f"- {product.film.code} (толщина {product.thickness} мм): {product.quantity} шт.\n"
        else:
            response += "Нет в наличии\n"
        
        # Возвращаем клавиатуру для возврата в меню категорий
        keyboard = get_menu_keyboard(MenuState.INVENTORY_FINISHED_PRODUCTS)
        await message.answer(response, reply_markup=keyboard)
    finally:
        db.close()

# Обработчик для пленки
@router.message(F.text == "🎞 Пленка")
async def handle_films(message: Message, state: FSMContext):
    await state.set_state(MenuState.INVENTORY_FILMS)
    
    db = next(get_db())
    try:
        # Получаем список пленок
        films = db.query(Film).all()
        
        response = "🎞 Пленки на складе:\n\n"
        if films:
            for film in films:
                meters_per_roll = film.meters_per_roll or 50.0  # По умолчанию 50 метров в рулоне
                rolls = film.total_remaining / meters_per_roll if meters_per_roll > 0 else 0
                response += (
                    f"- {film.code}:\n"
                    f"  • Рулонов: {rolls:.1f}\n"
                    f"  • Общая длина: {film.total_remaining:.2f} м\n"
                    f"  • Можно произвести панелей: {film.calculate_possible_panels()}\n\n"
                )
        else:
            response += "Нет в наличии\n"
        
        # Возвращаем клавиатуру для возврата в меню категорий
        keyboard = get_menu_keyboard(MenuState.INVENTORY_FILMS)
        await message.answer(response, reply_markup=keyboard)
    finally:
        db.close()

# Обработчик для панелей
@router.message(F.text == "🪵 Панели")
async def handle_panels(message: Message, state: FSMContext):
    await state.set_state(MenuState.INVENTORY_PANELS)
    
    db = next(get_db())
    try:
        # Получаем список панелей
        panels = db.query(Panel).all()
        
        response = "🪵 Пустые панели на складе:\n\n"
        if panels:
            for panel in panels:
                response += f"- Толщина {panel.thickness} мм: {panel.quantity} шт.\n"
        else:
            response += "Нет в наличии\n"
        
        # Возвращаем клавиатуру для возврата в меню категорий
        keyboard = get_menu_keyboard(MenuState.INVENTORY_PANELS)
        await message.answer(response, reply_markup=keyboard)
    finally:
        db.close()

# Обработчик для стыков
@router.message(F.text == "🔄 Стыки")
async def handle_joints(message: Message, state: FSMContext):
    await state.set_state(MenuState.INVENTORY_JOINTS)
    
    db = next(get_db())
    try:
        # Получаем список стыков
        joints = db.query(Joint).all()
        
        response = "🔄 Стыки на складе:\n\n"
        if joints:
            for joint in joints:
                response += (
                    f"- {joint.color} ({joint.type.value}, {joint.thickness} мм):\n"
                    f"  • Количество: {joint.quantity}\n"
                )
        else:
            response += "Нет в наличии\n"
        
        # Возвращаем клавиатуру для возврата в меню категорий
        keyboard = get_menu_keyboard(MenuState.INVENTORY_JOINTS)
        await message.answer(response, reply_markup=keyboard)
    finally:
        db.close()

# Обработчик для клея
@router.message(F.text == "🧪 Клей")
async def handle_glue(message: Message, state: FSMContext):
    await state.set_state(MenuState.INVENTORY_GLUE)
    
    db = next(get_db())
    try:
        # Получаем информацию о клее
        glue = db.query(Glue).first()
        
        response = "🧪 Клей на складе:\n\n"
        if glue:
            response += f"Количество: {glue.quantity}\n"
        else:
            response += "Нет в наличии\n"
        
        # Возвращаем клавиатуру для возврата в меню категорий
        keyboard = get_menu_keyboard(MenuState.INVENTORY_GLUE)
        await message.answer(response, reply_markup=keyboard)
    finally:
        db.close()

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    if not await check_warehouse_access(message):
        return
    
    await state.set_state(MenuState.WAREHOUSE_MAIN)
    await message.answer(
        "Выберите действие:",
        reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
    )

@router.message(F.text == "◀️ Назад")
async def handle_back(message: Message, state: FSMContext):
    """Обработка нажатия на кнопку 'Назад'"""
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

@router.message(lambda message: message.text and message.text.startswith("/confirm_"))
async def confirm_specific_order(message: Message, state: FSMContext):
    """Обработка команды для подтверждения конкретного заказа"""
    if not await check_warehouse_access(message):
        return
    
    try:
        # Извлекаем ID заказа из команды /confirm_123
        order_id = int(message.text.split("_")[1])
        await process_order_shipment(message, order_id)
    except (IndexError, ValueError):
        await message.answer(
            "❌ Неверный формат команды. Используйте /confirm_ID, где ID - номер заказа.",
            reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_ORDERS)
        )

async def process_order_shipment(message: Message, order_id: int):
    """Обрабатывает отгрузку заказа"""
    db = next(get_db())
    try:
        # Получаем заказ по ID
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            await message.answer(
                f"❌ Заказ #{order_id} не найден.",
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
            )
            return
            
        # Проверяем статус заказа
        if order.status == OrderStatus.COMPLETED:
            await message.answer(
                f"❌ Заказ #{order_id} уже выполнен.",
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
            )
            return
        
        # Получаем пользователя склада
        warehouse_user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not warehouse_user:
            await message.answer(
                "❌ Ваша учетная запись не найдена. Обратитесь к администратору.",
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
            )
            return
        
        try:
            # Подготавливаем данные для CompletedOrder с учетом обязательных полей
            completed_order_data = {
                'order_id': order.id,
                'manager_id': order.manager_id,
                'warehouse_user_id': warehouse_user.id,
                'installation_required': getattr(order, 'installation_required', False),
                'customer_phone': getattr(order, 'customer_phone', "") or "Не указан",
                'delivery_address': getattr(order, 'delivery_address', "") or "Не указан"
            }
            
            # Обходим все поля CompletedOrder для проверки
            valid_fields = {}
            for column in CompletedOrder.__table__.columns:
                valid_fields[column.name] = True
            
            # Удаляем неверные поля, если они были добавлены по ошибке
            for field in list(completed_order_data.keys()):
                if field not in valid_fields:
                    logging.warning(f"Удаляем недопустимое поле {field} из данных CompletedOrder")
                    del completed_order_data[field]
            
            # Проверяем, что все обязательные поля включены
            for column in CompletedOrder.__table__.columns:
                if not column.nullable and column.name not in ['id', 'completed_at'] and column.name not in completed_order_data and not column.default:
                    if column.name == 'customer_phone':
                        completed_order_data[column.name] = "Не указан"
                    elif column.name == 'delivery_address':
                        completed_order_data[column.name] = "Не указан"
                    else:
                        logging.warning(f"Добавляем пустое значение для обязательного поля {column.name}")
                        completed_order_data[column.name] = None
            
            # Создаем запись о выполненном заказе
            logging.info(f"Создаем CompletedOrder с данными: {completed_order_data}")
            completed_order = CompletedOrder(**completed_order_data)
            db.add(completed_order)
            db.flush()  # Получаем ID созданного заказа
            
            # Добавляем информацию о продуктах в выполненный заказ
            if hasattr(order, 'products') and order.products:
                for product in order.products:
                    try:
                        # Определяем необходимые атрибуты для CompletedOrderItem
                        item_data = {
                            'order_id': completed_order.id,
                            'quantity': getattr(product, 'quantity', 0),
                            'color': getattr(product, 'color', "Неизвестно"),
                            'thickness': getattr(product, 'thickness', 0.5)
                        }
                        
                        # Вместо поиска по film_id, ищем Film по коду пленки (color) и затем FinishedProduct
                        color = getattr(product, 'color', None)
                        thickness = getattr(product, 'thickness', 0.5)
                        
                        if color and item_data['quantity'] > 0:
                            # Создаем запись о выполненном товаре
                            completed_item = CompletedOrderItem(**item_data)
                            db.add(completed_item)
                            logging.info(f"Добавлен товар в completed_order_items: {item_data}")
                            
                            # Ищем пленку по коду
                            film = db.query(Film).filter(Film.code == color).first()
                            if film:
                                # Ищем готовую продукцию по film_id и толщине
                                finished_product = db.query(FinishedProduct).filter(
                                    FinishedProduct.film_id == film.id,
                                    FinishedProduct.thickness == thickness
                                ).first()
                                
                                if finished_product:
                                    old_quantity = finished_product.quantity
                                    new_quantity = old_quantity - item_data['quantity']
                                    logging.info(f"Списываем продукцию со склада: film_code={color}, film_id={film.id}, thickness={thickness}, было={old_quantity}, станет={new_quantity}")
                                    
                                    finished_product.quantity = new_quantity
                                    db.flush()  # Фиксируем изменения в памяти
                                    
                                    # Проверяем, что изменения применились
                                    updated_product = db.query(FinishedProduct).filter(
                                        FinishedProduct.film_id == film.id,
                                        FinishedProduct.thickness == thickness
                                    ).first()
                                    
                                    if updated_product and updated_product.quantity == new_quantity:
                                        logging.info(f"Успешно списана продукция. Новое количество в базе: {updated_product.quantity}")
                                    else:
                                        logging.error(f"Ошибка списания продукции! Текущее количество в базе: {updated_product.quantity if updated_product else 'не найдено'}")
                                else:
                                    logging.error(f"Готовая продукция не найдена для film_id={film.id}, thickness={thickness}")
                            else:
                                logging.error(f"Пленка с кодом {color} не найдена")
                    except Exception as e:
                        logging.error(f"Ошибка при добавлении продукта в выполненный заказ: {str(e)}")
            else:
                # Для поддержки старой структуры
                try:
                    if hasattr(order, 'film_code') and order.film_code:
                        # Находим пленку по коду
                        film = db.query(Film).filter(Film.code == order.film_code).first()
                        
                        # Создаем запись о выполненном товаре
                        item_data = {
                            'order_id': completed_order.id,
                            'color': order.film_code,
                            'thickness': getattr(order, 'panel_thickness', 0.5),
                            'quantity': getattr(order, 'panel_quantity', 0)
                        }
                        
                        completed_item = CompletedOrderItem(**item_data)
                        db.add(completed_item)
                        logging.info(f"Добавлен товар из старой структуры в completed_order_items: {item_data}")
                        
                        # Списываем со склада
                        if film:
                            finished_product = db.query(FinishedProduct).filter(
                                FinishedProduct.film_id == film.id,
                                FinishedProduct.thickness == item_data['thickness']
                            ).first()
                            
                            if finished_product:
                                old_quantity = finished_product.quantity
                                new_quantity = old_quantity - item_data['quantity']
                                logging.info(f"Списываем продукцию из старой структуры: film_id={film.id}, thickness={item_data['thickness']}, было={old_quantity}, станет={new_quantity}")
                                
                                finished_product.quantity = new_quantity
                                db.flush()
                                
                                # Проверяем, что изменения применились
                                updated_product = db.query(FinishedProduct).filter(
                                    FinishedProduct.film_id == film.id,
                                    FinishedProduct.thickness == item_data['thickness']
                                ).first()
                                
                                if updated_product and updated_product.quantity == new_quantity:
                                    logging.info(f"Успешно списана продукция из старой структуры. Новое количество в базе: {updated_product.quantity}")
                                else:
                                    logging.error(f"Ошибка списания продукции из старой структуры! Текущее количество в базе: {updated_product.quantity if updated_product else 'не найдено'}")
                            else:
                                logging.error(f"Готовая продукция не найдена для film_id={film.id}, thickness={item_data['thickness']}")
                        else:
                            logging.error(f"Пленка с кодом {order.film_code} не найдена")
                except Exception as e:
                    logging.error(f"Ошибка при добавлении продукта из старой структуры: {str(e)}")
            
            # Добавляем информацию о стыках в выполненный заказ
            if hasattr(order, 'joints') and order.joints:
                for joint_item in order.joints:
                    try:
                        joint_type = getattr(joint_item, 'joint_type', None)
                        joint_color = getattr(joint_item, 'joint_color', None)
                        thickness = getattr(joint_item, 'joint_thickness', 0.5)
                        quantity = getattr(joint_item, 'quantity', getattr(joint_item, 'joint_quantity', 0))
                        
                        if joint_type and joint_color and quantity > 0:
                            # Создаем запись о выполненном стыке
                            joint_data = {
                                'order_id': completed_order.id,
                                'joint_type': joint_type,
                                'joint_color': joint_color,
                                'quantity': quantity,
                                'joint_thickness': thickness  # Используем правильное имя поля
                            }
                            
                            completed_joint = CompletedOrderJoint(**joint_data)
                            db.add(completed_joint)
                            logging.info(f"Добавлен стык в completed_order_joints: {joint_data}")
                            
                            # Списываем со склада
                            joint_db = db.query(Joint).filter(
                                Joint.type == joint_type,
                                Joint.color == joint_color,
                                Joint.thickness == thickness
                            ).first()
                            
                            if joint_db:
                                old_quantity = joint_db.quantity
                                new_quantity = old_quantity - quantity
                                logging.info(f"Списываем стык со склада: type={joint_type}, color={joint_color}, thickness={thickness}, было={old_quantity}, станет={new_quantity}")
                                
                                joint_db.quantity = new_quantity
                                db.flush()
                                
                                # Проверяем, что изменения применились
                                updated_joint = db.query(Joint).filter(
                                    Joint.type == joint_type,
                                    Joint.color == joint_color,
                                    Joint.thickness == thickness
                                ).first()
                                
                                if updated_joint and updated_joint.quantity == new_quantity:
                                    logging.info(f"Успешно списан стык. Новое количество в базе: {updated_joint.quantity}")
                                else:
                                    logging.error(f"Ошибка списания стыка! Текущее количество в базе: {updated_joint.quantity if updated_joint else 'не найдено'}")
                    except Exception as e:
                        logging.error(f"Ошибка при добавлении стыка в выполненный заказ: {str(e)}")
            else:
                # Для поддержки старой структуры
                try:
                    # Получаем информацию о стыке из старой структуры
                    joint_type = getattr(order, 'joint_type', None)
                    joint_color = getattr(order, 'joint_color', None)
                    joint_quantity = getattr(order, 'joint_quantity', 0)
                    
                    if joint_type and joint_color and joint_quantity > 0:
                        # Создаем запись о выполненном стыке
                        joint_data = {
                            'order_id': completed_order.id,
                            'joint_type': joint_type,
                            'joint_color': joint_color,
                            'quantity': joint_quantity,
                            'joint_thickness': getattr(order, 'panel_thickness', 0.5)  # Используем правильное имя поля
                        }
                        
                        completed_joint = CompletedOrderJoint(**joint_data)
                        db.add(completed_joint)
                        logging.info(f"Добавлен стык из старой структуры в completed_order_joints: {joint_data}")
                        
                        # Списываем со склада
                        joint_thickness = getattr(order, 'panel_thickness', 0.5)
                        joint_db = db.query(Joint).filter(
                            Joint.type == joint_type,
                            Joint.color == joint_color,
                            Joint.thickness == joint_thickness
                        ).first()
                        
                        if joint_db:
                            old_quantity = joint_db.quantity
                            new_quantity = old_quantity - joint_quantity
                            logging.info(f"Списываем стык из старой структуры: type={joint_type}, color={joint_color}, thickness={joint_thickness}, было={old_quantity}, станет={new_quantity}")
                            
                            joint_db.quantity = new_quantity
                            db.flush()
                            
                            # Проверяем, что изменения применились
                            updated_joint = db.query(Joint).filter(
                                Joint.type == joint_type,
                                Joint.color == joint_color,
                                Joint.thickness == joint_thickness
                            ).first()
                            
                            if updated_joint and updated_joint.quantity == new_quantity:
                                logging.info(f"Успешно списан стык из старой структуры. Новое количество в базе: {updated_joint.quantity}")
                            else:
                                logging.error(f"Ошибка списания стыка из старой структуры! Текущее количество в базе: {updated_joint.quantity if updated_joint else 'не найдено'}")
                except Exception as e:
                    logging.error(f"Ошибка при добавлении стыка из старой структуры: {str(e)}")
            
            # Добавляем информацию о клее в выполненный заказ
            glue_quantity = 0
            if hasattr(order, 'glues') and order.glues:
                try:
                    glue_quantity = sum(getattr(glue, 'quantity', 0) for glue in order.glues)
                except Exception as e:
                    logging.error(f"Ошибка при извлечении данных о клее: {str(e)}")
            else:
                # Если нет glues, пробуем получить атрибуты напрямую из заказа (старая структура)
                glue_quantity = getattr(order, 'glue_quantity', 0)
                
            if glue_quantity > 0:
                try:
                    # Создаем запись о выполненном клее
                    glue_data = {
                        'order_id': completed_order.id,
                        'quantity': glue_quantity
                    }
                    
                    completed_glue = CompletedOrderGlue(**glue_data)
                    db.add(completed_glue)
                    logging.info(f"Добавлен клей в completed_order_glues: {glue_data}")
                    
                    # Списываем клей со склада
                    glue = db.query(Glue).first()
                    if glue:
                        old_quantity = glue.quantity
                        new_quantity = old_quantity - glue_quantity
                        logging.info(f"Списываем клей со склада: было={old_quantity}, станет={new_quantity}")
                        
                        glue.quantity = new_quantity
                        db.flush()
                        
                        # Проверяем, что изменения применились
                        updated_glue = db.query(Glue).first()
                        if updated_glue and updated_glue.quantity == new_quantity:
                            logging.info(f"Успешно списан клей. Новое количество в базе: {updated_glue.quantity}")
                        else:
                            logging.error(f"Ошибка списания клея! Текущее количество в базе: {updated_glue.quantity if updated_glue else 'не найдено'}")
                except Exception as e:
                    logging.error(f"Ошибка при добавлении клея в выполненный заказ: {str(e)}")
            
            # Меняем статус заказа на выполненный
            order.status = OrderStatus.COMPLETED
            order.completed_at = datetime.utcnow()
            
            # Сохраняем изменения в базе данных
            logging.info(f"Применяем все изменения в БД через commit для заказа #{order.id}")
            db.commit()
            logging.info(f"Изменения успешно сохранены в БД для заказа #{order.id}")
            
            # Отправляем сообщение менеджеру о выполнении заказа
            manager = db.query(User).filter(User.id == order.manager_id).first()
            if manager and manager.telegram_id:
                try:
                    await message.bot.send_message(
                        manager.telegram_id,
                        f"✅ Заказ #{order.id} выполнен и отправлен клиенту."
                    )
                except Exception as e:
                    logging.error(f"Ошибка при отправке уведомления менеджеру: {str(e)}")
            
            # Отправляем подтверждение складу
            await message.answer(
                f"✅ Заказ #{order.id} успешно обработан и отмечен как выполненный.",
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
            )
        
        except Exception as e:
            db.rollback()
            logging.error(f"Ошибка при создании CompletedOrder: {str(e)}")
            await message.answer(
                f"❌ Произошла ошибка при обработке заказа: {str(e)}",
                reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
            )
            return
        
    except Exception as e:
        logging.error(f"Ошибка при подтверждении отгрузки заказа #{order_id}: {str(e)}")
        await message.answer(
            f"❌ Произошла ошибка при обработке заказа: {str(e)}",
            reply_markup=get_menu_keyboard(MenuState.WAREHOUSE_MAIN)
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

async def check_warehouse_access(message: Message) -> bool:
    """Проверяет, имеет ли пользователь права для роли склада"""
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        
        if not user or user.role not in [UserRole.WAREHOUSE, UserRole.SUPER_ADMIN]:
            await message.answer("У вас нет прав для выполнения этой команды.")
            return False
        return True
    finally:
        db.close() 