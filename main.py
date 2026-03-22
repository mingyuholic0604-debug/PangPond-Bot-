import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
import psycopg2
import os
import random
import asyncio
import time


# -------------------------------
# Bot setup
# -------------------------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------------------
# Database
# -------------------------------
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    boba INT,
    cake INT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS inventory (
    user_id TEXT,
    card_id INT,
    name TEXT,
    era TEXT,
    group_name TEXT,
    rarity INT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS cooldowns (
    user_id TEXT,
    command TEXT,
    last_used BIGINT,
    PRIMARY KEY (user_id, command)
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS reminders (
    user_id TEXT,
    command TEXT,
    end_time BIGINT,
    channel_id TEXT
)
""")

cur.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            user_id TEXT PRIMARY KEY,
            about TEXT DEFAULT '',
            fav_card_id INT
        );
    """)

cur.execute("""
        CREATE TABLE IF NOT EXISTS cooldowns (
            user_id TEXT,
            command TEXT,
            last_used INT,
            PRIMARY KEY (user_id, command)
        );
    """)

conn.commit()


def get_cooldown(user, command):
    cur.execute(
        "SELECT last_used FROM cooldowns WHERE user_id=%s AND command=%s",
        (user, command)
    )
    data = cur.fetchone()
    return data[0] if data else 0


def set_cooldown(user, command, timestamp):
    cur.execute(
        "INSERT INTO cooldowns (user_id, command, last_used) VALUES (%s,%s,%s) "
        "ON CONFLICT (user_id, command) DO UPDATE SET last_used=%s",
        (user, command, timestamp, timestamp)
    )
    conn.commit()
    
# -------------------------------
# Cards (WITH IDs)
# -------------------------------
cards = [
    {"id": 1, "name": "Kant", "era": "The Heart Killers", "group": "First Kanaphan", "rarity": 2},
    {"id": 2, "name": "Bison", "era": "The Heart Killers", "group": "Khaotung Thanawat", "rarity": 2},
    {"id": 3, "name": "Fadel", "era": "The Heart Killers", "group": "Joong Archen", "rarity": 3},
    {"id": 4, "name": "Style", "era": "The Heart Killers", "group": "Dunk Natachai", "rarity": 3}
]

# -------------------------------
# Start Button
# -------------------------------
class StartView(discord.ui.View):
    @discord.ui.button(label="Start", style=discord.ButtonStyle.green)
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = str(interaction.user.id)

        cur.execute("SELECT * FROM users WHERE user_id = %s", (user,))
        if cur.fetchone():
            await interaction.response.send_message("You already started!", ephemeral=True)
            return

        cur.execute("INSERT INTO users VALUES (%s, %s, %s)", (user, 0, 0))
        conn.commit()

        embed = discord.Embed(
            title="🍞 Welcome!",
            description="Your journey begins now!",
            color=discord.Color.orange()
        )

        await interaction.response.send_message(embed=embed)

# -------------------------------
# /start
# -------------------------------
@bot.tree.command(name="start")
async def start(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🍞 PangPond Bot",
        description="Click the button to start!",
        color=discord.Color.orange()
    )

    await interaction.response.send_message(embed=embed, view=StartView())

# -------------------------------
# /balance
# -------------------------------
@bot.tree.command(name="balance")
async def balance(interaction: discord.Interaction):
    user = str(interaction.user.id)

    cur.execute("SELECT boba, cake FROM users WHERE user_id = %s", (user,))
    data = cur.fetchone()

    if not data:
        await interaction.response.send_message("Use /start first!", ephemeral=True)
        return

    boba, cake = data

    cur.execute("SELECT COUNT(*) FROM inventory WHERE user_id = %s", (user,))
    count = cur.fetchone()[0]

    embed = discord.Embed(
        title="💰 Your Balance",
        description=(
            f"🧋 Boba: **{boba}**\n"
            f"🍰 Cake Coins: **{cake}**\n"
            f"🎴 Cards: **{count}**"
        ),
        color=discord.Color.orange()
    )

    await interaction.response.send_message(embed=embed)

# -------------------------------
# /drop
# -------------------------------
DROP_COOLDOWN = 600  # 10 minutes

@bot.tree.command(name="drop")
@app_commands.describe(reminder="Turn reminder on/off (optional)")
async def drop_cmd(
    interaction: discord.Interaction,
    reminder: bool | None = None
):

    user_id = str(interaction.user.id)
    now = int(time.time())

    # 🔹 Check cooldown
    with conn.cursor() as cur:
        cur.execute(
            "SELECT last_used FROM cooldowns WHERE user_id=%s AND command=%s",
            (user_id, "drop")
        )
        res = cur.fetchone()

    last = res[0] if res else 0
    remaining = DROP_COOLDOWN - (now - last)

    if remaining > 0:
        minutes = remaining // 60
        seconds = remaining % 60

        await interaction.response.send_message(
            f"⏱ You can drop again in {minutes}m {seconds}s",
            ephemeral=True
        )
        return

    try:
        with conn.cursor() as cur:

            # 🎴 Pick random card
            card = random.choice(cards)

            # 📦 Add to inventory
            cur.execute(
                "INSERT INTO inventory (user_id, card_id, name, era, group_name, rarity) VALUES (%s,%s,%s,%s,%s,%s)",
                (user_id, card["id"], card["name"], card["era"], card["group"], card["rarity"])
            )

            # 🔢 Count copies
            cur.execute(
                "SELECT COUNT(*) FROM inventory WHERE user_id=%s AND card_id=%s",
                (user_id, card["id"])
            )
            copies = cur.fetchone()[0]

            # 🔹 Save cooldown
            cur.execute("""
                INSERT INTO cooldowns (user_id, command, last_used)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, command)
                DO UPDATE SET last_used = %s
            """, (user_id, "drop", now, now))

            # 🔹 Update reminder preference if provided
            if reminder is not None:
                cur.execute("""
                    INSERT INTO reminder_settings (user_id, command, enabled)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, command)
                    DO UPDATE SET enabled = %s
                """, (user_id, "drop", reminder, reminder))

            # 🔹 Check if reminder enabled
            cur.execute(
                "SELECT enabled FROM reminder_settings WHERE user_id=%s AND command=%s",
                (user_id, "drop")
            )
            res = cur.fetchone()
            enabled = res[0] if res else True

            # 🔔 Create reminder
            if enabled:
                cur.execute("""
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

            conn.commit()

        # ⭐ Rarity display
        rarity_str = "🍞" * int(card.get("rarity", 1))

        # 🎴 Embed
        embed = discord.Embed(
            title="🎴 You got a new card!",
            description=f"**{card['name']}** (ID: {card['id']})\n📀 {card['era']} | 👥 {card['group']}\n{rarity_str}",
            color=discord.Color.orange()
        )

        if "image" in card:
            embed.set_image(url=card["image"])

        embed.set_footer(text=f"You have {copies} copies of this card.")

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


# -------------------------------
# /inventory (PAGED)
# -------------------------------

from discord.ui import View, Button
from discord import app_commands
import discord

@bot.tree.command(name="inventory")
@app_commands.describe(
    user="View another user's inventory (optional)",
    filter_type="Filter by id, name, era, or group",
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
        with conn.cursor() as cur:
            cur.execute("""
                SELECT card_id, name, era, group_name, rarity, COUNT(*) as copies
                FROM inventory
                WHERE user_id = %s
                GROUP BY card_id, name, era, group_name, rarity
                ORDER BY name
            """, (user_id,))
            data = cur.fetchall()

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
                data = [c for c in data if str(c[0]) == fv]

            elif ft == "name":
                data = [c for c in data if fv in str(c[1]).lower()]

            elif ft == "era":
                data = [c for c in data if str(c[2]).lower() == fv]

            elif ft == "group":
                data = [c for c in data if str(c[3]).lower() == fv]

        if not data:
            await interaction.response.send_message("❌ No cards match this filter.", ephemeral=True)
            return

        # Pagination
        per_page = 5
        total_pages = (len(data) - 1) // per_page + 1

        def get_embed(page):
            embed = discord.Embed(
                title=f"🎒 {target.name}'s Inventory (Page {page+1}/{total_pages})",
                color=discord.Color.orange()
            )

            start = page * per_page
            end = start + per_page

            for card_id, name, era, group_name, rarity, copies in data[start:end]:
                rarity_str = "🍞" * int(rarity)

                embed.add_field(
                    name=f"{name} (ID: {card_id})",
                    value=f"📀 {era} | 👥 {group_name}\n{rarity_str} | Copies: {copies}",
                    inline=False
                )

            return embed

        class InventoryView(View):
            def __init__(self):
                super().__init__(timeout=120)
                self.page = 0

            @discord.ui.button(label="⬅️", style=discord.ButtonStyle.gray)
            async def prev(self, interaction, button):
                if self.page > 0:
                    self.page -= 1
                    await interaction.response.edit_message(embed=get_embed(self.page), view=self)

            @discord.ui.button(label="➡️", style=discord.ButtonStyle.gray)
            async def next(self, interaction, button):
                if self.page < total_pages - 1:
                    self.page += 1
                    await interaction.response.edit_message(embed=get_embed(self.page), view=self)

        await interaction.response.send_message(embed=get_embed(0), view=InventoryView())

    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)
        

# -------------------------------
# daily command
# -------------------------------

DAILY_COOLDOWN = 86400  # 24 hours

@bot.tree.command(name="daily")
@app_commands.describe(reminder="Turn reminder on/off (optional)")
async def daily_cmd(
    interaction: discord.Interaction,
    reminder: bool | None = None
):

    user_id = str(interaction.user.id)
    now = int(time.time())

    # 🔹 Check cooldown
    with conn.cursor() as cur:
        cur.execute(
            "SELECT last_used FROM cooldowns WHERE user_id=%s AND command=%s",
            (user_id, "daily")
        )
        res = cur.fetchone()

    last = res[0] if res else 0
    remaining = DAILY_COOLDOWN - (now - last)

    if remaining > 0:
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60

        await interaction.response.send_message(
            f"⏱ You can claim daily again in {hours}h {minutes}m",
            ephemeral=True
        )
        return

    try:
        boba = 2000
        cake = 10

        with conn.cursor() as cur:

            # 🔹 Update balance
            cur.execute("""
                INSERT INTO users (user_id, boba, cake)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id)
                DO UPDATE SET 
                    boba = users.boba + %s,
                    cake = users.cake + %s
            """, (user_id, boba, cake, boba, cake))

            # 🔹 Save cooldown
            cur.execute("""
                INSERT INTO cooldowns (user_id, command, last_used)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, command)
                DO UPDATE SET last_used = %s
            """, (user_id, "daily", now, now))

            # 🔹 Update reminder preference if provided
            if reminder is not None:
                cur.execute("""
                    INSERT INTO reminder_settings (user_id, command, enabled)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, command)
                    DO UPDATE SET enabled = %s
                """, (user_id, "daily", reminder, reminder))

            # 🔹 Check if reminder enabled
            cur.execute(
                "SELECT enabled FROM reminder_settings WHERE user_id=%s AND command=%s",
                (user_id, "daily")
            )
            res = cur.fetchone()
            enabled = res[0] if res else True

            # 🔔 Create reminder
            if enabled:
                cur.execute("""
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

            conn.commit()

        # 🎁 Embed
        embed = discord.Embed(
            title="🎁 Daily Reward Claimed!",
            description=f"You received:\n💰 **{boba} boba**\n🍰 **{cake} cake coins**",
            color=discord.Color.green()
        )

        embed.set_image(url="https://media2.giphy.com/media/v1.Y2lkPTZjMDliOTUydmlrODh6YXlxcWI4dGhhbXl3czZpejVmZzVnOXEydDN2dmswdmM5aSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/uKKSAhC0gb5roHsy9v/giphy.gif")

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)
        
    
    
        

# -------------------------------
# weekly 
# -------------------------------

WEEKLY_COOLDOWN = 604800  # 7 days

@bot.tree.command(name="weekly")
@app_commands.describe(reminder="Turn reminder on/off (optional)")
async def weekly_cmd(
    interaction: discord.Interaction,
    reminder: bool | None = None
):

    user_id = str(interaction.user.id)
    now = int(time.time())

    # 🔹 Check cooldown
    with conn.cursor() as cur:
        cur.execute(
            "SELECT last_used FROM cooldowns WHERE user_id=%s AND command=%s",
            (user_id, "weekly")
        )
        res = cur.fetchone()

    last = res[0] if res else 0
    remaining = WEEKLY_COOLDOWN - (now - last)

    if remaining > 0:
        days = remaining // 86400
        hours = (remaining % 86400) // 3600

        await interaction.response.send_message(
            f"⏱ You can claim weekly again in {days}d {hours}h",
            ephemeral=True
        )
        return

    try:
        boba = 5000
        cake = 50

        with conn.cursor() as cur:

            # 🔹 Update balance
            cur.execute("""
                INSERT INTO users (user_id, boba, cake)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id)
                DO UPDATE SET 
                    boba = users.boba + %s,
                    cake = users.cake + %s
            """, (user_id, boba, cake, boba, cake))

            # 🔹 Save cooldown
            cur.execute("""
                INSERT INTO cooldowns (user_id, command, last_used)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, command)
                DO UPDATE SET last_used = %s
            """, (user_id, "weekly", now, now))

            # 🔹 Update reminder preference if provided
            if reminder is not None:
                cur.execute("""
                    INSERT INTO reminder_settings (user_id, command, enabled)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, command)
                    DO UPDATE SET enabled = %s
                """, (user_id, "weekly", reminder, reminder))

            # 🔹 Check if reminder enabled
            cur.execute(
                "SELECT enabled FROM reminder_settings WHERE user_id=%s AND command=%s",
                (user_id, "weekly")
            )
            res = cur.fetchone()
            enabled = res[0] if res else True

            # 🔔 Create reminder
            if enabled:
                cur.execute("""
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

            conn.commit()

        # 🎁 Embed
        embed = discord.Embed(
            title="🎉 Weekly Reward Claimed!",
            description=f"You received:\n💰 **{boba} boba**\n🍰 **{cake} cake coins**",
            color=discord.Color.gold()
        )

        embed.set_image(url="https://media0.giphy.com/media/v1.Y2lkPTZjMDliOTUyY2xhcHA5cDM1aWhkcGl5MDR1MzY1bmZuNGF6aXMxeWl0dTM0ODNjMyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/5wKuwXycuNfl0VEOgI/giphy.gif")

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


# -------------------------------
# /bake
# -------------------------------

BAKE_COOLDOWN = 3600  # 1 hour

@bot.tree.command(name="bake")
@app_commands.describe(reminder="Turn reminder on/off (optional)")
async def bake_cmd(
    interaction: discord.Interaction,
    reminder: bool | None = None
):

    user_id = str(interaction.user.id)
    now = int(time.time())

    # 🔹 Check cooldown
    with conn.cursor() as cur:
        cur.execute(
            "SELECT last_used FROM cooldowns WHERE user_id=%s AND command=%s",
            (user_id, "bake")
        )
        res = cur.fetchone()

    last = res[0] if res else 0
    remaining = BAKE_COOLDOWN - (now - last)

    if remaining > 0:
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60

        await interaction.response.send_message(
            f"⏱ You can bake again in {hours}h {minutes}m",
            ephemeral=True
        )
        return

    try:
        boba = random.randint(200, 800)
        cake = random.randint(1, 5)

        with conn.cursor() as cur:

            # 🔹 Update balance
            cur.execute("""
                INSERT INTO users (user_id, boba, cake)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id)
                DO UPDATE SET 
                    boba = users.boba + %s,
                    cake = users.cake + %s
            """, (user_id, boba, cake, boba, cake))

            # 🔹 Save cooldown
            cur.execute("""
                INSERT INTO cooldowns (user_id, command, last_used)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, command)
                DO UPDATE SET last_used = %s
            """, (user_id, "bake", now, now))

            # 🔹 Update reminder preference ONLY if user sets it
            if reminder is not None:
                cur.execute("""
                    INSERT INTO reminder_settings (user_id, command, enabled)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, command)
                    DO UPDATE SET enabled = %s
                """, (user_id, "bake", reminder, reminder))

            # 🔹 Check if reminders enabled
            cur.execute(
                "SELECT enabled FROM reminder_settings WHERE user_id=%s AND command=%s",
                (user_id, "bake")
            )
            res = cur.fetchone()
            enabled = res[0] if res else True

            # 🔹 Create reminder
            if enabled:
                cur.execute("""
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

            conn.commit()

        embed = discord.Embed(
            title="🍰 Baking Complete!",
            description=f"You earned:\n💰 **{boba} boba**\n🍰 **{cake} cake coins**",
            color=discord.Color.pink()
        )

        embed.set_image(url="https://media4.giphy.com/media/v1.Y2lkPTZjMDliOTUyZGZnMDcwM2o3Zmp6Y2tndHFweHZydTZtMmU1MzE2bHBrc201cjJlZiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/LMuPuB2jQkmgX59vWX/giphy.gif")

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


# -------------------------------
# cooldowns
# -------------------------------
        
@bot.tree.command(name="cooldown")
async def cooldown_cmd(interaction: discord.Interaction):

    user_id = str(interaction.user.id)
    now = int(time.time())

    commands = {
        "drop": 600,
        "bake": 3600,
        "daily": 86400,
        "weekly": 604800
    }

    embed = discord.Embed(
        title="⏱ Your Cooldowns",
        color=discord.Color.blue()
    )

    try:
        with conn.cursor() as cur:
            for cmd, cd_time in commands.items():

                cur.execute(
                    "SELECT last_used FROM cooldowns WHERE user_id=%s AND command=%s",
                    (user_id, cmd)
                )
                res = cur.fetchone()

                last = res[0] if res else 0
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

                embed.add_field(
                    name=f"/{cmd}",
                    value=value,
                    inline=False
                )

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

# ------------------------------- 
# -------------------------------


                    
# -------------------------------
# /manage
# -------------------------------

@bot.tree.command(name="manage")
@app_commands.describe(
    user="The user to modify",
    action="Choose Add or Remove",
    type="Choose the type to modify",
    amount="Amount of currency or card ID"
)
@app_commands.choices(
    action=[
        app_commands.Choice(name="Add", value="add"),
        app_commands.Choice(name="Remove", value="remove")
    ],
    type=[
        app_commands.Choice(name="Boba", value="boba"),
        app_commands.Choice(name="Cake coins", value="cake coins"),
        app_commands.Choice(name="Card", value="card")
    ]
)
async def handle_cmd(interaction: discord.Interaction, user: discord.User, action: app_commands.Choice[str], type: app_commands.Choice[str], amount: str):
    # cast user roles safely
    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("❌ Could not verify your roles.", ephemeral=True)
        return

    if not any(role.name.lower() == "mod" for role in interaction.user.roles):
        await interaction.response.send_message("❌ You are not authorized.", ephemeral=True)
        return

    target_id = str(user.id)
    action_value = action.value  # "add" or "remove"
    type_value = type.value      # "boba", "cake coins", "card"

    # handle currency
    if type_value in ["boba", "cake coins"]:
        amt = int(amount)
        if action_value == "add":
            cur.execute(f"UPDATE users SET {type_value} = {type_value} + %s WHERE user_id = %s", (amt, target_id))
        else:
            cur.execute(f"UPDATE users SET {type_value} = {type_value} - %s WHERE user_id = %s", (amt, target_id))
        conn.commit()
        await interaction.response.send_message(f"✅ {action_value.title()}ed {amt} {type_value} for {user.mention}")

    # handle cards
    elif type_value == "card":
        card_id = int(amount)
        if action_value == "add":
            card_data = next((c for c in cards if c["id"] == card_id), None)
            if not card_data:
                await interaction.response.send_message("❌ Card ID not found.", ephemeral=True)
                return
            cur.execute(
                "INSERT INTO inventory (user_id, card_id, name, era, group_name, rarity) VALUES (%s,%s,%s,%s,%s,%s)",
                (target_id, card_data["id"], card_data["name"], card_data["era"], card_data["group"], card_data["rarity"])
            )
            conn.commit()
            await interaction.response.send_message(f"✅ Card **{card_data['name']}** added to {user.mention}")
        else:
            cur.execute("DELETE FROM inventory WHERE user_id=%s AND card_id=%s", (target_id, card_id))
            conn.commit()
            await interaction.response.send_message(f"✅ Card ID {card_id} removed from {user.mention}")
            
# ------------------------------
# pay
# ------------------------------

@bot.tree.command(name="pay")
@app_commands.describe(
    user="User to pay",
    amount="Amount to send",
    currency="boba or cake"
)
async def pay_cmd(interaction: discord.Interaction, user: discord.Member, amount: int, currency: str):
    sender_id = str(interaction.user.id)
    receiver_id = str(user.id)
    currency = currency.lower()

    if amount <= 0:
        await interaction.response.send_message("❌ Amount must be positive.")
        return

    if sender_id == receiver_id:
        await interaction.response.send_message("❌ You cannot pay yourself.")
        return

    if currency not in ["boba", "cake"]:
        await interaction.response.send_message("❌ Currency must be 'boba' or 'cake'.")
        return

    try:
        with conn.cursor() as cur:
            # Ensure receiver exists
            cur.execute(
                "INSERT INTO users (user_id, boba, cake) VALUES (%s, 0, 0) ON CONFLICT DO NOTHING",
                (receiver_id,)
            )

            # Check sender balance
            cur.execute(f"SELECT {currency} FROM users WHERE user_id = %s", (sender_id,))
            result = cur.fetchone()

            if not result or result[0] < amount:
                await interaction.response.send_message(f"❌ Not enough {currency}.")
                return

            # Deduct sender
            cur.execute(
                f"UPDATE users SET {currency} = {currency} - %s WHERE user_id = %s",
                (amount, sender_id)
            )

            # Add to receiver
            cur.execute(
                f"UPDATE users SET {currency} = {currency} + %s WHERE user_id = %s",
                (amount, receiver_id)
            )

            conn.commit()

        # Emoji based on currency
        emoji = "💰" if currency == "boba" else "🍰"

        embed = discord.Embed(
            title="💸 Payment Successful!",
            description=f"{interaction.user.mention} sent **{amount} {currency}** {emoji} to {user.mention}",
            color=discord.Color.green()
        )

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        conn.rollback()  # 🔥 prevents broken DB
        await interaction.response.send_message(f"❌ Error: {e}")

# -------------------------------
# MENU 
# -------------------------------

from discord.ui import View
from discord import app_commands
import discord

@bot.tree.command(name="menu")
@app_commands.describe(
    filter_type="Filter by id, name, era, or group (optional)",
    filter_value="Value to filter (optional)"
)
async def menu_cmd(
    interaction: discord.Interaction,
    filter_type: str | None = None,
    filter_value: str | None = None
):

    filtered_cards = cards

    # Apply filter only if BOTH are provided
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

    if not filtered_cards:
        await interaction.response.send_message("❌ No cards found.", ephemeral=True)
        return

    # Pagination
    per_page = 5
    total_pages = (len(filtered_cards) - 1) // per_page + 1

    def get_embed(page):
        embed = discord.Embed(
            title=f"📖 Card Menu (Page {page+1}/{total_pages})",
            color=discord.Color.orange()
        )

        start = page * per_page
        end = start + per_page

        for c in filtered_cards[start:end]:
            rarity = "🍞" * int(c.get("rarity", 1))
            embed.add_field(
                name=f"{c.get('name')} (ID: {c.get('id')})",
                value=f"📀 {c.get('era')} | 👥 {c.get('group')}\n{rarity}",
                inline=False
            )

        return embed

    # Buttons
    class MenuView(View):
        def __init__(self):
            super().__init__(timeout=120)
            self.page = 0

        @discord.ui.button(label="⬅️", style=discord.ButtonStyle.gray)
        async def prev(self, interaction2: discord.Interaction, button):
            if self.page > 0:
                self.page -= 1
                await interaction2.response.edit_message(embed=get_embed(self.page), view=self)

        @discord.ui.button(label="➡️", style=discord.ButtonStyle.gray)
        async def next(self, interaction2: discord.Interaction, button):
            if self.page < total_pages - 1:
                self.page += 1
                await interaction2.response.edit_message(embed=get_embed(self.page), view=self)

    await interaction.response.send_message(embed=get_embed(0), view=MenuView())  

# -------------------------------
# gift
# -------------------------------

@bot.tree.command(name="giftcard")
@app_commands.describe(
    user="The user to send card to",
    card_id="ID of the card to send"
)
async def giftcard_cmd(interaction: discord.Interaction, user: discord.User, card_id: int):
    sender = str(interaction.user.id)
    receiver = str(user.id)

    # check sender has card
    cur.execute("SELECT * FROM inventory WHERE user_id=%s AND card_id=%s", (sender, card_id))
    card_row = cur.fetchone()
    if not card_row:
        await interaction.response.send_message("❌ You don't have this card.", ephemeral=True)
        return

    # transfer card
    cur.execute("UPDATE inventory SET user_id=%s WHERE user_id=%s AND card_id=%s", (receiver, sender, card_id))
    conn.commit()
    await interaction.response.send_message(f"🎁 You gifted **{card_row[2]}** to {user.mention}")


# -------------------------------
# /profile
# -------------------------------
@bot.tree.command(name="profile")
@app_commands.describe(user="View another user's profile (optional)")
async def profile_cmd(interaction: discord.Interaction, user: discord.Member | None = None):

    target = user if user else interaction.user
    user_id = str(target.id)

    try:
        with conn.cursor() as cur:
            # get balance
            cur.execute("SELECT boba, cake FROM users WHERE user_id=%s", (user_id,))
            res = cur.fetchone()

            if not res:
                boba, cake = 0, 0
            else:
                boba, cake = res

            # get profile
            cur.execute("SELECT about, fav_card_id FROM profiles WHERE user_id=%s", (user_id,))
            p = cur.fetchone()

            about = p[0] if p else "No about set."
            fav_card_id = p[1] if p else None

        embed = discord.Embed(
            title=f"👤 {target.name}'s Profile",
            color=discord.Color.purple()
        )

        embed.add_field(name="💰 Boba", value=str(boba))
        embed.add_field(name="🍰 Cake Coins", value=str(cake), inline=False)

        embed.add_field(name="📝 About", value=about or "No about set.", inline=False)

        # Favourite card
        if fav_card_id:
            fav_card = next((c for c in cards if c["id"] == fav_card_id), None)

            if fav_card:
                rarity = "🍞" * int(fav_card.get("rarity", 1))

                embed.add_field(
                    name="🎴 Favourite Card",
                    value=f"{fav_card['name']} (ID: {fav_card['id']})\n📀 {fav_card['era']} | 👥 {fav_card['group']}\n{rarity}",
                    inline=False
                )

                if "image" in fav_card:
                    embed.set_image(url=fav_card["image"])

        embed.set_footer(text=f"User ID: {user_id}")

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

# -------------------------------
# /setabout
# -------------------------------
@bot.tree.command(name="setabout")
@app_commands.describe(text="Set your profile about")
async def setabout_cmd(interaction: discord.Interaction, text: str):

    user_id = str(interaction.user.id)

    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO profiles (user_id, about)
                VALUES (%s, %s)
                ON CONFLICT (user_id)
                DO UPDATE SET about = %s
            """, (user_id, text, text))
            conn.commit()

        await interaction.response.send_message("✅ About updated!", ephemeral=True)

    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


# -------------------------------
# /setfav
# -------------------------------

@bot.tree.command(name="setfav")
@app_commands.describe(card_id="Card ID to set as favourite")
async def setfav_cmd(interaction: discord.Interaction, card_id: int):

    user_id = str(interaction.user.id)

    try:
        with conn.cursor() as cur:
            # check if user owns card
            cur.execute(
                "SELECT 1 FROM inventory WHERE user_id=%s AND card_id=%s",
                (user_id, card_id)
            )
            if not cur.fetchone():
                await interaction.response.send_message("❌ You don't own this card.", ephemeral=True)
                return

            # save favourite
            cur.execute("""
                INSERT INTO profiles (user_id, fav_card_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id)
                DO UPDATE SET fav_card_id = %s
            """, (user_id, card_id, card_id))
            conn.commit()

        await interaction.response.send_message("🎴 Favourite card set!", ephemeral=True)

    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

# -------------------------------
# on ready
# -------------------------------

@bot.event
async def on_ready():
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reminder_settings (
                user_id TEXT,
                command TEXT,
                enabled BOOLEAN DEFAULT TRUE,
                PRIMARY KEY (user_id, command)
            );
        """)
        conn.commit()

    print("Bot is ready!")

# -------------------------------
# reminder loop
# -------------------------------
            
async def reminder_loop():
    await bot.wait_until_ready()

    while True:
        now = int(time.time())

        try:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id, command, end_time, channel_id FROM reminders")
                reminders = cur.fetchall()

                for user_id, command, end_time, channel_id in reminders:
                    if now >= end_time:

                        # 🔹 Check if reminder is enabled
                        cur.execute(
                            "SELECT enabled FROM reminder_settings WHERE user_id=%s AND command=%s",
                            (user_id, command)
                        )
                        res = cur.fetchone()
                        enabled = res[0] if res else True

                        channel = bot.get_channel(int(channel_id))

                        # 🔹 Only send if enabled
                        if enabled and isinstance(channel, (discord.TextChannel, discord.Thread)):
                            await channel.send(f"<@{user_id}> your **{command}** is ready!")

                        # 🔹 Delete reminder after processing
                        cur.execute(
                            "DELETE FROM reminders WHERE user_id=%s AND command=%s",
                            (user_id, command)
                        )

                conn.commit()

        except Exception as e:
            conn.rollback()  # 🔥 prevents DB lock
            print(f"Reminder loop error: {e}")

        await asyncio.sleep(30)
        

# -------------------------------
# Run bot
# -------------------------------
token = os.getenv("TOKEN")
if not token:
    raise ValueError("TOKEN missing")

bot.run(token)