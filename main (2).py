import discord
from discord.ext import commands
from discord import app_commands
from discord.app_commands import CommandOnCooldown, checks
import random
import json
import os
from flask import Flask
from threading import Thread

# -------------------------------
# Keep-alive server
# -------------------------------
app = Flask("")
@app.route("/")
def home():
    return "PangPond Bot is alive!"
def run():
    app.run(host="0.0.0.0", port=8080)
Thread(target=run).start()

# -------------------------------
# Bot setup
# -------------------------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------------------
# File names for persistence
# -------------------------------
USER_DATA_FILE = "user_data.json"
INVENTORY_FILE = "inventory.json"

# -------------------------------
# Data storage
# -------------------------------
user_data = {}
inventory = {}

# -------------------------------
# Persistence functions
# -------------------------------
def load_data():
    global user_data, inventory
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, "r") as f:
            user_data = json.load(f)
        user_data = {str(k): v for k, v in user_data.items()}  # ensure string keys
    if os.path.exists(INVENTORY_FILE):
        with open(INVENTORY_FILE, "r") as f:
            inventory = json.load(f)
        inventory = {str(k): v for k, v in inventory.items()}

def save_data():
    with open(USER_DATA_FILE, "w") as f:
        json.dump(user_data, f)
    with open(INVENTORY_FILE, "w") as f:
        json.dump(inventory, f)

# -------------------------------
# Card definitions
# -------------------------------
cards = [
    {"name": "Kant", "era": "The Heart Killers", "group": "First Kanaphan", "rarity": 2, "image": "https://link-to-kant-image.png"},
    {"name": "Bison", "era": "The Heart Killers", "group": "Khaotung Thanawat", "rarity": 2, "image": "https://link-to-bison-image.png"},
    {"name": "Fadel", "era": "The Heart Killers", "group": "Joong Archen", "rarity": 3, "image": "https://link-to-fadel-image.png"},
    {"name": "Style", "era": "The Heart Killers", "group": "Dunk Natachai", "rarity": 3, "image": "https://link-to-style-image.png"}
]

# -------------------------------
# On ready
# -------------------------------
@bot.event
async def on_ready():
    load_data()  # force-load saved data before syncing commands
    synced = await bot.tree.sync()  # global slash command sync
    print(f"{bot.user} is online and {len(synced)} commands synced globally!")

# -------------------------------
# /start
# -------------------------------
@bot.tree.command(name="start", description="Start collecting cards with PangPond Bot")
async def start(interaction: discord.Interaction):
    user = str(interaction.user.id)
    if user in user_data:
        await interaction.response.send_message("☕ PangPond already opened a cafe account for you!")
        return

    user_data[user] = {"boba": 200, "cake": 0}
    inventory[user] = []
    save_data()

    embed = discord.Embed(
        title="🍞 Welcome to PangPond Cafe!",
        description="You received **200 Boba 🧋** to start your collection!\nUse `/drop` to collect your first card.",
        color=0xFFD580
    )
    await interaction.response.send_message(embed=embed)

# -------------------------------
# /balance
# -------------------------------
@bot.tree.command(name="balance", description="Check your PangPond cafe balance")
async def balance(interaction: discord.Interaction):
    user = str(interaction.user.id)
    if user not in user_data:
        await interaction.response.send_message("🍞 Use `/start` first!")
        return

    boba = user_data[user]["boba"]
    cake = user_data[user]["cake"]

    embed = discord.Embed(title="☕ PangPond Cafe Wallet", color=0xFFD580)
    embed.add_field(name="🧋 Boba", value=str(boba), inline=True)
    embed.add_field(name="🍰 Cake Coins", value=str(cake), inline=True)
    await interaction.response.send_message(embed=embed)

# -------------------------------
# /drop (10 min cooldown)
# -------------------------------
@bot.tree.command(name="drop", description="PangPond drops a fresh card from the oven (free!)")
@checks.cooldown(1, 600, key=lambda i: i.user.id)  # 10 min per user
async def drop(interaction: discord.Interaction):
    user = str(interaction.user.id)
    if user not in user_data:
        await interaction.response.send_message("🍞 Start your cafe journey first with `/start`!")
        return

    cards_pool = (
        [card for card in cards if card["rarity"] == 1] * 50 +
        [card for card in cards if card["rarity"] == 2] * 30 +
        [card for card in cards if card["rarity"] == 3] * 15 +
        [card for card in cards if card["rarity"] == 4] * 5
    )

    card = random.choice(cards_pool)
    bread = "🍞" * card["rarity"]
    inventory[user].append(card)
    save_data()

    embed = discord.Embed(title="🎴 Fresh card from PangPond's oven!", color=0xFFD580)
    embed.add_field(name="🍓 Name", value=card["name"], inline=True)
    embed.add_field(name="📀 Era", value=card["era"], inline=True)
    embed.add_field(name="👥 Group", value=card["group"], inline=True)
    embed.add_field(name="🍞 Rarity", value=bread, inline=True)
    embed.set_thumbnail(url=card["image"])
    await interaction.response.send_message(embed=embed)

@drop.error
async def drop_error(interaction: discord.Interaction, error):
    if isinstance(error, CommandOnCooldown):
        await interaction.response.send_message(
            f"⏳ You just pulled a card! Try again in {round(error.retry_after/60)} minutes."
        )

# -------------------------------
# /inventory
# -------------------------------
@bot.tree.command(name="inventory", description="See all the cards you collected in PangPond Cafe")
async def inventory_cmd(interaction: discord.Interaction):
    user = str(interaction.user.id)
    if user not in inventory or len(inventory[user]) == 0:
        await interaction.response.send_message("🍞 You haven’t collected any cards yet! Use `/drop` to get your first card.")
        return

    embed = discord.Embed(title="🎴 Your PangPond Collection", color=0xFFD580)
    for card in inventory[user]:
        bread = "🍞" * card["rarity"]
        embed.add_field(
            name=card["name"],
            value=f"📀 Era: {card['era']}\n👥 Group: {card['group']}\n🍞 Rarity: {bread}\n[Image Link]({card['image']})",
            inline=False
        )
    await interaction.response.send_message(embed=embed)

# -------------------------------
# /daily (24h cooldown, 200 Boba)
# -------------------------------
@bot.tree.command(name="daily", description="Collect your daily reward!")
@checks.cooldown(1, 86400, key=lambda i: i.user.id)
async def daily(interaction: discord.Interaction):
    user = str(interaction.user.id)
    if user not in user_data:
        await interaction.response.send_message("🍞 Use `/start` first!")
        return
    user_data[user]["boba"] += 200
    save_data()

    embed = discord.Embed(title="🌞 Daily Reward Collected!", description="You received **200 🧋 Boba**!", color=0xFFD580)
    await interaction.response.send_message(embed=embed)

@daily.error
async def daily_error(interaction: discord.Interaction, error):
    if isinstance(error, CommandOnCooldown):
        await interaction.response.send_message(f"⏳ You already claimed your daily reward! Try again in {round(error.retry_after/3600,1)} hours.")

# -------------------------------
# /weekly (7 days cooldown, 500 Boba)
# -------------------------------
@bot.tree.command(name="weekly", description="Collect your weekly reward!")
@checks.cooldown(1, 604800, key=lambda i: i.user.id)
async def weekly(interaction: discord.Interaction):
    user = str(interaction.user.id)
    if user not in user_data:
        await interaction.response.send_message("🍞 Use `/start` first!")
        return
    user_data[user]["boba"] += 500
    save_data()

    embed = discord.Embed(title="🎉 Weekly Reward Collected!", description="You received **500 🧋 Boba**!", color=0xFFD580)
    await interaction.response.send_message(embed=embed)

@weekly.error
async def weekly_error(interaction: discord.Interaction, error):
    if isinstance(error, CommandOnCooldown):
        await interaction.response.send_message(f"⏳ You already claimed your weekly reward! Try again in {round(error.retry_after/3600/24,1)} days.")

# -------------------------------
# /bake (1h cooldown, 20-100 Boba)
# -------------------------------
@bot.tree.command(name="bake", description="Bake something and earn Boba!")
@checks.cooldown(1, 3600, key=lambda i: i.user.id)
async def bake(interaction: discord.Interaction):
    user = str(interaction.user.id)
    if user not in user_data:
        await interaction.response.send_message("🍞 Use `/start` first!")
        return

    boba_reward = random.randint(20,100)
    user_data[user]["boba"] += boba_reward
    save_data()

    embed = discord.Embed(title="🥐 You baked something delicious!", description=f"You earned **{boba_reward} 🧋 Boba**!", color=0xFFD580)
    await interaction.response.send_message(embed=embed)

@bake.error
async def bake_error(interaction: discord.Interaction, error):
    if isinstance(error, CommandOnCooldown):
        await interaction.response.send_message(f"⏳ You are still baking! Try again in {round(error.retry_after/60)} minutes.")

# -------------------------------
# Run bot
# -------------------------------
import os
bot.run(os.getenv("TOKEN"))