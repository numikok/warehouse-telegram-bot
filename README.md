# Telegram-бот для управления складом

Телеграм-бот для управления складом, производством и продажами.

## Быстрый деплой на Heroku

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/numikok/warehouse-telegram-bot)

## Переменные окружения

Для работы бота необходимо настроить следующие переменные окружения:

- `BOT_TOKEN` - токен Telegram-бота от BotFather
- `ADMIN_USER_ID` - ID пользователя Telegram для роли Супер-админа
- `DATABASE_URL` - URL подключения к базе данных PostgreSQL
- `HEROKU` - флаг, указывающий на запуск на Heroku (установите в "1")

## Установка и запуск

### Локальный запуск

1. Клонируйте репозиторий
```
git clone https://github.com/numikok/warehouse-telegram-bot.git
cd warehouse-telegram-bot
```

2. Создайте файл `.env` с переменными окружения
```
BOT_TOKEN=ваш_токен_бота
ADMIN_USER_ID=ваш_id_в_телеграм
DATABASE_URL=postgresql://user:password@localhost/db_name
```

3. Установите зависимости
```
pip install -r requirements.txt
```

4. Запустите бота
```
python main.py
```

### Деплой на Heroku вручную

1. Создайте приложение на Heroku
```
heroku create имя-вашего-приложения
```

2. Добавьте базу данных PostgreSQL
```
heroku addons:create heroku-postgresql:hobby-dev
```

3. Настройте переменные окружения
```
heroku config:set BOT_TOKEN=ваш_токен_бота
heroku config:set ADMIN_USER_ID=ваш_id_в_телеграм
heroku config:set HEROKU=1
```

4. Деплой на Heroku
```
git push heroku main
```

5. Запустите приложение
```
heroku ps:scale web=1
```

## Роли в системе

- **Супер-администратор** - полный доступ ко всем функциям
- **Менеджер по продажам** - создание заказов, проверка наличия товаров
- **Производство** - регистрация поступления сырья, производство панелей
- **Склад** - контроль остатков, комплектация заказов
- **Ожидание роли** - пользователь ждет назначения роли

## Features

- User role management (Super Admin, Sales Manager, Production, Warehouse Worker)
- Inventory tracking for:
  - Colors (140 types with unique markings)
  - Empty panels
  - Film
  - Finished products
- Production tracking
- Sales management
- Warehouse notifications
- Reporting system

## Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file with the following variables:
```
BOT_TOKEN=your_telegram_bot_token
DATABASE_URL=postgresql://user:password@localhost:5432/warehouse_bot
ADMIN_USER_ID=your_telegram_user_id
```

4. Initialize the database:
```bash
alembic upgrade head
```

5. Run the bot:
```bash
python main.py
```

## Deploy to Heroku

For quick deployment to Heroku, click the "Deploy to Heroku" button at the top of this README.

For detailed deployment instructions, see [HEROKU_DEPLOY.md](HEROKU_DEPLOY.md).

## Database Structure

The bot uses PostgreSQL with the following main tables:
- users (user management and roles)
- colors (color inventory)
- panels (empty panels inventory)
- film (film inventory)
- finished_products (finished products inventory)
- operations (operation history)

## Commands

- `/start` - Start the bot
- `/help` - Show help information
- `/приход` - Record incoming materials (Production)
- `/производство` - Record production (Production)
- `/продажа` - Create sales order (Sales Manager)
- `/отчет` - Generate reports (Super Admin)
