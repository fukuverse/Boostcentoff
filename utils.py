def user_ref(user_id: int, username: str | None) -> str:
    """Единый формат ссылки на пользователя для админ-уведомлений.
    Если username не задан (в Telegram это не обязательное поле),
    возвращает id без "(@None)"."""
    if username:
        return f"{user_id} (@{username})"
    return f"{user_id} (без username)"
