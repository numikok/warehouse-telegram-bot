# Order Table Migration

This migration removes deprecated fields from the `orders` and `completed_orders` tables that are now stored in related tables:

## Removed Fields
- `film_code` (цвет пленки) - now stored in `order_films`
- `panel_quantity` (количество панелей) - calculated from related products
- `joint_type` (тип стыка) - now stored in `order_joints` 
- `joint_color` (цвет стыка) - now stored in `order_joints`
- `joint_quantity` (количество стыков) - calculated from related joints
- `glue_quantity` (количество клея) - now stored in `order_glues`
- `panel_thickness` (толщина панели) - now stored in each product/item record
- `joint_thickness` (толщина стыка) - already in `order_joints`

## Remaining Fields
- `id`: Уникальный идентификатор заказа
- `manager_id`: ID менеджера, оформившего заказ
- `customer_phone`: Телефон клиента
- `delivery_address`: Адрес доставки
- `installation_required`: Требуется ли монтаж (True/False)
- `status`: Статус заказа (new, in_progress, completed, etc.)
- `created_at`: Дата создания заказа
- `updated_at`: Дата последнего обновления заказа
- `completed_at`: Дата выполнения заказа (если завершен)

## How to Run Migration

1. Make sure all code changes are committed and pushed to Heroku
2. Run the migration:

```
heroku run alembic upgrade head
```

3. Verify that the migration completed successfully

## Rollback (if needed)

To roll back this migration:

```
heroku run alembic downgrade remove_deprecated_order_fields-1
``` 