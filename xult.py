# XULT - Ultimate Discord Bot with Smart Channel Detection
# Complete backend for Render

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
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytz
import xml.etree.ElementTree as ET
from urllib.parse import quote
import difflib
from typing import List, Dict, Any, Optional
import psutil
from aiohttp import web
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ==================== CONFIGURATION ====================

# Bot Token - MUST be from environment variable
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not TOKEN:
    raise ValueError("No Discord bot token found! Set DISCORD_BOT_TOKEN environment variable.")

# Discord OAuth
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')

# API Keys from environment
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
TWITCH_CLIENT_ID = os.getenv('TWITCH_CLIENT_ID')
TWITCH_CLIENT_SECRET = os.getenv('TWITCH_CLIENT_SECRET')
TWITTER_BEARER_TOKEN = os.getenv('TWITTER_BEARER_TOKEN')
GIPHY_API_KEY = os.getenv('GIPHY_API_KEY', 'dimlVnesALO2DLu14diWdZAAcZIgW1L1')

# Bot Owner ID from environment
BOT_OWNER_ID = int(os.getenv('BOT_OWNER_ID'))

# Premium Role ID for vending machine access
PREMIUM_ROLE_ID = int(os.getenv('PREMIUM_ROLE_ID'))

# Main Server ID for role checks
MAIN_SERVER_ID = int(os.getenv('MAIN_SERVER_ID'))

# Log Channel ID for gen usage
GEN_LOG_CHANNEL_ID = int(os.getenv('GEN_LOG_CHANNEL_ID'))

# Target Server ID for logs
TARGET_SERVER_ID = int(os.getenv('TARGET_SERVER_ID'))

# API Configuration
API_PORT = int(os.getenv('PORT', os.getenv('API_PORT', 10000)))
API_KEY = os.getenv('API_KEY', secrets.token_hex(32))

# Directory setup
BASE_DIR = Path.cwd()
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)
STOCK_DIR = BASE_DIR / "stock"
STOCK_DIR.mkdir(exist_ok=True)

# ==================== DATABASE SETUP ====================

conn = sqlite3.connect(DATA_DIR / "xult.db")
c = conn.cursor()

# Users table
c.execute("""CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    avatar TEXT,
    coins INTEGER DEFAULT 0,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    last_daily TIMESTAMP,
    role TEXT DEFAULT 'user',
    premium_expires TIMESTAMP,
    banned INTEGER DEFAULT 0,
    banned_reason TEXT
)""")

# Server configs table
c.execute("""CREATE TABLE IF NOT EXISTS server_configs (
    server_id INTEGER PRIMARY KEY,
    prefix TEXT DEFAULT '!',
    log_channel INTEGER,
    welcome_channel INTEGER,
    welcome_message TEXT,
    leave_channel INTEGER,
    leave_message TEXT,
    auto_role INTEGER,
    mod_role INTEGER,
    admin_role INTEGER,
    muted_role INTEGER,
    config TEXT
)""")

# Command settings table
c.execute("""CREATE TABLE IF NOT EXISTS command_settings (
    server_id INTEGER,
    command_name TEXT,
    enabled INTEGER DEFAULT 1,
    allowed_roles TEXT,
    disabled_channels TEXT,
    PRIMARY KEY (server_id, command_name)
)""")

# Premium users table
c.execute("""CREATE TABLE IF NOT EXISTS premium_users (
    user_id INTEGER PRIMARY KEY,
    guild_id INTEGER,
    role_id INTEGER,
    granted_at TIMESTAMP,
    expires_at TIMESTAMP,
    is_active INTEGER DEFAULT 1
)""")

# Stock usage tracking
c.execute("""CREATE TABLE IF NOT EXISTS stock_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    stock_type TEXT,
    stock_content TEXT,
    generated_at TIMESTAMP,
    server_id INTEGER,
    server_name TEXT,
    channel_id INTEGER,
    channel_name TEXT,
    is_dm INTEGER DEFAULT 0
)""")

# User cooldowns
c.execute("""CREATE TABLE IF NOT EXISTS user_cooldowns (
    user_id INTEGER PRIMARY KEY,
    last_generated TIMESTAMP,
    generation_count INTEGER DEFAULT 0
)""")

# Warnings table
c.execute("""CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    moderator_id INTEGER,
    reason TEXT,
    timestamp TIMESTAMP,
    server_id INTEGER
)""")

# Jailed members table
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

# Logs table
c.execute("""CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT,
    details TEXT,
    ip TEXT,
    timestamp TIMESTAMP
)""")

# Sessions table for web login
c.execute("""CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id INTEGER,
    access_token TEXT,
    refresh_token TEXT,
    expires_at TIMESTAMP,
    created_at TIMESTAMP
)""")

# Economy tables
c.execute("""CREATE TABLE IF NOT EXISTS shop (
    name TEXT PRIMARY KEY,
    price INTEGER,
    description TEXT,
    role_id INTEGER
)""")

c.execute("""CREATE TABLE IF NOT EXISTS lottery (
    user_id INTEGER,
    entry_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)""")

# Notification tables
c.execute("""CREATE TABLE IF NOT EXISTS tracked_channels (
    server_id INTEGER,
    platform TEXT,
    channel_id TEXT,
    last_post_id TEXT,
    role_id INTEGER,
    PRIMARY KEY (server_id, platform, channel_id)
)""")

c.execute("""CREATE TABLE IF NOT EXISTS reaction_roles (
    message_id INTEGER,
    channel_id INTEGER,
    role_id INTEGER,
    emoji TEXT,
    PRIMARY KEY (message_id, emoji)
)""")

c.execute("""CREATE TABLE IF NOT EXISTS role_on_join (
    server_id INTEGER PRIMARY KEY,
    role_id INTEGER,
    delay INTEGER
)""")

c.execute("""CREATE TABLE IF NOT EXISTS bad_words (
    server_id INTEGER,
    word TEXT,
    PRIMARY KEY (server_id, word)
)""")

c.execute("""CREATE TABLE IF NOT EXISTS allowed_channels (
    server_id INTEGER,
    channel_id INTEGER,
    PRIMARY KEY (server_id, channel_id)
)""")

c.execute("""CREATE TABLE IF NOT EXISTS four_twenty (
    server_id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    role_id INTEGER,
    voice_channel_id INTEGER,
    timezone TEXT DEFAULT 'UTC'
)""")

c.execute("""CREATE TABLE IF NOT EXISTS verification (
    server_id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    role_id INTEGER,
    log_channel_id INTEGER,
    message_id INTEGER
)""")

c.execute("""CREATE TABLE IF NOT EXISTS report_channels (
    server_id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    role_id INTEGER
)""")

c.execute("""CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER,
    reporter_id INTEGER,
    reported_id INTEGER,
    reason TEXT,
    evidence TEXT,
    status TEXT DEFAULT 'pending',
    timestamp TIMESTAMP
)""")

# Channel activity tracking
c.execute("""CREATE TABLE IF NOT EXISTS channel_activity (
    channel_id INTEGER PRIMARY KEY,
    server_id INTEGER,
    message_count INTEGER DEFAULT 0,
    unique_users INTEGER DEFAULT 0,
    last_message TIMESTAMP,
    last_reset TIMESTAMP
)""")

conn.commit()

# Initialize shop items
shop_items = [
    ("VIP Role", 500, "Gives VIP role", None),
    ("Double XP", 300, "Double XP for 24h", None),
    ("Mystery Box", 100, "Random coins or reward", None)
]
for name, price, desc, role_id in shop_items:
    c.execute("INSERT OR IGNORE INTO shop (name, price, description, role_id) VALUES (?, ?, ?, ?)", (name, price, desc, role_id))
conn.commit()

# ==================== JSON DATA MANAGEMENT ====================

JSON_FILES = {
    "server_settings": DATA_DIR / "server_settings.json",
    "tracked_channels": DATA_DIR / "tracked_channels.json",
    "role_on_join": DATA_DIR / "role_on_join.json",
    "reaction_role_menus": DATA_DIR / "reaction_role_menus.json",
    "gen_access": DATA_DIR / "gen_access.json",
    "report_channels": DATA_DIR / "report_channels.json",
    "log_channels": DATA_DIR / "log_channels.json",
    "bad_words": DATA_DIR / "bad_words.json",
    "auto_update": DATA_DIR / "auto_update.json",
    "four_twenty": DATA_DIR / "four_twenty.json",
    "verification": DATA_DIR / "verification.json"
}

def init_json_files():
    for name, file_path in JSON_FILES.items():
        if not file_path.exists():
            with open(file_path, 'w') as f:
                json.dump({}, f)

init_json_files()

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
bot.start_time = datetime.now()
bot.owner_id = BOT_OWNER_ID

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
    "accounts": {"name": "General Accounts", "emoji": "👤", "description": "Various account types"},
    "randomip": {"name": "Random IP", "emoji": "🌐", "description": "Random IP addresses"},
    "combo": {"name": "Combos", "emoji": "🔐", "description": "Email:password combinations"}
}

# ==================== GLOBAL VARIABLES ====================

# Cooldowns
user_cooldowns = {}
FREE_GEN_TIMEOUT = 5
PREMIUM_GEN_TIMEOUT = 2
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
    ("What has a heart that doesn't beat?", "artichoke"),
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
    ("What has legs but doesn't walk?", "table"),
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
BLOCK_WORDS = ["nigger", "niggas", "niggers", "jews", "chinks", "nazis", "fags", "fagots", "nigga", "fagot", "discord.gg/"]

# Twitch notifications
notified_streams = {}

# Twitter user cache
user_id_cache = {}

# ==================== SMART CHANNEL DETECTION ====================

EVENT_CHANNEL_KEYWORDS = [
    "general", "chat", "main", "discussion", "lounge", 
    "talk", "global", "world", "public", "community", 
    "social", "offtopic", "off-topic", "general-chat", 
    "main-chat", "town-square", "gen", "general-chat"
]

def normalize_channel_name(name):
    """
    Normalize channel names that use unicode fonts/symbols to plain text.
    
    Examples:
    "💬┃𝔾𝕖𝕟𝕖𝕣𝕒𝕝" -> "general"
    "┃𝗚𝗲𝗻𝗲𝗿𝗮𝗹-𝗰𝗵𝗮𝘁" -> "general-chat"
    "🌟┃𝕄𝕒𝕚𝕟" -> "main"
    """
    # Normalize unicode (decomposes characters)
    name = unicodedata.normalize("NFKD", name)
    
    # Remove emojis and symbols (keep only letters, numbers, spaces, hyphens)
    name = re.sub(r'[^\w\s-]', '', name)
    
    # Convert to lowercase and strip
    return name.lower().strip()

def find_main_chat(guild):
    """
    Find the main chat channel in a server intelligently.
    Handles fancy unicode fonts, emojis, and symbols.
    """
    # First pass: look for channels with keywords
    for channel in guild.text_channels:
        # Skip channels we can't send messages to
        if not channel.permissions_for(guild.me).send_messages:
            continue
        
        # Normalize the channel name
        clean_name = normalize_channel_name(channel.name)
        
        # Check if any keyword is in the normalized name
        if any(keyword in clean_name for keyword in EVENT_CHANNEL_KEYWORDS):
            print(f"✅ Found main chat: {channel.name} -> {clean_name}")
            return channel
    
    # Second pass: get the most active channel from database
    c.execute("""
        SELECT channel_id FROM channel_activity 
        WHERE server_id = ? 
        ORDER BY message_count DESC, last_message DESC 
        LIMIT 1
    """, (guild.id,))
    row = c.fetchone()
    
    if row:
        channel = guild.get_channel(row[0])
        if channel and channel.permissions_for(guild.me).send_messages:
            print(f"📊 Using most active channel: {channel.name}")
            return channel
    
    # Third pass: just get the first text channel
    text_channels = [c for c in guild.text_channels if c.permissions_for(guild.me).send_messages]
    
    if text_channels:
        # Sort by position (usually #general is first)
        text_channels.sort(key=lambda c: c.position)
        print(f"ℹ️ Using fallback channel: {text_channels[0].name}")
        return text_channels[0]
    
    return None

# ==================== STOCK FUNCTIONS ====================

def get_stock_filename(stock_type: str):
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
        # Handle both line breaks and double line breaks
        if '\n\n' in content:
            return len([item for item in content.split('\n\n') if item.strip()])
        else:
            return len([line for line in content.split('\n') if line.strip()])
    except:
        return 0

def read_stock_entries(stock_type: str) -> list:
    filename = get_stock_filename(stock_type)
    create_stock_file(stock_type)
    try:
        content = filename.read_text(encoding="utf-8").strip()
        if not content:
            return []
        # Handle both line breaks and double line breaks
        if '\n\n' in content:
            return [item.strip() for item in content.split('\n\n') if item.strip()]
        else:
            return [line.strip() for line in content.split('\n') if line.strip()]
    except:
        return []

def write_stock_entries(stock_type: str, entries: list):
    filename = get_stock_filename(stock_type)
    with open(filename, "w", encoding="utf-8") as f:
        # Write with double line breaks for better separation
        f.write('\n\n'.join(str(e) for e in entries))

def add_stock_entries(stock_type: str, new_entries: list):
    current = read_stock_entries(stock_type)
    current.extend(new_entries)
    write_stock_entries(stock_type, current)

def get_stock_entry(stock_type: str) -> Optional[str]:
    entries = read_stock_entries(stock_type)
    if not entries:
        return None
    first = entries[0]
    remaining = entries[1:]
    write_stock_entries(stock_type, remaining)
    return first

def is_on_cooldown(user_id: int) -> tuple:
    timeout = FREE_GEN_TIMEOUT
    if user_id == CUSTOM_USER_ID:
        timeout = CUSTOM_USER_TIMEOUT
    
    last_used = user_cooldowns.get(user_id, 0)
    if time.time() - last_used < timeout:
        remaining = int(timeout - (time.time() - last_used))
        return True, remaining
    return False, 0

def set_cooldown(user_id: int):
    user_cooldowns[user_id] = time.time()

# ==================== MODERATION FUNCTIONS ====================

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

def contains_bad_word(message_content: str, guild_id: int) -> bool:
    normalized_content = re.sub(r'[^a-zA-Z0-9\s]', '', message_content.lower())
    words_in_message = normalized_content.split()
    
    for word in BLOCK_WORDS:
        for msg_word in words_in_message:
            if difflib.get_close_matches(msg_word, [word], n=1, cutoff=0.85):
                return True
    
    c.execute("SELECT word FROM bad_words WHERE server_id = ?", (guild_id,))
    server_bad_words = [row[0] for row in c.fetchall()]
    
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

# ==================== TWITCH/API FUNCTIONS ====================

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

# ==================== AUTO-UPDATE FUNCTIONS ====================

async def send_auto_update(bot_instance):
    """Send auto-update to all servers with stock info"""
    auto_update_data = load_json(JSON_FILES["auto_update"], {})
    
    for guild_id, data in auto_update_data.items():
        guild = bot_instance.get_guild(int(guild_id))
        if not guild:
            continue
        
        channel = bot_instance.get_channel(data.get("channel_id"))
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

# ==================== EVENTS ====================

@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')
    print(f'Bot ID: {bot.user.id}')
    print(f'Stock directory: {STOCK_DIR}')
    print(f'Gen Log Channel ID: {GEN_LOG_CHANNEL_ID}')
    print(f'Target Server ID: {TARGET_SERVER_ID}')
    
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
    
    # Track channel activity for smart event detection
    if message.guild and not message.author.bot:
        channel_id = message.channel.id
        server_id = message.guild.id
        
        # Update channel activity
        c.execute("""
            INSERT INTO channel_activity (channel_id, server_id, message_count, unique_users, last_message, last_reset)
            VALUES (?, ?, 1, 1, ?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET
                message_count = message_count + 1,
                unique_users = (
                    SELECT COUNT(DISTINCT user_id) FROM (
                        SELECT ? as user_id UNION ALL
                        SELECT DISTINCT user_id FROM channel_activity WHERE channel_id = ?
                    )
                ),
                last_message = ?
        """, (channel_id, server_id, datetime.now().isoformat(), datetime.now().isoformat(), 
              message.author.id, channel_id, datetime.now().isoformat()))
        conn.commit()
    
    # XP System
    new_level = add_xp(message.author.id, random.randint(1, 5))
    add_coins(message.author.id, random.randint(0, 2))
    
    if new_level:
        await assign_level_role(message.author, new_level)
    
    # Bad word filter
    if message.guild:
        guild_id = message.guild.id
        
        # Check allowed channels
        c.execute("SELECT channel_id FROM allowed_channels WHERE server_id = ?", (guild_id,))
        allowed_channels = [row[0] for row in c.fetchall()]
        
        if message.channel.id not in allowed_channels:
            if contains_bad_word(message.content, guild_id) or filter_bypass_techniques(message.content):
                await message.delete()
                
                # Add warning
                c.execute("INSERT INTO warnings (user_id, moderator_id, reason, timestamp, server_id) VALUES (?, ?, ?, ?, ?)",
                         (message.author.id, bot.user.id, "Inappropriate language", datetime.now().isoformat(), guild_id))
                conn.commit()
                
                c.execute("SELECT COUNT(*) FROM warnings WHERE user_id = ? AND server_id = ?", (message.author.id, guild_id))
                warning_count = c.fetchone()[0]
                
                embed = discord.Embed(
                    title="🚫 Warning!",
                    description=f"{message.author.mention}, watch your language! Keep it clean! 😆",
                    color=discord.Color.red()
                )
                await message.channel.send(embed=embed)
                
                try:
                    dm_embed = discord.Embed(
                        title="⚠️ Warning!",
                        description=f"**Warning {warning_count}/3**\nYou used inappropriate language in **{message.guild.name}**.\nPlease follow the server rules and keep the chat clean.\nAfter 3 warnings, you will be **timed out for 10 minutes**.",
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
                        
                        # Clear warnings
                        c.execute("DELETE FROM warnings WHERE user_id = ? AND server_id = ?", (message.author.id, guild_id))
                        conn.commit()
                    except:
                        pass
                
                # Log action
                config = get_server_config(guild_id)
                if config.get("log_channel"):
                    log_channel = message.guild.get_channel(config["log_channel"])
                    if log_channel:
                        embed = discord.Embed(title="📝 Warning Log", color=discord.Color.red())
                        embed.add_field(name="User", value=message.author.mention, inline=False)
                        embed.add_field(name="Action", value=f"Warning {warning_count}/3", inline=False)
                        embed.add_field(name="Content", value=message.content[:500], inline=False)
                        await log_channel.send(embed=embed)
    
    await bot.process_commands(message)

@bot.event
async def on_member_join(member: discord.Member):
    guild_id = member.guild.id
    
    # Auto role
    c.execute("SELECT role_id, delay FROM role_on_join WHERE server_id = ?", (guild_id,))
    row = c.fetchone()
    if row:
        role_id, delay = row
        role = member.guild.get_role(role_id)
        
        await asyncio.sleep(delay)
        
        try:
            await member.add_roles(role)
        except:
            pass
    
    # Welcome message
    config = get_server_config(guild_id)
    if config.get("welcome_channel") and config.get("welcome_message"):
        channel = member.guild.get_channel(config["welcome_channel"])
        if channel:
            msg = config["welcome_message"].replace("{user}", member.mention).replace("{server}", member.guild.name)
            await channel.send(msg)

@bot.event
async def on_member_remove(member: discord.Member):
    guild_id = member.guild.id
    
    # Leave message
    config = get_server_config(guild_id)
    if config.get("leave_channel") and config.get("leave_message"):
        channel = member.guild.get_channel(config["leave_channel"])
        if channel:
            msg = config["leave_message"].replace("{user}", member.name).replace("{server}", member.guild.name)
            await channel.send(msg)

@bot.event
async def on_voice_state_update(member, before, after):
    config = get_server_config(member.guild.id)
    if config.get("log_channel"):
        log_channel = member.guild.get_channel(config["log_channel"])
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
    if message.author.bot:
        return
    
    config = get_server_config(message.guild.id)
    if config.get("log_channel"):
        log_channel = message.guild.get_channel(config["log_channel"])
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
    
    config = get_server_config(before.guild.id)
    if config.get("log_channel"):
        log_channel = before.guild.get_channel(config["log_channel"])
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

def get_server_config(guild_id: int) -> dict:
    """Get server configuration"""
    c.execute("SELECT * FROM server_configs WHERE server_id = ?", (guild_id,))
    row = c.fetchone()
    if row:
        return {
            "server_id": row[0],
            "prefix": row[1],
            "log_channel": row[2],
            "welcome_channel": row[3],
            "welcome_message": row[4],
            "leave_channel": row[5],
            "leave_message": row[6],
            "auto_role": row[7],
            "mod_role": row[8],
            "admin_role": row[9],
            "muted_role": row[10],
            "config": json.loads(row[11]) if row[11] else {}
        }
    return {"server_id": guild_id, "prefix": "!", "config": {}}

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
    """
    Random event that gives coins to a random member.
    Intelligently finds the main chat channel even with fancy names.
    """
    if not bot.guilds:
        return

    # Pick a random guild
    guild = random.choice(bot.guilds)
    
    # Get non-bot members
    members = [m for m in guild.members if not m.bot]
    if not members:
        return

    # Pick random member
    member = random.choice(members)
    reward = random.randint(5, 30)
    
    # Add coins
    add_coins(member.id, reward)
    
    # Find the main chat channel (handles fancy names)
    channel = find_main_chat(guild)
    
    # For debugging: log what we found
    if channel:
        print(f"🎲 Random event in {guild.name}: {member.name} got {reward} coins in #{channel.name}")
        
        embed = discord.Embed(
            title="🎉 Random Event!",
            description=f"{member.mention} received **{reward} coins!**",
            color=discord.Color.gold()
        )
        embed.set_footer(text="Keep being active for more events!")
        
        await channel.send(embed=embed)
    else:
        print(f"⚠️ Couldn't find a suitable channel in {guild.name}")

@tasks.loop(minutes=5)
async def check_twitter_posts():
    logging.info("🔁 Checking Twitter...")
    
    async with aiohttp.ClientSession() as session:
        c.execute("SELECT server_id, channel_id, role_id FROM tracked_channels WHERE platform = 'twitter'")
        for server_id, channel_id, role_id in c.fetchall():
            guild = bot.get_guild(server_id)
            if not guild:
                continue
            
            channel = guild.get_channel(channel_id)
            if not channel:
                continue
            
            c.execute("SELECT channel_id, last_post_id FROM tracked_channels WHERE server_id = ? AND platform = 'twitter'", (server_id,))
            for twitter_username, last_post_id in c.fetchall():
                try:
                    headers = {"Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"}
                    user_id = await fetch_user_id(session, twitter_username, headers)
                    if not user_id:
                        continue
                    
                    posts_url = f"https://api.twitter.com/2/users/{user_id}/tweets?tweet.fields=created_at&max_results=5"
                    async with session.get(posts_url, headers=headers) as resp:
                        if resp.status != 200:
                            continue
                        
                        posts_data = await resp.json()
                        tweets = posts_data.get("data", [])
                        if not tweets:
                            continue
                        
                        latest_tweet = tweets[0]
                        new_post_id = latest_tweet["id"]
                        
                        if new_post_id == last_post_id:
                            continue
                        
                        c.execute("UPDATE tracked_channels SET last_post_id = ? WHERE server_id = ? AND platform = 'twitter' AND channel_id = ?",
                                 (new_post_id, server_id, twitter_username))
                        conn.commit()
                        
                        embed = discord.Embed(
                            title=f"📢 New Tweet from @{twitter_username}",
                            description=latest_tweet.get("text", "*No content*")[:200],
                            color=discord.Color.blue()
                        )
                        embed.set_author(
                            name=f"@{twitter_username}",
                            url=f"https://twitter.com/{twitter_username}"
                        )
                        
                        role_mention = f"<@&{role_id}>" if role_id else ""
                        await channel.send(content=role_mention, embed=embed)
                except Exception as e:
                    logging.error(f"Twitter error for @{twitter_username}: {e}")
                await asyncio.sleep(2)

@tasks.loop(minutes=3)
async def check_youtube():
    logging.info("🔁 Checking YouTube...")
    
    c.execute("SELECT server_id, channel_id, role_id FROM tracked_channels WHERE platform = 'youtube'")
    for server_id, channel_id, role_id in c.fetchall():
        guild = bot.get_guild(server_id)
        if not guild:
            continue
        
        channel = guild.get_channel(channel_id)
        if not channel:
            continue
        
        c.execute("SELECT channel_id, last_post_id FROM tracked_channels WHERE server_id = ? AND platform = 'youtube'", (server_id,))
        for youtube_channel_id, last_post_id in c.fetchall():
            try:
                rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={youtube_channel_id}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(rss_url) as response:
                        if response.status != 200:
                            continue
                        content = await response.text()
                
                root = ET.fromstring(content)
                namespace = {
                    "yt": "http://www.youtube.com/xml/schemas/2015",
                    "atom": "http://www.w3.org/2005/Atom",
                }
                
                latest_entry = root.find(".//atom:entry", namespace)
                if latest_entry is None:
                    continue
                
                video_id_elem = latest_entry.find("yt:videoId", namespace)
                video_id = video_id_elem.text if video_id_elem is not None else None
                if not video_id:
                    continue
                
                if video_id == last_post_id:
                    continue
                
                c.execute("UPDATE tracked_channels SET last_post_id = ? WHERE server_id = ? AND platform = 'youtube' AND channel_id = ?",
                         (video_id, server_id, youtube_channel_id))
                conn.commit()
                
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
                    url=f"https://www.youtube.com/channel/{youtube_channel_id}",
                    icon_url="https://www.youtube.com/s/desktop/8d3b0b0e/img/favicon_144x144.png"
                )
                embed.set_thumbnail(url=f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg")
                
                role_mention = f"<@&{role_id}>" if role_id else ""
                await channel.send(content=role_mention, embed=embed)
            except Exception as e:
                logging.error(f"YouTube error for {youtube_channel_id}: {e}")

@tasks.loop(minutes=2)
async def check_twitch():
    logging.info("🔁 Checking Twitch...")
    
    oauth_token = await get_twitch_oauth_token()
    if not oauth_token:
        return
    
    async with aiohttp.ClientSession() as session:
        c.execute("SELECT server_id, channel_id, role_id FROM tracked_channels WHERE platform = 'twitch'")
        for server_id, channel_id, role_id in c.fetchall():
            guild = bot.get_guild(server_id)
            if not guild:
                continue
            
            channel = guild.get_channel(channel_id)
            if not channel:
                continue
            
            c.execute("SELECT channel_id, last_post_id FROM tracked_channels WHERE server_id = ? AND platform = 'twitch'", (server_id,))
            for twitch_username, last_post_id in c.fetchall():
                try:
                    url = f"https://api.twitch.tv/helix/streams?user_login={twitch_username}"
                    headers = {"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {oauth_token}"}
                    
                    async with session.get(url, headers=headers) as resp:
                        if resp.status != 200:
                            continue
                        
                        data = await resp.json()
                        if not data.get("data"):
                            notified_streams.pop(twitch_username, None)
                            continue
                        
                        stream_data = data["data"][0]
                        
                        if notified_streams.get(twitch_username) == stream_data["id"]:
                            continue
                        
                        c.execute("UPDATE tracked_channels SET last_post_id = ? WHERE server_id = ? AND platform = 'twitch' AND channel_id = ?",
                                 (stream_data["id"], server_id, twitch_username))
                        conn.commit()
                        notified_streams[twitch_username] = stream_data["id"]
                        
                        embed = discord.Embed(
                            title="📡 Live Now!",
                            description=f"[{stream_data['title']}](https://www.twitch.tv/{twitch_username})",
                            color=discord.Color.purple()
                        )
                        embed.set_author(
                            name=f"{stream_data['user_name']} on Twitch",
                            url=f"https://www.twitch.tv/{twitch_username}",
                            icon_url="https://static.twitchcdn.net/assets/favicon-32-e29e246c157142c94346.png"
                        )
                        embed.set_thumbnail(url=stream_data["thumbnail_url"].replace("{width}", "320").replace("{height}", "180"))
                        embed.add_field(name="Game", value=stream_data.get("game_name", "Unknown"), inline=True)
                        embed.add_field(name="Viewers", value=stream_data.get("viewer_count", 0), inline=True)
                        
                        role_mention = f"<@&{role_id}>" if role_id else ""
                        await channel.send(content=role_mention, embed=embed)
                except Exception as e:
                    logging.error(f"Twitch error for {twitch_username}: {e}")

@tasks.loop(seconds=30)
async def check_unjail():
    now = datetime.utcnow()
    
    c.execute("SELECT server_id, user_id, roles, jail_time, duration FROM jailed_members")
    for server_id, user_id, roles_json, jail_time_str, duration in c.fetchall():
        try:
            jail_time = datetime.strptime(jail_time_str, '%Y-%m-%d %H:%M:%S')
            duration_delta = parse_duration(duration)
            release_time = jail_time + duration_delta
            
            if now >= release_time:
                guild = bot.get_guild(server_id)
                if guild:
                    member = guild.get_member(user_id)
                    if member:
                        roles = json.loads(roles_json)
                        role_objects = [guild.get_role(role_id) for role_id in roles if guild.get_role(role_id)]
                        
                        if role_objects:
                            await member.add_roles(*role_objects, reason="Unjailed")
                        
                        for channel in guild.text_channels + guild.voice_channels:
                            await channel.set_permissions(member, overwrite=None)
                        
                        try:
                            embed = discord.Embed(title="✅ You Have Been Unjailed!", color=discord.Color.green())
                            embed.add_field(name="Server", value=guild.name, inline=False)
                            await member.send(embed=embed)
                        except:
                            pass
                
                c.execute("DELETE FROM jailed_members WHERE server_id = ? AND user_id = ?", (server_id, user_id))
                conn.commit()
        except Exception as e:
            logging.error(f"Error checking unjail for {user_id}: {e}")

@tasks.loop(minutes=1)
async def send_daily_messages():
    c.execute("SELECT server_id, channel_id, role_id, voice_channel_id, timezone FROM four_twenty")
    for server_id, channel_id, role_id, voice_channel_id, timezone_str in c.fetchall():
        guild = bot.get_guild(server_id)
        if not guild:
            continue
        
        try:
            timezone = pytz.timezone(timezone_str)
        except:
            timezone = pytz.UTC
        
        next_time = get_next_schedule_time(timezone)
        now = datetime.now(timezone)
        
        if abs((next_time - now).total_seconds()) < 60:
            await send_four_twenty_message(guild, channel_id, role_id, voice_channel_id)
            await asyncio.sleep(61)

# ==================== VIEW CLASSES ====================

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
        c.execute("SELECT role_id, log_channel_id FROM verification WHERE server_id = ?", (interaction.guild.id,))
        row = c.fetchone()
        
        if not row:
            await interaction.response.send_message("Verification is not set up. Please contact an administrator.", ephemeral=True)
            return
        
        role_id, log_channel_id = row
        
        verified_role = interaction.guild.get_role(role_id)
        if not verified_role:
            await interaction.response.send_message("The verified role is invalid.", ephemeral=True)
            return
        
        if verified_role in interaction.user.roles:
            await interaction.response.send_message("You are already verified!", ephemeral=True)
            return
        
        try:
            await interaction.user.add_roles(verified_role)
            await interaction.response.send_message(f"You have been verified and assigned the '{verified_role.name}' role!", ephemeral=True)
            
            if log_channel_id:
                log_channel = interaction.guild.get_channel(log_channel_id)
                if log_channel:
                    await log_channel.send(f"✅ {interaction.user.mention} has verified.")
        except discord.Forbidden:
            await interaction.response.send_message("I do not have permission to assign roles.", ephemeral=True)

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
        value="`/reactionrole` `/setupverification` `/setverifybutton` `/setreportchannel` `/report` `/setlogchannels` `/save_server` `/load_server`",
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
    
    embed.set_footer(text="XULT - The Ultimate Discord Bot • Dashboard: https://your-vercel-app.vercel.app")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="stocklist", description="List all available stock types")
async def stocklist(interaction: discord.Interaction):
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
    
    # Update username
    c.execute("UPDATE users SET username = ? WHERE id = ?", (str(interaction.user), interaction.user.id))
    conn.commit()
    
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
    responses = ["Yes", "No", "Maybe", "Definitely", "Absolutely not", "Ask again later", "It is certain", "Very doubtful"]
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

# ==================== STOCK/GEN COMMANDS ====================

@bot.tree.command(name="addstock", description="Add stock entries")
async def addstock(interaction: discord.Interaction, stock_type: str, file: discord.Attachment = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    if file and file.filename.endswith(".txt"):
        stock_filename = get_stock_filename(stock_type)
        uploaded_content = await file.read()
        content = uploaded_content.decode("utf-8").strip()
        
        if stock_filename.exists():
            with open(stock_filename, "a", encoding="utf-8") as f:
                f.write("\n\n" + content)
            await interaction.response.send_message(f"✅ Appended to existing {stock_type} stock file.", ephemeral=True)
        else:
            with open(stock_filename, "w", encoding="utf-8") as f:
                f.write(content)
            await interaction.response.send_message(f"✅ Created new {stock_type} stock file.", ephemeral=True)
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

@bot.tree.command(name="gen", description="🎁 Generate a stock entry.")
async def gen_free(interaction: discord.Interaction, stock_type: str):
    """Generate a stock entry with access control."""
    gen_access_data = load_json(JSON_FILES["gen_access"], {})
    guild_id = str(interaction.guild.id)
    allowed_roles = gen_access_data.get(guild_id, [])

    # Check if the user has the required role
    if not any(role.id in allowed_roles for role in interaction.user.roles):
        await interaction.response.send_message(
            "❌ You do not have permission to use this command.", ephemeral=True
        )
        return

    await interaction.response.defer()  # Defer the response to allow time for processing

    # Check if the user is on cooldown
    is_cooldown, remaining = is_on_cooldown(interaction.user.id)
    if is_cooldown:
        await interaction.followup.send(
            f"⏳ {interaction.user.mention}, you must wait `{remaining}` seconds before using this again."
        )
        return

    # Read stock entries
    entries = read_stock_entries(stock_type)
    if not entries:
        await interaction.followup.send(f"❌ {interaction.user.mention}, no free stock available.")
        return

    # Get the first stock entry and remove it from the list
    stock_info = entries.pop(0).strip()
    write_stock_entries(stock_type, entries)

    # Set cooldown for the user
    set_cooldown(interaction.user.id)

    # Try to send the stock info to the user's DMs
    try:
        await interaction.user.send(f"```\n{stock_info}\n```")
        await interaction.followup.send(f"📩 {interaction.user.mention}, stock sent to your DMs!")
    except discord.Forbidden:
        await interaction.followup.send(
            f"❌ {interaction.user.mention}, unable to send you a DM. Please enable direct messages."
        )

    # Send auto-update to all servers
    await send_auto_update(bot)

    # Log the generation in the specified channel in your server
    target_server = bot.get_guild(TARGET_SERVER_ID)

    if target_server:
        # Get the channel in your server where you want the log to be sent
        target_channel = target_server.get_channel(GEN_LOG_CHANNEL_ID)

        if target_channel:
            embed = discord.Embed(
                title="📝 Stock Generation Log",
                description=f"{interaction.user.mention} generated a stock entry.",
                color=discord.Color.blue()
            )
            embed.add_field(name="Stock Type", value=stock_type, inline=True)
            embed.add_field(name="Stock Info", value=f"```\n{stock_info}\n```", inline=False)
            embed.add_field(name="Channel", value=interaction.channel.mention, inline=True)
            embed.add_field(name="Server", value=interaction.guild.name, inline=True)
            embed.set_footer(text=f"User ID: {interaction.user.id}")

            await target_channel.send(embed=embed)
            
    # Save to database
    c.execute("""INSERT INTO stock_usage 
                 (user_id, username, stock_type, stock_content, generated_at, server_id, server_name, channel_id, channel_name, is_dm) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (interaction.user.id, str(interaction.user), stock_type, stock_info, datetime.now().isoformat(),
               interaction.guild.id, interaction.guild.name,
               interaction.channel.id, interaction.channel.name, 0))
    conn.commit()

@bot.tree.command(name="dmgen", description="📩 DM Gen: Get a stock entry directly in DMs.")
async def dm_gen(interaction: discord.Interaction, stock_type: str):
    """Generate stock via DMs. Works only in DMs and for all users."""

    # Ensure it's used in a DM
    if interaction.guild is not None:
        await interaction.response.send_message("❌ This command can only be used in DMs with the bot.", ephemeral=True)
        return

    await interaction.response.defer()

    # Cooldown check
    is_cooldown, remaining = is_on_cooldown(interaction.user.id)
    if is_cooldown:
        await interaction.followup.send(
            f"⏳ You must wait `{remaining}` seconds before using this again.",
            ephemeral=True
        )
        return

    # Load stock
    entries = read_stock_entries(stock_type)
    if not entries:
        await interaction.followup.send("❌ No stock available for that type.", ephemeral=True)
        return

    stock_info = entries.pop(0).strip()
    write_stock_entries(stock_type, entries)
    set_cooldown(interaction.user.id)

    # Send the stock info to the user's DM
    try:
        await interaction.user.send(f"🎁 Here's your stock:\n```\n{stock_info}\n```")
        await interaction.followup.send("✅ Stock sent to your DMs!", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Unable to send DM. Please enable direct messages.", ephemeral=True)
        return

    # 🔁 Send the stock auto-update message
    await send_auto_update(bot)

    # Log the generation in your main server
    target_server = bot.get_guild(TARGET_SERVER_ID)

    if target_server:
        target_channel = target_server.get_channel(GEN_LOG_CHANNEL_ID)
        if target_channel:
            embed = discord.Embed(
                title="📩 DM Stock Generation Log",
                description=f"{interaction.user.mention} generated a stock entry via DMs.",
                color=discord.Color.green()
            )
            embed.add_field(name="Stock Type", value=stock_type, inline=True)
            embed.add_field(name="Stock Info", value=f"```\n{stock_info}\n```", inline=False)
            embed.add_field(name="Location", value="Direct Message", inline=True)
            embed.set_footer(text=f"User ID: {interaction.user.id}")
            await target_channel.send(embed=embed)
            
    # Save to database
    c.execute("""INSERT INTO stock_usage 
                 (user_id, username, stock_type, stock_content, generated_at, server_id, server_name, channel_id, channel_name, is_dm) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (interaction.user.id, str(interaction.user), stock_type, stock_info, datetime.now().isoformat(),
               0, "DM", 0, "DM", 1))
    conn.commit()

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
        
        # Save to database
        roles_json = json.dumps([role.id for role in initial_roles])
        c.execute("INSERT INTO jailed_members (server_id, user_id, roles, jail_time, duration, reason, jailed_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (interaction.guild.id, member.id, roles_json, datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), duration, reason, interaction.user.id))
        conn.commit()
        
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
        c.execute("SELECT roles FROM jailed_members WHERE server_id = ? AND user_id = ?", (interaction.guild.id, member.id))
        row = c.fetchone()
        
        if row:
            roles = json.loads(row[0])
            role_objects = [interaction.guild.get_role(role_id) for role_id in roles if interaction.guild.get_role(role_id)]
            
            if role_objects:
                await member.add_roles(*role_objects, reason="Unjailed")
            
            for channel in interaction.guild.text_channels + interaction.guild.voice_channels:
                await channel.set_permissions(member, overwrite=None)
            
            c.execute("DELETE FROM jailed_members WHERE server_id = ? AND user_id = ?", (interaction.guild.id, member.id))
            conn.commit()
            
            try:
                embed = discord.Embed(title="✅ You Have Been Unjailed!", color=discord.Color.green())
                embed.add_field(name="Reason", value=f"Unjailed by {interaction.user.display_name}", inline=False)
                embed.add_field(name="Server", value=interaction.guild.name, inline=False)
                await member.send(embed=embed)
            except:
                pass
            
            await interaction.followup.send(f"✅ {member.mention} has been unjailed.")
        else:
            await interaction.followup.send(f"{member.mention} is not jailed.")
            
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
    c.execute("SELECT reason, timestamp, moderator_id FROM warnings WHERE user_id = ? AND server_id = ? ORDER BY timestamp DESC", 
             (user.id, interaction.guild.id))
    warnings_list = c.fetchall()
    
    embed = discord.Embed(
        title=f"⚠️ Warnings for {user.display_name}",
        color=discord.Color.orange()
    )
    
    if not warnings_list:
        embed.description = f"{user.mention} has no warnings."
    else:
        embed.description = f"{user.mention} has **{len(warnings_list)}** warnings."
        
        for i, (reason, timestamp, mod_id) in enumerate(warnings_list[:5], 1):
            mod = interaction.guild.get_member(mod_id)
            mod_name = mod.display_name if mod else f"Unknown ({mod_id})"
            date = timestamp[:10] if timestamp else 'Unknown'
            embed.add_field(
                name=f"Warning {i}",
                value=f"**Reason:** {reason}\n**Date:** {date}\n**Mod:** {mod_name}",
                inline=False
            )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="resetwarn", description="Reset a user's warnings")
@app_commands.describe(user="The user to reset warnings for", reason="Reason for resetting warnings")
async def resetwarn(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    c.execute("DELETE FROM warnings WHERE user_id = ? AND server_id = ?", (user.id, interaction.guild.id))
    conn.commit()
    
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
    
    c.execute("INSERT OR REPLACE INTO role_on_join (server_id, role_id, delay) VALUES (?, ?, ?)",
             (interaction.guild.id, role.id, delay_seconds))
    conn.commit()
    
    await interaction.response.send_message(f"✅ Set **{role.name}** to be assigned to new members after {delay}.", ephemeral=True)

@bot.tree.command(name="set_logs", description="Set a channel for logging")
async def set_logs(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    c.execute("INSERT OR REPLACE INTO server_configs (server_id, log_channel) VALUES (?, ?)",
             (interaction.guild.id, channel.id))
    conn.commit()
    
    await interaction.response.send_message(f"✅ Log channel set to {channel.mention}.", ephemeral=True)

@bot.tree.command(name="add_allowed_channel", description="Add a channel where bad words are not moderated")
async def add_allowed_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    c.execute("INSERT OR IGNORE INTO allowed_channels (server_id, channel_id) VALUES (?, ?)",
             (interaction.guild.id, channel.id))
    conn.commit()
    
    await interaction.response.send_message(f"✅ {channel.mention} added to allowed channels.", ephemeral=True)

@bot.tree.command(name="upload_bad_words", description="Upload a .txt file containing bad words to add")
async def upload_bad_words(interaction: discord.Interaction, file: discord.Attachment = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    if not file or not file.filename.endswith(".txt"):
        await interaction.response.send_message("Please upload a valid .txt file.", ephemeral=True)
        return
    
    try:
        file_contents = await file.read()
        lines = file_contents.decode("utf-8", errors="ignore").splitlines()
        new_words = [line.strip().lower() for line in lines if line.strip()]
    except Exception as e:
        await interaction.response.send_message(f"Error reading the file: {e}", ephemeral=True)
        return
    
    for word in new_words:
        c.execute("INSERT OR IGNORE INTO bad_words (server_id, word) VALUES (?, ?)", (interaction.guild.id, word))
    conn.commit()
    
    await interaction.response.send_message(f"✅ Added {len(new_words)} new bad words.", ephemeral=True)

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
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    c.execute("INSERT OR IGNORE INTO tracked_channels (server_id, platform, channel_id, last_post_id) VALUES (?, ?, ?, ?)",
             (interaction.guild.id, 'youtube', channel_id, None))
    conn.commit()
    
    await interaction.response.send_message(f"✅ Now tracking YouTube channel: {channel_id}", ephemeral=True)

@bot.tree.command(name="addtwitchstream", description="Track a Twitch stream for live notifications")
async def addtwitchstream(interaction: discord.Interaction, channel_name: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    channel_name = channel_name.lower()
    c.execute("INSERT OR IGNORE INTO tracked_channels (server_id, platform, channel_id, last_post_id) VALUES (?, ?, ?, ?)",
             (interaction.guild.id, 'twitch', channel_name, None))
    conn.commit()
    
    await interaction.response.send_message(f"✅ Now tracking Twitch stream: {channel_name}", ephemeral=True)

@bot.tree.command(name="addtwitteraccount", description="Track a Twitter/X account for new tweets")
async def addtwitteraccount(interaction: discord.Interaction, username: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    username = username.lower().replace('@', '')
    c.execute("INSERT OR IGNORE INTO tracked_channels (server_id, platform, channel_id, last_post_id) VALUES (?, ?, ?, ?)",
             (interaction.guild.id, 'twitter', username, None))
    conn.commit()
    
    await interaction.response.send_message(f"✅ Now tracking Twitter account: @{username}", ephemeral=True)

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
    
    embed = discord.Embed(
        title="🎭 Reaction Role Menu",
        description="Select a role from the dropdown below to assign or remove it.",
        color=discord.Color.blue()
    )
    embed.add_field(name="Available Roles", value="\n".join([role.name for role in selected_roles]), inline=False)
    
    await interaction.response.send_message(embed=embed, view=RoleView(role_options))

@bot.tree.command(name="setupverification", description="Set up verification system")
async def setupverification(interaction: discord.Interaction, verify_channel: discord.TextChannel, verified_role: discord.Role, log_channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    c.execute("INSERT OR REPLACE INTO verification (server_id, channel_id, role_id, log_channel_id) VALUES (?, ?, ?, ?)",
             (interaction.guild.id, verify_channel.id, verified_role.id, log_channel.id))
    conn.commit()
    
    await interaction.response.send_message(
        f"✅ **Verification Setup Complete:**\n"
        f"Channel: {verify_channel.mention}\n"
        f"Role: {verified_role.mention}\n"
        f"Logs: {log_channel.mention}",
        ephemeral=True
    )

@bot.tree.command(name="setverifybutton", description="Send verification button to the verification channel")
async def setverifybutton(interaction: discord.Interaction):
    c.execute("SELECT channel_id FROM verification WHERE server_id = ?", (interaction.guild.id,))
    row = c.fetchone()
    
    if not row:
        await interaction.response.send_message("❌ Please run `/setupverification` first.", ephemeral=True)
        return
    
    verify_channel_id = row[0]
    verify_channel = interaction.guild.get_channel(verify_channel_id)
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
    
    c.execute("INSERT OR REPLACE INTO report_channels (server_id, channel_id, role_id) VALUES (?, ?, ?)",
             (interaction.guild.id, channel.id, role.id))
    conn.commit()
    
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
    c.execute("SELECT channel_id, role_id FROM report_channels WHERE server_id = ?", (interaction.guild.id,))
    row = c.fetchone()
    
    if not row:
        await interaction.response.send_message("❌ Report channel not set.", ephemeral=True)
        return
    
    report_channel_id, manager_role_id = row
    
    report_channel = bot.get_channel(report_channel_id)
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
    await report_channel.send(content=f"{role_mention}, a new report has been submitted!", embed=embed)
    
    # Save to database
    c.execute("INSERT INTO reports (server_id, reporter_id, reported_id, reason, evidence, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
             (interaction.guild.id, interaction.user.id, user.id if user else None, issue, evidence_text, datetime.now().isoformat()))
    conn.commit()
    
    await interaction.response.send_message("✅ Your report has been submitted.", ephemeral=True)

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
    member_channel: discord.TextChannel = None,
    chat_channel: discord.TextChannel = None,
    voice_channel: discord.TextChannel = None,
    mod_channel: discord.TextChannel = None,
    server_channel: discord.TextChannel = None,
    bot_update_channel: discord.TextChannel = None
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need **Administrator** permissions to use this command.", ephemeral=True)
        return
    
    log_channels = load_json(JSON_FILES["log_channels"], {})
    guild_id = str(interaction.guild.id)
    
    if guild_id not in log_channels:
        log_channels[guild_id] = {}
    
    if member_channel:
        log_channels[guild_id]["member"] = member_channel.id
    if chat_channel:
        log_channels[guild_id]["chat"] = chat_channel.id
    if voice_channel:
        log_channels[guild_id]["voice"] = voice_channel.id
    if mod_channel:
        log_channels[guild_id]["mod"] = mod_channel.id
    if server_channel:
        log_channels[guild_id]["server"] = server_channel.id
    if bot_update_channel:
        log_channels[guild_id]["bot_update"] = bot_update_channel.id
    
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
    
    c.execute("INSERT OR REPLACE INTO four_twenty (server_id, channel_id, role_id, voice_channel_id, timezone) VALUES (?, ?, ?, ?, ?)",
             (interaction.guild.id, daily_channel.id, role.id if role else None, voice_channel.id if voice_channel else None, resolved_timezone.zone))
    conn.commit()
    
    await interaction.response.send_message(
        f"✅ **4:20 Settings Updated:**\n"
        f"Channel: {daily_channel.mention}\n"
        f"Timezone: {resolved_timezone.zone}\n"
        f"Role: {role.mention if role else 'None'}\n"
        f"Voice: {voice_channel.mention if voice_channel else 'None'}"
    )

@bot.tree.command(name="test", description="Send a test 4:20 message")
async def test(interaction: discord.Interaction):
    c.execute("SELECT channel_id, role_id, voice_channel_id FROM four_twenty WHERE server_id = ?", (interaction.guild.id,))
    row = c.fetchone()
    
    if not row:
        await interaction.response.send_message("❌ No 4:20 configuration found for this server.", ephemeral=True)
        return
    
    channel_id, role_id, voice_channel_id = row
    
    channel = interaction.guild.get_channel(channel_id)
    if not channel:
        await interaction.response.send_message("❌ Configured channel not found.", ephemeral=True)
        return
    
    await send_four_twenty_message(interaction.guild, channel_id, role_id, voice_channel_id)
    await interaction.response.send_message("✅ Test message sent!", ephemeral=True)

# ==================== FUN COMMANDS ====================

@bot.tree.command(name="gif", description="Get a GIF from GIPHY")
async def gif(interaction: discord.Interaction, search: str):
    async with aiohttp.ClientSession() as session:
        url = f"https://api.giphy.com/v1/gifs/search?api_key={GIPHY_API_KEY}&q={search}&limit=1&rating=pg"
        async with session.get(url) as resp:
            data = await resp.json()

    embed = discord.Embed(
        title=f"🎬 GIF result for '{search}'",
        color=discord.Color.blue()
    )

    if data.get("data") and data["data"]:
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

# ==================== BROADCAST COMMAND (Owner only) ====================

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
                    embed.set_footer(text=f"Sent by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
                    if thumbnail:
                        embed.set_thumbnail(url=thumbnail.url)
                    embed.timestamp = discord.utils.utcnow()
                    embed.add_field(name="Support", value="Join our [support server](https://discord.gg/pQBKywjW7h)", inline=False)
                    
                    try:
                        await channel.send(embed=embed)
                        sent_count += 1
                    except:
                        pass
    
    await interaction.followup.send(f"✅ Update broadcasted to {sent_count} servers.", ephemeral=True)

# ==================== API SERVER ====================

import asyncio
from aiohttp import web

# Save API key for frontend
with open(DATA_DIR / "api_key.txt", "w") as f:
    f.write(API_KEY)

print(f"🔑 API Key: {API_KEY}")
print(f"📡 API Server will start on port {API_PORT}")

# ==================== API HANDLERS ====================

async def handle_api_key(request):
    """GET /api/key - Public endpoint to get API key for frontend"""
    return web.json_response({"key": API_KEY})

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
        
        # Get recent activity
        c.execute("SELECT user_id, username, stock_type, generated_at FROM stock_usage ORDER BY generated_at DESC LIMIT 10")
        recent = []
        for user_id, username, stock_type, generated_at in c.fetchall():
            time_str = datetime.fromisoformat(generated_at).strftime("%H:%M:%S")
            recent.append({
                "userId": str(user_id),
                "username": username or f"User-{user_id}",
                "type": stock_type,
                "item": stock_type,
                "time": time_str
            })
        
        return web.json_response({
            "total_users": total_users,
            "total_servers": total_servers,
            "total_commands": commands_today,
            "premium_users": premium_users,
            "activity": activity,
            "recent": recent,
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
                "description": STOCK_TYPES.get(stock_type, {}).get("description", ""),
                "cooldown": 5
            }
        
        return web.json_response(stock_data)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

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
                    return web.json_response({"hasPremium": True})
        
        return web.json_response({"hasPremium": False})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

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

async def handle_api_user_servers(request):
    """GET /api/user/servers - Get servers the user can manage"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        servers = []
        for guild in bot.guilds:
            servers.append({
                "id": str(guild.id),
                "name": guild.name,
                "icon": guild.icon.url if guild.icon else None,
                "memberCount": guild.member_count,
                "ownerId": str(guild.owner_id)
            })
        
        return web.json_response(servers)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_server_config(request):
    """GET /api/server/{server_id}/config - Get server config"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        server_id = int(request.match_info.get('server_id'))
        
        # Get server config
        config = get_server_config(server_id)
        
        # Get gen access roles
        gen_access = load_json(JSON_FILES["gen_access"], {})
        gen_roles = gen_access.get(str(server_id), [])
        
        # Get auto update
        auto_update = load_json(JSON_FILES["auto_update"], {})
        auto = auto_update.get(str(server_id), {})
        
        # Get tracked channels
        c.execute("SELECT platform, channel_id, role_id FROM tracked_channels WHERE server_id = ?", (server_id,))
        tracked = {}
        for platform, channel_id, role_id in c.fetchall():
            if platform not in tracked:
                tracked[platform] = []
            tracked[platform].append({
                "channel": channel_id,
                "role": role_id
            })
        
        # Get role on join
        c.execute("SELECT role_id, delay FROM role_on_join WHERE server_id = ?", (server_id,))
        role_on_join = c.fetchone()
        
        # Get allowed channels
        c.execute("SELECT channel_id FROM allowed_channels WHERE server_id = ?", (server_id,))
        allowed_channels = [row[0] for row in c.fetchall()]
        
        # Get four twenty
        c.execute("SELECT channel_id, role_id, voice_channel_id, timezone FROM four_twenty WHERE server_id = ?", (server_id,))
        four_twenty = c.fetchone()
        
        # Get verification
        c.execute("SELECT channel_id, role_id, log_channel_id FROM verification WHERE server_id = ?", (server_id,))
        verification = c.fetchone()
        
        # Get report channel
        c.execute("SELECT channel_id, role_id FROM report_channels WHERE server_id = ?", (server_id,))
        report = c.fetchone()
        
        # Get log channels from JSON
        log_channels = load_json(JSON_FILES["log_channels"], {})
        logs = log_channels.get(str(server_id), {})
        
        return web.json_response({
            "server_id": server_id,
            "config": config,
            "gen_access": gen_roles,
            "auto_update": auto,
            "tracked": tracked,
            "role_on_join": {
                "role_id": role_on_join[0] if role_on_join else None,
                "delay": role_on_join[1] if role_on_join else None
            } if role_on_join else None,
            "allowed_channels": allowed_channels,
            "four_twenty": {
                "channel_id": four_twenty[0],
                "role_id": four_twenty[1],
                "voice_channel_id": four_twenty[2],
                "timezone": four_twenty[3]
            } if four_twenty else None,
            "verification": {
                "channel_id": verification[0],
                "role_id": verification[1],
                "log_channel_id": verification[2]
            } if verification else None,
            "report": {
                "channel_id": report[0],
                "role_id": report[1]
            } if report else None,
            "logs": logs
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_update_gen_access(request):
    """POST /api/server/{server_id}/gen_access - Update gen access roles"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        server_id = request.match_info.get('server_id')
        data = await request.json()
        
        roles = data.get('roles', [])
        
        gen_access = load_json(JSON_FILES["gen_access"], {})
        gen_access[server_id] = roles
        save_json(JSON_FILES["gen_access"], gen_access)
        
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_update_auto_update(request):
    """POST /api/server/{server_id}/auto_update - Update auto update settings"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        server_id = request.match_info.get('server_id')
        data = await request.json()
        
        auto_update = load_json(JSON_FILES["auto_update"], {})
        auto_update[server_id] = {
            "channel_id": data.get("channel_id"),
            "role_id": data.get("role_id")
        }
        save_json(JSON_FILES["auto_update"], auto_update)
        
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_update_logs(request):
    """POST /api/server/{server_id}/logs - Update log channels"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        server_id = request.match_info.get('server_id')
        data = await request.json()
        
        log_channels = load_json(JSON_FILES["log_channels"], {})
        log_channels[server_id] = {
            "member": data.get("member"),
            "chat": data.get("chat"),
            "voice": data.get("voice"),
            "mod": data.get("mod"),
            "server": data.get("server"),
            "bot_update": data.get("bot_update")
        }
        save_json(JSON_FILES["log_channels"], log_channels)
        
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

# Owner API Routes
async def handle_api_owner_users(request):
    """GET /api/owner/users - Get all users with full data (owner only)"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        c.execute("SELECT id, username, coins, xp, level, role, banned FROM users ORDER BY coins DESC")
        users = []
        for user_id, username, coins, xp, level, role, banned in c.fetchall():
            # Check premium
            c.execute("SELECT is_active FROM premium_users WHERE user_id = ?", (user_id,))
            premium_row = c.fetchone()
            is_premium = premium_row and premium_row[0] == 1
            
            # Count warnings
            c.execute("SELECT COUNT(*) FROM warnings WHERE user_id = ?", (user_id,))
            warning_count = c.fetchone()[0]
            
            # Count generations
            c.execute("SELECT COUNT(*) FROM stock_usage WHERE user_id = ?", (user_id,))
            gen_count = c.fetchone()[0]
            
            users.append({
                "id": user_id,
                "username": username or f"User-{user_id}",
                "coins": coins,
                "xp": xp,
                "level": level,
                "role": role or "user",
                "premium": is_premium,
                "banned": bool(banned),
                "warnings": warning_count,
                "generations": gen_count
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
            # Get server config
            config = get_server_config(guild.id)
            
            servers.append({
                "id": guild.id,
                "name": guild.name,
                "icon": guild.icon.url if guild.icon else None,
                "memberCount": guild.member_count,
                "ownerId": guild.owner_id,
                "ownerName": str(guild.owner) if guild.owner else "Unknown",
                "createdAt": guild.created_at.isoformat(),
                "config": config
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
        
        c.execute("SELECT COUNT(*) FROM users WHERE banned = 1")
        banned_users = c.fetchone()[0] or 0
        
        c.execute("SELECT COUNT(*) FROM stock_usage")
        total_generations = c.fetchone()[0] or 0
        
        c.execute("SELECT COUNT(*) FROM warnings")
        total_warnings = c.fetchone()[0] or 0
        
        # Get database size
        db_size = os.path.getsize(DATA_DIR / "xult.db") / (1024 * 1024)  # MB
        
        # Get stock count
        total_stock = 0
        for file in STOCK_DIR.glob("*.txt"):
            count = count_stock(file.stem)
            total_stock += count
        
        return web.json_response({
            "commandsToday": commands_today,
            "premiumUsers": premium_users,
            "bannedUsers": banned_users,
            "totalGenerations": total_generations,
            "totalWarnings": total_warnings,
            "totalStock": total_stock,
            "dbSize": round(db_size, 2)
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_owner_user_toggle_premium(request):
    """POST /api/owner/users/{user_id}/premium - Toggle premium status"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        user_id = int(request.match_info.get('user_id'))
        data = await request.json()
        action = data.get('action', 'toggle')  # 'add', 'remove', or 'toggle'
        
        if action == 'add':
            c.execute("INSERT OR REPLACE INTO premium_users (user_id, guild_id, role_id, granted_at, is_active) VALUES (?, ?, ?, ?, 1)",
                     (user_id, MAIN_SERVER_ID, PREMIUM_ROLE_ID, datetime.now().isoformat()))
        elif action == 'remove':
            c.execute("DELETE FROM premium_users WHERE user_id = ?", (user_id,))
        else:  # toggle
            c.execute("SELECT is_active FROM premium_users WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            if row:
                new_status = 0 if row[0] == 1 else 1
                c.execute("UPDATE premium_users SET is_active = ? WHERE user_id = ?", (new_status, user_id))
            else:
                c.execute("INSERT INTO premium_users (user_id, guild_id, role_id, granted_at, is_active) VALUES (?, ?, ?, ?, 1)",
                         (user_id, MAIN_SERVER_ID, PREMIUM_ROLE_ID, datetime.now().isoformat()))
        
        conn.commit()
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_owner_user_ban(request):
    """POST /api/owner/users/{user_id}/ban - Ban/unban user"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        user_id = int(request.match_info.get('user_id'))
        data = await request.json()
        action = data.get('action', 'ban')  # 'ban' or 'unban'
        reason = data.get('reason', 'No reason provided')
        
        if action == 'ban':
            c.execute("UPDATE users SET banned = 1, banned_reason = ? WHERE id = ?", (reason, user_id))
        else:
            c.execute("UPDATE users SET banned = 0, banned_reason = NULL WHERE id = ?", (user_id,))
        
        conn.commit()
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_owner_user_reset_warnings(request):
    """POST /api/owner/users/{user_id}/warnings/reset - Reset user warnings"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        user_id = int(request.match_info.get('user_id'))
        
        c.execute("DELETE FROM warnings WHERE user_id = ?", (user_id,))
        conn.commit()
        
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_owner_user_add_coins(request):
    """POST /api/owner/users/{user_id}/coins - Add/remove coins"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        user_id = int(request.match_info.get('user_id'))
        data = await request.json()
        amount = data.get('amount', 0)
        
        if amount > 0:
            add_coins(user_id, amount)
        else:
            remove_coins(user_id, abs(amount))
        
        return web.json_response({"success": True, "new_balance": get_balance(user_id)})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_owner_logs(request):
    """GET /api/owner/logs - Get system logs"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        c.execute("SELECT user_id, action, details, timestamp FROM logs ORDER BY timestamp DESC LIMIT 100")
        logs = []
        for user_id, action, details, timestamp in c.fetchall():
            logs.append({
                "userId": user_id,
                "action": action,
                "details": details,
                "time": timestamp
            })
        
        return web.json_response(logs)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_api_owner_stock_usage(request):
    """GET /api/owner/stock/usage - Get stock usage logs"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        c.execute("""SELECT user_id, username, stock_type, stock_content, generated_at, server_name, channel_name, is_dm 
                     FROM stock_usage ORDER BY generated_at DESC LIMIT 100""")
        logs = []
        for user_id, username, stock_type, stock_content, generated_at, server_name, channel_name, is_dm in c.fetchall():
            time_str = datetime.fromisoformat(generated_at).strftime("%Y-%m-%d %H:%M:%S")
            logs.append({
                "userId": user_id,
                "username": username or f"User-{user_id}",
                "type": stock_type,
                "content": stock_content[:50] + "..." if len(stock_content) > 50 else stock_content,
                "time": time_str,
                "server": server_name,
                "channel": channel_name,
                "is_dm": bool(is_dm)
            })
        
        return web.json_response(logs)
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
    app.router.add_get('/api/key', handle_api_key)
    
    # API routes (require API key)
    app.router.add_get('/api/stats', handle_api_stats)
    app.router.add_get('/api/stock', handle_api_stock)
    app.router.add_get('/api/check-premium/{user_id}', handle_api_check_premium)
    app.router.add_get('/api/user/roles/{user_id}', handle_api_user_roles)
    app.router.add_get('/api/user/servers', handle_api_user_servers)
    app.router.add_get('/api/server/{server_id}/config', handle_api_server_config)
    app.router.add_post('/api/server/{server_id}/gen_access', handle_api_update_gen_access)
    app.router.add_post('/api/server/{server_id}/auto_update', handle_api_update_auto_update)
    app.router.add_post('/api/server/{server_id}/logs', handle_api_update_logs)
    
    # Owner routes
    app.router.add_get('/api/owner/users', handle_api_owner_users)
    app.router.add_get('/api/owner/servers', handle_api_owner_servers)
    app.router.add_get('/api/owner/stats', handle_api_owner_stats)
    app.router.add_get('/api/owner/logs', handle_api_owner_logs)
    app.router.add_get('/api/owner/stock/usage', handle_api_owner_stock_usage)
    app.router.add_post('/api/owner/users/{user_id}/premium', handle_api_owner_user_toggle_premium)
    app.router.add_post('/api/owner/users/{user_id}/ban', handle_api_owner_user_ban)
    app.router.add_post('/api/owner/users/{user_id}/warnings/reset', handle_api_owner_user_reset_warnings)
    app.router.add_post('/api/owner/users/{user_id}/coins', handle_api_owner_user_add_coins)
    
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
            print(f"✅ API key endpoint: http://0.0.0.0:{port}/api/key")
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
    print(f"📋 Gen Log Channel ID: {GEN_LOG_CHANNEL_ID}")
    print(f"🎯 Target Server ID: {TARGET_SERVER_ID}")
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
