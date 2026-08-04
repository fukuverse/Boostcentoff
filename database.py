import asyncpg
import datetime
from config import DATABASE_URL, INVALID_WINDOW_MINUTES, INVALID_LIMIT, SOFT_BAN_MINUTES

pool: asyncpg.Pool | None = None


async def init_db():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)
    async with pool.acquire() as con:
        await con.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            balance BIGINT NOT NULL DEFAULT 0,
            is_banned BOOLEAN NOT NULL DEFAULT FALSE,
            ban_permanent BOOLEAN NOT NULL DEFAULT FALSE,
            ban_until TIMESTAMP,
            ban_count INT NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            platform TEXT NOT NULL,
            service_key TEXT NOT NULL,
            variant TEXT NOT NULL,
            amount INT NOT NULL,
            link TEXT NOT NULL,
            price BIGINT NOT NULL,
            status TEXT NOT NULL DEFAULT 'В ожидании',
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS topups (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            method TEXT NOT NULL,
            file_id TEXT,
            amount BIGINT,
            status TEXT NOT NULL DEFAULT 'В ожидании',
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS balance_logs (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            admin_id BIGINT,
            amount BIGINT NOT NULL,
            balance_after BIGINT NOT NULL,
            reason TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS free_usage (
            user_id BIGINT NOT NULL,
            service_key TEXT NOT NULL,
            last_used_at TIMESTAMP NOT NULL,
            PRIMARY KEY (user_id, service_key)
        );

        CREATE TABLE IF NOT EXISTS invalid_events (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """)


async def close_db():
    if pool:
        await pool.close()


# ---------------------------------------------------------------- users
async def ensure_user(user_id: int, username: str | None) -> bool:
    """Возвращает True если пользователь новый (создан только что)."""
    async with pool.acquire() as con:
        row = await con.fetchrow("SELECT user_id FROM users WHERE user_id=$1", user_id)
        if row:
            await con.execute("UPDATE users SET username=$2 WHERE user_id=$1", user_id, username)
            return False
        await con.execute(
            "INSERT INTO users (user_id, username) VALUES ($1, $2)", user_id, username
        )
        return True


async def get_balance(user_id: int) -> int:
    async with pool.acquire() as con:
        row = await con.fetchrow("SELECT balance FROM users WHERE user_id=$1", user_id)
        return row["balance"] if row else 0


async def change_balance(user_id: int, delta: int, admin_id: int | None = None, reason: str = "") -> int:
    async with pool.acquire() as con:
        async with con.transaction():
            # upsert: если пользователя почему-то ещё нет в users — создаём его с этим балансом,
            # а не падаем с ошибкой (раньше тут был TypeError: 'NoneType' object is not subscriptable)
            row = await con.fetchrow(
                "INSERT INTO users (user_id, balance) VALUES ($1, $2) "
                "ON CONFLICT (user_id) DO UPDATE SET balance = users.balance + EXCLUDED.balance "
                "RETURNING balance",
                user_id, delta,
            )
            new_balance = row["balance"]
            await con.execute(
                "INSERT INTO balance_logs (user_id, admin_id, amount, balance_after, reason) "
                "VALUES ($1,$2,$3,$4,$5)",
                user_id, admin_id, delta, new_balance, reason,
            )
            return new_balance


async def get_balance_logs(limit: int = 20):
    async with pool.acquire() as con:
        return await con.fetch(
            "SELECT * FROM balance_logs ORDER BY created_at DESC LIMIT $1", limit
        )


# ---------------------------------------------------------------- бан / спам-защита
async def register_invalid_event(user_id: int) -> dict:
    """Логирует некорректный ввод, проверяет частоту и банит при превышении.
    Возвращает {"banned": bool, "permanent": bool, "until": datetime|None, "count": int}"""
    async with pool.acquire() as con:
        await con.execute("INSERT INTO invalid_events (user_id) VALUES ($1)", user_id)
        since = datetime.datetime.utcnow() - datetime.timedelta(minutes=INVALID_WINDOW_MINUTES)
        count = await con.fetchval(
            "SELECT COUNT(*) FROM invalid_events WHERE user_id=$1 AND created_at >= $2",
            user_id, since,
        )
        if count < INVALID_LIMIT:
            return {"banned": False, "permanent": False, "until": None, "count": count}

        user = await con.fetchrow("SELECT ban_count FROM users WHERE user_id=$1", user_id)
        prev_bans = user["ban_count"] if user else 0

        if prev_bans == 0:
            until = datetime.datetime.utcnow() + datetime.timedelta(minutes=SOFT_BAN_MINUTES)
            await con.execute(
                "UPDATE users SET is_banned=TRUE, ban_permanent=FALSE, ban_until=$2, ban_count=ban_count+1 "
                "WHERE user_id=$1",
                user_id, until,
            )
            return {"banned": True, "permanent": False, "until": until, "count": count}
        else:
            await con.execute(
                "UPDATE users SET is_banned=TRUE, ban_permanent=TRUE, ban_until=NULL, ban_count=ban_count+1 "
                "WHERE user_id=$1",
                user_id,
            )
            return {"banned": True, "permanent": True, "until": None, "count": count}


async def is_banned(user_id: int) -> bool:
    async with pool.acquire() as con:
        row = await con.fetchrow(
            "SELECT is_banned, ban_permanent, ban_until FROM users WHERE user_id=$1", user_id
        )
        if not row or not row["is_banned"]:
            return False
        if row["ban_permanent"]:
            return True
        if row["ban_until"] and row["ban_until"] > datetime.datetime.utcnow():
            return True
        # временный бан истёк — снимаем автоматически
        await con.execute(
            "UPDATE users SET is_banned=FALSE, ban_until=NULL WHERE user_id=$1", user_id
        )
        return False


async def unban_user(user_id: int):
    async with pool.acquire() as con:
        await con.execute(
            "UPDATE users SET is_banned=FALSE, ban_permanent=FALSE, ban_until=NULL WHERE user_id=$1",
            user_id,
        )


# ---------------------------------------------------------------- бесплатное продвижение (cooldown)
async def check_free_cooldown(user_id: int, service_key: str, cooldown_days: int) -> tuple[bool, datetime.datetime | None]:
    """Возвращает (доступно_ли, когда_станет_доступно)"""
    async with pool.acquire() as con:
        row = await con.fetchrow(
            "SELECT last_used_at FROM free_usage WHERE user_id=$1 AND service_key=$2",
            user_id, service_key,
        )
        if not row:
            return True, None
        next_available = row["last_used_at"] + datetime.timedelta(days=cooldown_days)
        if datetime.datetime.utcnow() >= next_available:
            return True, None
        return False, next_available


async def mark_free_used(user_id: int, service_key: str):
    async with pool.acquire() as con:
        await con.execute(
            "INSERT INTO free_usage (user_id, service_key, last_used_at) VALUES ($1,$2,NOW()) "
            "ON CONFLICT (user_id, service_key) DO UPDATE SET last_used_at=NOW()",
            user_id, service_key,
        )


# ---------------------------------------------------------------- заказы
async def create_order(user_id: int, platform: str, service_key: str, variant: str,
                        amount: int, link: str, price: int) -> int:
    async with pool.acquire() as con:
        row = await con.fetchrow(
            "INSERT INTO orders (user_id, platform, service_key, variant, amount, link, price) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id",
            user_id, platform, service_key, variant, amount, link, price,
        )
        return row["id"]


async def get_order(order_id: int):
    async with pool.acquire() as con:
        return await con.fetchrow("SELECT * FROM orders WHERE id=$1", order_id)


async def get_user_orders(user_id: int, limit: int = 20):
    async with pool.acquire() as con:
        return await con.fetch(
            "SELECT * FROM orders WHERE user_id=$1 ORDER BY id DESC LIMIT $2", user_id, limit
        )


async def set_order_status(order_id: int, status: str):
    async with pool.acquire() as con:
        await con.execute("UPDATE orders SET status=$2 WHERE id=$1", order_id, status)


def _orders_where(status: str | None, platform: str | None, service_key: str | None):
    conditions = []
    params = []
    if status:
        params.append(status)
        conditions.append(f"status=${len(params)}")
    if platform:
        params.append(platform)
        conditions.append(f"platform=${len(params)}")
    if service_key:
        params.append(service_key)
        conditions.append(f"service_key=${len(params)}")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return where, params


async def get_orders_page(offset: int = 0, limit: int = 10, status: str | None = None,
                           platform: str | None = None, service_key: str | None = None):
    where, params = _orders_where(status, platform, service_key)
    async with pool.acquire() as con:
        params_full = params + [limit, offset]
        query = f"SELECT * FROM orders {where} ORDER BY id DESC LIMIT ${len(params)+1} OFFSET ${len(params)+2}"
        return await con.fetch(query, *params_full)


async def count_orders(status: str | None = None, platform: str | None = None,
                        service_key: str | None = None) -> int:
    where, params = _orders_where(status, platform, service_key)
    async with pool.acquire() as con:
        query = f"SELECT COUNT(*) FROM orders {where}"
        return await con.fetchval(query, *params)


# ---------------------------------------------------------------- пополнения
async def create_topup(user_id: int, method: str, file_id: str) -> int:
    async with pool.acquire() as con:
        row = await con.fetchrow(
            "INSERT INTO topups (user_id, method, file_id) VALUES ($1,$2,$3) RETURNING id",
            user_id, method, file_id,
        )
        return row["id"]


async def get_topup(topup_id: int):
    async with pool.acquire() as con:
        return await con.fetchrow("SELECT * FROM topups WHERE id=$1", topup_id)


async def set_topup_status(topup_id: int, status: str, amount: int | None = None) -> bool:
    """Обновляет статус заявки, только если она ещё 'В ожидании' (защита от повторной обработки).
    Возвращает True, если обновление прошло."""
    async with pool.acquire() as con:
        if amount is not None:
            row = await con.fetchrow(
                "UPDATE topups SET status=$2, amount=$3 "
                "WHERE id=$1 AND status='В ожидании' RETURNING id",
                topup_id, status, amount,
            )
        else:
            row = await con.fetchrow(
                "UPDATE topups SET status=$2 "
                "WHERE id=$1 AND status='В ожидании' RETURNING id",
                topup_id, status,
            )
        return row is not None


async def get_pending_topups(limit: int = 10):
    async with pool.acquire() as con:
        return await con.fetch(
            "SELECT * FROM topups WHERE status='В ожидании' ORDER BY id ASC LIMIT $1", limit
        )


async def count_pending_topups() -> int:
    async with pool.acquire() as con:
        return await con.fetchval("SELECT COUNT(*) FROM topups WHERE status='В ожидании'")


# ---------------------------------------------------------------- рассылка
async def get_all_user_ids():
    async with pool.acquire() as con:
        rows = await con.fetch("SELECT user_id FROM users")
        return [r["user_id"] for r in rows]


# ---------------------------------------------------------------- статистика
async def stats_users():
    async with pool.acquire() as con:
        total = await con.fetchval("SELECT COUNT(*) FROM users")
        today = await con.fetchval(
            "SELECT COUNT(*) FROM users WHERE created_at >= NOW() - INTERVAL '1 day'"
        )
        banned = await con.fetchval("SELECT COUNT(*) FROM users WHERE is_banned=TRUE")
        return {"total": total, "today": today, "banned": banned}


async def stats_orders():
    async with pool.acquire() as con:
        total = await con.fetchval("SELECT COUNT(*) FROM orders")
        pending = await con.fetchval("SELECT COUNT(*) FROM orders WHERE status='В ожидании'")
        done = await con.fetchval("SELECT COUNT(*) FROM orders WHERE status='Сделано'")
        cancelled = await con.fetchval("SELECT COUNT(*) FROM orders WHERE status='Отменено'")
        return {"total": total, "pending": pending, "done": done, "cancelled": cancelled}


async def stats_turnover():
    async with pool.acquire() as con:
        spent = await con.fetchval(
            "SELECT COALESCE(SUM(price),0) FROM orders WHERE status != 'Отменено'"
        )
        topped_up = await con.fetchval(
            "SELECT COALESCE(SUM(amount),0) FROM balance_logs WHERE amount > 0"
        )
        return {"spent": spent, "topped_up": topped_up}


async def stats_top_services(limit: int = 5):
    async with pool.acquire() as con:
        return await con.fetch(
            "SELECT service_key, COUNT(*) as cnt FROM orders GROUP BY service_key "
            "ORDER BY cnt DESC LIMIT $1", limit
        )
