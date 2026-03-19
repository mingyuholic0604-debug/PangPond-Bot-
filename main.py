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
    now = int(time.time())

    last = get_cooldown(user, "drop")
    if now - last < 600:
        remaining = 600 - (now - last)
        await interaction.response.send_message(
            f"⏳ Wait {int(remaining//60)}m {int(remaining%60)}s"
        )
        return

    card = random.choice(cards)

    cur.execute(
    """
    INSERT INTO inventory (user_id, card_id, name, era, group_name, rarity)
    VALUES (%s, %s, %s, %s, %s, %s)
    """,
    (user, card["id"], card["name"], card["era"], card["group"], card["rarity"])
)
    conn.commit()

    set_cooldown(user, "drop", now)

    embed = discord.Embed(
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
    now = time.time()

    embed = discord.Embed(title="⏳ Your Cooldowns", color=discord.Color.orange())

    # define cooldown durations in seconds
    cooldown_times = {"drop":600,"daily":86400,"weekly":604800,"bake":3600}

    for cmd, duration in cooldown_times.items():
        if user in cooldowns.get(cmd, {}):
            remaining = int(duration - (now - cooldowns[cmd][user]))
            if remaining > 0:
                if remaining >= 3600:  # hours
                    h = remaining // 3600
                    m = (remaining % 3600) // 60
                    s = remaining % 60
                    embed.add_field(name=cmd, value=f"{h}h {m}m {s}s", inline=False)
                else:
                    m = remaining // 60
                    s = remaining % 60
                    embed.add_field(name=cmd, value=f"{m}m {s}s", inline=False)
            else:
                embed.add_field(name=cmd, value="Ready", inline=False)
        else:
            embed.add_field(name=cmd, value="Ready", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

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
    action="add or remove",
    type="boba/cake/card",
    amount="Amount of currency or card ID"
)
async def handle_cmd(interaction: discord.Interaction, user: discord.User, action: str, type: str, amount: str):
    # ensure interaction.user is a Member (has roles)
    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("❌ Could not verify your roles.", ephemeral=True)
        return

    # check for mod role
    if not any(role.name.lower() == "mod" for role in interaction.user.roles):
        await interaction.response.send_message("❌ You are not authorized to use this command.", ephemeral=True)
        return

    target_id = str(user.id)

    # -------------------------------
    # Handle currency
    # -------------------------------
    if type.lower() in ["boba", "cake"]:
        amt = int(amount)
        if action.lower() == "add":
            cur.execute(f"UPDATE users SET {type.lower()} = {type.lower()} + %s WHERE user_id = %s", (amt, target_id))
        elif action.lower() == "remove":
            cur.execute(f"UPDATE users SET {type.lower()} = {type.lower()} - %s WHERE user_id = %s", (amt, target_id))
        else:
            await interaction.response.send_message("❌ Invalid action. Use add or remove.", ephemeral=True)
            return
        conn.commit()
        await interaction.response.send_message(f"✅ {action.title()}ed {amt} {type} for {user.mention}")

    # -------------------------------
    # Handle cards
    # -------------------------------
    elif type.lower() == "card":
        card_id = int(amount)
        if action.lower() == "add":
            # get card info from your cards list
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

        elif action.lower() == "remove":
            cur.execute("DELETE FROM inventory WHERE user_id=%s AND card_id=%s", (target_id, card_id))
            conn.commit()
            await interaction.response.send_message(f"✅ Card ID {card_id} removed from {user.mention}")
        else:
            await interaction.response.send_message("❌ Invalid action. Use add or remove.", ephemeral=True)

    else:
        await interaction.response.send_message("❌ Invalid type. Use boba, cake, or card.", ephemeral=True)

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