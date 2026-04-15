kimport discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button

import psycopg2
from psycopg2.pool import SimpleConnectionPool

import os
import random
import asyncio
import time

from dotenv import load_dotenv
import os

load_dotenv()

print("🚀 BOT FILE STARTED")

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
# SAF FUNCTION (FIXED)
# -------------------------------

def run_query(query, params=None, fetchone=False, fetchall=False):
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)

            if fetchone:
                return cur.fetchone()
            if fetchall:
                return cur.fetchall()

            conn.commit()

    except Exception as e:
        conn.rollback()  # 🔥 critical
        print(f"[DB ERROR] {e}")

    finally:
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
    
def ensure_user(user_id: str):
    run_query(
        "INSERT INTO users (user_id, boba, cakecoins) VALUES (%s, 0, 0) ON CONFLICT (user_id) DO NOTHING",
        (user_id,)
    )

async def log_action(user_id: str, action: str, details: str):

    timestamp = int(time.time())

    # 🔹 Save to DB
    run_query(
        "INSERT INTO logs (user_id, command, details, timestamp) VALUES (%s,%s,%s,%s)",
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

def get_remaining_cooldown(user_id: str, command: str, cooldown_time: int):
    last = get_cooldown(user_id, command)
    now = int(time.time())

    remaining = cooldown_time - (now - last)
    return max(0, remaining)

def set_reminder(user_id, command, duration, channel_id):
    now = int(time.time())

    run_query("""
        INSERT INTO reminders (user_id, command, end_time, channel_id)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id, command)
        DO UPDATE SET end_time = %s, channel_id = %s
    """, (
        user_id,
        command,
        now + duration,
        str(channel_id),
        now + duration,
        str(channel_id)
    ))

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

reminder_task = None

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
            cur.execute("""CREATE TABLE IF NOT EXISTS regular_cards (
        card_id TEXT PRIMARY KEY,
        name TEXT,
        group_name TEXT,
        era TEXT,
        rarity INT
    );""")

            cur.execute("""CREATE TABLE IF NOT EXISTS custom_cards (
        card_id TEXT PRIMARY KEY,
        name TEXT,
        group_name TEXT,
        era TEXT,
        rarity INT
    );""")

            cur.execute("""CREATE TABLE IF NOT EXISTS spec_cards (
        card_id TEXT PRIMARY KEY,
        name TEXT,
        group_name TEXT,
        era TEXT,
        rarity INT,
        event_name TEXT
    );""")

            cur.execute("""CREATE TABLE IF NOT EXISTS active_events (
        event_name TEXT PRIMARY KEY
    );""")

            cur.execute("""CREATE TABLE IF NOT EXISTS user_cards (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        card_id TEXT
    );""")

            cur.execute("""CREATE TABLE IF NOT EXISTS cooldowns (
        user_id BIGINT PRIMARY KEY,
        last_drop TIMESTAMP
    );""")

            cur.execute("""CREATE TABLE IF NOT EXISTS logs (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        action TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );""")

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[DB SETUP ERROR] {e}")

    finally:
        db_pool.putconn(conn)


from PIL import Image
from io import BytesIO
import aiohttp

# 🔹 Safe image loader
async def get_image(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    print(f"❌ Failed to fetch: {url}")
                    return None

                data = await resp.read()

                if not data:
                    print(f"❌ Empty data: {url}")
                    return None

                img = Image.open(BytesIO(data))
                img.load()  # 🔥 IMPORTANT (fixes GitHub issues)

                return img.convert("RGBA")

    except Exception as e:
        print(f"❌ Image error: {url} -> {e}")
        return None


# 🔹 Grid creator
async def create_card_grid(image_urls):
    images = []

    for url in image_urls:
        img = await get_image(url)

        # 🔥 fallback if image fails
        if img is None:
            img = Image.new("RGBA", (300, 400), (255, 0, 0, 255))

        # resize all images same size
        img = img.resize((300, 400))
        images.append(img)

    # 🔹 Create grid (3 cards in a row)
    width = 300 * len(images)
    height = 400

    grid = Image.new("RGBA", (width, height))

    for i, img in enumerate(images):
        grid.paste(img, (i * 300, 0))

    # 🔹 Save to buffer
    buffer = BytesIO()
    grid.save(buffer, format="PNG")
    buffer.seek(0)

    return buffer



# BUTTON DROP

class DropView(discord.ui.View):
    def __init__(self, user_id, cards, interaction):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.cards = cards
        self.interaction = interaction
        self.claimed_index = None

    async def handle_pick(self, interaction, index):
        if str(interaction.user.id) != self.user_id:
            return await interaction.response.send_message(
                "❌ This isn't your drop!",
                ephemeral=True
            )

        if self.claimed_index is not None:
            return await interaction.response.send_message(
                "❌ You already picked a card!",
                ephemeral=True
            )

        self.claimed_index = index

        card = self.cards[index]
        card_id, name, era, group, rarity, image = card

        # 🔹 Add to inventory
        run_query("""
        INSERT INTO inventory (user_id, card_id, name, era, group_name, rarity)
        VALUES (%s, %s, %s, %s, %s, %s)
        """, (self.user_id, card_id, name, era, group, rarity))

        # 🔹 Count copies
        copies_res = run_query(
            "SELECT COUNT(*) FROM inventory WHERE user_id=%s AND card_id=%s",
            (self.user_id, card_id),
            fetchone=True
        )
        copies = copies_res[0] if copies_res else 1

        # 🔹 Group Progress (UNIQUE cards owned)
        owned_res = run_query("""
            SELECT COUNT(DISTINCT card_id)
            FROM inventory
            WHERE user_id=%s AND group_name=%s
        """, (self.user_id, group), fetchone=True)

        owned = owned_res[0] if owned_res else 0

        total_res = run_query("""
            SELECT COUNT(*)
            FROM cards
            WHERE group_name=%s
        """, (group,), fetchone=True)

        total = total_res[0] if total_res else 0

        # 🔹 Rarity display
        rarity_display = PANG * int(rarity)

        # 🔹 Build description
        desc = ""

        for i, c in enumerate(self.cards, start=1):
            cid, cname, cera, cgroup, crarity, _ = c
            crarity_display = PANG * int(crarity)

            desc += (
                f"**Card #{i} ({cid})**\n"
                f"{SPIRAL} {cname} ({cera})\n"
                f"{crarity_display}\n"
            )

            # ONLY show details for picked card
            if i - 1 == index:
                desc += (
                    f"{interaction.user.mention}\n"
                    f"Group Progress: {owned}/{total}\n"
                    f"Copies: {copies}\n"
                )

            desc += "\n"

        embed = discord.Embed(
            title="Results of the drop!",
            description=desc,
            color=discord.Color.purple()
        )

        # 🔹 Show picked card image
        if image:
            embed.set_image(url=image)

        await interaction.response.edit_message(embed=embed, view=None)

        # 🔹 Log
        await log_action(
            self.user_id,
            "drop_pick",
            f"Picked {name} ({card_id})"
        )

    @discord.ui.button(label="1", style=discord.ButtonStyle.primary)
    async def pick1(self, interaction, button):
        await self.handle_pick(interaction, 0)

    @discord.ui.button(label="2", style=discord.ButtonStyle.primary)
    async def pick2(self, interaction, button):
        await self.handle_pick(interaction, 1)

    @discord.ui.button(label="3", style=discord.ButtonStyle.primary)
    async def pick3(self, interaction, button):
        await self.handle_pick(interaction, 2)

async def group_autocomplete(interaction: discord.Interaction, current: str):
    results = run_query(
        "SELECT DISTINCT group_name FROM cards WHERE group_name ILIKE %s LIMIT 25",
        (f"%{current}%",),
        fetchall=True
    )

    return [
        app_commands.Choice(name=r[0], value=r[0])
        for r in results
    ]

async def era_autocomplete(interaction: discord.Interaction, current: str):
    results = run_query(
        "SELECT DISTINCT era FROM cards WHERE era ILIKE %s LIMIT 25",
        (f"%{current}%",),
        fetchall=True
    )

    return [
        app_commands.Choice(name=r[0], value=r[0])
        for r in results
    ]

CATEGORIES = ["regular", "spec", "custom"]

async def category_autocomplete(interaction: discord.Interaction, current: str):
    return [
        app_commands.Choice(name=c, value=c)
        for c in CATEGORIES
        if current.lower() in c.lower()
    ]
    
# -------------------------------
# /balance
# -------------------------------
@bot.tree.command(
    name="balance",
    description="Check your balance and total cards"
)
async def balance(interaction: discord.Interaction):

    user_id = str(interaction.user.id)

    await interaction.response.defer()

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

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
            
# -------------------------------
# /drop
# -------------------------------

DROP_COOLDOWN = 600

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

    await interaction.response.defer()

    try:
        # 🔹 Ensure user
        ensure_user(user_id)

        # 🔹 Cooldown check
        remaining = get_remaining_cooldown(user_id, "drop", DROP_COOLDOWN)

        if remaining > 0:
            minutes = remaining // 60
            seconds = remaining % 60

            return await interaction.followup.send(
                f"{BALL} You can drop again in {minutes}m {seconds}s",
                ephemeral=True
            )

        # 🔹 Get regular cards
        regular_cards = run_query("""
            SELECT card_id, name, era, group_name, rarity, image
            FROM cards
            WHERE category='regular'
        """, fetchall=True)

        # 🔹 Get ACTIVE event
        active_event = run_query(
            "SELECT event_name FROM events WHERE active=TRUE ORDER BY RANDOM() LIMIT 1",
            fetchone=True
        )

        event_cards = []
        if active_event:
            event_name = active_event[0]

            event_cards = run_query("""
                SELECT card_id, name, era, group_name, rarity, image
                FROM spec_cards
                WHERE event_name=%s
            """, (event_name,), fetchall=True)

        # 🔹 Merge pool (30% event chance)
        all_cards = []

        if event_cards and random.random() < 0.3:
            all_cards.extend(event_cards)

        all_cards.extend(regular_cards)

        if not all_cards:
            return await interaction.followup.send(
                "❌ No cards available.",
                ephemeral=True
            )

        # 🔹 Weighted rarity system
        def get_weighted_card():
            weighted = []
            for c in all_cards:
                rarity = int(c[4]) if c[4] else 1
                weight = max(1, 6 - rarity)
                weighted.extend([c] * weight)
            return random.choice(weighted)

        # 🔹 Pick 3 cards
        cards = [get_weighted_card() for _ in range(3)]

        # 🔹 Set cooldown
        set_cooldown(user_id, "drop", now)

        # 🔹 Reminder toggle save
        if reminder is not None:
            run_query("""
                INSERT INTO reminder_settings (user_id, command, enabled)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, command)
                DO UPDATE SET enabled = %s
            """, (user_id, "drop", reminder, reminder))

        # 🔹 Check reminder enabled
        res = run_query(
            "SELECT enabled FROM reminder_settings WHERE user_id=%s AND command=%s",
            (user_id, "drop"),
            fetchone=True
        )
        enabled = res[0] if res else True

        # 🔹 Set reminder (CLEAN SYSTEM)
        if enabled:
            set_reminder(user_id, "drop", DROP_COOLDOWN, interaction.channel_id)

        # 🔹 Create image grid
        image_urls = [c[5] for c in cards]
        grid_buffer = await create_card_grid(image_urls)
        file = discord.File(grid_buffer, filename="drop.png")

        # 🔹 Build description
        desc = ""
        for i, c in enumerate(cards, start=1):
            cid, name, era, group, rarity, _ = c
            rarity_display = PANG * int(rarity)

            desc += (
                f"**Card #{i} ({cid})**\n"
                f"{SPIRAL} {name} ({era})\n"
                f"{STAR} {group}\n"
                f"{rarity_display}\n\n"
            )

        # 🔹 Embed
        embed = discord.Embed(
            title=f"{PANCAKE} Choose a card!",
            description=desc,
            color=discord.Color.orange()
        )

        embed.set_image(url="attachment://drop.png")

        # 🔹 Send with buttons
        await interaction.followup.send(
            embed=embed,
            file=file,
            view=DropView(user_id, cards, interaction)
        )

        # 🔹 Logging
        await log_action(
            user_id,
            "drop",
            "Generated 3-card drop"
        )

    except Exception as e:
        await interaction.followup.send(
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

    await interaction.response.defer()

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
            await interaction.followup.send(
                f"❌ {target.name}'s inventory is empty!",
                ephemeral=True
            )
            return

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
            await interaction.followup.send(
                "❌ No cards match this filter.",
                ephemeral=True
            )
            return

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

        await interaction.followup.send(
            embed=get_embed(0),
            view=InventoryView()
        )

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
    
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

    await interaction.response.defer()

    try:
        # 🔹 Ensure user
        ensure_user(user_id)

        # 🔹 Cooldown check
        remaining = get_remaining_cooldown(user_id, "daily", DAILY_COOLDOWN)

        if remaining > 0:
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60

            return await interaction.followup.send(
                f"{BALL} You can claim daily again in {hours}h {minutes}m",
                ephemeral=True
            )

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

        # 🔹 Logging
        await log_action(
            user_id,
            "daily",
            f"+{boba} boba, +{cakecoins} cakecoins"
        )

        # 🔹 Set cooldown
        set_cooldown(user_id, "daily", now)

        # 🔹 Reminder toggle save
        if reminder is not None:
            run_query("""
                INSERT INTO reminder_settings (user_id, command, enabled)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, command)
                DO UPDATE SET enabled = %s
            """, (user_id, "daily", reminder, reminder))

        # 🔹 Check reminder enabled
        res = run_query(
            "SELECT enabled FROM reminder_settings WHERE user_id=%s AND command=%s",
            (user_id, "daily"),
            fetchone=True
        )
        enabled = res[0] if res else True

        # 🔹 Set reminder (CLEAN SYSTEM)
        if enabled:
            set_reminder(user_id, "daily", DAILY_COOLDOWN, interaction.channel_id)

        # 🔹 Embed
        embed = discord.Embed(
            title=f"{BUTTON} Daily Reward Claimed!",
            description=(
                f"{SPIRAL} You received:\n\n"
                f"{BOBA} **{boba} boba**\n"
                f"{CAKE} **{cakecoins} cakecoins**"
            ),
            color=discord.Color.green()
        )

        embed.set_image(
            url="https://media2.giphy.com/media/v1.Y2lkPTZjMDliOTUydmlrODh6YXlxcWI4dGhhbXl3czZpejVmZzVnOXEydDN2dmswdmM5aSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/uKKSAhC0gb5roHsy9v/giphy.gif"
        )

        await interaction.followup.send(embed=embed)

        # 🔹 Extra logging (DB logs table)
        run_query(
            "INSERT INTO logs (user_id, command, details) VALUES (%s,%s,%s)",
            (user_id, "daily", f"+{boba} boba, +{cakecoins} cakecoins")
        )

    except Exception as e:
        await interaction.followup.send(
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

    await interaction.response.defer()

    try:
        # 🔹 Ensure user
        ensure_user(user_id)

        # 🔹 Cooldown check
        remaining = get_remaining_cooldown(user_id, "weekly", WEEKLY_COOLDOWN)

        if remaining > 0:
            days = remaining // 86400
            hours = (remaining % 86400) // 3600

            return await interaction.followup.send(
                f"⏱ You can claim weekly again in {days}d {hours}h",
                ephemeral=True
            )

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

        # 🔹 Logging
        await log_action(
            user_id,
            "weekly",
            f"+{boba} boba, +{cakecoins} cakecoins"
        )

        # 🔹 Set cooldown
        set_cooldown(user_id, "weekly", now)

        # 🔹 Reminder toggle save
        if reminder is not None:
            run_query("""
                INSERT INTO reminder_settings (user_id, command, enabled)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, command)
                DO UPDATE SET enabled = %s
            """, (user_id, "weekly", reminder, reminder))

        # 🔹 Check reminder enabled
        res = run_query(
            "SELECT enabled FROM reminder_settings WHERE user_id=%s AND command=%s",
            (user_id, "weekly"),
            fetchone=True
        )
        enabled = res[0] if res else True

        # 🔹 Set reminder (CLEAN SYSTEM)
        if enabled:
            set_reminder(user_id, "weekly", WEEKLY_COOLDOWN, interaction.channel_id)

        # 🔹 Embed
        embed = discord.Embed(
            title=f"{BUTTON} Weekly Reward Claimed!",
            description=(
                f"{SPIRAL} You received:\n\n"
                f"{BOBA} **{boba} boba**\n"
                f"{CAKE} **{cakecoins} cakecoins**"
            ),
            color=discord.Color.gold()
        )

        embed.set_image(
            url="https://media0.giphy.com/media/v1.Y2lkPTZjMDliOTUyY2xhcHA5cDM1aWhkcGl5MDR1MzY1bmZuNGF6aXMxeWl0dTM0ODNjMyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/5wKuwXycuNfl0VEOgI/giphy.gif"
        )

        await interaction.followup.send(embed=embed)

        # 🔹 Extra DB log
        run_query(
            "INSERT INTO logs (user_id, command, details) VALUES (%s,%s,%s)",
            (user_id, "weekly", f"+{boba} boba, +{cakecoins} cakecoins")
        )

    except Exception as e:
        await interaction.followup.send(
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

    await interaction.response.defer()

    try:
        # 🔹 Ensure user exists
        ensure_user(user_id)

        # 🔹 Cooldown check
        remaining = get_remaining_cooldown(user_id, "bake", BAKE_COOLDOWN)

        if remaining > 0:
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60

            return await interaction.followup.send(
                f"{BALL} You can bake again in {hours}h {minutes}m",
                ephemeral=True
            )

        # 🎁 Rewards (random)
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

        # 🔹 Reminder toggle save
        if reminder is not None:
            run_query("""
                INSERT INTO reminder_settings (user_id, command, enabled)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, command)
                DO UPDATE SET enabled = %s
            """, (user_id, "bake", reminder, reminder))

        # 🔹 Check if reminders enabled
        res = run_query(
            "SELECT enabled FROM reminder_settings WHERE user_id=%s AND command=%s",
            (user_id, "bake"),
            fetchone=True
        )
        enabled = res[0] if res else True

        # 🔹 Set reminder
        if enabled:
            set_reminder(user_id, "bake", BAKE_COOLDOWN, interaction.channel_id)

        # 🔹 Embed
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

        await interaction.followup.send(embed=embed)

        # 🔹 Logging
        run_query(
            "INSERT INTO logs (user_id, command, details) VALUES (%s,%s,%s)",
            (user_id, "bake", f"+{boba} boba, +{cakecoins} cakecoins")
        )

        await log_action(
            user_id,
            "bake",
            f"+{boba} boba, +{cakecoins} cakecoins"
        )

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        
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

    await interaction.response.defer()

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

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
                    

# -------------------------------
# /manage (ADMIN ONLY)
# -------------------------------
GUILD_ID = 1475099422315647006

@bot.tree.command(
    name="manage",
    description="Admin command",
    guild=discord.Object(id=GUILD_ID)
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

    await interaction.response.defer(ephemeral=True)

    # 🔒 SERVER LOCK (VERY IMPORTANT 🔥)
    MAIN_GUILD_ID = 1475099422315647006  # ⬅️ PUT YOUR SERVER ID HERE

    if interaction.guild_id != MAIN_GUILD_ID:
        await interaction.followup.send(
            "❌ Only staff for PangPond can use this command.",
            ephemeral=True
        )
        return

    # 🔒 ROLE CHECK
    if not isinstance(interaction.user, discord.Member):
        await interaction.followup.send(
            "❌ Could not verify roles.",
            ephemeral=True
        )
        return

    if not interaction.user.guild_permissions.manage_guild:
        await interaction.followup.send(
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
                await interaction.followup.send(
                    "❌ Invalid amount.",
                    ephemeral=True
                )
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

            await interaction.followup.send(
                f"✅ {action_value.title()}ed {amount} {type_value} for {user.mention}"
            )

            # 📜 LOG
            run_query(
                "INSERT INTO logs (user_id, command, details) VALUES (%s,%s,%s)",
                (target_id, "manage_currency", f"{action_value} {amount} {type_value}")
            )

# -------------------------------
# 🃏 CARDS (DB BASED ✅)
# -------------------------------
        elif type_value == "card":

            if not card_id or not quantity or quantity <= 0:
                await interaction.followup.send(
                    "❌ Provide valid card_id and quantity.",
                    ephemeral=True
                )
                return

            # 🔹 Get card from DB (NOT list ❌)
            card_data = run_query(
                "SELECT id, name, era, group_name, rarity FROM cards WHERE id=%s",
                (card_id,),
                fetchone=True
            )

            if not card_data:
                await interaction.followup.send(
                    "❌ Card not found.",
                    ephemeral=True
                )
                return

            card_id_db, name, era, group_name, rarity = card_data

            if action_value == "add":

                for _ in range(quantity):
                    run_query(
                        "INSERT INTO inventory (user_id, card_id, name, era, group_name, rarity) VALUES (%s,%s,%s,%s,%s,%s)",
                        (target_id, card_id_db, name, era, group_name, rarity)
                    )

                await interaction.followup.send(
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
                    await interaction.followup.send(
                        f"❌ User only has {owned} copies.",
                        ephemeral=True
                    )
                    return

                run_query("""
                    DELETE FROM inventory
                    WHERE ctid IN (
                        SELECT ctid FROM inventory
                        WHERE user_id=%s AND card_id=%s
                        LIMIT %s
                    )
                """, (target_id, card_id, quantity))

                await interaction.followup.send(
                    f"✅ Removed {quantity}x **{name}** from {user.mention}"
                )

            # 📜 LOG
            run_query(
                "INSERT INTO logs (user_id, command, details) VALUES (%s,%s,%s)",
                (target_id, "manage_card", f"{action_value} {quantity} {card_id}")
            )
            await log_action(
    str(interaction.user.id),
    "manage",
    f"{action_value} {type_value} for {target_id}"
            )

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
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

    await interaction.response.defer(ephemeral=True)

    if interaction.guild_id != OWNER_GUILD_ID:
        await interaction.followup.send(
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
        await interaction.followup.send(
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

    await interaction.followup.send(embed=embed, ephemeral=True)
    
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

    await interaction.response.defer()

    # 🔒 Validations
    if amount <= 0:
        await interaction.followup.send(
            "❌ Amount must be positive.",
            ephemeral=True
        )
        return

    if sender_id == receiver_id:
        await interaction.followup.send(
            "❌ You cannot pay yourself.",
            ephemeral=True
        )
        return

    if currency not in ["boba", "cakecoins"]:
        await interaction.followup.send(
            "❌ Currency must be 'boba' or 'cakecoins'.",
            ephemeral=True
        )
        return

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
            await interaction.followup.send(
                f"❌ Not enough {currency}.",
                ephemeral=True
            )
            return

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
        f"**{amount} {currency}** {emoji}"
    ),
    color=discord.Color.green()
)

        await interaction.followup.send(
    content=f"{user.mention}",  # 🔥 this makes the ping work
    embed=embed
)

        # 📜 LOGGING (NEW 🔥)
        run_query(
            "INSERT INTO logs (user_id, command, details) VALUES (%s,%s,%s)",
            (sender_id, "pay_sent", f"{amount} {currency} → {receiver_id}")
        )
        run_query(
            "INSERT INTO logs (user_id, command, details) VALUES (%s,%s,%s)",
            (receiver_id, "pay_received", f"{amount} {currency} ← {sender_id}")
        )
        await log_action(
    sender_id,
    "pay",
    f"Sent {amount} {currency} to {receiver_id}"
)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        

# -------------------------------
# /menu
# -------------------------------
@bot.tree.command(
    name="menu",
    description="View all available cards"
)
@app_commands.describe(
    filter_type="id / name / era / group / rarity / category",
    filter_value="Value to filter"
)
async def menu_cmd(
    interaction: discord.Interaction,
    filter_type: str | None = None,
    filter_value: str | None = None
):
    await interaction.response.defer()

    try:
        # 🔹 Get all cards
        cards = run_query("""
            SELECT card_id, name, era, group_name, rarity, category, image
            FROM cards
            ORDER BY rarity DESC
        """, fetchall=True)

        if not cards:
            return await interaction.followup.send(
                "❌ No cards found.",
                ephemeral=True
            )

        # 🔹 Default = all cards
        data = cards

        # 🔹 Apply filters
        if filter_type and filter_value:
            ft = filter_type.lower()
            fv = filter_value.lower()

            if ft == "id":
                data = [c for c in cards if str(c[0]).lower() == fv]

            elif ft == "name":
                data = [c for c in cards if fv in str(c[1]).lower()]

            elif ft == "era":
                data = [c for c in cards if str(c[2]).lower() == fv]

            elif ft == "group":
                data = [c for c in cards if str(c[3]).lower() == fv]

            elif ft == "rarity":
                try:
                    rarity_val = int(fv)
                    data = [c for c in cards if c[4] == rarity_val]
                except:
                    data = []

            elif ft == "category":
                data = [c for c in cards if str(c[5]).lower() == fv]

        if not data:
            return await interaction.followup.send(
                "❌ No cards match this filter.",
                ephemeral=True
            )

        # 🔹 Pagination
        per_page = 5
        total_pages = (len(data) - 1) // per_page + 1

        def get_embed(page):
            embed = discord.Embed(
                title=f"{TEA} Card Menu (Page {page+1}/{total_pages})",
                color=discord.Color.orange()
            )

            start = page * per_page
            end = start + per_page

            for card_id, name, era, group_name, rarity, category, image in data[start:end]:
                rarity_str = PANG * int(rarity)

                embed.add_field(
                    name=f"{name} (ID: {card_id})",
                    value=(
                        f"{SPIRAL} {era} | {STAR} {group_name}\n"
                        f"{rarity_str}\n"
                        f"{CHOCOLATE} {category}"
                    ),
                    inline=False
                )

            return embed

        # 🔹 Pagination view
        class MenuView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=120)
                self.page = 0

            @discord.ui.button(emoji=LEFT, style=discord.ButtonStyle.gray)
            async def prev(self, interaction2: discord.Interaction, button: discord.ui.Button):
                if self.page > 0:
                    self.page -= 1
                    await interaction2.response.edit_message(
                        embed=get_embed(self.page),
                        view=self
                    )

            @discord.ui.button(emoji=RIGHT, style=discord.ButtonStyle.gray)
            async def next(self, interaction2: discord.Interaction, button: discord.ui.Button):
                if self.page < total_pages - 1:
                    self.page += 1
                    await interaction2.response.edit_message(
                        embed=get_embed(self.page),
                        view=self
                    )

        # 🔹 Send first page
        await interaction.followup.send(
            embed=get_embed(0),
            view=MenuView()
        )

    except Exception as e:
        await interaction.followup.send(
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

    await interaction.response.defer()

    # 🔒 Basic checks
    if sender == receiver:
        await interaction.followup.send(
            "❌ You can't gift cards to yourself.",
            ephemeral=True
        )
        return

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
        await interaction.followup.send(
            "❌ You must provide at least one card.",
            ephemeral=True
        )
        return

    # ❌ Prevent duplicate cards
    card_ids = [cid for cid, _ in inputs]
    if len(card_ids) != len(set(card_ids)):
        await interaction.followup.send(
            "❌ You cannot send the same card multiple times.",
            ephemeral=True
        )
        return

    try:
        summary = []

        for card_id, amount in inputs:

            # 🔹 Validate amount
            if amount < 1 or amount > 5:
                await interaction.followup.send(
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
                await interaction.followup.send(
                    f"❌ Not enough copies of {card_id}.",
                    ephemeral=True
                )
                return

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

        await interaction.followup.send(
    content=f"{user.mention}",  # 🔥 ensures ping works
    embed=embed
)


        # 📜 LOGGING (NEW 🔥)
        run_query(
            "INSERT INTO logs (user_id, command, details) VALUES (%s,%s,%s)",
            (sender, "gift_sent", str(summary))
        )
        run_query(
            "INSERT INTO logs (user_id, command, details) VALUES (%s,%s,%s)",
            (receiver, "gift_received", str(summary))
        )
        await log_action(
    sender,
    "giftcard",
    f"Sent {amount}x {card_id} to {receiver}"
        )

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

# --------------
@bot.tree.command(name="ping")
async def ping_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("pong")  # fast = OK

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

    await interaction.response.defer()

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

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        
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

    await interaction.response.defer(ephemeral=True)

    try:
        # 🔹 Ensure user exists (VERY IMPORTANT)
        run_query(
            "INSERT INTO users (user_id, boba, cakecoins) VALUES (%s, 0, 0) ON CONFLICT (user_id) DO NOTHING",
            (user_id,)
        )

        # 🔒 Limit length (prevents spam / huge embeds)
        if len(text) > 300:
            await interaction.followup.send(
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

        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


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

    await interaction.response.defer(ephemeral=True)

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
            await interaction.followup.send(
                "❌ You don't own this card.",
                ephemeral=True
            )
            return

        # 🔹 Save favourite
        run_query(
            "UPDATE profiles SET fav_card_id=%s WHERE user_id=%s",
            (card_id, user_id)
        )

        await interaction.followup.send(
            f"{PUDDING} Favourite card set to **{card_id}**!",
            ephemeral=True
        )

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


# -------------------------------
# /addcard
# -------------------------------

ALLOWED_USERS = [
    1322126091929915454,  # N
    1254757830704103484   # S
]
import discord
from discord import app_commands

@bot.tree.command(name="addcard", description="Add a new card")
@app_commands.autocomplete(
    group=group_autocomplete,
    era=era_autocomplete,
    category=category_autocomplete
)
@app_commands.describe(
    name="Card name",
    group="Group name",
    era="Era",
    rarity="1 to 5",
    category="regular / spec / custom",
    card_id="Unique card ID",
    image="Image URL"
)
async def addcard(
    interaction: discord.Interaction,
    name: str,
    group: str,
    era: str,
    rarity: int,
    category: str,
    card_id: str,
    image: str
):
    # 🔒 Permission check FIRST
    if interaction.user.id not in ALLOWED_USERS:
        return await interaction.response.send_message(
            "❌ You are not allowed to use this command.",
            ephemeral=True
        )

    # 🔹 Defer ONLY ONCE
    await interaction.response.defer()

    try:
        # 🔹 Insert into DB
        run_query("""
        INSERT INTO cards (card_id, name, era, group_name, rarity, category, image)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (card_id, name, era, group, rarity, category, image))

        # 🔹 Pang rarity display
        rarity_display = PANG * int(rarity)

        # 🔹 Embed preview
        embed = discord.Embed(
            title="✅ Card Added!",
            description=(
                f"**{name}** ({card_id})\n"
                f"{SPIRAL} {era}\n"
                f"{STAR} {group}\n"
                f"{rarity_display}\n"
                f"{CHOCOLATE} Category: {category}"
            ),
            color=discord.Color.green()
        )

        if image:
            embed.set_image(url=image)

        await interaction.followup.send(embed=embed)

        # 🔹 Logging
        await log_action(
            str(interaction.user.id),
            "addcard",
            f"{name} ({card_id})"
        )

    except Exception as e:
        await interaction.followup.send(
            f"❌ Error: {e}",
            ephemeral=True
        )

# -------------------------------
# /deletecard
# -------------------------------

@bot.tree.command(name="deletecard", description="Delete a card")
@app_commands.describe(card_id="Card ID to delete")
async def deletecard_cmd(interaction: discord.Interaction, card_id: str):
    await interaction.response.defer()

    try:
        # 🔹 Try deleting from regular cards
        result = run_query("""
            DELETE FROM cards
            WHERE LOWER(card_id) = LOWER(%s)
            RETURNING card_id
        """, (card_id,), fetchone=True)

        if result:
            return await interaction.followup.send(
                f"{SPIRAL} Deleted `{result[0]}` from Regular cards"
            )

        # 🔹 Try deleting from event cards
        result = run_query("""
            DELETE FROM spec_cards
            WHERE LOWER(card_id) = LOWER(%s)
            RETURNING card_id
        """, (card_id,), fetchone=True)

        if result:
            return await interaction.followup.send(
                f"{SPIRAL} Deleted `{result[0]}` from Event cards"
            )

        # ❌ Not found anywhere
        await interaction.followup.send(
            f"❌ Card `{card_id}` not found in database.",
            ephemeral=True
        )

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        
# -------------------------------
# EVENTS
# -------------------------------
@bot.tree.command(name="startevent", description="Start an event")
@app_commands.describe(event="Event name")
@app_commands.checks.has_permissions(administrator=True)
async def startevent(interaction: discord.Interaction, event: str):
    await interaction.response.defer()

    try:
        # ❌ already active?
        cursor.execute("SELECT event_name FROM active_events WHERE event_name = %s;", (event,))
        if cursor.fetchone():
            await interaction.followup.send(f"❌ Event `{event}` is already active.")
            return

        # ✅ add event
        cursor.execute("INSERT INTO active_events (event_name) VALUES (%s);", (event,))
        conn.commit()

        # 📝 log
        cursor.execute(
            "INSERT INTO logs (user_id, action) VALUES (%s, %s);",
            (interaction.user.id, f"Started event {event}")
        )
        conn.commit()

        await interaction.followup.send(f"✅ Event `{event}` started!")

    except Exception as e:
        print(f"Start event error: {e}")
        await interaction.followup.send("❌ Error starting event.")

@bot.tree.command(name="endevent", description="End an event")
@app_commands.describe(event="Event name")
@app_commands.checks.has_permissions(administrator=True)
async def endevent(interaction: discord.Interaction, event: str):
    await interaction.response.defer()

    try:
        # ❌ check exists
        cursor.execute("SELECT event_name FROM active_events WHERE event_name = %s;", (event,))
        if not cursor.fetchone():
            await interaction.followup.send(f"❌ Event `{event}` is not active.")
            return

        # ✅ delete
        cursor.execute("DELETE FROM active_events WHERE event_name = %s;", (event,))
        conn.commit()

        # 📝 log
        cursor.execute(
            "INSERT INTO logs (user_id, action) VALUES (%s, %s);",
            (interaction.user.id, f"Ended event {event}")
        )
        conn.commit()

        await interaction.followup.send(f"🛑 Event `{event}` ended.")

    except Exception as e:
        print(f"End event error: {e}")
        await interaction.followup.send("❌ Error ending event.")

@bot.tree.command(name="events", description="View active events")
async def events(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        cursor.execute("SELECT event_name FROM active_events;")
        events = cursor.fetchall()

        if not events:
            await interaction.followup.send("❌ No active events.")
            return

        event_list = "\n".join([f"• {e[0]}" for e in events])

        await interaction.followup.send(f"🎉 Active Events:\n{event_list}")

    except Exception as e:
        print(f"Events error: {e}")
        await interaction.followup.send("❌ Error fetching events.")
    

GUILD_ID = 1475099422315647006  # 👈 put your server ID here




# -------------------------------
# reminder loop
# -------------------------------


async def reminder_loop():
    await bot.wait_until_ready()

    while not bot.is_closed():
        try:
            now = int(time.time())

            reminders = run_query("""
                SELECT user_id, command, end_time, channel_id
                FROM reminders
                WHERE end_time <= %s
            """, (now,), fetchall=True)

            for user_id, command, end_time, channel_id in reminders:
                try:
                    # 🔹 Get channel safely
                    channel = bot.get_channel(int(channel_id))

                    if channel is None or not isinstance(channel, discord.TextChannel):
                        continue

                    # 🔹 Build embed (NO ping inside)
                    embed = discord.Embed(
                        title=f"{PANCAKE} Cooldown Ready!",
                        description=(
                            f"{BALL} Your `{command}` is ready to use again!\n"
                        ),
                        color=discord.Color.orange()
                    )

                    # 🔹 SEND with ping OUTSIDE embed
                    await channel.send(
                        content=f"{SPIRAL} <@{user_id}>",
                        embed=embed
                    )

                    # 🔹 Remove reminder after sending
                    run_query("""
                        DELETE FROM reminders
                        WHERE user_id=%s AND command=%s
                    """, (user_id, command))

                except Exception as e:
                    print(f"❌ Reminder send error: {e}")

            # 🔹 Check every 10 seconds
            await asyncio.sleep(10)

        except Exception as e:
            print(f"❌ Reminder loop error: {e}")
            await asyncio.sleep(10)


# -------------------------------
# /sync 
# -------------------------------

@bot.tree.command(name="sync", description="Sync slash commands")
@app_commands.describe(scope="Where to sync commands")
@app_commands.choices(scope=[
    app_commands.Choice(name="Guild (fast)", value="guild"),
    app_commands.Choice(name="Global (slow)", value="global"),
    app_commands.Choice(name="Clear + Resync", value="clear"),
])
async def sync_cmd(interaction: discord.Interaction, scope: app_commands.Choice[str]):
    
    # 🔒 Permission check
    if interaction.user.id not in ALLOWED_USERS:
        return await interaction.response.send_message(
            "❌ You are not allowed to use this command.",
            ephemeral=True
        )

    await interaction.response.defer(ephemeral=True)

    try:
        guild = interaction.guild

        # 🔹 GUILD SYNC (instant)
        if scope.value == "guild":
            synced = await bot.tree.sync(guild=guild)
            await interaction.followup.send(
                f"✅ Synced {len(synced)} commands to this server"
            )

        # 🔹 GLOBAL SYNC (slow)
        elif scope.value == "global":
            synced = await bot.tree.sync()
            await interaction.followup.send(
                f"🌍 Synced {len(synced)} commands globally (may take time)"
            )

        # 🔹 CLEAR + RESYNC (fix bugs)
        elif scope.value == "clear":
            bot.tree.clear_commands(guild=guild)
            synced = await bot.tree.sync(guild=guild)

            await interaction.followup.send(
                f"🧹 Cleared & resynced {len(synced)} commands"
            )

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}")


# -------------------------------
# on_ready
# -------------------------------

import asyncio
import os
import sys

# 🔹 Global task
reminder_task = None


@bot.event
async def on_ready():
    global reminder_task

    print("🔥 on_ready triggered")
    
    await asyncio.to_thread(setup_database)

    # 🔹 Debug commands
    cmds = bot.tree.get_commands()
    print("Commands loaded:", len(cmds))
    print([cmd.name for cmd in cmds])

    # 🔹 Sync commands
    try:
        synced = await bot.tree.sync()
        print(f"🌍 Synced {len(synced)} commands")
    except Exception as e:
        print(f"❌ Sync error: {e}")

    # 🔹 Start reminder loop ONLY once
    if reminder_task is None or reminder_task.done():
        reminder_task = asyncio.create_task(reminder_loop())

    print(f"{PANCAKE} Logged in as {bot.user}")


# -------------------------------
# Run bot
# -------------------------------

TOKEN: str = os.getenv("TOKEN") or ""

if not TOKEN:
    print("❌ TOKEN missing!")
    sys.exit(1)

bot.run(TOKEN)