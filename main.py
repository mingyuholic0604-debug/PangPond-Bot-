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

BALL = os.getenv("BALL_EMOJI") or "⚽"
BOBA = os.getenv("BOBA_EMOJI") or "🧋"
BUTTON = os.getenv("BUTTON_EMOJI") or "🔘"
CAKE = os.getenv("CAKE_EMOJI") or "🍰"
CHOCOLATE = os.getenv("CHOCOLATE_EMOJI") or "🍫"
CROISSANT = os.getenv("CROISSANT_EMOJI") or "🥐"
ICE = os.getenv("ICE_EMOJI") or "❄️"
LEFT = os.getenv("LEFT_EMOJI") or "⬅️"
PANCAKE = os.getenv("PANCAKE_EMOJI") or "🥞"
PANG = os.getenv("PANG_EMOJI") or "🍞"
PUDDING = os.getenv("PUDDING_EMOJI") or "🍮"
RIGHT = os.getenv("RIGHT_EMOJI") or "➡️"
SPIRAL = os.getenv("SPIRAL_EMOJI") or "🌀"
STAR = os.getenv("STAR_EMOJI") or "⭐"
TEA = os.getenv("TEA_EMOJI") or "🍵"


# -------------------------------
# DATABASE POOL
# -------------------------------
db_pool = SimpleConnectionPool(
    1, 10,
    DATABASE_URL,
    sslmode="require"
)

# -------------------------------
# SAFE QUERY FUNCTION
# -------------------------------
def run_query(query, params=(), fetchone=False, fetchall=False):
    conn = None
    try:
        conn = db_pool.getconn()

        with conn.cursor() as cur:
            cur.execute(query, params)

            if fetchone:
                result = cur.fetchone()
            elif fetchall:
                result = cur.fetchall()
            else:
                result = None

        conn.commit()
        return result

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[DB ERROR] {e}")
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
    return res[0] if res else 0


def set_cooldown(user_id: str, command: str, now: int):
    run_query("""
        INSERT INTO cooldowns (user_id, command, last_used)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, command)
        DO UPDATE SET last_used = %s
    """, (user_id, command, now, now))


# -------------------------------
# Bot setup
# -------------------------------
intents = discord.Intents.default()

# Enable message content (only needed for prefix commands)
intents.message_content = True  

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


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

            # 🔹 Inventory (TEXT ID ✅)
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

            # 🔹 Profiles (TEXT ID ✅)
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

        conn.commit()

    except Exception as e:
        conn.rollback()
        print(f"[DB SETUP ERROR] {e}")

    finally:
        db_pool.putconn(conn)


# -------------------------------
# Cards (TEXT IDs - DOT FORMAT)
# -------------------------------
cards = [
    {"id": "FK.KANT.THK", "name": "Kant", "era": "The Heart Killers", "group": "First Kanaphan", "rarity": PANG * 1},
    {"id": "KT.BISON.THK", "name": "Bison", "era": "The Heart Killers", "group": "Khaotung Thanawat", "rarity": PANG * 1},
    {"id": "JA.FADEL.THK", "name": "Fadel", "era": "The Heart Killers", "group": "Joong Archen", "rarity": PANG * 1},
    {"id": "DN.STYLE.THK", "name": "Style", "era": "The Heart Killers", "group": "Dunk Natachai", "rarity": PANG * 1}
]

    
# -------------------------------
# Start Button View
# -------------------------------
class StartView(discord.ui.View):

    @discord.ui.button(label="Start", style=discord.ButtonStyle.green)
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)

        try:
            # 🔹 Check if user exists
            exists = run_query(
                "SELECT 1 FROM users WHERE user_id = %s",
                (user_id,),
                fetchone=True
            )

            if exists:
                await interaction.response.send_message(
                    "You already started!",
                    ephemeral=True
                )
                return

            # 🔹 Insert new user
            run_query(
                "INSERT INTO users (user_id, boba, cakecoins) VALUES (%s, %s, %s)",
                (user_id, 0, 0)
            )

            # 🔹 Embed response
            embed = discord.Embed(
                title=f"{PUDDING} Welcome!",
                description="Your journey begins now!",
                color=discord.Color.orange()
            )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )

# -------------------------------
# /start
# -------------------------------
@bot.tree.command(
    name="start",
    description="Start your journey and create your account"
)
async def start(interaction: discord.Interaction):

    embed = discord.Embed(
        title=f"{PUDDING} PangPond Bot",
        description=f"{PANG} Click the button below to start your journey!",
        color=discord.Color.orange()
    )

    try:
        await interaction.response.send_message(
            embed=embed,
            view=StartView()
        )

    except Exception as e:
        # 🔹 Safe fallback if interaction already responded
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )

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
        # 🔹 Get balance
        data = run_query(
            "SELECT boba, cakecoins FROM users WHERE user_id = %s",
            (user_id,),
            fetchone=True
        )

        if not data:
            await interaction.response.send_message(
                "Use /start first!",
                ephemeral=True
            )
            return

        boba, cakecoins = data

        # 🔹 Get card count
        count_res = run_query(
            "SELECT COUNT(*) FROM inventory WHERE user_id = %s",
            (user_id,),
            fetchone=True
        )

        count = count_res[0] if count_res else 0

        # 🔹 Create embed
        embed = discord.Embed(
            title=f"{ICE} Your Balance",
            description=(
                f"{BOBA} Boba: **{boba}**\n"
                f"{CAKE} Cakecoins: **{cakecoins}**\n"
                f"{CROISSANT} Cards: **{count}**"
            ),
            color=discord.Color.orange()
        )

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        # 🔹 Prevent double response crash
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )
            

# -------------------------------
# /drop
# -------------------------------
DROP_COOLDOWN = 300  # change to 300 for 5 mins

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
        # 🔹 Check cooldown
        last = get_cooldown(user_id, "drop")
        remaining = DROP_COOLDOWN - (now - last)

        if remaining > 0:
            minutes = remaining // 60
            seconds = remaining % 60

            await interaction.response.send_message(
                f"⏱ You can drop again in {minutes}m {seconds}s",
                ephemeral=True
            )
            return

        # 🎴 Pick random card
        card = random.choice(cards)

        # 📦 Add to inventory
        run_query(
            "INSERT INTO inventory (user_id, card_id, name, era, group_name, rarity) VALUES (%s,%s,%s,%s,%s,%s)",
            (user_id, card["id"], card["name"], card["era"], card["group"], card["rarity"])
        )

        # 🔢 Count copies
        copies_res = run_query(
            "SELECT COUNT(*) FROM inventory WHERE user_id=%s AND card_id=%s",
            (user_id, card["id"]),
            fetchone=True
        )
        copies = copies_res[0] if copies_res else 1

        # 🔹 Save cooldown
        set_cooldown(user_id, "drop", now)

        # 🔹 Update reminder preference
        if reminder is not None:
            run_query("""
                INSERT INTO reminder_settings (user_id, command, enabled)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, command)
                DO UPDATE SET enabled = %s
            """, (user_id, "drop", reminder, reminder))

        # 🔹 Check if reminder enabled
        res = run_query(
            "SELECT enabled FROM reminder_settings WHERE user_id=%s AND command=%s",
            (user_id, "drop"),
            fetchone=True
        )
        enabled = res[0] if res else True

        # 🔔 Create reminder
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

        # 🎨 Rarity (already emoji ✅)
        rarity_str = card["rarity"]

        # 📦 Embed
        embed = discord.Embed(
            title=f"{PANCAKE} You got a card!",
            description=(
                f"**{card['name']}** (ID: {card['id']})\n"
                f"{SPIRAL} {card['era']} | {STAR} {card['group']}\n"
                f"{rarity_str}"
            ),
            color=discord.Color.orange()
        )

        if "image" in card:
            embed.set_image(url=card["image"])

        embed.set_footer(text=f"You have {copies} copies of this card.")

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
        # 🔹 Fetch inventory
        data = run_query("""
            SELECT card_id, name, era, group_name, rarity, COUNT(*) as copies
            FROM inventory
            WHERE user_id = %s
            GROUP BY card_id, name, era, group_name, rarity
            ORDER BY name
        """, (user_id,), fetchall=True)

        if not data:
            await interaction.response.send_message(
                f"❌ {target.name}'s inventory is empty!",
                ephemeral=True
            )
            return

        # 🔹 Apply filters
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

            # 🔥 NEW: rarity filter (1–5 → emoji)
            elif ft == "rarity":
                try:
                    rarity_num = int(fv)
                    if 1 <= rarity_num <= 5:
                        target_rarity = PANG * rarity_num
                        data = [c for c in data if c[4] == target_rarity]
                    else:
                        data = []
                except:
                    data = []

        if not data:
            await interaction.response.send_message(
                "❌ No cards match this filter.",
                ephemeral=True
            )
            return

        # 🔹 Pagination
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
                rarity_str = rarity  # already emoji

                embed.add_field(
                    name=f"{name} (ID: {card_id})",
                    value=f"{SPIRAL} {era} | {STAR} {group_name}\n{rarity_str} | Copies: {copies}",
                    inline=False
                )

            return embed

        # 🔹 Pagination View
        class InventoryView(View):
            def __init__(self):
                super().__init__(timeout=120)
                self.page = 0

            @discord.ui.button(label=LEFT, style=discord.ButtonStyle.gray)
            async def prev(self, interaction: discord.Interaction, button: Button):
                if self.page > 0:
                    self.page -= 1
                    await interaction.response.edit_message(
                        embed=get_embed(self.page),
                        view=self
                    )

            @discord.ui.button(label=RIGHT, style=discord.ButtonStyle.gray)
            async def next(self, interaction: discord.Interaction, button: Button):
                if self.page < total_pages - 1:
                    self.page += 1
                    await interaction.response.edit_message(
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
        # 🔹 Check cooldown
        last = get_cooldown(user_id, "daily")
        remaining = DAILY_COOLDOWN - (now - last)

        if remaining > 0:
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60

            await interaction.response.send_message(
                f"⏱ You can claim daily again in {hours}h {minutes}m",
                ephemeral=True
            )
            return

        # 🎁 Rewards
        boba = 2000
        cakecoins = 10

        # 🔹 Update balance
        run_query("""
            INSERT INTO users (user_id, boba, cakecoins)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET 
                boba = users.boba + %s,
                cakecoins = users.cakecoins + %s
        """, (user_id, boba, cakecoins, boba, cakecoins))

        # 🔹 Save cooldown
        set_cooldown(user_id, "daily", now)

        # 🔹 Update reminder preference
        if reminder is not None:
            run_query("""
                INSERT INTO reminder_settings (user_id, command, enabled)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, command)
                DO UPDATE SET enabled = %s
            """, (user_id, "daily", reminder, reminder))

        # 🔹 Check if reminder enabled
        res = run_query(
            "SELECT enabled FROM reminder_settings WHERE user_id=%s AND command=%s",
            (user_id, "daily"),
            fetchone=True
        )
        enabled = res[0] if res else True

        # 🔔 Create reminder
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

        # 🎁 Embed
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

    except Exception as e:
        # 🔹 Safe interaction handling
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
        # 🔹 Check cooldown
        last = get_cooldown(user_id, "weekly")
        remaining = WEEKLY_COOLDOWN - (now - last)

        if remaining > 0:
            days = remaining // 86400
            hours = (remaining % 86400) // 3600

            await interaction.response.send_message(
                f"⏱ You can claim weekly again in {days}d {hours}h",
                ephemeral=True
            )
            return

        # 🎁 Rewards
        boba = 5000
        cakecoins = 50

        # 🔹 Update balance
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

        # 🔹 Update reminder preference
        if reminder is not None:
            run_query("""
                INSERT INTO reminder_settings (user_id, command, enabled)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, command)
                DO UPDATE SET enabled = %s
            """, (user_id, "weekly", reminder, reminder))

        # 🔹 Check if reminder enabled
        res = run_query(
            "SELECT enabled FROM reminder_settings WHERE user_id=%s AND command=%s",
            (user_id, "weekly"),
            fetchone=True
        )
        enabled = res[0] if res else True

        # 🔔 Create reminder
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

        # 🎁 Embed
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
        # 🔹 Check cooldown
        last = get_cooldown(user_id, "bake")
        remaining = BAKE_COOLDOWN - (now - last)

        if remaining > 0:
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60

            await interaction.response.send_message(
                f"⏱ You can bake again in {hours}h {minutes}m",
                ephemeral=True
            )
            return

        # 🎁 Rewards
        boba = random.randint(200, 800)
        cakecoins = random.randint(1, 5)

        # 🔹 Update balance
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

        # 🔹 Update reminder preference
        if reminder is not None:
            run_query("""
                INSERT INTO reminder_settings (user_id, command, enabled)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, command)
                DO UPDATE SET enabled = %s
            """, (user_id, "bake", reminder, reminder))

        # 🔹 Check if reminder enabled
        res = run_query(
            "SELECT enabled FROM reminder_settings WHERE user_id=%s AND command=%s",
            (user_id, "bake"),
            fetchone=True
        )
        enabled = res[0] if res else True

        # 🔔 Create reminder
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

        # 🎁 Embed
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

    except Exception as e:
        # 🔹 Safe interaction handling
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

    # 🔥 Optional emojis per command (clean UI)
    cmd_emojis = {
        "drop": PANCAKE,
        "bake": CROISSANT,
        "daily": BUTTON,
        "weekly": STAR
    }

    try:
        embed = discord.Embed(
            title=f"{TEA} Your Cooldowns",
            color=discord.Color.blue()
        )

        for cmd, cd_time in commands_list.items():

            # 🔹 Get cooldown
            last = get_cooldown(user_id, cmd)
            remaining = cd_time - (now - last)

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
        # 🔹 Safe interaction handling
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )
                    

# -------------------------------
# /manage
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
async def handle_cmd(
    interaction: discord.Interaction,
    user: discord.User,
    action: app_commands.Choice[str],
    type: app_commands.Choice[str],
    amount: int | None = None,
    card_id: str | None = None,
    quantity: int | None = None
):

    # 🔒 Role check
    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("❌ Could not verify roles.", ephemeral=True)
        return

    if not any(role.name.lower() == "mod" for role in interaction.user.roles):
        await interaction.response.send_message("❌ You are not authorized.", ephemeral=True)
        return

    target_id = str(user.id)
    action_value = action.value
    type_value = type.value

    try:
        # 🔹 Currency
        if type_value in ["boba", "cakecoins"]:
            if amount is None or amount <= 0:
                await interaction.response.send_message("❌ Invalid amount.", ephemeral=True)
                return

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

        # 🔹 Cards
        elif type_value == "card":
            if not card_id or not quantity or quantity <= 0:
                await interaction.response.send_message(
                    "❌ Provide valid card_id and quantity.",
                    ephemeral=True
                )
                return

            card_data = next((c for c in cards if c["id"] == card_id), None)

            if not card_data:
                await interaction.response.send_message("❌ Card not found.", ephemeral=True)
                return

            if action_value == "add":
                for _ in range(quantity):
                    run_query(
                        "INSERT INTO inventory (user_id, card_id, name, era, group_name, rarity) VALUES (%s,%s,%s,%s,%s,%s)",
                        (
                            target_id,
                            card_data["id"],
                            card_data["name"],
                            card_data["era"],
                            card_data["group"],
                            card_data["rarity"]
                        )
                    )

                await interaction.response.send_message(
                    f"✅ Added {quantity}x **{card_data['name']}** to {user.mention}"
                )

            else:
                # 🔹 Check how many user has
                owned_res = run_query(
                    "SELECT COUNT(*) FROM inventory WHERE user_id=%s AND card_id=%s",
                    (target_id, card_id),
                    fetchone=True
                )
                owned = owned_res[0] if owned_res else 0

                if owned < quantity:
                    await interaction.response.send_message(
                        f"❌ User only has {owned} copies.",
                        ephemeral=True
                    )
                    return

                # 🔹 Remove multiple copies safely
                run_query("""
                    DELETE FROM inventory
                    WHERE ctid IN (
                        SELECT ctid FROM inventory
                        WHERE user_id=%s AND card_id=%s
                        LIMIT %s
                    )
                """, (target_id, card_id, quantity))

                await interaction.response.send_message(
                    f"✅ Removed {quantity}x **{card_data['name']}** from {user.mention}"
                )

    except Exception as e:
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )           
            

        
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
        await interaction.response.send_message(
            "❌ Amount must be positive.",
            ephemeral=True
        )
        return

    if sender_id == receiver_id:
        await interaction.response.send_message(
            "❌ You cannot pay yourself.",
            ephemeral=True
        )
        return

    if currency not in ["boba", "cakecoins"]:
        await interaction.response.send_message(
            "❌ Currency must be 'boba' or 'cakecoins'.",
            ephemeral=True
        )
        return

    try:
        # 🔹 Ensure both users exist
        run_query(
            "INSERT INTO users (user_id, boba, cakecoins) VALUES (%s, 0, 0) ON CONFLICT (user_id) DO NOTHING",
            (sender_id,)
        )
        run_query(
            "INSERT INTO users (user_id, boba, cakecoins) VALUES (%s, 0, 0) ON CONFLICT (user_id) DO NOTHING",
            (receiver_id,)
        )

        # 🔹 Check sender balance
        res = run_query(
            f"SELECT {currency} FROM users WHERE user_id = %s",
            (sender_id,),
            fetchone=True
        )

        if not res or res[0] < amount:
            await interaction.response.send_message(
                f"❌ Not enough {currency}.",
                ephemeral=True
            )
            return

        # 🔹 Transfer
        run_query(
            f"UPDATE users SET {currency} = {currency} - %s WHERE user_id = %s",
            (amount, sender_id)
        )

        run_query(
            f"UPDATE users SET {currency} = {currency} + %s WHERE user_id = %s",
            (amount, receiver_id)
        )

        # 🎨 Emoji fix
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

    filtered_cards = cards

    # 🔹 Apply filter only if BOTH are provided
    if filter_type and filter_value:
        ft = str(filter_type).lower()
        fv = str(filter_value).lower()

        if ft == "id":
            filtered_cards = [c for c in cards if str(c.get("id")) == fv]

        elif ft == "name":
            filtered_cards = [c for c in cards if fv in str(c.get("name", "")).lower()]

        elif ft == "era":
            filtered_cards = [c for c in cards if str(c.get("era", "")).lower() == fv]

        elif ft == "group":
            filtered_cards = [c for c in cards if str(c.get("group", "")).lower() == fv]

        # ⭐ NEW: RARITY FILTER
        elif ft == "rarity":
            try:
                rarity_val = int(fv)
                if 1 <= rarity_val <= 5:
                    filtered_cards = [
                        c for c in cards if int(c.get("rarity", 1)) == rarity_val
                    ]
                else:
                    filtered_cards = []
            except:
                filtered_cards = []

    if not filtered_cards:
        await interaction.response.send_message(
            "❌ No cards found.",
            ephemeral=True
        )
        return

    # 🔹 Pagination
    per_page = 5
    total_pages = (len(filtered_cards) - 1) // per_page + 1

    def get_embed(page):
        embed = discord.Embed(
            title=f"{TEA} Card Menu (Page {page+1}/{total_pages})",
            color=discord.Color.orange()
        )

        start = page * per_page
        end = start + per_page

        for c in filtered_cards[start:end]:
            rarity = PANG * int(c.get("rarity", 1))  # ✅ FIXED EMOJI

            embed.add_field(
                name=f"{c.get('name')} (ID: {c.get('id')})",
                value=(
                    f"{SPIRAL} {c.get('era')} | {STAR} {c.get('group')}\n"
                    f"{rarity}"
                ),
                inline=False
            )

        return embed

    # 🔹 Buttons
    class MenuView(View):
        def __init__(self):
            super().__init__(timeout=120)
            self.page = 0

        @discord.ui.button(label=f"{LEFT}", style=discord.ButtonStyle.gray)
        async def prev(self, interaction2: discord.Interaction, button: discord.ui.Button):
            if self.page > 0:
                self.page -= 1
                await interaction2.response.edit_message(
                    embed=get_embed(self.page),
                    view=self
                )

        @discord.ui.button(label=f"{RIGHT}", style=discord.ButtonStyle.gray)
        async def next(self, interaction2: discord.Interaction, button: discord.ui.Button):
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
        await interaction.response.send_message(
            "❌ You can't gift cards to yourself.",
            ephemeral=True
        )
        return

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
        await interaction.response.send_message(
            "❌ You must provide at least one card.",
            ephemeral=True
        )
        return

    # 🔥 Prevent duplicate card entries
    card_ids = [cid for cid, _ in inputs]
    if len(card_ids) != len(set(card_ids)):
        await interaction.response.send_message(
            "❌ You cannot send the same card multiple times.",
            ephemeral=True
        )
        return

    try:
        summary = []

        for card_id, amount in inputs:

            if amount < 1 or amount > 5:
                await interaction.response.send_message(
                    f"❌ Amount for card {card_id} must be 1–5.",
                    ephemeral=True
                )
                return

            # 🔹 Check ownership
            owned = run_query(
                "SELECT card_id, name, era, group_name, rarity FROM inventory WHERE user_id=%s AND card_id=%s",
                (sender, card_id),
                fetchall=True
            )

            if not owned or len(owned) < amount:
                await interaction.response.send_message(
                    f"❌ Not enough copies of {card_id}.",
                    ephemeral=True
                )
                return

            card_info = owned[0]

            # 🔹 Remove safely
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

            # ⭐ Rarity display
            rarity_str = PANG * int(card_info[4])

            summary.append(f"{amount}x {card_info[1]} {rarity_str}")

        # 🎁 Final message
        embed = discord.Embed(
            title=f"{CHOCOLATE} Gift Sent!",
            description="\n".join(summary),
            color=discord.Color.green()
        )

        embed.set_footer(text=f"Sent to {user.display_name}")

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
        # 🔹 Get balance
        res = run_query(
            "SELECT boba, cakecoins FROM users WHERE user_id=%s",
            (user_id,),
            fetchone=True
        )
        boba, cakecoins = res if res else (0, 0)

        # 🔹 Get card count
        count_res = run_query(
            "SELECT COUNT(*) FROM inventory WHERE user_id=%s",
            (user_id,),
            fetchone=True
        )
        card_count = count_res[0] if count_res else 0

        # 🔹 Get profile
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

        # 📝 About
        embed.add_field(
            name=f"{PANCAKE} About",
            value=about or "No about set.",
            inline=False
        )

        # 🎴 Favourite card
        if fav_card_id:
            fav_card = next((c for c in cards if c["id"] == fav_card_id), None)

            if fav_card:
                rarity = PANG * int(fav_card.get("rarity", 1))  # ✅ FIXED

                embed.add_field(
                    name=f"{PUDDING} Favourite Card",
                    value=(
                        f"{fav_card['name']} (ID: {fav_card['id']})\n"
                        f"{SPIRAL} {fav_card['era']} | {STAR} {fav_card['group']}\n"
                        f"{rarity}"
                    ),
                    inline=False
                )

                # ✅ FIXED INDENT
                if "image" in fav_card:
                    embed.set_image(url=fav_card["image"])

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

    # 🔒 Optional: limit length (prevents spam / huge embeds)
    if len(text) > 300:
        await interaction.response.send_message(
            "❌ About must be under 300 characters.",
            ephemeral=True
        )
        return

    try:
        run_query("""
            INSERT INTO profiles (user_id, about)
            VALUES (%s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET about = %s
        """, (user_id, text, text))

        await interaction.response.send_message(
            f"✅ {PUDDING} About updated!",
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
# /setfav
# -------------------------------
@bot.tree.command(
    name="setfav",
    description="Set your favourite card"
)
@app_commands.describe(card_id="Card ID to set as favourite")
async def setfav_cmd(interaction: discord.Interaction, card_id: str):

    user_id = str(interaction.user.id)

    try:
        # 🔹 Check if user owns the card
        owned = run_query(
            "SELECT 1 FROM inventory WHERE user_id=%s AND card_id=%s",
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
        run_query("""
            INSERT INTO profiles (user_id, fav_card_id)
            VALUES (%s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET fav_card_id = %s
        """, (user_id, card_id, card_id))

        await interaction.response.send_message(
            f"{PUDDING} Favourite card set!",
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

    started = True  # 🔒 prevents duplicate runs

    try:
        setup_database()
        await bot.tree.sync()
        bot.loop.create_task(reminder_loop())

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