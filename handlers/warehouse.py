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
                # Пытаемся использовать устаревшие свойства, если они есть
                try:
                    if hasattr(order, 'film_code') and order.film_code:
                        panel_quantity = 0
                        try:
                            if hasattr(order, 'panel_quantity'):
                                panel_quantity = order.panel_quantity
                        except:
                            pass
                        products_info = f"🎨 Пленка: {order.film_code}, {panel_quantity} шт.\n"
                    else:
                        products_info = "🎨 Продукция: Не указана\n"
                except:
                    products_info = "🎨 Продукция: Не указана\n"
            
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
            try:
                if hasattr(order, 'glues') and order.glues:
                    for glue in order.glues:
                        glue_quantity += getattr(glue, 'quantity', 0)
                elif hasattr(order, 'glue_quantity'):
                    glue_quantity = order.glue_quantity
            except Exception as e:
                logging.error(f"Error getting glue quantity: {str(e)}")
                glue_quantity = 0
            
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
    await state.set_state(MenuState.WAREHOUSE_STOCK)
    await cmd_stock(message, state)

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
        
        # Инициализируем переменные, которые будут использоваться для создания CompletedOrder
        panel_thickness = 0.5  # значение по умолчанию
        film_code = "Неизвестно"  # Значение по умолчанию, всегда должно быть заполнено
        panel_quantity = 0
        joint_type = None
        joint_color = None
        joint_quantity = 0
        glue_quantity = 0
        
        # Проверяем наличие продуктов и извлекаем данные
        if hasattr(order, 'products') and order.products:
            try:
                # Берем данные из первого продукта для backward compatibility
                first_product = order.products[0]
                panel_thickness = getattr(first_product, 'thickness', 0.5)
                panel_quantity = sum(getattr(product, 'quantity', 0) for product in order.products)
                
                # Для film_code используем один из двух возможных подходов: либо через film_id, либо через color
                film = None
                if hasattr(first_product, 'film_id') and first_product.film_id is not None:
                    film = db.query(Film).filter(Film.id == first_product.film_id).first()
                    if film:
                        film_code = film.code
                
                # Если film_id не существует или не найден в базе, используем поле color
                if film_code == "Неизвестно" and hasattr(first_product, 'color') and first_product.color:
                    film_code = first_product.color
            except Exception as e:
                logging.error(f"Ошибка при извлечении данных о продуктах: {str(e)}")
        else:
            # Если нет products, пробуем получить атрибуты напрямую из заказа (старая структура)
            panel_thickness = getattr(order, 'panel_thickness', 0.5)
            if hasattr(order, 'film_code') and order.film_code:
                film_code = order.film_code
            panel_quantity = getattr(order, 'panel_quantity', 0)
        
        # Проверяем наличие стыков и извлекаем данные
        if hasattr(order, 'joints') and order.joints:
            try:
                # Берем данные из первого стыка для backward compatibility
                first_joint = order.joints[0]
                joint_type = getattr(first_joint, 'joint_type', JointType.SIMPLE)
                joint_color = getattr(first_joint, 'joint_color', "")
                joint_quantity = sum(getattr(joint, 'quantity', 0) for joint in order.joints)
            except Exception as e:
                logging.error(f"Ошибка при извлечении данных о стыках: {str(e)}")
        else:
            # Если нет joints, пробуем получить атрибуты напрямую из заказа (старая структура)
            joint_type = getattr(order, 'joint_type', None)
            joint_color = getattr(order, 'joint_color', "")
            joint_quantity = getattr(order, 'joint_quantity', 0)
        
        # Проверяем наличие клея и извлекаем данные
        if hasattr(order, 'glues') and order.glues:
            try:
                glue_quantity = sum(getattr(glue, 'quantity', 0) for glue in order.glues)
            except Exception as e:
                logging.error(f"Ошибка при извлечении данных о клее: {str(e)}")
        else:
            # Если нет glues, пробуем получить атрибуты напрямую из заказа (старая структура)
            glue_quantity = getattr(order, 'glue_quantity', 0)
        
        try:
            # Проверим структуру CompletedOrder, чтобы определить обязательные поля
            required_fields = {}
            for column in CompletedOrder.__table__.columns:
                if not column.nullable and column.name not in ['id', 'completed_at'] and not column.default:
                    required_fields[column.name] = True
            
            # Подготавливаем данные для CompletedOrder с учетом обязательных полей
            completed_order_data = {
                'order_id': order.id,
                'manager_id': order.manager_id,
                'warehouse_user_id': warehouse_user.id,
                'installation_required': getattr(order, 'installation_required', False),
                'customer_phone': getattr(order, 'customer_phone', "") or "Не указан",
                'delivery_address': getattr(order, 'delivery_address', "") or "Не указан",
                # Всегда добавляем film_code, так как он обязателен по схеме БД
                'film_code': film_code,
                # Также добавляем другие поля, которые могут быть обязательными
                'panel_thickness': panel_thickness
            }
            
            # Добавляем остальные необязательные поля, если они существуют в схеме
            if hasattr(CompletedOrder, 'panel_quantity'):
                completed_order_data['panel_quantity'] = panel_quantity
                
            if joint_type is not None and hasattr(CompletedOrder, 'joint_type'):
                completed_order_data['joint_type'] = joint_type
                
            if joint_color is not None and hasattr(CompletedOrder, 'joint_color'):
                completed_order_data['joint_color'] = joint_color
                
            if hasattr(CompletedOrder, 'joint_quantity'):
                completed_order_data['joint_quantity'] = joint_quantity
                
            if hasattr(CompletedOrder, 'glue_quantity'):
                completed_order_data['glue_quantity'] = glue_quantity
            
            # Проверяем, что все обязательные поля включены
            for field in required_fields:
                if field not in completed_order_data:
                    logging.warning(f"Обязательное поле {field} отсутствует в данных. Устанавливаем значение по умолчанию.")
                    if field == 'film_code':
                        completed_order_data[field] = "Неизвестно"
                    elif field == 'customer_phone':
                        completed_order_data[field] = "Не указан"
                    elif field == 'delivery_address':
                        completed_order_data[field] = "Не указан"
                    elif field == 'panel_thickness':
                        completed_order_data[field] = 0.5
                    elif field == 'joint_color':
                        completed_order_data[field] = ""
                    elif field == 'joint_quantity' or field == 'panel_quantity' or field == 'glue_quantity':
                        completed_order_data[field] = 0
                    else:
                        completed_order_data[field] = None
            
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
                            'completed_order_id': completed_order.id,
                            'quantity': getattr(product, 'quantity', 0),
                            'color': getattr(product, 'color', film_code),  # Используем film_code как запасной вариант
                            'thickness': getattr(product, 'thickness', panel_thickness)
                        }
                        
                        # Проверяем наличие film_id и добавляем его, если он есть
                        film_id = getattr(product, 'film_id', None)
                        if film_id is not None and hasattr(CompletedOrderItem, 'film_id'):
                            item_data['film_id'] = film_id
                        
                        if item_data['quantity'] > 0:
                            # Создаем запись о выполненном товаре
                            completed_item = CompletedOrderItem(**item_data)
                            db.add(completed_item)
                            
                            # Списываем со склада
                            if film_id is not None:
                                finished_product = db.query(FinishedProduct).filter(
                                    FinishedProduct.film_id == film_id,
                                    FinishedProduct.thickness == item_data['thickness']
                                ).first()
                                
                                if finished_product:
                                    finished_product.quantity -= item_data['quantity']
                    except Exception as e:
                        logging.error(f"Ошибка при добавлении продукта в выполненный заказ: {str(e)}")
            else:
                # Для поддержки старой структуры
                try:
                    if film_code != "Неизвестно" and panel_thickness > 0 and panel_quantity > 0:
                        # Находим пленку по коду
                        film = db.query(Film).filter(Film.code == film_code).first()
                        
                        # Создаем запись о выполненном товаре
                        item_data = {
                            'completed_order_id': completed_order.id,
                            'color': film_code,
                            'thickness': panel_thickness,
                            'quantity': panel_quantity
                        }
                        
                        # Добавляем film_id, если он существует
                        if film and hasattr(CompletedOrderItem, 'film_id'):
                            item_data['film_id'] = film.id
                            
                        completed_item = CompletedOrderItem(**item_data)
                        db.add(completed_item)
                        
                        # Списываем со склада
                        if film:
                            finished_product = db.query(FinishedProduct).filter(
                                FinishedProduct.film_id == film.id,
                                FinishedProduct.thickness == panel_thickness
                            ).first()
                            
                            if finished_product:
                                finished_product.quantity -= panel_quantity
                except Exception as e:
                    logging.error(f"Ошибка при добавлении продукта из старой структуры: {str(e)}")
            
            # Добавляем информацию о стыках в выполненный заказ
            if hasattr(order, 'joints') and order.joints:
                for joint_item in order.joints:
                    try:
                        joint_type = getattr(joint_item, 'joint_type', None)
                        joint_color = getattr(joint_item, 'joint_color', None)
                        thickness = getattr(joint_item, 'joint_thickness', panel_thickness)
                        quantity = getattr(joint_item, 'quantity', getattr(joint_item, 'joint_quantity', 0))
                        
                        if joint_type and joint_color and quantity > 0:
                            # Создаем запись о выполненном стыке
                            completed_joint = CompletedOrderJoint(
                                completed_order_id=completed_order.id,
                                joint_type=joint_type,
                                joint_color=joint_color,
                                quantity=quantity,
                                thickness=thickness
                            )
                            db.add(completed_joint)
                            
                            # Списываем со склада
                            joint_db = db.query(Joint).filter(
                                Joint.type == joint_type,
                                Joint.color == joint_color,
                                Joint.thickness == thickness
                            ).first()
                            
                            if joint_db:
                                joint_db.quantity -= quantity
                    except Exception as e:
                        logging.error(f"Ошибка при добавлении стыка в выполненный заказ: {str(e)}")
            elif joint_type and joint_color and joint_quantity > 0:
                # Для поддержки старой структуры
                try:
                    # Создаем запись о выполненном стыке
                    completed_joint = CompletedOrderJoint(
                        completed_order_id=completed_order.id,
                        joint_type=joint_type,
                        joint_color=joint_color,
                        quantity=joint_quantity,
                        thickness=panel_thickness
                    )
                    db.add(completed_joint)
                    
                    # Списываем со склада
                    joint_db = db.query(Joint).filter(
                        Joint.type == joint_type,
                        Joint.color == joint_color,
                        Joint.thickness == panel_thickness
                    ).first()
                    
                    if joint_db:
                        joint_db.quantity -= joint_quantity
                except Exception as e:
                    logging.error(f"Ошибка при добавлении стыка из старой структуры: {str(e)}")
            
            # Добавляем информацию о клее в выполненный заказ
            if glue_quantity > 0:
                try:
                    # Создаем запись о выполненном клее
                    completed_glue = CompletedOrderGlue(
                        completed_order_id=completed_order.id,
                        quantity=glue_quantity
                    )
                    db.add(completed_glue)
                    
                    # Списываем клей со склада
                    glue = db.query(Glue).first()
                    if glue:
                        glue.quantity -= glue_quantity
                except Exception as e:
                    logging.error(f"Ошибка при добавлении клея в выполненный заказ: {str(e)}")
            
            # Меняем статус заказа на выполненный
            order.status = OrderStatus.COMPLETED
            order.completed_at = datetime.utcnow()
            
            # Сохраняем изменения в базе данных
            db.commit()
            
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