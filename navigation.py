from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from models import UserRole
from enum import Enum, auto
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.fsm.state import State
import logging
from typing import Union

class MenuState(str, Enum):
    # Главное меню для каждой роли
    SUPER_ADMIN_MAIN = "super_admin_main"
    SALES_MAIN = "sales_main"
    WAREHOUSE_MAIN = "warehouse_main"
    PRODUCTION_MAIN = "production_main"
    
    # Подменю производства
    PRODUCTION_MATERIALS = "production_materials"
    PRODUCTION_DEFECT = "production_defect"
    PRODUCTION_PROCESS = "production_process"
    PRODUCTION_ORDERS = "production_orders"
    
    # Подменю склада
    WAREHOUSE_STOCK = "warehouse_stock"
    WAREHOUSE_ORDERS = "warehouse_orders"
    WAREHOUSE_INCOME = "warehouse_income"
    WAREHOUSE_MATERIALS = "warehouse_materials"
    WAREHOUSE_COMPLETED_ORDERS = "warehouse_completed_orders"
    WAREHOUSE_VIEW_COMPLETED_ORDER = "warehouse_view_completed_order"
    WAREHOUSE_RETURN_REQUESTS = "warehouse_return_requests"
    VIEW_RETURN_REQUEST = "view_return_request"
    
    # Подменю продаж
    SALES_ORDER = "sales_order"
    SALES_STOCK = "sales_stock"
    SALES_HISTORY = "sales_history"
    SALES_CREATE_ORDER = "sales_create_order"  # Новое состояние для создания заказа
    SALES_ORDER_CONFIRM = "sales_order_confirm"  # Подтверждение заказа
    SALES_COMPLETED_ORDERS = "sales_completed_orders"
    SALES_VIEW_COMPLETED_ORDER = "sales_view_completed_order"
    
    # Подменю супер-админа
    SUPER_ADMIN_USERS = "super_admin_users"
    SUPER_ADMIN_REPORTS = "super_admin_reports"
    SUPER_ADMIN_SETTINGS = "super_admin_settings"
    SUPER_ADMIN_WAREHOUSE = "super_admin_warehouse"
    SUPER_ADMIN_PRODUCTION = "super_admin_production"
    SUPER_ADMIN_SALES = "super_admin_sales"
    SUPER_ADMIN_CHINA_ORDER = "super_admin_china_order"
    
    # Инвентарь - новые состояния для всех ролей
    INVENTORY_CATEGORIES = "inventory_categories"
    INVENTORY_FINISHED_PRODUCTS = "inventory_finished_products"
    INVENTORY_FILMS = "inventory_films"
    INVENTORY_PANELS = "inventory_panels"
    INVENTORY_JOINTS = "inventory_joints"
    INVENTORY_GLUE = "inventory_glue"

# Структура навигации: какое меню куда ведет при нажатии "Назад"
MENU_NAVIGATION = {
    # Производство
    MenuState.PRODUCTION_MATERIALS: MenuState.PRODUCTION_MAIN,
    MenuState.PRODUCTION_DEFECT: MenuState.PRODUCTION_MAIN,
    MenuState.PRODUCTION_PROCESS: MenuState.PRODUCTION_MAIN,
    MenuState.PRODUCTION_ORDERS: MenuState.PRODUCTION_MAIN,
    MenuState.PRODUCTION_MAIN: MenuState.SUPER_ADMIN_MAIN,  # Для возврата из роли производства в супер админа
    
    # Склад
    MenuState.WAREHOUSE_STOCK: MenuState.WAREHOUSE_MAIN,
    MenuState.WAREHOUSE_ORDERS: MenuState.WAREHOUSE_MAIN,
    MenuState.WAREHOUSE_INCOME: MenuState.WAREHOUSE_MAIN,
    MenuState.WAREHOUSE_MATERIALS: MenuState.WAREHOUSE_MAIN,
    MenuState.WAREHOUSE_COMPLETED_ORDERS: MenuState.WAREHOUSE_MAIN,
    MenuState.WAREHOUSE_VIEW_COMPLETED_ORDER: MenuState.WAREHOUSE_COMPLETED_ORDERS,
    MenuState.WAREHOUSE_RETURN_REQUESTS: MenuState.WAREHOUSE_MAIN,
    MenuState.VIEW_RETURN_REQUEST: MenuState.WAREHOUSE_RETURN_REQUESTS,
    MenuState.WAREHOUSE_MAIN: MenuState.SUPER_ADMIN_MAIN,  # Для возврата из роли склада в супер админа
    
    # Инвентарь - новые состояния для всех ролей
    MenuState.INVENTORY_FINISHED_PRODUCTS: MenuState.INVENTORY_CATEGORIES,
    MenuState.INVENTORY_FILMS: MenuState.INVENTORY_CATEGORIES,
    MenuState.INVENTORY_PANELS: MenuState.INVENTORY_CATEGORIES,
    MenuState.INVENTORY_JOINTS: MenuState.INVENTORY_CATEGORIES,
    MenuState.INVENTORY_GLUE: MenuState.INVENTORY_CATEGORIES,
    MenuState.INVENTORY_CATEGORIES: lambda role: ROLE_MAIN_MENU.get(role),
    
    # Продажи
    MenuState.SALES_ORDER: MenuState.SALES_MAIN,
    MenuState.SALES_STOCK: MenuState.SALES_MAIN,
    MenuState.SALES_HISTORY: MenuState.SALES_MAIN,
    MenuState.SALES_CREATE_ORDER: MenuState.SALES_MAIN,  # Возврат в главное меню продаж
    MenuState.SALES_ORDER_CONFIRM: MenuState.SALES_CREATE_ORDER,  # Возврат к созданию заказа
    MenuState.SALES_COMPLETED_ORDERS: MenuState.SALES_MAIN,
    MenuState.SALES_VIEW_COMPLETED_ORDER: MenuState.SALES_COMPLETED_ORDERS,
    MenuState.SALES_MAIN: MenuState.SUPER_ADMIN_MAIN,  # Для возврата из роли продаж в супер админа
    
    # Супер-админ
    MenuState.SUPER_ADMIN_USERS: MenuState.SUPER_ADMIN_MAIN,
    MenuState.SUPER_ADMIN_REPORTS: MenuState.SUPER_ADMIN_MAIN,
    MenuState.SUPER_ADMIN_SETTINGS: MenuState.SUPER_ADMIN_MAIN,
    MenuState.SUPER_ADMIN_WAREHOUSE: MenuState.SUPER_ADMIN_MAIN,
    MenuState.SUPER_ADMIN_PRODUCTION: MenuState.SUPER_ADMIN_MAIN,
    MenuState.SUPER_ADMIN_SALES: MenuState.SUPER_ADMIN_MAIN,
    MenuState.SUPER_ADMIN_CHINA_ORDER: MenuState.SUPER_ADMIN_MAIN,
}

# Маппинг ролей на их главные меню
ROLE_MAIN_MENU = {
    UserRole.SUPER_ADMIN: MenuState.SUPER_ADMIN_MAIN,
    UserRole.SALES_MANAGER: MenuState.SALES_MAIN,
    UserRole.WAREHOUSE: MenuState.WAREHOUSE_MAIN,
    UserRole.PRODUCTION: MenuState.PRODUCTION_MAIN,
    UserRole.NONE: None,  # Для роли NONE нет главного меню
}

def get_menu_keyboard(menu_state: MenuState, is_admin_context: bool = False) -> ReplyKeyboardMarkup:
    """Возвращает клавиатуру для конкретного состояния меню
    
    Args:
        menu_state: Состояние меню, для которого требуется клавиатура
        is_admin_context: Флаг, указывающий, что клавиатура запрашивается в контексте супер-админа
    """
    keyboards = {
        # Главное меню производства
        MenuState.PRODUCTION_MAIN: [
            [KeyboardButton(text="📥 Приход сырья")],
            [KeyboardButton(text="🛠 Производство")],
            [KeyboardButton(text="📋 Заказы на производство")],
            [KeyboardButton(text="🚫 Брак")],
            [KeyboardButton(text="📊 Остатки")]
        ],
        
        # Подменю производства
        MenuState.PRODUCTION_MATERIALS: [
            [KeyboardButton(text="🪵 Панель")],
            [KeyboardButton(text="🎨 Пленка")],
            [KeyboardButton(text="⚙️ Стык")],
            [KeyboardButton(text="🧴 Клей")],
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        MenuState.PRODUCTION_DEFECT: [
            [KeyboardButton(text="🪵 Панель")],
            [KeyboardButton(text="🎨 Пленка")],
            [KeyboardButton(text="⚙️ Стык")],
            [KeyboardButton(text="🧴 Клей")],
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        MenuState.PRODUCTION_PROCESS: [
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        MenuState.PRODUCTION_ORDERS: [
            [KeyboardButton(text="✨ Завершить заказ")],
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        # Главное меню продаж
        MenuState.SALES_MAIN: [
            [KeyboardButton(text="📝 Составить заказ")],
            [KeyboardButton(text="📝 Заказать")],
            [KeyboardButton(text="✅ Завершенные заказы")],
            [KeyboardButton(text="📊 Остатки")],
        ],
        
        # Подменю продаж
        MenuState.SALES_ORDER: [
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        MenuState.SALES_STOCK: [
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        MenuState.SALES_HISTORY: [
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        MenuState.SALES_CREATE_ORDER: [
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        MenuState.SALES_ORDER_CONFIRM: [
            [KeyboardButton(text="✅ Подтвердить"), KeyboardButton(text="❌ Отменить"), KeyboardButton(text="◀️ Назад")]
        ],
        
        MenuState.SALES_COMPLETED_ORDERS: [
            [KeyboardButton(text="◀️ Назад")]
        ],
        MenuState.SALES_VIEW_COMPLETED_ORDER: [
            [KeyboardButton(text="◀️ К списку завершенных")]
        ],
        
        # Главное меню склада
        MenuState.WAREHOUSE_MAIN: [
            [KeyboardButton(text="📦 Остатки"), KeyboardButton(text="📦 Мои заказы")],
            [KeyboardButton(text="✅ Завершенные заказы"), KeyboardButton(text="♻️ Запросы на возврат")]
        ],
        
        # Подменю склада
        MenuState.WAREHOUSE_STOCK: [
            [KeyboardButton(text="📊 Все остатки")],
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        MenuState.WAREHOUSE_ORDERS: [
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        MenuState.WAREHOUSE_INCOME: [
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        MenuState.WAREHOUSE_MATERIALS: [
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        MenuState.WAREHOUSE_COMPLETED_ORDERS: [
            [KeyboardButton(text="◀️ Назад")]
        ],
        MenuState.WAREHOUSE_VIEW_COMPLETED_ORDER: [
            [KeyboardButton(text="◀️ К списку завершенных")]
        ],
        
        # Новые меню для категорий инвентаря
        MenuState.INVENTORY_CATEGORIES: [
            [KeyboardButton(text="✅ Готовая продукция")],
            [KeyboardButton(text="🎞 Пленка")],
            [KeyboardButton(text="🪵 Панели")],
            [KeyboardButton(text="🔄 Стыки")],
            [KeyboardButton(text="🧪 Клей")],
            [KeyboardButton(text="📊 Все остатки")],
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        # Каждая категория инвентаря просто имеет кнопку назад
        MenuState.INVENTORY_FINISHED_PRODUCTS: [
            [KeyboardButton(text="◀️ Назад")]
        ],
        MenuState.INVENTORY_FILMS: [
            [KeyboardButton(text="◀️ Назад")]
        ],
        MenuState.INVENTORY_PANELS: [
            [KeyboardButton(text="◀️ Назад")]
        ],
        MenuState.INVENTORY_JOINTS: [
            [KeyboardButton(text="◀️ Назад")]
        ],
        MenuState.INVENTORY_GLUE: [
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        # Главное меню супер-админа
        MenuState.SUPER_ADMIN_MAIN: [
            [KeyboardButton(text="👥 Управление пользователями")],
            [KeyboardButton(text="📊 Отчеты и статистика")],
            [KeyboardButton(text="⚙️ Настройки системы")],
            [KeyboardButton(text="💼 Роль менеджера по продажам")],
            [KeyboardButton(text="📦 Роль склада")],
            [KeyboardButton(text="🏭 Роль производства")],
            [KeyboardButton(text="Заказ в Китай")]
        ],
        
        # Подменю супер-админа
        MenuState.SUPER_ADMIN_USERS: [
            [KeyboardButton(text="👤 Назначить роль")],
            [KeyboardButton(text="📋 Список пользователей")],
            [KeyboardButton(text="🔄 Сбросить роль пользователя")],
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        MenuState.SUPER_ADMIN_REPORTS: [
            [KeyboardButton(text="📊 Общая статистика")],
            [KeyboardButton(text="📈 Отчет по продажам")],
            [KeyboardButton(text="🏭 Отчет по производству")],
            [KeyboardButton(text="📝 История операций")],
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        MenuState.SUPER_ADMIN_SETTINGS: [
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        MenuState.SUPER_ADMIN_WAREHOUSE: [
            [KeyboardButton(text="📦 Остатки материалов")],
            [KeyboardButton(text="✅ Подтвердить отгрузку")],
            [KeyboardButton(text="📋 Мои заказы")],
            [KeyboardButton(text="➕ Приход материалов")],
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        MenuState.SUPER_ADMIN_PRODUCTION: [
            [KeyboardButton(text="📥 Приход сырья")],
            [KeyboardButton(text="🛠 Производство")],
            [KeyboardButton(text="📋 Заказы на производство")],
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        MenuState.SUPER_ADMIN_SALES: [
            [KeyboardButton(text="📝 Заказать")],
            [KeyboardButton(text="📋 Мои заказы")],
            [KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        # Новое меню для Заказа в Китай
        MenuState.SUPER_ADMIN_CHINA_ORDER: [
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        # Fallback
        None: [[KeyboardButton(text="/start")]]
    }
    
    # Special handling for admin context (add back button)
    if is_admin_context and menu_state in [MenuState.WAREHOUSE_MAIN, MenuState.PRODUCTION_MAIN, MenuState.SALES_MAIN]:
        keyboard_layout = keyboards.get(menu_state, keyboards[None])
        # Ensure 'Назад в админку' is not already there
        if not any(b.text == "🔙 Назад в админку" for row in keyboard_layout for b in row):
             keyboard_layout.append([KeyboardButton(text="🔙 Назад в админку")])
        return ReplyKeyboardMarkup(keyboard=keyboard_layout, resize_keyboard=True)

    # Default return
    keyboard_layout = keyboards.get(menu_state, keyboards[None])
    return ReplyKeyboardMarkup(keyboard=keyboard_layout, resize_keyboard=True)

async def go_back(state: FSMContext, role: UserRole) -> tuple[Union[MenuState, None], ReplyKeyboardMarkup]:
    """
    Возвращает предыдущее состояние меню и соответствующую клавиатуру.
    Возвращает None для состояния, если не удается определить предыдущее.
    """
    current_state_str = await state.get_state()
    logging.info(f"go_back called. Current state string: {current_state_str}, Role: {role}")
    
    next_menu: Union[MenuState, None] = None
    main_role_menu = ROLE_MAIN_MENU.get(role)

    if not current_state_str:
        # Если состояние не установлено, возвращаемся в главное меню роли
        logging.warning("Current state is None, returning to main role menu.")
        next_menu = main_role_menu
    else:
        try:
            current_menu = MenuState(current_state_str)
            logging.info(f"Current menu state resolved to: {current_menu}")
            
            # Определяем, куда нужно вернуться
            nav_target = MENU_NAVIGATION.get(current_menu)
            logging.info(f"Navigation target from MENU_NAVIGATION: {nav_target}")
            
            if callable(nav_target):
                logging.info("Navigation target is callable, executing with role.")
                next_menu = nav_target(role) # Call the lambda function
                logging.info(f"Result from callable: {next_menu}")
            elif isinstance(nav_target, MenuState):
                next_menu = nav_target
            else:
                # Если нет указанного перехода или target не callable/MenuState
                logging.warning(f"No valid navigation target found for {current_menu}, returning to main role menu.")
                next_menu = main_role_menu

        except ValueError:
            # Если текущее состояние не является MenuState, возвращаемся в главное меню роли
            logging.warning(f"Current state '{current_state_str}' is not a valid MenuState, returning to main role menu.")
            next_menu = main_role_menu

    if next_menu is None:
        # Если главное меню роли не найдено (e.g., Role.NONE) или другая ошибка
        logging.error(f"Could not determine next menu. Returning None state and empty keyboard.")
        # Вернуть None для состояния и пустую клавиатуру, чтобы вызвать /start
        return None, ReplyKeyboardRemove() 
        
    logging.info(f"Determined next menu state: {next_menu}")
    # Получаем state_data для проверки is_admin_context
    state_data = await state.get_data()
    is_admin_context = state_data.get("is_admin_context", False)
    logging.info(f"Getting keyboard for {next_menu} with is_admin_context={is_admin_context}")
    
    keyboard = get_menu_keyboard(next_menu, is_admin_context)
    return next_menu, keyboard

def get_role_keyboard(role: UserRole) -> ReplyKeyboardMarkup:
    """Возвращает главную клавиатуру для роли"""
    if role == UserRole.NONE:
        # Для пользователей без роли возвращаем пустую клавиатуру
        return ReplyKeyboardRemove()
    
    main_menu = ROLE_MAIN_MENU[role]
    return get_menu_keyboard(main_menu)

def get_back_keyboard() -> ReplyKeyboardMarkup:
    """Возвращает клавиатуру только с кнопкой Назад"""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="◀️ Назад")]],
        resize_keyboard=True
    )

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Возвращает клавиатуру с кнопкой Отмена"""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )

def get_joint_thickness_keyboard():
    # Создаем клавиатуру с толщинами стыков
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="0.5")],
            [KeyboardButton(text="0.8")],
            [KeyboardButton(text="◀️ Назад")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_film_thickness_keyboard():
    # Создаем клавиатуру с толщинами пленки
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="0.5")],
            [KeyboardButton(text="0.8")],
            [KeyboardButton(text="◀️ Назад")]
        ],
        resize_keyboard=True
    )
    return keyboard

async def get_role_menu_keyboard(menu_state: MenuState, message: Message, state: FSMContext) -> ReplyKeyboardMarkup:
    """Получает клавиатуру меню, учитывая роль пользователя и контекст админа"""
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            return get_menu_keyboard(menu_state)
            
        # Получаем флаг админ-контекста
        state_data = await state.get_data()
        is_admin_context = state_data.get("is_admin_context", False)
        
        # Применяем флаг контекста админа для меню
        if user.role == UserRole.SUPER_ADMIN and is_admin_context:
            return get_menu_keyboard(menu_state, is_admin_context=True)
        else:
            return get_menu_keyboard(menu_state)
    finally:
        db.close() 