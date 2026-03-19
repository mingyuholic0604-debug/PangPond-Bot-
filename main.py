import discord
from discord.ext import commands
from discord import app_commands
import psycopg2
import os
import random
import time
import asyncio

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

@bot.tree.command(name="drop")
async def drop(interaction: discord.Interaction):
    user = str(interaction.user.id)
    now = time.time()

    if user in cooldowns["drop"]:
        remaining = 600 - (now - cooldowns["drop"][user])
        if remaining > 0:
            await interaction.response.send_message(
                f"⏳ Wait {int(remaining//60)}m {int(remaining%60)}s",
                ephemeral=True
            )
            return

    card = random.choice(cards)
    cooldowns["drop"][user] = now

    cur.execute(
        "INSERT INTO inventory VALUES (%s, %s, %s, %s, %s, %s)",
        (user, card["id"], card["name"], card["era"], card["group"], card["rarity"])
    )
    conn.commit()

    embed = discord.Embed(
        title="Fresh card from PangPond's oven!",
        description=(
            f"🎴 **{card['name']}** (ID: {card['id']})\n"
            f"📀 {card['era']} | 👥 {card['group']}\n"
            f"🍞 {'🍞' * int(card['rarity'])}"
        ),
        color=discord.Color.orange()
    )

    await interaction.response.send_message(embed=embed)

# -------------------------------
# /inventory (PAGED)
# -------------------------------
@bot.tree.command(name="inventory")
async def inventory(interaction: discord.Interaction, page: int = 1):
    user = str(interaction.user.id)

    cur.execute("SELECT * FROM inventory WHERE user_id = %s", (user,))
    data = cur.fetchall()

    if not data:
        await interaction.response.send_message("No cards!", ephemeral=True)
        return

    per_page = 5
    start = (page - 1) * per_page
    end = start + per_page

    page_data = data[start:end]

    desc = ""
    for c in page_data:
        desc += f"🎴 {c[2]} (ID: {c[1]})\n📀 {c[3]} | 👥 {c[4]}\n🍞 {'🍞'*c[5]}\n\n"

    embed = discord.Embed(
        title=f"🎒 Inventory (Page {page})",
        description=desc,
        color=discord.Color.orange()
    )

    await interaction.response.send_message(embed=embed)

# daily command 
@bot.tree.command(name="daily")
async def daily(interaction: discord.Interaction):
    user = str(interaction.user.id)
    now = int(time.time())

    last = get_cooldown(user, "daily")
    if now - last < 86400:
        remaining = 86400 - (now - last)
        await interaction.response.send_message(
            f"⏳ Come back in {remaining//3600}h",
            ephemeral=True
        )
        return

    cur.execute(
        "UPDATE users SET boba = boba + 2000, cake = cake + 10 WHERE user_id=%s",
        (user,)
    )
    conn.commit()

    set_cooldown(user, "daily", now)

    embed = discord.Embed(
        description="🎁 You got **2000 Boba 🧋 + 10 Cake 🍰**!",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed)

# weekly 

@bot.tree.command(name="weekly")
async def weekly(interaction: discord.Interaction):
    user = str(interaction.user.id)
    now = int(time.time())

    last = get_cooldown(user, "weekly")
    if now - last < 604800:
        remaining = 604800 - (now - last)
        await interaction.response.send_message(
            f"⏳ Come back in {remaining//86400} days",
            ephemeral=True
        )
        return

    cur.execute(
        "UPDATE users SET boba = boba + 5000, cake = cake + 50 WHERE user_id=%s",
        (user,)
    )
    conn.commit()

    set_cooldown(user, "weekly", now)

    embed = discord.Embed(
        description="🎁 You got **5000 Boba 🧋 + 50 Cake 🍰**!",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed)

# bake
@bot.tree.command(name="bake")
async def bake(interaction: discord.Interaction):
    user = str(interaction.user.id)
    now = int(time.time())

    last = get_cooldown(user, "bake")
    if now - last < 3600:
        remaining = 3600 - (now - last)
        await interaction.response.send_message(
            f"⏳ Wait {remaining//60}m",
            ephemeral=True
        )
        return

    reward = random.randint(200, 800)

    cur.execute(
        "UPDATE users SET boba = boba + %s WHERE user_id=%s",
        (reward, user)
    )
    conn.commit()

    set_cooldown(user, "bake", now)

    embed = discord.Embed(
        description=f"🍳 You earned **{reward} Boba 🧋**!",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed)

# cooldowns

@bot.tree.command(name="cooldowns")
async def cooldowns_cmd(interaction: discord.Interaction):
    user = str(interaction.user.id)
    now = int(time.time())

    cmds = {
        "drop": 600,
        "bake": 3600,
        "daily": 86400,
        "weekly": 604800
    }

    desc = ""

    for cmd, cd in cmds.items():
        last = get_cooldown(user, cmd)
        remaining = cd - (now - last)

        if remaining > 0:
            desc += f"⏳ {cmd}: {remaining}s\n"
        else:
            desc += f"✅ {cmd}: Ready\n"

    embed = discord.Embed(
        title="Cooldowns",
        description=desc,
        color=discord.Color.orange()
    )

    await interaction.response.send_message(embed=embed)

# reminder 

@bot.tree.command(name="reminder")
async def reminder(interaction: discord.Interaction, command: str):
    user = str(interaction.user.id)
    now = int(time.time())

    durations = {
        "drop": 600,
        "bake": 3600,
        "daily": 86400,
        "weekly": 604800
    }

    if command not in durations:
        await interaction.response.send_message("Invalid command", ephemeral=True)
        return

    last = get_cooldown(user, command)
    end_time = last + durations[command]

    cur.execute(
        "INSERT INTO reminders VALUES (%s,%s,%s,%s)",
        (user, command, end_time, str(interaction.channel.id))
    )
    conn.commit()

    await interaction.response.send_message(
        f"🔔 Reminder set for {command}!"
    )

# sync

@bot.tree.command(name="sync")
async def sync(interaction: discord.Interaction):
    await bot.tree.sync()
    await interaction.response.send_message("✅ Synced!")
    
# on ready

@bot.event
async def on_ready():
    print(f"{bot.user} is online!")
    bot.loop.create_task(reminder_loop())

async def reminder_loop():
    while True:
        now = int(time.time())

        cur.execute("SELECT * FROM reminders")
        data = cur.fetchall()

        for r in data:
            user_id, command, end_time, channel_id = r

            if now >= end_time:
                channel = bot.get_channel(int(channel_id))
                if channel:
                    await channel.send(f"<@{user_id}> your **{command}** is ready!")

                cur.execute(
                    "DELETE FROM reminders WHERE user_id=%s AND command=%s",
                    (user_id, command)
                )
                conn.commit()

        await asyncio.sleep(30)

# -------------------------------
# Run bot
# -------------------------------
token = os.getenv("TOKEN")
if not token:
    raise ValueError("TOKEN missing")

bot.run(token)