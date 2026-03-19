import discord
from discord.ext import commands
from discord import app_commands
import psycopg2
import os
import random
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
cooldowns = {"drop": {}}

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
        title="TEST NEW EMBED",
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

# -------------------------------
# Run bot
# -------------------------------
token = os.getenv("TOKEN")
if not token:
    raise ValueError("TOKEN missing")

bot.run(token)