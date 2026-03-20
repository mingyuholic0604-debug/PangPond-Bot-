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

DROP_COOLDOWN = 600  # 10 min
cooldowns = {"drop": {}, "bake": {}}

@bot.tree.command(name="drop")
async def drop_cmd(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    now = int(time.time())

    # Check cooldown
    last = cooldowns["drop"].get(user_id, 0)
    remaining = DROP_COOLDOWN - (now - last)
    if remaining > 0:
        await interaction.response.send_message(
            f"⏱ Drop cooldown: {remaining//10}m left", ephemeral=True
        )
        return

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

            # count copies of this card the user has
            cur.execute(
                "SELECT COUNT(*) FROM inventory WHERE user_id=%s AND card_id=%s",
                (user_id, card["id"])
            )
            copies = cur.fetchone()[0]

        # update cooldown
        cooldowns["drop"][user_id] = now

        # rarity emojis
        rarity_str = "🍞" * int(card.get("rarity", 1))

        # create embed
        embed = discord.Embed(
            title="🎴 You got a new card!",
            description=f"**{card['name']}** (ID: {card['id']})\n📀 {card['era']} | 👥 {card['group']} | {rarity_str}",
            color=discord.Color.orange()
        )

        # set card image if available
        if "image" in card:
            embed.set_image(url=card["image"])

        # set footer with copies count
        embed.set_footer(text=f"You have {copies} copies of this card.")

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


# -------------------------------
# /inventory (PAGED)
# -------------------------------

from discord.ui import View, Button
from discord import app_commands
import discord

@bot.tree.command(name="inventory")
@app_commands.describe(user="View another user's inventory (optional)")
async def inventory_cmd(interaction: discord.Interaction, user: discord.Member | None = None):

    if user is None:
        target = interaction.user
    else:
        target = user

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

        # Pagination
        per_page = 5
        total_pages = (len(data) - 1) // per_page + 1

        def get_embed(page):
            embed = discord.Embed(
                title=f"🎒 {target.name}'s Inventory (Page {page+1}/{total_pages})",
                color=discord.Color.orange()
            )

            start, end = page * per_page, (page + 1) * per_page
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
            async def prev(self, interaction2, button):
                if self.page > 0:
                    self.page -= 1
                    await interaction2.response.edit_message(embed=get_embed(self.page), view=self)

            @discord.ui.button(label="➡️", style=discord.ButtonStyle.gray)
            async def next(self, interaction2, button):
                if self.page < total_pages - 1:
                    self.page += 1
                    await interaction2.response.edit_message(embed=get_embed(self.page), view=self)

        await interaction.response.send_message(embed=get_embed(0), view=InventoryView())

    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)
        

# -------------------------------
# daily command
# -------------------------------

@bot.tree.command(name="daily")
async def daily_cmd(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    now = int(time.time())

    COOLDOWN = 86400
    last = cooldowns.get("daily", {}).get(user_id, 0)
    remaining = COOLDOWN - (now - last)

    if remaining > 0:
        await interaction.response.send_message(
            f"⏱ Daily cooldown: {remaining//3600}h {(remaining%3600)//60}m"
        )
        return

    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET boba = boba + 2000, cake = cake + 10 WHERE user_id = %s",
                (user_id,)
            )
            conn.commit()

        cooldowns.setdefault("daily", {})[user_id] = now

        embed = discord.Embed(
            title="🎁 Daily Reward!",
            description="💰 **2000 boba**\n🍰 **10 cake coins**",
            color=discord.Color.green()
        )
        embed.set_image(url="https://media2.giphy.com/media/v1.Y2lkPTZjMDliOTUydmlrODh6YXlxcWI4dGhhbXl3czZpejVmZzVnOXEydDN2dmswdmM5aSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/uKKSAhC0gb5roHsy9v/giphy.gif")
        embed.set_footer(text=f"Claimed by {interaction.user.name}")

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}")

        

# -------------------------------
# weekly 
# -------------------------------

@bot.tree.command(name="weekly")
async def weekly_cmd(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    now = int(time.time())

    COOLDOWN = 604800
    last = cooldowns.get("weekly", {}).get(user_id, 0)
    remaining = COOLDOWN - (now - last)

    if remaining > 0:
        await interaction.response.send_message(
            f"⏱ Weekly cooldown: {remaining//86400}d {(remaining%86400)//3600}h"
        )
        return

    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET boba = boba + 5000, cake = cake + 50 WHERE user_id = %s",
                (user_id,)
            )
            conn.commit()

        cooldowns.setdefault("weekly", {})[user_id] = now

        embed = discord.Embed(
            title="🎉 Weekly Reward!",
            description="💰 **5000 boba**\n🍰 **50 cake coins**",
            color=discord.Color.purple()
        )
        embed.set_image(url="https://media0.giphy.com/media/v1.Y2lkPTZjMDliOTUyY2xhcHA5cDM1aWhkcGl5MDR1MzY1bmZuNGF6aXMxeWl0dTM0ODNjMyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/5wKuwXycuNfl0VEOgI/giphy.gif")
        embed.set_footer(text=f"Claimed by {interaction.user.name}")

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}")
            


# -------------------------------
# /bake
# -------------------------------

@bot.tree.command(name="bake")
async def bake_cmd(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    now = int(time.time())

    BAKE_COOLDOWN = 1800  # 30 min
    last = cooldowns["bake"].get(user_id, 0)
    remaining = BAKE_COOLDOWN - (now - last)

    if remaining > 0:
        await interaction.response.send_message(
            f"⏱ Bake cooldown: {remaining//60}m {remaining%60}s left"
        )
        return

    boba_reward = random.randint(200, 800)
    cake_reward = random.randint(1, 5)

    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET boba = boba + %s, cake = cake + %s WHERE user_id = %s",
                (boba_reward, cake_reward, user_id)
            )
            conn.commit()

        cooldowns["bake"][user_id] = now

        embed = discord.Embed(
            title="🎂 Baking Success!",
            description=f"💰 **{boba_reward} boba**\n🍰 **{cake_reward} cake coins**",
            color=discord.Color.orange()
        )
        embed.set_image(url="https://media4.giphy.com/media/v1.Y2lkPTZjMDliOTUyZGZnMDcwM2o3Zmp6Y2tndHFweHZydTZtMmU1MzE2bHBrc201cjJlZiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/LMuPuB2jQkmgX59vWX/giphy.gif")
        
        embed.set_footer(text=f"{interaction.user.name} just baked!")

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}")

# -------------------------------
# cooldowns
# -------------------------------

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

# -------------------------------
# reminder 
# -------------------------------
from discord.ui import View, Button

@bot.tree.command(name="reminders")
async def reminders_cmd(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT command, end_time FROM reminders WHERE user_id=%s",
                (user_id,)
            )
            data = cur.fetchall()

        if not data:
            await interaction.response.send_message("❌ You have no active reminders.", ephemeral=True)
            return

        # Format list
        desc = ""
        now = int(time.time())

        for command, end_time in data:
            remaining = max(0, end_time - now)
            desc += f"**{command}** → {remaining//60}m {remaining%60}s\n"

        embed = discord.Embed(
            title="🔔 Your Reminders",
            description=desc,
            color=discord.Color.orange()
        )

        # Buttons
        class ReminderView(View):
            def __init__(self):
                super().__init__(timeout=120)

                for command, _ in data:
                    self.add_item(ReminderButton(command))

        class ReminderButton(Button):
            def __init__(self, command):
                super().__init__(label=f"Toggle {command}", style=discord.ButtonStyle.gray)
                self.command = command

            async def callback(self, interaction):
                try:
                    with conn.cursor() as cur:
                        # delete reminder (toggle OFF)
                        cur.execute(
                            "DELETE FROM reminders WHERE user_id=%s AND command=%s",
                            (str(interaction.user.id), self.command)
                        )
                        conn.commit()

                    await interaction.response.send_message(
                        f"❌ {self.command} reminder turned OFF",
                        ephemeral=True
                    )

                except Exception as e:
                    conn.rollback()
                    await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

        await interaction.response.send_message(embed=embed, view=ReminderView())

    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)
         
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

# on ready

@bot.event
async def on_ready():
    print(f"{bot.user} is online!")
    await bot.tree.sync()  # sync commands
    bot.loop.create_task(reminder_loop())  # start the reminder loop

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
                        channel = bot.get_channel(int(channel_id))

                        if isinstance(channel, (discord.TextChannel, discord.Thread)):
                            await channel.send(f"<@{user_id}> your **{command}** is ready!")

                        cur.execute(
                            "DELETE FROM reminders WHERE user_id=%s AND command=%s",
                            (user_id, command)
                        )

                conn.commit()

        except Exception as e:
            conn.rollback()  # 🔥 VERY IMPORTANT
            print(f"Reminder loop error: {e}")

        await asyncio.sleep(30)
        
        

# -------------------------------
# Run bot
# -------------------------------
token = os.getenv("TOKEN")
if not token:
    raise ValueError("TOKEN missing")

bot.run(token)