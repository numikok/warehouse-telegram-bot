from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum as SQLEnum, BigInteger, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime
import enum

Base = declarative_base()

class UserRole(enum.Enum):
    NONE = "Ожидание роли"
    SUPER_ADMIN = "Супер-администратор"
    SALES_MANAGER = "Менеджер по продажам"
    PRODUCTION = "Производство"
    WAREHOUSE = "Склад"

class JointType(enum.Enum):
    BUTTERFLY = "butterfly"  # Бабочка
    SIMPLE = "simple"      # Простые
    CLOSING = "closing"    # Замыкающие

class OperationType(enum.Enum):
    INCOME = "INCOME"
    PRODUCTION = "PRODUCTION"
    SALE = "SALE"
    WAREHOUSE = "WAREHOUSE"
    READY_PRODUCT_OUT = "READY_PRODUCT_OUT"  # Отпуск готовой продукции
    JOINT_OUT = "JOINT_OUT"  # Отпуск стыков
    GLUE_OUT = "GLUE_OUT"  # Отпуск клея

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String, nullable=False)
    role = Column(SQLEnum(UserRole), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    operations = relationship("Operation", back_populates="user")

class Film(Base):
    __tablename__ = "films"
    
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False)
    panel_consumption = Column(Float, nullable=False, default=3.0)  # Расход на одну панель в метрах
    meters_per_roll = Column(Float, nullable=False, default=50.0)  # Метров в одном рулоне
    total_remaining = Column(Float, nullable=False, default=0)  # Общее количество оставшихся метров
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    finished_products = relationship("FinishedProduct", back_populates="film")
    
    def calculate_remaining(self) -> float:
        return self.total_remaining
        
    def calculate_possible_panels(self) -> int:
        if self.panel_consumption <= 0:
            return 0
        return int(self.total_remaining / self.panel_consumption)

class Panel(Base):
    __tablename__ = "panels"
    
    id = Column(Integer, primary_key=True)
    quantity = Column(Integer, default=0)  # Количество панелей (каждая по 3 метра)
    thickness = Column(Float, nullable=False, default=0.5)  # Толщина панели (0.5 или 0.8)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class Joint(Base):
    __tablename__ = "joints"
    
    id = Column(Integer, primary_key=True)
    type = Column(SQLEnum(JointType), nullable=False)  # Тип стыка
    thickness = Column(Float, nullable=False)  # Толщина (0.5 или 0.8)
    color = Column(String, nullable=False)    # Цвет стыка
    quantity = Column(Integer, default=0)     # Количество
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class Glue(Base):
    __tablename__ = "glue"
    
    id = Column(Integer, primary_key=True)
    quantity = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class FinishedProduct(Base):
    __tablename__ = "finished_products"
    
    id = Column(Integer, primary_key=True)
    film_id = Column(Integer, ForeignKey('films.id'), nullable=False)
    quantity = Column(Integer, default=0)
    thickness = Column(Float, nullable=False, default=0.5)  # Толщина панели (0.5 или 0.8)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    film = relationship("Film", back_populates="finished_products")

class Operation(Base):
    __tablename__ = "operations"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    operation_type = Column(String, nullable=False)  # income, production, sale, etc.
    quantity = Column(Integer, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    details = Column(String)  # JSON строка с дополнительными данными
    
    user = relationship("User", back_populates="operations")

class ProductionOrder(Base):
    __tablename__ = "production_orders"
    
    id = Column(Integer, primary_key=True)
    manager_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    panel_quantity = Column(Integer, nullable=False)
    film_color = Column(String, nullable=False)
    panel_thickness = Column(Float, nullable=False, default=0.5)  # Толщина панели (0.5 или 0.8)
    status = Column(String, default="new")  # new, in_progress, completed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    manager = relationship("User", foreign_keys=[manager_id]) 

class OrderStatus(enum.Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    CREATED = "created"

class OrderJoint(Base):
    __tablename__ = "order_joints"
    
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=False)
    joint_type = Column(SQLEnum(JointType), nullable=False)
    joint_color = Column(String, nullable=False)
    joint_quantity = Column(Integer, nullable=False)
    joint_thickness = Column(Float, nullable=False, default=0.5)  # Толщина стыка (0.5 или 0.8)
    
    order = relationship("Order", back_populates="joints")
    
    # Alias for backward compatibility
    @property
    def quantity(self):
        return self.joint_quantity
        
    @quantity.setter
    def quantity(self, value):
        self.joint_quantity = value

class OrderItem(Base):
    __tablename__ = "order_items"
    
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=False)
    product_id = Column(Integer, ForeignKey('finished_products.id'), nullable=True)
    quantity = Column(Integer, nullable=False)
    color = Column(String, nullable=False)
    thickness = Column(Float, nullable=False, default=0.5)  # Толщина продукции (0.5 или 0.8)
    
    order = relationship("Order", back_populates="products")
    product = relationship("FinishedProduct")

class OrderGlue(Base):
    __tablename__ = "order_glues"
    
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=False)
    quantity = Column(Integer, nullable=False)
    
    order = relationship("Order", back_populates="glues")

class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True)
    manager_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    installation_required = Column(Boolean, default=False)
    customer_phone = Column(String, nullable=True)
    delivery_address = Column(String, nullable=True)
    status = Column(SQLEnum(OrderStatus), nullable=False, default=OrderStatus.NEW)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    manager = relationship("User", foreign_keys=[manager_id])
    
    products = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    joints = relationship("OrderJoint", back_populates="order", cascade="all, delete-orphan")
    glues = relationship("OrderGlue", back_populates="order", cascade="all, delete-orphan")

    def to_dict(self):
        joints_data = [{"type": joint.joint_type.value, "color": joint.joint_color, "quantity": joint.quantity, "thickness": joint.joint_thickness} for joint in self.joints] if self.joints else []
        items_data = [{"product_id": item.product_id, "color": item.color, "thickness": item.thickness, "quantity": item.quantity} for item in self.products] if self.products else []
        glue_quantity = sum([glue.quantity for glue in self.glues]) if self.glues else 0
            
        return {
            "id": self.id,
            "items": items_data,
            "joints": joints_data,
            "glue_quantity": glue_quantity,
            "installation_required": self.installation_required,
            "customer_phone": self.customer_phone,
            "delivery_address": self.delivery_address,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }

class CompletedOrderJoint(Base):
    __tablename__ = "completed_order_joints"
    
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('completed_orders.id', ondelete='CASCADE'), nullable=False)
    joint_type = Column(SQLEnum(JointType), nullable=False)
    joint_color = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    joint_thickness = Column(Float, nullable=False, default=0.5)  # Толщина стыка (0.5 или 0.8)
    
    order = relationship("CompletedOrder", back_populates="joints")

class CompletedOrderItem(Base):
    __tablename__ = "completed_order_items"
    
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('completed_orders.id', ondelete='CASCADE'), nullable=False)
    product_id = Column(Integer, nullable=True)
    quantity = Column(Integer, nullable=False)
    color = Column(String, nullable=False)
    thickness = Column(Float, nullable=False, default=0.5)  # Толщина продукции (0.5 или 0.8)
    
    order = relationship("CompletedOrder", back_populates="items")

class CompletedOrderGlue(Base):
    __tablename__ = "completed_order_glues"
    
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('completed_orders.id', ondelete='CASCADE'), nullable=False)
    quantity = Column(Integer, nullable=False)
    
    order = relationship("CompletedOrder", back_populates="glues")

class CompletedOrder(Base):
    __tablename__ = "completed_orders"
    
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, unique=True, nullable=False)  # ID исходного заказа
    manager_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    warehouse_user_id = Column(Integer, ForeignKey('users.id'), nullable=False)  # ID складовщика, выполнившего заказ
    installation_required = Column(Boolean, default=False)
    customer_phone = Column(String, nullable=False)
    delivery_address = Column(String, nullable=False)
    completed_at = Column(DateTime(timezone=True), server_default=func.now())
    
    manager = relationship("User", foreign_keys=[manager_id])
    warehouse_user = relationship("User", foreign_keys=[warehouse_user_id])
    joints = relationship("CompletedOrderJoint", back_populates="order", cascade="all, delete-orphan")
    items = relationship("CompletedOrderItem", back_populates="order", cascade="all, delete-orphan")
    glues = relationship("CompletedOrderGlue", back_populates="order", cascade="all, delete-orphan")

    def to_dict(self):
        joints_data = [{"type": joint.joint_type.value, "color": joint.joint_color, "quantity": joint.quantity, "thickness": joint.joint_thickness} for joint in self.joints] if self.joints else []
        items_data = [{"product_id": item.product_id, "color": item.color, "thickness": item.thickness, "quantity": item.quantity} for item in self.items] if self.items else []
            
        return {
            "id": self.id,
            "original_order_id": self.order_id,
            "items": items_data,
            "joints": joints_data,
            "glue_quantity": sum([glue.quantity for glue in self.glues]) if self.glues else 0,
            "installation_required": self.installation_required,
            "customer_phone": self.customer_phone,
            "delivery_address": self.delivery_address,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        } 