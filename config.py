import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    # Railway иногда выдаёт старый формат схемы, asyncpg требует postgresql://
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

CLICK_CARD = os.getenv("CLICK_CARD", "0000 0000 0000 0000")
PAYNET_CARD = os.getenv("PAYNET_CARD", "0000 0000 0000 0000")

SITE_URL = "https://xaruem.github.io/BoostCent/"

# Защита от спама некорректными ссылками/числами
INVALID_WINDOW_MINUTES = 10      # окно времени для подсчёта ошибок
INVALID_LIMIT = 5                # сколько ошибок за окно триггерит бан
SOFT_BAN_MINUTES = 60            # первый бан — временный (минуты)
# второй бан подряд (после истечения первого и нового нарушения) — постоянный (is_permanent=True)

# Минимальная сумма пополнения (защита от копеечного спама заявками)
# Максимума нет — админ может ввести любую сумму выше минимальной.
MIN_TOPUP_AMOUNT = 100
