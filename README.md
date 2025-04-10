# Warehouse Management Telegram Bot

Telegram bot for warehouse management, production tracking, and sales management.

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy)

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
- `/отчет` - Generate reports (Super Admin) # warehouse-telegram-bot
