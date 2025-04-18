from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from models import UserRole
from enum import Enum, auto
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

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
    
    # Подменю продаж
    SALES_ORDER = "sales_order"
    SALES_STOCK = "sales_stock"
    SALES_HISTORY = "sales_history"
    SALES_CREATE_ORDER = "sales_create_order"  # Новое состояние для создания заказа
    SALES_ORDER_CONFIRM = "sales_order_confirm"  # Подтверждение заказа
    
    # Подменю супер-админа
    SUPER_ADMIN_USERS = "super_admin_users"
    SUPER_ADMIN_REPORTS = "super_admin_reports"
    SUPER_ADMIN_SETTINGS = "super_admin_settings"
    SUPER_ADMIN_WAREHOUSE = "super_admin_warehouse"
    SUPER_ADMIN_PRODUCTION = "super_admin_production"
    SUPER_ADMIN_SALES = "super_admin_sales"

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
    MenuState.WAREHOUSE_MAIN: MenuState.SUPER_ADMIN_MAIN,  # Для возврата из роли склада в супер админа
    
    # Продажи
    MenuState.SALES_ORDER: MenuState.SALES_MAIN,
    MenuState.SALES_STOCK: MenuState.SALES_MAIN,
    MenuState.SALES_HISTORY: MenuState.SALES_MAIN,
    MenuState.SALES_CREATE_ORDER: MenuState.SALES_MAIN,  # Возврат в главное меню продаж
    MenuState.SALES_ORDER_CONFIRM: MenuState.SALES_CREATE_ORDER,  # Возврат к созданию заказа
    MenuState.SALES_MAIN: MenuState.SUPER_ADMIN_MAIN,  # Для возврата из роли продаж в супер админа
    
    # Супер-админ
    MenuState.SUPER_ADMIN_USERS: MenuState.SUPER_ADMIN_MAIN,
    MenuState.SUPER_ADMIN_REPORTS: MenuState.SUPER_ADMIN_MAIN,
    MenuState.SUPER_ADMIN_SETTINGS: MenuState.SUPER_ADMIN_MAIN,
    MenuState.SUPER_ADMIN_WAREHOUSE: MenuState.SUPER_ADMIN_MAIN,
    MenuState.SUPER_ADMIN_PRODUCTION: MenuState.SUPER_ADMIN_MAIN,
    MenuState.SUPER_ADMIN_SALES: MenuState.SUPER_ADMIN_MAIN,
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
            [KeyboardButton(text="📋 Заказы на производство")],
            [KeyboardButton(text="📥 Приход сырья")],
            [KeyboardButton(text="🛠 Производство")],
            [KeyboardButton(text="🚫 Брак")]
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
            [KeyboardButton(text="📝 Заказать производство")],
            [KeyboardButton(text="📝 Составить заказ")],
            [KeyboardButton(text="📦 Количество готовой продукции")]
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
            [KeyboardButton(text="✅ Подтвердить")],
            [KeyboardButton(text="❌ Отменить")],
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        # Главное меню склада
        MenuState.WAREHOUSE_MAIN: [
            [KeyboardButton(text="📦 Остатки")],
            [KeyboardButton(text="📦 Мои заказы")]
        ],
        
        # Подменю склада
        MenuState.WAREHOUSE_STOCK: [
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        MenuState.WAREHOUSE_ORDERS: [
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        MenuState.WAREHOUSE_INCOME: [
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        MenuState.WAREHOUSE_MATERIALS: [
            [KeyboardButton(text="Пустые панели")],
            [KeyboardButton(text="Стыки")],
            [KeyboardButton(text="Клей")],
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        # Главное меню супер-админа
        MenuState.SUPER_ADMIN_MAIN: [
            [KeyboardButton(text="👥 Управление пользователями")],
            [KeyboardButton(text="📊 Отчеты и статистика")],
            [KeyboardButton(text="⚙️ Настройки системы")],
            [KeyboardButton(text="💼 Роль менеджера по продажам")],
            [KeyboardButton(text="📦 Роль склада")],
            [KeyboardButton(text="🏭 Роль производства")]
        ],
        
        # Подменю супер-админа
        MenuState.SUPER_ADMIN_USERS: [
            [KeyboardButton(text="👤 Назначить роль")],
            [KeyboardButton(text="📋 Список пользователей")],
            [KeyboardButton(text="❌ Удалить пользователя")],
            [KeyboardButton(text="🔄 Сбросить роль пользователя")],
            [KeyboardButton(text="◀️ Назад")]
        ],
        
        MenuState.SUPER_ADMIN_REPORTS: [
            [KeyboardButton(text="📊 Общая статистика")],
            [KeyboardButton(text="📈 Отчет по продажам")],
            [KeyboardButton(text="🏭 Отчет по производству")],
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
            [KeyboardButton(text="📝 Создать заказ")],
            [KeyboardButton(text="📋 Мои заказы")],
            [KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="◀️ Назад")]
        ],
    }
    
    # Добавляем кнопку "Назад" ко всем клавиатурам, которые ее не имеют и не являются главными меню
    keyboard = keyboards.get(menu_state, [[KeyboardButton(text="◀️ Назад")]])
    
    # Если это основное меню какой-то роли, убеждаемся, что кнопки "Назад" нет
    if menu_state in [MenuState.SUPER_ADMIN_MAIN, MenuState.SALES_MAIN, 
                      MenuState.WAREHOUSE_MAIN, MenuState.PRODUCTION_MAIN]:
        # Проверяем, нет ли кнопки "Назад" в последнем ряду
        if keyboard and keyboard[-1] and any(button.text == "◀️ Назад" for button in keyboard[-1]):
            keyboard = keyboard[:-1]  # Удаляем последний ряд с кнопкой "Назад"
            
    # Если это главное меню одной из ролей (кроме супер-админа) и есть флаг admin_context,
    # добавляем кнопку "🔙 Назад" для возврата в меню супер-админа
    if is_admin_context and menu_state in [MenuState.SALES_MAIN, MenuState.WAREHOUSE_MAIN, MenuState.PRODUCTION_MAIN]:
        keyboard.append([KeyboardButton(text="🔙 Назад в админку")])
    
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

async def go_back(state: FSMContext, role: UserRole) -> tuple[MenuState, ReplyKeyboardMarkup]:
    """
    Возвращает предыдущее состояние меню и соответствующую клавиатуру
    """
    current_state = await state.get_state()
    if not current_state:
        # Если состояние не установлено, возвращаемся в главное меню роли
        main_menu = ROLE_MAIN_MENU[role]
        return main_menu, get_menu_keyboard(main_menu)
    
    try:
        # Получаем текущее состояние меню из FSM
        current_menu = MenuState(current_state)
        
        # Определяем, куда нужно вернуться
        next_menu = MENU_NAVIGATION.get(current_menu)
        if not next_menu:
            # Если нет указанного перехода, возвращаемся в главное меню роли
            next_menu = ROLE_MAIN_MENU[role]
        
        return next_menu, get_menu_keyboard(next_menu)
    except ValueError:
        # Если текущее состояние не является MenuState, возвращаемся в главное меню роли
        main_menu = ROLE_MAIN_MENU[role]
        return main_menu, get_menu_keyboard(main_menu)

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
    # ... existing code ... 