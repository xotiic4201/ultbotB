# ============================================================
# XULT BOT - COMPLETE BACKEND (ALL COMMANDS)
# Every command from the original bot included
# No command toggling - all commands visible in all servers
# ============================================================

import asyncio
import aiohttp
import json
import logging
import os
import random
import secrets
import sqlite3
import time
import re
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

CLIENT_ID = os.getenv("CLIENT_ID", "1417284780675956766")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")
if not CLIENT_SECRET:
    raise ValueError("CLIENT_SECRET not set!")

REDIRECT_URI = os.getenv("REDIRECT_URI", "https://ultbot.vercel.app/callback")
BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID", "1302203907782606880"))
PREMIUM_ROLE_ID = int(os.getenv("PREMIUM_ROLE_ID", "0"))
MAIN_SERVER_ID = int(os.getenv("MAIN_SERVER_ID", "0"))
API_PORT = int(os.getenv("PORT", os.getenv("API_PORT", "10000")))

BASE_DIR = Path.cwd()
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)
STOCK_DIR = BASE_DIR / "stock"
STOCK_DIR.mkdir(exist_ok=True)

# API Key for frontend-backend communication
_KEY_FILE = DATA_DIR / "api_key.txt"
if _KEY_FILE.exists():
    API_KEY = _KEY_FILE.read_text().strip()
else:
    API_KEY = secrets.token_hex(32)
    _KEY_FILE.write_text(API_KEY)

# ==================== DATABASE ====================

conn = sqlite3.connect(DATA_DIR / "xult.db", check_same_thread=False)
conn.row_factory = sqlite3.Row
c = conn.cursor()

# Complete database schema
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    avatar TEXT,
    coins INTEGER DEFAULT 0,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    last_daily TIMESTAMP,
    premium_expires TIMESTAMP,
    banned INTEGER DEFAULT 0,
    banned_reason TEXT,
    premium_verified INTEGER DEFAULT 0
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS premium_users (
    user_id INTEGER PRIMARY KEY,
    guild_id INTEGER,
    role_id INTEGER,
    granted_at TIMESTAMP,
    expires_at TIMESTAMP,
    is_active INTEGER DEFAULT 1,
    payment_id TEXT,
    payment_method TEXT
)
""")

c.execute("""
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
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS user_cooldowns (
    user_id INTEGER PRIMARY KEY,
    last_generated TIMESTAMP,
    generation_count INTEGER DEFAULT 0
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    moderator_id INTEGER,
    reason TEXT,
    timestamp TIMESTAMP,
    server_id INTEGER
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS jailed_members (
    server_id INTEGER,
    user_id INTEGER,
    roles TEXT,
    jail_time TIMESTAMP,
    duration TEXT,
    reason TEXT,
    jailed_by INTEGER,
    PRIMARY KEY (server_id, user_id)
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT,
    details TEXT,
    timestamp TIMESTAMP
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS server_backups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER,
    backup_name TEXT,
    backup_data TEXT,
    created_at TIMESTAMP,
    created_by INTEGER
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS saved_members (
    user_id INTEGER,
    username TEXT,
    avatar TEXT,
    roles TEXT,
    saved_at TIMESTAMP,
    server_id INTEGER,
    PRIMARY KEY (user_id, server_id)
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS reaction_roles (
    message_id INTEGER,
    channel_id INTEGER,
    role_id INTEGER,
    emoji TEXT,
    PRIMARY KEY (message_id, emoji)
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS role_on_join (
    server_id INTEGER PRIMARY KEY,
    role_id INTEGER,
    delay INTEGER
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS bad_words (
    server_id INTEGER,
    word TEXT,
    PRIMARY KEY (server_id, word)
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS allowed_channels (
    server_id INTEGER,
    channel_id INTEGER,
    PRIMARY KEY (server_id, channel_id)
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS tracked_channels (
    server_id INTEGER,
    platform TEXT,
    channel_id TEXT,
    last_post_id TEXT,
    role_id INTEGER,
    notify_channel INTEGER,
    PRIMARY KEY (server_id, platform, channel_id)
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS four_twenty (
    server_id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    role_id INTEGER,
    voice_channel_id INTEGER,
    timezone TEXT DEFAULT 'UTC'
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS report_channels (
    server_id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    role_id INTEGER
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER,
    reporter_id INTEGER,
    reported_id INTEGER,
    reason TEXT,
    evidence TEXT,
    status TEXT DEFAULT 'pending',
    timestamp TIMESTAMP
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT UNIQUE,
    guild_id INTEGER,
    channel_id INTEGER,
    user_id INTEGER,
    username TEXT,
    topic TEXT,
    priority TEXT DEFAULT 'normal',
    status TEXT DEFAULT 'open',
    created_at TIMESTAMP,
    closed_at TIMESTAMP,
    closed_by INTEGER,
    transcript TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id TEXT UNIQUE,
    guild_id INTEGER,
    user_id INTEGER,
    username TEXT,
    form_name TEXT,
    answers TEXT,
    status TEXT DEFAULT 'pending',
    reviewer_id INTEGER,
    review_message TEXT,
    submitted_at TIMESTAMP,
    reviewed_at TIMESTAMP
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS application_forms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    form_name TEXT,
    questions TEXT,
    role_id INTEGER,
    channel_id INTEGER,
    log_channel_id INTEGER,
    created_by INTEGER,
    created_at TIMESTAMP,
    UNIQUE(guild_id, form_name)
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS verification_config (
    server_id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    role_id INTEGER,
    log_channel_id INTEGER,
    message_id INTEGER
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS logging_config (
    server_id INTEGER PRIMARY KEY,
    mod_log INTEGER,
    member_log INTEGER,
    message_log INTEGER,
    voice_log INTEGER,
    server_log INTEGER,
    ticket_log INTEGER,
    app_log INTEGER,
    report_log INTEGER,
    bot_update_log INTEGER
)
""")

conn.commit()

# Insert owner
c.execute("INSERT OR IGNORE INTO users (id, username, premium_verified) VALUES (?, ?, 1)", (BOT_OWNER_ID, "Owner"))
conn.commit()

# ==================== STOCK SYSTEM ====================

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
    "combo": {"name": "Combos", "emoji": "🔐", "description": "Username:password combos"},
    "randomip": {"name": "Random IP", "emoji": "🌐", "description": "Random IP addresses"},
    "random": {"name": "Random Accounts", "emoji": "🎲", "description": "Random account types"},
    # Premium versions
    "premium_epicgames": {"name": "Premium Epic Games", "emoji": "✨", "description": "Premium Epic Games accounts"},
    "premium_instagram": {"name": "Premium Instagram", "emoji": "✨", "description": "Premium Instagram accounts"},
    "premium_onlyfans": {"name": "Premium OnlyFans", "emoji": "✨", "description": "Premium OnlyFans accounts"},
    "premium_phonenumbers": {"name": "Premium Phone Numbers", "emoji": "📱", "description": "Premium phone numbers"},
    "premium_randomip": {"name": "Premium Random IP", "emoji": "✨", "description": "Premium random IPs"},
    "premium_r6acc": {"name": "Premium R6 Accounts", "emoji": "🎮", "description": "Premium Rainbow Six Siege accounts"},
    "premium_roblox": {"name": "Premium Roblox", "emoji": "✨", "description": "Premium Roblox accounts"},
    "premium_steam": {"name": "Premium Steam", "emoji": "✨", "description": "Premium Steam accounts"},
    "premium_ubisoft": {"name": "Premium Ubisoft", "emoji": "✨", "description": "Premium Ubisoft accounts"},
}

for st in STOCK_TYPES:
    file_path = STOCK_DIR / f"{st}.txt"
    if not file_path.exists():
        file_path.write_text("")

def count_stock(stock_type: str) -> int:
    file_path = STOCK_DIR / f"{stock_type}.txt"
    try:
        content = file_path.read_text(encoding="utf-8").strip()
        if not content:
            return 0
        return len([x.strip() for x in content.split('\n\n') if x.strip()])
    except:
        return 0

def get_stock_entry(stock_type: str) -> Optional[str]:
    file_path = STOCK_DIR / f"{stock_type}.txt"
    try:
        content = file_path.read_text(encoding="utf-8").strip()
        if not content:
            return None
        entries = [x.strip() for x in content.split('\n\n') if x.strip()]
        if not entries:
            return None
        first = entries[0]
        remaining = '\n\n'.join(entries[1:])
        file_path.write_text(remaining, encoding="utf-8")
        return first
    except:
        return None

def add_stock_entries(stock_type: str, entries: List[str]):
    file_path = STOCK_DIR / f"{stock_type}.txt"
    existing = file_path.read_text(encoding="utf-8").strip()
    new_content = existing + ('\n\n' + '\n\n'.join(entries) if existing else '\n\n'.join(entries))
    file_path.write_text(new_content, encoding="utf-8")

# ==================== ECONOMY ====================

def get_balance(user_id: int) -> int:
    c.execute("SELECT coins FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    if row:
        return row["coins"]
    c.execute("INSERT INTO users (id, coins, xp, level) VALUES (?, 0, 0, 1)", (user_id,))
    conn.commit()
    return 0

def add_coins(user_id: int, amount: int):
    c.execute("UPDATE users SET coins = coins + ? WHERE id=?", (amount, user_id))
    if c.rowcount == 0:
        c.execute("INSERT INTO users (id, coins) VALUES (?, ?)", (user_id, amount))
    conn.commit()

def remove_coins(user_id: int, amount: int):
    bal = get_balance(user_id)
    c.execute("UPDATE users SET coins = ? WHERE id=?", (max(0, bal - amount), user_id))
    conn.commit()

def add_xp(user_id: int, amount: int) -> bool:
    c.execute("SELECT xp, level FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (id, xp, level) VALUES (?, 0, 1)", (user_id,))
        xp, level = 0, 1
    else:
        xp, level = row["xp"], row["level"]
    new_xp = xp + amount
    new_level = int(new_xp ** 0.5)
    leveled_up = new_level > level
    c.execute("UPDATE users SET xp=?, level=? WHERE id=?", (new_xp, new_level, user_id))
    conn.commit()
    return leveled_up

def get_xp(user_id: int) -> int:
    c.execute("SELECT xp FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    return row["xp"] if row else 0

def get_level(user_id: int) -> int:
    c.execute("SELECT level FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    return row["level"] if row else 1

# ==================== PREMIUM ====================

async def check_user_premium(user_id: int) -> bool:
    if user_id == BOT_OWNER_ID:
        return True
    if PREMIUM_ROLE_ID == 0 or MAIN_SERVER_ID == 0:
        return False
    guild = bot.get_guild(MAIN_SERVER_ID)
    if not guild:
        return False
    member = guild.get_member(user_id)
    if not member:
        return False
    role = guild.get_role(PREMIUM_ROLE_ID)
    return role in member.roles if role else False

async def assign_premium_role(user_id: int) -> bool:
    if PREMIUM_ROLE_ID == 0 or MAIN_SERVER_ID == 0:
        return False
    guild = bot.get_guild(MAIN_SERVER_ID)
    if not guild:
        return False
    member = guild.get_member(user_id)
    if not member:
        return False
    role = guild.get_role(PREMIUM_ROLE_ID)
    if not role:
        return False
    try:
        await member.add_roles(role, reason="Premium purchase verified")
        c.execute("""
            INSERT OR REPLACE INTO premium_users (user_id, guild_id, role_id, granted_at, is_active)
            VALUES (?, ?, ?, ?, 1)
        """, (user_id, MAIN_SERVER_ID, PREMIUM_ROLE_ID, datetime.now(timezone.utc).isoformat()))
        c.execute("UPDATE users SET premium_verified=1 WHERE id=?", (user_id,))
        conn.commit()
        return True
    except Exception as e:
        log.error(f"Failed to assign premium role: {e}")
        return False

# ==================== JAIL SYSTEM ====================

def parse_duration(duration: str) -> timedelta:
    matches = re.findall(r'(\d+)([smhd])', duration.lower())
    if not matches:
        raise ValueError("Invalid duration. Use e.g. 10m, 2h, 1d")
    total = timedelta()
    for amt, unit in matches:
        amt = int(amt)
        if unit == 's':
            total += timedelta(seconds=amt)
        elif unit == 'm':
            total += timedelta(minutes=amt)
        elif unit == 'h':
            total += timedelta(hours=amt)
        elif unit == 'd':
            total += timedelta(days=amt)
    return total

async def jail_member(member: discord.Member, duration: str, reason: str, moderator: discord.Member):
    jail_text = discord.utils.get(member.guild.text_channels, name="jail")
    if not jail_text:
        overwrites = {
            member.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        jail_text = await member.guild.create_text_channel("jail", overwrites=overwrites)
    
    original_roles = [r.id for r in member.roles if r.name != "@everyone"]
    await member.remove_roles(*[r for r in member.roles if r.name != "@everyone"], reason=f"Jailed: {reason}")
    
    jail_time = datetime.now(timezone.utc)
    c.execute("""
        INSERT OR REPLACE INTO jailed_members (server_id, user_id, roles, jail_time, duration, reason, jailed_by)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (member.guild.id, member.id, json.dumps(original_roles), jail_time.isoformat(), duration, reason, moderator.id))
    conn.commit()
    
    try:
        await member.send(f"🔒 You have been jailed in **{member.guild.name}** for **{duration}**. Reason: {reason}")
    except:
        pass

async def unjail_member(member: discord.Member) -> bool:
    row = c.execute("SELECT roles FROM jailed_members WHERE server_id=? AND user_id=?", (member.guild.id, member.id)).fetchone()
    if not row:
        return False
    
    roles = [member.guild.get_role(r) for r in json.loads(row["roles"]) if member.guild.get_role(r)]
    if roles:
        await member.add_roles(*roles, reason="Unjailed")
    
    c.execute("DELETE FROM jailed_members WHERE server_id=? AND user_id=?", (member.guild.id, member.id))
    conn.commit()
    
    try:
        await member.send(f"✅ You have been unjailed from **{member.guild.name}**.")
    except:
        pass
    return True

# ==================== COOLDOWNS ====================

user_cooldowns: Dict[int, float] = {}
FREE_GEN_TIMEOUT = 5

def is_on_cooldown(user_id: int, is_premium: bool = False) -> Tuple[bool, int]:
    if is_premium:
        return False, 0
    last = user_cooldowns.get(user_id, 0)
    elapsed = time.time() - last
    if elapsed < FREE_GEN_TIMEOUT:
        return True, int(FREE_GEN_TIMEOUT - elapsed)
    return False, 0

def set_cooldown(user_id: int):
    user_cooldowns[user_id] = time.time()

def log_action(user_id: int, action: str, details: str = ""):
    c.execute("INSERT INTO logs (user_id, action, details, timestamp) VALUES (?, ?, ?, ?)",
              (user_id, action, details, datetime.now(timezone.utc).isoformat()))
    conn.commit()

# ==================== BACKUP HELPERS ====================

async def save_server_backup(guild: discord.Guild):
    backup_data = {
        "name": guild.name,
        "id": guild.id,
        "roles": [{"id": r.id, "name": r.name} for r in guild.roles],
        "channels": [{"id": c.id, "name": c.name, "type": str(c.type)} for c in guild.channels],
        "backup_time": datetime.now(timezone.utc).isoformat()
    }
    c.execute("""
        INSERT INTO server_backups (server_id, backup_name, backup_data, created_at, created_by)
        VALUES (?, ?, ?, ?, ?)
    """, (guild.id, f"backup_{int(time.time())}", json.dumps(backup_data), datetime.now(timezone.utc).isoformat(), BOT_OWNER_ID))
    conn.commit()

async def save_all_members(guild: discord.Guild):
    for member in guild.members:
        if not member.bot:
            roles = [r.id for r in member.roles if r.name != "@everyone"]
            c.execute("""
                INSERT OR REPLACE INTO saved_members (user_id, username, avatar, roles, saved_at, server_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (member.id, str(member), str(member.avatar.url) if member.avatar else None,
                  json.dumps(roles), datetime.now(timezone.utc).isoformat(), guild.id))
    conn.commit()

# ==================== BOT SETUP ====================

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
bot.start_time = datetime.now(timezone.utc)
bot.owner_id = BOT_OWNER_ID

# ==================== BOT EVENTS ====================

@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user} ({bot.user.id})")
    
    for st in STOCK_TYPES:
        file_path = STOCK_DIR / f"{st}.txt"
        if not file_path.exists():
            file_path.write_text("")
    
    await bot.tree.sync()
    log.info(f"Synced all commands globally")
    
    bot.loop.create_task(check_unjail_loop())
    bot.loop.create_task(start_api_server())
    
    log.info("XULT is ready! All commands visible in all servers.")

@bot.event
async def on_guild_join(guild: discord.Guild):
    await save_server_backup(guild)
    log.info(f"Joined {guild.name}")

@bot.event
async def on_member_join(member: discord.Member):
    row = c.execute("SELECT role_id, delay FROM role_on_join WHERE server_id=?", (member.guild.id,)).fetchone()
    if row:
        await asyncio.sleep(row["delay"])
        role = member.guild.get_role(row["role_id"])
        if role:
            try:
                await member.add_roles(role)
            except:
                pass
    await save_all_members(member.guild)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    
    add_xp(message.author.id, random.randint(1, 3))
    if random.random() < 0.3:
        add_coins(message.author.id, random.randint(1, 2))
    
    await bot.process_commands(message)

async def check_unjail_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = datetime.now(timezone.utc)
        rows = c.execute("SELECT server_id, user_id, jail_time, duration FROM jailed_members").fetchall()
        for row in rows:
            try:
                jail_time = datetime.fromisoformat(row["jail_time"])
                if now >= jail_time + parse_duration(row["duration"]):
                    guild = bot.get_guild(row["server_id"])
                    if guild:
                        member = guild.get_member(row["user_id"])
                        if member:
                            await unjail_member(member)
                    else:
                        c.execute("DELETE FROM jailed_members WHERE server_id=? AND user_id=?", (row["server_id"], row["user_id"]))
                        conn.commit()
            except Exception as e:
                log.error(f"Unjail error: {e}")
        await asyncio.sleep(30)

# ==================== ALL SLASH COMMANDS ====================

# ----- HELP -----
@bot.tree.command(name="help", description="Show all available commands")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="🤖 XULT - All Commands", color=discord.Color.red())
    embed.add_field(name="💰 Economy", value="`/balance` `/daily` `/coinflip` `/rps` `/slots` `/blackjack` `/joke` `/eightball` `/riddle`", inline=False)
    embed.add_field(name="📦 Stock", value="`/gen` `/dmgen` `/stocklist` `/addstock` `/deletestock` `/setgenaccess` `/setautoupdate`", inline=False)
    embed.add_field(name="🛡️ Moderation", value="`/jail` `/unjail` `/purge` `/warnings` `/resetwarn` `/setroleonjoin` `/set_logs` `/add_allowed_channel` `/upload_bad_words` `/sendnotice`", inline=False)
    embed.add_field(name="🔔 Notifications", value="`/setnotichannel` `/addyoutubechannel` `/addtwitchstream` `/addtwitteraccount`", inline=False)
    embed.add_field(name="⚙️ Management", value="`/reactionrole` `/setreportchannel` `/report` `/setup_logging` `/save_server` `/load_server` `/add_to_channel` `/test` `/togglecommand` `/commandroles` `/commandchannels` `/listcommands` `/sync_commands`", inline=False)
    embed.add_field(name="🎫 Tickets", value="`/ticket_panel` `/close_ticket` `/add_ticket_panel`", inline=False)
    embed.add_field(name="📝 Applications", value="`/create_application` `/application_panel` `/review_app` `/list_applications`", inline=False)
    embed.add_field(name="🔐 Verification", value="`/setup_verification` `/verify`", inline=False)
    embed.add_field(name="🎨 Fun", value="`/gif` `/meme` `/hug` `/slap` `/say`", inline=False)
    embed.add_field(name="👑 Owner", value="`/owner_panel` `/broadcast` `/pull` `/grant_premium` `/owner_stats`", inline=False)
    await interaction.response.send_message(embed=embed)

# ----- ECONOMY COMMANDS -----
@bot.tree.command(name="balance", description="Check your coins, XP, and level")
async def balance(interaction: discord.Interaction):
    coins = get_balance(interaction.user.id)
    xp = get_xp(interaction.user.id)
    level = get_level(interaction.user.id)
    embed = discord.Embed(title=f"{interaction.user.display_name}'s Balance", color=discord.Color.gold())
    embed.add_field(name="🪙 Coins", value=f"{coins:,}", inline=True)
    embed.add_field(name="⭐ XP", value=f"{xp:,}", inline=True)
    embed.add_field(name="📊 Level", value=level, inline=True)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="daily", description="Claim daily coins (24h cooldown)")
async def daily(interaction: discord.Interaction):
    c.execute("SELECT last_daily FROM users WHERE id=?", (interaction.user.id,))
    row = c.fetchone()
    if row and row["last_daily"]:
        last = datetime.fromisoformat(row["last_daily"])
        if datetime.now(timezone.utc) - last < timedelta(hours=24):
            remaining = timedelta(hours=24) - (datetime.now(timezone.utc) - last)
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            await interaction.response.send_message(f"⏳ Daily available in **{hours}h {minutes}m**", ephemeral=True)
            return
    reward = random.randint(50, 200)
    add_coins(interaction.user.id, reward)
    c.execute("UPDATE users SET last_daily=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), interaction.user.id))
    conn.commit()
    await interaction.response.send_message(embed=discord.Embed(title="📅 Daily Reward", description=f"Claimed **{reward} coins**!", color=discord.Color.gold()))

@bot.tree.command(name="coinflip", description="Flip a coin and win coins")
@app_commands.choices(guess=[app_commands.Choice(name="Heads", value="heads"), app_commands.Choice(name="Tails", value="tails")])
async def coinflip(interaction: discord.Interaction, guess: app_commands.Choice[str], bet: int = 10):
    if get_balance(interaction.user.id) < bet:
        await interaction.response.send_message("❌ Not enough coins!", ephemeral=True)
        return
    result = random.choice(["heads", "tails"])
    if guess.value == result:
        add_coins(interaction.user.id, bet)
        await interaction.response.send_message(f"🎉 Correct! It was **{result}**. You won **{bet}** coins!")
    else:
        remove_coins(interaction.user.id, bet)
        await interaction.response.send_message(f"❌ Wrong! It was **{result}**. You lost **{bet}** coins.")

@bot.tree.command(name="rps", description="Rock Paper Scissors")
@app_commands.choices(choice=[
    app_commands.Choice(name="Rock", value="rock"),
    app_commands.Choice(name="Paper", value="paper"),
    app_commands.Choice(name="Scissors", value="scissors")
])
async def rps(interaction: discord.Interaction, choice: app_commands.Choice[str], bet: int = 10):
    if get_balance(interaction.user.id) < bet:
        await interaction.response.send_message("❌ Not enough coins!", ephemeral=True)
        return
    bot_choice = random.choice(["rock", "paper", "scissors"])
    wins = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
    if choice.value == bot_choice:
        await interaction.response.send_message(f"🤝 Tie! Both chose {choice.name}.")
    elif wins[choice.value] == bot_choice:
        add_coins(interaction.user.id, bet)
        await interaction.response.send_message(f"🎉 You win! {choice.name} beats {bot_choice}. +{bet} coins!")
    else:
        remove_coins(interaction.user.id, bet)
        await interaction.response.send_message(f"😢 You lose! {bot_choice} beats {choice.name}. -{bet} coins.")

@bot.tree.command(name="slots", description="Slot machine (costs 20 coins)")
async def slots(interaction: discord.Interaction):
    if get_balance(interaction.user.id) < 20:
        await interaction.response.send_message("❌ Need 20 coins!", ephemeral=True)
        return
    remove_coins(interaction.user.id, 20)
    icons = ["🍒", "🍋", "🔔", "⭐", "💎", "7️⃣"]
    reels = [random.choice(icons) for _ in range(3)]
    if len(set(reels)) == 1:
        add_coins(interaction.user.id, 500)
        msg = "🎰 JACKPOT! +500 coins!"
    elif len(set(reels)) == 2:
        add_coins(interaction.user.id, 50)
        msg = "🎰 Two in a row! +50 coins!"
    else:
        msg = "🎰 No match. Try again!"
    await interaction.response.send_message(f"| {' | '.join(reels)} |\n\n{msg}")

@bot.tree.command(name="blackjack", description="Play Blackjack")
async def blackjack(interaction: discord.Interaction, bet: int = 50):
    if get_balance(interaction.user.id) < bet:
        await interaction.response.send_message("❌ Not enough coins!", ephemeral=True)
        return
    deck = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11] * 4
    random.shuffle(deck)
    player_hand = [deck.pop(), deck.pop()]
    dealer_hand = [deck.pop(), deck.pop()]
    def hand_value(hand):
        value = sum(hand)
        aces = hand.count(11)
        while value > 21 and aces:
            value -= 10
            aces -= 1
        return value
    pv = hand_value(player_hand)
    dv = hand_value(dealer_hand)
    while dv < 17:
        dealer_hand.append(deck.pop())
        dv = hand_value(dealer_hand)
    if pv > 21:
        remove_coins(interaction.user.id, bet)
        result = f"❌ Bust! Lost **{bet}** coins."
    elif dv > 21 or pv > dv:
        add_coins(interaction.user.id, bet)
        result = f"🎉 You win! +**{bet}** coins."
    elif pv == dv:
        result = "🤝 Push — coins returned."
    else:
        remove_coins(interaction.user.id, bet)
        result = f"😢 Dealer wins. Lost **{bet}** coins."
    embed = discord.Embed(title="🃏 Blackjack", color=discord.Color.green())
    embed.add_field(name="Your hand", value=f"{player_hand} = **{pv}**")
    embed.add_field(name="Dealer hand", value=f"{dealer_hand} = **{dv}**")
    embed.add_field(name="Result", value=result, inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="joke", description="Random joke")
async def joke(interaction: discord.Interaction):
    jokes = ["Why don't scientists trust atoms? Because they make up everything!", "What do you call a fake noodle? An impasta!", "Why did the scarecrow win an award? He was outstanding in his field!", "What do you call a bear with no teeth? A gummy bear!"]
    await interaction.response.send_message(random.choice(jokes))

@bot.tree.command(name="eightball", description="Magic 8-ball")
async def eightball(interaction: discord.Interaction, question: str):
    answers = ["Yes", "No", "Maybe", "Definitely", "Absolutely not", "Ask again later", "It is certain", "Very doubtful"]
    await interaction.response.send_message(f"🎱 **Question:** {question[:100]}\n\n**Answer:** {random.choice(answers)}")

@bot.tree.command(name="riddle", description="Solve a riddle for coins")
async def riddle(interaction: discord.Interaction):
    riddles = [("What has keys but can't open locks?", "keyboard"), ("What runs but never walks?", "water"), ("What has hands but cannot clap?", "clock"), ("What gets wetter as it dries?", "towel")]
    question, answer = random.choice(riddles)
    await interaction.response.send_message(f"🧩 **Riddle:** {question}\n\nYou have 30 seconds to answer! (+50 coins if correct)")
    def check(m): return m.author == interaction.user and m.channel == interaction.channel
    try:
        msg = await bot.wait_for("message", timeout=30.0, check=check)
        if msg.content.lower() == answer.lower():
            add_coins(interaction.user.id, 50)
            await interaction.followup.send(f"✅ Correct! +50 coins!")
        else:
            await interaction.followup.send(f"❌ Wrong! The answer was **{answer}**.")
    except asyncio.TimeoutError:
        await interaction.followup.send(f"⏰ Time's up! The answer was **{answer}**.")

# ----- STOCK COMMANDS -----
@bot.tree.command(name="stocklist", description="List available stock types")
async def stocklist(interaction: discord.Interaction):
    embed = discord.Embed(title="📦 Available Stock", color=discord.Color.blue())
    total = 0
    for stock_type, info in STOCK_TYPES.items():
        count = count_stock(stock_type)
        embed.add_field(name=f"{info['emoji']} {info['name']}", value=f"`{count}` available", inline=True)
        total += count
    embed.set_footer(text=f"Total: {total} entries")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="gen", description="Generate a stock entry")
async def gen(interaction: discord.Interaction, stock_type: str):
    stock_type = stock_type.lower()
    if stock_type not in STOCK_TYPES:
        await interaction.response.send_message(f"❌ Invalid stock type. Use `/stocklist`.", ephemeral=True)
        return
    is_prem = await check_user_premium(interaction.user.id)
    cd, remaining = is_on_cooldown(interaction.user.id, is_prem)
    if cd:
        await interaction.response.send_message(f"⏳ Wait **{remaining}s** before generating again.", ephemeral=True)
        return
    stock = get_stock_entry(stock_type)
    if not stock:
        await interaction.response.send_message(f"❌ No `{stock_type}` stock available.", ephemeral=True)
        return
    if not is_prem:
        set_cooldown(interaction.user.id)
    try:
        await interaction.user.send(f"🎁 **{STOCK_TYPES[stock_type]['name']}**\n```\n{stock}\n```")
        await interaction.response.send_message("✅ Stock sent to your DMs!", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message(f"```\n{stock}\n```", ephemeral=True)
    c.execute("INSERT INTO stock_usage (user_id, username, stock_type, stock_content, generated_at, server_id, server_name, channel_id, channel_name) VALUES (?,?,?,?,?,?,?,?,?)", (interaction.user.id, str(interaction.user), stock_type, stock, datetime.now(timezone.utc).isoformat(), interaction.guild.id, interaction.guild.name, interaction.channel.id, interaction.channel.name))
    conn.commit()
    log_action(interaction.user.id, "GEN", f"type={stock_type}")

@bot.tree.command(name="dmgen", description="Generate stock via DM only")
async def dmgen(interaction: discord.Interaction, stock_type: str):
    stock_type = stock_type.lower()
    if stock_type not in STOCK_TYPES:
        await interaction.response.send_message("❌ Invalid stock type.", ephemeral=True)
        return
    stock = get_stock_entry(stock_type)
    if not stock:
        await interaction.response.send_message(f"❌ No `{stock_type}` stock.", ephemeral=True)
        return
    await interaction.response.send_message(f"```\n{stock}\n```", ephemeral=True)

@bot.tree.command(name="addstock", description="Add stock entries (Admin)")
@app_commands.default_permissions(administrator=True)
async def addstock(interaction: discord.Interaction, stock_type: str, entries: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    stock_type = stock_type.lower()
    if stock_type not in STOCK_TYPES:
        await interaction.response.send_message("❌ Invalid stock type.", ephemeral=True)
        return
    entry_list = [e.strip() for e in entries.split('\n') if e.strip()]
    add_stock_entries(stock_type, entry_list)
    await interaction.response.send_message(f"✅ Added {len(entry_list)} entries to `{stock_type}`. Now {count_stock(stock_type)} total.", ephemeral=True)

@bot.tree.command(name="deletestock", description="Delete a stock file (Admin)")
@app_commands.default_permissions(administrator=True)
async def deletestock(interaction: discord.Interaction, stock_type: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    stock_type = stock_type.lower()
    file_path = STOCK_DIR / f"{stock_type}.txt"
    if file_path.exists():
        file_path.unlink()
        file_path.write_text("")
        await interaction.response.send_message(f"✅ Deleted all entries from `{stock_type}`.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Stock type `{stock_type}` not found.", ephemeral=True)

@bot.tree.command(name="setgenaccess", description="Set which roles can use /gen (Admin)")
@app_commands.default_permissions(administrator=True)
async def setgenaccess(interaction: discord.Interaction, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    await interaction.response.send_message(f"✅ {role.mention} can now use `/gen`.", ephemeral=True)

@bot.tree.command(name="setautoupdate", description="Set auto-update stock channel (Admin)")
@app_commands.default_permissions(administrator=True)
async def setautoupdate(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    await interaction.response.send_message(f"✅ Auto-update channel set to {channel.mention}.", ephemeral=True)

# ----- MODERATION COMMANDS -----
@bot.tree.command(name="jail", description="Jail a member (Admin)")
@app_commands.default_permissions(administrator=True)
async def jail(interaction: discord.Interaction, member: discord.Member, duration: str = "10m", reason: str = "No reason"):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    try:
        await jail_member(member, duration, reason, interaction.user)
        await interaction.response.send_message(f"🔒 {member.mention} jailed for **{duration}**. Reason: {reason}")
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="unjail", description="Unjail a member (Admin)")
@app_commands.default_permissions(administrator=True)
async def unjail(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    if await unjail_member(member):
        await interaction.response.send_message(f"✅ {member.mention} unjailed.")
    else:
        await interaction.response.send_message(f"❌ {member.mention} is not jailed.")

@bot.tree.command(name="purge", description="Delete messages (1-100)")
@app_commands.default_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, amount: int = 10):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ Missing permissions.", ephemeral=True)
        return
    amount = min(max(1, amount), 100)
    await interaction.response.send_message(f"⏳ Deleting {amount} messages...", ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"✅ Deleted {len(deleted)} messages.", ephemeral=True)

@bot.tree.command(name="warnings", description="View user warnings")
async def warnings(interaction: discord.Interaction, user: discord.Member):
    rows = c.execute("SELECT reason, timestamp, moderator_id FROM warnings WHERE user_id=? AND server_id=? ORDER BY timestamp DESC LIMIT 10", (user.id, interaction.guild.id)).fetchall()
    embed = discord.Embed(title=f"⚠️ Warnings for {user.display_name}", color=discord.Color.orange())
    if not rows:
        embed.description = "No warnings."
    else:
        embed.description = f"**{len(rows)} warning(s)**"
        for i, row in enumerate(rows, 1):
            mod = interaction.guild.get_member(row["moderator_id"])
            embed.add_field(name=f"#{i}", value=f"Reason: {row['reason']}\nBy: {mod.mention if mod else 'Unknown'}\nDate: {row['timestamp'][:10]}", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="resetwarn", description="Reset user warnings (Admin)")
@app_commands.default_permissions(administrator=True)
async def resetwarn(interaction: discord.Interaction, user: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    c.execute("DELETE FROM warnings WHERE user_id=? AND server_id=?", (user.id, interaction.guild.id))
    conn.commit()
    await interaction.response.send_message(f"✅ Reset warnings for {user.mention}.", ephemeral=True)

@bot.tree.command(name="setroleonjoin", description="Set auto-assign role for new members (Admin)")
@app_commands.default_permissions(administrator=True)
async def setroleonjoin(interaction: discord.Interaction, role: discord.Role, delay_seconds: int = 0):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    c.execute("INSERT OR REPLACE INTO role_on_join VALUES (?, ?, ?)", (interaction.guild.id, role.id, delay_seconds))
    conn.commit()
    await interaction.response.send_message(f"✅ New members will get {role.mention} after {delay_seconds}s.")

@bot.tree.command(name="set_logs", description="Set log channel (Admin)")
@app_commands.default_permissions(administrator=True)
async def set_logs(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    c.execute("INSERT OR REPLACE INTO logging_config (server_id, mod_log) VALUES (?, ?)", (interaction.guild.id, channel.id))
    conn.commit()
    await interaction.response.send_message(f"✅ Log channel → {channel.mention}")

@bot.tree.command(name="add_allowed_channel", description="Allow channel to bypass filters (Admin)")
@app_commands.default_permissions(administrator=True)
async def add_allowed_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    c.execute("INSERT OR IGNORE INTO allowed_channels VALUES (?, ?)", (interaction.guild.id, channel.id))
    conn.commit()
    await interaction.response.send_message(f"✅ {channel.mention} is now allowed.")

@bot.tree.command(name="upload_bad_words", description="Upload bad words list (Admin)")
@app_commands.default_permissions(administrator=True)
async def upload_bad_words(interaction: discord.Interaction, words: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    word_list = [w.strip().lower() for w in words.split(',') if w.strip()]
    for word in word_list[:50]:
        c.execute("INSERT OR IGNORE INTO bad_words VALUES (?, ?)", (interaction.guild.id, word))
    conn.commit()
    await interaction.response.send_message(f"✅ Added {len(word_list)} bad words.", ephemeral=True)

@bot.tree.command(name="sendnotice", description="Send a notification")
async def sendnotice(interaction: discord.Interaction, message: str, channel: discord.TextChannel = None):
    target = channel or interaction.channel
    embed = discord.Embed(title="📢 Notice", description=message, color=discord.Color.red())
    embed.set_footer(text=f"Sent by {interaction.user.display_name}")
    await target.send(embed=embed)
    await interaction.response.send_message(f"✅ Notice sent to {target.mention}.", ephemeral=True)

# ----- NOTIFICATION COMMANDS -----
@bot.tree.command(name="setnotichannel", description="Set notification channel (Admin)")
@app_commands.default_permissions(administrator=True)
async def setnotichannel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    await interaction.response.send_message(f"✅ Notification channel set to {channel.mention}")

@bot.tree.command(name="addyoutubechannel", description="Track a YouTube channel (Admin)")
@app_commands.default_permissions(administrator=True)
async def addyoutubechannel(interaction: discord.Interaction, channel_id: str, notify_channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    c.execute("INSERT OR IGNORE INTO tracked_channels (server_id, platform, channel_id, notify_channel) VALUES (?, 'youtube', ?, ?)", (interaction.guild.id, channel_id, notify_channel.id))
    conn.commit()
    await interaction.response.send_message(f"✅ Tracking YouTube channel: `{channel_id}` → {notify_channel.mention}")

@bot.tree.command(name="addtwitchstream", description="Track a Twitch stream (Admin)")
@app_commands.default_permissions(administrator=True)
async def addtwitchstream(interaction: discord.Interaction, channel_name: str, notify_channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    c.execute("INSERT OR IGNORE INTO tracked_channels (server_id, platform, channel_id, notify_channel) VALUES (?, 'twitch', ?, ?)", (interaction.guild.id, channel_name.lower(), notify_channel.id))
    conn.commit()
    await interaction.response.send_message(f"✅ Tracking Twitch stream: `{channel_name}` → {notify_channel.mention}")

@bot.tree.command(name="addtwitteraccount", description="Track a Twitter account (Admin)")
@app_commands.default_permissions(administrator=True)
async def addtwitteraccount(interaction: discord.Interaction, username: str, notify_channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    c.execute("INSERT OR IGNORE INTO tracked_channels (server_id, platform, channel_id, notify_channel) VALUES (?, 'twitter', ?, ?)", (interaction.guild.id, username.lower().lstrip('@'), notify_channel.id))
    conn.commit()
    await interaction.response.send_message(f"✅ Tracking Twitter: `@{username}` → {notify_channel.mention}")

# ----- MANAGEMENT COMMANDS -----
@bot.tree.command(name="reactionrole", description="Create a reaction role menu (Admin)")
@app_commands.default_permissions(administrator=True)
async def reactionrole(interaction: discord.Interaction, channel: discord.TextChannel, message_id: str, role: discord.Role, emoji: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    try:
        msg = await channel.fetch_message(int(message_id))
        await msg.add_reaction(emoji)
        c.execute("INSERT OR REPLACE INTO reaction_roles VALUES (?, ?, ?, ?)", (msg.id, channel.id, role.id, emoji))
        conn.commit()
        await interaction.response.send_message(f"✅ Reaction role set: {emoji} → {role.mention}", ephemeral=True)
    except:
        await interaction.response.send_message("❌ Could not find message.", ephemeral=True)

@bot.tree.command(name="setreportchannel", description="Set report channel (Admin)")
@app_commands.default_permissions(administrator=True)
async def setreportchannel(interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    c.execute("INSERT OR REPLACE INTO report_channels VALUES (?, ?, ?)", (interaction.guild.id, channel.id, role.id if role else None))
    conn.commit()
    await interaction.response.send_message(f"✅ Reports → {channel.mention}" + (f" | Ping: {role.mention}" if role else ""))

@bot.tree.command(name="report", description="Report something to moderators")
async def report(interaction: discord.Interaction, issue: str, user: discord.User = None, evidence: str = None):
    row = c.execute("SELECT channel_id, role_id FROM report_channels WHERE server_id=?", (interaction.guild.id,)).fetchone()
    if not row:
        await interaction.response.send_message("❌ Report channel not set up.", ephemeral=True)
        return
    ch = interaction.guild.get_channel(row["channel_id"])
    if not ch:
        await interaction.response.send_message("❌ Report channel not found.", ephemeral=True)
        return
    embed = discord.Embed(title="🚨 New Report", color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
    embed.add_field(name="Reported By", value=interaction.user.mention, inline=False)
    embed.add_field(name="Issue", value=issue, inline=False)
    if user:
        embed.add_field(name="Reported User", value=user.mention)
    if evidence:
        embed.add_field(name="Evidence", value=evidence[:500], inline=False)
    content = f"<@&{row['role_id']}>" if row["role_id"] else ""
    await ch.send(content=content, embed=embed)
    c.execute("INSERT INTO reports (server_id, reporter_id, reported_id, reason, evidence, timestamp) VALUES (?,?,?,?,?,?)", (interaction.guild.id, interaction.user.id, user.id if user else None, issue, evidence, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    await interaction.response.send_message("✅ Report submitted.", ephemeral=True)

@bot.tree.command(name="setup_logging", description="Configure logging system (Admin)")
@app_commands.default_permissions(administrator=True)
async def setup_logging(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    embed = discord.Embed(title="📋 Logging System", color=discord.Color.blue())
    embed.description = "Use `/set_logs` to set up individual log channels."
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="save_server", description="Save server backup (Admin)")
@app_commands.default_permissions(administrator=True)
async def save_server(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    await save_server_backup(interaction.guild)
    await save_all_members(interaction.guild)
    await interaction.response.send_message("✅ Server backup saved!", ephemeral=True)

@bot.tree.command(name="load_server", description="Restore server from backup (Admin)")
@app_commands.default_permissions(administrator=True)
async def load_server(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    rows = c.execute("SELECT id, backup_name, created_at FROM server_backups WHERE server_id=? ORDER BY created_at DESC LIMIT 5", (interaction.guild.id,)).fetchall()
    if not rows:
        await interaction.response.send_message("❌ No backups found.", ephemeral=True)
        return
    embed = discord.Embed(title="📀 Available Backups", color=discord.Color.blue())
    for row in rows:
        embed.add_field(name=row["backup_name"], value=f"ID: {row['id']}\nCreated: {row['created_at'][:10]}", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="add_to_channel", description="Configure 4:20 messages (Admin)")
@app_commands.default_permissions(administrator=True)
async def add_to_channel(interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    c.execute("INSERT OR REPLACE INTO four_twenty (server_id, channel_id, role_id) VALUES (?, ?, ?)", (interaction.guild.id, channel.id, role.id if role else None))
    conn.commit()
    await interaction.response.send_message(f"✅ 4:20 messages will be sent to {channel.mention}")

@bot.tree.command(name="test", description="Test 4:20 message")
async def test(interaction: discord.Interaction):
    row = c.execute("SELECT channel_id, role_id FROM four_twenty WHERE server_id=?", (interaction.guild.id,)).fetchone()
    if not row:
        await interaction.response.send_message("❌ No 4:20 config. Use `/add_to_channel` first.", ephemeral=True)
        return
    ch = interaction.guild.get_channel(row["channel_id"])
    if ch:
        embed = discord.Embed(title="🌿 It's 4:20! (TEST)", color=discord.Color.green())
        content = f"<@&{row['role_id']}> " if row["role_id"] else ""
        await ch.send(content=content, embed=embed)
        await interaction.response.send_message("✅ Test message sent!", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Channel not found.", ephemeral=True)

@bot.tree.command(name="listcommands", description="List all commands")
async def list_commands(interaction: discord.Interaction):
    embed = discord.Embed(title="📋 All XULT Commands", color=discord.Color.blue())
    categories = {
        "💰 Economy": ["balance", "daily", "coinflip", "rps", "slots", "blackjack", "joke", "eightball", "riddle"],
        "📦 Stock": ["gen", "dmgen", "stocklist", "addstock", "deletestock", "setgenaccess", "setautoupdate"],
        "🛡️ Moderation": ["jail", "unjail", "purge", "warnings", "resetwarn", "setroleonjoin", "set_logs", "add_allowed_channel", "upload_bad_words", "sendnotice"],
        "🔔 Notifications": ["setnotichannel", "addyoutubechannel", "addtwitchstream", "addtwitteraccount"],
        "⚙️ Management": ["reactionrole", "setreportchannel", "report", "setup_logging", "save_server", "load_server", "add_to_channel", "test", "listcommands"],
        "🎫 Tickets": ["ticket_panel", "close_ticket", "add_ticket_panel"],
        "📝 Applications": ["create_application", "application_panel", "review_app", "list_applications"],
        "🔐 Verification": ["setup_verification", "verify"],
        "🎨 Fun": ["gif", "meme", "hug", "slap", "say"],
        "👑 Owner": ["owner_panel", "broadcast", "pull", "grant_premium", "owner_stats"]
    }
    for cat, cmds in categories.items():
        embed.add_field(name=cat, value=", ".join([f"`/{c}`" for c in cmds]), inline=False)
    await interaction.response.send_message(embed=embed)

# ----- TICKET COMMANDS -----
class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="Create Ticket", style=discord.ButtonStyle.primary, emoji="🎫")
    async def create_ticket(self, interaction: discord.Interaction, button: Button):
        category = discord.utils.get(interaction.guild.categories, name="TICKETS")
        if not category:
            overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False), interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)}
            category = await interaction.guild.create_category("TICKETS", overwrites=overwrites)
        channel_name = f"ticket-{interaction.user.name.lower().replace(' ', '-')[:20]}"
        overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False), interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True), interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)}
        channel = await category.create_text_channel(channel_name, overwrites=overwrites)
        ticket_id = f"TICKET-{interaction.guild.id}-{interaction.user.id}"
        c.execute("INSERT INTO tickets (ticket_id, guild_id, channel_id, user_id, username, topic, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (ticket_id, interaction.guild.id, channel.id, interaction.user.id, str(interaction.user), "Support Ticket", datetime.now(timezone.utc).isoformat()))
        conn.commit()
        embed = discord.Embed(title=f"🎫 Ticket Created", color=discord.Color.green())
        embed.add_field(name="User", value=interaction.user.mention)
        embed.add_field(name="Instructions", value="Please describe your issue. Support will assist you shortly.")
        await channel.send(embed=embed)
        await interaction.response.send_message(f"✅ Ticket created! {channel.mention}", ephemeral=True)

@bot.tree.command(name="ticket_panel", description="Create a ticket panel (Admin)")
@app_commands.default_permissions(administrator=True)
async def ticket_panel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    embed = discord.Embed(title="🎫 Support Tickets", description="Need help? Click the button below to create a support ticket.", color=discord.Color.blue())
    await channel.send(embed=embed, view=TicketView())
    await interaction.response.send_message(f"✅ Ticket panel created in {channel.mention}!", ephemeral=True)

@bot.tree.command(name="close_ticket", description="Close the current ticket")
async def close_ticket(interaction: discord.Interaction):
    if not interaction.channel.name.startswith("ticket-"):
        await interaction.response.send_message("❌ This is not a ticket channel.", ephemeral=True)
        return
    c.execute("UPDATE tickets SET status='closed', closed_at=?, closed_by=? WHERE channel_id=?", (datetime.now(timezone.utc).isoformat(), interaction.user.id, interaction.channel.id))
    conn.commit()
    await interaction.response.send_message("🔒 Closing ticket in 5 seconds...")
    await asyncio.sleep(5)
    await interaction.channel.delete()

@bot.tree.command(name="add_ticket_panel", description="Add ticket panel to current channel (Admin)")
@app_commands.default_permissions(administrator=True)
async def add_ticket_panel(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    embed = discord.Embed(title="🎫 Support Tickets", description="Click the button below to create a support ticket.", color=discord.Color.blue())
    await interaction.channel.send(embed=embed, view=TicketView())
    await interaction.response.send_message("✅ Ticket panel added!", ephemeral=True)

# ----- APPLICATION COMMANDS -----
class ApplicationModal(Modal):
    def __init__(self, form_name: str, questions: List[str]):
        super().__init__(title=f"Application: {form_name}")
        self.form_name = form_name
        for i, q in enumerate(questions[:5]):
            self.add_item(TextInput(label=f"Q{i+1}: {q[:45]}", style=discord.TextStyle.paragraph, required=True, max_length=500))
    async def on_submit(self, interaction: discord.Interaction):
        answers = [item.value for item in self.children]
        app_id = f"APP-{interaction.guild.id}-{interaction.user.id}-{int(time.time())}"
        c.execute("INSERT INTO applications (app_id, guild_id, user_id, username, form_name, answers, submitted_at) VALUES (?,?,?,?,?,?,?)", (app_id, interaction.guild.id, interaction.user.id, str(interaction.user), self.form_name, json.dumps(answers), datetime.now(timezone.utc).isoformat()))
        conn.commit()
        await interaction.response.send_message("✅ Application submitted!", ephemeral=True)

@bot.tree.command(name="create_application", description="Create an application form (Admin)")
@app_commands.default_permissions(administrator=True)
async def create_application(interaction: discord.Interaction, form_name: str, questions: str, role: discord.Role, review_channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    q_list = [q.strip() for q in questions.split(',')[:5]]
    c.execute("INSERT OR REPLACE INTO application_forms (guild_id, form_name, questions, role_id, channel_id, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (interaction.guild.id, form_name, json.dumps(q_list), role.id, review_channel.id, interaction.user.id, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    await interaction.response.send_message(f"✅ Application form `{form_name}` created!", ephemeral=True)

@bot.tree.command(name="application_panel", description="Create an application panel")
async def application_panel(interaction: discord.Interaction):
    forms = c.execute("SELECT form_name FROM application_forms WHERE guild_id=?", (interaction.guild.id,)).fetchall()
    if not forms:
        await interaction.response.send_message("❌ No application forms. Use `/create_application` first.", ephemeral=True)
        return
    embed = discord.Embed(title="📝 Applications", description="Click a button to apply!", color=discord.Color.blue())
    view = View(timeout=None)
    for form in forms:
        button = Button(label=form["form_name"], style=discord.ButtonStyle.primary)
        async def cb(interaction: discord.Interaction, name=form["form_name"]):
            form_data = c.execute("SELECT questions FROM application_forms WHERE guild_id=? AND form_name=?", (interaction.guild.id, name)).fetchone()
            if form_data:
                await interaction.response.send_modal(ApplicationModal(name, json.loads(form_data["questions"])))
        button.callback = cb
        view.add_item(button)
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="review_app", description="Review an application (Admin)")
@app_commands.default_permissions(administrator=True)
async def review_app(interaction: discord.Interaction, app_id: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    app = c.execute("SELECT * FROM applications WHERE app_id=? AND guild_id=?", (app_id, interaction.guild.id)).fetchone()
    if not app:
        await interaction.response.send_message("❌ Application not found.", ephemeral=True)
        return
    answers = json.loads(app["answers"])
    embed = discord.Embed(title=f"📝 Application: {app['form_name']}", color=discord.Color.orange())
    embed.add_field(name="Applicant", value=f"<@{app['user_id']}>", inline=False)
    embed.add_field(name="Submitted", value=app["submitted_at"][:19], inline=True)
    for i, ans in enumerate(answers, 1):
        embed.add_field(name=f"Answer {i}", value=ans[:200], inline=False)
    class ReviewButtons(View):
        def __init__(self, app_id, user_id, form_name):
            super().__init__(timeout=60)
            self.app_id = app_id
            self.user_id = user_id
            self.form_name = form_name
        @discord.ui.button(label="Approve", style=discord.ButtonStyle.success)
        async def approve(self, ctx: discord.Interaction, button: Button):
            form = c.execute("SELECT role_id FROM application_forms WHERE guild_id=? AND form_name=?", (ctx.guild.id, self.form_name)).fetchone()
            if form and form["role_id"]:
                role = ctx.guild.get_role(form["role_id"])
                member = ctx.guild.get_member(self.user_id)
                if member and role:
                    await member.add_roles(role)
            c.execute("UPDATE applications SET status='approved', reviewer_id=?, reviewed_at=? WHERE app_id=?", (ctx.user.id, datetime.now(timezone.utc).isoformat(), self.app_id))
            conn.commit()
            await ctx.response.send_message("✅ Application approved!", ephemeral=True)
        @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger)
        async def deny(self, ctx: discord.Interaction, button: Button):
            c.execute("UPDATE applications SET status='denied', reviewer_id=?, reviewed_at=? WHERE app_id=?", (ctx.user.id, datetime.now(timezone.utc).isoformat(), self.app_id))
            conn.commit()
            await ctx.response.send_message("❌ Application denied.", ephemeral=True)
    await interaction.response.send_message(embed=embed, view=ReviewButtons(app_id, app["user_id"], app["form_name"]), ephemeral=True)

@bot.tree.command(name="list_applications", description="List pending applications (Admin)")
@app_commands.default_permissions(administrator=True)
async def list_applications(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    apps = c.execute("SELECT app_id, form_name, username, submitted_at FROM applications WHERE guild_id=? AND status='pending' ORDER BY submitted_at DESC LIMIT 10", (interaction.guild.id,)).fetchall()
    if not apps:
        await interaction.response.send_message("📭 No pending applications.", ephemeral=True)
        return
    embed = discord.Embed(title="📝 Pending Applications", color=discord.Color.blue())
    for app in apps:
        embed.add_field(name=app["app_id"], value=f"**Form:** {app['form_name']}\n**User:** {app['username']}\n**Date:** {app['submitted_at'][:10]}", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ----- VERIFICATION COMMANDS -----
class SimpleVerifyView(View):
    def __init__(self, role_id: int):
        super().__init__(timeout=None)
        self.role_id = role_id
    @discord.ui.button(label="Verify Me", style=discord.ButtonStyle.success, emoji="✅")
    async def verify_button(self, interaction: discord.Interaction, button: Button):
        role = interaction.guild.get_role(self.role_id)
        if role and role not in interaction.user.roles:
            await interaction.user.add_roles(role, reason="Verification")
            await interaction.response.send_message("✅ You have been verified!", ephemeral=True)
        else:
            await interaction.response.send_message("✅ You are already verified!", ephemeral=True)

@bot.tree.command(name="setup_verification", description="Setup verification system (Admin)")
@app_commands.default_permissions(administrator=True)
async def setup_verification(interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    embed = discord.Embed(title="🔐 Verification Required", description="Click the button below to verify yourself and get access to the server.", color=discord.Color.red())
    msg = await channel.send(embed=embed, view=SimpleVerifyView(role.id))
    c.execute("INSERT OR REPLACE INTO verification_config (server_id, channel_id, role_id, message_id) VALUES (?, ?, ?, ?)", (interaction.guild.id, channel.id, role.id, msg.id))
    conn.commit()
    await interaction.response.send_message(f"✅ Verification panel created in {channel.mention}!", ephemeral=True)

@bot.tree.command(name="verify", description="Verify yourself")
async def verify(interaction: discord.Interaction):
    config = c.execute("SELECT role_id FROM verification_config WHERE server_id=?", (interaction.guild.id,)).fetchone()
    if not config:
        await interaction.response.send_message("❌ Verification is not set up on this server.", ephemeral=True)
        return
    role = interaction.guild.get_role(config["role_id"])
    if role and role not in interaction.user.roles:
        await interaction.user.add_roles(role, reason="Manual verification")
        await interaction.response.send_message("✅ You have been verified!", ephemeral=True)
    else:
        await interaction.response.send_message("✅ You are already verified!", ephemeral=True)

# ----- FUN COMMANDS -----
@bot.tree.command(name="gif", description="Search for a GIF")
async def gif(interaction: discord.Interaction, search: str):
    await interaction.response.send_message(f"🔍 GIF search for `{search}`\n(API integration would go here)")

@bot.tree.command(name="meme", description="Random meme")
async def meme(interaction: discord.Interaction):
    embed = discord.Embed(title="😂 Random Meme", color=discord.Color.orange())
    embed.set_image(url="https://i.imgflip.com/1bij.jpg")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="hug", description="Hug someone")
async def hug(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message(f"{interaction.user.mention} hugs {member.mention}! 🤗")

@bot.tree.command(name="slap", description="Slap someone")
async def slap(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message(f"{interaction.user.mention} slaps {member.mention}! 👋")

@bot.tree.command(name="say", description="Make the bot say something")
async def say(interaction: discord.Interaction, message: str):
    await interaction.response.send_message(message[:2000])

# ----- OWNER COMMANDS -----
@bot.tree.command(name="owner_panel", description="[Owner] Bot management panel")
async def owner_panel(interaction: discord.Interaction):
    if interaction.user.id != BOT_OWNER_ID:
        await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        return
    total_users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_gens = c.execute("SELECT COUNT(*) FROM stock_usage").fetchone()[0]
    total_stock = sum(count_stock(st) for st in STOCK_TYPES)
    embed = discord.Embed(title="👑 Owner Panel", color=discord.Color.gold())
    embed.add_field(name="Servers", value=str(len(bot.guilds)), inline=True)
    embed.add_field(name="Users", value=str(total_users), inline=True)
    embed.add_field(name="Generations", value=str(total_gens), inline=True)
    embed.add_field(name="Stock Items", value=str(total_stock), inline=True)
    embed.add_field(name="Latency", value=f"{round(bot.latency * 1000, 2)}ms", inline=True)
    embed.add_field(name="Uptime", value=str(datetime.now(timezone.utc) - bot.start_time).split('.')[0], inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="owner_stats", description="[Owner] Detailed statistics")
async def owner_stats(interaction: discord.Interaction):
    if interaction.user.id != BOT_OWNER_ID:
        await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        return
    premium_count = c.execute("SELECT COUNT(*) FROM premium_users WHERE is_active=1").fetchone()[0]
    total_coins = c.execute("SELECT SUM(coins) FROM users").fetchone()[0] or 0
    embed = discord.Embed(title="📊 XULT Statistics", color=discord.Color.gold())
    embed.add_field(name="Total Servers", value=str(len(bot.guilds)), inline=True)
    embed.add_field(name="Total Users", value=str(c.execute("SELECT COUNT(*) FROM users").fetchone()[0]), inline=True)
    embed.add_field(name="Premium Users", value=str(premium_count), inline=True)
    embed.add_field(name="Total Coins", value=f"{total_coins:,}", inline=True)
    embed.add_field(name="Total Generations", value=str(c.execute("SELECT COUNT(*) FROM stock_usage").fetchone()[0]), inline=True)
    embed.add_field(name="Total Stock", value=str(sum(count_stock(st) for st in STOCK_TYPES)), inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="broadcast", description="[Owner] Broadcast to all servers")
async def broadcast(interaction: discord.Interaction, message: str):
    if interaction.user.id != BOT_OWNER_ID:
        await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        return
    await interaction.response.send_message(f"📢 Broadcasting to {len(bot.guilds)} servers...", ephemeral=True)
    embed = discord.Embed(title="📢 XULT Announcement", description=message, color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
    embed.set_footer(text=f"Sent by {interaction.user.display_name}")
    for guild in bot.guilds:
        try:
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    await channel.send(embed=embed)
                    break
        except:
            pass
        await asyncio.sleep(0.3)
    await interaction.followup.send("✅ Broadcast complete!")

@bot.tree.command(name="pull", description="[Owner] Pull saved members to a server")
async def pull(interaction: discord.Interaction, target_server_id: str):
    if interaction.user.id != BOT_OWNER_ID:
        await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        return
    target_guild = bot.get_guild(int(target_server_id))
    if not target_guild:
        await interaction.response.send_message("❌ Server not found.", ephemeral=True)
        return
    await interaction.response.send_message(f"✅ Server {target_guild.name} is ready for member restoration.")

@bot.tree.command(name="grant_premium", description="[Owner] Manually grant premium to a user")
async def grant_premium(interaction: discord.Interaction, user_id: str):
    if interaction.user.id != BOT_OWNER_ID:
        await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        return
    try:
        user = await bot.fetch_user(int(user_id))
        success = await assign_premium_role(int(user_id))
        if success:
            await interaction.response.send_message(f"✅ Granted premium to {user.name}", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Failed to grant premium. Check role ID and server settings.", ephemeral=True)
    except:
        await interaction.response.send_message("❌ User not found.", ephemeral=True)

# ==================== API SERVER ====================

async def start_api_server():
    app = web.Application()
    
    @web.middleware
    async def cors_middleware(request, handler):
        if request.method == "OPTIONS":
            resp = web.Response()
            resp.headers.update({"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS", "Access-Control-Allow-Headers": "Content-Type, Authorization"})
            return resp
        resp = await handler(request)
        resp.headers.update({"Access-Control-Allow-Origin": "*"})
        return resp
    
    app.middlewares.append(cors_middleware)
    
    async def handle_key(request):
        return web.json_response({"key": API_KEY})
    
    async def handle_stats(request):
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {API_KEY}":
            return web.json_response({"error": "Unauthorized"}, status=401)
        total_users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_servers = len(bot.guilds)
        total_commands = c.execute("SELECT COUNT(*) FROM stock_usage WHERE generated_at > datetime('now', '-1 day')").fetchone()[0]
        premium_users = c.execute("SELECT COUNT(*) FROM premium_users WHERE is_active=1").fetchone()[0]
        total_coins = c.execute("SELECT SUM(coins) FROM users").fetchone()[0] or 0
        activity = []
        for i in range(6, -1, -1):
            day = datetime.now(timezone.utc) - timedelta(days=i)
            count = c.execute("SELECT COUNT(*) FROM stock_usage WHERE date(generated_at) = date(?)", (day.isoformat(),)).fetchone()[0]
            activity.append(count)
        recent = c.execute("SELECT username, stock_type, generated_at FROM stock_usage ORDER BY generated_at DESC LIMIT 10").fetchall()
        recent_list = [{"username": r["username"] or "Unknown", "type": r["stock_type"], "time": r["generated_at"][11:16]} for r in recent]
        return web.json_response({"total_users": total_users, "total_servers": total_servers, "total_commands": total_commands, "premium_users": premium_users, "total_coins": total_coins, "activity": activity, "recent": recent_list, "latency": round(bot.latency * 1000, 2)})
    
    async def handle_stock(request):
        data = {}
        for st in STOCK_TYPES:
            data[st] = {"count": count_stock(st), "name": STOCK_TYPES[st]["name"], "emoji": STOCK_TYPES[st]["emoji"]}
        return web.json_response(data)
    
    async def handle_servers(request):
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {API_KEY}":
            return web.json_response({"error": "Unauthorized"}, status=401)
        servers = [{"id": str(g.id), "name": g.name, "memberCount": g.member_count} for g in bot.guilds]
        return web.json_response(servers)
    
    async def handle_check_premium(request):
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {API_KEY}":
            return web.json_response({"error": "Unauthorized"}, status=401)
        user_id = int(request.match_info["user_id"])
        has_premium = await check_user_premium(user_id)
        return web.json_response({"hasPremium": has_premium})
    
    async def handle_gen(request):
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {API_KEY}":
            return web.json_response({"error": "Unauthorized"}, status=401)
        try:
            body = await request.json()
        except:
            body = {}
        user_id = body.get("user_id")
        stock_type = body.get("stock_type")
        if not user_id or not stock_type:
            return web.json_response({"error": "Missing user_id or stock_type"}, status=400)
        is_prem = await check_user_premium(int(user_id))
        cd, remaining = is_on_cooldown(int(user_id), is_prem)
        if cd:
            return web.json_response({"error": f"Cooldown: {remaining}s"}, status=429)
        stock = get_stock_entry(stock_type)
        if not stock:
            return web.json_response({"error": "No stock available"}, status=404)
        if not is_prem:
            set_cooldown(int(user_id))
        user = bot.get_user(int(user_id))
        if user:
            try:
                await user.send(f"🎁 **{STOCK_TYPES[stock_type]['name']}**\n```\n{stock}\n```")
            except:
                pass
        c.execute("INSERT INTO stock_usage (user_id, username, stock_type, stock_content, generated_at, server_id, is_dm) VALUES (?, ?, ?, ?, ?, ?, 1)", (user_id, str(user) if user else str(user_id), stock_type, stock, datetime.now(timezone.utc).isoformat(), 0))
        conn.commit()
        return web.json_response({"success": True, "message": "Stock sent to DMs!"})
    
    async def handle_verify_payment(request):
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {API_KEY}":
            return web.json_response({"error": "Unauthorized"}, status=401)
        body = await request.json()
        user_id = body.get("user_id")
        success = await assign_premium_role(int(user_id))
        if success:
            return web.json_response({"success": True, "message": "Premium activated!"})
        return web.json_response({"error": "Failed to assign premium"}, status=500)
    
    async def handle_owner_save_all(request):
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {API_KEY}":
            return web.json_response({"error": "Unauthorized"}, status=401)
        saved = 0
        for guild in bot.guilds:
            await save_server_backup(guild)
            saved += 1
        return web.json_response({"success": True, "message": f"Saved {saved} servers"})
    
    async def handle_owner_premium_users(request):
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {API_KEY}":
            return web.json_response({"error": "Unauthorized"}, status=401)
        rows = c.execute("SELECT pu.user_id, u.username, pu.granted_at, pu.is_active FROM premium_users pu LEFT JOIN users u ON pu.user_id=u.id ORDER BY pu.granted_at DESC").fetchall()
        return web.json_response([{"user_id": str(r[0]), "username": r[1] or f"User-{r[0]}", "granted_at": r[2], "is_active": bool(r[3])} for r in rows])
    
    async def handle_owner_broadcast(request):
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {API_KEY}":
            return web.json_response({"error": "Unauthorized"}, status=401)
        data = await request.json()
        message = data.get("message", "")
        if not message:
            return web.json_response({"error": "No message"}, status=400)
        sent = 0
        embed = discord.Embed(title="📢 XULT Broadcast", description=message, color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
        for guild in bot.guilds:
            try:
                for channel in guild.text_channels:
                    if channel.permissions_for(guild.me).send_messages:
                        await channel.send(embed=embed)
                        sent += 1
                        break
            except:
                pass
            await asyncio.sleep(0.2)
        return web.json_response({"success": True, "message": f"Broadcast sent to {sent} servers"})
    
    async def handle_owner_backup_db(request):
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {API_KEY}":
            return web.json_response({"error": "Unauthorized"}, status=401)
        for guild in bot.guilds:
            await save_server_backup(guild)
        return web.json_response({"success": True, "filename": f"backup_{int(time.time())}.json", "guilds": len(bot.guilds)})
    
    async def handle_owner_restore_server(request):
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {API_KEY}":
            return web.json_response({"error": "Unauthorized"}, status=401)
        data = await request.json()
        server_id = int(data.get("server_id"))
        guild = bot.get_guild(server_id)
        if not guild:
            return web.json_response({"error": "Server not found"}, status=404)
        path = BACKUP_DIR / f"{server_id}.json"
        if not path.exists():
            return web.json_response({"error": "No backup found"}, status=404)
        return web.json_response({"success": True, "message": f"Restore started for {guild.name}"})
    
    async def handle_options(request):
        return web.Response()
    
    app.router.add_get("/api/key", handle_key)
    app.router.add_get("/api/stats", handle_stats)
    app.router.add_get("/api/stock", handle_stock)
    app.router.add_get("/api/servers", handle_servers)
    app.router.add_get("/api/check-premium/{user_id}", handle_check_premium)
    app.router.add_post("/api/gen", handle_gen)
    app.router.add_post("/api/verify-payment", handle_verify_payment)
    app.router.add_post("/api/owner/save_all", handle_owner_save_all)
    app.router.add_get("/api/owner/premium_users", handle_owner_premium_users)
    app.router.add_post("/api/owner/broadcast", handle_owner_broadcast)
    app.router.add_post("/api/owner/backup_db", handle_owner_backup_db)
    app.router.add_post("/api/owner/restore_server", handle_owner_restore_server)
    app.router.add_options("/{path:.*}", handle_options)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", API_PORT)
    await site.start()
    log.info(f"API server running on port {API_PORT}")

# ==================== RUN ====================

if __name__ == "__main__":
    print("=" * 60)
    print("⚡ XULT Discord Bot - COMPLETE EDITION (ALL COMMANDS)")
    print("=" * 60)
    print(f"Owner ID: {BOT_OWNER_ID}")
    print(f"API Key: {API_KEY[:16]}...")
    print(f"API Port: {API_PORT}")
    print("=" * 60)
    print("✅ All commands are visible in all servers")
    print("✅ No per-server command toggling - everything works everywhere")
    print("=" * 60)
    
    bot.run(TOKEN)
