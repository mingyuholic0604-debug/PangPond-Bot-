import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button

import psycopg2
from psycopg2.pool import SimpleConnectionPool

import os
import random
import asyncio
import time


# -------------------------------
# ENV VARIABLES
# -------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")

# 🔹 Default emojis (fallbacks)
BALL = os.getenv("BALL_EMOJI") or "⚽"
BOBA = os.getenv("BOBA_EMOJI") or "🧋"
BUTTON = os.getenv("BUTTON_EMOJI") or "🔘"
CAKE = os.getenv("CAKE_EMOJI") or "🍰"
CHOCOLATE = os.getenv("CHOCOLATE_EMOJI") or "🍫"
CROISSANT = os.getenv("CROISSANT_EMOJI") or "🥐"
ICE = os.getenv("ICE_EMOJI") or "❄️"
PANCAKE = os.getenv("PANCAKE_EMOJI") or "🥞"
PANG = os.getenv("PANG_EMOJI") or "🍞"
PUDDING = os.getenv("PUDDING_EMOJI") or "🍮"
SPIRAL = os.getenv("SPIRAL_EMOJI") or "🌀"
STAR = os.getenv("STAR_EMOJI") or "⭐"
TEA = os.getenv("TEA_EMOJI") or "🍵"

LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0"))

# -------------------------------
# BUTTON EMOJIS (FIXED)
# -------------------------------

def get_emoji(env_name, default):
    val = os.getenv(env_name)

    # ✅ If not set → fallback
    if not val:
        return default

    try:
        # ✅ Try custom emoji
        return discord.PartialEmoji.from_str(val)
    except Exception:
        # ✅ Fallback if invalid
        return default

LEFT = get_emoji("LEFT_EMOJI", "⬅️")
RIGHT = get_emoji("RIGHT_EMOJI", "➡️")

# -------------------------------
# DATABASE POOL
# -------------------------------
db_pool = SimpleConnectionPool(
    1, 10,
    DATABASE_URL,
    sslmode="require"
)

# -------------------------------
# SAFE QUERY FUNCTION (FIXED)
# -------------------------------
def run_query(query, params=(), fetchone=False, fetchall=False):
    conn = None
    result = None

    try:
        conn = db_pool.getconn()

        with conn.cursor() as cur:
            cur.execute(query, params)

            # 🔹 Fetch BEFORE commit (important for some DBs)
            if fetchone:
                result = cur.fetchone()
            elif fetchall:
                result = cur.fetchall()

        conn.commit()
        return result

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[DB ERROR1] {e}\nQuery: {query}\nParams: {params}")
        return None

    finally:
        if conn:
            db_pool.putconn(conn)

# -------------------------------
# COOLDOWN HELPERS
# -------------------------------
def get_cooldown(user_id: str, command: str):
    res = run_query(
        "SELECT last_used FROM cooldowns WHERE user_id=%s AND command=%s",
        (user_id, command),
        fetchone=True
    )

    # 🔹 Safe fallback
    if not res or res[0] is None:
        return 0

    return int(res[0])


def set_cooldown(user_id: str, command: str, now: int):
    run_query("""
        INSERT INTO cooldowns (user_id, command, last_used)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, command)
        DO UPDATE SET last_used = EXCLUDED.last_used
    """, (user_id, command, now))

# -------------------------------
# Ensure user exists
# -------------------------------
def ensure_user(user_id: str):
    run_query(
        "INSERT INTO users (user_id, boba, cakecoins) VALUES (%s, 0, 0) ON CONFLICT (user_id) DO NOTHING",
        (user_id,)
    )

async def log_action(user_id: str, action: str, details: str):

    timestamp = int(time.time())

    # 🔹 Save to DB
    run_query(
        "INSERT INTO logs (user_id, action, details, timestamp) VALUES (%s,%s,%s,%s)",
        (user_id, action, details, timestamp)
    )

    # 🎨 Action styles
    styles = {
        "drop": ("🎲 DROP", discord.Color.orange()),
        "daily": ("💰 DAILY", discord.Color.green()),
        "weekly": ("📅 WEEKLY", discord.Color.gold()),
        "bake": ("🥐 BAKE", discord.Color.pink()),
        "pay": ("💸 PAY", discord.Color.green()),
        "giftcard": ("🎁 GIFT", discord.Color.green()),
        "manage": ("🛠 ADMIN", discord.Color.red()),
        "addcard": ("➕ ADD CARD", discord.Color.blurple()),
        "event_start": ("🎉 EVENT START", discord.Color.purple()),
        "event_end": ("🛑 EVENT END", discord.Color.dark_red())
    }

    title, color = styles.get(
        action,
        (f"📜 {action.upper()}", discord.Color.dark_blue())
    )

    # 🔹 Send to Discord
    try:
        if LOG_CHANNEL_ID:
            channel = bot.get_channel(LOG_CHANNEL_ID)

            if isinstance(channel, discord.TextChannel):
                embed = discord.Embed(
                    title=title,
                    description=details,
                    color=color
                )

                embed.add_field(
                    name="👤 User",
                    value=f"<@{user_id}> (`{user_id}`)"
                )

                embed.set_footer(text=f"<t:{timestamp}:F>")

                await channel.send(embed=embed)

    except Exception as e:
        print(f"[LOG ERROR] {e}")

    
# -------------------------------
# OPTIONAL: helper to calculate remaining time
# -------------------------------
def get_remaining_cooldown(user_id: str, command: str, cooldown_time: int):
    last = get_cooldown(user_id, command)
    now = int(time.time())

    remaining = cooldown_time - (now - last)
    return max(0, remaining)


# -------------------------------
# BOT SETUP
# -------------------------------


intents = discord.Intents.default()

# 🔹 Only needed if you use prefix commands
intents.message_content = True  

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

import os
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    t = Thread(target=run)
    t.start()

# 🔐 Safe TOKEN handling
TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError("❌ TOKEN is missing from environment variables!")

# 🚀 Start everything
keep_alive()
bot.run(TOKEN)


# -------------------------------
# Database setup (RUN ON START)
# -------------------------------

def setup_database():
    conn = db_pool.getconn()

    try:
        with conn.cursor() as cur:

            # 🔹 Users
            cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                boba INT DEFAULT 0,
                cakecoins INT DEFAULT 0
            )
            """)

            # 🔧 Fix missing columns
            cur.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS boba INT DEFAULT 0;
            """)

            cur.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS cakecoins INT DEFAULT 0;
            """)

            # 🔹 Inventory
            cur.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                user_id TEXT,
                card_id TEXT,
                name TEXT,
                era TEXT,
                group_name TEXT,
                rarity INT
            )
            """)

            # 🔹 Cooldowns
            cur.execute("""
            CREATE TABLE IF NOT EXISTS cooldowns (
                user_id TEXT,
                command TEXT,
                last_used BIGINT,
                PRIMARY KEY (user_id, command)
            )
            """)

            # 🔹 Profiles
            cur.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                user_id TEXT PRIMARY KEY,
                about TEXT DEFAULT '',
                fav_card_id TEXT
            )
            """)

            # 🔹 Reminders
            cur.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                user_id TEXT,
                command TEXT,
                end_time BIGINT,
                channel_id TEXT,
                PRIMARY KEY (user_id, command)
            )
            """)

            # 🔹 Reminder Settings
            cur.execute("""
            CREATE TABLE IF NOT EXISTS reminder_settings (
                user_id TEXT,
                command TEXT,
                enabled BOOLEAN,
                PRIMARY KEY (user_id, command)
            )
            """)

            # 🔹 Cards table (NEW SYSTEM)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS cards (
                card_id TEXT PRIMARY KEY,
                name TEXT,
                era TEXT,
                group_name TEXT,
                rarity INT,
                image TEXT,
                category TEXT,
                event_name TEXT
            )
            """)

            # 🔹 Logs
            cur.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id SERIAL PRIMARY KEY,
                user_id TEXT,
                command TEXT,
                details TEXT,
                guild_id TEXT,
                timestamp BIGINT
            )
            """)

        conn.commit()

    except Exception as e:
        conn.rollback()
        print(f"[DB SETUP ERROR] {e}")

    finally:
        db_pool.putconn(conn)


# -------------------------------
# /balance
# -------------------------------
@bot.tree.command(
    name="balance",
    description="Check your balance and total cards"
)
async def balance(interaction: discord.Interaction):

    user_id = str(interaction.user.id)

    try:
        # 🔹 Ensure user exists (use helper ✅)
        ensure_user(user_id)

        # 🔹 Get balance
        data = run_query(
            "SELECT boba, cakecoins FROM users WHERE user_id = %s",
            (user_id,),
            fetchone=True
        )

        boba, cakecoins = data if data else (0, 0)

        # 🔹 Get card count
        count_res = run_query(
            "SELECT COUNT(*) FROM inventory WHERE user_id = %s",
            (user_id,),
            fetchone=True
        )

        card_count = count_res[0] if count_res else 0

        # 🎨 Embed
        embed = discord.Embed(
            title=f"{ICE} Your Balance",
            description=(
                f"{BOBA} Boba: **{boba}**\n"
                f"{CAKE} Cakecoins: **{cakecoins}**\n"
                f"{CROISSANT} Cards: **{card_count}**"
            ),
            color=discord.Color.orange()
        )

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        if interaction.response.is_done():
            await interaction.followup.send(
                f"❌ Error: {e}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )
            
# -------------------------------
# /drop
# -------------------------------
DROP_COOLDOWN = 300  

@bot.tree.command(
    name="drop",
    description="Get a random card"
)
@app_commands.describe(reminder="Turn reminder on/off (optional)")
async def drop_cmd(
    interaction: discord.Interaction,
    reminder: bool | None = None
):

    user_id = str(interaction.user.id)
    now = int(time.time())

    try:
        # 🔹 Ensure user exists
        ensure_user(user_id)

        # 🔹 Cooldown check
        remaining = get_remaining_cooldown(user_id, "drop", DROP_COOLDOWN)

        if remaining > 0:
            minutes = remaining // 60
            seconds = remaining % 60

            return await interaction.response.send_message(
                f"⏱ You can drop again in {minutes}m {seconds}s",
                ephemeral=True
            )
        
# -------------------------------
# 🎴 GET RANDOM CARD FROM DB
# -------------------------------
        all_cards = run_query(
            "SELECT card_id, name, era, group_name, rarity, image FROM cards",
            fetchall=True
        )

        if not all_cards:
            return await interaction.response.send_message(
                "❌ No cards available. Ask a mod to add cards.",
                ephemeral=True
            )

        # 🔹 Weighted rarity system
        weighted_cards = []
        for c in all_cards:
            rarity = int(c[4]) if c[4] else 1

            # More rare = less chance
            weight = max(1, 6 - rarity)
            weighted_cards.extend([c] * weight)

        card = random.choice(weighted_cards)

        card_id, name, era, group, rarity, image = card

# -------------------------------
# 📦 ADD TO INVENTORY
# -------------------------------
        run_query(
            """INSERT INTO inventory 
            (user_id, card_id, name, era, group_name, rarity)
            VALUES (%s,%s,%s,%s,%s,%s)""",
            (user_id, card_id, name, era, group, rarity)
        )

        # 🔢 Count copies
        copies_res = run_query(
            "SELECT COUNT(*) FROM inventory WHERE user_id=%s AND card_id=%s",
            (user_id, card_id),
            fetchone=True
        )
        copies = copies_res[0] if copies_res else 1

        # 🔹 Set cooldown
        set_cooldown(user_id, "drop", now)
        await log_action(
    user_id,
    "drop",
    f"Got {card[1]} ({card[0]})"
)


# -------------------------------
# 🔔 REMINDER SYSTEM
# -------------------------------
        if reminder is not None:
            run_query("""
                INSERT INTO reminder_settings (user_id, command, enabled)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, command)
                DO UPDATE SET enabled = %s
            """, (user_id, "drop", reminder, reminder))

        res = run_query(
            "SELECT enabled FROM reminder_settings WHERE user_id=%s AND command=%s",
            (user_id, "drop"),
            fetchone=True
        )
        enabled = res[0] if res else True

        if enabled:
            run_query("""
                INSERT INTO reminders (user_id, command, end_time, channel_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, command)
                DO UPDATE SET end_time = %s, channel_id = %s
            """, (
                user_id,
                "drop",
                now + DROP_COOLDOWN,
                str(interaction.channel_id),
                now + DROP_COOLDOWN,
                str(interaction.channel_id)
            ))

# -------------------------------
# 🎨 DISPLAY
# -------------------------------
        rarity_display = PANG * int(rarity)

        embed = discord.Embed(
            title=f"{PANCAKE} You got a card!",
            description=(
                f"**{name}** (ID: {card_id})\n"
                f"{SPIRAL} {era} | {STAR} {group}\n"
                f"{rarity_display}"
            ),
            color=discord.Color.orange()
        )

        if image:
            embed.set_image(url=image)

        embed.set_footer(text=f"You have {copies} copies of this card.")

        await interaction.response.send_message(embed=embed)

# -------------------------------
# 📜 LOGGING (NEW FEATURE 🔥)
# -------------------------------
        run_query(
            "INSERT INTO logs (user_id, action, details) VALUES (%s,%s,%s)",
            (user_id, "drop", f"{name} ({card_id})")
        )

    except Exception as e:
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )

# -------------------------------
# /inventory (PAGED)
# -------------------------------
@bot.tree.command(
    name="inventory",
    description="View your or another user's inventory"
)
@app_commands.describe(
    user="View another user's inventory (optional)",
    filter_type="Filter by id, name, era, group, or rarity",
    filter_value="Value for the filter"
)
async def inventory_cmd(
    interaction: discord.Interaction,
    user: discord.Member | None = None,
    filter_type: str | None = None,
    filter_value: str | None = None
):

    target = user if user else interaction.user
    user_id = str(target.id)

    try:
        # 🔹 Ensure user exists
        ensure_user(user_id)

        # 🔹 Fetch inventory (GROUPED COPIES ✅)
        data = run_query("""
            SELECT card_id, name, era, group_name, rarity, COUNT(*) as copies
            FROM inventory
            WHERE user_id = %s
            GROUP BY card_id, name, era, group_name, rarity
            ORDER BY name
        """, (user_id,), fetchall=True)

        if not data:
            return await interaction.response.send_message(
                f"❌ {target.name}'s inventory is empty!",
                ephemeral=True
            )

# -------------------------------
# 🔍 FILTER SYSTEM (FIXED)
# -------------------------------
        if filter_type and filter_value:
            ft = str(filter_type).lower()
            fv = str(filter_value).lower()

            if ft == "id":
                data = [c for c in data if str(c[0]).lower() == fv]

            elif ft == "name":
                data = [c for c in data if fv in str(c[1]).lower()]

            elif ft == "era":
                data = [c for c in data if str(c[2]).lower() == fv]

            elif ft == "group":
                data = [c for c in data if str(c[3]).lower() == fv]

            elif ft == "rarity":
                try:
                    rarity_num = int(fv)
                    data = [c for c in data if int(c[4]) == rarity_num]
                except:
                    data = []

        if not data:
            return await interaction.response.send_message(
                "❌ No cards match this filter.",
                ephemeral=True
            )

# -------------------------------
# 📄 PAGINATION
# -------------------------------
        per_page = 5
        total_pages = (len(data) - 1) // per_page + 1

        def get_embed(page):
            embed = discord.Embed(
                title=f"{TEA} {target.name}'s Inventory (Page {page+1}/{total_pages})",
                color=discord.Color.orange()
            )

            start = page * per_page
            end = start + per_page

            for card_id, name, era, group_name, rarity, copies in data[start:end]:
                rarity_display = PANG * int(rarity)

                embed.add_field(
                    name=f"{name} (ID: {card_id})",
                    value=(
                        f"{SPIRAL} {era} | {STAR} {group_name}\n"
                        f"{rarity_display} | Copies: {copies}"
                    ),
                    inline=False
                )

            return embed

# -------------------------------
# 🔘 PAGINATION VIEW
# -------------------------------
        class InventoryView(View):
            def __init__(self):
                super().__init__(timeout=120)
                self.page = 0

            @discord.ui.button(emoji=LEFT, style=discord.ButtonStyle.gray)
            async def prev(self, interaction2: discord.Interaction, button: Button):
                if self.page > 0:
                    self.page -= 1
                    await interaction2.response.edit_message(
                        embed=get_embed(self.page),
                        view=self
                    )

            @discord.ui.button(emoji=RIGHT, style=discord.ButtonStyle.gray)
            async def next(self, interaction2: discord.Interaction, button: Button):
                if self.page < total_pages - 1:
                    self.page += 1
                    await interaction2.response.edit_message(
                        embed=get_embed(self.page),
                        view=self
                    )

        await interaction.response.send_message(
            embed=get_embed(0),
            view=InventoryView()
        )

    except Exception as e:
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )
    
# -------------------------------
# /daily
# -------------------------------
DAILY_COOLDOWN = 86400  # 24 hours

@bot.tree.command(
    name="daily",
    description="Claim your daily rewards"
)
@app_commands.describe(reminder="Turn reminder on/off (optional)")
async def daily_cmd(
    interaction: discord.Interaction,
    reminder: bool | None = None
):

    user_id = str(interaction.user.id)
    now = int(time.time())

    try:
        # 🔹 Ensure user exists
        ensure_user(user_id)

        # 🔹 Cooldown check
        remaining = get_remaining_cooldown(user_id, "daily", DAILY_COOLDOWN)

        if remaining > 0:
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60

            return await interaction.response.send_message(
                f"⏱ You can claim daily again in {hours}h {minutes}m",
                ephemeral=True
            )

        # 🎁 Rewards
        boba = 2000
        cakecoins = 10

        # 🔹 Update balance (SAFE ✅)
        run_query("""
            INSERT INTO users (user_id, boba, cakecoins)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET
                boba = users.boba + %s,
                cakecoins = users.cakecoins + %s
        """, (user_id, boba, cakecoins, boba, cakecoins))
        await log_action(
    user_id,
    "daily",
    f"+{boba} boba, +{cakecoins} cakecoins"
    )
        # 🔹 Save cooldown
        set_cooldown(user_id, "daily", now)

# -------------------------------
# 🔔 REMINDER SYSTEM
# -------------------------------
        if reminder is not None:
            run_query("""
                INSERT INTO reminder_settings (user_id, command, enabled)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, command)
                DO UPDATE SET enabled = %s
            """, (user_id, "daily", reminder, reminder))

        res = run_query(
            "SELECT enabled FROM reminder_settings WHERE user_id=%s AND command=%s",
            (user_id, "daily"),
            fetchone=True
        )
        enabled = res[0] if res else True

        if enabled:
            run_query("""
                INSERT INTO reminders (user_id, command, end_time, channel_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, command)
                DO UPDATE SET end_time = %s, channel_id = %s
            """, (
                user_id,
                "daily",
                now + DAILY_COOLDOWN,
                str(interaction.channel_id),
                now + DAILY_COOLDOWN,
                str(interaction.channel_id)
            ))

# -------------------------------
# 🎨 EMBED
# -------------------------------
        embed = discord.Embed(
            title=f"{BUTTON} Daily Reward Claimed!",
            description=(
                f"You received:\n"
                f"{BOBA} **{boba} boba**\n"
                f"{CAKE} **{cakecoins} cakecoins**"
            ),
            color=discord.Color.green()
        )

        embed.set_image(
            url="https://media2.giphy.com/media/v1.Y2lkPTZjMDliOTUydmlrODh6YXlxcWI4dGhhbXl3czZpejVmZzVnOXEydDN2dmswdmM5aSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/uKKSAhC0gb5roHsy9v/giphy.gif"
        )

        await interaction.response.send_message(embed=embed)

# -------------------------------
# 📜 LOGGING (NEW 🔥)
# -------------------------------
        run_query(
            "INSERT INTO logs (user_id, action, details) VALUES (%s,%s,%s)",
            (user_id, "daily", f"+{boba} boba, +{cakecoins} cakecoins")
        )

    except Exception as e:
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )
        

# -------------------------------
# /weekly
# -------------------------------
WEEKLY_COOLDOWN = 604800  # 7 days

@bot.tree.command(
    name="weekly",
    description="Claim your weekly rewards"
)
@app_commands.describe(reminder="Turn reminder on/off (optional)")
async def weekly_cmd(
    interaction: discord.Interaction,
    reminder: bool | None = None
):

    user_id = str(interaction.user.id)
    now = int(time.time())

    try:
        # 🔹 Ensure user exists
        ensure_user(user_id)

        # 🔹 Cooldown check
        remaining = get_remaining_cooldown(user_id, "weekly", WEEKLY_COOLDOWN)

        if remaining > 0:
            days = remaining // 86400
            hours = (remaining % 86400) // 3600

            return await interaction.response.send_message(
                f"⏱ You can claim weekly again in {days}d {hours}h",
                ephemeral=True
            )

        # 🎁 Rewards
        boba = 5000
        cakecoins = 50

        # 🔹 Update balance (FIXED ✅)
        run_query("""
            INSERT INTO users (user_id, boba, cakecoins)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET
                boba = users.boba + %s,
                cakecoins = users.cakecoins + %s
        """, (user_id, boba, cakecoins, boba, cakecoins))

        # 🔹 Save cooldown
        set_cooldown(user_id, "weekly", now)

# -------------------------------
# 🔔 REMINDER SYSTEM
# -------------------------------
        if reminder is not None:
            run_query("""
                INSERT INTO reminder_settings (user_id, command, enabled)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, command)
                DO UPDATE SET enabled = %s
            """, (user_id, "weekly", reminder, reminder))

        res = run_query(
            "SELECT enabled FROM reminder_settings WHERE user_id=%s AND command=%s",
            (user_id, "weekly"),
            fetchone=True
        )
        enabled = res[0] if res else True

        if enabled:
            run_query("""
                INSERT INTO reminders (user_id, command, end_time, channel_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, command)
                DO UPDATE SET end_time = %s, channel_id = %s
            """, (
                user_id,
                "weekly",
                now + WEEKLY_COOLDOWN,
                str(interaction.channel_id),
                now + WEEKLY_COOLDOWN,
                str(interaction.channel_id)
            ))
        await log_action(
    user_id,
    "weekly",
    f"+{boba} boba, +{cakecoins} cakecoins"
)

        # -------------------------------
        # 🎨 EMBED
        # -------------------------------
        embed = discord.Embed(
            title=f"{BUTTON} Weekly Reward Claimed!",
            description=(
                f"You received:\n"
                f"{BOBA} **{boba} boba**\n"
                f"{CAKE} **{cakecoins} cakecoins**"
            ),
            color=discord.Color.gold()
        )

        embed.set_image(
            url="https://media0.giphy.com/media/v1.Y2lkPTZjMDliOTUyY2xhcHA5cDM1aWhkcGl5MDR1MzY1bmZuNGF6aXMxeWl0dTM0ODNjMyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/5wKuwXycuNfl0VEOgI/giphy.gif"
        )

        await interaction.response.send_message(embed=embed)

# -------------------------------
# 📜 LOGGING (NEW 🔥)
# -------------------------------
        run_query(
            "INSERT INTO logs (user_id, action, details) VALUES (%s,%s,%s)",
            (user_id, "weekly", f"+{boba} boba, +{cakecoins} cakecoins")
        )

    except Exception as e:
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )
        
# -------------------------------
# /bake
# -------------------------------
BAKE_COOLDOWN = 3600  # 1 hour
        
@bot.tree.command(
    name="bake",
    description="Bake to earn boba and cakecoins"
)
@app_commands.describe(reminder="Turn reminder on/off (optional)")
async def bake_cmd(
    interaction: discord.Interaction,
    reminder: bool | None = None
):

    user_id = str(interaction.user.id)
    now = int(time.time())

    try:
        # 🔹 Ensure user exists
        ensure_user(user_id)

        # 🔹 Cooldown check
        remaining = get_remaining_cooldown(user_id, "bake", BAKE_COOLDOWN)

        if remaining > 0:
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60

            return await interaction.response.send_message(
                f"⏱ You can bake again in {hours}h {minutes}m",
                ephemeral=True
            )

        # 🎁 Rewards (random)
        boba = random.randint(200, 800)
        cakecoins = random.randint(1, 5)

        # 🔹 Update balance (FIXED ✅)
        run_query("""
            INSERT INTO users (user_id, boba, cakecoins)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET
                boba = users.boba + %s,
                cakecoins = users.cakecoins + %s
        """, (user_id, boba, cakecoins, boba, cakecoins))

        # 🔹 Save cooldown
        set_cooldown(user_id, "bake", now)

        # -------------------------------
        # 🔔 REMINDER SYSTEM
        # -------------------------------
        if reminder is not None:
            run_query("""
                INSERT INTO reminder_settings (user_id, command, enabled)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, command)
                DO UPDATE SET enabled = %s
            """, (user_id, "bake", reminder, reminder))

        res = run_query(
            "SELECT enabled FROM reminder_settings WHERE user_id=%s AND command=%s",
            (user_id, "bake"),
            fetchone=True
        )
        enabled = res[0] if res else True

        if enabled:
            run_query("""
                INSERT INTO reminders (user_id, command, end_time, channel_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, command)
                DO UPDATE SET end_time = %s, channel_id = %s
            """, (
                user_id,
                "bake",
                now + BAKE_COOLDOWN,
                str(interaction.channel_id),
                now + BAKE_COOLDOWN,
                str(interaction.channel_id)
            ))

        # -------------------------------
        # 🎨 EMBED
        # -------------------------------
        embed = discord.Embed(
            title=f"{CROISSANT} Baking Complete!",
            description=(
                f"You earned:\n"
                f"{BOBA} **{boba} boba**\n"
                f"{CAKE} **{cakecoins} cakecoins**"
            ),
            color=discord.Color.pink()
        )

        embed.set_image(
            url="https://media4.giphy.com/media/v1.Y2lkPTZjMDliOTUyZGZnMDcwM2o3Zmp6Y2tndHFweHZydTZtMmU1MzE2bHBrc201cjJlZiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/LMuPuB2jQkmgX59vWX/giphy.gif"
        )

        await interaction.response.send_message(embed=embed)

# -------------------------------
# 📜 LOGGING (NEW 🔥)
# -------------------------------
        run_query(
            "INSERT INTO logs (user_id, action, details) VALUES (%s,%s,%s)",
            (user_id, "bake", f"+{boba} boba, +{cakecoins} cakecoins")
        )
        await log_action(
    user_id,
    "bake",
    f"+{boba} boba, +{cakecoins} cakecoins"
)

    except Exception as e:
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )
        
# -------------------------------
# /cooldown
# -------------------------------
@bot.tree.command(
    name="cooldown",
    description="Check your command cooldowns"
)
async def cooldown_cmd(interaction: discord.Interaction):

    user_id = str(interaction.user.id)
    now = int(time.time())

    commands_list = {
        "drop": 300,
        "bake": 3600,
        "daily": 86400,
        "weekly": 604800
    }

    # 🔥 Emojis per command
    cmd_emojis = {
        "drop": PANCAKE,
        "bake": CROISSANT,
        "daily": BUTTON,
        "weekly": STAR
    }

    try:
        # 🔹 Ensure user exists
        ensure_user(user_id)

        embed = discord.Embed(
            title=f"{TEA} Your Cooldowns",
            color=discord.Color.blue()
        )

        for cmd, cd_time in commands_list.items():

            # 🔹 Use unified cooldown system ✅
            remaining = get_remaining_cooldown(user_id, cmd, cd_time)

            if remaining <= 0:
                value = "✅ Ready"
            else:
                days = remaining // 86400
                hours = (remaining % 86400) // 3600
                minutes = (remaining % 3600) // 60

                if days > 0:
                    value = f"{days}d {hours}h"
                elif hours > 0:
                    value = f"{hours}h {minutes}m"
                else:
                    value = f"{minutes}m"

            emoji = cmd_emojis.get(cmd, "")

            embed.add_field(
                name=f"{emoji} /{cmd}",
                value=value,
                inline=False
            )

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )
                    

# -------------------------------
# /manage (ADMIN ONLY)
# -------------------------------
@bot.tree.command(
    name="manage",
    description="Admin command to modify user data"
)
@app_commands.describe(
    user="The user to modify",
    action="Add or Remove",
    type="What to modify",
    amount="Amount (for currency)",
    card_id="Card ID (for cards)",
    quantity="Number of copies (for cards)"
)
@app_commands.choices(
    action=[
        app_commands.Choice(name="Add", value="add"),
        app_commands.Choice(name="Remove", value="remove")
    ],
    type=[
        app_commands.Choice(name="Boba", value="boba"),
        app_commands.Choice(name="Cakecoins", value="cakecoins"),
        app_commands.Choice(name="Card", value="card")
    ]
)
async def manage_cmd(
    interaction: discord.Interaction,
    user: discord.User,
    action: app_commands.Choice[str],
    type: app_commands.Choice[str],
    amount: int | None = None,
    card_id: str | None = None,
    quantity: int | None = None
):

    # 🔒 SERVER LOCK (VERY IMPORTANT 🔥)
    MAIN_GUILD_ID = 1475099422315647006  # ⬅️ PUT YOUR SERVER ID HERE

    if interaction.guild_id != MAIN_GUILD_ID:
        return await interaction.response.send_message(
            "❌ Only staff for PangPond can use this command.",
            ephemeral=True
        )

    # 🔒 ROLE CHECK
    if not isinstance(interaction.user, discord.Member):
        return await interaction.response.send_message(
            "❌ Could not verify roles.",
            ephemeral=True
        )

    if not interaction.user.guild_permissions.manage_guild:
     await interaction.response.send_message(
        "❌ You are not authorized.",
        ephemeral=True
    )
    return

    target_id = str(user.id)
    action_value = action.value
    type_value = type.value

    try:
        # 🔹 Ensure target exists
        ensure_user(target_id)

# -------------------------------
# 💰 CURRENCY
# -------------------------------
        if type_value in ["boba", "cakecoins"]:

            if amount is None or amount <= 0:
                return await interaction.response.send_message(
                    "❌ Invalid amount.",
                    ephemeral=True
                )

            if action_value == "add":
                run_query(
                    f"UPDATE users SET {type_value} = {type_value} + %s WHERE user_id=%s",
                    (amount, target_id)
                )
            else:
                run_query(
                    f"UPDATE users SET {type_value} = GREATEST({type_value} - %s, 0) WHERE user_id=%s",
                    (amount, target_id)
                )

            await interaction.response.send_message(
                f"✅ {action_value.title()}ed {amount} {type_value} for {user.mention}"
            )

            # 📜 LOG
            run_query(
                "INSERT INTO logs (user_id, action, details) VALUES (%s,%s,%s)",
                (target_id, "manage_currency", f"{action_value} {amount} {type_value}")
            )

# -------------------------------
# 🃏 CARDS (DB BASED ✅)
# -------------------------------
        elif type_value == "card":

            if not card_id or not quantity or quantity <= 0:
                return await interaction.response.send_message(
                    "❌ Provide valid card_id and quantity.",
                    ephemeral=True
                )

            # 🔹 Get card from DB (NOT list ❌)
            card_data = run_query(
                "SELECT id, name, era, group_name, rarity FROM cards WHERE id=%s",
                (card_id,),
                fetchone=True
            )

            if not card_data:
                return await interaction.response.send_message(
                    "❌ Card not found.",
                    ephemeral=True
                )

            card_id_db, name, era, group_name, rarity = card_data

            if action_value == "add":

                for _ in range(quantity):
                    run_query(
                        "INSERT INTO inventory (user_id, card_id, name, era, group_name, rarity) VALUES (%s,%s,%s,%s,%s,%s)",
                        (target_id, card_id_db, name, era, group_name, rarity)
                    )

                await interaction.response.send_message(
                    f"✅ Added {quantity}x **{name}** to {user.mention}"
                )

            else:
                # 🔹 Check owned
                owned_res = run_query(
                    "SELECT COUNT(*) FROM inventory WHERE user_id=%s AND card_id=%s",
                    (target_id, card_id),
                    fetchone=True
                )
                owned = owned_res[0] if owned_res else 0

                if owned < quantity:
                    return await interaction.response.send_message(
                        f"❌ User only has {owned} copies.",
                        ephemeral=True
                    )

                run_query("""
                    DELETE FROM inventory
                    WHERE ctid IN (
                        SELECT ctid FROM inventory
                        WHERE user_id=%s AND card_id=%s
                        LIMIT %s
                    )
                """, (target_id, card_id, quantity))

                await interaction.response.send_message(
                    f"✅ Removed {quantity}x **{name}** from {user.mention}"
                )

            # 📜 LOG
            run_query(
                "INSERT INTO logs (user_id, action, details) VALUES (%s,%s,%s)",
                (target_id, "manage_card", f"{action_value} {quantity} {card_id}")
            )
            await log_action(
    str(interaction.user.id),
    "manage",
    f"{action_value} {type_value} for {target_id}"
            )

    except Exception as e:
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )
# -------------------------------
# /logs
# -------------------------------

OWNER_GUILD_ID = 1475099422315647006

@bot.tree.command(name="logs", description="View logs with filters")
@app_commands.describe(
    user="Filter by user",
    action="Filter by action (drop, pay, etc)"
)
async def logs_cmd(
    interaction: discord.Interaction,
    user: discord.User | None = None,
    action: str | None = None
):

    if interaction.guild_id != OWNER_GUILD_ID:
        await interaction.response.send_message(
            "❌ Not allowed.",
            ephemeral=True
        )
        return

    query = "SELECT user_id, action, details, timestamp FROM logs"
    conditions = []
    params = []

    # 🔹 Filters
    if user:
        conditions.append("user_id = %s")
        params.append(str(user.id))

    if action:
        conditions.append("action = %s")
        params.append(action.lower())

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY id DESC LIMIT 15"

    data = run_query(query, tuple(params), fetchall=True)

    if not data:
        await interaction.response.send_message(
            "❌ No logs found.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="📜 Filtered Logs",
        color=discord.Color.dark_blue()
    )

    for user_id, act, details, ts in data:
        embed.add_field(
            name=f"{act.upper()} | {user_id}",
            value=f"{details}\n<t:{ts}:R>",
            inline=False
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)
    
# ------------------------------
# /pay
# ------------------------------
@bot.tree.command(
    name="pay",
    description="Send boba or cakecoins to another user"
)
@app_commands.describe(
    user="User to pay",
    amount="Amount to send",
    currency="boba or cakecoins"
)
async def pay_cmd(
    interaction: discord.Interaction,
    user: discord.Member,
    amount: int,
    currency: str
):

    sender_id = str(interaction.user.id)
    receiver_id = str(user.id)
    currency = currency.lower()

    # 🔒 Validations
    if amount <= 0:
        return await interaction.response.send_message(
            "❌ Amount must be positive.",
            ephemeral=True
        )

    if sender_id == receiver_id:
        return await interaction.response.send_message(
            "❌ You cannot pay yourself.",
            ephemeral=True
        )

    if currency not in ["boba", "cakecoins"]:
        return await interaction.response.send_message(
            "❌ Currency must be 'boba' or 'cakecoins'.",
            ephemeral=True
        )

    try:
        # 🔹 Ensure users exist
        ensure_user(sender_id)
        ensure_user(receiver_id)

        # 🔹 Check balance
        res = run_query(
            f"SELECT {currency} FROM users WHERE user_id = %s",
            (sender_id,),
            fetchone=True
        )

        if not res or res[0] < amount:
            return await interaction.response.send_message(
                f"❌ Not enough {currency}.",
                ephemeral=True
            )

        # 🔒 SAFE TRANSFER (atomic style)
        run_query(
            f"UPDATE users SET {currency} = {currency} - %s WHERE user_id = %s",
            (amount, sender_id)
        )

        run_query(
            f"UPDATE users SET {currency} = {currency} + %s WHERE user_id = %s",
            (amount, receiver_id)
        )

        emoji = BOBA if currency == "boba" else CAKE

        embed = discord.Embed(
            title=f"{PUDDING} Payment Successful!",
            description=(
                f"{interaction.user.mention} sent "
                f"**{amount} {currency}** {emoji} to {user.mention}"
            ),
            color=discord.Color.green()
        )

        await interaction.response.send_message(embed=embed)

        # 📜 LOGGING (NEW 🔥)
        run_query(
            "INSERT INTO logs (user_id, action, details) VALUES (%s,%s,%s)",
            (sender_id, "pay_sent", f"{amount} {currency} → {receiver_id}")
        )
        run_query(
            "INSERT INTO logs (user_id, action, details) VALUES (%s,%s,%s)",
            (receiver_id, "pay_received", f"{amount} {currency} ← {sender_id}")
        )
        await log_action(
    sender_id,
    "pay",
    f"Sent {amount} {currency} to {receiver_id}"
)
    except Exception as e:
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )
        

# -------------------------------
# /menu
# -------------------------------
@bot.tree.command(
    name="menu",
    description="View all available cards"
)
@app_commands.describe(
    filter_type="Filter by id, name, era, group, or rarity (optional)",
    filter_value="Value to filter (optional)"
)
async def menu_cmd(
    interaction: discord.Interaction,
    filter_type: str | None = None,
    filter_value: str | None = None
):

    try:
        # 🔹 Get all cards from DB
        data = run_query(
            "SELECT id, name, era, group_name, rarity FROM cards ORDER BY name",
            fetchall=True
        )

        if not data:
            return await interaction.response.send_message(
                "❌ No cards found.",
                ephemeral=True
            )

        # 🔹 Apply filter
        if filter_type and filter_value:
            ft = filter_type.lower()
            fv = filter_value.lower()

            if ft == "id":
                data = [c for c in data if str(c[0]).lower() == fv]

            elif ft == "name":
                data = [c for c in data if fv in str(c[1]).lower()]

            elif ft == "era":
                data = [c for c in data if str(c[2]).lower() == fv]

            elif ft == "group":
                data = [c for c in data if str(c[3]).lower() == fv]

            elif ft == "rarity":
                try:
                    rarity_val = int(fv)
                    data = [c for c in data if c[4] == rarity_val]
                except:
                    data = []

        if not data:
            return await interaction.response.send_message(
                "❌ No cards match this filter.",
                ephemeral=True
            )

        # -------------------------------
        # 📄 Pagination
        # -------------------------------
        per_page = 5
        total_pages = (len(data) - 1) // per_page + 1

        def get_embed(page):
            embed = discord.Embed(
                title=f"{TEA} Card Menu (Page {page+1}/{total_pages})",
                color=discord.Color.orange()
            )

            start = page * per_page
            end = start + per_page

            for card_id, name, era, group_name, rarity in data[start:end]:
                rarity_str = PANG * int(rarity)

                embed.add_field(
                    name=f"{name} (ID: {card_id})",
                    value=(
                        f"{SPIRAL} {era} | {STAR} {group_name}\n"
                        f"{rarity_str}"
                    ),
                    inline=False
                )

            return embed

        # -------------------------------
        # 🔘 Pagination Buttons
        # -------------------------------
        class MenuView(View):
            def __init__(self):
                super().__init__(timeout=120)
                self.page = 0

            @discord.ui.button(emoji=LEFT, style=discord.ButtonStyle.gray)
            async def prev(self, interaction2: discord.Interaction, button: Button):
                if self.page > 0:
                    self.page -= 1
                    await interaction2.response.edit_message(
                        embed=get_embed(self.page),
                        view=self
                    )

            @discord.ui.button(emoji=RIGHT, style=discord.ButtonStyle.gray)
            async def next(self, interaction2: discord.Interaction, button: Button):
                if self.page < total_pages - 1:
                    self.page += 1
                    await interaction2.response.edit_message(
                        embed=get_embed(self.page),
                        view=self
                    )

        await interaction.response.send_message(
            embed=get_embed(0),
            view=MenuView()
        )

    except Exception as e:
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )
    
    
# -------------------------------
# /giftcard (advanced)
# -------------------------------
@bot.tree.command(
    name="giftcard",
    description="Send up to 5 different cards with custom amounts"
)
@app_commands.describe(
    user="The user to send cards to",
    card1="Card ID 1",
    amount1="Amount for card 1",
    card2="Card ID 2 (optional)",
    amount2="Amount for card 2",
    card3="Card ID 3 (optional)",
    amount3="Amount for card 3",
    card4="Card ID 4 (optional)",
    amount4="Amount for card 4",
    card5="Card ID 5 (optional)",
    amount5="Amount for card 5"
)
async def giftcard_cmd(
    interaction: discord.Interaction,
    user: discord.User,
    card1: str,
    amount1: int,
    card2: str | None = None,
    amount2: int | None = None,
    card3: str | None = None,
    amount3: int | None = None,
    card4: str | None = None,
    amount4: int | None = None,
    card5: str | None = None,
    amount5: int | None = None,
):

    sender = str(interaction.user.id)
    receiver = str(user.id)

    # 🔒 Basic checks
    if sender == receiver:
        return await interaction.response.send_message(
            "❌ You can't gift cards to yourself.",
            ephemeral=True
        )

    # 🔹 Ensure users exist
    ensure_user(sender)
    ensure_user(receiver)

    # 🔹 Collect inputs
    inputs = [
        (card1, amount1),
        (card2, amount2),
        (card3, amount3),
        (card4, amount4),
        (card5, amount5),
    ]

    # Remove empty ones
    inputs = [(cid, amt) for cid, amt in inputs if cid and amt]

    if not inputs:
        return await interaction.response.send_message(
            "❌ You must provide at least one card.",
            ephemeral=True
        )

    # ❌ Prevent duplicate cards
    card_ids = [cid for cid, _ in inputs]
    if len(card_ids) != len(set(card_ids)):
        return await interaction.response.send_message(
            "❌ You cannot send the same card multiple times.",
            ephemeral=True
        )

    try:
        summary = []

        for card_id, amount in inputs:

            # 🔹 Validate amount
            if amount < 1 or amount > 5:
                return await interaction.response.send_message(
                    f"❌ Amount for card {card_id} must be 1–5.",
                    ephemeral=True
                )

            # 🔹 Check ownership
            owned = run_query(
                "SELECT card_id, name, era, group_name, rarity FROM inventory WHERE user_id=%s AND card_id=%s",
                (sender, card_id),
                fetchall=True
            )

            if not owned or len(owned) < amount:
                return await interaction.response.send_message(
                    f"❌ Not enough copies of {card_id}.",
                    ephemeral=True
                )

            card_info = owned[0]

            # 🔹 Remove from sender
            run_query("""
                DELETE FROM inventory
                WHERE ctid IN (
                    SELECT ctid FROM inventory
                    WHERE user_id=%s AND card_id=%s
                    LIMIT %s
                )
            """, (sender, card_id, amount))

            # 🔹 Add to receiver
            for _ in range(amount):
                run_query(
                    "INSERT INTO inventory (user_id, card_id, name, era, group_name, rarity) VALUES (%s,%s,%s,%s,%s,%s)",
                    (
                        receiver,
                        card_info[0],
                        card_info[1],
                        card_info[2],
                        card_info[3],
                        card_info[4]
                    )
                )

            rarity_str = PANG * int(card_info[4])
            summary.append(f"{amount}x {card_info[1]} {rarity_str}")

        # 🎁 Final embed
        embed = discord.Embed(
            title=f"{CHOCOLATE} Gift Sent!",
            description="\n".join(summary),
            color=discord.Color.green()
        )

        embed.set_footer(text=f"Sent to {user.display_name}")

        await interaction.response.send_message(embed=embed)

        # 📜 LOGGING (NEW 🔥)
        run_query(
            "INSERT INTO logs (user_id, action, details) VALUES (%s,%s,%s)",
            (sender, "gift_sent", str(summary))
        )
        run_query(
            "INSERT INTO logs (user_id, action, details) VALUES (%s,%s,%s)",
            (receiver, "gift_received", str(summary))
        )
        await log_action(
    sender,
    "giftcard",
    f"Sent {amount}x {card_id} to {receiver}"
        )

    except Exception as e:
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )   


# -------------------------------
# /profile
# -------------------------------
@bot.tree.command(
    name="profile",
    description="View your or another user's profile"
)
@app_commands.describe(user="View another user's profile (optional)")
async def profile_cmd(
    interaction: discord.Interaction,
    user: discord.Member | None = None
):

    target = user if user else interaction.user
    user_id = str(target.id)

    try:
        # 🔹 Ensure user exists
        ensure_user(user_id)

        # 🔹 Balance
        res = run_query(
            "SELECT boba, cakecoins FROM users WHERE user_id=%s",
            (user_id,),
            fetchone=True
        )
        boba, cakecoins = res if res else (0, 0)

        # 🔹 Card count
        count_res = run_query(
            "SELECT COUNT(*) FROM inventory WHERE user_id=%s",
            (user_id,),
            fetchone=True
        )
        card_count = count_res[0] if count_res else 0

        # 🔹 Profile data
        p = run_query(
            "SELECT about, fav_card_id FROM profiles WHERE user_id=%s",
            (user_id,),
            fetchone=True
        )
        about = p[0] if p else "No about set."
        fav_card_id = p[1] if p else None

        # 🎨 Embed
        embed = discord.Embed(
            title=f"{TEA} {target.name}'s Profile",
            color=discord.Color.purple()
        )

        embed.add_field(name=f"{BOBA} Boba", value=str(boba))
        embed.add_field(name=f"{CAKE} Cakecoins", value=str(cakecoins))
        embed.add_field(name=f"{BUTTON} Cards", value=str(card_count), inline=False)

        embed.add_field(
            name=f"{PANCAKE} About",
            value=about or "No about set.",
            inline=False
        )

        # 🔹 Favourite Card (FROM DB ✅)
        if fav_card_id:
            fav = run_query(
                """SELECT name, era, group_name, rarity 
                   FROM inventory 
                   WHERE user_id=%s AND card_id=%s 
                   LIMIT 1""",
                (user_id, fav_card_id),
                fetchone=True
            )

            if fav:
                name, era, group_name, rarity = fav
                rarity_str = PANG * int(rarity)

                embed.add_field(
                    name=f"{PUDDING} Favourite Card",
                    value=(
                        f"{name} (ID: {fav_card_id})\n"
                        f"{SPIRAL} {era} | {STAR} {group_name}\n"
                        f"{rarity_str}"
                    ),
                    inline=False
                )
            else:
                embed.add_field(
                    name=f"{PUDDING} Favourite Card",
                    value="❌ Card not found",
                    inline=False
                )

        # 🔻 Footer
        embed.set_footer(text=f"User ID: {user_id}")

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )
        
 # -------------------------------
# /setabout
# -------------------------------
@bot.tree.command(
    name="setabout",
    description="Set your profile about"
)
@app_commands.describe(text="Your profile about text")
async def setabout_cmd(interaction: discord.Interaction, text: str):

    user_id = str(interaction.user.id)

    try:
        # 🔹 Ensure user exists (VERY IMPORTANT)
        run_query(
            "INSERT INTO users (user_id, boba, cakecoins) VALUES (%s, 0, 0) ON CONFLICT (user_id) DO NOTHING",
            (user_id,)
        )

        # 🔒 Limit length (prevents spam / huge embeds)
        if len(text) > 300:
            await interaction.response.send_message(
                "❌ About must be under 300 characters.",
                ephemeral=True
            )
            return

        # 🔹 Save about
        run_query("""
            INSERT INTO profiles (user_id, about)
            VALUES (%s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET about = %s
        """, (user_id, text, text))

        # 🔹 Log action
        await log_action(
            user_id,
            "setabout",
            f"Updated about: {text[:50]}{'...' if len(text) > 50 else ''}"
        )

        # ✅ Success message
        embed = discord.Embed(
            description=f"{PUDDING} About updated!",
            color=discord.Color.green()
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )


# -------------------------------
# /setfav
# -------------------------------
@bot.tree.command(
    name="setfav",
    description="Set your favourite card"
)
@app_commands.describe(card_id="Card ID to set as favourite")
async def setfav_cmd(interaction: discord.Interaction, card_id: str):

    user_id = str(interaction.user.id)
    card_id = str(card_id).strip()

    try:
        # 🔹 Ensure profile exists
        run_query(
            "INSERT INTO profiles (user_id, about) VALUES (%s, '') ON CONFLICT (user_id) DO NOTHING",
            (user_id,)
        )

        # 🔹 Check if user owns the card (TEXT SAFE ✅)
        owned = run_query(
            "SELECT 1 FROM inventory WHERE user_id=%s AND LOWER(card_id)=LOWER(%s)",
            (user_id, card_id),
            fetchone=True
        )

        if not owned:
            await interaction.response.send_message(
                "❌ You don't own this card.",
                ephemeral=True
            )
            return

        # 🔹 Save favourite
        run_query(
            "UPDATE profiles SET fav_card_id=%s WHERE user_id=%s",
            (card_id, user_id)
        )

        await interaction.response.send_message(
            f"{PUDDING} Favourite card set to **{card_id}**!",
            ephemeral=True
        )

    except Exception as e:
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )
            
# -------------------------------
# on_ready
# -------------------------------
started = False  # 👈 global flag

@bot.event
async def on_ready():
    global started

    if started:
        return

    started = True  # 🔒 prevent duplicate runs

    try:
        print("🔄 Starting bot setup...")

        # 🔹 Setup database
        setup_database()

        # 🔹 Sync slash commands
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} commands")

        # 🔹 Start reminder loop safely
        if not hasattr(bot, "reminder_task"):
            bot.reminder_task = bot.loop.create_task(reminder_loop())
            print("🔔 Reminder loop started")

        print(f"✅ Logged in as {bot.user}")

    except Exception as e:
        print(f"❌ Startup error: {e}")
        
# -------------------------------
# reminder loop
# -------------------------------
async def reminder_loop():
    await bot.wait_until_ready()

    while True:
        now = int(time.time())

        try:
            reminders = run_query(
                "SELECT user_id, command, end_time, channel_id FROM reminders WHERE end_time <= %s",
                (now,),
                fetchall=True
            ) or []

            for user_id, command, end_time, channel_id in reminders:

                # 🔹 Get channel safely
                channel = bot.get_channel(int(channel_id))
                if channel is None:
                    try:
                        channel = await bot.fetch_channel(int(channel_id))
                    except:
                        continue

                # 🔹 Send reminder
                if isinstance(channel, (discord.TextChannel, discord.Thread)):
                    try:
                        await channel.send(
                            f"{BALL} <@{user_id}> your **{command}** is ready!"
                        )
                    except Exception as e:
                        print(f"Send failed: {e}")

                # 🔹 Delete reminder after sending
                run_query(
                    "DELETE FROM reminders WHERE user_id=%s AND command=%s",
                    (user_id, command)
                )

        except Exception as e:
            print(f"Reminder loop error: {e}")

        await asyncio.sleep(60)                  

# -------------------------------
# Run bot
# -------------------------------
import os
import sys

TOKEN: str = os.getenv("TOKEN") or ""

if not TOKEN:
    print("❌ TOKEN missing!")
    sys.exit(1)

bot.run(TOKEN)