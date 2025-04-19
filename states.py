from aiogram.fsm.state import State, StatesGroup

class ProductionStates(StatesGroup):
    waiting_for_material_type = State()
    waiting_for_panel_quantity = State()
    waiting_for_panel_thickness = State()
    waiting_for_film_code = State()
    waiting_for_film_quantity = State()
    waiting_for_film_meters = State()
    waiting_for_panel_consumption = State()
    
    # Состояния для прихода стыков
    waiting_for_joint_type = State()
    waiting_for_joint_color = State()
    waiting_for_joint_thickness = State()
    waiting_for_joint_quantity = State()
    
    # Состояния для прихода клея
    waiting_for_glue_quantity = State()
    
    # Состояния для производства
    waiting_for_production_panel_thickness = State()
    waiting_for_production_film_color = State()
    waiting_for_production_quantity = State()
    
    # Состояния для брака
    waiting_for_defect_type = State()
    waiting_for_defect_joint_type = State()
    waiting_for_defect_joint_color = State()
    waiting_for_defect_joint_thickness = State()
    waiting_for_defect_joint_quantity = State()
    waiting_for_defect_panel_thickness = State()
    waiting_for_defect_panel_quantity = State()
    waiting_for_defect_film_color = State()
    waiting_for_defect_film_thickness = State()
    waiting_for_defect_film_meters = State()
    waiting_for_defect_glue_quantity = State()
    
    # Состояния для управления заказами
    waiting_for_order_id_to_complete = State()
    
    # Состояния для раскроя панелей
    waiting_for_cut_panel_width = State()
    waiting_for_cut_panel_height = State()
    waiting_for_cut_panel_quantity = State()
    
    # Состояния для рулонов
    waiting_for_roll_count = State()
    waiting_for_roll_length = State()
    
class ProductionOrderStates(StatesGroup):
    waiting_for_panel_thickness = State()
    waiting_for_panel_quantity = State()
    waiting_for_film_color = State()
    
class WarehouseStates(StatesGroup):
    waiting_for_order_id = State()
    waiting_for_confirmation = State()
    waiting_for_joint_type = State()
    waiting_for_joint_thickness = State()
    waiting_for_joint_color = State()
    waiting_for_joint_quantity = State()
    waiting_for_panel_thickness = State()
    waiting_for_panel_quantity = State()
    waiting_for_glue_quantity = State()
    
class SalesStates(StatesGroup):
    # Базовые состояния для работы с пленкой
    waiting_for_film = State()
    waiting_for_film_code = State()
    waiting_for_film_name = State()
    waiting_for_film_color = State()
    waiting_for_panel_quantity = State()
    waiting_for_panels_count = State()
    
    # Состояния для множественного выбора продуктов
    selecting_products = State()
    product_thickness = State()
    product_quantity = State()
    add_more_products = State()
    
    # Состояния для множественного выбора стыков
    selecting_joints = State()
    joint_quantity = State()
    add_more_joints = State()
    waiting_for_joint_type = State()
    waiting_for_joint_color = State()
    waiting_for_joint_quantity = State()
    
    # Общие состояния для заказа
    waiting_for_need_joints = State()
    waiting_for_need_glue = State()
    waiting_for_installation = State()
    waiting_for_customer_name = State()
    waiting_for_customer_phone = State()
    waiting_for_delivery_address = State()
    waiting_for_confirmation = State()
    
    # Дополнительные состояния
    waiting_for_glue_quantity = State()
    waiting_for_installation = State()
    waiting_for_phone = State()
    waiting_for_address = State()
    current_thickness = State()
    current_film_code = State()
    selected_products = State()
    selected_joints = State()
    
    # Состояния для заказа с множественным выбором
    waiting_for_order_joint_type = State()
    waiting_for_order_joint_thickness = State()
    waiting_for_order_joint_color = State()
    waiting_for_order_joint_quantity = State()
    waiting_for_add_more_joints = State()
    waiting_for_order_more_joints = State()
    waiting_for_order_glue_needed = State()
    waiting_for_order_glue_quantity = State()
    waiting_for_order_installation = State()
    waiting_for_order_customer_phone = State()
    waiting_for_order_delivery_address = State()
    waiting_for_order_confirmation = State()
    waiting_for_order_film_color = State()
    waiting_for_order_panel_quantity = State() 