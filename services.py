import re
from math import ceil

PLATFORM_NAMES = {"tg": "Telegram", "ig": "Instagram", "yt": "YouTube", "tt": "TikTok"}

PLATFORM_SERVICES = {
    "tg": ["tg_views", "tg_subs", "tg_reactions"],
    "ig": ["ig_views", "ig_subs", "ig_reactions"],
    "yt": ["yt_views", "yt_subs"],
    "tt": ["tt_views", "tt_likes", "tt_subs", "tt_reposts", "tt_comments"],
}

SERVICE_LABELS = {
    "tg_views": "👁 Просмотры",
    "tg_subs": "👤 Подписчики",
    "tg_reactions": "❤️ Реакции",
    "ig_views": "🎬 Reels",
    "ig_subs": "👤 Подписчики",
    "ig_reactions": "❤️ Реакции",
    "yt_views": "👁 Просмотры",
    "yt_subs": "👤 Подписчики",
    "tt_views": "👁 Просмотры",
    "tt_likes": "❤️ Лайки",
    "tt_subs": "👤 Подписчики",
    "tt_reposts": "🔁 Репосты",
    "tt_comments": "💬 Комментарии",
}

# link_type определяет что именно должен прислать пользователь и какой regex использовать
SERVICES = {
    "tg_views": {
        "platform": "tg", "title": "Просмотры",
        "free": {
            "price_per_1000": 0, "min": 50, "max": 100, "cooldown_days": 1,
            "link_type": "tg_post", "label": "Бесплатное продвижение",
            "extra": "Только для публичных каналов.\nОтправьте не ссылку канала, а пост с канала.\nДоступно 1 раз в день.",
        },
        "paid": {
            "price_per_1000": 7000, "min": 500, "max": 500000,
            "link_type": "tg_post", "label": "Платное продвижение",
            "extra": "Только для публичных каналов.\nОтправьте не ссылку канала, а пост с канала.",
        },
    },
    "tg_subs": {
        "platform": "tg", "title": "Подписчики",
        "free": {
            "price_per_1000": 0, "min": 10, "max": 30, "cooldown_days": 7,
            "link_type": "tg_channel", "label": "Бесплатное продвижение",
            "extra": "Только для публичных каналов и групп.",
        },
        "tiers": [
            {"key": "g30", "label": "30 дней гарантия", "price_per_1000": 16000},
            {"key": "g90", "label": "90 дней гарантия", "price_per_1000": 36000},
            {"key": "g365", "label": "365 дней гарантия", "price_per_1000": 52000},
        ],
        "min": 1000, "max": 300000, "link_type": "tg_channel",
        "extra": "Только для публичных каналов и групп.",
    },
    "tg_reactions": {
        "platform": "tg", "title": "Реакции",
        "free": {
            "price_per_1000": 0, "min": 50, "max": 50, "cooldown_days": 1,
            "link_type": "tg_post", "label": "Бесплатная реакция",
            "extra": "Отправьте не ссылку канала, а пост с канала.\nДоступно 1 раз в день.",
        },
        "paid": {
            "price_per_1000": 12000, "min": 1000, "max": 1000000,
            "link_type": "tg_post", "label": "Платная реакция",
            "extra": "Начинает работать от 1 до 30 минут.\nВ день от 1 до 600 реакций.\nТолько для публичных каналов и групп.\nОтправьте не ссылку канала, а пост с канала.",
        },
    },
    "ig_views": {
        "platform": "ig", "title": "Просмотры (Reels)",
        "free": {
            "price_per_1000": 0, "min": 500, "max": 500, "cooldown_days": 7,
            "link_type": "ig_post", "label": "Бесплатное продвижение",
            "extra": "Доступно 1 раз в неделю.",
        },
        "paid": {
            "price_per_1000": 7000, "min": 1000, "max": 1000000,
            "link_type": "ig_post", "label": "Платное продвижение",
        },
    },
    "ig_subs": {
        "platform": "ig", "title": "Подписчики",
        "tiers": [
            {"key": "nog", "label": "Без гарантии", "price_per_1000": 19000},
            {"key": "g30", "label": "Гарантия 30 дней", "price_per_1000": 31000},
            {"key": "g90", "label": "Гарантия 90 дней", "price_per_1000": 48000},
        ],
        "min": 1000, "max": 1000000, "link_type": "ig_profile",
    },
    "ig_reactions": {
        "platform": "ig", "title": "Реакции",
        "free": {
            "price_per_1000": 0, "min": 50, "max": 50, "cooldown_days": 1,
            "link_type": "ig_post", "label": "Бесплатная реакция",
            "extra": "Доступно 1 раз в день.",
        },
        "paid": {
            "price_per_1000": 12000, "min": 1000, "max": 500000,
            "link_type": "ig_post", "label": "Платное продвижение",
        },
    },
    "yt_views": {
        "platform": "yt", "title": "Просмотры",
        "paid": {
            "price_per_1000": 38000, "min": 1000, "max": 1000000,
            "link_type": "yt_video", "label": "Платное продвижение",
        },
    },
    "yt_subs": {
        "platform": "yt", "title": "Подписчики",
        "tiers": [{"key": "nog", "label": "Без гарантии", "price_per_1000": 120000}],
        "min": 1000, "max": 1000000, "link_type": "yt_channel",
    },
    "tt_views": {
        "platform": "tt", "title": "Просмотры",
        "paid": {
            "price_per_1000": 3000, "min": 1000, "max": 1000000,
            "link_type": "tt_video", "label": "Платное продвижение",
        },
    },
    "tt_likes": {
        "platform": "tt", "title": "Лайки",
        "paid": {
            "price_per_1000": 18000, "min": 1000, "max": 1000000,
            "link_type": "tt_video", "label": "Платное продвижение",
        },
    },
    "tt_subs": {
        "platform": "tt", "title": "Подписчики",
        "tiers": [
            {"key": "g1m", "label": "1 месяц гарантия", "price_per_1000": 130000},
            {"key": "g3m", "label": "3 месяца гарантия", "price_per_1000": 300000},
        ],
        "min": 1000, "max": 1000000, "link_type": "tt_profile",
    },
    "tt_reposts": {
        "platform": "tt", "title": "Репосты",
        "paid": {
            "price_per_1000": 55000, "min": 1000, "max": 1000000,
            "link_type": "tt_video", "label": "Платное продвижение",
        },
    },
    "tt_comments": {
        "platform": "tt", "title": "Комментарии",
        "paid": {
            "price_per_1000": 27000, "min": 1000, "max": 1000000,
            "link_type": "tt_video", "label": "Платное продвижение",
        },
    },
}

LINK_PATTERNS = {
    "tg_channel": re.compile(r'^(https?://)?(t\.me|telegram\.me)/(?!\+)[A-Za-z0-9_]{4,32}/?$|^@[A-Za-z0-9_]{4,32}$'),
    "tg_post": re.compile(r'^(https?://)?(t\.me|telegram\.me)/[A-Za-z0-9_]{4,32}/\d+/?$'),
    "ig_profile": re.compile(r'^(https?://)?(www\.)?instagram\.com/[A-Za-z0-9_.]{2,30}/?$'),
    "ig_post": re.compile(r'^(https?://)?(www\.)?instagram\.com/(p|reel|reels)/[A-Za-z0-9_-]+/?'),
    "yt_video": re.compile(r'^(https?://)?(www\.)?(youtube\.com/watch\?v=[\w-]+|youtu\.be/[\w-]+)'),
    "yt_channel": re.compile(r'^(https?://)?(www\.)?youtube\.com/(channel/|c/|@)[\w-]+'),
    "tt_video": re.compile(r'^(https?://)?(www\.)?(vm\.)?tiktok\.com/(@[\w.-]+/video/\d+|[\w-]+)/?'),
    "tt_profile": re.compile(r'^(https?://)?(www\.)?tiktok\.com/@[\w.-]+/?$|^@[\w.-]{2,24}$'),
}

LINK_HINTS = {
    "tg_channel": "Отправьте ссылку на канал, например:\nhttps://t.me/mychannel",
    "tg_post": "Отправьте ссылку на пост (не на канал), например:\nhttps://t.me/mychannel/123",
    "ig_profile": "Отправьте ссылку на профиль, например:\nhttps://instagram.com/username",
    "ig_post": "Отправьте ссылку на пост/Reels, например:\nhttps://instagram.com/p/xxxxx",
    "yt_video": "Отправьте ссылку на видео, например:\nhttps://youtube.com/watch?v=xxxxx",
    "yt_channel": "Отправьте ссылку на канал, например:\nhttps://youtube.com/@channel",
    "tt_video": "Отправьте ссылку на видео, например:\nhttps://www.tiktok.com/@username/video/1234567890",
    "tt_profile": "Отправьте ссылку на профиль или @username, например:\nhttps://www.tiktok.com/@username",
}


def validate_link(link_type: str, text: str) -> bool:
    pattern = LINK_PATTERNS.get(link_type)
    return bool(pattern and pattern.match(text.strip()))


def calc_price(price_per_1000: int, amount: int) -> int:
    return ceil(price_per_1000 * amount / 1000)


def get_variant_cfg(service_key: str, variant: str) -> dict:
    """variant: 'free' | 'paid' | tier key (напр. 'g30')"""
    cfg = SERVICES[service_key]
    if variant == "free":
        v = dict(cfg["free"])
    elif variant == "paid":
        v = dict(cfg["paid"])
    else:
        tier = next(t for t in cfg["tiers"] if t["key"] == variant)
        v = {
            "price_per_1000": tier["price_per_1000"],
            "min": cfg["min"], "max": cfg["max"],
            "link_type": cfg["link_type"],
            "label": tier["label"],
            "extra": cfg.get("extra", ""),
        }
    v.setdefault("cooldown_days", None)
    v.setdefault("extra", "")
    v.setdefault("label", "Платно" if v["price_per_1000"] else "Бесплатно")
    v["platform"] = cfg["platform"]
    v["service_title"] = cfg["title"]
    v["service_key"] = service_key
    v["variant"] = variant
    return v


def build_info_text(service_key: str, variant: str, order_id: int | None = None) -> str:
    v = get_variant_cfg(service_key, variant)
    lines = [f"<b>{v['service_title']} — {v['label']}</b>", ""]
    if order_id:
        lines.append(f"ID заявки: {order_id}")
    if v["price_per_1000"] == 0:
        lines.append("Цена: бесплатно")
    else:
        lines.append(f"Цена (1000) — {v['price_per_1000']} so'm")
    lines.append("")
    lines.append(f"Минимум: {v['min']} шт.")
    lines.append(f"Максимум: {v['max']} шт.")
    if v["cooldown_days"]:
        lines.append(f"Доступно раз в {v['cooldown_days']} дней.")
    if v["extra"]:
        lines.append("")
        lines.append(v["extra"])
    return "\n".join(lines)
