import discord
from discord.ext import commands
from discord import app_commands
import psycopg2
import os
import random
import asyncio
import time

cooldowns = {
    "drop": {},
    "daily": {},
    "weekly": {},
    "bake": {}
}
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
    COOLDOWN = 600  # 10 minutes

    if user in cooldowns["drop"]:
        remaining = COOLDOWN - (now - cooldowns["drop"][user])
        if remaining > 0:
            embed = discord.Embed(
                title="⏳ Drop Cooldown",
                description=f"Wait **{int(remaining//60)}m {int(remaining%60)}s**",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return

    # Pick a card (your existing code)
    card = random.choice(cards)
    cur.execute(
        "INSERT INTO inventory (user_id, card_id, name, era, group_name, rarity) VALUES (%s,%s,%s,%s,%s,%s)",
        (user, card["id"], card["name"], card["era"], card["group"], card["rarity"])
    )
    conn.commit()

    cooldowns["drop"][user] = now  # update cooldown

    embed = discord.Embed(
    description=f"🎴 **{card['name']}** (ID: {card['id']})\n📀 {card['era']} | 👥 {card['group']}\n{'🍞' * int(card['rarity'])}",
    color=discord.Color.orange()
    )

    if "image" in card:
        embed.set_thumbnail(url=card["image"])
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
# daily command
# -------------------------------
@bot.tree.command(name="daily")
async def daily(interaction: discord.Interaction):
    user = str(interaction.user.id)
    now = time.time()
    COOLDOWN = 86400  # 24h

    if user in cooldowns["daily"]:
        remaining = COOLDOWN - (now - cooldowns["daily"][user])
        if remaining > 0:
            embed = discord.Embed(
                title="⏳ Daily Cooldown",
                description=f"Come back in **{int(remaining//3600)}h {int((remaining%3600)//60)}m**",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return

    reward_boba = 2000
    reward_cake = 10
    cur.execute(
        "UPDATE users SET boba = boba + %s, cake = cake + %s WHERE user_id = %s",
        (reward_boba, reward_cake, user)
    )
    conn.commit()

    cooldowns["daily"][user] = now

    embed = discord.Embed(
        title="🎁 Daily Reward",
        description=f"You got **{reward_boba} Boba** and **{reward_cake} Cake**!",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed)

# weekly 

@bot.tree.command(name="weekly")
async def weekly(interaction: discord.Interaction):
    user = str(interaction.user.id)
    now = time.time()
    COOLDOWN = 604800  # 7 days

    if user in cooldowns["weekly"]:
        remaining = COOLDOWN - (now - cooldowns["weekly"][user])
        if remaining > 0:
            embed = discord.Embed(
                title="⏳ Weekly Cooldown",
                description=f"Come back in **{int(remaining//86400)}d {int((remaining%86400)//3600)}h**",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return

    reward_boba = 5000
    reward_cake = 50
    cur.execute(
        "UPDATE users SET boba = boba + %s, cake = cake + %s WHERE user_id = %s",
        (reward_boba, reward_cake, user)
    )
    conn.commit()

    cooldowns["weekly"][user] = now

    embed = discord.Embed(
        title="🎁 Weekly Reward",
        description=f"You got **{reward_boba} Boba** and **{reward_cake} Cake**!",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed)

# BAKE
@bot.tree.command(name="bake")
async def bake(interaction: discord.Interaction):
    user = str(interaction.user.id)
    now = time.time()
    COOLDOWN = 3600  # 1 hour

    if user in cooldowns["bake"]:
        remaining = COOLDOWN - (now - cooldowns["bake"][user])
        if remaining > 0:
            embed = discord.Embed(
                title="⏳ Bake Cooldown",
                description=f"Wait **{int(remaining//60)}m {int(remaining%60)}s**",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return

    reward = random.randint(200, 800)
    cur.execute("UPDATE users SET boba = boba + %s WHERE user_id = %s", (reward, user))
    conn.commit()

    cooldowns["bake"][user] = now

    embed = discord.Embed(
        title="🍳 Baking Complete!",
        description=f"You earned **{reward} Boba 🧋**!",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed)

# cooldowns

@bot.tree.command(name="cooldowns")
async def cooldowns_cmd(interaction: discord.Interaction):
    user = str(interaction.user.id)
    now = time.time()

    # Cooldown durations in seconds
    cooldown_times = {
        "drop": 600,
        "daily": 86400,
        "weekly": 604800,
        "bake": 3600
    }

    embed = discord.Embed(
        title="⏱ Your Cooldowns",
        color=discord.Color.orange()
    )

    for cmd_name, duration in cooldown_times.items():
        if user in cooldowns[cmd_name]:
            remaining = int(duration - (now - cooldowns[cmd_name][user]))
            if remaining > 0:
                if remaining >= 86400:  # days
                    text = f"{remaining//86400}d {(remaining%86400)//3600}h"
                elif remaining >= 3600:  # hours
                    text = f"{remaining//3600}h {(remaining%3600)//60}m"
                elif remaining >= 60:  # minutes
                    text = f"{remaining//60}m {remaining%60}s"
                else:
                    text = f"{remaining}s"
            else:
                text = "Ready ✅"
        else:
            text = "Ready ✅"

        embed.add_field(name=cmd_name.capitalize(), value=text, inline=True)

    await interaction.response.send_message(embed=embed)

# reminder 

@bot.tree.command(name="reminder")
@app_commands.describe(command="Which command to get a reminder for")
async def reminder_cmd(interaction: discord.Interaction, command: str):
    user = str(interaction.user.id)
    now = time.time()

    if command not in cooldowns:
        await interaction.response.send_message(f"❌ Command `{command}` does not exist!", ephemeral=True)
        return

    if user not in cooldowns[command]:
        await interaction.response.send_message(f"✅ `{command}` is already ready!", ephemeral=True)
        return

    # calculate the end time of the cooldown
    duration = {"drop":600,"daily":86400,"weekly":604800,"bake":3600}[command]
    end_time = cooldowns[command][user] + duration

    # insert reminder into DB
    cur.execute(
        "INSERT INTO reminders (user_id, command, end_time, channel_id) VALUES (%s,%s,%s,%s)",
        (user, command, int(end_time), str(interaction.channel_id))
    )
    conn.commit()

    await interaction.response.send_message(f"✅ I will remind you when `{command}` is ready!", ephemeral=True)

# sync

@bot.tree.command(name="sync")
async def sync(interaction: discord.Interaction):
    await bot.tree.sync()
    await interaction.response.send_message("✅ Synced!")

# handle

@bot.tree.command(name="handle")
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
        app_commands.Choice(name="Cake", value="cake"),
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
    type_value = type.value      # "boba", "cake", "card"

    # handle currency
    if type_value in ["boba", "cake"]:
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

# pay
@bot.tree.command(name="pay")
@app_commands.describe(
    user="The user to pay",
    type="boba/cake/card",
    amount="Amount or card ID"
)
async def pay_cmd(interaction: discord.Interaction, user: discord.User, type: str, amount: str):
    sender = str(interaction.user.id)
    receiver = str(user.id)

    # Ensure user exists
    cur.execute("SELECT * FROM users WHERE user_id=%s", (sender,))
    if not cur.fetchone():
        await interaction.response.send_message("❌ You need to /start first.", ephemeral=True)
        return
    cur.execute("SELECT * FROM users WHERE user_id=%s", (receiver,))
    if not cur.fetchone():
        await interaction.response.send_message("❌ Recipient hasn't started yet.", ephemeral=True)
        return

    if type.lower() in ["boba", "cake"]:
        amt = int(amount)
        # check sender balance
        cur.execute(f"SELECT {type.lower()} FROM users WHERE user_id=%s", (sender,))
        balance = cur.fetchone()[0]
        if balance < amt:
            await interaction.response.send_message("❌ You don't have enough.", ephemeral=True)
            return
        # transfer
        cur.execute(f"UPDATE users SET {type.lower()} = {type.lower()} - %s WHERE user_id=%s", (amt, sender))
        cur.execute(f"UPDATE users SET {type.lower()} = {type.lower()} + %s WHERE user_id=%s", (amt, receiver))
        conn.commit()
        await interaction.response.send_message(f"✅ You sent {amt} {type} to {user.mention}")

    elif type.lower() == "card":
        card_id = int(amount)
        # check if sender has the card
        cur.execute("SELECT * FROM inventory WHERE user_id=%s AND card_id=%s", (sender, card_id))
        if not cur.fetchone():
            await interaction.response.send_message("❌ You don't have this card.", ephemeral=True)
            return
        # transfer
        cur.execute("UPDATE inventory SET user_id=%s WHERE user_id=%s AND card_id=%s", (receiver, sender, card_id))
        conn.commit()
        await interaction.response.send_message(f"✅ You sent card ID {card_id} to {user.mention}")
    else:
        await interaction.response.send_message("❌ Invalid type. Use boba, cake, or card.", ephemeral=True)

# gift

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

# on ready

@bot.event
async def on_ready():
    print(f"{bot.user} is online!")
    await bot.tree.sync()  # sync commands
    bot.loop.create_task(reminder_loop())  # start the reminder loop
    
# reminder loop

async def reminder_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = int(time.time())
        cur.execute("SELECT * FROM reminders")
        reminders = cur.fetchall()

        for r in reminders:
            user_id, command, end_time, channel_id = r

            # get channel
            channel = bot.get_channel(int(channel_id))

            # only send if channel exists and is a TextChannel or Thread
            if isinstance(channel, (discord.TextChannel, discord.Thread)):
                await channel.send(f"<@{user_id}> your **{command}** is ready!")

            # remove reminder from DB
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