import asyncio
import aiohttp
import json
import logging
import os
import random
import re
import secrets
import sqlite3
import time
import unicodedata
import difflib
import pytz
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import quote

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import View, Button, Select, Modal, TextInput
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("xult")

# ==================== CONFIGURATION ====================

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN not set!")

CLIENT_ID = os.getenv("CLIENT_ID", "")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("REDIRECT_URI", "https://ultbot-f.vercel.app/callback")

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID", "")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")
GIPHY_API_KEY = os.getenv("GIPHY_API_KEY", "dimlVnesALO2DLu14diWdZAAcZIgW1L1")

BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID", "1302203907782606880"))
PREMIUM_ROLE_ID = int(os.getenv("PREMIUM_ROLE_ID", "1474136325912399994"))
MAIN_SERVER_ID = int(os.getenv("MAIN_SERVER_ID", "1344385779627069541"))
GEN_LOG_CHANNEL_ID = int(os.getenv("GEN_LOG_CHANNEL_ID", "0"))
TARGET_SERVER_ID = int(os.getenv("TARGET_SERVER_ID", "0"))

API_PORT = int(os.getenv("PORT", os.getenv("API_PORT", "10000")))

BASE_DIR = Path.cwd()
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)
STOCK_DIR = BASE_DIR / "stock"
STOCK_DIR.mkdir(exist_ok=True)

DISCORD_API_URL = "https://discord.com/api/v10"
OWNER_ID = 1302203907782606880

# ── Stable API key (survives restarts) ──────────────────────
_KEY_FILE = DATA_DIR / "api_key.txt"
if _KEY_FILE.exists():
    API_KEY = _KEY_FILE.read_text().strip()
else:
    API_KEY = os.getenv("API_KEY", secrets.token_hex(32))
    _KEY_FILE.write_text(API_KEY)

# ==================== DATABASE SETUP ====================

conn = sqlite3.connect(DATA_DIR / "xultt.db", check_same_thread=False)
conn.row_factory = sqlite3.Row
c = conn.cursor()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
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
    banned_reason TEXT,
    access_token TEXT,
    refresh_token TEXT,
    token_expires TIMESTAMP,
    is_owner INTEGER DEFAULT 0,
    premium_verified INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS server_configs (
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
);
CREATE TABLE IF NOT EXISTS command_settings (
    server_id INTEGER,
    command_name TEXT,
    enabled INTEGER DEFAULT 1,
    allowed_roles TEXT,
    disabled_channels TEXT,
    PRIMARY KEY (server_id, command_name)
);
CREATE TABLE IF NOT EXISTS premium_users (
    user_id INTEGER PRIMARY KEY,
    guild_id INTEGER,
    role_id INTEGER,
    granted_at TIMESTAMP,
    expires_at TIMESTAMP,
    is_active INTEGER DEFAULT 1,
    payment_id TEXT,
    payment_method TEXT
);
CREATE TABLE IF NOT EXISTS stock_usage (
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
);
CREATE TABLE IF NOT EXISTS user_cooldowns (
    user_id INTEGER PRIMARY KEY,
    last_generated TIMESTAMP,
    generation_count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    moderator_id INTEGER,
    reason TEXT,
    timestamp TIMESTAMP,
    server_id INTEGER
);
CREATE TABLE IF NOT EXISTS jailed_members (
    server_id INTEGER,
    user_id INTEGER,
    roles TEXT,
    jail_time TIMESTAMP,
    duration TEXT,
    reason TEXT,
    jailed_by INTEGER,
    PRIMARY KEY (server_id, user_id)
);
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT,
    details TEXT,
    ip TEXT,
    timestamp TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id INTEGER,
    access_token TEXT,
    refresh_token TEXT,
    expires_at TIMESTAMP,
    created_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS shop (
    name TEXT PRIMARY KEY,
    price INTEGER,
    description TEXT,
    role_id INTEGER
);
CREATE TABLE IF NOT EXISTS lottery (
    user_id INTEGER,
    entry_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS tracked_channels (
    server_id INTEGER,
    platform TEXT,
    channel_id TEXT,
    last_post_id TEXT,
    role_id INTEGER,
    notify_channel INTEGER,
    PRIMARY KEY (server_id, platform, channel_id)
);
CREATE TABLE IF NOT EXISTS reaction_roles (
    message_id INTEGER,
    channel_id INTEGER,
    role_id INTEGER,
    emoji TEXT,
    PRIMARY KEY (message_id, emoji)
);
CREATE TABLE IF NOT EXISTS role_on_join (
    server_id INTEGER PRIMARY KEY,
    role_id INTEGER,
    delay INTEGER
);
CREATE TABLE IF NOT EXISTS bad_words (
    server_id INTEGER,
    word TEXT,
    PRIMARY KEY (server_id, word)
);
CREATE TABLE IF NOT EXISTS allowed_channels (
    server_id INTEGER,
    channel_id INTEGER,
    PRIMARY KEY (server_id, channel_id)
);
CREATE TABLE IF NOT EXISTS four_twenty (
    server_id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    role_id INTEGER,
    voice_channel_id INTEGER,
    timezone TEXT DEFAULT 'UTC'
);
CREATE TABLE IF NOT EXISTS verification (
    server_id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    role_id INTEGER,
    log_channel_id INTEGER,
    message_id INTEGER,
    verified_role_id INTEGER,
    require_oauth INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS report_channels (
    server_id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    role_id INTEGER
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER,
    reporter_id INTEGER,
    reported_id INTEGER,
    reason TEXT,
    evidence TEXT,
    status TEXT DEFAULT 'pending',
    timestamp TIMESTAMP
);
CREATE TABLE IF NOT EXISTS channel_activity (
    channel_id INTEGER PRIMARY KEY,
    server_id INTEGER,
    message_count INTEGER DEFAULT 0,
    unique_users INTEGER DEFAULT 0,
    last_message TIMESTAMP,
    last_reset TIMESTAMP
);
CREATE TABLE IF NOT EXISTS saved_members (
    user_id INTEGER,
    username TEXT,
    avatar TEXT,
    roles TEXT,
    saved_at TIMESTAMP,
    server_id INTEGER,
    PRIMARY KEY (user_id, server_id)
);
CREATE TABLE IF NOT EXISTS oauth_states (
    state TEXT PRIMARY KEY,
    created_at TIMESTAMP,
    redirect_uri TEXT
);
CREATE TABLE IF NOT EXISTS server_backups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER,
    backup_name TEXT,
    backup_data TEXT,
    created_at TIMESTAMP,
    created_by INTEGER
);
CREATE TABLE IF NOT EXISTS pending_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    payment_id TEXT,
    amount REAL,
    method TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP,
    verified_at TIMESTAMP
);
"""

for stmt in _SCHEMA.strip().split(";"):
    if stmt.strip():
        c.execute(stmt)
conn.commit()

c.execute("INSERT OR IGNORE INTO users (id, username, is_owner, premium_verified) VALUES (?, ?, 1, 1)", (OWNER_ID, "Owner"))
c.execute("UPDATE users SET is_owner = 1, premium_verified = 1 WHERE id = ?", (OWNER_ID,))
conn.commit()

shop_items = [
    ("VIP Role", 500, "Gives VIP role", None),
    ("Double XP", 300, "Double XP for 24h", None),
    ("Mystery Box", 100, "Random coins or reward", None)
]
for name, price, desc, role_id in shop_items:
    c.execute("INSERT OR IGNORE INTO shop (name, price, description, role_id) VALUES (?, ?, ?, ?)",
              (name, price, desc, role_id))
conn.commit()

# ==================== JSON DATA MANAGEMENT ====================

JSON_FILES = {
    "server_settings": DATA_DIR / "server_settings.json",
    "gen_access": DATA_DIR / "gen_access.json",
    "auto_update": DATA_DIR / "auto_update.json",
    "log_channels": DATA_DIR / "log_channels.json",
}

for file_path in JSON_FILES.values():
    if not file_path.exists():
        file_path.write_text("{}")


def load_json(file_path, default=None):
    try:
        return json.loads(file_path.read_text()) or (default if default is not None else {})
    except Exception:
        return default if default is not None else {}


def save_json(file_path, data):
    file_path.write_text(json.dumps(data, indent=2))


def log_action(user_id: int, action: str, details: str = ""):
    c.execute("INSERT INTO logs (user_id, action, details, timestamp) VALUES (?, ?, ?, ?)",
              (user_id, action, details, datetime.now(timezone.utc).isoformat()))
    conn.commit()

# ==================== INTENTS & BOT INIT ====================

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
bot.start_time = datetime.now(timezone.utc)
bot.owner_id = OWNER_ID

# ==================== DYNAMIC COMMAND TREE ====================

class DynamicCommandTree(app_commands.CommandTree):
    """Command tree that hides commands based on permissions"""
    
    def __init__(self, bot):
        super().__init__(bot)
        self._last_interaction = None
    
    async def get_commands_for_guild(self, guild_id: int, user_roles: List[int], is_owner: bool = False):
        """Return only commands visible to this user"""
        visible_commands = []
        
        # Get all commands registered for this guild
        guild_obj = discord.Object(id=guild_id) if guild_id else None
        all_commands = await super().get_commands(guild=guild_obj)
        
        for cmd in all_commands:
            # Skip if command is disabled for this guild
            if not is_command_enabled(guild_id, cmd.name):
                continue
            
            # Skip if user doesn't have required roles
            allowed_roles = get_command_allowed_roles(guild_id, cmd.name)
            if allowed_roles and not any(role in allowed_roles for role in user_roles):
                continue
            
            visible_commands.append(cmd)
        
        return visible_commands
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check permissions before command execution"""
        self._last_interaction = interaction
        
        if not interaction.guild:
            return True
        
        command_name = interaction.command.name if interaction.command else None
        if not command_name:
            return True
        
        # Check if command is enabled
        if not is_command_enabled(interaction.guild.id, command_name):
            await interaction.response.send_message("❌ This command is disabled on this server.", ephemeral=True)
            return False
        
        # Check role restrictions
        allowed_roles = get_command_allowed_roles(interaction.guild.id, command_name)
        if allowed_roles and not any(role.id in allowed_roles for role in interaction.user.roles):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return False
        
        # Check channel restrictions
        disabled_channels = get_command_disabled_channels(interaction.guild.id, command_name)
        if interaction.channel.id in disabled_channels:
            await interaction.response.send_message(f"❌ This command is disabled in {interaction.channel.mention}.", ephemeral=True)
            return False
        
        return True

# ==================== PERMISSION FUNCTIONS ====================

def is_command_enabled(guild_id: int, command_name: str) -> bool:
    c.execute("SELECT enabled FROM command_settings WHERE server_id = ? AND command_name = ?",
              (guild_id, command_name))
    row = c.fetchone()
    return row[0] == 1 if row else True


def get_command_allowed_roles(guild_id: int, command_name: str) -> List[int]:
    c.execute("SELECT allowed_roles FROM command_settings WHERE server_id = ? AND command_name = ?",
              (guild_id, command_name))
    row = c.fetchone()
    if row and row[0]:
        return json.loads(row[0])
    return []


def get_command_disabled_channels(guild_id: int, command_name: str) -> List[int]:
    c.execute("SELECT disabled_channels FROM command_settings WHERE server_id = ? AND command_name = ?",
              (guild_id, command_name))
    row = c.fetchone()
    if row and row[0]:
        return json.loads(row[0])
    return []


def update_command_setting(guild_id: int, command_name: str, enabled: bool,
                           allowed_roles: List[int] = None, disabled_channels: List[int] = None):
    c.execute("""INSERT OR REPLACE INTO command_settings
                 (server_id, command_name, enabled, allowed_roles, disabled_channels)
                 VALUES (?, ?, ?, ?, ?)""",
              (guild_id, command_name.lower(), 1 if enabled else 0,
               json.dumps(allowed_roles) if allowed_roles else None,
               json.dumps(disabled_channels) if disabled_channels else None))
    conn.commit()
    
    # Auto-resync commands for this guild
    asyncio.create_task(sync_guild_commands(guild_id))


async def sync_guild_commands(guild_id: int):
    """Sync commands for a specific guild"""
    try:
        guild = bot.get_guild(guild_id)
        if guild:
            await bot.tree.sync(guild=discord.Object(id=guild_id))
            log.info(f"Synced commands for guild {guild.name} ({guild_id})")
            return True
    except Exception as e:
        log.error(f"Failed to sync guild {guild_id}: {e}")
    return False


async def sync_all_guilds():
    """Sync commands for all guilds"""
    for guild in bot.guilds:
        await sync_guild_commands(guild.id)
        await asyncio.sleep(0.5)

# ==================== STOCK TYPE DEFINITIONS ====================

STOCK_TYPES = {
    "steam": {"name": "Steam Accounts", "emoji": "🎮", "description": "Steam game accounts", "price": 3},
    "netflix": {"name": "Netflix Accounts", "emoji": "🎬", "description": "Netflix premium accounts", "price": 3},
    "spotify": {"name": "Spotify Accounts", "emoji": "🎵", "description": "Spotify premium accounts", "price": 3},
    "discord": {"name": "Discord Nitro", "emoji": "💎", "description": "Discord Nitro codes", "price": 3},
    "minecraft": {"name": "Minecraft Accounts", "emoji": "⛏️", "description": "Minecraft Java accounts", "price": 3},
    "roblox": {"name": "Roblox Accounts", "emoji": "🎮", "description": "Roblox game accounts", "price": 3},
    "epicgames": {"name": "Epic Games", "emoji": "⚡", "description": "Epic Games accounts", "price": 3},
    "ubisoft": {"name": "Ubisoft", "emoji": "🎯", "description": "Ubisoft/Uplay accounts", "price": 3},
    "instagram": {"name": "Instagram", "emoji": "📸", "description": "Instagram accounts", "price": 3},
    "onlyfans": {"name": "OnlyFans", "emoji": "🔞", "description": "OnlyFans premium accounts", "price": 3},
    "mega": {"name": "MEGA Links", "emoji": "📁", "description": "MEGA.nz file links", "price": 3},
    "email": {"name": "Email Accounts", "emoji": "📧", "description": "Email:password combinations", "price": 3},
    "accounts": {"name": "General Accounts", "emoji": "👤", "description": "Various account types", "price": 3},
    "randomip": {"name": "Random IP", "emoji": "🌐", "description": "Random IP addresses", "price": 3},
    "combo": {"name": "Combos", "emoji": "🔐", "description": "Email:password combinations", "price": 3}
}

# ==================== GLOBAL VARIABLES ====================

user_cooldowns = {}
FREE_GEN_TIMEOUT = 5
PREMIUM_GEN_TIMEOUT = 0

LEVEL_ROLES = {5: "Level 5", 10: "Level 10"}

RIDDLES = [
    ("What has keys but can't open locks?", "keyboard"),
    ("What runs but never walks?", "water"),
    ("What has hands but cannot clap?", "clock"),
]
active_riddle = None
riddle_answer = None

BLOCK_WORDS = ["nigger", "niggas", "niggers", "jews", "chinks", "nazis", "fags", "fagots", "nigga", "fagot", "discord.gg/"]
notified_streams = {}
user_id_cache = {}

# ==================== SMART CHANNEL DETECTION ====================

EVENT_CHANNEL_KEYWORDS = [
    "general", "chat", "main", "discussion", "lounge",
    "talk", "global", "world", "public", "community",
    "social", "offtopic", "off-topic", "general-chat",
    "main-chat", "town-square", "gen"
]


def normalize_channel_name(name: str) -> str:
    name = unicodedata.normalize("NFKD", name)
    name = re.sub(r'[^\w\s-]', '', name)
    return name.lower().strip()


def find_main_chat(guild: discord.Guild) -> Optional[discord.TextChannel]:
    for channel in guild.text_channels:
        if not channel.permissions_for(guild.me).send_messages:
            continue
        clean_name = normalize_channel_name(channel.name)
        if any(keyword in clean_name for keyword in EVENT_CHANNEL_KEYWORDS):
            return channel
    c.execute("""SELECT channel_id FROM channel_activity
                 WHERE server_id = ? ORDER BY message_count DESC, last_message DESC LIMIT 1""", (guild.id,))
    row = c.fetchone()
    if row:
        channel = guild.get_channel(row[0])
        if channel and channel.permissions_for(guild.me).send_messages:
            return channel
    text_channels = [ch for ch in guild.text_channels if ch.permissions_for(guild.me).send_messages]
    if text_channels:
        text_channels.sort(key=lambda ch: ch.position)
        return text_channels[0]
    return None

# ==================== STOCK FUNCTIONS ====================

def get_stock_filename(stock_type: str) -> Path:
    return STOCK_DIR / f"{stock_type.lower().strip().replace(' ', '_')}.txt"


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
        if '\n\n' in content:
            return len([item for item in content.split('\n\n') if item.strip()])
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
        if '\n\n' in content:
            return [item.strip() for item in content.split('\n\n') if item.strip()]
        return [line.strip() for line in content.split('\n') if line.strip()]
    except:
        return []


def write_stock_entries(stock_type: str, entries: list):
    filename = get_stock_filename(stock_type)
    filename.write_text('\n\n'.join(str(e) for e in entries), encoding="utf-8")


def get_stock_entry(stock_type: str) -> Optional[str]:
    entries = read_stock_entries(stock_type)
    if not entries:
        return None
    first = entries[0]
    write_stock_entries(stock_type, entries[1:])
    return first


def add_stock_entries(stock_type: str, new_entries: list):
    current = read_stock_entries(stock_type)
    current.extend(new_entries)
    write_stock_entries(stock_type, current)


def is_on_cooldown(user_id: int, is_premium: bool = False) -> Tuple[bool, int]:
    if is_premium:
        return False, 0
    last_used = user_cooldowns.get(user_id, 0)
    elapsed = time.time() - last_used
    if elapsed < FREE_GEN_TIMEOUT:
        return True, int(FREE_GEN_TIMEOUT - elapsed)
    return False, 0


def set_cooldown(user_id: int):
    user_cooldowns[user_id] = time.time()

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
    c.execute("UPDATE users SET coins = ? WHERE id = ?", (max(0, current - amount), user_id))
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
    new_level = int(new_xp ** 0.5)
    if new_level > current_level:
        c.execute("UPDATE users SET level = ? WHERE id = ?", (new_level, user_id))
        conn.commit()
        return True
    return False

# ==================== PREMIUM FUNCTIONS ====================

async def check_user_premium(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    main_guild = bot.get_guild(MAIN_SERVER_ID)
    if not main_guild:
        return False
    member = main_guild.get_member(user_id)
    if not member:
        return False
    premium_role = main_guild.get_role(PREMIUM_ROLE_ID)
    if not premium_role:
        return False
    return premium_role in member.roles


async def assign_premium_role(user_id: int) -> bool:
    main_guild = bot.get_guild(MAIN_SERVER_ID)
    if not main_guild:
        return False
    member = main_guild.get_member(user_id)
    if not member:
        return False
    premium_role = main_guild.get_role(PREMIUM_ROLE_ID)
    if not premium_role:
        return False
    try:
        await member.add_roles(premium_role, reason="Premium purchase verified")
        c.execute("""INSERT OR REPLACE INTO premium_users
                     (user_id, guild_id, role_id, granted_at, is_active)
                     VALUES (?, ?, ?, ?, 1)""",
                  (user_id, MAIN_SERVER_ID, PREMIUM_ROLE_ID, datetime.now(timezone.utc).isoformat()))
        c.execute("UPDATE users SET premium_verified = 1 WHERE id = ?", (user_id,))
        conn.commit()
        return True
    except:
        return False

# ==================== MODERATION FUNCTIONS ====================

def parse_duration(duration: str) -> timedelta:
    duration = duration.lower()
    matches = re.findall(r'(\d+)([smhd])', duration)
    if not matches:
        raise ValueError("Invalid duration format. Use e.g., '10m', '2h', '1d'")
    total = timedelta()
    for amount, unit in matches:
        amount = int(amount)
        if unit == 's': total += timedelta(seconds=amount)
        elif unit == 'm': total += timedelta(minutes=amount)
        elif unit == 'h': total += timedelta(hours=amount)
        elif unit == 'd': total += timedelta(days=amount)
    return total


def contains_bad_word(content: str, guild_id: int) -> bool:
    normalized = re.sub(r'[^a-zA-Z0-9\s]', '', content.lower())
    words = normalized.split()
    for word in BLOCK_WORDS:
        for w in words:
            if difflib.get_close_matches(w, [word], n=1, cutoff=0.85):
                return True
    c.execute("SELECT word FROM bad_words WHERE server_id = ?", (guild_id,))
    for (word,) in c.fetchall():
        for w in words:
            if difflib.get_close_matches(w, [word], n=1, cutoff=0.85):
                return True
    return False


def filter_bypass_techniques(content: str) -> bool:
    patterns = [
        r'([a@][s5][s$]?)', r'([n1][i1][g9][g6]?)', r'([s5][e3]?[x8][t7]?)',
        r'[b8][i1][t7][c3]?', r'[s5][h][i1][t7]?', r'[f@][a4][g9]',
    ]
    for pattern in patterns:
        if re.search(pattern, content.lower()):
            return True
    return False


def get_server_config(guild_id: int) -> dict:
    c.execute("SELECT * FROM server_configs WHERE server_id = ?", (guild_id,))
    row = c.fetchone()
    if row:
        config = json.loads(row["config"]) if row["config"] else {}
        return dict(row, config=config)
    return {"server_id": guild_id, "prefix": "!", "config": {}}


async def assign_level_role(member: discord.Member, level: int):
    if level in LEVEL_ROLES:
        role = discord.utils.get(member.guild.roles, name=LEVEL_ROLES[level])
        if role:
            await member.add_roles(role)

# ==================== ANTI-NUKE / BACKUP ====================

def save_server_backup(guild: discord.Guild):
    backup = {"roles": [], "categories": [], "channels": [], "settings": get_server_config(guild.id)}
    for role in guild.roles:
        if role.name != "@everyone":
            backup["roles"].append({
                "name": role.name, "color": role.color.value, "hoist": role.hoist,
                "mentionable": role.mentionable, "permissions": role.permissions.value,
                "position": role.position
            })
    for cat in guild.categories:
        overwrites = {}
        for target, perm in cat.overwrites.items():
            if isinstance(target, discord.Role):
                allow, deny = perm.pair()
                overwrites[str(target.id)] = {"allow": allow.value, "deny": deny.value}
        backup["categories"].append({"name": cat.name, "position": cat.position, "overwrites": overwrites})
    for ch in guild.text_channels + guild.voice_channels:
        overwrites = {}
        for target, perm in ch.overwrites.items():
            if isinstance(target, discord.Role):
                allow, deny = perm.pair()
                overwrites[str(target.id)] = {"allow": allow.value, "deny": deny.value}
        backup["channels"].append({
            "name": ch.name, "type": "text" if isinstance(ch, discord.TextChannel) else "voice",
            "category": ch.category.name if ch.category else None, "position": ch.position,
            "overwrites": overwrites, "topic": ch.topic if isinstance(ch, discord.TextChannel) else None,
            "slowmode_delay": ch.slowmode_delay if isinstance(ch, discord.TextChannel) else None,
            "bitrate": ch.bitrate if isinstance(ch, discord.VoiceChannel) else None,
            "user_limit": ch.user_limit if isinstance(ch, discord.VoiceChannel) else None
        })
    save_json(BACKUP_DIR / f"{guild.id}.json", backup)
    c.execute("INSERT INTO server_backups (server_id, backup_name, backup_data, created_at, created_by) VALUES (?, ?, ?, ?, ?)",
              (guild.id, f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}", json.dumps(backup),
               datetime.now(timezone.utc).isoformat(), bot.owner_id))
    conn.commit()
    log.info(f"Backup saved for {guild.name} ({guild.id})")


async def load_server_backup(guild: discord.Guild, backup_data: dict = None) -> bool:
    if backup_data is None:
        path = BACKUP_DIR / f"{guild.id}.json"
        backup = load_json(path)
    else:
        backup = backup_data
    if not backup:
        return False
    role_map = {}
    for r in sorted(backup.get("roles", []), key=lambda x: x["position"]):
        try:
            new_role = await guild.create_role(
                name=r["name"], permissions=discord.Permissions(r["permissions"]),
                colour=discord.Colour(r["color"]), hoist=r["hoist"],
                mentionable=r["mentionable"], reason="AntiNuke Restore"
            )
            role_map[r["name"]] = new_role
            await asyncio.sleep(0.5)
        except:
            continue
    cat_map = {}
    for cat in backup.get("categories", []):
        try:
            new_cat = await guild.create_category(name=cat["name"], position=cat["position"], reason="AntiNuke Restore")
            for rid, pair in cat["overwrites"].items():
                role = guild.get_role(int(rid)) or next((r for name, r in role_map.items() if str(r.id) == rid), None)
                if role:
                    perms = discord.PermissionOverwrite.from_pair(discord.Permissions(pair["allow"]), discord.Permissions(pair["deny"]))
                    await new_cat.set_permissions(role, overwrite=perms)
            cat_map[cat["name"]] = new_cat
            await asyncio.sleep(0.5)
        except:
            continue
    for ch in backup.get("channels", []):
        try:
            parent = cat_map.get(ch["category"])
            if ch["type"] == "text":
                new_ch = await guild.create_text_channel(
                    name=ch["name"], category=parent, position=ch["position"],
                    topic=ch.get("topic"), slowmode_delay=ch.get("slowmode_delay", 0), reason="AntiNuke Restore"
                )
            else:
                new_ch = await guild.create_voice_channel(
                    name=ch["name"], category=parent, position=ch["position"],
                    bitrate=ch.get("bitrate", 64000), user_limit=ch.get("user_limit", 0), reason="AntiNuke Restore"
                )
            for rid, pair in ch["overwrites"].items():
                role = guild.get_role(int(rid)) or next((r for name, r in role_map.items() if str(r.id) == rid), None)
                if role:
                    perms = discord.PermissionOverwrite.from_pair(discord.Permissions(pair["allow"]), discord.Permissions(pair["deny"]))
                    await new_ch.set_permissions(role, overwrite=perms)
            await asyncio.sleep(0.5)
        except:
            continue
    return True


async def save_member_data(member: discord.Member):
    roles = [r.id for r in member.roles if r.name != "@everyone"]
    c.execute("""INSERT OR REPLACE INTO saved_members
                 (user_id, username, avatar, roles, saved_at, server_id)
                 VALUES (?, ?, ?, ?, ?, ?)""",
              (member.id, str(member), str(member.avatar.url) if member.avatar else None,
               json.dumps(roles), datetime.now(timezone.utc).isoformat(), member.guild.id))
    conn.commit()


async def restore_member_to_server(member_id: int, target_guild: discord.Guild) -> bool:
    row = c.execute("SELECT username, avatar, roles FROM saved_members WHERE user_id = ?", (member_id,)).fetchone()
    if not row:
        return False
    member = target_guild.get_member(member_id)
    if member:
        roles = [target_guild.get_role(r) for r in json.loads(row["roles"]) if target_guild.get_role(r)]
        if roles:
            await member.add_roles(*roles, reason="Restored from backup")
        return True
    return False


async def save_all_members(guild: discord.Guild):
    for member in guild.members:
        if not member.bot:
            await save_member_data(member)
    log.info(f"Saved {len([m for m in guild.members if not m.bot])} members from {guild.name}")

# ==================== JAIL FUNCTIONS ====================

async def setup_jail_channel(guild: discord.Guild) -> Tuple[discord.TextChannel, discord.VoiceChannel]:
    jail_text = discord.utils.get(guild.text_channels, name="jail")
    if not jail_text:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
        }
        jail_text = await guild.create_text_channel("jail", overwrites=overwrites, reason="Jail system")
    jail_voice = discord.utils.get(guild.voice_channels, name="Jail VC")
    if not jail_voice:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=False, speak=False),
            guild.me: discord.PermissionOverwrite(connect=True, manage_channels=True, mute_members=True),
        }
        jail_voice = await guild.create_voice_channel("Jail VC", overwrites=overwrites, reason="Jail system")
    return jail_text, jail_voice


async def jail_member(member: discord.Member, duration: str, reason: str, moderator: discord.Member):
    jail_text, jail_voice = await setup_jail_channel(member.guild)
    original_roles = [r for r in member.roles if r.name != "@everyone"]
    await member.remove_roles(*original_roles, reason=f"Jailed: {reason}")
    await jail_text.set_permissions(member, read_messages=True, send_messages=True)
    await jail_voice.set_permissions(member, connect=True, speak=True)
    if member.voice and member.voice.channel:
        await member.move_to(jail_voice)
    roles_json = json.dumps([r.id for r in original_roles])
    c.execute("""INSERT OR REPLACE INTO jailed_members
                 (server_id, user_id, roles, jail_time, duration, reason, jailed_by)
                 VALUES (?, ?, ?, ?, ?, ?, ?)""",
              (member.guild.id, member.id, roles_json,
               datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
               duration, reason, moderator.id))
    conn.commit()
    try:
        await member.send(f"🔒 You have been jailed in **{member.guild.name}** for **{duration}**.\nReason: {reason}")
    except:
        pass
    return jail_text, jail_voice


async def unjail_member(member: discord.Member):
    row = c.execute("SELECT roles FROM jailed_members WHERE server_id = ? AND user_id = ?",
                    (member.guild.id, member.id)).fetchone()
    if not row:
        return False
    roles = [member.guild.get_role(r) for r in json.loads(row[0]) if member.guild.get_role(r)]
    if roles:
        await member.add_roles(*roles, reason="Unjailed")
    jail_text = discord.utils.get(member.guild.text_channels, name="jail")
    jail_voice = discord.utils.get(member.guild.voice_channels, name="Jail VC")
    if jail_text:
        await jail_text.set_permissions(member, overwrite=None)
    if jail_voice:
        await jail_voice.set_permissions(member, overwrite=None)
    c.execute("DELETE FROM jailed_members WHERE server_id = ? AND user_id = ?", (member.guild.id, member.id))
    conn.commit()
    try:
        await member.send(f"✅ You have been unjailed from **{member.guild.name}**.")
    except:
        pass
    return True

# ==================== VIEW CLASSES ====================

class DeleteStockDropdown(View):
    def __init__(self, stock_files):
        super().__init__(timeout=60)
        options = [discord.SelectOption(label=f[:100], value=f) for f in stock_files[:25]]
        select = Select(placeholder="Select a stock file to delete", options=options)
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        stock_type = self.children[0].values[0]
        filename = get_stock_filename(stock_type)
        if filename.exists():
            filename.unlink()
            await interaction.response.send_message(f"✅ The `{stock_type}` stock file has been deleted.", ephemeral=True)


class RoleSelect(Select):
    def __init__(self, role_options):
        super().__init__(placeholder="Select a role...", options=role_options[:25], min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(int(self.values[0]))
        if not role:
            return
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


# ==================== VERIFICATION VIEWS ====================

class VerificationView(View):
    """Persistent view — survives bot restarts via custom_id."""

    def __init__(self, require_oauth: bool = True):
        super().__init__(timeout=None)
        self.require_oauth = require_oauth

    @discord.ui.button(
        label="Verify Me",
        style=discord.ButtonStyle.success,
        custom_id="xult_verify_button",
        emoji="✅",
    )
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_verify(interaction)


async def _handle_verify(interaction: discord.Interaction):
    """Core verification logic."""
    row = c.execute(
        "SELECT role_id, log_channel_id, require_oauth FROM verification WHERE server_id = ?",
        (interaction.guild.id,),
    ).fetchone()

    if not row:
        await interaction.response.send_message(
            "❌ Verification is not configured. Ask an admin to run `/setup_oauth_verification`.", ephemeral=True
        )
        return

    role_id, log_channel_id, require_oauth = row["role_id"], row["log_channel_id"], row["require_oauth"]
    verified_role = interaction.guild.get_role(role_id)

    if not verified_role:
        await interaction.response.send_message(
            "❌ The verified role no longer exists. Contact an admin.", ephemeral=True
        )
        return

    if verified_role in interaction.user.roles:
        await interaction.response.send_message("✅ You are already verified!", ephemeral=True)
        return

    if require_oauth:
        oauth_url = (
            f"https://discord.com/api/oauth2/authorize"
            f"?client_id={CLIENT_ID}"
            f"&redirect_uri={quote(REDIRECT_URI)}"
            f"&response_type=code"
            f"&scope=identify+guilds"
            f"&state={interaction.guild.id}:{interaction.user.id}"
        )
        embed = discord.Embed(
            title="🔗 OAuth Verification",
            description=(
                "Click the link below to verify your account via Discord OAuth.\n\n"
                f"[**→ Click here to verify**]({oauth_url})"
            ),
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Non-OAuth path: grant role directly
    try:
        await interaction.user.add_roles(verified_role, reason="XULT Button Verification")
        await interaction.response.send_message(
            f"✅ You've been verified and given **{verified_role.name}**!", ephemeral=True
        )
        log_channel = interaction.guild.get_channel(log_channel_id)
        if log_channel:
            embed = discord.Embed(
                title="✅ Member Verified",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc),
            )
            embed.add_field(name="User", value=f"{interaction.user.mention} (`{interaction.user.id}`)")
            embed.add_field(name="Method", value="Button (no OAuth)")
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            await log_channel.send(embed=embed)
        log_action(interaction.user.id, "VERIFIED", f"guild={interaction.guild.id} method=button")
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ I don't have permission to assign that role. Make sure my role is above the verified role.", ephemeral=True
        )

# ==================== EVENTS ====================

@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user} ({bot.user.id})")
    
    # Replace the command tree with dynamic version
    bot.tree = DynamicCommandTree(bot)

    for stock_type in STOCK_TYPES:
        create_stock_file(stock_type)

    # Re-register persistent verification views
    rows = c.execute("SELECT require_oauth FROM verification").fetchall()
    for row in rows:
        bot.add_view(VerificationView(require_oauth=bool(row["require_oauth"])))
    log.info(f"Re-registered {len(rows)} persistent verification view(s)")

    for guild in bot.guilds:
        try:
            await bot.tree.sync(guild=discord.Object(id=guild.id))
            log.info(f"Synced commands for {guild.name}")
        except Exception as e:
            log.error(f"Failed to sync for {guild.name}: {e}")

    daily_coins.start()
    random_event_loop.start()
    check_youtube.start()
    check_twitch.start()
    check_twitter_posts.start()
    check_unjail.start()
    send_daily_messages.start()

    bot.loop.create_task(start_api_server())
    log.info("All background tasks started")


@bot.event
async def on_guild_join(guild: discord.Guild):
    save_server_backup(guild)
    await save_all_members(guild)
    try:
        await bot.tree.sync(guild=discord.Object(id=guild.id))
        log.info(f"Synced commands for new guild: {guild.name}")
    except Exception as e:
        log.error(f"Failed to sync for {guild.name}: {e}")


@bot.event
async def on_member_join(member: discord.Member):
    c.execute("SELECT role_id, delay FROM role_on_join WHERE server_id = ?", (member.guild.id,))
    row = c.fetchone()
    if row:
        await asyncio.sleep(row["delay"])
        role = member.guild.get_role(row["role_id"])
        if role:
            try:
                await member.add_roles(role)
            except:
                pass
    config = get_server_config(member.guild.id)
    if config.get("welcome_channel") and config.get("welcome_message"):
        channel = member.guild.get_channel(config["welcome_channel"])
        if channel:
            msg = config["welcome_message"].replace("{user}", member.mention).replace("{server}", member.guild.name)
            await channel.send(msg)
    await save_member_data(member)


@bot.event
async def on_member_remove(member: discord.Member):
    config = get_server_config(member.guild.id)
    if config.get("leave_channel") and config.get("leave_message"):
        channel = member.guild.get_channel(config["leave_channel"])
        if channel:
            msg = config["leave_message"].replace("{user}", member.name).replace("{server}", member.guild.name)
            await channel.send(msg)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        await bot.process_commands(message)
        return

    c.execute("""INSERT INTO channel_activity (channel_id, server_id, message_count, unique_users, last_message, last_reset)
                 VALUES (?, ?, 1, 1, ?, ?)
                 ON CONFLICT(channel_id) DO UPDATE SET
                 message_count = message_count + 1,
                 last_message = ?""",
              (message.channel.id, message.guild.id,
               datetime.now(timezone.utc).isoformat(),
               datetime.now(timezone.utc).isoformat(),
               datetime.now(timezone.utc).isoformat()))
    conn.commit()

    new_level = add_xp(message.author.id, random.randint(1, 5))
    add_coins(message.author.id, random.randint(0, 2))
    if new_level:
        await assign_level_role(message.author, get_level(message.author.id))

    if is_command_enabled(message.guild.id, "moderation"):
        c.execute("SELECT channel_id FROM allowed_channels WHERE server_id = ?", (message.guild.id,))
        allowed = [row[0] for row in c.fetchall()]
        if message.channel.id not in allowed and (contains_bad_word(message.content, message.guild.id) or filter_bypass_techniques(message.content)):
            await message.delete()
            c.execute("INSERT INTO warnings (user_id, moderator_id, reason, timestamp, server_id) VALUES (?, ?, ?, ?, ?)",
                      (message.author.id, bot.user.id, "Inappropriate language",
                       datetime.now(timezone.utc).isoformat(), message.guild.id))
            conn.commit()
            c.execute("SELECT COUNT(*) FROM warnings WHERE user_id = ? AND server_id = ?",
                      (message.author.id, message.guild.id))
            warning_count = c.fetchone()[0]
            embed = discord.Embed(title="🚫 Warning!",
                                 description=f"{message.author.mention}, watch your language! Warning {warning_count}/3",
                                 color=discord.Color.red())
            await message.channel.send(embed=embed, delete_after=5)
            if warning_count >= 3:
                try:
                    await message.author.timeout(discord.utils.utcnow() + timedelta(minutes=10),
                                                reason="3 warnings for inappropriate language")
                    c.execute("DELETE FROM warnings WHERE user_id = ? AND server_id = ?",
                             (message.author.id, message.guild.id))
                    conn.commit()
                except:
                    pass

    await bot.process_commands(message)

# ==================== BACKGROUND TASKS ====================

@tasks.loop(hours=24)
async def daily_coins():
    c.execute("SELECT id FROM users")
    for (user_id,) in c.fetchall():
        add_coins(user_id, 50)
    log.info("Daily coins distributed")


@tasks.loop(minutes=60)
async def random_event_loop():
    if not bot.guilds:
        return
    guild = random.choice(bot.guilds)
    members = [m for m in guild.members if not m.bot]
    if not members:
        return
    member = random.choice(members)
    reward = random.randint(5, 30)
    add_coins(member.id, reward)
    channel = find_main_chat(guild)
    if channel:
        embed = discord.Embed(title="🎉 Random Event!",
                             description=f"{member.mention} received **{reward} coins!**",
                             color=discord.Color.gold())
        await channel.send(embed=embed)


@tasks.loop(minutes=3)
async def check_youtube():
    rows = c.execute("SELECT server_id, channel_id, last_post_id, role_id FROM tracked_channels WHERE platform = 'youtube'").fetchall()
    for server_id, channel_id, last_id, role_id in rows:
        guild = bot.get_guild(server_id)
        if not guild:
            continue
        channel = guild.get_channel(channel_id)
        if not channel:
            continue
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}") as resp:
                    if resp.status != 200:
                        continue
                    content = await resp.text()
            root = ET.fromstring(content)
            ns = {"yt": "http://www.youtube.com/xml/schemas/2015", "atom": "http://www.w3.org/2005/Atom"}
            entry = root.find(".//atom:entry", ns)
            if entry is None:
                continue
            video_id = entry.find("yt:videoId", ns)
            if video_id is None or video_id.text == last_id:
                continue
            title = entry.find("atom:title", ns).text or "New Video"
            channel_name = root.find(".//atom:title", ns).text or "YouTube Channel"
            c.execute("UPDATE tracked_channels SET last_post_id = ? WHERE server_id = ? AND platform = 'youtube' AND channel_id = ?",
                      (video_id.text, server_id, channel_id))
            conn.commit()
            embed = discord.Embed(title="🎥 New YouTube Upload!",
                                 description=f"**{title}**\n[Watch Video](https://youtu.be/{video_id.text})",
                                 color=discord.Color.red())
            embed.set_author(name=channel_name, url=f"https://www.youtube.com/channel/{channel_id}")
            embed.set_thumbnail(url=f"https://i.ytimg.com/vi/{video_id.text}/hqdefault.jpg")
            role_mention = f"<@&{role_id}>" if role_id else ""
            await channel.send(content=role_mention, embed=embed)
        except Exception as e:
            log.error(f"YouTube error: {e}")


@tasks.loop(minutes=2)
async def check_twitch():
    if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
        return
    async with aiohttp.ClientSession() as session:
        async with session.post("https://id.twitch.tv/oauth2/token",
                                params={"client_id": TWITCH_CLIENT_ID, "client_secret": TWITCH_CLIENT_SECRET,
                                        "grant_type": "client_credentials"}) as resp:
            if resp.status != 200:
                return
            oauth_data = await resp.json()
            oauth = oauth_data.get("access_token")
            if not oauth:
                return
    rows = c.execute("SELECT server_id, channel_id, last_post_id, role_id FROM tracked_channels WHERE platform = 'twitch'").fetchall()
    async with aiohttp.ClientSession() as session:
        for server_id, channel_id, last_id, role_id in rows:
            guild = bot.get_guild(server_id)
            if not guild:
                continue
            channel = guild.get_channel(channel_id)
            if not channel:
                continue
            try:
                headers = {"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {oauth}"}
                async with session.get(f"https://api.twitch.tv/helix/streams?user_login={channel_id}", headers=headers) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    if not data.get("data"):
                        notified_streams.pop(channel_id, None)
                        continue
                    stream = data["data"][0]
                    if notified_streams.get(channel_id) == stream["id"]:
                        continue
                    c.execute("UPDATE tracked_channels SET last_post_id = ? WHERE server_id = ? AND platform = 'twitch' AND channel_id = ?",
                              (stream["id"], server_id, channel_id))
                    conn.commit()
                    notified_streams[channel_id] = stream["id"]
                    embed = discord.Embed(title="📡 Live Now!",
                                         description=f"[{stream['title']}](https://www.twitch.tv/{channel_id})",
                                         color=discord.Color.purple())
                    embed.set_author(name=f"{stream['user_name']} on Twitch", url=f"https://www.twitch.tv/{channel_id}")
                    embed.set_thumbnail(url=stream["thumbnail_url"].replace("{width}", "320").replace("{height}", "180"))
                    embed.add_field(name="Game", value=stream.get("game_name", "Unknown"), inline=True)
                    embed.add_field(name="Viewers", value=stream.get("viewer_count", 0), inline=True)
                    role_mention = f"<@&{role_id}>" if role_id else ""
                    await channel.send(content=role_mention, embed=embed)
            except Exception as e:
                log.error(f"Twitch error: {e}")


@tasks.loop(minutes=5)
async def check_twitter_posts():
    if not TWITTER_BEARER_TOKEN:
        return
    rows = c.execute("SELECT server_id, channel_id, last_post_id, role_id FROM tracked_channels WHERE platform = 'twitter'").fetchall()
    async with aiohttp.ClientSession() as session:
        for server_id, channel_id, last_id, role_id in rows:
            guild = bot.get_guild(server_id)
            if not guild:
                continue
            channel = guild.get_channel(channel_id)
            if not channel:
                continue
            try:
                headers = {"Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"}
                async with session.get(f"https://api.twitter.com/2/users/by/username/{quote(channel_id)}", headers=headers) as resp:
                    if resp.status != 200:
                        continue
                    user_data = await resp.json()
                    uid = user_data.get("data", {}).get("id")
                    if not uid:
                        continue
                    async with session.get(f"https://api.twitter.com/2/users/{uid}/tweets?tweet.fields=created_at&max_results=5", headers=headers) as tweets_resp:
                        if tweets_resp.status != 200:
                            continue
                        tweets_data = await tweets_resp.json()
                        tweets = tweets_data.get("data", [])
                        if not tweets or tweets[0]["id"] == last_id:
                            continue
                        tweet = tweets[0]
                        c.execute("UPDATE tracked_channels SET last_post_id = ? WHERE server_id = ? AND platform = 'twitter' AND channel_id = ?",
                                  (tweet["id"], server_id, channel_id))
                        conn.commit()
                        embed = discord.Embed(title=f"📢 New Tweet from @{channel_id}",
                                             description=tweet.get("text", "*No content*")[:200],
                                             color=discord.Color.blue())
                        embed.set_author(name=f"@{channel_id}", url=f"https://twitter.com/{channel_id}")
                        role_mention = f"<@&{role_id}>" if role_id else ""
                        await channel.send(content=role_mention, embed=embed)
            except Exception as e:
                log.error(f"Twitter error: {e}")
            await asyncio.sleep(2)


@tasks.loop(seconds=30)
async def check_unjail():
    rows = c.execute("SELECT server_id, user_id, roles, jail_time, duration FROM jailed_members").fetchall()
    now = datetime.now(timezone.utc)
    for server_id, user_id, roles_json, jail_time_str, duration in rows:
        try:
            jail_time = datetime.strptime(jail_time_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            release = jail_time + parse_duration(duration)
            if now >= release:
                guild = bot.get_guild(server_id)
                if guild:
                    member = guild.get_member(user_id)
                    if member:
                        await unjail_member(member)
                else:
                    c.execute("DELETE FROM jailed_members WHERE server_id = ? AND user_id = ?", (server_id, user_id))
                    conn.commit()
        except Exception as e:
            log.error(f"Unjail error: {e}")


@tasks.loop(minutes=1)
async def send_daily_messages():
    rows = c.execute("SELECT server_id, channel_id, role_id, voice_channel_id, timezone FROM four_twenty").fetchall()
    for server_id, channel_id, role_id, voice_channel_id, tz_str in rows:
        guild = bot.get_guild(server_id)
        if not guild:
            continue
        try:
            tz = pytz.timezone(tz_str or "UTC")
        except:
            tz = pytz.UTC
        now = datetime.now(tz)
        if now.hour in (4, 16) and now.minute == 20:
            channel = guild.get_channel(channel_id)
            if channel:
                role_mention = f"<@&{role_id}>" if role_id else ""
                vc = guild.get_channel(voice_channel_id) if voice_channel_id else None
                voice_link = f"[Join voice chat!]({vc.jump_url})" if vc else "No voice chat configured."
                embed = discord.Embed(title="It's 4:20! 🌿",
                                     description=f"Join the session! {voice_link}\n{role_mention}",
                                     color=discord.Color.green())
                await channel.send(embed=embed)
                await asyncio.sleep(61)


async def send_auto_update(bot_instance):
    auto_update_data = load_json(JSON_FILES["auto_update"], {})
    for guild_id, data in auto_update_data.items():
        guild = bot_instance.get_guild(int(guild_id))
        if not guild:
            continue
        channel = bot_instance.get_channel(data.get("channel_id"))
        if not channel:
            continue
        role_mention = f"<@&{data['role_id']}>" if data.get("role_id") else ""
        stock_info = []
        for file in STOCK_DIR.glob("*.txt"):
            count = count_stock(file.stem)
            stock_info.append(f"➜ **{file.stem.capitalize()}**: `{count}` entries")
            if len(stock_info) >= 20:
                break
        embed = discord.Embed(title="📦 Stock Update", color=discord.Color.green())
        embed.add_field(name="Stock", value="\n".join(stock_info) if stock_info else "🚫 No stock available.", inline=False)
        embed.set_footer(text="Stock updates are live! 🔄")
        try:
            await channel.send(content=f"📢 {role_mention}, latest stock update!", embed=embed)
        except:
            pass

# ==================== SLASH COMMANDS ====================

# ── VERIFICATION ──────────────────────────────────────────────
@bot.tree.command(
    name="setup_oauth_verification",
    description="Set up the verification system for this server",
)
@app_commands.describe(
    verify_channel="Channel where the verification button is posted",
    verified_role="Role granted after successful verification",
    log_channel="Channel where verification logs are sent",
    require_oauth="Require Discord OAuth login to verify (default: True)",
)
async def setup_oauth_verification(
    interaction: discord.Interaction,
    verify_channel: discord.TextChannel,
    verified_role: discord.Role,
    log_channel: discord.TextChannel,
    require_oauth: bool = True,
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    c.execute(
        """INSERT OR REPLACE INTO verification
           (server_id, channel_id, role_id, log_channel_id, verified_role_id, require_oauth)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (interaction.guild.id, verify_channel.id, verified_role.id,
         log_channel.id, verified_role.id, 1 if require_oauth else 0),
    )
    conn.commit()

    embed = discord.Embed(
        title="✅ Verification Required",
        description=(
            f"To gain access to **{interaction.guild.name}**, you must verify your account.\n\n"
            f"Click the button below to begin."
        ),
        color=discord.Color.red(),
    )
    embed.set_footer(
        text=f"{interaction.guild.name} • Powered by XULT",
        icon_url=interaction.guild.icon.url if interaction.guild.icon else None,
    )

    view = VerificationView(require_oauth=require_oauth)
    try:
        msg = await verify_channel.send(embed=embed, view=view)
        c.execute("UPDATE verification SET message_id = ? WHERE server_id = ?", (msg.id, interaction.guild.id))
        conn.commit()
        bot.add_view(view)
    except discord.Forbidden:
        await interaction.followup.send(f"❌ Cannot send messages in {verify_channel.mention}.", ephemeral=True)
        return

    await interaction.followup.send(
        f"✅ Verification set up successfully!\n"
        f"📌 Verify channel: {verify_channel.mention}\n"
        f"🏷️ Verified role: {verified_role.mention}\n"
        f"📋 Log channel: {log_channel.mention}\n"
        f"🔗 OAuth required: **{'Yes' if require_oauth else 'No'}**",
        ephemeral=True,
    )
    log_action(interaction.user.id, "SETUP_VERIFICATION",
               f"guild={interaction.guild.id} channel={verify_channel.id} role={verified_role.id}")


@bot.tree.command(name="verify", description="Manually trigger the verification process")
async def verify_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("This command only works in servers.", ephemeral=True)
        return
    await _handle_verify(interaction)


# ── OWNER COMMANDS ────────────────────────────────────────────
@bot.tree.command(name="owner_panel", description="[Owner] Open the bot management panel")
async def owner_panel(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        return
    embed = discord.Embed(title="👑 XULT Owner Panel", color=discord.Color.gold())
    embed.add_field(name="Servers", value=str(len(bot.guilds)), inline=True)
    embed.add_field(name="Latency", value=f"{round(bot.latency*1000,2)}ms", inline=True)
    embed.add_field(name="Uptime", value=str(datetime.now(timezone.utc)-bot.start_time).split('.')[0], inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="owner_stats", description="[Owner] Get detailed bot statistics")
async def owner_stats(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        return
    total_users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_servers = len(bot.guilds)
    premium_users = c.execute("SELECT COUNT(*) FROM premium_users WHERE is_active = 1").fetchone()[0]
    banned_users = c.execute("SELECT COUNT(*) FROM users WHERE banned = 1").fetchone()[0]
    total_warnings = c.execute("SELECT COUNT(*) FROM warnings").fetchone()[0]
    stock_total = sum(count_stock(f.stem) for f in STOCK_DIR.glob("*.txt"))
    embed = discord.Embed(title="📊 XULT Statistics", color=discord.Color.gold())
    embed.add_field(name="👥 Users", value=f"{total_users:,}", inline=True)
    embed.add_field(name="🏠 Servers", value=f"{total_servers:,}", inline=True)
    embed.add_field(name="⭐ Premium", value=f"{premium_users:,}", inline=True)
    embed.add_field(name="🚫 Banned", value=f"{banned_users:,}", inline=True)
    embed.add_field(name="⚠️ Warnings", value=f"{total_warnings:,}", inline=True)
    embed.add_field(name="📦 Stock", value=f"{stock_total:,}", inline=True)
    embed.add_field(name="📡 Latency", value=f"{round(bot.latency*1000,2)}ms", inline=True)
    embed.add_field(name="⏰ Uptime", value=str(datetime.now(timezone.utc)-bot.start_time).split('.')[0], inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="broadcastupdate", description="[Owner] Broadcast update to all servers")
@app_commands.describe(message="Update message", thumbnail="Thumbnail image")
async def broadcastupdate(interaction: discord.Interaction, message: str, thumbnail: discord.Attachment = None):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    log_channels = load_json(JSON_FILES["log_channels"], {})
    sent = 0
    for guild_id, channels in log_channels.items():
        ch_id = channels.get("bot_update")
        if ch_id:
            guild = bot.get_guild(int(guild_id))
            if guild:
                channel = guild.get_channel(int(ch_id))
                if channel:
                    embed = discord.Embed(title="📢 XULT Bot Update", description=message,
                                         color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
                    embed.set_footer(text=f"Sent by {interaction.user.display_name}")
                    if thumbnail:
                        embed.set_thumbnail(url=thumbnail.url)
                    try:
                        await channel.send(embed=embed)
                        sent += 1
                    except:
                        pass
    await interaction.followup.send(f"✅ Broadcasted to {sent} servers.", ephemeral=True)


@bot.tree.command(name="pull", description="[Owner] Pull saved members to a server")
@app_commands.describe(target_server="Target server ID or name", count="Number of members to pull (default: all)")
async def pull_members(interaction: discord.Interaction, target_server: str, count: str = "all"):
    """Owner-only command to pull saved members to a server"""
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    # Find target guild
    target_guild = None
    for guild in bot.guilds:
        if str(guild.id) == target_server or guild.name.lower() == target_server.lower():
            target_guild = guild
            break
    
    if not target_guild:
        await interaction.followup.send(f"❌ Server '{target_server}' not found.", ephemeral=True)
        return
    
    # Get saved members
    saved = c.execute("SELECT DISTINCT user_id FROM saved_members").fetchall()
    if not saved:
        await interaction.followup.send("❌ No saved members found in database.", ephemeral=True)
        return
    
    # Determine how many to pull
    if str(count).lower() == "all":
        members_to_pull = [r[0] for r in saved]
    else:
        try:
            limit = int(count)
            members_to_pull = [r[0] for r in saved[:limit]]
        except ValueError:
            await interaction.followup.send("❌ Count must be a number or 'all'.", ephemeral=True)
            return
    
    # Pull members
    success_count = 0
    for uid in members_to_pull:
        if await restore_member_to_server(uid, target_guild):
            success_count += 1
        await asyncio.sleep(0.3)  # Rate limiting
    
    await interaction.followup.send(
        f"✅ Pulled {success_count}/{len(members_to_pull)} members to **{target_guild.name}**.",
        ephemeral=True
    )
    log_action(interaction.user.id, "PULL_MEMBERS", f"target={target_guild.id} count={success_count}")


# ── HELP ──────────────────────────────────────────────────────
@bot.tree.command(name="help", description="Get information about the bot and its commands")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="🤖 XULT - Ultimate Discord Bot",
                         description="Your all-in-one solution!", color=discord.Color.red())
    embed.add_field(name="💰 Economy & Games",
                   value="`/balance` `/daily` `/coinflip` `/rps` `/slots` `/blackjack` `/joke` `/eightball` `/riddle`", inline=False)
    embed.add_field(name="📦 Stock/Generator",
                   value="`/addstock` `/deletestock` `/gen` `/dmgen` `/setgenaccess` `/setautoupdate` `/stocklist`", inline=False)
    embed.add_field(name="🛡️ Moderation",
                   value="`/jail` `/unjail` `/purge` `/warnings` `/resetwarn` `/setroleonjoin` `/set_logs` `/add_allowed_channel` `/upload_bad_words` `/sendnotice`", inline=False)
    embed.add_field(name="🔐 Verification",
                   value="`/setup_oauth_verification` `/verify`", inline=False)
    embed.add_field(name="📢 Notifications",
                   value="`/setnotichannel` `/addyoutubechannel` `/addtwitchstream` `/addtwitteraccount`", inline=False)
    embed.add_field(name="⚙️ Server Management",
                   value="`/reactionrole` `/setreportchannel` `/report` `/setlogchannels` `/save_server` `/load_server`", inline=False)
    embed.add_field(name="🎮 Command Control",
                   value="`/togglecommand` `/commandroles` `/commandchannels` `/listcommands` `/view_enabled_commands`", inline=False)
    embed.add_field(name="🌿 4:20 Reminder", value="`/add_to_channel` `/test`", inline=False)
    embed.add_field(name="🎨 Fun", value="`/gif` `/meme` `/hug` `/slap` `/say`", inline=False)
    embed.set_footer(text="XULT - The Ultimate Discord Bot")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ── COMMAND CONTROL ───────────────────────────────────────────
@bot.tree.command(name="togglecommand", description="Enable or disable a command on your server")
@app_commands.describe(command="Command name", enabled="Enable or disable")
async def toggle_command(interaction: discord.Interaction, command: str, enabled: bool):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    update_command_setting(interaction.guild.id, command.lower(), enabled)
    await interaction.response.send_message(f"✅ `/{command}` {'enabled' if enabled else 'disabled'}.", ephemeral=True)


@bot.tree.command(name="commandroles", description="Set allowed roles for a command")
@app_commands.describe(command="Command name", roles="Role IDs comma-separated")
async def command_roles(interaction: discord.Interaction, command: str, roles: str = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    command = command.lower()
    if roles is None:
        update_command_setting(interaction.guild.id, command, True, [])
        await interaction.response.send_message(f"✅ Role restrictions removed for `/{command}`.", ephemeral=True)
    else:
        role_ids = [int(r.strip()) for r in roles.split(',') if r.strip().isdigit()]
        update_command_setting(interaction.guild.id, command, True, role_ids)
        await interaction.response.send_message(f"✅ Only specified roles can use `/{command}`.", ephemeral=True)


@bot.tree.command(name="commandchannels", description="Set channels where a command is disabled")
@app_commands.describe(command="Command name", channels="Channel IDs comma-separated")
async def command_channels(interaction: discord.Interaction, command: str, channels: str = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    command = command.lower()
    if channels is None:
        update_command_setting(interaction.guild.id, command, True, None, [])
        await interaction.response.send_message(f"✅ Channel restrictions removed for `/{command}`.", ephemeral=True)
    else:
        channel_ids = [int(ch.strip()) for ch in channels.split(',') if ch.strip().isdigit()]
        update_command_setting(interaction.guild.id, command, True, None, channel_ids)
        await interaction.response.send_message(f"✅ `/{command}` disabled in those channels.", ephemeral=True)


@bot.tree.command(name="listcommands", description="List all commands and their status")
async def list_commands(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    all_commands = [
        "help","balance","daily","coinflip","rps","slots","blackjack","joke","eightball","riddle",
        "gen","dmgen","stocklist","addstock","deletestock","setgenaccess","setautoupdate",
        "jail","unjail","purge","warnings","resetwarn","setroleonjoin","set_logs","add_allowed_channel",
        "upload_bad_words","sendnotice","setup_oauth_verification","verify",
        "setnotichannel","addyoutubechannel","addtwitchstream","addtwitteraccount",
        "reactionrole","setreportchannel","report","setlogchannels","save_server","load_server",
        "add_to_channel","test","gif","meme","hug","slap","say",
        "togglecommand","commandroles","commandchannels","listcommands","view_enabled_commands"
    ]
    embed = discord.Embed(title="📋 Command Settings", color=discord.Color.blue())
    chunks = [all_commands[i:i+20] for i in range(0, len(all_commands), 20)]
    for i, chunk in enumerate(chunks):
        value = "\n".join([f"`/{cmd}`: {'✅' if is_command_enabled(interaction.guild.id, cmd) else '❌'}" for cmd in chunk])
        embed.add_field(name=f"Commands {i+1}", value=value, inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="view_enabled_commands", description="View which commands are enabled for you")
async def view_enabled_commands(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("This command only works in servers.", ephemeral=True)
        return
    
    user_roles = [role.id for role in interaction.user.roles]
    enabled_commands = []
    disabled_commands = []
    
    # Get all commands from the tree
    all_commands = bot.tree.get_commands(guild=discord.Object(id=interaction.guild.id))
    
    for cmd in all_commands:
        if is_command_enabled(interaction.guild.id, cmd.name):
            allowed_roles = get_command_allowed_roles(interaction.guild.id, cmd.name)
            if not allowed_roles or any(role in allowed_roles for role in user_roles):
                enabled_commands.append(f"✅ /{cmd.name}")
            else:
                disabled_commands.append(f"🔒 /{cmd.name} (role restricted)")
        else:
            disabled_commands.append(f"❌ /{cmd.name} (disabled)")
    
    embed = discord.Embed(title="📋 Your Available Commands", color=discord.Color.blue())
    
    if enabled_commands:
        chunks = [enabled_commands[i:i+20] for i in range(0, len(enabled_commands), 20)]
        for i, chunk in enumerate(chunks):
            embed.add_field(name=f"✅ Available ({i+1})", value="\n".join(chunk), inline=True)
    
    if disabled_commands:
        chunks = [disabled_commands[i:i+20] for i in range(0, len(disabled_commands), 20)]
        for i, chunk in enumerate(chunks):
            embed.add_field(name=f"❌ Unavailable ({i+1})", value="\n".join(chunk), inline=True)
    
    embed.set_footer(text=f"Total: {len(enabled_commands)} available • {len(disabled_commands)} unavailable")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ── ECONOMY ───────────────────────────────────────────────────
@bot.tree.command(name="balance", description="Check your coins, XP, and level")
async def balance(interaction: discord.Interaction):
    coins = get_balance(interaction.user.id)
    xp = get_xp(interaction.user.id)
    level = get_level(interaction.user.id)
    c.execute("UPDATE users SET username = ? WHERE id = ?", (str(interaction.user), interaction.user.id))
    conn.commit()
    embed = discord.Embed(title=f"{interaction.user.display_name}'s Balance", color=discord.Color.gold())
    embed.add_field(name="Coins", value=f"{coins:,}", inline=True)
    embed.add_field(name="XP", value=f"{xp:,}", inline=True)
    embed.add_field(name="Level", value=level, inline=True)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="daily", description="Claim your daily coins (24h cooldown)")
async def daily(interaction: discord.Interaction):
    c.execute("SELECT last_daily FROM users WHERE id = ?", (interaction.user.id,))
    row = c.fetchone()
    if row and row[0]:
        last = datetime.fromisoformat(row[0])
        if datetime.now(timezone.utc) - last < timedelta(hours=24):
            remaining = timedelta(hours=24) - (datetime.now(timezone.utc) - last)
            h, m = divmod(int(remaining.total_seconds()) // 60, 60)
            await interaction.response.send_message(f"⏳ Daily available in **{h}h {m}m**.", ephemeral=True); return
    reward = random.randint(50, 200)
    add_coins(interaction.user.id, reward)
    c.execute("UPDATE users SET last_daily = ? WHERE id = ?", (datetime.now(timezone.utc).isoformat(), interaction.user.id))
    conn.commit()
    embed = discord.Embed(title="📅 Daily Reward", description=f"You claimed **{reward} coins**!", color=discord.Color.gold())
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="coinflip", description="Flip a coin and guess heads or tails")
@app_commands.choices(guess=[app_commands.Choice(name="Heads", value="heads"), app_commands.Choice(name="Tails", value="tails")])
async def coinflip(interaction: discord.Interaction, guess: app_commands.Choice[str]):
    result = random.choice(["heads", "tails"])
    if guess.value == result:
        add_coins(interaction.user.id, 10)
        embed = discord.Embed(title="🎉 Correct!", description=f"It was **{result}**! +10 coins", color=discord.Color.green())
    else:
        embed = discord.Embed(title="❌ Wrong!", description=f"Guessed **{guess.name}** but it was **{result}**", color=discord.Color.red())
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="rps", description="Play rock-paper-scissors")
@app_commands.choices(choice=[app_commands.Choice(name="Rock", value="rock"), app_commands.Choice(name="Paper", value="paper"), app_commands.Choice(name="Scissors", value="scissors")])
async def rps(interaction: discord.Interaction, choice: app_commands.Choice[str]):
    bot_choice = random.choice(["rock", "paper", "scissors"])
    wins = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
    if choice.value == bot_choice:
        embed = discord.Embed(title="🤝 Tie!", description=f"Both chose {choice.name}", color=discord.Color.blue())
    elif wins[choice.value] == bot_choice:
        add_coins(interaction.user.id, 10)
        embed = discord.Embed(title="🎉 You win!", description=f"{choice.name} beats {bot_choice}! +10 coins", color=discord.Color.green())
    else:
        embed = discord.Embed(title="😢 You lose!", description=f"{bot_choice} beats {choice.name}!", color=discord.Color.red())
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="slots", description="Play the slot machine (costs 20 coins)")
async def slots(interaction: discord.Interaction):
    if get_balance(interaction.user.id) < 20:
        await interaction.response.send_message("❌ You need 20 coins!", ephemeral=True); return
    add_coins(interaction.user.id, -20)
    icons = ["🍒", "🍋", "🔔", "⭐", "💎", "7️⃣"]
    reels = [random.choice(icons) for _ in range(3)]
    if len(set(reels)) == 1:
        winnings, msg = 500, "JACKPOT! +500 coins!"
    elif len(set(reels)) == 2:
        winnings, msg = 50, "Two in a row! +50 coins!"
    else:
        winnings, msg = 0, "No match. Try again!"
    if winnings:
        add_coins(interaction.user.id, winnings)
    embed = discord.Embed(title="🎰 Slot Machine", description=f"| {' | '.join(reels)} |\n\n{msg}",
                         color=discord.Color.gold() if winnings else discord.Color.dark_gray())
    embed.set_footer(text=f"Balance: {get_balance(interaction.user.id):,} coins")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="blackjack", description="Play blackjack against the dealer")
@app_commands.describe(bet="Amount to bet")
async def blackjack(interaction: discord.Interaction, bet: int):
    if bet <= 0 or get_balance(interaction.user.id) < bet:
        await interaction.response.send_message("❌ Invalid bet or insufficient coins.", ephemeral=True); return
    deck = [2,3,4,5,6,7,8,9,10,10,10,10,11] * 4
    random.shuffle(deck)
    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]
    def hand_value(hand):
        val = sum(hand)
        aces = hand.count(11)
        while val > 21 and aces:
            val -= 10; aces -= 1
        return val
    pv, dv = hand_value(player), hand_value(dealer)
    while dv < 17:
        dealer.append(deck.pop()); dv = hand_value(dealer)
    if pv > 21:
        add_coins(interaction.user.id, -bet); result = f"❌ Bust! Lost **{bet}** coins."
    elif dv > 21 or pv > dv:
        add_coins(interaction.user.id, bet); result = f"🎉 You win! +**{bet}** coins."
    elif pv == dv:
        result = "🤝 Push — coins returned."
    else:
        add_coins(interaction.user.id, -bet); result = f"😢 Dealer wins. Lost **{bet}** coins."
    embed = discord.Embed(title="🃏 Blackjack", color=discord.Color.green())
    embed.add_field(name="Your hand", value=f"{player} = **{pv}**", inline=True)
    embed.add_field(name="Dealer", value=f"{dealer} = **{dv}**", inline=True)
    embed.add_field(name="Result", value=result, inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="joke", description="Get a random joke")
async def joke(interaction: discord.Interaction):
    async with aiohttp.ClientSession() as session:
        async with session.get("https://official-joke-api.appspot.com/jokes/random") as resp:
            data = await resp.json()
            embed = discord.Embed(description=f"**{data['setup']}**\n\n{data['punchline']}", color=discord.Color.orange())
            await interaction.response.send_message(embed=embed)


@bot.tree.command(name="eightball", description="Ask the magic 8-ball a question")
@app_commands.describe(question="Your question")
async def eightball(interaction: discord.Interaction, question: str):
    responses = ["Yes","No","Maybe","Definitely","Absolutely not","Ask again later","It is certain","Very doubtful"]
    embed = discord.Embed(title=f"🎱 {question[:100]}", description=random.choice(responses), color=discord.Color.dark_blue())
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="riddle", description="Solve a riddle to earn coins")
async def riddle(interaction: discord.Interaction):
    global active_riddle, riddle_answer
    if active_riddle:
        await interaction.response.send_message("A riddle is already active!", ephemeral=True); return
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
    active_riddle = None; riddle_answer = None


# ── STOCK/GEN ─────────────────────────────────────────────────
@bot.tree.command(name="stocklist", description="List all available stock types")
async def stocklist(interaction: discord.Interaction):
    embed = discord.Embed(title="📦 Available Stock", description="Use `/gen <type>` to generate.", color=discord.Color.blue())
    total = 0
    for file in list(STOCK_DIR.glob("*.txt"))[:20]:
        count = count_stock(file.stem)
        info = STOCK_TYPES.get(file.stem, {"name": file.stem.capitalize(), "emoji": "📄"})
        embed.add_field(name=f"{info['emoji']} {info['name']}", value=f"`{count}` available", inline=True)
        total += count
    embed.set_footer(text=f"Total: {total} • Cooldown: 5s for free users")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="addstock", description="Add stock entries (Admin only)")
@app_commands.describe(stock_type="Type of stock", file="Text file with entries")
async def addstock(interaction: discord.Interaction, stock_type: str, file: discord.Attachment = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True); return
    if not file or not file.filename.endswith(".txt"):
        await interaction.response.send_message("Please upload a .txt file.", ephemeral=True); return
    content = (await file.read()).decode("utf-8").strip()
    if not content:
        await interaction.response.send_message("File is empty.", ephemeral=True); return
    filename = get_stock_filename(stock_type)
    if filename.exists():
        with open(filename, "a", encoding="utf-8") as f:
            f.write("\n\n" + content)
        await interaction.response.send_message(f"✅ Appended to {stock_type} stock.", ephemeral=True)
    else:
        filename.write_text(content, encoding="utf-8")
        await interaction.response.send_message(f"✅ Created {stock_type} stock file.", ephemeral=True)
    log_action(interaction.user.id, "ADD_STOCK", f"type={stock_type}")


@bot.tree.command(name="deletestock", description="Delete a stock file (Admin only)")
async def deletestock(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True); return
    files = [f.stem for f in STOCK_DIR.glob("*.txt")][:25]
    if not files:
        await interaction.response.send_message("No stock files available.", ephemeral=True); return
    view = DeleteStockDropdown(files)
    await interaction.response.send_message("Select a stock file to delete:", view=view, ephemeral=True)


@bot.tree.command(name="gen", description="Generate a stock entry")
@app_commands.describe(stock_type="Type of stock to generate")
async def gen(interaction: discord.Interaction, stock_type: str):
    is_premium = await check_user_premium(interaction.user.id)
    gen_access = load_json(JSON_FILES["gen_access"], {})
    if str(interaction.guild.id) in gen_access:
        allowed = gen_access[str(interaction.guild.id)]
        if allowed and not any(r.id in allowed for r in interaction.user.roles):
            await interaction.response.send_message("❌ You don't have permission to use /gen.", ephemeral=True); return
    await interaction.response.defer()
    cd, remaining = is_on_cooldown(interaction.user.id, is_premium)
    if cd:
        await interaction.followup.send(f"⏳ Wait **{remaining}s** before using /gen again.", ephemeral=True); return
    stock = get_stock_entry(stock_type)
    if not stock:
        await interaction.followup.send(f"❌ No stock available for `{stock_type}`.", ephemeral=True); return
    if not is_premium:
        set_cooldown(interaction.user.id)
    try:
        await interaction.user.send(f"```\n{stock}\n```")
        await interaction.followup.send("📩 Stock sent to your DMs!", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send(f"```\n{stock}\n```", ephemeral=True)
    await send_auto_update(bot)
    c.execute("""INSERT INTO stock_usage (user_id, username, stock_type, stock_content, generated_at, server_id, server_name, channel_id, channel_name, is_dm)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
              (interaction.user.id, str(interaction.user), stock_type, stock, datetime.now(timezone.utc).isoformat(),
               interaction.guild.id, interaction.guild.name, interaction.channel.id, interaction.channel.name))
    conn.commit()
    log_action(interaction.user.id, "GEN", f"type={stock_type}")


@bot.tree.command(name="dmgen", description="Generate a stock entry via DM")
@app_commands.describe(stock_type="Type of stock to generate")
async def dmgen(interaction: discord.Interaction, stock_type: str):
    if interaction.guild:
        await interaction.response.send_message("❌ This command can only be used in DMs.", ephemeral=True); return
    await interaction.response.defer(ephemeral=True)
    is_premium = await check_user_premium(interaction.user.id)
    cd, remaining = is_on_cooldown(interaction.user.id, is_premium)
    if cd:
        await interaction.followup.send(f"⏳ Wait **{remaining}s**.", ephemeral=True); return
    stock = get_stock_entry(stock_type)
    if not stock:
        await interaction.followup.send(f"❌ No stock available for `{stock_type}`.", ephemeral=True); return
    if not is_premium:
        set_cooldown(interaction.user.id)
    await interaction.followup.send(f"```\n{stock}\n```", ephemeral=True)
    c.execute("""INSERT INTO stock_usage (user_id, username, stock_type, stock_content, generated_at, server_id, server_name, channel_id, channel_name, is_dm)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
              (interaction.user.id, str(interaction.user), stock_type, stock, datetime.now(timezone.utc).isoformat(), 0, "DM", 0, "DM"))
    conn.commit()


@bot.tree.command(name="setgenaccess", description="Set roles that can use /gen (Admin only)")
@app_commands.describe(role="Role to allow")
async def setgenaccess(interaction: discord.Interaction, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True); return
    data = load_json(JSON_FILES["gen_access"], {})
    gid = str(interaction.guild.id)
    if gid not in data:
        data[gid] = []
    if role.id not in data[gid]:
        data[gid].append(role.id)
        save_json(JSON_FILES["gen_access"], data)
    await interaction.response.send_message(f"✅ {role.mention} can now use `/gen`.")


@bot.tree.command(name="setautoupdate", description="Set auto-update stock channel (Admin only)")
@app_commands.describe(channel="Channel for updates", role="Role to ping")
async def setautoupdate(interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True); return
    data = load_json(JSON_FILES["auto_update"], {})
    data[str(interaction.guild.id)] = {"channel_id": channel.id, "role_id": role.id if role else None}
    save_json(JSON_FILES["auto_update"], data)
    await interaction.response.send_message(f"✅ Auto-update set to {channel.mention}" + (f" with {role.mention}" if role else ""))


# ── MODERATION ────────────────────────────────────────────────
@bot.tree.command(name="jail", description="Jail a member")
@app_commands.describe(member="Member to jail", duration="Duration (e.g., 10m, 2h, 1d)", reason="Reason")
async def jail_cmd(interaction: discord.Interaction, member: discord.Member, duration: str = "10m", reason: str = "No reason"):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True); return
    await interaction.response.defer()
    try:
        jail_text, _ = await jail_member(member, duration, reason, interaction.user)
        await interaction.followup.send(f"🔒 {member.mention} jailed for **{duration}**. Reason: {reason}")
        log_action(interaction.user.id, "JAIL", f"target={member.id} duration={duration}")
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


@bot.tree.command(name="unjail", description="Unjail a member")
@app_commands.describe(member="Member to unjail")
async def unjail_cmd(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True); return
    await interaction.response.defer()
    if await unjail_member(member):
        await interaction.followup.send(f"✅ {member.mention} has been unjailed.")
    else:
        await interaction.followup.send(f"{member.mention} is not jailed.")


@bot.tree.command(name="purge", description="Delete messages")
@app_commands.describe(amount="Number of messages (1-100)", channel="Channel to purge")
async def purge(interaction: discord.Interaction, amount: int = 10, channel: discord.TextChannel = None):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ Manage Messages required.", ephemeral=True); return
    if amount < 1 or amount > 100:
        await interaction.response.send_message("Amount must be 1-100.", ephemeral=True); return
    channel = channel or interaction.channel
    await interaction.response.send_message(f"⏳ Purging {amount} messages...", ephemeral=True)
    deleted = await channel.purge(limit=amount)
    await interaction.followup.send(f"✅ Deleted {len(deleted)} messages.", ephemeral=True)


@bot.tree.command(name="warnings", description="View a user's warnings")
@app_commands.describe(user="User to check")
async def warnings(interaction: discord.Interaction, user: discord.Member):
    rows = c.execute("SELECT reason, timestamp, moderator_id FROM warnings WHERE user_id = ? AND server_id = ? ORDER BY timestamp DESC",
                     (user.id, interaction.guild.id)).fetchall()
    embed = discord.Embed(title=f"⚠️ Warnings for {user.display_name}", color=discord.Color.orange())
    if not rows:
        embed.description = f"{user.mention} has no warnings."
    else:
        embed.description = f"**{len(rows)} warnings**"
        for i, (reason, ts, mod_id) in enumerate(rows[:10], 1):
            mod = interaction.guild.get_member(mod_id)
            embed.add_field(name=f"Warning {i}",
                          value=f"**Reason:** {reason}\n**Mod:** {mod.mention if mod else mod_id}\n**Date:** {ts[:10]}",
                          inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="resetwarn", description="Reset a user's warnings (Admin only)")
@app_commands.describe(user="User to reset", reason="Reason")
async def resetwarn(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason"):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True); return
    c.execute("DELETE FROM warnings WHERE user_id = ? AND server_id = ?", (user.id, interaction.guild.id))
    conn.commit()
    try:
        await user.send(f"✅ Your warnings in **{interaction.guild.name}** have been reset. Reason: {reason}")
    except:
        pass
    await interaction.response.send_message(f"✅ Reset warnings for {user.mention}.")


@bot.tree.command(name="setroleonjoin", description="Set role for new members (Admin only)")
@app_commands.describe(role="Role to assign", delay="Delay (e.g., 10m, 2h, 1d)")
async def setroleonjoin(interaction: discord.Interaction, role: discord.Role, delay: str = "0s"):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True); return
    try:
        secs = int(parse_duration(delay).total_seconds())
    except:
        await interaction.response.send_message("Invalid delay format.", ephemeral=True); return
    c.execute("INSERT OR REPLACE INTO role_on_join (server_id, role_id, delay) VALUES (?, ?, ?)",
              (interaction.guild.id, role.id, secs))
    conn.commit()
    await interaction.response.send_message(f"✅ New members will get {role.mention} after {delay}.")


@bot.tree.command(name="set_logs", description="Set log channel (Admin only)")
@app_commands.describe(channel="Log channel")
async def set_logs(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True); return
    c.execute("INSERT OR REPLACE INTO server_configs (server_id, log_channel) VALUES (?, ?)", (interaction.guild.id, channel.id))
    conn.commit()
    await interaction.response.send_message(f"✅ Log channel set to {channel.mention}.")


@bot.tree.command(name="add_allowed_channel", description="Allow channel to bypass bad word filter (Admin only)")
@app_commands.describe(channel="Channel to allow")
async def add_allowed_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True); return
    c.execute("INSERT OR IGNORE INTO allowed_channels (server_id, channel_id) VALUES (?, ?)", (interaction.guild.id, channel.id))
    conn.commit()
    await interaction.response.send_message(f"✅ {channel.mention} added to allowed channels.")


@bot.tree.command(name="upload_bad_words", description="Upload bad words from .txt file (Admin only)")
@app_commands.describe(file="Text file with bad words")
async def upload_bad_words(interaction: discord.Interaction, file: discord.Attachment):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True); return
    if not file or not file.filename.endswith(".txt"):
        await interaction.response.send_message("Please upload a .txt file.", ephemeral=True); return
    content = (await file.read()).decode("utf-8", errors="ignore")
    words = [w.strip().lower() for w in content.splitlines() if w.strip()]
    for word in words[:100]:
        c.execute("INSERT OR IGNORE INTO bad_words (server_id, word) VALUES (?, ?)", (interaction.guild.id, word))
    conn.commit()
    await interaction.response.send_message(f"✅ Added {len(words)} bad words.")


@bot.tree.command(name="sendnotice", description="Send a notification")
@app_commands.describe(message="Message", channel="Channel to send", user="User to DM", title="Embed title", ping_role="Role to ping")
async def sendnotice(interaction: discord.Interaction, message: str, channel: discord.TextChannel = None,
                     user: discord.User = None, title: str = "Notification", ping_role: discord.Role = None):
    embed = discord.Embed(title=title, description=message, color=discord.Color.red())
    embed.set_footer(text=f"Sent by {interaction.user.display_name}")
    ping = f"<@&{ping_role.id}> " if ping_role else ""
    if user:
        try:
            await user.send(embed=embed)
            await interaction.response.send_message("✅ Notification sent via DM.", ephemeral=True)
        except:
            await interaction.response.send_message("❌ Failed to send DM.", ephemeral=True)
    elif channel:
        await channel.send(ping, embed=embed)
        await interaction.response.send_message(f"✅ Notification sent to {channel.mention}.", ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed)


# ── NOTIFICATIONS ─────────────────────────────────────────────
@bot.tree.command(name="setnotichannel", description="Set channel for media notifications (Admin only)")
@app_commands.describe(channel="Notification channel", role="Role to ping")
async def setnotichannel(interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True); return
    data = load_json(JSON_FILES["server_settings"], {})
    data[str(interaction.guild.id)] = {"notification_channel_id": channel.id, "notification_role_id": role.id if role else None}
    save_json(JSON_FILES["server_settings"], data)
    await interaction.response.send_message(f"✅ Notification channel set to {channel.mention}" + (f" with {role.mention}" if role else ""))


@bot.tree.command(name="addyoutubechannel", description="Track a YouTube channel (Admin only)")
@app_commands.describe(channel_id="YouTube channel ID (UCxxxxxx)")
async def addyoutubechannel(interaction: discord.Interaction, channel_id: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True); return
    c.execute("INSERT OR IGNORE INTO tracked_channels (server_id, platform, channel_id, last_post_id, role_id) VALUES (?, ?, ?, ?, ?)",
              (interaction.guild.id, 'youtube', channel_id, None, None))
    conn.commit()
    await interaction.response.send_message(f"✅ Tracking YouTube: {channel_id}")


@bot.tree.command(name="addtwitchstream", description="Track a Twitch stream (Admin only)")
@app_commands.describe(channel_name="Twitch username")
async def addtwitchstream(interaction: discord.Interaction, channel_name: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True); return
    c.execute("INSERT OR IGNORE INTO tracked_channels (server_id, platform, channel_id, last_post_id, role_id) VALUES (?, ?, ?, ?, ?)",
              (interaction.guild.id, 'twitch', channel_name.lower(), None, None))
    conn.commit()
    await interaction.response.send_message(f"✅ Tracking Twitch: {channel_name}")


@bot.tree.command(name="addtwitteraccount", description="Track a Twitter/X account (Admin only)")
@app_commands.describe(username="Twitter username (without @)")
async def addtwitteraccount(interaction: discord.Interaction, username: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True); return
    c.execute("INSERT OR IGNORE INTO tracked_channels (server_id, platform, channel_id, last_post_id, role_id) VALUES (?, ?, ?, ?, ?)",
              (interaction.guild.id, 'twitter', username.lower().replace('@', ''), None, None))
    conn.commit()
    await interaction.response.send_message(f"✅ Tracking Twitter: @{username}")


# ── SERVER MANAGEMENT ─────────────────────────────────────────
@bot.tree.command(name="reactionrole", description="Create a reaction role dropdown (Admin only)")
@app_commands.describe(roles="Comma-separated role names")
async def reactionrole(interaction: discord.Interaction, roles: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True); return
    role_names = [r.strip() for r in roles.split(",")]
    found = [r for r in interaction.guild.roles if r.name in role_names][:25]
    if not found:
        await interaction.response.send_message("No matching roles found.", ephemeral=True); return
    options = [discord.SelectOption(label=r.name, value=str(r.id)) for r in found]
    embed = discord.Embed(title="🎭 Reaction Role Menu", description="Select a role from the dropdown below.", color=discord.Color.blue())
    await interaction.response.send_message(embed=embed, view=RoleView(options))


@bot.tree.command(name="setreportchannel", description="Set report channel (Admin only)")
@app_commands.describe(channel="Reports channel", role="Role to ping")
async def setreportchannel(interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True); return
    c.execute("INSERT OR REPLACE INTO report_channels (server_id, channel_id, role_id) VALUES (?, ?, ?)",
              (interaction.guild.id, channel.id, role.id))
    conn.commit()
    await interaction.response.send_message(f"✅ Reports → {channel.mention} | Ping: {role.mention}")


@bot.tree.command(name="report", description="Report an issue to moderators")
@app_commands.describe(issue="What happened", user="User to report", evidence_text="Text evidence", evidence_file="File evidence")
async def report(interaction: discord.Interaction, issue: str, user: discord.User = None,
                evidence_text: str = None, evidence_file: discord.Attachment = None):
    row = c.execute("SELECT channel_id, role_id FROM report_channels WHERE server_id = ?", (interaction.guild.id,)).fetchone()
    if not row:
        await interaction.response.send_message("Report channel not set up.", ephemeral=True); return
    report_channel = bot.get_channel(row[0])
    if not report_channel:
        await interaction.response.send_message("Report channel not found.", ephemeral=True); return
    embed = discord.Embed(title="🚨 New Report", color=discord.Color.red(), timestamp=discord.utils.utcnow())
    embed.add_field(name="Reported By", value=interaction.user.mention, inline=False)
    embed.add_field(name="Issue", value=issue, inline=False)
    if user: embed.add_field(name="Reported User", value=user.mention, inline=False)
    if evidence_text: embed.add_field(name="Text Evidence", value=evidence_text, inline=False)
    if evidence_file: embed.add_field(name="File Evidence", value=evidence_file.url, inline=False)
    await report_channel.send(f"<@&{row[1]}>", embed=embed)
    c.execute("INSERT INTO reports (server_id, reporter_id, reported_id, reason, evidence, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
              (interaction.guild.id, interaction.user.id, user.id if user else None, issue, evidence_text, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    await interaction.response.send_message("✅ Report submitted.", ephemeral=True)


@bot.tree.command(name="setlogchannels", description="Set granular log channels (Admin only)")
@app_commands.describe(member_channel="Member logs", chat_channel="Message logs", voice_channel="Voice logs",
                      mod_channel="Moderation logs", server_channel="Server logs", bot_update_channel="Bot update logs")
async def setlogchannels(interaction: discord.Interaction, member_channel: discord.TextChannel, chat_channel: discord.TextChannel,
                        voice_channel: discord.TextChannel, mod_channel: discord.TextChannel, server_channel: discord.TextChannel,
                        bot_update_channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True); return
    data = load_json(JSON_FILES["log_channels"], {})
    data[str(interaction.guild.id)] = {
        "member": member_channel.id, "chat": chat_channel.id, "voice": voice_channel.id,
        "mod": mod_channel.id, "server": server_channel.id, "bot_update": bot_update_channel.id
    }
    save_json(JSON_FILES["log_channels"], data)
    await interaction.response.send_message("✅ Log channels configured.")


@bot.tree.command(name="save_server", description="Save server backup (Admin only)")
async def save_server(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True); return
    save_server_backup(interaction.guild)
    await save_all_members(interaction.guild)
    await interaction.response.send_message("✅ Server backup saved.", ephemeral=True)


@bot.tree.command(name="load_server", description="Restore server from backup (Admin only)")
async def load_server(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True); return
    await interaction.response.defer(ephemeral=True)
    if not (BACKUP_DIR / f"{interaction.guild.id}.json").exists():
        await interaction.followup.send("No backup found for this server.", ephemeral=True); return
    ok = await load_server_backup(interaction.guild)
    await interaction.followup.send("✅ Server restore complete." if ok else "❌ Failed to restore.", ephemeral=True)


# ── 4:20 ──────────────────────────────────────────────────────
@bot.tree.command(name="add_to_channel", description="Configure 4:20 messages (Admin only)")
@app_commands.describe(daily_channel="Channel for 4:20 messages", timezone="Timezone (e.g., America/New_York)",
                      role="Role to ping", voice_channel="Voice channel to link")
async def add_to_channel(interaction: discord.Interaction, daily_channel: discord.TextChannel, timezone: str = "UTC",
                        role: discord.Role = None, voice_channel: discord.VoiceChannel = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True); return
    try:
        tz = pytz.timezone(timezone)
    except:
        await interaction.response.send_message(f"Invalid timezone: {timezone}", ephemeral=True); return
    c.execute("INSERT OR REPLACE INTO four_twenty (server_id, channel_id, role_id, voice_channel_id, timezone) VALUES (?, ?, ?, ?, ?)",
              (interaction.guild.id, daily_channel.id, role.id if role else None, voice_channel.id if voice_channel else None, tz.zone))
    conn.commit()
    await interaction.response.send_message(f"✅ 4:20 set to {daily_channel.mention} (TZ: {tz.zone})" + (f" with {role.mention}" if role else ""))


@bot.tree.command(name="test", description="Send a test 4:20 message")
async def test(interaction: discord.Interaction):
    row = c.execute("SELECT channel_id, role_id, voice_channel_id FROM four_twenty WHERE server_id = ?", (interaction.guild.id,)).fetchone()
    if not row:
        await interaction.response.send_message("No 4:20 configuration found.", ephemeral=True); return
    channel = interaction.guild.get_channel(row[0])
    if not channel:
        await interaction.response.send_message("Configured channel not found.", ephemeral=True); return
    role_mention = f"<@&{row[1]}>" if row[1] else ""
    vc = interaction.guild.get_channel(row[2]) if row[2] else None
    voice_link = f"[Join voice chat!]({vc.jump_url})" if vc else "No voice chat configured."
    embed = discord.Embed(title="It's 4:20! 🌿 (TEST)", description=f"Join the session! {voice_link}\n{role_mention}", color=discord.Color.green())
    await channel.send(embed=embed)
    await interaction.response.send_message("✅ Test message sent!", ephemeral=True)


# ── FUN ───────────────────────────────────────────────────────
@bot.tree.command(name="gif", description="Get a GIF from GIPHY")
@app_commands.describe(search="Search term")
async def gif(interaction: discord.Interaction, search: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.giphy.com/v1/gifs/search?api_key={GIPHY_API_KEY}&q={search}&limit=1&rating=pg") as resp:
            data = await resp.json()
    embed = discord.Embed(title=f"🎬 GIF: {search}", color=discord.Color.blue())
    if data.get("data") and data["data"]:
        embed.set_image(url=data["data"][0]["images"]["original"]["url"])
    else:
        embed.description = "No GIF found."
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="meme", description="Get a random meme")
async def meme(interaction: discord.Interaction):
    async with aiohttp.ClientSession() as session:
        async with session.get("https://meme-api.com/gimme") as resp:
            data = await resp.json()
            embed = discord.Embed(title=f"😂 {data['title'][:100]}", color=discord.Color.orange())
            embed.set_image(url=data['url'])
            await interaction.response.send_message(embed=embed)


@bot.tree.command(name="hug", description="Hug a member")
@app_commands.describe(member="Member to hug")
async def hug(interaction: discord.Interaction, member: discord.Member):
    embed = discord.Embed(description=f"{interaction.user.mention} hugs {member.mention}! 🤗", color=discord.Color.magenta())
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="slap", description="Slap a member")
@app_commands.describe(member="Member to slap")
async def slap(interaction: discord.Interaction, member: discord.Member):
    embed = discord.Embed(description=f"{interaction.user.mention} slaps {member.mention}! 👋", color=discord.Color.red())
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="say", description="Bot repeats your message")
@app_commands.describe(text="Text to repeat")
async def say(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(text[:2000])


# ==================== API SERVER ====================

async def handle_api_key(request):
    return web.json_response({"key": API_KEY})


async def handle_api_health(request):
    return web.json_response({"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()})


async def handle_api_stats(request):
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        total_users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0] or 0
        total_servers = len(bot.guilds)
        premium = c.execute("SELECT COUNT(*) FROM premium_users WHERE is_active = 1").fetchone()[0] or 0
        cmds_today = c.execute("SELECT COUNT(*) FROM stock_usage WHERE generated_at > datetime('now', '-1 day')").fetchone()[0] or 0
        total_coins = c.execute("SELECT SUM(coins) FROM users").fetchone()[0] or 0
        activity = []
        for i in range(6, -1, -1):
            day = datetime.now(timezone.utc) - timedelta(days=i)
            count = c.execute("SELECT COUNT(*) FROM stock_usage WHERE date(generated_at) = date(?)", (day.isoformat(),)).fetchone()[0] or 0
            activity.append(count)
        recent = []
        for row in c.execute("SELECT user_id, username, stock_type, generated_at FROM stock_usage ORDER BY generated_at DESC LIMIT 10").fetchall():
            recent.append({
                "userId": str(row[0]),
                "username": row[1] or f"User-{row[0]}",
                "type": row[2],
                "time": datetime.fromisoformat(row[3]).strftime("%H:%M:%S")
            })
        return web.json_response({
            "total_users": total_users, "total_servers": total_servers,
            "total_commands": cmds_today, "premium_users": premium,
            "total_coins": total_coins,
            "activity": activity, "recent": recent,
            "latency": round(bot.latency * 1000, 2),
            "uptime": str(datetime.now(timezone.utc) - bot.start_time).split(".")[0]
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_api_stock(request):
    # Stock endpoint is public (no auth required) for dashboard stock display
    try:
        stock_data = {}
        for file in STOCK_DIR.glob("*.txt"):
            stock_data[file.stem] = {
                "count": count_stock(file.stem),
                "name": STOCK_TYPES.get(file.stem, {}).get("name", file.stem.capitalize()),
                "emoji": STOCK_TYPES.get(file.stem, {}).get("emoji", "📄"),
                "cooldown": 5,
                "price": STOCK_TYPES.get(file.stem, {}).get("price", 3)
            }
        return web.json_response(stock_data)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_api_check_premium(request):
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        user_id = int(request.match_info.get("user_id"))
        if user_id == OWNER_ID:
            return web.json_response({"hasPremium": True})
        has_premium = await check_user_premium(user_id)
        return web.json_response({"hasPremium": has_premium})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_api_gen(request):
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        data = await request.json()
        user_id = data.get("user_id")
        stock_type = data.get("stock_type")
        if not user_id or not stock_type:
            return web.json_response({"error": "Missing user_id or stock_type"}, status=400)
        is_premium = await check_user_premium(int(user_id))
        cd, remaining = is_on_cooldown(int(user_id), is_premium)
        if cd:
            return web.json_response({"error": f"Cooldown: {remaining}s", "cooldown": remaining}, status=429)
        stock = get_stock_entry(stock_type)
        if not stock:
            return web.json_response({"error": "No stock available"}, status=404)
        if not is_premium:
            set_cooldown(int(user_id))
        user = bot.get_user(int(user_id))
        if user:
            try:
                await user.send(f"🎁 Here's your **{stock_type}** from the vending machine:\n```\n{stock}\n```")
            except:
                pass
        c.execute("""INSERT INTO stock_usage (user_id, username, stock_type, stock_content, generated_at, server_id, server_name, channel_id, channel_name, is_dm)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                  (user_id, str(user) if user else str(user_id), stock_type, stock,
                   datetime.now(timezone.utc).isoformat(), 0, "Vending Machine", 0, "Web"))
        conn.commit()
        return web.json_response({"success": True, "message": "Stock sent to your DMs!"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_api_verify_payment(request):
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        data = await request.json()
        user_id = int(data.get("user_id"))
        payment_method = data.get("method", "paypal")
        transaction_id = data.get("transaction_id", "manual")
        success = await assign_premium_role(user_id)
        if success:
            c.execute("""INSERT INTO pending_payments (user_id, payment_id, amount, method, status, created_at, verified_at)
                         VALUES (?, ?, ?, ?, ?, ?, ?)""",
                      (user_id, transaction_id, 3.00, payment_method, "completed",
                       datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()))
            conn.commit()
            return web.json_response({"success": True, "message": "Premium activated!"})
        return web.json_response({"error": "Failed to assign premium role — is the user in the main server?"}, status=500)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_api_servers(request):
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        servers = [{"id": str(g.id), "name": g.name, "icon": str(g.icon.url) if g.icon else None,
                   "memberCount": g.member_count, "ownerId": str(g.owner_id)} for g in bot.guilds]
        return web.json_response(servers)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_api_server_config(request):
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        server_id = int(request.match_info.get("server_id"))
        all_cmds = [
            "help","balance","daily","coinflip","rps","slots","blackjack","joke","eightball","riddle",
            "gen","dmgen","stocklist","addstock","deletestock","setgenaccess","setautoupdate",
            "jail","unjail","purge","warnings","resetwarn","setroleonjoin","set_logs","add_allowed_channel",
            "upload_bad_words","sendnotice","setup_oauth_verification","verify",
            "setnotichannel","addyoutubechannel","addtwitchstream","addtwitteraccount",
            "reactionrole","setreportchannel","report","setlogchannels","save_server","load_server",
            "add_to_channel","test","gif","meme","hug","slap","say",
            "togglecommand","commandroles","commandchannels","listcommands","view_enabled_commands"
        ]
        commands_status = {}
        for cmd in all_cmds:
            commands_status[cmd] = {
                "enabled": is_command_enabled(server_id, cmd),
                "allowed_roles": get_command_allowed_roles(server_id, cmd),
                "disabled_channels": get_command_disabled_channels(server_id, cmd)
            }
        return web.json_response({"server_id": server_id, "commands": commands_status})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_api_update_command(request):
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        server_id = int(request.match_info.get("server_id"))
        command = request.match_info.get("command")
        data = await request.json()
        update_command_setting(server_id, command, data.get("enabled", True),
                               data.get("allowed_roles", []), data.get("disabled_channels", []))
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_api_update_gen_access(request):
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        server_id = request.match_info.get("server_id")
        data = await request.json()
        gen_access = load_json(JSON_FILES["gen_access"], {})
        gen_access[server_id] = data.get("roles", [])
        save_json(JSON_FILES["gen_access"], gen_access)
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ── OWNER API ROUTES ──────────────────────────────────────────

async def handle_owner_pull(request):
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        data = await request.json()
        target = data.get("target_server", "")
        count = data.get("count", "all")
        target_guild = next((g for g in bot.guilds if str(g.id) == target or g.name.lower() == target.lower()), None)
        if not target_guild:
            return web.json_response({"error": f"Server '{target}' not found"}, status=404)
        saved = c.execute("SELECT DISTINCT user_id FROM saved_members").fetchall()
        members_to_pull = [r[0] for r in saved] if str(count).lower() == "all" else [r[0] for r in saved[:int(count)]]
        ok = 0
        for uid in members_to_pull:
            if await restore_member_to_server(uid, target_guild):
                ok += 1
            await asyncio.sleep(0.3)
        return web.json_response({"success": True, "message": f"Pulled {ok}/{len(members_to_pull)} members to {target_guild.name}"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_owner_save_all(request):
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        saved = 0
        for guild in bot.guilds:
            save_server_backup(guild)
            await save_all_members(guild)
            saved += 1
            await asyncio.sleep(0.5)
        return web.json_response({"success": True, "message": f"Saved {saved} servers"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_owner_manage_coins(request):
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        data = await request.json()
        user_id = int(data.get("user_id"))
        amount = int(data.get("amount", 0))
        if amount > 0:
            add_coins(user_id, amount)
        else:
            remove_coins(user_id, abs(amount))
        return web.json_response({"success": True, "message": f"Updated coins for {user_id}"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_owner_ban_user(request):
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        data = await request.json()
        user_id = int(data.get("user_id"))
        reason = data.get("reason", "No reason")
        c.execute("UPDATE users SET banned = 1, banned_reason = ? WHERE id = ?", (reason, user_id))
        conn.commit()
        return web.json_response({"success": True, "message": f"Banned user {user_id}"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_owner_premium_users(request):
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        rows = c.execute("SELECT user_id, granted_at, is_active FROM premium_users ORDER BY granted_at DESC LIMIT 50").fetchall()
        result = []
        for row in rows:
            user = bot.get_user(row["user_id"])
            result.append({
                "user_id": str(row["user_id"]),
                "username": user.name if user else f"User-{row['user_id']}",
                "granted_at": row["granted_at"],
                "is_active": row["is_active"],
            })
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_owner_logs(request):
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        rows = c.execute("SELECT user_id, action, details, timestamp FROM logs ORDER BY timestamp DESC LIMIT 50").fetchall()
        return web.json_response([
            {"userId": str(r["user_id"]), "action": r["action"], "details": r["details"], "time": r["timestamp"]}
            for r in rows
        ])
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_owner_broadcast(request):
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        data = await request.json()
        message = data.get("message", "")
        if not message:
            return web.json_response({"error": "No message"}, status=400)
        log_channels = load_json(JSON_FILES["log_channels"], {})
        sent = 0
        for guild_id, channels in log_channels.items():
            ch_id = channels.get("bot_update")
            if ch_id:
                guild = bot.get_guild(int(guild_id))
                if guild:
                    channel = guild.get_channel(int(ch_id))
                    if channel:
                        embed = discord.Embed(title="📢 XULT Announcement", description=message,
                                             color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
                        try:
                            await channel.send(embed=embed)
                            sent += 1
                        except:
                            pass
        return web.json_response({"success": True, "message": f"Broadcast sent to {sent} servers"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_owner_backup_db(request):
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        backup_path = DATA_DIR / filename
        conn.backup(sqlite3.connect(str(backup_path)))
        return web.json_response({"success": True, "filename": filename})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_owner_restore_server(request):
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        data = await request.json()
        server_id = int(data.get("server_id"))
        guild = bot.get_guild(server_id)
        if not guild:
            return web.json_response({"error": f"Server {server_id} not found"}, status=404)
        row = c.execute("SELECT backup_data FROM server_backups WHERE server_id = ? ORDER BY created_at DESC LIMIT 1",
                       (server_id,)).fetchone()
        if not row:
            return web.json_response({"error": "No backup found"}, status=404)
        success = await load_server_backup(guild, json.loads(row["backup_data"]))
        if success:
            return web.json_response({"success": True, "message": f"Restored {guild.name}"})
        return web.json_response({"error": "Restore failed"}, status=500)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ==================== API SERVER STARTUP ====================

async def start_api_server():
    app = web.Application()

    @web.middleware
    async def cors_middleware(request, handler):
        if request.method == "OPTIONS":
            resp = web.Response()
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            return resp
        resp = await handler(request)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return resp

    app.middlewares.append(cors_middleware)

    # Core routes
    app.router.add_get("/health",                                   handle_api_health)
    app.router.add_get("/api/key",                                  handle_api_key)
    app.router.add_get("/api/stats",                                handle_api_stats)
    app.router.add_get("/api/stock",                                handle_api_stock)
    app.router.add_get("/api/check-premium/{user_id}",              handle_api_check_premium)
    app.router.add_post("/api/gen",                                 handle_api_gen)
    app.router.add_post("/api/verify-payment",                      handle_api_verify_payment)
    app.router.add_get("/api/servers",                              handle_api_servers)
    app.router.add_get("/api/server/{server_id}/config",            handle_api_server_config)
    app.router.add_post("/api/server/{server_id}/command/{command}", handle_api_update_command)
    app.router.add_post("/api/server/{server_id}/gen_access",       handle_api_update_gen_access)

    # Owner routes
    app.router.add_post("/api/owner/pull",           handle_owner_pull)
    app.router.add_post("/api/owner/save_all",        handle_owner_save_all)
    app.router.add_post("/api/owner/manage_coins",    handle_owner_manage_coins)
    app.router.add_post("/api/owner/ban_user",        handle_owner_ban_user)
    app.router.add_get( "/api/owner/premium_users",   handle_owner_premium_users)
    app.router.add_get( "/api/owner/logs",            handle_owner_logs)
    app.router.add_post("/api/owner/broadcast",       handle_owner_broadcast)
    app.router.add_post("/api/owner/backup_db",       handle_owner_backup_db)
    app.router.add_post("/api/owner/restore_server",  handle_owner_restore_server)

    port = API_PORT
    for attempt in range(10):
        try:
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", port)
            await site.start()
            log.info(f"API server on :{port}")
            return
        except OSError:
            port += 1
    log.error("Could not start API server")


# ==================== RUN BOT ====================

if __name__ == "__main__":
    print("=" * 55)
    print("  ⚡  XULT — Ultimate Discord Bot (PATCHED)")
    print("=" * 55)
    print(f"  Data:   {DATA_DIR}")
    print(f"  Stock:  {STOCK_DIR}")
    print(f"  API:    port {API_PORT}")
    print(f"  Owner:  {OWNER_ID}")
    print(f"  Key:    {API_KEY[:8]}...  (stable)")
    print(f"  Premium Role: {PREMIUM_ROLE_ID}")
    print(f"  Main Server:  {MAIN_SERVER_ID}")
    print("=" * 55)

    bot.run(TOKEN)
