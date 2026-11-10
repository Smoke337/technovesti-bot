# ТехноВести — Telegram-бот новостей IT, науки и космоса

Бот публикует в канал [@technonews337](https://t.me/technonews337) новости
из российских источников: Habr, 3DNews, Hi-News, CNews, N+1, Naked Science.

## Расписание (Europe/Saratov, UTC+4)

- Дайджест «Главное за сутки» — ежедневно в 8:30
- Отдельные посты с картинкой — в 9:14, 11:14, 13:14, 15:14, 17:14, 19:14, 21:14

Расписание выполняется через GitHub Actions (`.github/workflows/`).

## Настройка

1. Создайте бота у [@BotFather](https://t.me/BotFather), добавьте его
   администратором канала с правом публикации сообщений.
2. В настройках репозитория: **Settings → Secrets and variables → Actions →
   New repository secret**:
   - `BOT_TOKEN` — токен от BotFather
   - `CHAT_ID` — `@имя_канала`
3. Готово — планировщик работает. Ручной запуск: вкладка **Actions** →
   выбрать workflow → **Run workflow**.

## Локальный запуск

```
python bot.py            # один пост
python bot.py --digest   # дайджест
python bot.py --test     # предпросмотр без отправки
```

Локально настройки берутся из `config.json` (`bot_token`, `chat_id`,
`max_chars`). В облаке — из переменных окружения `BOT_TOKEN` и `CHAT_ID`.

Файл `posted.json` хранит опубликованные ссылки, чтобы не было повторов;
workflow коммитит его обратно в репозиторий после каждой публикации.
