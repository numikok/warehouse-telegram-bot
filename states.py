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
    waiting_for_film_code = State()
    waiting_for_panel_thickness = State()
    waiting_for_panel_quantity = State()
    waiting_for_joint_type = State()
    waiting_for_joint_color = State()
    waiting_for_joint_thickness = State()
    waiting_for_joint_quantity = State()
    waiting_for_glue_quantity = State()
    waiting_for_installation = State()
    waiting_for_customer_phone = State()
    waiting_for_delivery_address = State()
    waiting_for_confirmation = State() 