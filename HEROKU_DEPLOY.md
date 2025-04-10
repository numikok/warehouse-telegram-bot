# Деплой Telegram-бота на Heroku

## Требования
- Аккаунт на [Heroku](https://heroku.com)
- Git, установленный на вашем компьютере
- Heroku CLI, установленный на вашем компьютере
- Токен бота от [@BotFather](https://t.me/BotFather)
- Ваш Telegram User ID (можно получить через [@userinfobot](https://t.me/userinfobot))

## Способ 1: Деплой через кнопку "Deploy to Heroku"

1. Нажмите на кнопку "Deploy to Heroku" в README проекта
2. Заполните необходимые переменные окружения:
   - `BOT_TOKEN`: Токен вашего Telegram-бота
   - `ADMIN_USER_ID`: Ваш Telegram User ID для назначения роли супер-администратора
3. Нажмите "Deploy"
4. После завершения деплоя, перейдите на вкладку "Resources" и убедитесь, что включен dyno для worker: переключите рычажок рядом с "worker: python main.py"

## Способ 2: Деплой через Heroku CLI

1. Склонируйте репозиторий:
   ```
   git clone <URL репозитория>
   cd <директория проекта>
   ```

2. Войдите в Heroku:
   ```
   heroku login
   ```

3. Создайте новое приложение Heroku:
   ```
   heroku create <имя-приложения>
   ```

4. Добавьте базу данных PostgreSQL:
   ```
   heroku addons:create heroku-postgresql:hobby-dev
   ```

5. Настройте переменные окружения:
   ```
   heroku config:set BOT_TOKEN=<ваш токен бота>
   heroku config:set ADMIN_USER_ID=<ваш Telegram User ID>
   ```

6. Отправьте код в Heroku:
   ```
   git push heroku main
   ```

7. Запустите миграции базы данных:
   ```
   heroku run alembic upgrade head
   ```

8. Активируйте worker dyno:
   ```
   heroku ps:scale worker=1 web=0
   ```

   Или, если вам также нужен веб-сервер для предотвращения усыпления:
   ```
   heroku ps:scale worker=1 web=1
   ```

## Настройка автоматического перезапуска (опционально)

Если вы хотите, чтобы ваш бот автоматически перезапускался в случае сбоя:

1. Установите add-on Heroku Scheduler:
   ```
   heroku addons:create scheduler:standard
   ```

2. Откройте панель Scheduler:
   ```
   heroku addons:open scheduler
   ```

3. Добавьте новое задание с командой:
   ```
   curl -X POST https://<имя-приложения>.herokuapp.com/
   ```
   с периодичностью каждые 10 минут или час.

## Мониторинг и отладка

- Просмотр логов:
  ```
  heroku logs --tail
  ```

- Запуск консоли:
  ```
  heroku run bash
  ```

- Проверка статуса dyno:
  ```
  heroku ps
  ```

## Устранение проблем

### Проблема с типом PostgreSQL enum

Если вы столкнулись с ошибкой добавления значений в PostgreSQL enum после деплоя:

1. Подключитесь к консоли Heroku:
   ```
   heroku run bash
   ```

2. Запустите скрипт обновления enum:
   ```
   python update_userrole_enum.py
   ```

### Проблема с подключением к базе данных

Если бот не может подключиться к базе данных, проверьте формат DATABASE_URL:

1. Проверьте текущее значение:
   ```
   heroku config:get DATABASE_URL
   ```

2. Удостоверьтесь, что в коде есть преобразование из "postgres://" в "postgresql://" 

## Информация о процессах (dynos)

В Procfile определены два типа процессов:
- `worker`: Основной процесс бота, использующий Telegram Bot API в режиме long polling
- `web`: Веб-сервер, который поддерживает активность приложения, предотвращая его усыпление

Для экономии ресурсов рекомендуется включать только worker процесс:
```
heroku ps:scale worker=1 web=0
```

Если вы хотите избежать усыпления приложения (для бесплатных аккаунтов Heroku), включите также web процесс:
```
heroku ps:scale worker=1 web=1
``` 