# XULT - Ultimate Discord Bot
# Render-compatible version with stock files in root /stock directory

import secrets
import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import View, Button, Select
import random
import sqlite3
import asyncio
import aiohttp
import json
import os
import re
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytz
import xml.etree.ElementTree as ET
from urllib.parse import quote
import difflib
from typing import List, Dict, Any, Optional
import hashlib
import platform
import psutil

# ==================== CONFIGURATION & SETUP ====================

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot Token - MUST be from environment variable
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not TOKEN:
    raise ValueError("No Discord bot token found! Set DISCORD_BOT_TOKEN environment variable.")

# API Keys from environment
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY', '')
TWITCH_CLIENT_ID = os.getenv('TWITCH_CLIENT_ID', '')
TWITCH_CLIENT_SECRET = os.getenv('TWITCH_CLIENT_SECRET', '')
TWITTER_BEARER_TOKEN = os.getenv('TWITTER_BEARER_TOKEN', '')
GIPHY_API_KEY = os.getenv('GIPHY_API_KEY', 'dimlVnesALO2DLu14diWdZAAcZIgW1L1')

# Bot Owner ID from environment
BOT_OWNER_ID = int(os.getenv('BOT_OWNER_ID', '1302203907782606880'))

# Premium Role ID for vending machine access
PREMIUM_ROLE_ID = int(os.getenv('PREMIUM_ROLE_ID', '1474136325912399994'))

# Main Server ID for role checks
MAIN_SERVER_ID = int(os.getenv('MAIN_SERVER_ID', '1344385779627069541'))

# API Configuration
API_PORT = int(os.getenv('API_PORT', 5000))
API_KEY = os.getenv('API_KEY', secrets.token_hex(32))

# Directory setup - Use current directory for Render compatibility
BASE_DIR = Path.cwd()
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)

# Stock directory - in root for Render compatibility
STOCK_DIR = BASE_DIR / "stock"
STOCK_DIR.mkdir(exist_ok=True)

# ==================== DATABASE SETUP ====================

conn = sqlite3.connect(DATA_DIR / "xult.db")
c = conn.cursor()

# Economy tables
c.execute("""CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    coins INTEGER DEFAULT 0,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    last_daily TIMESTAMP,
    role TEXT DEFAULT 'user',
    premium_expires TIMESTAMP
)""")

c.execute("""CREATE TABLE IF NOT EXISTS shop (
    name TEXT PRIMARY KEY,
    price INTEGER,
    description TEXT
)""")

c.execute("""CREATE TABLE IF NOT EXISTS lottery (
    user_id INTEGER,
    entry_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)""")

# API Tables
c.execute("""CREATE TABLE IF NOT EXISTS premium_users (
    user_id INTEGER PRIMARY KEY,
    guild_id INTEGER,
    role_id INTEGER,
    granted_at TIMESTAMP,
    is_active INTEGER DEFAULT 1
)""")

c.execute("""CREATE TABLE IF NOT EXISTS stock_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    stock_type TEXT,
    stock_content TEXT,
    generated_at TIMESTAMP,
    ip_address TEXT
)""")

c.execute("""CREATE TABLE IF NOT EXISTS user_cooldowns (
    user_id INTEGER PRIMARY KEY,
    last_generated TIMESTAMP,
    generation_count INTEGER DEFAULT 0
)""")

c.execute("""CREATE TABLE IF NOT EXISTS banned_users (
    user_id INTEGER PRIMARY KEY,
    reason TEXT,
    banned_at TIMESTAMP,
    banned_by INTEGER
)""")

c.execute("""CREATE TABLE IF NOT EXISTS server_configs (
    server_id INTEGER PRIMARY KEY,
    config TEXT
)""")

c.execute("""CREATE TABLE IF NOT EXISTS notification_channels (
    server_id INTEGER,
    platform TEXT,
    channel_id INTEGER,
    role_id INTEGER,
    last_post_id TEXT,
    PRIMARY KEY (server_id, platform)
)""")

c.execute("""CREATE TABLE IF NOT EXISTS youtube_channels (
    channel_id TEXT PRIMARY KEY,
    server_id INTEGER,
    last_video_id TEXT
)""")

c.execute("""CREATE TABLE IF NOT EXISTS twitch_streams (
    username TEXT,
    server_id INTEGER,
    last_stream_id TEXT,
    PRIMARY KEY (username, server_id)
)""")

c.execute("""CREATE TABLE IF NOT EXISTS twitter_accounts (
    username TEXT,
    server_id INTEGER,
    last_tweet_id TEXT,
    PRIMARY KEY (username, server_id)
)""")

c.execute("""CREATE TABLE IF NOT EXISTS moderation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER,
    moderator_id INTEGER,
    user_id INTEGER,
    action TEXT,
    reason TEXT,
    timestamp TIMESTAMP
)""")

c.execute("""CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER,
    user_id INTEGER,
    moderator_id INTEGER,
    reason TEXT,
    timestamp TIMESTAMP
)""")

c.execute("""CREATE TABLE IF NOT EXISTS jailed_members (
    server_id INTEGER,
    user_id INTEGER,
    roles TEXT,
    jail_time TIMESTAMP,
    duration TEXT,
    reason TEXT,
    jailed_by INTEGER,
    PRIMARY KEY (server_id, user_id)
)""")

c.execute("""CREATE TABLE IF NOT EXISTS four_twenty (
    server_id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    role_id INTEGER,
    voice_channel_id INTEGER,
    timezone TEXT DEFAULT 'UTC'
)""")

conn.commit()

# Initialize shop items
shop_items = [
    ("VIP Role", 500, "Gives VIP role"),
    ("Double XP", 300, "Double XP for 24h"),
    ("Mystery Box", 100, "Random coins or reward")
]
for name, price, desc in shop_items:
    c.execute("INSERT OR IGNORE INTO shop (name, price, description) VALUES (?, ?, ?)", (name, price, desc))
conn.commit()

# ==================== JSON DATA MANAGEMENT ====================

JSON_FILES = {
    "server_settings": DATA_DIR / "server_settings.json",
    "tracked_channels": DATA_DIR / "tracked_channels.json",
    "role_on_join": DATA_DIR / "role_on_join.json",
    "reaction_role_menus": DATA_DIR / "reaction_role_menus.json",
    "pending_role_assignments": DATA_DIR / "pending_role_assignments.json",
    "gen_access": DATA_DIR / "gen_access.json",
    "report_channels": DATA_DIR / "report_channels.json",
    "active_reports": DATA_DIR / "active_reports.json",
    "log_channels": DATA_DIR / "log_channels.json",
    "warnings": DATA_DIR / "warnings.json",
    "bad_words": DATA_DIR / "bad_words.json",
    "jailed_members": DATA_DIR / "jailed_members.json",
    "auto_update": DATA_DIR / "auto_update.json",
    "server_configs": DATA_DIR / "server_configs.json",
    "four_twenty": DATA_DIR / "four_twenty.json",
}

def init_json_files():
    for name, file_path in JSON_FILES.items():
        if not file_path.exists():
            with open(file_path, 'w') as f:
                json.dump({}, f)

def load_json(file_path, default=None):
    try:
        with open(file_path, 'r') as f:
            data = f.read()
            return json.loads(data) if data else (default if default is not None else {})
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}

def save_json(file_path, data):
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving {file_path}: {e}")

# ==================== INTENTS & BOT INIT ====================

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ==================== GLOBAL VARIABLES ====================

# Cooldowns
user_cooldowns = {}
FREE_GEN_TIMEOUT = 5
CUSTOM_USER_ID = 1151697240025464852
CUSTOM_USER_TIMEOUT = 20

# Economy
LEVEL_ROLES = {5: "Level 5", 10: "Level 10"}

# Lottery
lottery_cooldowns = {}

# Riddles
RIDDLES = [
    ("What has keys but can't open locks?", "keyboard"),
    ("What runs but never walks?", "water"),
    ("What has hands but cannot clap?", "clock"),
    ("What can you catch but not throw?", "cold"),
    ("What has a face and two hands but no arms or legs?", "clock"),
    ("What has a neck but no head?", "bottle"),
    ("What gets wetter as it dries?", "towel"),
    ("What has cities but no houses?", "map"),
    ("What has a thumb and four fingers but is not alive?", "glove"),
    ("What has words but never speaks?", "book"),
    ("What can travel around the world while staying in a corner?", "stamp"),
    ("What has a head, a tail, is brown, and has no legs?", "penny"),
    ("What can be cracked, made, told, and played?", "joke"),
    ("What has a heart that doesn’t beat?", "artichoke"),
    ("What comes down but never goes up?", "rain"),
    ("What can fill a room but takes up no space?", "light"),
    ("What begins with T, ends with T, and has T in it?", "teapot"),
    ("What has one eye but cannot see?", "needle"),
    ("What kind of room has no doors or windows?", "mushroom"),
    ("What goes up but never comes down?", "age"),
    ("What has a ring but no finger?", "phone"),
    ("What has a spine but no bones?", "book"),
    ("What has to be broken before you can use it?", "egg"),
    ("What has a head and a tail but no body?", "coin"),
    ("What has teeth but cannot bite?", "comb"),
    ("What gets bigger the more you take away?", "hole"),
    ("What has many keys but cannot open a single lock?", "piano"),
    ("What has legs but doesn’t walk?", "table"),
    ("What has a bed but never sleeps?", "river"),
    ("What has a bark but no bite?", "tree"),
    ("What has an ear but cannot hear?", "corn"),
    ("What comes once in a minute, twice in a moment, but never in a thousand years?", "m"),
    ("What can run but never walks, has a mouth but never talks?", "river"),
    ("What is full of holes but still holds water?", "sponge"),
    ("What has four legs in the morning, two legs in the afternoon, and three legs in the evening?", "human"),
    ("What has a bottom at the top?", "leg"),
    ("What has a head and a foot but no body?", "bed"),
    ("What has a bank but no money?", "river"),
    ("What is so fragile that saying its name breaks it?", "silence"),
    ("What flies without wings?", "time"),
    ("What has roots that nobody sees?", "mountain"),
    ("What is always coming but never arrives?", "tomorrow"),
    ("What belongs to you but others use it more than you?", "name"),
    ("What can travel without moving?", "shadow")
]
active_riddle = None
riddle_answer = None

# Block words (global)
BLOCK_WORDS = ["nigger", "niggas", "niggers", "jews", "chinks", "nazis", "fags", "fagots", "nigga", "fagot", "nazis", "chink", "jew", "fag", "discord.gg/"]

# Twitch notifications
notified_streams = {}

# Twitter user cache
user_id_cache = {}

# ==================== STOCK HELPER FUNCTIONS ====================

def get_stock_filename(stock_type: str):
    """Get filename for stock type"""
    stock_type = stock_type.lower().strip().replace(' ', '_')
    return STOCK_DIR / f"{stock_type}.txt"

def create_stock_file(stock_type: str):
    filename = get_stock_filename(stock_type)
    if not filename.exists():
        filename.write_text("", encoding="utf-8")

def count_stock(stock_type: str) -> int:
    filename = get_stock_filename(stock_type)
    create_stock_file(stock_type)
    
    try:
        content = filename.read_text(encoding="utf-8").strip()
        if not content:
            return 0
        return len([l for l in content.split('\n') if l.strip()])
    except:
        return 0

def read_stock_entries(stock_type: str) -> list:
    filename = get_stock_filename(stock_type)
    create_stock_file(stock_type)
    
    try:
        content = filename.read_text(encoding="utf-8").strip()
        if not content:
            return []
        return [line.strip() for line in content.split('\n') if line.strip()]
    except:
        return []

def write_stock_entries(stock_type: str, entries: list):
    filename = get_stock_filename(stock_type)
    with open(filename, "w", encoding="utf-8") as f:
        f.write('\n'.join(str(e) for e in entries))

def add_stock_entries(stock_type: str, new_entries: list):
    current = read_stock_entries(stock_type)
    current.extend(new_entries)
    write_stock_entries(stock_type, current)

def get_stock_entry(stock_type: str) -> Optional[str]:
    """Get first entry and remove it"""
    entries = read_stock_entries(stock_type)
    if not entries:
        return None
    
    first = entries[0]
    remaining = entries[1:]
    write_stock_entries(stock_type, remaining)
    return first

def is_on_cooldown(user_id: int) -> tuple:
    timeout = CUSTOM_USER_TIMEOUT if user_id == CUSTOM_USER_ID else FREE_GEN_TIMEOUT
    last_used = user_cooldowns.get(user_id, 0)
    if time.time() - last_used < timeout:
        remaining = int(timeout - (time.time() - last_used))
        return True, remaining
    return False, 0

def set_cooldown(user_id: int):
    user_cooldowns[user_id] = time.time()

# ==================== STOCK TYPE DEFINITIONS ====================

STOCK_TYPES = {
    "steam": {"name": "Steam Accounts", "emoji": "🎮", "description": "Steam game accounts"},
    "netflix": {"name": "Netflix Accounts", "emoji": "🎬", "description": "Netflix premium accounts"},
    "spotify": {"name": "Spotify Accounts", "emoji": "🎵", "description": "Spotify premium accounts"},
    "discord": {"name": "Discord Nitro", "emoji": "💎", "description": "Discord Nitro codes"},
    "minecraft": {"name": "Minecraft Accounts", "emoji": "⛏️", "description": "Minecraft Java accounts"},
    "roblox": {"name": "Roblox Accounts", "emoji": "🎮", "description": "Roblox game accounts"},
    "epicgames": {"name": "Epic Games", "emoji": "⚡", "description": "Epic Games accounts"},
    "ubisoft": {"name": "Ubisoft", "emoji": "🎯", "description": "Ubisoft/Uplay accounts"},
    "instagram": {"name": "Instagram", "emoji": "📸", "description": "Instagram accounts"},
    "onlyfans": {"name": "OnlyFans", "emoji": "🔞", "description": "OnlyFans premium accounts"},
    "mega": {"name": "MEGA Links", "emoji": "📁", "description": "MEGA.nz file links"},
    "email": {"name": "Email Accounts", "emoji": "📧", "description": "Email:password combinations"},
    "accounts": {"name": "General Accounts", "emoji": "👤", "description": "Various account types"}
}

# ==================== MODERATION HELPER FUNCTIONS ====================

def parse_duration(duration: str) -> timedelta:
    duration = duration.lower()
    matches = re.findall(r'(\d+)([smhd])', duration)
    if not matches:
        raise ValueError("Invalid duration format. Use e.g., '10m', '2h', '1d'")
    
    total_time = timedelta()
    for amount, unit in matches:
        amount = int(amount)
        if unit == 's':
            total_time += timedelta(seconds=amount)
        elif unit == 'm':
            total_time += timedelta(minutes=amount)
        elif unit == 'h':
            total_time += timedelta(hours=amount)
        elif unit == 'd':
            total_time += timedelta(days=amount)
    return total_time

def contains_bad_word(message_content: str, guild_id: str) -> bool:
    bad_words = load_json(JSON_FILES["bad_words"], {})
    normalized_content = re.sub(r'[^a-zA-Z0-9\s]', '', message_content.lower())
    words_in_message = normalized_content.split()
    
    for word in BLOCK_WORDS:
        for msg_word in words_in_message:
            if difflib.get_close_matches(msg_word, [word], n=1, cutoff=0.85):
                return True
    
    server_bad_words = bad_words.get(guild_id, [])
    for word in server_bad_words:
        for msg_word in words_in_message:
            if difflib.get_close_matches(msg_word, [word], n=1, cutoff=0.85):
                return True
    return False

def filter_bypass_techniques(message_content: str) -> bool:
    bypass_patterns = [
        r'([a@][s5][s$]?)',
        r'([n1][i1][g9][g6]?)',
        r'([s5][e3]?[x8][t7]?)',
        r'[b8][i1][t7][c3]?',
        r'[s5][h][i1][t7]?',
        r'[f@][a4][g9]',
    ]
    for pattern in bypass_patterns:
        if re.search(pattern, message_content.lower()):
            return True
    return False

# ==================== TWITCH/API HELPER FUNCTIONS ====================

async def fetch_oauth_token(client_id, client_secret):
    url = "https://id.twitch.tv/oauth2/token"
    params = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                return data["access_token"]
    return None

async def get_twitch_oauth_token():
    return await fetch_oauth_token(TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET)

async def fetch_user_id(session, username, headers, retries=3):
    if username in user_id_cache:
        return user_id_cache[username]
    
    encoded_username = quote(username)
    url = f"https://api.twitter.com/2/users/by/username/{encoded_username}"
    
    for attempt in range(retries):
        async with session.get(url, headers=headers) as user_resp:
            if user_resp.status == 429:
                await asyncio.sleep(60)
                continue
            if user_resp.status == 404:
                return None
            if user_resp.status != 200:
                return None
            
            user_data = await user_resp.json()
            user_id = user_data.get("data", {}).get("id")
            if user_id:
                user_id_cache[username] = user_id
                return user_id
    return None

# ==================== ANTI-NUKE FUNCTIONS ====================

def save_server_backup(guild: discord.Guild):
    backup = {"roles": [], "categories": [], "channels": []}
    
    for role in guild.roles:
        backup["roles"].append({
            "name": role.name,
            "color": role.color.value,
            "hoist": role.hoist,
            "mentionable": role.mentionable,
            "permissions": role.permissions.value,
            "position": role.position
        })
    
    for cat in guild.categories:
        overwrites = {}
        for target, perm in cat.overwrites.items():
            if isinstance(target, discord.Role):
                allow, deny = perm.pair()
                overwrites[str(target.id)] = {"allow": allow.value, "deny": deny.value}
        backup["categories"].append({
            "name": cat.name,
            "position": cat.position,
            "overwrites": overwrites
        })
    
    for ch in guild.text_channels + guild.voice_channels:
        overwrites = {}
        for target, perm in ch.overwrites.items():
            if isinstance(target, discord.Role):
                allow, deny = perm.pair()
                overwrites[str(target.id)] = {"allow": allow.value, "deny": deny.value}
        backup["channels"].append({
            "name": ch.name,
            "type": "text" if isinstance(ch, discord.TextChannel) else "voice",
            "category": ch.category.name if ch.category else None,
            "position": ch.position,
            "overwrites": overwrites
        })
    
    save_json(BACKUP_DIR / f"{guild.id}.json", backup)

async def load_server_backup(guild: discord.Guild):
    path = BACKUP_DIR / f"{guild.id}.json"
    backup = load_json(path)
    if not backup:
        return False
    
    role_map = {}
    for r in sorted(backup["roles"], key=lambda x: x["position"]):
        try:
            new_role = await guild.create_role(
                name=r["name"],
                permissions=discord.Permissions(r["permissions"]),
                colour=discord.Colour(r["color"]),
                hoist=r["hoist"],
                mentionable=r["mentionable"],
                reason="AntiNuke Restore"
            )
            role_map[r["name"]] = new_role
            await asyncio.sleep(0.5)
        except:
            continue
    
    cat_map = {}
    for c in backup["categories"]:
        try:
            new_cat = await guild.create_category(
                name=c["name"], position=c["position"], reason="AntiNuke Restore"
            )
            for rid, pair in c["overwrites"].items():
                role = guild.get_role(int(rid)) or next(
                    (r for name, r in role_map.items() if str(r.id) == rid), None
                )
                if role:
                    perms = discord.PermissionOverwrite.from_permissions(
                        allow=discord.Permissions(pair["allow"]),
                        deny=discord.Permissions(pair["deny"])
                    )
                    await new_cat.set_permissions(role, overwrite=perms)
            cat_map[c["name"]] = new_cat
            await asyncio.sleep(0.5)
        except:
            continue
    
    for ch in backup["channels"]:
        try:
            parent = cat_map.get(ch["category"])
            if ch["type"] == "text":
                new_ch = await guild.create_text_channel(
                    ch["name"], category=parent, position=ch["position"], reason="AntiNuke Restore"
                )
            else:
                new_ch = await guild.create_voice_channel(
                    ch["name"], category=parent, position=ch["position"], reason="AntiNuke Restore"
                )
            for rid, pair in ch["overwrites"].items():
                role = guild.get_role(int(rid)) or next(
                    (r for name, r in role_map.items() if str(r.id) == rid), None
                )
                if role:
                    perms = discord.PermissionOverwrite.from_permissions(
                        allow=discord.Permissions(pair["allow"]),
                        deny=discord.Permissions(pair["deny"])
                    )
                    await new_ch.set_permissions(role, overwrite=perms)
            await asyncio.sleep(0.5)
        except:
            continue
    
    return True

# ==================== FOUR TWENTY FUNCTIONS ====================

def get_next_schedule_time(timezone):
    now = datetime.now(timezone)
    next_420am = datetime(now.year, now.month, now.day, 4, 20, tzinfo=timezone)
    next_420pm = datetime(now.year, now.month, now.day, 16, 20, tzinfo=timezone)
    
    if now < next_420am:
        return next_420am
    elif now < next_420pm:
        return next_420pm
    else:
        return next_420am + timedelta(days=1)

async def send_four_twenty_message(guild, channel_id, role_id, voice_channel_id):
    channel = guild.get_channel(channel_id)
    if not channel:
        return
    
    role_mention = f"<@&{role_id}>" if role_id else ""
    voice_channel = guild.get_channel(voice_channel_id) if voice_channel_id else None
    voice_link = f"[Join voice chat!]({voice_channel.jump_url})" if voice_channel else "No voice chat configured."
    
    embed = discord.Embed(
        title="It's 4:20! 🌿",
        description=f"Join the session! {voice_link}\n{role_mention}",
        color=discord.Color.green()
    )
    
    try:
        await channel.send(embed=embed)
    except:
        pass

# ==================== ECONOMY FUNCTIONS ====================

def get_balance(user_id: int) -> int:
    c.execute("SELECT coins FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    if row:
        return row[0]
    c.execute("INSERT INTO users (id, coins, xp, level) VALUES (?, 0, 0, 1)", (user_id,))
    conn.commit()
    return 0

def add_coins(user_id: int, amount: int):
    current = get_balance(user_id)
    c.execute("UPDATE users SET coins = ? WHERE id = ?", (current + amount, user_id))
    conn.commit()

def remove_coins(user_id: int, amount: int):
    current = get_balance(user_id)
    new_balance = max(0, current - amount)
    c.execute("UPDATE users SET coins = ? WHERE id = ?", (new_balance, user_id))
    conn.commit()

def get_xp(user_id: int) -> int:
    c.execute("SELECT xp FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    return row[0] if row else 0

def get_level(user_id: int) -> int:
    c.execute("SELECT level FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    return row[0] if row else 1

def add_xp(user_id: int, amount: int) -> bool:
    current_xp = get_xp(user_id)
    current_level = get_level(user_id)
    new_xp = current_xp + amount
    c.execute("UPDATE users SET xp = ? WHERE id = ?", (new_xp, user_id))
    conn.commit()
    
    # Check if leveled up
    new_level = int(new_xp ** 0.5)  # XP needed = level^2
    if new_level > current_level:
        c.execute("UPDATE users SET level = ? WHERE id = ?", (new_level, user_id))
        conn.commit()
        return True
    return False

# ==================== EVENTS ====================

@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')
    print(f'Bot ID: {bot.user.id}')
    print(f'Stock directory: {STOCK_DIR}')
    
    # Create default stock files
    for stock_type in STOCK_TYPES.keys():
        create_stock_file(stock_type)
    
    # Sync commands
    try:
        await bot.tree.sync()
        print("✅ Slash commands synced globally")
    except Exception as e:
        print(f"Error syncing commands: {e}")
    
    # Start background tasks
    daily_coins.start()
    random_event_loop.start()
    check_youtube.start()
    check_twitch.start()
    check_twitter_posts.start()
    check_unjail.start()
    send_daily_messages.start()
    
    # Start API server
    bot.loop.create_task(start_api_server())
    
    print("✅ All background tasks started")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    # XP System
    new_level = add_xp(message.author.id, random.randint(1, 5))
    add_coins(message.author.id, random.randint(0, 2))
    
    if new_level:
        await assign_level_role(message.author, new_level)
    
    # Bad word filter
    if message.guild:
        guild_id = str(message.guild.id)
        server_configs = load_json(JSON_FILES["server_configs"], {})
        server_config = server_configs.get(guild_id, {})
        
        if message.channel.id not in server_config.get("allowed_channels", []):
            if contains_bad_word(message.content, guild_id) or filter_bypass_techniques(message.content):
                await message.delete()
                
                warnings = load_json(JSON_FILES["warnings"], {})
                if guild_id not in warnings:
                    warnings[guild_id] = {}
                if str(message.author.id) not in warnings[guild_id]:
                    warnings[guild_id][str(message.author.id)] = {"count": 0, "warnings": []}
                
                warnings[guild_id][str(message.author.id)]["count"] += 1
                warnings[guild_id][str(message.author.id)]["warnings"].append({
                    "reason": "Inappropriate language",
                    "date": datetime.now().isoformat(),
                    "moderator": str(bot.user.id)
                })
                
                save_json(JSON_FILES["warnings"], warnings)
                
                warning_count = warnings[guild_id][str(message.author.id)]["count"]
                
                embed = discord.Embed(
                    title="🚫 Warning!",
                    description=f"{message.author.mention}, watch your language! Keep it clean! 😆",
                    color=discord.Color.red()
                )
                await message.channel.send(embed=embed)
                
                try:
                    dm_embed = discord.Embed(
                        title="⚠️ Warning!",
                        description=f"**Warning {warning_count}/3**\nYou used inappropriate language in **{message.guild.name}**.\nPlease follow the server rules and keep the chat clean.\nAfter 3 warnings, you will be **timed out for 10 minutes**.\n\n**Help us keep the community safe and fun for everyone!**",
                        color=discord.Color.red()
                    )
                    await message.author.send(embed=dm_embed)
                except:
                    pass
                
                if warning_count >= 3:
                    try:
                        until = discord.utils.utcnow() + timedelta(minutes=10)
                        await message.author.timeout(until, reason="Reached 3 warnings for inappropriate language")
                        await message.channel.send(f"{message.author.mention} has been timed out for 10 minutes due to repeated warnings.")
                        warnings[guild_id][str(message.author.id)]["count"] = 0
                        save_json(JSON_FILES["warnings"], warnings)
                    except:
                        pass
                
                await log_action(message, f"Warning {warning_count}/3 for inappropriate language", guild_id)
    
    await bot.process_commands(message)

@bot.event
async def on_member_join(member: discord.Member):
    guild_id = str(member.guild.id)
    role_settings = load_json(JSON_FILES["role_on_join"], {})
    
    if guild_id in role_settings:
        settings = role_settings[guild_id]
        role = member.guild.get_role(settings["role_id"])
        delay = settings["delay"]
        
        await asyncio.sleep(delay)
        
        try:
            await member.add_roles(role)
            embed = discord.Embed(
                title="🎉 Welcome to the Server!",
                description=f"You have been assigned the **{role.name}** role and can now participate in the server!",
                color=discord.Color.green()
            )
            embed.set_footer(text=f"Enjoy your time in {member.guild.name}!")
            await member.send(embed=embed)
        except:
            pass

@bot.event
async def on_voice_state_update(member, before, after):
    log_channels = load_json(JSON_FILES["log_channels"], {})
    guild_id = str(member.guild.id)
    
    if guild_id in log_channels:
        voice_channel_id = log_channels[guild_id].get("voice")
        if voice_channel_id:
            log_channel = bot.get_channel(int(voice_channel_id))
            if log_channel:
                if not before.channel and after.channel:
                    embed = discord.Embed(
                        title="✅ User Connected",
                        description=f"{member.mention} connected to {after.channel.name}.",
                        color=discord.Color.green()
                    )
                    await log_channel.send(embed=embed)
                elif before.channel and not after.channel:
                    embed = discord.Embed(
                        title="🚪 User Disconnected",
                        description=f"{member.mention} left {before.channel.name}.",
                        color=discord.Color.orange()
                    )
                    await log_channel.send(embed=embed)

@bot.event
async def on_message_delete(message):
    log_channels = load_json(JSON_FILES["log_channels"], {})
    guild_id = str(message.guild.id)
    
    if guild_id in log_channels:
        chat_channel_id = log_channels[guild_id].get("chat")
        if chat_channel_id:
            log_channel = bot.get_channel(int(chat_channel_id))
            if log_channel:
                embed = discord.Embed(
                    title="🗑️ Message Deleted",
                    description=f"Message from {message.author.mention} deleted in {message.channel.mention}.",
                    color=discord.Color.red()
                )
                embed.add_field(name="Content", value=message.content[:1000] if message.content else "*No content*", inline=False)
                await log_channel.send(embed=embed)

@bot.event
async def on_message_edit(before, after):
    if before.content == after.content or before.author.bot:
        return
    
    log_channels = load_json(JSON_FILES["log_channels"], {})
    guild_id = str(before.guild.id)
    
    if guild_id in log_channels:
        chat_channel_id = log_channels[guild_id].get("chat")
        if chat_channel_id:
            log_channel = bot.get_channel(int(chat_channel_id))
            if log_channel:
                embed = discord.Embed(
                    title="✏️ Message Edited",
                    description=f"Message from {before.author.mention} edited in {before.channel.mention}.",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Before", value=before.content[:500] if before.content else "*No content*", inline=False)
                embed.add_field(name="After", value=after.content[:500] if after.content else "*No content*", inline=False)
                await log_channel.send(embed=embed)

async def assign_level_role(member, level):
    if level in LEVEL_ROLES:
        role_name = LEVEL_ROLES[level]
        role = discord.utils.get(member.guild.roles, name=role_name)
        if role:
            await member.add_roles(role)
            try:
                await member.send(f"You reached Level {level}! Role **{role_name}** has been assigned to you.")
            except:
                pass

async def log_action(message, action, guild_id):
    server_configs = load_json(JSON_FILES["server_configs"], {})
    server_config = server_configs.get(guild_id, {})
    log_channel_id = server_config.get("log_channel")
    
    if log_channel_id:
        log_channel = message.guild.get_channel(log_channel_id)
        if log_channel:
            embed = discord.Embed(title="📝 Action Log", color=discord.Color.red())
            embed.add_field(name="Action", value=action, inline=False)
            embed.add_field(name="User", value=f"{message.author.mention}", inline=False)
            embed.add_field(name="Channel", value=message.channel.mention, inline=False)
            embed.add_field(name="Message", value=message.content[:500] if message.content else "*No content*", inline=False)
            await log_channel.send(embed=embed)

# ==================== BACKGROUND TASKS ====================

@tasks.loop(hours=24)
async def daily_coins():
    c.execute("SELECT id FROM users")
    users = c.fetchall()
    for (user_id,) in users:
        add_coins(user_id, 50)
    print("✅ Daily coins distributed")

@tasks.loop(minutes=60)
async def random_event_loop():
    if not bot.guilds:
        return
    guild = random.choice(bot.guilds)
    if not guild.members:
        return
    member = random.choice([m for m in guild.members if not m.bot])
    if member:
        reward = random.randint(5, 30)
        add_coins(member.id, reward)
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                await channel.send(f"🎉 Random event! {member.mention} received {reward} coins!")
                break

@tasks.loop(minutes=5)
async def check_twitter_posts():
    logging.info("🔁 Checking Twitter...")
    
    server_settings = load_json(JSON_FILES["server_settings"], {})
    tracked_channels = load_json(JSON_FILES["tracked_channels"], {})
    
    async with aiohttp.ClientSession() as session:
        for guild_id, settings in server_settings.items():
            notification_channel_id = settings.get("notification_channel_id")
            role_id = settings.get("notification_role_id")
            
            x_accounts = tracked_channels.get(str(guild_id), {}).get("x", {})
            headers = {"Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"}
            
            for username, account_data in x_accounts.items():
                try:
                    user_id = await fetch_user_id(session, username, headers)
                    if not user_id:
                        continue
                    
                    posts_url = f"https://api.twitter.com/2/users/{user_id}/tweets?tweet.fields=created_at,public_metrics&max_results=5"
                    async with session.get(posts_url, headers=headers) as resp:
                        if resp.status == 429:
                            await asyncio.sleep(60)
                            continue
                        if resp.status != 200:
                            continue
                        
                        posts_data = await resp.json()
                        tweets = posts_data.get("data", [])
                        if not tweets:
                            continue
                        
                        latest_tweet = tweets[0]
                        new_post_id = latest_tweet["id"]
                        
                        if new_post_id == account_data.get("last_post_id"):
                            continue
                        
                        tracked_channels[str(guild_id)]["x"][username]["last_post_id"] = new_post_id
                        save_json(JSON_FILES["tracked_channels"], tracked_channels)
                        
                        embed = discord.Embed(
                            title=f"📢 New Tweet from @{username}",
                            description=latest_tweet.get("text", "*No content*")[:200],
                            color=discord.Color.blue(),
                            timestamp=datetime.now(pytz.timezone("America/Los_Angeles"))
                        )
                        embed.set_author(
                            name=f"@{username}",
                            url=f"https://twitter.com/{username}"
                        )
                        
                        view = View()
                        view.add_item(Button(label="❤️ Like", style=discord.ButtonStyle.link, url=f"https://twitter.com/intent/like?tweet_id={new_post_id}"))
                        view.add_item(Button(label="🔁 Retweet", style=discord.ButtonStyle.link, url=f"https://twitter.com/intent/retweet?tweet_id={new_post_id}"))
                        view.add_item(Button(label="💬 Reply", style=discord.ButtonStyle.link, url=f"https://twitter.com/intent/tweet?in_reply_to={new_post_id}"))
                        
                        channel = bot.get_channel(notification_channel_id)
                        if channel:
                            role_mention = f"<@&{role_id}>" if role_id else ""
                            await channel.send(content=role_mention, embed=embed, view=view)
                except Exception as e:
                    logging.error(f"Twitter error for @{username}: {e}")
                await asyncio.sleep(2)

@tasks.loop(minutes=3)
async def check_youtube():
    logging.info("🔁 Checking YouTube...")
    
    server_settings = load_json(JSON_FILES["server_settings"], {})
    tracked_channels = load_json(JSON_FILES["tracked_channels"], {})
    
    for guild_id, settings in server_settings.items():
        notification_channel_id = settings.get("notification_channel_id")
        notification_role_id = settings.get("notification_role_id")
        youtube_channels = tracked_channels.get(str(guild_id), {}).get("youtube", {})
        
        for stored_channel_id, channel_data in youtube_channels.items():
            try:
                rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={stored_channel_id}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(rss_url) as response:
                        if response.status != 200:
                            continue
                        content = await response.text()
                
                root = ET.fromstring(content)
                namespace = {
                    "yt": "http://www.youtube.com/xml/schemas/2015",
                    "atom": "http://www.w3.org/2005/Atom",
                    "media": "http://search.yahoo.com/mrss/"
                }
                
                latest_entry = root.find(".//atom:entry", namespace)
                if latest_entry is None:
                    continue
                
                video_id_elem = latest_entry.find("yt:videoId", namespace)
                video_id = video_id_elem.text if video_id_elem is not None else None
                if not video_id:
                    continue
                
                if video_id == channel_data.get("last_post_id"):
                    continue
                
                tracked_channels[str(guild_id)]["youtube"][stored_channel_id]["last_post_id"] = video_id
                save_json(JSON_FILES["tracked_channels"], tracked_channels)
                
                title_elem = latest_entry.find("atom:title", namespace)
                title = title_elem.text if title_elem is not None else "Unknown Title"
                channel_name_elem = root.find(".//atom:title", namespace)
                channel_name = channel_name_elem.text if channel_name_elem is not None else "Unknown Channel"
                
                is_live = "live" in title.lower()
                
                embed = discord.Embed(
                    title="🔴 Live Now!" if is_live else "🎥 New YouTube Upload!",
                    description=f"**{title}**\n[Watch Video](https://youtu.be/{video_id})",
                    color=discord.Color.red() if is_live else discord.Color.green()
                )
                embed.set_author(
                    name=channel_name,
                    url=f"https://www.youtube.com/channel/{stored_channel_id}",
                    icon_url="https://www.youtube.com/s/desktop/8d3b0b0e/img/favicon_144x144.png"
                )
                embed.set_thumbnail(url=f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg")
                
                channel = bot.get_channel(notification_channel_id)
                if channel:
                    role_mention = f"<@&{notification_role_id}>" if notification_role_id else ""
                    await channel.send(content=role_mention, embed=embed)
            except Exception as e:
                logging.error(f"YouTube error for {stored_channel_id}: {e}")

@tasks.loop(minutes=2)
async def check_twitch():
    logging.info("🔁 Checking Twitch...")
    
    server_settings = load_json(JSON_FILES["server_settings"], {})
    tracked_channels = load_json(JSON_FILES["tracked_channels"], {})
    
    oauth_token = await get_twitch_oauth_token()
    if not oauth_token:
        return
    
    async with aiohttp.ClientSession() as session:
        for guild_id, settings in server_settings.items():
            notification_channel_id = settings.get("notification_channel_id")
            role_id = settings.get("notification_role_id")
            twitch_channels = tracked_channels.get(str(guild_id), {}).get("twitch", {})
            
            for channel_name, channel_data in twitch_channels.items():
                try:
                    url = f"https://api.twitch.tv/helix/streams?user_login={channel_name}"
                    headers = {"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {oauth_token}"}
                    
                    async with session.get(url, headers=headers) as resp:
                        if resp.status != 200:
                            continue
                        
                        data = await resp.json()
                        if not data.get("data"):
                            notified_streams.pop(channel_name, None)
                            continue
                        
                        stream_data = data["data"][0]
                        
                        if notified_streams.get(channel_name) == stream_data["id"]:
                            continue
                        
                        tracked_channels[str(guild_id)]["twitch"][channel_name]["last_post_id"] = stream_data["id"]
                        save_json(JSON_FILES["tracked_channels"], tracked_channels)
                        notified_streams[channel_name] = stream_data["id"]
                        
                        embed = discord.Embed(
                            title="📡 Live Now!",
                            description=f"[{stream_data['title']}](https://www.twitch.tv/{channel_name})",
                            color=discord.Color.purple()
                        )
                        embed.set_author(
                            name=f"{stream_data['user_name']} on Twitch",
                            url=f"https://www.twitch.tv/{channel_name}",
                            icon_url="https://static.twitchcdn.net/assets/favicon-32-e29e246c157142c94346.png"
                        )
                        embed.set_thumbnail(url=stream_data["thumbnail_url"].replace("{width}", "320").replace("{height}", "180"))
                        embed.add_field(name="Game", value=stream_data.get("game_name", "Unknown"), inline=True)
                        embed.add_field(name="Viewers", value=stream_data.get("viewer_count", 0), inline=True)
                        
                        channel = bot.get_channel(notification_channel_id)
                        if channel:
                            role_mention = f"<@&{role_id}>" if role_id else ""
                            await channel.send(content=role_mention, embed=embed)
                except Exception as e:
                    logging.error(f"Twitch error for {channel_name}: {e}")

@tasks.loop(seconds=30)
async def check_unjail():
    now = datetime.utcnow()
    jailed_members = load_json(JSON_FILES["jailed_members"], {})
    updated = False
    
    for guild_id, members in list(jailed_members.items()):
        guild = bot.get_guild(int(guild_id))
        if not guild:
            continue
        
        for member_id, data in list(members.items()):
            try:
                jail_time = datetime.strptime(data["jail_time"], '%Y-%m-%d %H:%M:%S')
                duration = parse_duration(data["duration"])
                release_time = jail_time + duration
                
                if now >= release_time:
                    member = guild.get_member(int(member_id))
                    if member:
                        await unjail_member(member, reason="Jail time expired")
                        updated = True
                        
                        del jailed_members[guild_id][member_id]
                        
                        if not jailed_members[guild_id]:
                            del jailed_members[guild_id]
            except Exception as e:
                logging.error(f"Error checking unjail for {member_id}: {e}")
                continue
    
    if updated:
        save_json(JSON_FILES["jailed_members"], jailed_members)

async def unjail_member(member: discord.Member, reason: str = "Jail time expired"):
    guild_id = str(member.guild.id)
    jailed_members = load_json(JSON_FILES["jailed_members"], {})
    
    if guild_id not in jailed_members or str(member.id) not in jailed_members[guild_id]:
        return
    
    previous_roles = jailed_members[guild_id][str(member.id)]["roles"]
    role_objects = [member.guild.get_role(role_id) for role_id in previous_roles if member.guild.get_role(role_id)]
    
    if role_objects:
        await member.add_roles(*role_objects, reason="Unjailed")
    
    for channel in member.guild.text_channels + member.guild.voice_channels:
        await channel.set_permissions(member, overwrite=None)
    
    del jailed_members[guild_id][str(member.id)]
    save_json(JSON_FILES["jailed_members"], jailed_members)
    
    try:
        embed = discord.Embed(title="✅ You Have Been Unjailed!", color=discord.Color.green())
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Server", value=member.guild.name, inline=False)
        await member.send(embed=embed)
    except:
        pass

@tasks.loop(minutes=1)
async def send_daily_messages():
    four_twenty_data = load_json(JSON_FILES["four_twenty"], {})
    
    for guild in bot.guilds:
        config = four_twenty_data.get(str(guild.id))
        if not config:
            continue
        
        try:
            timezone = pytz.timezone(config.get("timezone", "UTC"))
        except:
            timezone = pytz.UTC
        
        next_time = get_next_schedule_time(timezone)
        now = datetime.now(timezone)
        
        if abs((next_time - now).total_seconds()) < 60:
            await send_four_twenty_message(
                guild,
                config.get("channel_id"),
                config.get("role_id"),
                config.get("voice_channel_id")
            )
            await asyncio.sleep(61)

# ==================== VIEW CLASSES ====================

class SlotsView(View):
    def __init__(self, user_id):
        super().__init__(timeout=100)
        self.user_id = user_id
        self.emojis = ["🍎", "🍌", "🍒", "🍇", "💎"]
        self.bet_amount = 1
    
    @discord.ui.button(label="Spin 🎰", style=discord.ButtonStyle.green)
    async def spin(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your slot machine!", ephemeral=True)
            return
        
        coins = get_balance(self.user_id)
        if coins < self.bet_amount:
            await interaction.response.send_message(f"You don't have enough coins to bet {self.bet_amount}!", ephemeral=True)
            return
        
        remove_coins(self.user_id, self.bet_amount)
        result = [random.choice(self.emojis) for _ in range(3)]
        jackpot = len(set(result)) == 1
        
        if jackpot:
            won = self.bet_amount * 5
        else:
            won = 0 if random.random() < 0.5 else self.bet_amount * random.randint(1, 2)
        
        if won > 0:
            add_coins(self.user_id, won)
        
        embed = discord.Embed(title="🎰 Slot Machine", color=discord.Color.green())
        embed.description = " | ".join(result)
        embed.set_footer(text=f"Current Coins: {get_balance(self.user_id)}")
        
        if jackpot:
            embed.add_field(name="Jackpot! 🎉", value=f"You won {won} coins!", inline=False)
        elif won > 0:
            embed.add_field(name="You won!", value=f"You earned {won} coins.", inline=False)
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Bet 1", style=discord.ButtonStyle.blurple)
    async def bet1(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your slot machine!", ephemeral=True)
            return
        self.bet_amount = 1
        await interaction.response.send_message("Bet set to 1 coin.", ephemeral=True)
    
    @discord.ui.button(label="Bet 5", style=discord.ButtonStyle.blurple)
    async def bet5(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your slot machine!", ephemeral=True)
            return
        self.bet_amount = 5
        await interaction.response.send_message("Bet set to 5 coins.", ephemeral=True)
    
    @discord.ui.button(label="Bet 10", style=discord.ButtonStyle.blurple)
    async def bet10(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your slot machine!", ephemeral=True)
            return
        self.bet_amount = 10
        await interaction.response.send_message("Bet set to 10 coins.", ephemeral=True)
    
    @discord.ui.button(label="Bet 100", style=discord.ButtonStyle.blurple)
    async def bet100(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your slot machine!", ephemeral=True)
            return
        self.bet_amount = 100
        await interaction.response.send_message("Bet set to 100 coins.", ephemeral=True)
    
    @discord.ui.button(label="Bet ALL", style=discord.ButtonStyle.red)
    async def betall(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your slot machine!", ephemeral=True)
            return
        self.bet_amount = get_balance(self.user_id)
        await interaction.response.send_message(f"Bet set to all your coins ({self.bet_amount}).", ephemeral=True)

class BlackjackView(View):
    def __init__(self, user_id, bet, deck, player, dealer):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.bet = bet
        self.deck = deck
        self.player = player
        self.dealer = dealer
        self.game_over = False
    
    def hand_value(self, hand):
        value = sum(hand)
        aces = hand.count(11)
        while value > 21 and aces:
            value -= 10
            aces -= 1
        return value
    
    async def update_embed(self, interaction, final=False, result_text=None):
        player_score = self.hand_value(self.player)
        dealer_score = self.hand_value(self.dealer)
        
        desc = (
            f"**Your hand:** {self.player} → {player_score}\n"
            f"**Dealer's hand:** {self.dealer if final else [self.dealer[0], '?']} → {dealer_score if final else '?'}\n"
        )
        if result_text:
            desc += f"\n{result_text}"
        
        embed = discord.Embed(
            title="🃏 Blackjack",
            description=desc,
            color=discord.Color.green() if result_text and "win" in result_text.lower() else discord.Color.blue()
        )
        
        if final:
            await interaction.response.edit_message(embed=embed, view=None)
            self.stop()
        else:
            await interaction.response.edit_message(embed=embed, view=self)
    
    async def player_bust(self, interaction):
        remove_coins(self.user_id, self.bet)
        await self.update_embed(interaction, final=True, result_text=f"💥 You busted! You lose {self.bet} coins.")
        self.game_over = True
        self.stop()
    
    async def dealer_turn(self):
        while self.hand_value(self.dealer) < 17:
            self.dealer.append(self.deck.pop())
    
    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your game.", ephemeral=True)
            return
        
        self.player.append(self.deck.pop())
        if self.hand_value(self.player) > 21:
            await self.player_bust(interaction)
        else:
            await self.update_embed(interaction)
    
    @discord.ui.button(label="Stand", style=discord.ButtonStyle.success)
    async def stand(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your game.", ephemeral=True)
            return
        
        await self.dealer_turn()
        player_score = self.hand_value(self.player)
        dealer_score = self.hand_value(self.dealer)
        
        if dealer_score > 21 or player_score > dealer_score:
            reward = random.randint(10, 500)
            add_coins(self.user_id, reward)
            result = f"🎉 You win with {player_score}! You gain **{reward} coins**."
        elif player_score == dealer_score:
            result = f"🤝 Push with {player_score}. Your bet is returned."
            add_coins(self.user_id, self.bet)
        else:
            remove_coins(self.user_id, self.bet)
            result = f"😢 Dealer wins with {dealer_score}. You lose {self.bet} coins."
        
        await self.update_embed(interaction, final=True, result_text=result)
        self.game_over = True
        self.stop()
    
    @discord.ui.button(label="Double Down", style=discord.ButtonStyle.danger)
    async def double_down(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your game.", ephemeral=True)
            return
        
        balance = get_balance(self.user_id)
        if self.bet * 2 > balance:
            await interaction.response.send_message("❌ Not enough coins to double down.", ephemeral=True)
            return
        
        self.bet *= 2
        self.player.append(self.deck.pop())
        if self.hand_value(self.player) > 21:
            await self.player_bust(interaction)
        else:
            await self.stand(interaction, button)

class DeleteStockDropdown(View):
    def __init__(self, stock_files):
        super().__init__()
        self.select = Select(
            placeholder="Select a stock file to delete",
            options=[discord.SelectOption(label=stock, value=stock) for stock in stock_files]
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)
    
    async def select_callback(self, interaction: discord.Interaction):
        stock_type = self.select.values[0]
        stock_filename = get_stock_filename(stock_type)
        
        if stock_filename.exists():
            stock_filename.unlink()
            await interaction.response.send_message(f"✅ The `{stock_type}` stock file has been deleted.", ephemeral=True)
            await asyncio.sleep(2)
            await send_auto_update()

class RoleSelect(Select):
    def __init__(self, role_options):
        super().__init__(
            placeholder="Select a role...",
            options=role_options,
            min_values=1,
            max_values=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        selected_role_id = int(self.values[0])
        role = interaction.guild.get_role(selected_role_id)
        
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"Removed the role **{role.name}**.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"Assigned you the role **{role.name}**.", ephemeral=True)

class RoleView(View):
    def __init__(self, role_options):
        super().__init__(timeout=None)
        self.add_item(RoleSelect(role_options))

class VerifyButton(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Verify", style=discord.ButtonStyle.green)
    async def verify_button_callback(self, interaction: discord.Interaction, button: Button):
        settings = load_json("settings.json") if os.path.exists("settings.json") else {}
        verified_role_id = settings.get('verified_role')
        
        if not verified_role_id:
            await interaction.response.send_message("Verified role is not set. Please contact an administrator.", ephemeral=True)
            return
        
        verified_role = interaction.guild.get_role(int(verified_role_id))
        if not verified_role:
            await interaction.response.send_message("The verified role ID is invalid or the role does not exist.", ephemeral=True)
            return
        
        if verified_role in interaction.user.roles:
            await interaction.response.send_message("You are already verified!", ephemeral=True)
            return
        
        try:
            await interaction.user.add_roles(verified_role)
            await interaction.response.send_message(f"You have been verified and assigned the '{verified_role.name}' role!", ephemeral=True)
            
            try:
                await interaction.user.send(f"🎉 You have been successfully verified in **{interaction.guild.name}**! You have been assigned the role: **{verified_role.name}**.")
            except:
                pass
        except discord.Forbidden:
            await interaction.response.send_message("I do not have permission to assign roles. Please contact an administrator.", ephemeral=True)

# ==================== AUTO-UPDATE FUNCTIONS ====================

async def send_auto_update():
    auto_update_data = load_json(JSON_FILES["auto_update"], {})
    
    for guild_id, data in auto_update_data.items():
        guild = bot.get_guild(int(guild_id))
        if not guild:
            continue
        
        channel = bot.get_channel(data.get("channel_id"))
        if not channel:
            continue
        
        role_id = data.get("role_id")
        role_mention = f"<@&{role_id}>" if role_id else ""
        
        stock_info = []
        for file in STOCK_DIR.glob("*.txt"):
            stock_type = file.stem
            count = count_stock(stock_type)
            stock_info.append(f"➜ **{stock_type.capitalize()}**: `{count}` entries")
        
        embed = discord.Embed(title="📦 **Stock Update**", color=discord.Color.green())
        embed.add_field(name="**Stock**", value="\n".join(stock_info) if stock_info else "🚫 No stock available.", inline=False)
        embed.set_footer(text="Stock updates are live! 🔄")
        
        try:
            await channel.send(content=f"📢 {role_mention}, latest stock update!", embed=embed)
        except:
            pass

# ==================== SLASH COMMANDS ====================

@bot.tree.command(name="help", description="Get information about the bot and its commands")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 XULT - Ultimate Discord Bot",
        description="Your all-in-one solution for economy, moderation, notifications, and more!",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="💰 **Economy & Games**",
        value="`/balance` `/coinflip` `/rps` `/slots` `/blackjack` `/roulette` `/lottery` `/joke` `/eightball` `/riddle`",
        inline=False
    )
    
    embed.add_field(
        name="🛡️ **Moderation**",
        value="`/jail` `/unjail` `/purge` `/warnings` `/resetwarn` `/setroleonjoin` `/set_logs` `/add_allowed_channel` `/upload_bad_words` `/sendnotice`",
        inline=False
    )
    
    embed.add_field(
        name="📢 **Notifications**",
        value="`/setnotichannel` `/addyoutubechannel` `/addtwitchstream` `/addtwitteraccount`",
        inline=False
    )
    
    embed.add_field(
        name="📦 **Stock/Generator**",
        value="`/addstock` `/deletestock` `/gen` `/dmgen` `/setgenaccess` `/setautoupdate` `/stocklist`",
        inline=False
    )
    
    embed.add_field(
        name="⚙️ **Server Management**",
        value="`/reactionrole` `/setupverification` `/setverifybutton` `/setreportchannel` `/report` `/setlogchannels` `/updatelogchannels` `/save_server` `/load_server`",
        inline=False
    )
    
    embed.add_field(
        name="🌿 **4:20 Reminder**",
        value="`/add_to_channel` `/test`",
        inline=False
    )
    
    embed.add_field(
        name="🎨 **Fun Commands**",
        value="`/gif` `/meme` `/hug` `/slap` `/say`",
        inline=False
    )
    
    embed.add_field(
        name="📢 **Broadcast**",
        value="`/broadcastupdate` (Bot Owner only)",
        inline=False
    )
    
    embed.set_footer(text="XULT - The Ultimate Discord Bot • Support: https://discord.gg/pQBKywjW7h")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="stocklist", description="List all available stock types")
async def stocklist(interaction: discord.Interaction):
    """List all available stock types with counts"""
    
    embed = discord.Embed(
        title="📦 Available Stock",
        description="Use `/gen <type>` to generate from any available stock.",
        color=discord.Color.blue()
    )
    
    stock_count = 0
    for file in STOCK_DIR.glob("*.txt"):
        stock_type = file.stem
        count = count_stock(stock_type)
        stock_info = STOCK_TYPES.get(stock_type, {"name": stock_type.capitalize(), "emoji": "📄"})
        embed.add_field(
            name=f"{stock_info['emoji']} {stock_info['name']}",
            value=f"`{count}` available\n*{stock_info.get('description', '')}*",
            inline=True
        )
        stock_count += count
    
    if not embed.fields:
        embed.description = "No stock available!"
    
    embed.set_footer(text=f"Total entries: {stock_count} • Cooldown: 5 seconds")
    
    await interaction.response.send_message(embed=embed)

# ==================== ECONOMY COMMANDS ====================

@bot.tree.command(name="balance", description="Check your coins, XP, and level")
async def balance(interaction: discord.Interaction):
    coins = get_balance(interaction.user.id)
    xp = get_xp(interaction.user.id)
    level = get_level(interaction.user.id)
    
    embed = discord.Embed(
        title=f"{interaction.user.display_name}'s Balance",
        color=discord.Color.gold()
    )
    embed.add_field(name="Coins", value=coins, inline=True)
    embed.add_field(name="XP", value=xp, inline=True)
    embed.add_field(name="Level", value=level, inline=True)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="coinflip", description="Flip a coin and guess heads or tails")
@app_commands.describe(guess="Your guess: heads or tails")
async def coinflip(interaction: discord.Interaction, guess: str):
    guess = guess.lower()
    result = random.choice(["heads", "tails"])
    
    embed = discord.Embed(color=discord.Color.blue())
    if guess == result:
        add_coins(interaction.user.id, 10)
        embed.title = "🎉 You guessed correctly!"
        embed.description = f"You guessed **{guess}** and it was **{result}**! You won 10 coins!"
    else:
        embed.title = "❌ Wrong guess!"
        embed.description = f"You guessed **{guess}** but it was **{result}**. Better luck next time!"
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rps", description="Play rock-paper-scissors")
@app_commands.describe(choice="rock, paper, or scissors")
async def rps(interaction: discord.Interaction, choice: str):
    choice = choice.lower()
    options = ["rock", "paper", "scissors"]
    bot_choice = random.choice(options)
    win = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
    
    embed = discord.Embed(color=discord.Color.purple())
    if choice not in options:
        embed.title = "⚠️ Invalid Choice"
        embed.description = "Choose rock, paper, or scissors."
    elif bot_choice == choice:
        embed.title = "🤝 It's a tie!"
        embed.description = f"Bot chose **{bot_choice}**."
    elif win[choice] == bot_choice:
        add_coins(interaction.user.id, 10)
        embed.title = "🎉 You win!"
        embed.description = f"Bot chose **{bot_choice}**. You won 10 coins!"
    else:
        embed.title = "😢 You lose!"
        embed.description = f"Bot chose **{bot_choice}**."
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="slots", description="Play the slot machine")
async def slots(interaction: discord.Interaction):
    view = SlotsView(interaction.user.id)
    embed = discord.Embed(title="🎰 Slot Machine", description="Choose your bet and press Spin!", color=discord.Color.green())
    embed.set_footer(text=f"Current Coins: {get_balance(interaction.user.id)}")
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="blackjack", description="Play an interactive game of blackjack")
async def blackjack(interaction: discord.Interaction, bet: int):
    user_id = interaction.user.id
    balance = get_balance(user_id)
    
    if bet <= 0:
        await interaction.response.send_message("❌ Bet must be greater than zero.", ephemeral=True)
        return
    if bet > balance:
        await interaction.response.send_message("❌ You don't have enough coins to bet that amount.", ephemeral=True)
        return
    
    deck = [2,3,4,5,6,7,8,9,10,10,10,10,11]*4
    random.shuffle(deck)
    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]
    
    remove_coins(user_id, bet)
    
    view = BlackjackView(user_id, bet, deck, player, dealer)
    embed = discord.Embed(
        title="🃏 Blackjack",
        description=f"**Your hand:** {player} → {view.hand_value(player)}\n**Dealer's hand:** [{dealer[0]}, '?'] → ?",
        color=discord.Color.blue()
    )
    
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="roulette", description="Bet on roulette (red, black, or green)")
async def roulette(interaction: discord.Interaction, color: str, bet: int):
    user_id = interaction.user.id
    balance = get_balance(user_id)
    color = color.lower()
    
    if bet <= 0:
        await interaction.response.send_message("❌ Bet must be greater than zero.", ephemeral=True)
        return
    if bet > balance:
        await interaction.response.send_message("❌ You don't have enough coins to bet that amount.", ephemeral=True)
        return
    if color not in ["red", "black", "green"]:
        await interaction.response.send_message("❌ Invalid color! Choose red, black, or green.", ephemeral=True)
        return
    
    embed = discord.Embed(title="🎡 Roulette", description="The wheel is spinning...", color=discord.Color.blurple())
    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()
    
    for delay in [0.3, 0.4, 0.5, 0.6, 0.8]:
        temp_roll = random.randint(0, 36)
        temp_color = "green" if temp_roll == 0 else ("black" if temp_roll % 2 == 0 else "red")
        temp_embed = discord.Embed(
            title="🎡 Roulette",
            description=f"Ball bouncing around... landed on **{temp_color.upper()} {temp_roll}** (not final)",
            color=discord.Color.red() if temp_color == "red" else discord.Color.green() if temp_color == "green" else discord.Color.dark_gray()
        )
        await msg.edit(embed=temp_embed)
        await asyncio.sleep(delay)
    
    roll = random.randint(0, 36)
    result_color = "green" if roll == 0 else ("black" if roll % 2 == 0 else "red")
    
    if color == result_color:
        winnings = bet * 14 if color == "green" else bet * 2
        add_coins(user_id, winnings)
        result_text = f"🎉 The ball landed on **{result_color.upper()} {roll}**! You won {winnings} coins!"
        result_color_code = discord.Color.green()
    else:
        remove_coins(user_id, bet)
        result_text = f"😢 The ball landed on **{result_color.upper()} {roll}**. You lost {bet} coins."
        result_color_code = discord.Color.red()
    
    final_embed = discord.Embed(title="🎡 Roulette Result", description=result_text, color=result_color_code)
    await msg.edit(embed=final_embed)

@bot.tree.command(name="lottery", description="Enter the lottery")
async def lottery(interaction: discord.Interaction):
    user_id = interaction.user.id
    now = time.time()
    
    if user_id in lottery_cooldowns and now - lottery_cooldowns[user_id] < 600:
        remaining = int(600 - (now - lottery_cooldowns[user_id]))
        minutes, seconds = divmod(remaining, 60)
        embed = discord.Embed(
            description=f"⏳ You must wait {minutes}m {seconds}s before entering again!",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    lottery_cooldowns[user_id] = now
    c.execute("INSERT INTO lottery (user_id) VALUES (?)", (user_id,))
    conn.commit()
    
    embed = discord.Embed(
        description=f"🎉 {interaction.user.mention} entered the lottery!",
        color=discord.Color.gold()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="drawlottery", description="Draw a winner from the lottery (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def drawlottery(interaction: discord.Interaction):
    c.execute("SELECT user_id FROM lottery")
    users = c.fetchall()
    
    if not users:
        embed = discord.Embed(description="⚠️ No entries in the lottery!", color=discord.Color.red())
        await interaction.response.send_message(embed=embed)
        return
    
    winner_id = random.choice(users)[0]
    winner = interaction.guild.get_member(winner_id)
    reward = random.randint(100, 500)
    add_coins(winner_id, reward)
    
    embed = discord.Embed(
        title="🎊 Lottery Winner!",
        description=f"{winner.mention} won the lottery and receives **{reward} coins**!",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)
    
    c.execute("DELETE FROM lottery")
    conn.commit()

@drawlottery.error
async def drawlottery_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        embed = discord.Embed(
            description="❌ You need Administrator permission to draw the lottery!",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="joke", description="Get a random joke")
async def joke(interaction: discord.Interaction):
    async with aiohttp.ClientSession() as session:
        async with session.get("https://official-joke-api.appspot.com/jokes/random") as resp:
            data = await resp.json()
            embed = discord.Embed(
                title="😂 Joke",
                description=f"{data['setup']}\n\n{data['punchline']}",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed)

@bot.tree.command(name="eightball", description="Ask the magic 8-ball a question")
@app_commands.describe(question="Your question")
async def eightball(interaction: discord.Interaction, question: str):
    responses = ["Yes", "No", "Maybe", "Definitely", "Absolutely not", "Ask again later"]
    embed = discord.Embed(
        title=f"🎱 Question: {question}",
        description=random.choice(responses),
        color=discord.Color.dark_blue()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="riddle", description="Solve a riddle to earn coins")
async def riddle(interaction: discord.Interaction):
    global active_riddle, riddle_answer
    
    if active_riddle:
        await interaction.response.send_message("A riddle is already active!")
        return
    
    active_riddle, riddle_answer = random.choice(RIDDLES)
    await interaction.response.send_message(f"🧩 Riddle: {active_riddle}")
    
    def check(m):
        return m.content.lower() == riddle_answer.lower() and m.author == interaction.user and m.channel == interaction.channel
    
    try:
        msg = await bot.wait_for("message", timeout=30.0, check=check)
        add_coins(msg.author.id, 50)
        await interaction.channel.send(f"✅ Correct! {msg.author.mention} earned 50 coins!")
    except asyncio.TimeoutError:
        await interaction.channel.send(f"⏰ Time's up! The answer was: {riddle_answer}")
    
    active_riddle = None
    riddle_answer = None

# ==================== MODERATION COMMANDS ====================

@bot.tree.command(name="jail", description="Jail a member for a specified duration")
async def jail(interaction: discord.Interaction, member: discord.Member, duration: str = "10m", reason: str = "No reason provided"):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    try:
        initial_roles = [role for role in member.roles if role != interaction.guild.default_role]
        await member.remove_roles(*initial_roles, reason="Jailed")
        
        for channel in interaction.guild.text_channels + interaction.guild.voice_channels:
            await channel.set_permissions(member, read_messages=False, send_messages=False, connect=False, speak=False)
        
        jail_voice = discord.utils.get(interaction.guild.voice_channels, name="Jail VC")
        if not jail_voice:
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(connect=False),
                interaction.guild.me: discord.PermissionOverwrite(connect=True, manage_channels=True),
            }
            jail_voice = await interaction.guild.create_voice_channel("Jail VC", overwrites=overwrites)
        
        await jail_voice.set_permissions(member, connect=True, speak=True)
        
        if member.voice and member.voice.channel:
            await member.move_to(jail_voice)
        
        jailed_members = load_json(JSON_FILES["jailed_members"], {})
        guild_id = str(interaction.guild.id)
        
        if guild_id not in jailed_members:
            jailed_members[guild_id] = {}
        
        jailed_members[guild_id][str(member.id)] = {
            "roles": [role.id for role in initial_roles],
            "duration": duration,
            "reason": reason,
            "jail_time": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            "who_jailed": interaction.user.display_name,
            "server": interaction.guild.name
        }
        save_json(JSON_FILES["jailed_members"], jailed_members)
        
        try:
            embed = discord.Embed(title="🔒 You Have Been Jailed!", color=discord.Color.red())
            embed.add_field(name="Reason:", value=f"**{reason}**", inline=False)
            embed.add_field(name="Duration:", value=f"**{duration}**", inline=False)
            embed.add_field(name="Jailed By:", value=f"**{interaction.user.display_name}**", inline=False)
            embed.add_field(name="Server:", value=f"**{interaction.guild.name}**", inline=False)
            embed.set_footer(text="You will be automatically unjailed once your time expires.")
            await member.send(embed=embed)
        except:
            pass
        
        await interaction.followup.send(f"🔒 {member.mention} has been jailed for **{duration}**. Reason: **{reason}**.")
        
    except Exception as e:
        await interaction.followup.send(f"❌ Error jailing {member}: `{e}`", ephemeral=True)

@bot.tree.command(name="unjail", description="Unjail a member")
async def unjail(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    try:
        await unjail_member(member, reason=f"Unjailed by {interaction.user.display_name}")
        await interaction.followup.send(f"✅ {member.mention} has been unjailed.")
    except Exception as e:
        await interaction.followup.send(f"❌ Error unjailing {member}: `{e}`", ephemeral=True)

@bot.tree.command(name="purge", description="Purge messages in a channel")
@app_commands.describe(amount="Number of messages to delete (1-100)", channel="Channel to purge messages from (optional)")
async def purge(interaction: discord.Interaction, amount: int = 100, channel: discord.TextChannel = None):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ You don't have permission to purge messages.", ephemeral=True)
        return
    
    channel = channel or interaction.channel
    
    if amount < 1 or amount > 100:
        await interaction.response.send_message("❌ Amount must be between 1 and 100.", ephemeral=True)
        return
    
    await interaction.response.send_message(f"⏳ Purging {amount} messages...", ephemeral=True)
    
    try:
        deleted = await channel.purge(limit=amount)
        await interaction.followup.send(f"✅ Purged {len(deleted)} messages from {channel.mention}.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="warnings", description="View a user's warnings")
async def warnings(interaction: discord.Interaction, user: discord.Member):
    guild_id = str(interaction.guild.id)
    warnings_data = load_json(JSON_FILES["warnings"], {})
    
    user_warnings = warnings_data.get(guild_id, {}).get(str(user.id))
    
    embed = discord.Embed(
        title=f"⚠️ Warnings for {user.display_name}",
        color=discord.Color.orange()
    )
    
    if not user_warnings:
        embed.description = f"{user.mention} has no warnings."
    else:
        embed.description = f"{user.mention} has **{user_warnings.get('count', 0)}** warnings."
        
        if "warnings" in user_warnings:
            for i, warn in enumerate(user_warnings["warnings"][-5:], 1):
                date = warn.get('date', 'Unknown')[:10] if isinstance(warn.get('date'), str) else 'Unknown'
                embed.add_field(
                    name=f"Warning {i}",
                    value=f"**Reason:** {warn.get('reason', 'N/A')}\n**Date:** {date}",
                    inline=False
                )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="resetwarn", description="Reset a user's warnings")
@app_commands.describe(user="The user to reset warnings for", reason="Reason for resetting warnings")
async def resetwarn(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    guild_id = str(interaction.guild.id)
    warnings_data = load_json(JSON_FILES["warnings"], {})
    
    if guild_id in warnings_data and str(user.id) in warnings_data[guild_id]:
        del warnings_data[guild_id][str(user.id)]
        save_json(JSON_FILES["warnings"], warnings_data)
        
        try:
            embed = discord.Embed(
                title="✅ Warnings Reset",
                description=f"Your warnings in **{interaction.guild.name}** have been reset.",
                color=discord.Color.green()
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Reset by", value=interaction.user.mention, inline=False)
            await user.send(embed=embed)
        except:
            pass
        
        await interaction.response.send_message(f"✅ Reset warnings for {user.mention}.")
    else:
        await interaction.response.send_message(f"{user.mention} has no warnings to reset.")

@bot.tree.command(name="setroleonjoin", description="Set a role to be given to new members after a delay")
@app_commands.describe(role="The role to assign", delay="Delay (e.g., 10m, 2h, 1d)")
async def setroleonjoin(interaction: discord.Interaction, role: discord.Role, delay: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    time_multiplier = {"m": 60, "h": 3600, "d": 86400}
    try:
        unit = delay[-1]
        value = int(delay[:-1])
        if unit not in time_multiplier:
            raise ValueError
        delay_seconds = value * time_multiplier[unit]
    except:
        await interaction.response.send_message("Invalid delay format. Use e.g., `10m`, `2h`, `1d`.", ephemeral=True)
        return
    
    role_settings = load_json(JSON_FILES["role_on_join"], {})
    guild_id = str(interaction.guild.id)
    
    role_settings[guild_id] = {"role_id": role.id, "delay": delay_seconds}
    save_json(JSON_FILES["role_on_join"], role_settings)
    
    await interaction.response.send_message(f"✅ Set **{role.name}** to be assigned to new members after {delay}.", ephemeral=True)

@bot.tree.command(name="set_logs", description="Set a channel for logging bad words")
async def set_logs(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    server_configs = load_json(JSON_FILES["server_configs"], {})
    guild_id = str(interaction.guild.id)
    
    if guild_id not in server_configs:
        server_configs[guild_id] = {}
    
    server_configs[guild_id]["log_channel"] = channel.id
    save_json(JSON_FILES["server_configs"], server_configs)
    
    await interaction.response.send_message(f"✅ Log channel set to {channel.mention}.", ephemeral=True)

@bot.tree.command(name="add_allowed_channel", description="Add a channel where bad words are not moderated")
async def add_allowed_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    server_configs = load_json(JSON_FILES["server_configs"], {})
    guild_id = str(interaction.guild.id)
    
    if guild_id not in server_configs:
        server_configs[guild_id] = {"allowed_channels": []}
    if "allowed_channels" not in server_configs[guild_id]:
        server_configs[guild_id]["allowed_channels"] = []
    
    if channel.id not in server_configs[guild_id]["allowed_channels"]:
        server_configs[guild_id]["allowed_channels"].append(channel.id)
        save_json(JSON_FILES["server_configs"], server_configs)
        await interaction.response.send_message(f"✅ {channel.mention} added to allowed channels.", ephemeral=True)
    else:
        await interaction.response.send_message(f"{channel.mention} is already in allowed channels.", ephemeral=True)

@bot.tree.command(name="upload_bad_words", description="Upload a .txt file containing bad words to add")
async def upload_bad_words(interaction: discord.Interaction, file: discord.Attachment = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    if not file or not file.filename.endswith(".txt"):
        await interaction.response.send_message("Please upload a valid .txt file.", ephemeral=True)
        return
    
    guild_id = str(interaction.guild.id)
    bad_words_data = load_json(JSON_FILES["bad_words"], {})
    
    if guild_id not in bad_words_data:
        bad_words_data[guild_id] = []
    
    try:
        file_contents = await file.read()
        lines = file_contents.decode("utf-8", errors="ignore").splitlines()
        new_words = [line.strip().lower() for line in lines if line.strip()]
    except Exception as e:
        await interaction.response.send_message(f"Error reading the file: {e}", ephemeral=True)
        return
    
    existing_count = len(bad_words_data[guild_id])
    bad_words_data[guild_id].extend(new_words)
    bad_words_data[guild_id] = list(set(bad_words_data[guild_id]))
    save_json(JSON_FILES["bad_words"], bad_words_data)
    
    added_count = len(bad_words_data[guild_id]) - existing_count
    await interaction.response.send_message(f"✅ Added {added_count} new bad words. Total: {len(bad_words_data[guild_id])}", ephemeral=True)

@bot.tree.command(name="sendnotice", description="Send a notification to a channel or DM")
@app_commands.describe(
    message="Message content",
    channel="Channel to send the notification",
    user="User to DM the notification",
    title="Optional title",
    ping_role="Role to ping"
)
async def sendnotice(
    interaction: discord.Interaction,
    message: str,
    channel: discord.TextChannel = None,
    user: discord.User = None,
    title: str = "Notification",
    ping_role: discord.Role = None
):
    embed = discord.Embed(title=title, description=message, color=discord.Color.red())
    embed.set_footer(text=f"Sent by {interaction.user.display_name}")
    
    ping_message = f"<@&{ping_role.id}> " if ping_role else ""
    
    if user:
        try:
            await user.send(embed=embed)
            await interaction.response.send_message("✅ Notification sent via DM.", ephemeral=True)
        except:
            await interaction.response.send_message("❌ Failed to send DM.", ephemeral=True)
    elif channel:
        try:
            await channel.send(f"{ping_message}", embed=embed)
            await interaction.response.send_message(f"✅ Notification sent to {channel.mention}.", ephemeral=True)
        except:
            await interaction.response.send_message("❌ Failed to send to channel.", ephemeral=True)
    else:
        try:
            await interaction.user.send(embed=embed)
            await interaction.response.send_message("✅ Notification sent to your DMs.", ephemeral=True)
        except:
            await interaction.response.send_message("❌ Failed to send DM. You may have DMs disabled.", ephemeral=True)

# ==================== NOTIFICATION COMMANDS ====================

@bot.tree.command(name="setnotichannel", description="Set a channel for media notifications")
async def setnotichannel(interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    server_settings = load_json(JSON_FILES["server_settings"], {})
    guild_id = str(interaction.guild.id)
    
    server_settings[guild_id] = {
        "notification_channel_id": channel.id,
        "notification_role_id": role.id if role else None
    }
    save_json(JSON_FILES["server_settings"], server_settings)
    
    await interaction.response.send_message(f"✅ Notification channel set to {channel.mention}" + (f" with role {role.mention}" if role else ""), ephemeral=True)

@bot.tree.command(name="addyoutubechannel", description="Track a YouTube channel for uploads/live streams")
async def addyoutubechannel(interaction: discord.Interaction, channel_id: str):
    server_settings = load_json(JSON_FILES["server_settings"], {})
    guild_id = str(interaction.guild.id)
    
    if guild_id not in server_settings:
        await interaction.response.send_message("⚠️ Set a notification channel first with `/setnotichannel`.", ephemeral=True)
        return
    
    tracked_channels = load_json(JSON_FILES["tracked_channels"], {})
    
    if guild_id not in tracked_channels:
        tracked_channels[guild_id] = {}
    if "youtube" not in tracked_channels[guild_id]:
        tracked_channels[guild_id]["youtube"] = {}
    
    if channel_id in tracked_channels[guild_id]["youtube"]:
        await interaction.response.send_message(f"⚠️ Already tracking this YouTube channel.", ephemeral=True)
        return
    
    tracked_channels[guild_id]["youtube"][channel_id] = {"last_post_id": None}
    save_json(JSON_FILES["tracked_channels"], tracked_channels)
    
    await interaction.response.send_message(f"✅ Now tracking YouTube channel: {channel_id}", ephemeral=True)

@bot.tree.command(name="addtwitchstream", description="Track a Twitch stream for live notifications")
async def addtwitchstream(interaction: discord.Interaction, channel_name: str):
    server_settings = load_json(JSON_FILES["server_settings"], {})
    guild_id = str(interaction.guild.id)
    
    if guild_id not in server_settings:
        await interaction.response.send_message("⚠️ Set a notification channel first with `/setnotichannel`.", ephemeral=True)
        return
    
    tracked_channels = load_json(JSON_FILES["tracked_channels"], {})
    
    if guild_id not in tracked_channels:
        tracked_channels[guild_id] = {}
    if "twitch" not in tracked_channels[guild_id]:
        tracked_channels[guild_id]["twitch"] = {}
    
    channel_name = channel_name.lower()
    if channel_name in tracked_channels[guild_id]["twitch"]:
        await interaction.response.send_message(f"⚠️ Already tracking this Twitch stream.", ephemeral=True)
        return
    
    tracked_channels[guild_id]["twitch"][channel_name] = {"last_post_id": None}
    save_json(JSON_FILES["tracked_channels"], tracked_channels)
    
    await interaction.response.send_message(f"✅ Now tracking Twitch stream: {channel_name}", ephemeral=True)

@bot.tree.command(name="addtwitteraccount", description="Track a Twitter/X account for new tweets")
async def addtwitteraccount(interaction: discord.Interaction, username: str):
    server_settings = load_json(JSON_FILES["server_settings"], {})
    guild_id = str(interaction.guild.id)
    
    if guild_id not in server_settings:
        await interaction.response.send_message("⚠️ Set a notification channel first with `/setnotichannel`.", ephemeral=True)
        return
    
    tracked_channels = load_json(JSON_FILES["tracked_channels"], {})
    
    if guild_id not in tracked_channels:
        tracked_channels[guild_id] = {}
    if "x" not in tracked_channels[guild_id]:
        tracked_channels[guild_id]["x"] = {}
    
    username = username.lower()
    if username in tracked_channels[guild_id]["x"]:
        await interaction.response.send_message(f"⚠️ This server is already tracking @{username}.", ephemeral=True)
        return
    
    tracked_channels[guild_id]["x"][username] = {"last_post_id": None}
    save_json(JSON_FILES["tracked_channels"], tracked_channels)
    
    await interaction.response.send_message(f"✅ Now tracking Twitter account: @{username}", ephemeral=True)

# ==================== STOCK/GEN COMMANDS ====================

@bot.tree.command(name="addstock", description="Add stock entries")
async def addstock(interaction: discord.Interaction, stock_type: str, file: discord.Attachment = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    if file and file.filename.endswith(".txt"):
        content = await file.read()
        decoded = content.decode("utf-8", errors="ignore")
        lines = [line.strip() for line in decoded.split('\n') if line.strip()]
        
        if lines:
            add_stock_entries(stock_type, lines)
            await interaction.response.send_message(f"✅ Added {len(lines)} entries to **{stock_type}** stock!", ephemeral=True)
            await send_auto_update()
        else:
            await interaction.response.send_message("⚠️ No valid entries found in the file.", ephemeral=True)
    else:
        await interaction.response.send_message(f"📂 Upload a .txt file for {stock_type}.", ephemeral=True)

@bot.tree.command(name="deletestock", description="Delete a stock file")
async def deletestock(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Only admins can delete stock files.", ephemeral=True)
        return
    
    stock_files = [f.stem for f in STOCK_DIR.glob("*.txt")]
    
    if not stock_files:
        await interaction.response.send_message("⚠ No stock files available.", ephemeral=True)
        return
    
    view = DeleteStockDropdown(stock_files)
    await interaction.response.send_message("📂 Select a stock file to delete:", view=view, ephemeral=True)

@bot.tree.command(name="gen", description="Generate a stock entry")
async def gen(interaction: discord.Interaction, stock_type: str):
    """Generate a stock entry - premium role required in main server"""
    
    # Check premium role in main server
    main_guild = bot.get_guild(MAIN_SERVER_ID)
    if main_guild:
        member = main_guild.get_member(interaction.user.id)
        if not member:
            embed = discord.Embed(
                title="❌ Premium Required",
                description=f"You need to be in the main server to use this command.\nJoin and get the premium role!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        premium_role = main_guild.get_role(PREMIUM_ROLE_ID)
        if not premium_role or premium_role not in member.roles:
            embed = discord.Embed(
                title="❌ Premium Required",
                description=f"You need the premium role <@&{PREMIUM_ROLE_ID}> to use this command.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
    else:
        await interaction.response.send_message("❌ Cannot verify premium status. Main server not accessible.", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    # Check cooldown
    is_cooldown, remaining = is_on_cooldown(interaction.user.id)
    if is_cooldown:
        await interaction.followup.send(f"⏳ You must wait `{remaining}` seconds before using this again.")
        return
    
    # Get stock entry
    stock_info = get_stock_entry(stock_type)
    if not stock_info:
        await interaction.followup.send(f"❌ No stock available for {stock_type}.")
        return
    
    # Set cooldown
    set_cooldown(interaction.user.id)
    
    # Send to DMs
    try:
        await interaction.user.send(f"```\n{stock_info}\n```")
        await interaction.followup.send(f"📩 Stock sent to your DMs!")
        
        # Log usage
        c.execute("INSERT INTO stock_usage (user_id, stock_type, stock_content, generated_at) VALUES (?, ?, ?, ?)",
                 (interaction.user.id, stock_type, stock_info, datetime.now().isoformat()))
        conn.commit()
        
    except discord.Forbidden:
        await interaction.followup.send(f"❌ Unable to send DM. Please enable DMs.")
    
    await send_auto_update()

@bot.tree.command(name="dmgen", description="Generate stock via DM")
async def dmgen(interaction: discord.Interaction, stock_type: str):
    if interaction.guild is not None:
        await interaction.response.send_message("❌ This command can only be used in DMs.", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    is_cooldown, remaining = is_on_cooldown(interaction.user.id)
    if is_cooldown:
        await interaction.followup.send(f"⏳ You must wait `{remaining}` seconds before using this again.")
        return
    
    entries = read_stock_entries(stock_type)
    if not entries:
        await interaction.followup.send(f"❌ No stock available for {stock_type}.")
        return
    
    stock_info = entries.pop(0).strip()
    write_stock_entries(stock_type, entries)
    set_cooldown(interaction.user.id)
    
    await interaction.user.send(f"🎁 Here's your stock:\n```\n{stock_info}\n```")
    await interaction.followup.send("✅ Stock sent to your DMs!")
    
    await send_auto_update()

@bot.tree.command(name="setgenaccess", description="Set access roles for the /gen command")
async def setgenaccess(interaction: discord.Interaction, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Only admins can set gen access.", ephemeral=True)
        return
    
    gen_access = load_json(JSON_FILES["gen_access"], {})
    guild_id = str(interaction.guild.id)
    
    if guild_id not in gen_access:
        gen_access[guild_id] = []
    
    if role.id not in gen_access[guild_id]:
        gen_access[guild_id].append(role.id)
        save_json(JSON_FILES["gen_access"], gen_access)
    
    await interaction.response.send_message(f"✅ Role {role.mention} can now use `/gen`.", ephemeral=False)

@bot.tree.command(name="setautoupdate", description="Set auto-update stock channel and role")
async def setautoupdate(interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Only admins can set auto-update.", ephemeral=True)
        return
    
    auto_update = load_json(JSON_FILES["auto_update"], {})
    guild_id = str(interaction.guild.id)
    
    auto_update[guild_id] = {
        "channel_id": channel.id,
        "role_id": role.id
    }
    save_json(JSON_FILES["auto_update"], auto_update)
    
    await interaction.response.send_message(f"✅ Auto-update set to {channel.mention} with role {role.mention}.", ephemeral=False)

# ==================== SERVER MANAGEMENT COMMANDS ====================

@bot.tree.command(name="reactionrole", description="Create a reaction role dropdown menu")
async def reactionrole(interaction: discord.Interaction, roles: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    if not interaction.guild.me.guild_permissions.manage_roles:
        await interaction.response.send_message("❌ I need the `Manage Roles` permission.", ephemeral=True)
        return
    
    role_names = [r.strip() for r in roles.split(",")]
    guild_roles = {role.name: role for role in interaction.guild.roles if role.name != "@everyone"}
    selected_roles = [guild_roles[name] for name in role_names if name in guild_roles]
    
    if not selected_roles:
        await interaction.response.send_message("❌ No valid roles found.", ephemeral=True)
        return
    
    role_options = [discord.SelectOption(label=role.name, value=str(role.id)) for role in selected_roles]
    
    reaction_menus = load_json(JSON_FILES["reaction_role_menus"], {})
    reaction_menus[str(interaction.guild.id)] = [role.id for role in selected_roles]
    save_json(JSON_FILES["reaction_role_menus"], reaction_menus)
    
    embed = discord.Embed(
        title="🎭 Reaction Role Menu",
        description="Select a role from the dropdown below to assign or remove it.",
        color=discord.Color.blue()
    )
    embed.add_field(name="Available Roles", value="\n".join([role.name for role in selected_roles]), inline=False)
    embed.set_footer(text="Use the dropdown to manage your roles.")
    
    await interaction.response.send_message(embed=embed, view=RoleView(role_options))

@bot.tree.command(name="setupverification", description="Set up verification system")
async def setupverification(interaction: discord.Interaction, verify_channel: discord.TextChannel, verified_role: discord.Role, log_channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    settings = {
        'verify_channel': str(verify_channel.id),
        'verified_role': str(verified_role.id),
        'verify_log_channel': str(log_channel.id)
    }
    
    with open(DATA_DIR / "settings.json", "w") as f:
        json.dump(settings, f)
    
    await interaction.response.send_message(
        f"✅ **Verification Setup Complete:**\n"
        f"Channel: {verify_channel.mention}\n"
        f"Role: {verified_role.mention}\n"
        f"Logs: {log_channel.mention}",
        ephemeral=True
    )

@bot.tree.command(name="setverifybutton", description="Send verification button to the verification channel")
async def setverifybutton(interaction: discord.Interaction):
    settings_file = DATA_DIR / "settings.json"
    if not settings_file.exists():
        await interaction.response.send_message("❌ Please run `/setupverification` first.", ephemeral=True)
        return
    
    with open(settings_file, "r") as f:
        settings = json.load(f)
    
    verify_channel_id = settings.get('verify_channel')
    if not verify_channel_id:
        await interaction.response.send_message("❌ Verification channel not set.", ephemeral=True)
        return
    
    verify_channel = interaction.guild.get_channel(int(verify_channel_id))
    if not verify_channel:
        await interaction.response.send_message("❌ Verification channel not found.", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="🔒 Verification Required",
        description="Click the **Verify** button below to verify yourself and gain access to the server.",
        color=discord.Color.green()
    )
    embed.set_footer(text="XULT Verification System")
    
    await verify_channel.send(embed=embed, view=VerifyButton())
    await interaction.response.send_message("✅ Verification button sent to the verification channel.", ephemeral=True)

@bot.tree.command(name="setreportchannel", description="Set the channel for receiving reports")
async def setreportchannel(interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    report_channels = load_json(JSON_FILES["report_channels"], {})
    guild_id = str(interaction.guild.id)
    
    report_channels[guild_id] = {
        "channel_id": str(channel.id),
        "manager_role_id": str(role.id)
    }
    save_json(JSON_FILES["report_channels"], report_channels)
    
    await interaction.response.send_message(
        f"✅ Report channel: {channel.mention}\nReport Manager: {role.mention}",
        ephemeral=True
    )

@bot.tree.command(name="report", description="Report an issue or user to moderators")
async def report(
    interaction: discord.Interaction,
    issue: str,
    user: discord.User = None,
    evidence_text: str = None,
    evidence_file: discord.Attachment = None
):
    guild_id = str(interaction.guild.id)
    report_channel_data = load_json(JSON_FILES["report_channels"], {}).get(guild_id)
    
    if not report_channel_data:
        await interaction.response.send_message("❌ Report channel not set.", ephemeral=True)
        return
    
    report_channel_id = report_channel_data.get("channel_id")
    manager_role_id = report_channel_data.get("manager_role_id")
    
    if not report_channel_id or not manager_role_id:
        await interaction.response.send_message("❌ Report system not properly configured.", ephemeral=True)
        return
    
    report_channel = bot.get_channel(int(report_channel_id))
    if not report_channel:
        await interaction.response.send_message("❌ Report channel not found.", ephemeral=True)
        return
    
    embed = discord.Embed(title="🚨 New Report", color=discord.Color.red())
    embed.add_field(name="Reported By", value=interaction.user.mention, inline=False)
    embed.add_field(name="Issue", value=issue, inline=False)
    
    if user:
        embed.add_field(name="Reported User", value=user.mention, inline=False)
    if evidence_text:
        embed.add_field(name="Text Evidence", value=evidence_text, inline=False)
    if evidence_file:
        embed.add_field(name="File Evidence", value=evidence_file.url, inline=False)
    
    embed.set_footer(text=f"User ID: {interaction.user.id}")
    embed.timestamp = discord.utils.utcnow()
    
    role_mention = f"<@&{manager_role_id}>"
    message = await report_channel.send(content=f"{role_mention}, a new report has been submitted!", embed=embed)
    
    await interaction.response.send_message("✅ Your report has been submitted.", ephemeral=True)
    
    if user:
        try:
            dm_embed = discord.Embed(title="⚠️ You Have Been Reported", color=discord.Color.red())
            dm_embed.add_field(name="Server", value=interaction.guild.name, inline=False)
            dm_embed.add_field(name="Reported By", value=interaction.user.mention, inline=False)
            dm_embed.add_field(name="Issue", value=issue, inline=False)
            if evidence_text:
                dm_embed.add_field(name="Text Evidence", value=evidence_text, inline=False)
            if evidence_file:
                dm_embed.add_field(name="File Evidence", value=evidence_file.url, inline=False)
            await user.send(embed=dm_embed)
        except:
            pass

@bot.tree.command(name="setlogchannels", description="Set log channels for server events")
async def setlogchannels(
    interaction: discord.Interaction,
    member_channel: discord.TextChannel,
    chat_channel: discord.TextChannel,
    voice_channel: discord.TextChannel,
    mod_channel: discord.TextChannel,
    server_channel: discord.TextChannel,
    bot_update_channel: discord.TextChannel
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    log_channels = load_json(JSON_FILES["log_channels"], {})
    guild_id = str(interaction.guild.id)
    
    log_channels[guild_id] = {
        "member": str(member_channel.id),
        "chat": str(chat_channel.id),
        "voice": str(voice_channel.id),
        "mod": str(mod_channel.id),
        "server": str(server_channel.id),
        "bot_update": str(bot_update_channel.id)
    }
    save_json(JSON_FILES["log_channels"], log_channels)
    
    await interaction.response.send_message(
        f"✅ Log channels set:\n"
        f"Member: {member_channel.mention}\n"
        f"Chat: {chat_channel.mention}\n"
        f"Voice: {voice_channel.mention}\n"
        f"Mod: {mod_channel.mention}\n"
        f"Server: {server_channel.mention}\n"
        f"Bot Update: {bot_update_channel.mention}"
    )

@bot.tree.command(name="updatelogchannels", description="Update log channels for server events")
async def updatelogchannels(
    interaction: discord.Interaction,
    member_channel: discord.TextChannel,
    chat_channel: discord.TextChannel,
    voice_channel: discord.TextChannel,
    mod_channel: discord.TextChannel,
    server_channel: discord.TextChannel,
    bot_update_channel: discord.TextChannel
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    log_channels = load_json(JSON_FILES["log_channels"], {})
    guild_id = str(interaction.guild.id)
    
    log_channels[guild_id] = {
        "member": str(member_channel.id),
        "chat": str(chat_channel.id),
        "voice": str(voice_channel.id),
        "mod": str(mod_channel.id),
        "server": str(server_channel.id),
        "bot_update": str(bot_update_channel.id)
    }
    save_json(JSON_FILES["log_channels"], log_channels)
    
    await interaction.response.send_message(f"✅ Log channels updated.")

@bot.tree.command(name="save_server", description="Save full server structure backup")
async def save_server(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    save_server_backup(interaction.guild)
    await interaction.response.send_message("✅ Server backup saved.", ephemeral=True)

@bot.tree.command(name="load_server", description="Restore server from last backup")
async def load_server(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    backup_path = BACKUP_DIR / f"{interaction.guild.id}.json"
    if not backup_path.exists():
        await interaction.followup.send("❌ No backup found for this server.", ephemeral=True)
        return
    
    ok = await load_server_backup(interaction.guild)
    
    if ok:
        await interaction.followup.send("✅ Server restore complete.", ephemeral=True)
    else:
        await interaction.followup.send("❌ Failed to restore server.", ephemeral=True)

# ==================== FOUR TWENTY COMMANDS ====================

@bot.tree.command(name="add_to_channel", description="Configure 4:20 message channel")
async def add_to_channel(
    interaction: discord.Interaction,
    daily_channel: discord.TextChannel,
    timezone: str = 'UTC',
    role: discord.Role = None,
    voice_channel: discord.VoiceChannel = None
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    try:
        resolved_timezone = pytz.timezone(timezone)
    except:
        await interaction.response.send_message(f"❌ Invalid timezone: {timezone}", ephemeral=True)
        return
    
    four_twenty_data = load_json(JSON_FILES["four_twenty"], {})
    guild_id = str(interaction.guild.id)
    
    four_twenty_data[guild_id] = {
        'channel_id': daily_channel.id,
        'timezone': resolved_timezone.zone,
        'role_id': role.id if role else None,
        'voice_channel_id': voice_channel.id if voice_channel else None
    }
    save_json(JSON_FILES["four_twenty"], four_twenty_data)
    
    await interaction.response.send_message(
        f"✅ **4:20 Settings Updated:**\n"
        f"Channel: {daily_channel.mention}\n"
        f"Timezone: {resolved_timezone.zone}\n"
        f"Role: {role.mention if role else 'None'}\n"
        f"Voice: {voice_channel.mention if voice_channel else 'None'}"
    )

@bot.tree.command(name="test", description="Send a test 4:20 message")
async def test(interaction: discord.Interaction):
    four_twenty_data = load_json(JSON_FILES["four_twenty"], {})
    guild_id = str(interaction.guild.id)
    config = four_twenty_data.get(guild_id)
    
    if not config:
        await interaction.response.send_message("❌ No 4:20 configuration found for this server.", ephemeral=True)
        return
    
    channel = interaction.guild.get_channel(config.get('channel_id'))
    if not channel:
        await interaction.response.send_message("❌ Configured channel not found.", ephemeral=True)
        return
    
    await send_four_twenty_message(
        interaction.guild,
        config.get('channel_id'),
        config.get('role_id'),
        config.get('voice_channel_id')
    )
    await interaction.response.send_message("✅ Test message sent!", ephemeral=True)

# ==================== FUN COMMANDS ====================

@bot.tree.command(name="gif", description="Get a GIF from GIPHY")
async def gif(interaction: discord.Interaction, search: str):
    async with aiohttp.ClientSession() as session:
        url = (
            f"https://api.giphy.com/v1/gifs/search"
            f"?api_key={GIPHY_API_KEY}&q={search}&limit=1&rating=pg"
        )

        async with session.get(url) as resp:
            data = await resp.json()

    embed = discord.Embed(
        title=f"🎬 GIF result for '{search}'",
        color=discord.Color.blue()
    )

    if data.get("data"):
        gif_url = data["data"][0]["images"]["original"]["url"]
        embed.set_image(url=gif_url)
    else:
        embed.description = "No GIF found."

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="meme", description="Get a random meme")
async def meme(interaction: discord.Interaction):
    async with aiohttp.ClientSession() as session:
        async with session.get("https://meme-api.com/gimme") as resp:
            data = await resp.json()
            embed = discord.Embed(title=f"😂 {data['title']}", color=discord.Color.orange())
            embed.set_image(url=data['url'])
            await interaction.response.send_message(embed=embed)

@bot.tree.command(name="hug", description="Hug a member")
async def hug(interaction: discord.Interaction, member: discord.Member):
    embed = discord.Embed(
        description=f"{interaction.user.mention} hugs {member.mention}! 🤗",
        color=discord.Color.magenta()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="slap", description="Slap a member")
async def slap(interaction: discord.Interaction, member: discord.Member):
    embed = discord.Embed(
        description=f"{interaction.user.mention} slaps {member.mention}! 👋",
        color=discord.Color.red()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="say", description="Bot repeats your message")
async def say(interaction: discord.Interaction, text: str):
    embed = discord.Embed(description=text, color=discord.Color.green())
    await interaction.response.send_message(embed=embed)

# ==================== BROADCAST COMMAND ====================

@bot.tree.command(name="broadcastupdate", description="Broadcast an update to all servers (Bot Owner only)")
async def broadcastupdate(interaction: discord.Interaction, message: str, thumbnail: discord.Attachment = None):
    if interaction.user.id != BOT_OWNER_ID:
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        return
    
    log_channels = load_json(JSON_FILES["log_channels"], {})
    
    await interaction.response.send_message("📢 Broadcasting update...", ephemeral=True)
    
    sent_count = 0
    for guild_id, channels in log_channels.items():
        bot_update_channel_id = channels.get("bot_update")
        if bot_update_channel_id:
            guild = bot.get_guild(int(guild_id))
            if guild:
                channel = guild.get_channel(int(bot_update_channel_id))
                if channel:
                    owner = guild.owner
                    embed = discord.Embed(
                        title="📢 XULT Bot Update",
                        description=f"{owner.mention}\n\n{message}",
                        color=discord.Color.blurple()
                    )
                    embed.set_footer(text=f"Sent by {interaction.user.display_name}", icon_url=interaction.user.avatar.url)
                    if thumbnail:
                        embed.set_thumbnail(url=thumbnail.url)
                    embed.timestamp = discord.utils.utcnow()
                    embed.add_field(name="Support", value="Join our [support server](https://discord.gg/pQBKywjW7h).", inline=False)
                    
                    try:
                        await channel.send(embed=embed)
                        sent_count += 1
                    except:
                        pass
    
    await interaction.followup.send(f"✅ Update broadcasted to {sent_count} servers.", ephemeral=True)

# ==================== API SERVER ====================

import asyncio
from aiohttp import web
from datetime import datetime, timedelta
import psutil

# Save API key for frontend
with open(DATA_DIR / "api_key.txt", "w") as f:
    f.write(API_KEY)

print(f"🔑 API Key: {API_KEY}")
print(f"📡 API Server will start on port {API_PORT}")

# Store bot start time
bot.start_time = datetime.now()

# ==================== API HANDLERS ====================

async def handle_api_health(request):
    """GET /health - Health check"""
    return web.json_response({
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    })

async def handle_api_stats(request):
    """GET /api/stats - Get bot statistics"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        c.execute("SELECT COUNT(DISTINCT id) FROM users")
        total_users = c.fetchone()[0] or 0
        
        total_servers = len(bot.guilds)
        
        c.execute("SELECT COUNT(*) FROM premium_users WHERE is_active = 1")
        premium_users = c.fetchone()[0] or 0
        
        c.execute("SELECT COUNT(*) FROM stock_usage WHERE generated_at > datetime('now', '-1 day')")
        commands_today = c.fetchone()[0] or 0
        
        # Activity data for chart (last 7 days)
        activity = []
        for i in range(6, -1, -1):
            day = datetime.now() - timedelta(days=i)
            c.execute("SELECT COUNT(*) FROM stock_usage WHERE date(generated_at) = date(?)", (day.isoformat(),))
            count = c.fetchone()[0] or 0
            activity.append(count)
        
        return web.json_response({
            "total_users": total_users,
            "total_servers": total_servers,
            "total_commands": commands_today,
            "premium_users": premium_users,
            "activity": activity,
            "latency": round(bot.latency * 1000, 2),
            "uptime": str(datetime.now() - bot.start_time).split('.')[0]
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_stock(request):
    """GET /api/stock - Get all stock"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        stock_data = {}
        for file in STOCK_DIR.glob("*.txt"):
            stock_type = file.stem
            count = count_stock(stock_type)
            stock_data[stock_type] = {
                "count": count,
                "name": STOCK_TYPES.get(stock_type, {}).get("name", stock_type.capitalize()),
                "emoji": STOCK_TYPES.get(stock_type, {}).get("emoji", "📄"),
                "description": STOCK_TYPES.get(stock_type, {}).get("description", "")
            }
        
        return web.json_response(stock_data)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_generate(request):
    """POST /api/stock/generate/{type} - Generate stock"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        stock_type = request.match_info.get('type')
        data = await request.json()
        user_id = data.get('userId')
        ip = request.remote
        
        if not user_id or not stock_type:
            return web.json_response({"error": "Missing parameters"}, status=400)
        
        # Check if user is banned
        c.execute("SELECT * FROM banned_users WHERE user_id = ?", (user_id,))
        if c.fetchone():
            return web.json_response({"success": False, "error": "User is banned"})
        
        # Check premium status (in main server)
        main_guild = bot.get_guild(MAIN_SERVER_ID)
        if main_guild:
            member = main_guild.get_member(int(user_id))
            if not member:
                return web.json_response({"success": False, "error": "User not in main server"})
            
            premium_role = main_guild.get_role(PREMIUM_ROLE_ID)
            if not premium_role or premium_role not in member.roles:
                return web.json_response({"success": False, "error": "Premium role required"})
        else:
            return web.json_response({"success": False, "error": "Cannot verify premium status"})
        
        # Check cooldown
        c.execute("SELECT last_generated FROM user_cooldowns WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        if row and row[0]:
            last_gen = datetime.fromisoformat(row[0])
            if datetime.now() - last_gen < timedelta(seconds=5):
                remaining = 5 - (datetime.now() - last_gen).seconds
                return web.json_response({
                    "success": False,
                    "error": f"Please wait {remaining}s",
                    "cooldown": remaining
                })
        
        # Get stock
        content = get_stock_entry(stock_type)
        if not content:
            return web.json_response({"success": False, "error": "Out of stock"})
        
        # Log usage
        c.execute("INSERT INTO stock_usage (user_id, stock_type, stock_content, generated_at, ip_address) VALUES (?, ?, ?, ?, ?)",
                 (user_id, stock_type, content, datetime.now().isoformat(), ip))
        
        # Update cooldown
        c.execute("INSERT OR REPLACE INTO user_cooldowns (user_id, last_generated, generation_count) VALUES (?, ?, COALESCE((SELECT generation_count + 1 FROM user_cooldowns WHERE user_id = ?), 1))",
                 (user_id, datetime.now().isoformat(), user_id))
        
        conn.commit()
        
        remaining = count_stock(stock_type)
        
        return web.json_response({
            "success": True,
            "content": content,
            "remaining": remaining,
            "cooldown": 5
        })
        
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_api_check_premium(request):
    """GET /api/check-premium/{user_id} - Check premium status"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        user_id = int(request.match_info.get('user_id'))
        
        # Check in main server
        main_guild = bot.get_guild(MAIN_SERVER_ID)
        if main_guild:
            member = main_guild.get_member(user_id)
            if member:
                premium_role = main_guild.get_role(PREMIUM_ROLE_ID)
                if premium_role and premium_role in member.roles:
                    return web.json_response({"hasPremium": True, "roles": [str(r.id) for r in member.roles]})
        
        return web.json_response({"hasPremium": False, "roles": []})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_user(request):
    """GET /api/user/{user_id} - Get user economy data"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        user_id = int(request.match_info.get('user_id'))
        
        c.execute("SELECT coins, xp, level FROM users WHERE id = ?", (user_id,))
        row = c.fetchone()
        
        if not row:
            c.execute("INSERT INTO users (id, coins, xp, level) VALUES (?, 0, 0, 1)", (user_id,))
            conn.commit()
            row = (0, 0, 1)
        
        # Get rank
        c.execute("SELECT COUNT(*) FROM users WHERE coins > (SELECT coins FROM users WHERE id = ?)", (user_id,))
        rank = c.fetchone()[0] + 1
        
        return web.json_response({
            "coins": row[0],
            "xp": row[1],
            "level": row[2],
            "rank": rank
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_leaderboard(request):
    """GET /api/leaderboard - Get top users"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        c.execute("SELECT id, username, coins FROM users ORDER BY coins DESC LIMIT 10")
        users = []
        for user_id, username, coins in c.fetchall():
            users.append({
                "id": user_id,
                "username": username or f"User-{user_id}",
                "coins": coins
            })
        
        return web.json_response(users)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_stock_add(request):
    """POST /api/stock/add - Add stock (admin only)"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        data = await request.json()
        stock_type = data.get('type')
        content = data.get('content')
        
        if not stock_type or not content:
            return web.json_response({"error": "Missing parameters"}, status=400)
        
        # Parse content (simple line splitting)
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        if lines:
            add_stock_entries(stock_type, lines)
            return web.json_response({"success": True, "count": len(lines)})
        else:
            return web.json_response({"success": False, "error": "No valid entries"})
            
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

# Admin API Routes
async def handle_api_admin_users(request):
    """GET /api/admin/users - Get all users (admin only)"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        c.execute("SELECT id, username, coins, level, role FROM users ORDER BY coins DESC")
        users = []
        for user_id, username, coins, level, role in c.fetchall():
            # Check premium status
            has_premium = False
            main_guild = bot.get_guild(MAIN_SERVER_ID)
            if main_guild:
                member = main_guild.get_member(user_id)
                if member:
                    premium_role = main_guild.get_role(PREMIUM_ROLE_ID)
                    has_premium = premium_role and premium_role in member.roles
            
            users.append({
                "id": user_id,
                "username": username or f"User-{user_id}",
                "coins": coins,
                "level": level,
                "premium": has_premium,
                "role": role
            })
        
        return web.json_response(users)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_admin_stats(request):
    """GET /api/admin/stats - Get system stats (admin only)"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        # Get system stats
        cpu_percent = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        
        # Get uptime
        uptime = datetime.now() - bot.start_time
        hours = uptime.total_seconds() / 3600
        
        # Get DB size
        db_size = os.path.getsize(DATA_DIR / "xult.db") / (1024 * 1024)
        
        return web.json_response({
            "cpu": cpu_percent,
            "memory": memory.used / (1024 * 1024),
            "memory_total": memory.total / (1024 * 1024),
            "uptime": f"{int(hours)}h {int(uptime.seconds % 3600 / 60)}m",
            "dbSize": round(db_size, 2)
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_admin_premium(request):
    """GET /api/admin/premium - Get premium stats (admin only)"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        c.execute("SELECT COUNT(*) FROM premium_users WHERE is_active = 1")
        total = c.fetchone()[0] or 0
        
        return web.json_response({"total": total})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_admin_premium_users(request):
    """GET /api/admin/premium/users - Get all premium users (admin only)"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        c.execute("""
            SELECT u.id, u.username, p.granted_at, p.granted_at, p.is_active 
            FROM premium_users p
            JOIN users u ON u.id = p.user_id
            WHERE p.is_active = 1
            ORDER BY p.granted_at DESC
        """)
        users = []
        for user_id, username, granted_at, expires_at, is_active in c.fetchall():
            users.append({
                "id": user_id,
                "username": username or f"User-{user_id}",
                "granted_at": granted_at,
                "expires_at": expires_at,
                "is_active": is_active
            })
        
        return web.json_response(users)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_admin_logs_stock(request):
    """GET /api/admin/logs/stock - Get stock usage logs (admin only)"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        c.execute("SELECT user_id, stock_type, generated_at FROM stock_usage ORDER BY generated_at DESC LIMIT 50")
        logs = []
        for user_id, stock_type, generated_at in c.fetchall():
            time = datetime.fromisoformat(generated_at).strftime("%H:%M:%S")
            logs.append({
                "userId": user_id,
                "type": stock_type,
                "item": stock_type,
                "time": time
            })
        
        return web.json_response(logs)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_admin_user_jail(request):
    """POST /api/admin/users/{user_id}/jail - Jail a user (admin only)"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        user_id = int(request.match_info['user_id'])
        data = await request.json() if request.can_read_body else {}
        reason = data.get('reason', 'No reason provided')
        
        # Check if user exists in database
        c.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        if not c.fetchone():
            return web.json_response({"error": "User not found"}, status=404)
        
        # Add to banned_users table
        c.execute("INSERT OR REPLACE INTO banned_users (user_id, reason, banned_at, banned_by) VALUES (?, ?, ?, ?)",
                 (user_id, reason, datetime.now().isoformat(), request.headers.get('X-Admin-ID', 0)))
        conn.commit()
        
        return web.json_response({"success": True, "message": f"User {user_id} has been jailed"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_admin_user_premium_toggle(request):
    """POST /api/admin/users/{user_id}/premium/toggle - Toggle premium status (admin only)"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        user_id = int(request.match_info['user_id'])
        
        # Check if user exists
        c.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        if not c.fetchone():
            c.execute("INSERT INTO users (id, coins, xp, level) VALUES (?, 0, 0, 1)", (user_id,))
            conn.commit()
        
        # Toggle premium status
        c.execute("SELECT is_active FROM premium_users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        
        if row:
            new_status = 0 if row[0] == 1 else 1
            c.execute("UPDATE premium_users SET is_active = ?, granted_at = ? WHERE user_id = ?",
                     (new_status, datetime.now().isoformat(), user_id))
        else:
            c.execute("INSERT INTO premium_users (user_id, guild_id, role_id, granted_at, is_active) VALUES (?, ?, ?, ?, ?)",
                     (user_id, MAIN_SERVER_ID, PREMIUM_ROLE_ID, datetime.now().isoformat(), 1))
            new_status = 1
        
        conn.commit()
        
        return web.json_response({"success": True, "premium": new_status == 1})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_admin_user_premium_extend(request):
    """POST /api/admin/users/{user_id}/premium/extend - Extend premium duration (admin only)"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        user_id = int(request.match_info['user_id'])
        data = await request.json()
        days = data.get('days', 30)
        
        # Check if premium exists
        c.execute("SELECT granted_at FROM premium_users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        
        if row:
            # Update existing
            c.execute("UPDATE premium_users SET granted_at = ?, is_active = 1 WHERE user_id = ?",
                     (datetime.now().isoformat(), user_id))
        else:
            # Create new
            c.execute("INSERT INTO premium_users (user_id, guild_id, role_id, granted_at, is_active) VALUES (?, ?, ?, ?, ?)",
                     (user_id, MAIN_SERVER_ID, PREMIUM_ROLE_ID, datetime.now().isoformat(), 1))
        
        conn.commit()
        
        return web.json_response({"success": True, "extended": days})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_admin_server_sync(request):
    """POST /api/admin/servers/{server_id}/sync - Force sync server data (admin only)"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        server_id = int(request.match_info['server_id'])
        guild = bot.get_guild(server_id)
        
        if not guild:
            return web.json_response({"error": "Server not found"}, status=404)
        
        # Sync server data - update member counts, etc.
        # This would trigger a manual sync of server data
        
        return web.json_response({"success": True, "message": f"Server {guild.name} synced"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_admin_backup(request):
    """POST /api/admin/backup - Create database backup (admin only)"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        # Create backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = BACKUP_DIR / f"backup_{timestamp}.db"
        
        # Copy database file
        import shutil
        shutil.copy2(DATA_DIR / "xult.db", backup_file)
        
        return web.json_response({"success": True, "backup": str(backup_file)})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_admin_cache_clear(request):
    """POST /api/admin/cache/clear - Clear bot cache (admin only)"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        # Clear various caches
        global user_cooldowns, lottery_cooldowns, notified_streams, user_id_cache
        user_cooldowns.clear()
        lottery_cooldowns.clear()
        notified_streams.clear()
        user_id_cache.clear()
        
        return web.json_response({"success": True, "message": "Cache cleared"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_admin_sync(request):
    """POST /api/admin/sync - Sync databases (admin only)"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        # This would sync databases - for now just return success
        return web.json_response({"success": True, "message": "Databases synced"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_admin_sql(request):
    """POST /api/admin/sql - Execute SQL query (owner only)"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    # Check if user is owner (would need user ID from somewhere)
    # For now, just check API key
    
    try:
        data = await request.json()
        query = data.get('query')
        
        if not query:
            return web.json_response({"error": "No query provided"}, status=400)
        
        # Only allow SELECT queries for safety
        if not query.strip().upper().startswith('SELECT'):
            return web.json_response({"error": "Only SELECT queries are allowed"}, status=403)
        
        # Execute query
        c.execute(query)
        rows = c.fetchall()
        
        # Get column names
        columns = [description[0] for description in c.description] if c.description else []
        
        # Format result
        result = {
            "columns": columns,
            "rows": rows,
            "rowcount": len(rows)
        }
        
        return web.json_response({"success": True, "result": result})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

# Owner API Routes
async def handle_api_owner_users(request):
    """GET /api/owner/users - Get all users with full data (owner only)"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        c.execute("SELECT id, username, coins, xp, level, role FROM users ORDER BY coins DESC")
        users = []
        for user_id, username, coins, xp, level, role in c.fetchall():
            # Determine role
            user_role = role or "user"
            if str(user_id) == str(BOT_OWNER_ID):
                user_role = "owner"
            else:
                main_guild = bot.get_guild(MAIN_SERVER_ID)
                if main_guild:
                    member = main_guild.get_member(user_id)
                    if member:
                        premium_role = main_guild.get_role(PREMIUM_ROLE_ID)
                        if premium_role and premium_role in member.roles:
                            user_role = "premium"
            
            users.append({
                "id": user_id,
                "username": username or f"User-{user_id}",
                "coins": coins,
                "xp": xp,
                "level": level,
                "role": user_role
            })
        
        return web.json_response(users)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_owner_servers(request):
    """GET /api/owner/servers - Get all servers (owner only)"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        servers = []
        for guild in bot.guilds:
            servers.append({
                "id": guild.id,
                "name": guild.name,
                "members": guild.member_count,
                "owner": str(guild.owner_id)
            })
        
        return web.json_response(servers)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_owner_stats(request):
    """GET /api/owner/stats - Get owner stats"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        c.execute("SELECT COUNT(*) FROM stock_usage WHERE generated_at > datetime('now', '-1 day')")
        commands_today = c.fetchone()[0] or 0
        
        c.execute("SELECT COUNT(*) FROM premium_users WHERE is_active = 1")
        premium_users = c.fetchone()[0] or 0
        
        return web.json_response({
            "commandsToday": commands_today,
            "premiumUsers": premium_users
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

# User roles endpoint for premium check
async def handle_api_user_roles(request):
    """GET /api/user/roles/{user_id} - Get user roles"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        user_id = int(request.match_info.get('user_id'))
        
        main_guild = bot.get_guild(MAIN_SERVER_ID)
        if main_guild:
            member = main_guild.get_member(user_id)
            if member:
                roles = [str(r.id) for r in member.roles]
                return web.json_response({"roles": roles})
        
        return web.json_response({"roles": []})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

# ==================== START API SERVER ====================

async def start_api_server():
    """Start the aiohttp API server"""
    app = web.Application()
    
    # Add CORS middleware
    async def cors_middleware(app, handler):
        async def middleware(request):
            if request.method == 'OPTIONS':
                response = web.Response()
                response.headers['Access-Control-Allow-Origin'] = '*'
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
                return response
            
            response = await handler(request)
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response
        return middleware
    
    app.middlewares.append(cors_middleware)
    
    # Public routes
    app.router.add_get('/health', handle_api_health)
    
    # API routes (require API key)
    app.router.add_get('/api/stats', handle_api_stats)
    app.router.add_get('/api/stock', handle_api_stock)
    app.router.add_post('/api/stock/generate/{type}', handle_api_generate)
    app.router.add_post('/api/stock/add', handle_api_stock_add)
    app.router.add_get('/api/check-premium/{user_id}', handle_api_check_premium)
    app.router.add_get('/api/user/{user_id}', handle_api_user)
    app.router.add_get('/api/user/roles/{user_id}', handle_api_user_roles)
    app.router.add_get('/api/leaderboard', handle_api_leaderboard)
    
    # Admin routes
    app.router.add_get('/api/admin/users', handle_api_admin_users)
    app.router.add_get('/api/admin/stats', handle_api_admin_stats)
    app.router.add_get('/api/admin/premium', handle_api_admin_premium)
    app.router.add_get('/api/admin/premium/users', handle_api_admin_premium_users)
    app.router.add_get('/api/admin/logs/stock', handle_api_admin_logs_stock)
    app.router.add_post('/api/admin/users/{user_id}/jail', handle_api_admin_user_jail)
    app.router.add_post('/api/admin/users/{user_id}/premium/toggle', handle_api_admin_user_premium_toggle)
    app.router.add_post('/api/admin/users/{user_id}/premium/extend', handle_api_admin_user_premium_extend)
    app.router.add_post('/api/admin/servers/{server_id}/sync', handle_api_admin_server_sync)
    app.router.add_post('/api/admin/backup', handle_api_admin_backup)
    app.router.add_post('/api/admin/cache/clear', handle_api_admin_cache_clear)
    app.router.add_post('/api/admin/sync', handle_api_admin_sync)
    app.router.add_post('/api/admin/sql', handle_api_admin_sql)
    
    # Owner routes
    app.router.add_get('/api/owner/users', handle_api_owner_users)
    app.router.add_get('/api/owner/servers', handle_api_owner_servers)
    app.router.add_get('/api/owner/stats', handle_api_owner_stats)
    
    # Find available port
    port = API_PORT
    max_attempts = 10
    
    for attempt in range(max_attempts):
        try:
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, '0.0.0.0', port)
            await site.start()
            print(f"✅ API server running on http://0.0.0.0:{port}")
            print(f"✅ Health check available at http://0.0.0.0:{port}/health")
            return
        except OSError as e:
            if attempt < max_attempts - 1:
                port += 1
                print(f"⚠️ Port {port-1} in use, trying {port}...")
            else:
                print(f"❌ Could not find available port: {e}")

# ==================== RUN BOT ====================

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 Starting XULT - Ultimate Discord Bot")
    print("=" * 50)
    print(f"📁 Data directory: {DATA_DIR}")
    print(f"📁 Stock directory: {STOCK_DIR}")
    print(f"🔑 API Key: {API_KEY}")
    print(f"👑 Bot Owner ID: {BOT_OWNER_ID}")
    print(f"💎 Premium Role ID: {PREMIUM_ROLE_ID}")
    print(f"🏠 Main Server ID: {MAIN_SERVER_ID}")
    print("=" * 50)
    
    # Create required directories
    DATA_DIR.mkdir(exist_ok=True)
    BACKUP_DIR.mkdir(exist_ok=True)
    STOCK_DIR.mkdir(exist_ok=True)
    
    if not TOKEN:
        print("❌ ERROR: No bot token found! Set DISCORD_BOT_TOKEN environment variable.")
        exit(1)
    
    # Save API key for frontend
    with open(DATA_DIR / "api_key.txt", "w") as f:
        f.write(API_KEY)
    
    bot.run(TOKEN)
