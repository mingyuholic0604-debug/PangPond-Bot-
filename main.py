import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
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
async def drop_cmd(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    try:
        with conn.cursor() as cur:
            # pick a random card
            card = random.choice(cards)

            # insert into inventory
            cur.execute(
                "INSERT INTO inventory (user_id, card_id, name, era, group_name, rarity) VALUES (%s,%s,%s,%s,%s,%s)",
                (user_id, card["id"], card["name"], card["era"], card["group"], card["rarity"])
            )
            conn.commit()

        # build rarity string safely
        rarity_str = "🍞" * int(card.get("rarity", 1))

        # create embed with card image
        embed = discord.Embed(
            title=f"🎴 You got a new card!",
            description=f"**{card['name']}** (ID: {card['id']})\n📀 {card['era']} | 👥 {card['group']} | {rarity_str}",
            color=discord.Color.orange()
        )

        # set card image if available
        if "image" in card:
            embed.set_image(url=card["image"])

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

# -------------------------------
# /inventory (PAGED)
# -------------------------------


@bot.tree.command(name="inventory")
async def inventory_cmd(interaction: discord.Interaction):
    user = str(interaction.user.id)

    cur.execute("SELECT * FROM inventory WHERE user_id = %s ORDER BY card_id", (user,))
    cards_data = cur.fetchall()

    if not cards_data:
        embed = discord.Embed(
            title="🎒 Your Inventory",
            description="No cards yet! Use /drop to get cards.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
        return

    # pagination state
    page = 0
    per_page = 5  # cards per page
    total_pages = (len(cards_data) - 1) // per_page + 1

    def get_embed(page_num):
        embed = discord.Embed(
            title=f"🎒 Your Cards (Page {page_num+1}/{total_pages})",
            color=discord.Color.orange()
        )
        start = page_num * per_page
        end = start + per_page
        for card in cards_data[start:end]:
            embed.add_field(
                name=f"{card[2]} (ID: {card[1]})",
                value=f"📀 {card[3]}\n👥 {card[4]}\n🍞{'🍞'*card[5]}",
                inline=False
            )
        return embed

    # create buttons
    class InventoryView(View):
        def __init__(self):
            super().__init__(timeout=120)  # 2 minutes
            self.current_page = 0

        @discord.ui.button(label="⬅️", style=discord.ButtonStyle.gray)
        async def prev_button(self, interaction2: discord.Interaction, button: Button):
            if self.current_page > 0:
                self.current_page -= 1
                await interaction2.response.edit_message(embed=get_embed(self.current_page), view=self)

        @discord.ui.button(label="➡️", style=discord.ButtonStyle.gray)
        async def next_button(self, interaction2: discord.Interaction, button: Button):
            if self.current_page < total_pages - 1:
                self.current_page += 1
                await interaction2.response.edit_message(embed=get_embed(self.current_page), view=self)

    view = InventoryView()
    await interaction.response.send_message(embed=get_embed(page), view=view)
# -------------------------------
# daily command
# -------------------------------

@bot.tree.command(name="daily")
async def daily_cmd(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    now = int(time.time())
    cooldown_time = 86400  # 24 hours

    last_used = cooldowns.get("daily", {}).get(user_id, 0)
    remaining = cooldown_time - (now - last_used)

    if remaining > 0:
        await interaction.response.send_message(
            f"⏱ Daily cooldown: {remaining//3600}h {(remaining%3600)//60}m left",
            ephemeral=True
        )
        return

    try:
        with conn.cursor() as cur:
            # give 2000 boba + 10 cake coins
            cur.execute(
                "UPDATE users SET boba = boba + 2000, cake = cake + 10 WHERE user_id = %s",
                (user_id,)
            )
            conn.commit()

        # update cooldown
        cooldowns.setdefault("daily", {})[user_id] = now

        await interaction.response.send_message(
            "✅ You claimed your daily reward: **2000 boba + 10 cake coins**!", ephemeral=True
        )

    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

# weekly 

@bot.tree.command(name="weekly")
async def weekly_cmd(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    now = int(time.time())
    cooldown_time = 604800  # 7 days

    last_used = cooldowns.get("weekly", {}).get(user_id, 0)
    remaining = cooldown_time - (now - last_used)

    if remaining > 0:
        await interaction.response.send_message(
            f"⏱ Weekly cooldown: {remaining//86400}d {(remaining%86400)//3600}h left",
            ephemeral=True
        )
        return

    try:
        with conn.cursor() as cur:
            # give 5000 boba + 50 cake coins
            cur.execute(
                "UPDATE users SET boba = boba + 5000, cake = cake + 50 WHERE user_id = %s",
                (user_id,)
            )
            conn.commit()

        # update cooldown
        cooldowns.setdefault("weekly", {})[user_id] = now

        await interaction.response.send_message(
            "✅ You claimed your weekly reward: **5000 boba + 50 cake coins**!", ephemeral=True
        )

    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)
            


# -------------------------------
# /bake
# -------------------------------

@bot.tree.command(name="bake")
async def bake_cmd(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    # Generate random rewards
    boba_reward = random.randint(200, 800)
    cake_reward = random.randint(1, 5)

    try:
        with conn.cursor() as cur:
            # Add rewards to user
            cur.execute(
                "UPDATE users SET boba = boba + %s, cake = cake + %s WHERE user_id = %s",
                (boba_reward, cake_reward, user_id)
            )
            conn.commit()

        await interaction.response.send_message(
            f"🎂 You baked something delicious!\nYou earned **{boba_reward} boba** and **{cake_reward} cake coins**!",
            ephemeral=True
        )

    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

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
@app_commands.describe(command="Command to get reminded for")
async def reminder(interaction: discord.Interaction, command: str):
    user = str(interaction.user.id)
    channel_id = interaction.channel_id

    command = command.lower()
    cooldown_times = {
        "drop": 600,
        "daily": 86400,
        "weekly": 604800,
        "bake": 3600
    }

    if command not in cooldown_times:
        await interaction.response.send_message("❌ Invalid command. Use drop, daily, weekly, or bake.", ephemeral=True)
        return

    now = int(time.time())

    # calculate remaining cooldown properly
    if user in cooldowns[command]:
        remaining = cooldown_times[command] - (now - cooldowns[command][user])
        if remaining <= 0:
            await interaction.response.send_message(f"{command.capitalize()} is already ready! ✅", ephemeral=True)
            return
    else:
        await interaction.response.send_message(f"{command.capitalize()} is already ready! ✅", ephemeral=True)
        return

    # store reminder to fire exactly when cooldown ends
    end_time = now + remaining
    cur.execute(
        "INSERT INTO reminders (user_id, command, end_time, channel_id) VALUES (%s, %s, %s, %s)",
        (user, command, end_time, channel_id)
    )
    conn.commit()

    # reply with how long until the command is ready
    embed = discord.Embed(
        title=f"⏰ Reminder Set for {command.capitalize()}",
        description=f"I will ping you in this channel when it’s ready in **{int(remaining//60)}m {int(remaining%60)}s**",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed)
         

# /handle

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

# MENU 

from discord import app_commands

# Example fixed menu command with dropdown choices for Era and Group
@bot.tree.command(name="menu")
@app_commands.describe(
    filter_type="Choose filter type",
    filter_value="Pick value for the filter (optional)"
)
@app_commands.choices(
    filter_type=[
        app_commands.Choice(name="ID", value="id"),
        app_commands.Choice(name="Name", value="name"),
        app_commands.Choice(name="Era", value="era"),
        app_commands.Choice(name="Group", value="group")
    ]
)
async def menu_cmd(interaction: discord.Interaction, filter_type: app_commands.Choice[str], filter_value: str = None):
    # Determine which cards match
    filtered_cards = cards
    if filter_type.value == "id" and filter_value:
        filtered_cards = [c for c in cards if str(c["id"]) == filter_value]
    elif filter_type.value == "name" and filter_value:
        filtered_cards = [c for c in cards if filter_value.lower() in c["name"].lower()]
    elif filter_type.value == "era" and filter_value:
        filtered_cards = [c for c in cards if c["era"].lower() == filter_value.lower()]
    elif filter_type.value == "group" and filter_value:
        filtered_cards = [c for c in cards if c["group"].lower() == filter_value.lower()]

    if not filtered_cards:
        await interaction.response.send_message("❌ No cards found.", ephemeral=True)
        return

    # Pagination (left/right buttons)
    per_page = 5
    total_pages = (len(filtered_cards) - 1) // per_page + 1

    def get_embed(page):
        embed = discord.Embed(title=f"🎴 Card Menu (Page {page+1}/{total_pages})", color=discord.Color.orange())
        start, end = page*per_page, (page+1)*per_page
        for card in filtered_cards[start:end]:
            embed.add_field(
                name=f"{card['name']} (ID: {card['id']})",
                value=f"📀 {card['era']} |👥 {card['group']}\n{'🍞' * int(card.get('rarity', 1))}",
                inline=False
            )
        return embed

    from discord.ui import View, Button

    class MenuView(View):
        def __init__(self):
            super().__init__(timeout=120)
            self.page = 0

        @discord.ui.button(label="⬅️", style=discord.ButtonStyle.gray)
        async def prev(self, interaction2, button):
            if self.page > 0:
                self.page -= 1
                await interaction2.response.edit_message(embed=get_embed(self.page), view=self)

        @discord.ui.button(label="➡️", style=discord.ButtonStyle.gray)
        async def next(self, interaction2, button):
            if self.page < total_pages-1:
                self.page += 1
                await interaction2.response.edit_message(embed=get_embed(self.page), view=self)

    await interaction.response.send_message(embed=get_embed(0), view=MenuView())

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