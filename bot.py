import html
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes,
)

from config import BOT_TOKEN, OWNER_IDS, RANKS, DEVELOPERS_TEXT
from database import Database, init_db

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

db = Database()

PER_PAGE = 6  


def effective_rank(user_id: int) -> str:
    """Возвращает ранг с учётом жёстко прописанных владельцев."""
    if user_id in OWNER_IDS:
        return "owner"
    return db.get_user_rank(user_id)


def is_admin(user_id: int) -> bool:
    return effective_rank(user_id) in ("owner", "admin")


def is_staff(user_id: int) -> bool:
    return effective_rank(user_id) in ("owner", "admin", "moderator")


def rank_label(rank: str) -> str:
    return RANKS.get(rank, RANKS["user"])


def kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📬 Предложка",       callback_data="cat:suggest")],
        [InlineKeyboardButton("💬 Связь с админом", callback_data="cat:contact")],
        [InlineKeyboardButton("👨‍💻 Разработчики",   callback_data="cat:devs")],
    ])


def kb_back(to: str = "main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Назад", callback_data=f"back:{to}")
    ]])


def kb_admin_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📬 Предложки",  callback_data="adm:suggs:0"),
            InlineKeyboardButton("💬 Сообщения",  callback_data="adm:msgs:0"),
        ],
        [InlineKeyboardButton("👥 Пользователи", callback_data="adm:users:0")],
        [InlineKeyboardButton("🏅 Выдать ранг",  callback_data="adm:rank_menu")],
        [InlineKeyboardButton("📊 Статистика",   callback_data="adm:stats")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back:main")],
    ])



async def notify_staff(context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None):
    """Отправляет сообщение всему составу: владельцы, админы, модераторы."""
    staff = db.get_users_by_rank(["owner", "admin", "moderator"])
    notified = set()
    for u in staff:
        try:
            await context.bot.send_message(
                u["user_id"], text, parse_mode="HTML", reply_markup=reply_markup
            )
            notified.add(u["user_id"])
        except Exception as e:
            logger.warning(f"notify_staff: не удалось отправить {u['user_id']}: {e}")
    for oid in OWNER_IDS:
        if oid not in notified:
            try:
                await context.bot.send_message(
                    oid, text, parse_mode="HTML", reply_markup=reply_markup
                )
            except Exception as e:
                logger.warning(f"notify_staff: не удалось отправить владельцу {oid}: {e}")


async def safe_send(context: ContextTypes.DEFAULT_TYPE, user_id: int, text: str):
    try:
        await context.bot.send_message(user_id, text, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"safe_send: не удалось отправить {user_id}: {e}")


async def edit_or_send(update: Update, text: str, reply_markup=None, parse_mode="Markdown"):
    """Редактирует сообщение (если колбэк) или отправляет новое."""
    kw = dict(text=text, parse_mode=parse_mode, reply_markup=reply_markup)
    if update.callback_query:
        await update.callback_query.edit_message_text(**kw)
    else:
        await update.message.reply_text(**kw)



async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db.add_user(u.id, u.username or "", u.full_name)


    if u.id in OWNER_IDS and db.get_user_rank(u.id) != "owner":
        db.set_user_rank(u.id, "owner")

    rank = effective_rank(u.id)
    await update.message.reply_text(
        f"👋 Привет, *{u.first_name}*!\n"

        f"🏅 Ваш ранг: {rank_label(rank)}\n\n"
        "Выберите раздел:",
        parse_mode="Markdown",
        reply_markup=kb_main(),
    )




async def cmd_admpanel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db.add_user(u.id, u.username or "", u.full_name)

    if u.id in OWNER_IDS and db.get_user_rank(u.id) != "owner":
        db.set_user_rank(u.id, "owner")

    if not is_admin(u.id):
        await update.message.reply_text("❌ У вас нет доступа к панели администратора.")
        return

    await update.message.reply_text(
        f"🔐 *Панель администратора*\n"
        f"🏅 Ваш ранг: {rank_label(effective_rank(u.id))}\n\n"
        "Выберите раздел:",
        parse_mode="Markdown",
        reply_markup=kb_admin_panel(),
    )



async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    data = query.data

    if data == "back:main":
        rank = effective_rank(user.id)
        await query.edit_message_text(
            f"👋 Привет, *{user.first_name}*!\n"
            f"🏅 Ваш ранг: {rank_label(rank)}\n\n"
            "Выберите раздел:",
            parse_mode="Markdown",
            reply_markup=kb_main(),
        )
        return

    if data == "back:adm":
        if not is_admin(user.id):
            await query.edit_message_text("❌ Доступ запрещён.")
            return
        await query.edit_message_text(
            f"🔐 *Панель администратора*\n"
            f"🏅 Ваш ранг: {rank_label(effective_rank(user.id))}\n\n"
            "Выберите раздел:",
            parse_mode="Markdown",
            reply_markup=kb_admin_panel(),
        )
        return


    if data == "cat:suggest":
        context.user_data["state"] = "typing_suggestion"
        await query.edit_message_text(
            "📬 *Предложка*\n\n"
            "Напишите вашу идею или предложение — мы обязательно рассмотрим его!\n\n"
            "✏️ Введите текст предложения:",
            parse_mode="Markdown",
            reply_markup=kb_back("main"),
        )
        return

    if data == "cat:contact":
        context.user_data["state"] = "typing_contact"
        await query.edit_message_text(
            "💬 *Связь с администратором*\n\n"
            "Напишите ваше сообщение — администратор ответит вам как можно скорее.\n\n"
            "✏️ Введите сообщение:",
            parse_mode="Markdown",
            reply_markup=kb_back("main"),
        )
        return

    if data == "cat:devs":
        await query.edit_message_text(
            f"👨‍💻 *Разработчики*\n\n{DEVELOPERS_TEXT}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📲 Перейти в студию", url="https://t.me/kodvenstudio")],
                [InlineKeyboardButton("🔙 Назад", callback_data="back:main")],
            ]),
        )
        return


    parts = data.split(":")
    if parts[0] != "adm":
        return

    section = parts[1] if len(parts) > 1 else ""


    if section == "stats":
        if not is_admin(user.id):
            await query.edit_message_text("❌ Доступ запрещён.")
            return
        s = db.get_stats()
        await query.edit_message_text(
            "📊 *Статистика*\n\n"
            f"👥 Пользователей: *{s['total_users']}*\n"
            f"🛡️ Администраторов: *{s['admins']}*\n"
            f"⚔️ Модераторов: *{s['mods']}*\n\n"
            f"📬 Предложений всего: *{s['total_suggs']}*\n"
            f"🕐 Ожидают рассмотрения: *{s['pending_suggs']}*\n\n"
            f"💬 Сообщений всего: *{s['total_msgs']}*\n"
            f"📩 Непрочитанных: *{s['unread_msgs']}*",
            parse_mode="Markdown",
            reply_markup=kb_back("adm"),
        )
        return


    if section == "suggs":
        if not is_staff(user.id):
            await query.edit_message_text("❌ Доступ запрещён.")
            return
        page = int(parts[2]) if len(parts) > 2 else 0
        await _show_suggestions(query, page)
        return

    if section == "sugg_detail":
        if not is_staff(user.id):
            await query.edit_message_text("❌ Доступ запрещён.")
            return
        sugg = db.get_suggestion(int(parts[2]))
        if not sugg:
            await query.edit_message_text("❌ Предложение не найдено.", reply_markup=kb_back("adm"))
            return
        await _show_suggestion_detail(query, sugg, user.id)
        return

    if section == "sugg_approve":
        if not is_staff(user.id):
            return
        sugg = db.get_suggestion(int(parts[2]))
        if sugg:
            db.update_suggestion(sugg["id"], status="approved")
            await safe_send(
                context, sugg["user_id"],
                f"✅ Ваше предложение *#{sugg['id']}* было *одобрено*!\n\n_{sugg['text']}_",
            )
        await query.edit_message_text(
            "✅ Предложение одобрено! Пользователь уведомлён.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📬 К предложкам", callback_data="adm:suggs:0"),
                InlineKeyboardButton("🏠 Панель",       callback_data="back:adm"),
            ]]),
        )
        return

    if section == "sugg_reject":
        if not is_staff(user.id):
            return
        sugg = db.get_suggestion(int(parts[2]))
        if sugg:
            db.update_suggestion(sugg["id"], status="rejected")
            await safe_send(
                context, sugg["user_id"],
                f"❌ Ваше предложение *#{sugg['id']}* было *отклонено*.\n\n_{sugg['text']}_",
            )
        await query.edit_message_text(
            "❌ Предложение отклонено. Пользователь уведомлён.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📬 К предложкам", callback_data="adm:suggs:0"),
                InlineKeyboardButton("🏠 Панель",       callback_data="back:adm"),
            ]]),
        )
        return

    if section == "sugg_reply":
        if not is_staff(user.id):
            return
        sugg_id = int(parts[2])
        context.user_data["state"] = f"adm_reply_sugg:{sugg_id}"
        await query.edit_message_text(
            "✏️ Введите ответ на предложение:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Отмена", callback_data=f"adm:sugg_detail:{sugg_id}")
            ]]),
        )
        return


    if section == "msgs":
        if not is_staff(user.id):
            await query.edit_message_text("❌ Доступ запрещён.")
            return
        page = int(parts[2]) if len(parts) > 2 else 0
        await _show_messages(query, page)
        return

    if section == "msg_detail":
        if not is_staff(user.id):
            await query.edit_message_text("❌ Доступ запрещён.")
            return
        msg = db.get_admin_message(int(parts[2]))
        if not msg:
            await query.edit_message_text("❌ Сообщение не найдено.", reply_markup=kb_back("adm"))
            return
        db.mark_message_read(msg["id"])
        await _show_message_detail(query, msg, user.id)
        return

    if section == "msg_reply":
        if not is_staff(user.id):
            return
        msg_id = int(parts[2])
        context.user_data["state"] = f"adm_reply_msg:{msg_id}"
        await query.edit_message_text(
            "✏️ Введите ответ пользователю:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Отмена", callback_data=f"adm:msg_detail:{msg_id}")
            ]]),
        )
        return


    if section == "users":
        if not is_admin(user.id):
            await query.edit_message_text("❌ Доступ запрещён.")
            return
        page = int(parts[2]) if len(parts) > 2 else 0
        await _show_users(query, page)
        return

    if section == "user_detail":
        if not is_admin(user.id):
            await query.edit_message_text("❌ Доступ запрещён.")
            return
        target = db.get_user(int(parts[2]))
        if not target:
            await query.edit_message_text("❌ Пользователь не найден.", reply_markup=kb_back("adm"))
            return
        await _show_user_detail(query, context, target, user.id)
        return

    if section in ("give_admin", "give_mod", "remove_rank"):
        if not is_admin(user.id):
            await query.answer("❌ Недостаточно прав!", show_alert=True)
            return
        target_id = int(parts[2])
        target_rank = effective_rank(target_id)
        if target_rank == "owner":
            await query.answer("❌ Нельзя изменить ранг Владельца!", show_alert=True)
            return

        new_rank_map   = {"give_admin": "admin", "give_mod": "moderator", "remove_rank": "user"}
        notify_msg_map = {
            "give_admin":   "🛡️ Вам выдан ранг *Администратор*!",
            "give_mod":     "⚔️ Вам выдан ранг *Модератор*!",
            "remove_rank":  "👤 Ваш ранг был сброшен до *Пользователя*.",
        }
        new_rank = new_rank_map[section]
        db.set_user_rank(target_id, new_rank)
        await safe_send(context, target_id, notify_msg_map[section])

        target = db.get_user(target_id)
        await query.answer(f"✅ Ранг обновлён → {rank_label(new_rank)}")
        await _show_user_detail(query, context, target, user.id)
        return

    
    if section == "block":
        if not is_staff(user.id):
            await query.answer("❌ Недостаточно прав!", show_alert=True)
            return
        target_id = int(parts[2])
        if effective_rank(target_id) in ("owner", "admin", "moderator"):
            await query.answer("❌ Нельзя заблокировать сотрудника!", show_alert=True)
            return
        db.block_user(target_id)
        target = db.get_user(target_id)
        name = f"@{target['username']}" if target and target.get("username") else str(target_id)
        await safe_send(context, target_id, "🚫 Вы были заблокированы администрацией.")
        await query.answer(f"✅ Пользователь {name} заблокирован!", show_alert=True)
        try:
         
            current = query.message.reply_markup
            new_rows = []
            for row in (current.inline_keyboard if current else []):
                new_row = [btn for btn in row if "block" not in btn.callback_data]
                if new_row:
                    new_rows.append(new_row)
            new_rows.append([InlineKeyboardButton(f"🚫 Заблокирован: {name}", callback_data="noop")])
            await query.edit_message_reply_markup(InlineKeyboardMarkup(new_rows))
        except Exception:
            pass
        return

    if section == "unblock":
        if not is_staff(user.id):
            await query.answer("❌ Недостаточно прав!", show_alert=True)
            return
        target_id = int(parts[2])
        db.unblock_user(target_id)
        await safe_send(context, target_id, "✅ Вы были разблокированы администрацией.")
        await query.answer("✅ Пользователь разблокирован!")
        return

    if section == "noop":
        await query.answer()
        return

 
    if section == "rank_menu":
        if not is_admin(user.id):
            await query.edit_message_text("❌ Доступ запрещён.")
            return
        await query.edit_message_text(
            "🏅 <b>Выдача ранга</b>\n\n"
            "Выберите ранг, который хотите назначить:\n\n"
            "После нажатия — введите <b>ID</b> или <b>@username</b> пользователя.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛡️ Администратор", callback_data="adm:rank_pick:admin")],
                [InlineKeyboardButton("⚔️ Модератор",     callback_data="adm:rank_pick:moderator")],
                [InlineKeyboardButton("👤 Снять ранг",    callback_data="adm:rank_pick:user")],
                [InlineKeyboardButton("🔙 Назад",         callback_data="back:adm")],
            ]),
        )
        return

    if section == "rank_pick":
        if not is_admin(user.id):
            await query.edit_message_text("❌ Доступ запрещён.")
            return
        chosen_rank = parts[2]
        context.user_data["state"] = f"adm_rank_input:{chosen_rank}"
        rank_names = {"admin": "🛡️ Администратор", "moderator": "⚔️ Модератор", "user": "👤 Пользователь"}
        await query.edit_message_text(
            f"🏅 Выдача ранга: <b>{rank_names.get(chosen_rank, chosen_rank)}</b>\n\n"
            "Введите <b>Telegram ID</b> или <b>@username</b> пользователя:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Отмена", callback_data="adm:rank_menu")
            ]]),
        )
        return


STATUS_ICON = {"pending": "🕐", "approved": "✅", "rejected": "❌"}
STATUS_LABEL = {"pending": "🕐 Ожидает", "approved": "✅ Одобрено", "rejected": "❌ Отклонено"}
MSG_STATUS_ICON = {"unread": "📩", "read": "📬", "replied": "💬"}


def _short(text: str, n: int = 35) -> str:
    return text[:n] + "…" if len(text) > n else text


async def _show_suggestions(query, page: int):
    items = db.get_suggestions()
    total = len(items)
    if not total:
        await query.edit_message_text(
            "📭 Предложений пока нет.",
            reply_markup=kb_back("adm"),
        )
        return
    start, end = page * PER_PAGE, (page + 1) * PER_PAGE
    keyboard = []
    for s in items[start:end]:
        icon = STATUS_ICON.get(s["status"], "🕐")
        keyboard.append([InlineKeyboardButton(
            f"{icon} #{s['id']} — {_short(s['text'])}",
            callback_data=f"adm:sugg_detail:{s['id']}",
        )])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"adm:suggs:{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"adm:suggs:{page + 1}"))
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back:adm")])
    pages = (total - 1) // PER_PAGE + 1
    await query.edit_message_text(
        f"📬 *Предложки* — стр. {page + 1}/{pages}  (всего: {total})",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def _show_suggestion_detail(query, sugg: dict, admin_id: int):
    u = db.get_user(sugg["user_id"])
    user_ref = f"@{u['username']}" if u and u["username"] else f"ID {sugg['user_id']}"
    text = (
        f"📬 *Предложение #{sugg['id']}*\n\n"
        f"👤 От: {user_ref}\n"
        f"📅 {sugg['created_at']}\n"
        f"📊 Статус: {STATUS_LABEL.get(sugg['status'], sugg['status'])}\n\n"
        f"💬 {sugg['text']}"
    )
    if sugg["admin_reply"]:
        text += f"\n\n📝 *Ответ администрации:*\n{sugg['admin_reply']}"
    keyboard = []
    if sugg["status"] == "pending":
        keyboard.append([
            InlineKeyboardButton("✅ Одобрить", callback_data=f"adm:sugg_approve:{sugg['id']}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"adm:sugg_reject:{sugg['id']}"),
        ])
    keyboard.append([InlineKeyboardButton("💬 Ответить", callback_data=f"adm:sugg_reply:{sugg['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 К списку", callback_data="adm:suggs:0")])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def _show_messages(query, page: int):
    items = db.get_admin_messages()
    total = len(items)
    if not total:
        await query.edit_message_text("📭 Сообщений пока нет.", reply_markup=kb_back("adm"))
        return
    start, end = page * PER_PAGE, (page + 1) * PER_PAGE
    keyboard = []
    for m in items[start:end]:
        icon = MSG_STATUS_ICON.get(m["status"], "📬")
        keyboard.append([InlineKeyboardButton(
            f"{icon} #{m['id']} — {_short(m['text'])}",
            callback_data=f"adm:msg_detail:{m['id']}",
        )])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"adm:msgs:{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"adm:msgs:{page + 1}"))
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back:adm")])
    pages = (total - 1) // PER_PAGE + 1
    await query.edit_message_text(
        f"💬 *Сообщения* — стр. {page + 1}/{pages}  (всего: {total})",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def _show_message_detail(query, msg: dict, admin_id: int):
    u = db.get_user(msg["user_id"])
    user_ref = f"@{u['username']}" if u and u["username"] else f"ID {msg['user_id']}"
    text = (
        f"💬 *Сообщение #{msg['id']}*\n\n"
        f"👤 От: {user_ref}\n"
        f"📅 {msg['created_at']}\n\n"
        f"📝 {msg['text']}"
    )
    if msg["admin_reply"]:
        text += f"\n\n✅ *Ответ отправлен:*\n{msg['admin_reply']}"
    keyboard = [
        [InlineKeyboardButton("💬 Ответить", callback_data=f"adm:msg_reply:{msg['id']}")],
        [InlineKeyboardButton("🔙 К списку", callback_data="adm:msgs:0")],
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


RANK_ICON = {"owner": "👑", "admin": "🛡️", "moderator": "⚔️", "user": "👤"}


async def _show_users(query, page: int):
    items = db.get_all_users()
    total = len(items)
    if not total:
        await query.edit_message_text("👥 Пользователей нет.", reply_markup=kb_back("adm"))
        return
    start, end = page * PER_PAGE, (page + 1) * PER_PAGE
    keyboard = []
    for u in items[start:end]:
        rank = effective_rank(u["user_id"])
        icon = RANK_ICON.get(rank, "👤")
        name = f"@{u['username']}" if u["username"] else u["full_name"] or f"ID {u['user_id']}"
        keyboard.append([InlineKeyboardButton(
            f"{icon} {name}",
            callback_data=f"adm:user_detail:{u['user_id']}",
        )])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"adm:users:{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"adm:users:{page + 1}"))
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back:adm")])
    pages = (total - 1) // PER_PAGE + 1
    await query.edit_message_text(
        f"👥 *Пользователи* — стр. {page + 1}/{pages}  (всего: {total})",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def _show_user_detail(query, context, target: dict, admin_id: int):
    t_rank   = effective_rank(target["user_id"])
    blocked  = bool(target.get("blocked", 0))
    name     = target["full_name"] or "—"
    uname    = f"@{target['username']}" if target["username"] else "—"
    block_label = "🚫 Заблокирован" if blocked else "✅ Активен"

    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"🆔 ID: <code>{target['user_id']}</code>\n"
        f"📛 Имя: {html.escape(str(name))}\n"
        f"🔗 Username: {uname}\n"
        f"🏅 Ранг: {rank_label(t_rank)}\n"
        f"🔒 Статус: {block_label}\n"
        f"📅 В боте с: {target.get('joined_at', '—')}"
    )

    keyboard = []
    if t_rank != "owner":
        row1 = []
        if t_rank != "admin":
            row1.append(InlineKeyboardButton(
                "🛡️ Выдать Админа", callback_data=f"adm:give_admin:{target['user_id']}"
            ))
        if t_rank != "moderator":
            row1.append(InlineKeyboardButton(
                "⚔️ Выдать Мода", callback_data=f"adm:give_mod:{target['user_id']}"
            ))
        if row1:
            keyboard.append(row1)
        if t_rank in ("admin", "moderator"):
            keyboard.append([InlineKeyboardButton(
                "👤 Снять ранг", callback_data=f"adm:remove_rank:{target['user_id']}"
            )])
        if blocked:
            keyboard.append([InlineKeyboardButton(
                "✅ Разблокировать", callback_data=f"adm:unblock:{target['user_id']}"
            )])
        else:
            keyboard.append([InlineKeyboardButton(
                "🚫 Заблокировать", callback_data=f"adm:block:{target['user_id']}"
            )])

    keyboard.append([InlineKeyboardButton("🔙 К списку", callback_data="adm:users:0")])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))




async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.username or "", user.full_name)
    text  = update.message.text
    state = context.user_data.get("state")


    if state == "typing_suggestion":
        if db.is_blocked(user.id):
            await update.message.reply_text("❌ Вы заблокированы и не можете отправлять предложения.")
            return
        context.user_data.pop("state", None)
        sugg_id = db.add_suggestion(user.id, text)
        await update.message.reply_text(
            f"✅ Предложение <b>#{sugg_id}</b> отправлено!\n"
            "Администрация рассмотрит его в ближайшее время.",
            parse_mode="HTML",
            reply_markup=kb_main(),
        )
        uref = f"@{html.escape(user.username)}" if user.username else html.escape(user.full_name)
        kb_notify = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Принять",     callback_data=f"adm:sugg_approve:{sugg_id}"),
                InlineKeyboardButton("❌ Отклонить",   callback_data=f"adm:sugg_reject:{sugg_id}"),
                InlineKeyboardButton("🚫 Заблокировать", callback_data=f"adm:block:{user.id}"),
            ],
            [InlineKeyboardButton("🔍 Подробнее", callback_data=f"adm:sugg_detail:{sugg_id}")],
        ])
        await notify_staff(
            context,
            f"📬 <b>Новое предложение #{sugg_id}</b>\n\n"
            f"👤 От: {uref} (<code>{user.id}</code>)\n\n"
            f"{html.escape(text)}",
            reply_markup=kb_notify,
        )
        return

    if state == "typing_contact":
        if db.is_blocked(user.id):
            await update.message.reply_text("❌ Вы заблокированы и не можете отправлять сообщения.")
            return
        context.user_data.pop("state", None)
        msg_id = db.add_admin_message(user.id, text)
        await update.message.reply_text(
            f"✅ Сообщение <b>#{msg_id}</b> отправлено!\n"
            "Администратор ответит вам как можно скорее.",
            parse_mode="HTML",
            reply_markup=kb_main(),
        )
        uref = f"@{html.escape(user.username)}" if user.username else html.escape(user.full_name)
        kb_notify = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("💬 Ответить",      callback_data=f"adm:msg_reply:{msg_id}"),
                InlineKeyboardButton("🚫 Заблокировать", callback_data=f"adm:block:{user.id}"),
            ],
            [InlineKeyboardButton("🔍 Подробнее", callback_data=f"adm:msg_detail:{msg_id}")],
        ])
        await notify_staff(
            context,
            f"💬 <b>Новое сообщение #{msg_id}</b>\n\n"
            f"👤 От: {uref} (<code>{user.id}</code>)\n\n"
            f"{html.escape(text)}",
            reply_markup=kb_notify,
        )
        return


    if state and state.startswith("adm_reply_sugg:"):
        if not is_staff(user.id):
            context.user_data.pop("state", None)
            return
        sugg_id = int(state.split(":")[1])
        context.user_data.pop("state", None)
        sugg = db.get_suggestion(sugg_id)
        if sugg:
            db.update_suggestion(sugg_id, reply=text)
            await safe_send(
                context, sugg["user_id"],
                f"📬 <b>Ответ на ваше предложение #{sugg_id}</b>\n\n{html.escape(text)}",
            )
        await update.message.reply_text(
            "✅ Ответ отправлен!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📬 К предложкам", callback_data="adm:suggs:0"),
                InlineKeyboardButton("🏠 Панель",       callback_data="back:adm"),
            ]]),
        )
        return


    if state and state.startswith("adm_reply_msg:"):
        if not is_staff(user.id):
            context.user_data.pop("state", None)
            return
        msg_id = int(state.split(":")[1])
        context.user_data.pop("state", None)
        msg = db.get_admin_message(msg_id)
        if msg:
            db.update_message_reply(msg_id, text)
            await safe_send(
                context, msg["user_id"],
                f"💬 <b>Ответ администратора на ваше сообщение #{msg_id}</b>\n\n{html.escape(text)}",
            )
        await update.message.reply_text(
            "✅ Ответ отправлен!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💬 К сообщениям", callback_data="adm:msgs:0"),
                InlineKeyboardButton("🏠 Панель",       callback_data="back:adm"),
            ]]),
        )
        return


    if state and state.startswith("adm_rank_input:"):
        if not is_admin(user.id):
            context.user_data.pop("state", None)
            return
        new_rank = state.split(":")[1]
        context.user_data.pop("state", None)


        target = None
        inp = text.strip().lstrip("@")
        if inp.isdigit():
            target = db.get_user(int(inp))
        else:
            # Поиск по username
            all_users = db.get_all_users()
            for u2 in all_users:
                if u2.get("username", "").lower() == inp.lower():
                    target = u2
                    break

        rank_names = {"admin": "🛡️ Администратор", "moderator": "⚔️ Модератор", "user": "👤 Пользователь"}

        if not target:
            await update.message.reply_text(
                "❌ Пользователь не найден в базе.\n"
                "Он должен хотя бы раз написать боту /start.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Попробовать снова", callback_data="adm:rank_menu"),
                    InlineKeyboardButton("🏠 Панель", callback_data="back:adm"),
                ]]),
            )
            return

        target_rank = effective_rank(target["user_id"])
        if target_rank == "owner":
            await update.message.reply_text(
                "❌ Нельзя изменить ранг Владельца!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 К панели", callback_data="back:adm")
                ]]),
            )
            return

        db.set_user_rank(target["user_id"], new_rank)
        notify_texts = {
            "admin":     "🛡️ Вам выдан ранг <b>Администратор</b>!",
            "moderator": "⚔️ Вам выдан ранг <b>Модератор</b>!",
            "user":      "👤 Ваш ранг был сброшен до <b>Пользователя</b>.",
        }
        await safe_send(context, target["user_id"], notify_texts.get(new_rank, ""))

        name = f"@{target['username']}" if target.get("username") else target.get("full_name") or str(target["user_id"])
        await update.message.reply_text(
            f"✅ Пользователю <b>{html.escape(name)}</b> выдан ранг <b>{rank_names.get(new_rank)}</b>!",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏅 Выдать ещё", callback_data="adm:rank_menu"),
                InlineKeyboardButton("🏠 Панель",     callback_data="back:adm"),
            ]]),
        )
        return


    await update.message.reply_text(
        "Выберите раздел:",
        reply_markup=kb_main(),
    )



def main():
    import asyncio
    asyncio.set_event_loop(asyncio.new_event_loop())

    init_db()
    logger.info("Database initialised.")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("admpanel", cmd_admpanel))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    logger.info("Bot is running…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
