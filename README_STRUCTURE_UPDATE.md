# Обновление структуры базы данных заказов

Данное обновление исправляет структуру базы данных заказов в соответствии с требованиями:

## Основные изменения

1. Удалены таблицы:
   - `order_films` - информация о пленке теперь хранится только в `order_items`
   - `order_products` - информация о продукции теперь хранится только в `order_items`
   - `completed_order_films` - аналогично для завершенных заказов

2. Обновлены таблицы:
   - Проверено наличие столбца `joint_thickness` в таблице `order_joints`
   - Удален столбец `is_finished` в таблице `order_items` (если он был)
   - Обновлены модели в `models.py` для соответствия новой структуре

3. Исправлены отношения между таблицами:
   - `Order` теперь имеет связи только с `OrderItem`, `OrderJoint` и `OrderGlue`
   - `CompletedOrder` теперь имеет связи только с `CompletedOrderItem`, `CompletedOrderJoint` и `CompletedOrderGlue`

## Структура таблиц

### Таблица Orders
- `id`: Уникальный идентификатор заказа
- `manager_id`: ID менеджера, оформившего заказ
- `customer_phone`: Телефон клиента
- `delivery_address`: Адрес доставки
- `installation_required`: Требуется ли монтаж (True/False)
- `status`: Статус заказа
- `created_at`: Дата создания заказа
- `updated_at`: Дата последнего обновления заказа
- `completed_at`: Дата выполнения заказа (если завершен)

### Таблица Order Items
- `id`: Уникальный идентификатор записи
- `order_id`: Ссылка на заказ
- `product_id`: Ссылка на продукцию (панель с пленкой)
- `color`: Цвет готовой продукции
- `thickness`: Толщина готовой продукции
- `quantity`: Количество готовой продукции

### Таблица Order Joints
- `id`: Уникальный идентификатор записи
- `order_id`: Ссылка на заказ
- `joint_type`: Тип стыка (бабочка, простой, замыкающий)
- `joint_color`: Цвет стыка
- `joint_thickness`: Толщина стыка
- `quantity`: Количество стыков

### Таблица Order Glues
- `id`: Уникальный идентификатор записи
- `order_id`: Ссылка на заказ
- `quantity`: Количество клея

## Как применить миграцию

1. Убедитесь, что все изменения кода закоммичены и отправлены на Heroku:
```
git add models.py handlers/sales.py alembic/versions/fix_order_tables_structure.py README_STRUCTURE_UPDATE.md
git commit -m "Fix database structure for orders"
git push heroku main
```

2. Запустите миграцию на Heroku:
```
heroku run alembic upgrade head
```

3. Проверьте, что миграция успешно выполнена

## Откат миграции (при необходимости)

Для отката миграции выполните:

```
heroku run alembic downgrade fix_order_tables_structure-1
``` 