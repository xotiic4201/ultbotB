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

CLIENT_ID     = os.getenv("CLIENT_ID", "1417284780675956766")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")
REDIRECT_URI  = os.getenv("REDIRECT_URI", "https://ultbot-f.vercel.app/callback")

YOUTUBE_API_KEY      = os.getenv("YOUTUBE_API_KEY", "")
TWITCH_CLIENT_ID     = os.getenv("TWITCH_CLIENT_ID", "")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")
GIPHY_API_KEY        = os.getenv("GIPHY_API_KEY", "dimlVnesALO2DLu14diWdZAAcZIgW1L1")

BOT_OWNER_ID    = int(os.getenv("BOT_OWNER_ID", "1302203907782606880"))
PREMIUM_ROLE_ID = int(os.getenv("PREMIUM_ROLE_ID", "1474136325912399994"))
MAIN_SERVER_ID  = int(os.getenv("MAIN_SERVER_ID", "1344385779627069541"))
GEN_LOG_CHANNEL_ID = int(os.getenv("GEN_LOG_CHANNEL_ID", "1353956858263765033"))
TARGET_SERVER_ID   = int(os.getenv("TARGET_SERVER_ID", "1309396933789483038"))

API_PORT = int(os.getenv("PORT", os.getenv("API_PORT", "10000")))

BASE_DIR   = Path.cwd()
DATA_DIR   = BASE_DIR / "data";   DATA_DIR.mkdir(exist_ok=True)
BACKUP_DIR = DATA_DIR / "backups"; BACKUP_DIR.mkdir(exist_ok=True)
STOCK_DIR  = BASE_DIR / "stock";   STOCK_DIR.mkdir(exist_ok=True)

DISCORD_API_URL = "https://discord.com/api/v10"
OWNER_ID = 1302203907782606880

_KEY_FILE = DATA_DIR / "api_key.txt"
if _KEY_FILE.exists():
    API_KEY = _KEY_FILE.read_text().strip()
else:
    API_KEY = os.getenv("API_KEY", secrets.token_hex(32))
    _KEY_FILE.write_text(API_KEY)

# ==================== DATABASE ====================

conn = sqlite3.connect(DATA_DIR / "xultti.db", check_same_thread=False)
conn.row_factory = sqlite3.Row
c = conn.cursor()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, username TEXT, avatar TEXT,
    coins INTEGER DEFAULT 0, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1,
    last_daily TIMESTAMP, role TEXT DEFAULT 'user', premium_expires TIMESTAMP,
    banned INTEGER DEFAULT 0, banned_reason TEXT,
    access_token TEXT, refresh_token TEXT, token_expires TIMESTAMP,
    is_owner INTEGER DEFAULT 0, premium_verified INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS server_configs (
    server_id INTEGER PRIMARY KEY, prefix TEXT DEFAULT '!',
    log_channel INTEGER, welcome_channel INTEGER, welcome_message TEXT,
    leave_channel INTEGER, leave_message TEXT, auto_role INTEGER,
    mod_role INTEGER, admin_role INTEGER, muted_role INTEGER, config TEXT
);
CREATE TABLE IF NOT EXISTS command_settings (
    server_id INTEGER, command_name TEXT,
    enabled INTEGER DEFAULT 1, allowed_roles TEXT, disabled_channels TEXT,
    PRIMARY KEY (server_id, command_name)
);
CREATE TABLE IF NOT EXISTS premium_users (
    user_id INTEGER PRIMARY KEY, guild_id INTEGER, role_id INTEGER,
    granted_at TIMESTAMP, expires_at TIMESTAMP, is_active INTEGER DEFAULT 1,
    payment_id TEXT, payment_method TEXT
);
CREATE TABLE IF NOT EXISTS stock_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT,
    stock_type TEXT, stock_content TEXT, generated_at TIMESTAMP,
    server_id INTEGER, server_name TEXT, channel_id INTEGER, channel_name TEXT,
    is_dm INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS user_cooldowns (
    user_id INTEGER PRIMARY KEY, last_generated TIMESTAMP, generation_count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, moderator_id INTEGER,
    reason TEXT, timestamp TIMESTAMP, server_id INTEGER
);
CREATE TABLE IF NOT EXISTS jailed_members (
    server_id INTEGER, user_id INTEGER, roles TEXT, jail_time TIMESTAMP,
    duration TEXT, reason TEXT, jailed_by INTEGER,
    PRIMARY KEY (server_id, user_id)
);
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, action TEXT,
    details TEXT, ip TEXT, timestamp TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY, user_id INTEGER, access_token TEXT,
    refresh_token TEXT, expires_at TIMESTAMP, created_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS shop (name TEXT PRIMARY KEY, price INTEGER, description TEXT, role_id INTEGER);
CREATE TABLE IF NOT EXISTS lottery (user_id INTEGER, entry_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS tracked_channels (
    server_id INTEGER, platform TEXT, channel_id TEXT, last_post_id TEXT,
    role_id INTEGER, notify_channel INTEGER,
    PRIMARY KEY (server_id, platform, channel_id)
);
CREATE TABLE IF NOT EXISTS reaction_roles (
    message_id INTEGER, channel_id INTEGER, role_id INTEGER, emoji TEXT,
    PRIMARY KEY (message_id, emoji)
);
CREATE TABLE IF NOT EXISTS role_on_join (server_id INTEGER PRIMARY KEY, role_id INTEGER, delay INTEGER);
CREATE TABLE IF NOT EXISTS bad_words (server_id INTEGER, word TEXT, PRIMARY KEY (server_id, word));
CREATE TABLE IF NOT EXISTS allowed_channels (server_id INTEGER, channel_id INTEGER, PRIMARY KEY (server_id, channel_id));
CREATE TABLE IF NOT EXISTS four_twenty (
    server_id INTEGER PRIMARY KEY, channel_id INTEGER, role_id INTEGER,
    voice_channel_id INTEGER, timezone TEXT DEFAULT 'UTC'
);
CREATE TABLE IF NOT EXISTS verification (
    server_id INTEGER PRIMARY KEY, channel_id INTEGER, role_id INTEGER,
    log_channel_id INTEGER, message_id INTEGER, verified_role_id INTEGER,
    require_oauth INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS report_channels (server_id INTEGER PRIMARY KEY, channel_id INTEGER, role_id INTEGER);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT, server_id INTEGER, reporter_id INTEGER,
    reported_id INTEGER, reason TEXT, evidence TEXT, status TEXT DEFAULT 'pending', timestamp TIMESTAMP
);
CREATE TABLE IF NOT EXISTS channel_activity (
    channel_id INTEGER PRIMARY KEY, server_id INTEGER, message_count INTEGER DEFAULT 0,
    unique_users INTEGER DEFAULT 0, last_message TIMESTAMP, last_reset TIMESTAMP
);
CREATE TABLE IF NOT EXISTS saved_members (
    user_id INTEGER, username TEXT, avatar TEXT, roles TEXT,
    saved_at TIMESTAMP, server_id INTEGER, PRIMARY KEY (user_id, server_id)
);
CREATE TABLE IF NOT EXISTS oauth_states (state TEXT PRIMARY KEY, created_at TIMESTAMP, redirect_uri TEXT);
CREATE TABLE IF NOT EXISTS server_backups (
    id INTEGER PRIMARY KEY AUTOINCREMENT, server_id INTEGER, backup_name TEXT,
    backup_data TEXT, created_at TIMESTAMP, created_by INTEGER
);
CREATE TABLE IF NOT EXISTS pending_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, payment_id TEXT,
    amount REAL, method TEXT, status TEXT DEFAULT 'pending',
    created_at TIMESTAMP, verified_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id TEXT UNIQUE,
    guild_id INTEGER, channel_id INTEGER, user_id INTEGER, username TEXT,
    topic TEXT, priority TEXT DEFAULT 'normal', status TEXT DEFAULT 'open',
    created_at TIMESTAMP, closed_at TIMESTAMP, closed_by INTEGER, transcript TEXT
);
CREATE TABLE IF NOT EXISTS ticket_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id TEXT, user_id INTEGER,
    username TEXT, message TEXT, attachment_url TEXT, timestamp TIMESTAMP
);
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT, app_id TEXT UNIQUE,
    guild_id INTEGER, user_id INTEGER, username TEXT, form_name TEXT,
    answers TEXT, status TEXT DEFAULT 'pending', reviewer_id INTEGER,
    review_message TEXT, submitted_at TIMESTAMP, reviewed_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS application_forms (
    id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, form_name TEXT,
    questions TEXT, role_id INTEGER, channel_id INTEGER, log_channel_id INTEGER,
    created_by INTEGER, created_at TIMESTAMP, UNIQUE(guild_id, form_name)
);
CREATE TABLE IF NOT EXISTS logging_config (
    server_id INTEGER PRIMARY KEY, mod_log INTEGER, member_log INTEGER,
    message_log INTEGER, voice_log INTEGER, server_log INTEGER, ticket_log INTEGER,
    app_log INTEGER, report_log INTEGER, bot_update_log INTEGER
);
"""
for stmt in _SCHEMA.strip().split(";"):
    if stmt.strip():
        try:
            c.execute(stmt)
        except Exception as e:
            log.warning(f"Schema warning: {e}")
conn.commit()

c.execute("INSERT OR IGNORE INTO users (id, username, is_owner, premium_verified) VALUES (?, ?, 1, 1)", (OWNER_ID, "Owner"))
c.execute("UPDATE users SET is_owner=1, premium_verified=1 WHERE id=?", (OWNER_ID,))
conn.commit()

for name, price, desc, role_id in [("VIP Role",500,"Gives VIP role",None),("Double XP",300,"Double XP 24h",None),("Mystery Box",100,"Random reward",None)]:
    c.execute("INSERT OR IGNORE INTO shop VALUES (?,?,?,?)", (name,price,desc,role_id))
conn.commit()

# ==================== JSON DATA ====================

JSON_FILES = {
    "server_settings": DATA_DIR / "server_settings.json",
    "gen_access":      DATA_DIR / "gen_access.json",
    "auto_update":     DATA_DIR / "auto_update.json",
    "log_channels":    DATA_DIR / "log_channels.json",
}
for fp in JSON_FILES.values():
    if not fp.exists(): fp.write_text("{}")

def load_json(file_path, default=None):
    try:    return json.loads(file_path.read_text()) or (default if default is not None else {})
    except: return default if default is not None else {}

def save_json(file_path, data):
    file_path.write_text(json.dumps(data, indent=2))

def log_action(user_id: int, action: str, details: str = ""):
    c.execute("INSERT INTO logs (user_id,action,details,timestamp) VALUES (?,?,?,?)",
              (user_id, action, details, datetime.now(timezone.utc).isoformat()))
    conn.commit()

# ==================== INTENTS & BOT ====================

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
bot.start_time = datetime.now(timezone.utc)
bot.owner_id = OWNER_ID
command_sync_cooldown: Dict[int, datetime] = {}

# ==================== ALL COMMANDS LIST ====================
# This is the master list — every command the bot has.
# Commands are synced PER GUILD with only the enabled ones visible.

ALL_COMMANDS = [
    # Economy
    "balance","daily","coinflip","rps","slots","blackjack","joke","eightball","riddle",
    # Stock / Gen
    "gen","dmgen","stocklist","addstock","deletestock","setgenaccess","setautoupdate",
    # Moderation
    "jail","unjail","purge","warnings","resetwarn","setroleonjoin","set_logs",
    "add_allowed_channel","upload_bad_words","sendnotice",
    # Notifications
    "setnotichannel","addyoutubechannel","addtwitchstream","addtwitteraccount",
    # Server Management
    "reactionrole","setreportchannel","report","setup_logging","save_server","load_server",
    "add_to_channel","test","togglecommand","commandroles","commandchannels",
    "listcommands","sync_commands","sync_all_commands",
    # Tickets
    "ticket_panel","close_ticket","add_ticket_panel",
    # Applications
    "create_application","application_panel","review_app","list_applications",
    # Verification
    "verify","setup_oauth_verification",
    # Fun
    "gif","meme","hug","slap","say",
    # Owner
    "owner_panel","owner_stats","broadcastupdate","pull",
]

CMD_CATEGORIES = {
    "economy":      ["balance","daily","coinflip","rps","slots","blackjack","joke","eightball","riddle"],
    "stock":        ["gen","dmgen","stocklist","addstock","deletestock","setgenaccess","setautoupdate"],
    "moderation":   ["jail","unjail","purge","warnings","resetwarn","setroleonjoin","set_logs","add_allowed_channel","upload_bad_words","sendnotice"],
    "notifications":["setnotichannel","addyoutubechannel","addtwitchstream","addtwitteraccount"],
    "management":   ["reactionrole","setreportchannel","report","setup_logging","save_server","load_server","add_to_channel","test","togglecommand","commandroles","commandchannels","listcommands","sync_commands","sync_all_commands"],
    "tickets":      ["ticket_panel","close_ticket","add_ticket_panel"],
    "applications": ["create_application","application_panel","review_app","list_applications"],
    "verification": ["verify","setup_oauth_verification"],
    "fun":          ["gif","meme","hug","slap","say"],
    "owner":        ["owner_panel","owner_stats","broadcastupdate","pull"],
}

# ==================== PERMISSION HELPERS ====================

def is_command_enabled(guild_id: int, command_name: str) -> bool:
    c.execute("SELECT enabled FROM command_settings WHERE server_id=? AND command_name=?", (guild_id, command_name))
    row = c.fetchone()
    return row[0] == 1 if row else True

def get_command_allowed_roles(guild_id: int, command_name: str) -> List[int]:
    c.execute("SELECT allowed_roles FROM command_settings WHERE server_id=? AND command_name=?", (guild_id, command_name))
    row = c.fetchone()
    if row and row[0]:
        return json.loads(row[0])
    return []

def get_command_disabled_channels(guild_id: int, command_name: str) -> List[int]:
    c.execute("SELECT disabled_channels FROM command_settings WHERE server_id=? AND command_name=?", (guild_id, command_name))
    row = c.fetchone()
    if row and row[0]:
        return json.loads(row[0])
    return []

def update_command_setting(guild_id: int, command_name: str, enabled: bool,
                           allowed_roles: List[int] = None, disabled_channels: List[int] = None):
    c.execute("""INSERT OR REPLACE INTO command_settings
                 (server_id,command_name,enabled,allowed_roles,disabled_channels)
                 VALUES (?,?,?,?,?)""",
              (guild_id, command_name.lower(), 1 if enabled else 0,
               json.dumps(allowed_roles) if allowed_roles else None,
               json.dumps(disabled_channels) if disabled_channels else None))
    conn.commit()

# ==================== CORE GUILD SYNC ====================
# This is the KEY function: syncs only ENABLED commands to a guild.
# Disabled commands literally don't exist in that guild's slash menu.

async def sync_guild_commands(guild: discord.Guild) -> Tuple[int, int]:
    """Sync enabled-only commands to a guild. Returns (enabled_count, disabled_count)."""
    enabled, disabled = [], []
    for cmd_name in ALL_COMMANDS:
        cmd = bot.tree.get_command(cmd_name)
        if cmd:
            if is_command_enabled(guild.id, cmd_name):
                enabled.append(cmd)
            else:
                disabled.append(cmd_name)

    # Clear and re-add only enabled commands for this guild
    bot.tree.clear_commands(guild=guild)
    for cmd in enabled:
        bot.tree.add_command(cmd, guild=guild)
    try:
        await bot.tree.sync(guild=guild)
        log.info(f"Guild {guild.id} ({guild.name}): synced {len(enabled)} commands, hidden {len(disabled)}")
    except discord.HTTPException as e:
        log.error(f"Sync failed for guild {guild.id}: {e}")
    return len(enabled), len(disabled)

# ==================== LOGGING ====================

def get_logging_config(guild_id: int) -> dict:
    row = c.execute("SELECT * FROM logging_config WHERE server_id=?", (guild_id,)).fetchone()
    return dict(row) if row else {"server_id": guild_id}

def update_logging_config(guild_id: int, log_type: str, channel_id: int):
    c.execute(f"""INSERT INTO logging_config (server_id,{log_type}) VALUES (?,?)
                 ON CONFLICT(server_id) DO UPDATE SET {log_type}=?""",
              (guild_id, channel_id, channel_id))
    conn.commit()

async def send_log(guild_id: int, log_type: str, embed: discord.Embed):
    config = get_logging_config(guild_id)
    channel_id = config.get(log_type)
    if not channel_id: return
    guild = bot.get_guild(guild_id)
    if not guild: return
    channel = guild.get_channel(channel_id)
    if not channel: return
    try:
        await channel.send(embed=embed)
    except Exception as e:
        log.error(f"Log send failed: {e}")

# ==================== TICKET SYSTEM ====================

class TicketModal(Modal):
    def __init__(self, topic: str = None):
        super().__init__(title="Create Support Ticket")
        self.topic_input = TextInput(label="Ticket Topic", placeholder="Brief description...", required=True, max_length=100)
        self.description_input = TextInput(label="Description", placeholder="Details about your issue...", style=discord.TextStyle.paragraph, required=True, max_length=1000)
        self.priority_select = TextInput(label="Priority (low/normal/high/urgent)", placeholder="normal", required=False, max_length=20)
        if topic: self.topic_input.default = topic
        self.add_item(self.topic_input)
        self.add_item(self.description_input)
        self.add_item(self.priority_select)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        topic = self.topic_input.value
        description = self.description_input.value
        priority = (self.priority_select.value or "normal").lower()
        if priority not in ["low","normal","high","urgent"]: priority = "normal"
        ticket_id = f"TICKET-{interaction.guild.id}-{interaction.user.id}-{int(datetime.now().timestamp())}"
        category = discord.utils.get(interaction.guild.categories, name="Tickets") or await interaction.guild.create_category("Tickets")
        channel_name = f"ticket-{interaction.user.name.lower()[:12]}-{ticket_id[-6:]}"
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        channel = await category.create_text_channel(channel_name, overwrites=overwrites)
        c.execute("""INSERT INTO tickets (ticket_id,guild_id,channel_id,user_id,username,topic,priority,status,created_at)
                     VALUES (?,?,?,?,?,?,?,?,?)""",
                  (ticket_id, interaction.guild.id, channel.id, interaction.user.id, str(interaction.user), topic, priority, "open", datetime.now(timezone.utc).isoformat()))
        conn.commit()
        embed = discord.Embed(title=f"🎫 {ticket_id}", color=discord.Color.green(), timestamp=datetime.now(timezone.utc))
        embed.add_field(name="Topic", value=topic, inline=False)
        embed.add_field(name="Description", value=description, inline=False)
        embed.add_field(name="Priority", value=priority.upper(), inline=True)
        embed.add_field(name="Opened By", value=interaction.user.mention, inline=True)
        await channel.send(embed=embed)
        await channel.send(f"{interaction.user.mention} Support will be with you shortly.")
        await interaction.followup.send(f"✅ Ticket created! {channel.mention}", ephemeral=True)
        log_action(interaction.user.id, "CREATE_TICKET", f"ticket={ticket_id}")

class TicketPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Create Ticket", style=discord.ButtonStyle.primary, emoji="🎫", custom_id="create_ticket")
    async def create_ticket_button(self, interaction: discord.Interaction, button: Button):
        existing = c.execute("SELECT ticket_id,channel_id FROM tickets WHERE guild_id=? AND user_id=? AND status='open'",
                             (interaction.guild.id, interaction.user.id)).fetchone()
        if existing:
            ch = interaction.guild.get_channel(existing["channel_id"])
            msg = f"You already have an open ticket: {ch.mention}" if ch else "You already have an open ticket."
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
            return
        await interaction.response.send_modal(TicketModal())

    @discord.ui.button(label="My Tickets", style=discord.ButtonStyle.secondary, emoji="📋", custom_id="my_tickets")
    async def my_tickets_button(self, interaction: discord.Interaction, button: Button):
        tickets = c.execute("SELECT ticket_id,topic,status,created_at FROM tickets WHERE guild_id=? AND user_id=? ORDER BY created_at DESC LIMIT 10",
                            (interaction.guild.id, interaction.user.id)).fetchall()
        if not tickets:
            await interaction.response.send_message("📭 No tickets found.", ephemeral=True)
            return
        embed = discord.Embed(title="📋 Your Tickets", color=discord.Color.blue())
        for t in tickets:
            emoji = "🟢" if t["status"] == "open" else "🔴"
            embed.add_field(name=f"{emoji} {t['ticket_id']}",
                          value=f"**Topic:** {t['topic']}\n**Status:** {t['status'].upper()}\n**Created:** {t['created_at'][:10]}",
                          inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ==================== APPLICATION SYSTEM ====================

class ApplicationModal(Modal):
    def __init__(self, form_name: str, questions: List[str]):
        super().__init__(title=f"Application: {form_name}")
        self.questions = questions
        for i, question in enumerate(questions[:5]):
            self.add_item(TextInput(
                label=f"Q{i+1}: {question[:45]}",
                placeholder="Your answer...",
                required=True,
                style=discord.TextStyle.paragraph if len(question) > 50 else discord.TextStyle.short,
                max_length=500
            ))

    async def on_submit(self, interaction: discord.Interaction):
        answers = [item.value for item in self.children]
        form_name = self.title.replace("Application: ", "")
        form = c.execute("SELECT role_id,channel_id FROM application_forms WHERE guild_id=? AND form_name=?",
                        (interaction.guild.id, form_name)).fetchone()
        if not form:
            await interaction.response.send_message("❌ Form not found.", ephemeral=True)
            return
        app_id = f"APP-{interaction.guild.id}-{interaction.user.id}-{int(datetime.now().timestamp())}"
        answers_json = json.dumps(list(zip(self.questions[:5], answers)))
        c.execute("""INSERT INTO applications (app_id,guild_id,user_id,username,form_name,answers,status,submitted_at)
                     VALUES (?,?,?,?,?,?,?,?)""",
                  (app_id, interaction.guild.id, interaction.user.id, str(interaction.user),
                   form_name, answers_json, "pending", datetime.now(timezone.utc).isoformat()))
        conn.commit()
        review_ch = interaction.guild.get_channel(form["channel_id"])
        if review_ch:
            embed = discord.Embed(title=f"📝 New Application: {form_name}", color=discord.Color.orange(), timestamp=datetime.now(timezone.utc))
            embed.add_field(name="Applicant", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
            embed.add_field(name="App ID", value=app_id, inline=True)
            for i, (q, a) in enumerate(zip(self.questions[:5], answers), 1):
                embed.add_field(name=f"Q{i}: {q[:50]}", value=a[:200], inline=False)
            await review_ch.send(embed=embed, view=ApplicationReviewView(app_id))
        await interaction.response.send_message("✅ Application submitted!", ephemeral=True)

class ApplicationReviewView(View):
    def __init__(self, app_id: str):
        super().__init__(timeout=None)
        self.app_id = app_id

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, emoji="✅")
    async def approve(self, interaction: discord.Interaction, button: Button):
        app = c.execute("SELECT user_id,form_name,status FROM applications WHERE app_id=?", (self.app_id,)).fetchone()
        if not app or app["status"] != "pending":
            await interaction.response.send_message("❌ Already reviewed.", ephemeral=True); return
        c.execute("UPDATE applications SET status='approved',reviewer_id=?,reviewed_at=? WHERE app_id=?",
                  (interaction.user.id, datetime.now(timezone.utc).isoformat(), self.app_id))
        conn.commit()
        form = c.execute("SELECT role_id FROM application_forms WHERE guild_id=? AND form_name=?",
                        (interaction.guild.id, app["form_name"])).fetchone()
        member = interaction.guild.get_member(app["user_id"])
        if member and form and form["role_id"]:
            role = interaction.guild.get_role(form["role_id"])
            if role:
                await member.add_roles(role, reason=f"App approved: {self.app_id}")
                try: await member.send(f"✅ Your **{app['form_name']}** application was approved!")
                except: pass
        await interaction.response.send_message(f"✅ Approved {self.app_id}!", ephemeral=True)
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.add_field(name="Status", value="✅ APPROVED", inline=False)
        await interaction.message.edit(embed=embed, view=None)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, emoji="❌")
    async def deny(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(DenyReasonModal(self.app_id))

class DenyReasonModal(Modal):
    def __init__(self, app_id: str):
        super().__init__(title="Deny Application")
        self.app_id = app_id
        self.reason_input = TextInput(label="Reason", style=discord.TextStyle.paragraph, required=True, max_length=500)
        self.add_item(self.reason_input)

    async def on_submit(self, interaction: discord.Interaction):
        app = c.execute("SELECT user_id,form_name FROM applications WHERE app_id=?", (self.app_id,)).fetchone()
        if not app:
            await interaction.response.send_message("❌ Not found.", ephemeral=True); return
        c.execute("UPDATE applications SET status='denied',reviewer_id=?,review_message=?,reviewed_at=? WHERE app_id=?",
                  (interaction.user.id, self.reason_input.value, datetime.now(timezone.utc).isoformat(), self.app_id))
        conn.commit()
        member = interaction.guild.get_member(app["user_id"])
        if member:
            try: await member.send(f"❌ Your **{app['form_name']}** application was denied.\nReason: {self.reason_input.value}")
            except: pass
        await interaction.response.send_message(f"❌ Denied {self.app_id}.", ephemeral=True)

class ApplicationPanelView(View):
    def __init__(self, forms):
        super().__init__(timeout=None)
        for form_name, _ in forms[:5]:
            btn = Button(label=form_name, style=discord.ButtonStyle.primary, custom_id=f"app_{form_name}")
            btn.callback = self.create_cb(form_name)
            self.add_item(btn)

    def create_cb(self, form_name: str):
        async def cb(interaction: discord.Interaction):
            form = c.execute("SELECT questions FROM application_forms WHERE guild_id=? AND form_name=?",
                            (interaction.guild.id, form_name)).fetchone()
            if not form:
                await interaction.response.send_message("❌ Form not found.", ephemeral=True); return
            existing = c.execute("SELECT status FROM applications WHERE guild_id=? AND user_id=? AND form_name=? AND status!='denied'",
                                (interaction.guild.id, interaction.user.id, form_name)).fetchone()
            if existing:
                await interaction.response.send_message(f"❌ You already have a {existing['status']} application.", ephemeral=True); return
            await interaction.response.send_modal(ApplicationModal(form_name, json.loads(form["questions"])))
        return cb

# ==================== STOCK TYPES ====================

STOCK_TYPES = {
    "steam":     {"name":"Steam Accounts",    "emoji":"🎮","price":3},
    "netflix":   {"name":"Netflix Accounts",  "emoji":"🎬","price":3},
    "spotify":   {"name":"Spotify Accounts",  "emoji":"🎵","price":3},
    "discord":   {"name":"Discord Nitro",     "emoji":"💎","price":3},
    "minecraft": {"name":"Minecraft Accounts","emoji":"⛏️","price":3},
    "roblox":    {"name":"Roblox Accounts",   "emoji":"🎮","price":3},
    "epicgames": {"name":"Epic Games",        "emoji":"⚡","price":3},
    "instagram": {"name":"Instagram",         "emoji":"📸","price":3},
    "mega":      {"name":"MEGA Links",        "emoji":"📁","price":3},
    "email":     {"name":"Email Accounts",    "emoji":"📧","price":3},
    "accounts":  {"name":"General Accounts",  "emoji":"👤","price":3},
    "randomip":  {"name":"Random IP",         "emoji":"🌐","price":3},
    "combo":     {"name":"Combos",            "emoji":"🔐","price":3},
}

# ==================== GLOBALS ====================

user_cooldowns:    Dict[int, float] = {}
notified_streams:  Dict[str, str]   = {}
active_riddle = riddle_answer = None
FREE_GEN_TIMEOUT  = 5
LEVEL_ROLES       = {5:"Level 5", 10:"Level 10"}
BLOCK_WORDS       = ["nigger","niggas","niggers","jews","chinks","nazis","fags","fagots","nigga","fagot","discord.gg/"]
RIDDLES           = [
    ("What has keys but can't open locks?","keyboard"),
    ("What runs but never walks?","water"),
    ("What has hands but cannot clap?","clock"),
]

EVENT_CHANNEL_KEYWORDS = [
    "general","chat","main","discussion","lounge","talk","global",
    "world","public","community","social","offtopic","off-topic",
    "general-chat","main-chat","town-square","gen"
]

# ==================== STOCK HELPERS ====================

def get_stock_filename(stock_type: str) -> Path:
    return STOCK_DIR / f"{stock_type.lower().strip().replace(' ','_')}.txt"

def create_stock_file(stock_type: str):
    fp = get_stock_filename(stock_type)
    if not fp.exists(): fp.write_text("", encoding="utf-8")

def count_stock(stock_type: str) -> int:
    fp = get_stock_filename(stock_type); create_stock_file(stock_type)
    try:
        content = fp.read_text(encoding="utf-8").strip()
        if not content: return 0
        return len([x for x in (content.split('\n\n') if '\n\n' in content else content.split('\n')) if x.strip()])
    except: return 0

def read_stock_entries(stock_type: str) -> list:
    fp = get_stock_filename(stock_type); create_stock_file(stock_type)
    try:
        content = fp.read_text(encoding="utf-8").strip()
        if not content: return []
        return [x.strip() for x in (content.split('\n\n') if '\n\n' in content else content.split('\n')) if x.strip()]
    except: return []

def write_stock_entries(stock_type: str, entries: list):
    get_stock_filename(stock_type).write_text('\n\n'.join(str(e) for e in entries), encoding="utf-8")

def get_stock_entry(stock_type: str) -> Optional[str]:
    entries = read_stock_entries(stock_type)
    if not entries: return None
    first = entries[0]; write_stock_entries(stock_type, entries[1:]); return first

def add_stock_entries(stock_type: str, new_entries: list):
    current = read_stock_entries(stock_type)
    current.extend(new_entries)
    write_stock_entries(stock_type, current)

def is_on_cooldown(user_id: int, is_premium: bool = False) -> Tuple[bool, int]:
    if is_premium: return False, 0
    elapsed = time.time() - user_cooldowns.get(user_id, 0)
    if elapsed < FREE_GEN_TIMEOUT: return True, int(FREE_GEN_TIMEOUT - elapsed)
    return False, 0

def set_cooldown(user_id: int): user_cooldowns[user_id] = time.time()

# ==================== ECONOMY ====================

def get_balance(user_id: int) -> int:
    c.execute("SELECT coins FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    if row: return row[0]
    c.execute("INSERT INTO users (id,coins,xp,level) VALUES (?,0,0,1)", (user_id,)); conn.commit(); return 0

def add_coins(user_id: int, amount: int):
    c.execute("UPDATE users SET coins=coins+? WHERE id=?", (amount, user_id))
    if c.rowcount == 0: c.execute("INSERT INTO users (id,coins) VALUES (?,?)", (user_id, amount))
    conn.commit()

def remove_coins(user_id: int, amount: int):
    bal = get_balance(user_id)
    c.execute("UPDATE users SET coins=? WHERE id=?", (max(0, bal-amount), user_id)); conn.commit()

def get_xp(user_id: int) -> int:
    c.execute("SELECT xp FROM users WHERE id=?", (user_id,)); row = c.fetchone(); return row[0] if row else 0

def get_level(user_id: int) -> int:
    c.execute("SELECT level FROM users WHERE id=?", (user_id,)); row = c.fetchone(); return row[0] if row else 1

def add_xp(user_id: int, amount: int) -> bool:
    xp = get_xp(user_id); lvl = get_level(user_id); new_xp = xp + amount
    c.execute("UPDATE users SET xp=? WHERE id=?", (new_xp, user_id)); conn.commit()
    new_lvl = int(new_xp ** 0.5)
    if new_lvl > lvl:
        c.execute("UPDATE users SET level=? WHERE id=?", (new_lvl, user_id)); conn.commit(); return True
    return False

# ==================== PREMIUM ====================

async def check_user_premium(user_id: int) -> bool:
    if user_id == OWNER_ID: return True
    guild = bot.get_guild(MAIN_SERVER_ID)
    if not guild: return False
    member = guild.get_member(user_id)
    if not member: return False
    role = guild.get_role(PREMIUM_ROLE_ID)
    return role in member.roles if role else False

async def assign_premium_role(user_id: int) -> bool:
    guild = bot.get_guild(MAIN_SERVER_ID)
    if not guild: return False
    member = guild.get_member(user_id)
    if not member: return False
    role = guild.get_role(PREMIUM_ROLE_ID)
    if not role: return False
    try:
        await member.add_roles(role, reason="Premium purchase verified")
        c.execute("""INSERT OR REPLACE INTO premium_users (user_id,guild_id,role_id,granted_at,is_active)
                     VALUES (?,?,?,?,1)""", (user_id, MAIN_SERVER_ID, PREMIUM_ROLE_ID, datetime.now(timezone.utc).isoformat()))
        c.execute("UPDATE users SET premium_verified=1 WHERE id=?", (user_id,)); conn.commit()
        return True
    except: return False

# ==================== MODERATION ====================

def parse_duration(duration: str) -> timedelta:
    matches = re.findall(r'(\d+)([smhd])', duration.lower())
    if not matches: raise ValueError("Invalid duration. Use e.g. 10m, 2h, 1d")
    total = timedelta()
    for amt, unit in matches:
        amt = int(amt)
        total += {"s":timedelta(seconds=amt),"m":timedelta(minutes=amt),"h":timedelta(hours=amt),"d":timedelta(days=amt)}[unit]
    return total

def contains_bad_word(content: str, guild_id: int) -> bool:
    normalized = re.sub(r'[^a-zA-Z0-9\s]','',content.lower()).split()
    for word in BLOCK_WORDS:
        for w in normalized:
            if difflib.get_close_matches(w,[word],n=1,cutoff=0.85): return True
    for (word,) in c.execute("SELECT word FROM bad_words WHERE server_id=?", (guild_id,)).fetchall():
        for w in normalized:
            if difflib.get_close_matches(w,[word],n=1,cutoff=0.85): return True
    return False

def get_server_config(guild_id: int) -> dict:
    c.execute("SELECT * FROM server_configs WHERE server_id=?", (guild_id,))
    row = c.fetchone()
    if row:
        cfg = json.loads(row["config"]) if row["config"] else {}
        return dict(row, config=cfg)
    return {"server_id":guild_id,"prefix":"!","config":{}}

# ==================== JAIL ====================

async def jail_member(member: discord.Member, duration: str, reason: str, moderator: discord.Member):
    # Create jail channels if needed
    jail_text = discord.utils.get(member.guild.text_channels, name="jail")
    if not jail_text:
        ow = {member.guild.default_role: discord.PermissionOverwrite(read_messages=False),
              member.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)}
        jail_text = await member.guild.create_text_channel("jail", overwrites=ow)
    jail_voice = discord.utils.get(member.guild.voice_channels, name="Jail VC")
    if not jail_voice:
        ow = {member.guild.default_role: discord.PermissionOverwrite(connect=False),
              member.guild.me: discord.PermissionOverwrite(connect=True)}
        jail_voice = await member.guild.create_voice_channel("Jail VC", overwrites=ow)
    original = [r for r in member.roles if r.name != "@everyone"]
    await member.remove_roles(*original, reason=f"Jailed: {reason}")
    await jail_text.set_permissions(member, read_messages=True, send_messages=True)
    await jail_voice.set_permissions(member, connect=True, speak=True)
    if member.voice and member.voice.channel:
        await member.move_to(jail_voice)
    c.execute("""INSERT OR REPLACE INTO jailed_members (server_id,user_id,roles,jail_time,duration,reason,jailed_by)
                 VALUES (?,?,?,?,?,?,?)""",
              (member.guild.id, member.id, json.dumps([r.id for r in original]),
               datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'), duration, reason, moderator.id))
    conn.commit()
    try: await member.send(f"🔒 Jailed in **{member.guild.name}** for **{duration}**. Reason: {reason}")
    except: pass

async def unjail_member(member: discord.Member) -> bool:
    row = c.execute("SELECT roles FROM jailed_members WHERE server_id=? AND user_id=?", (member.guild.id, member.id)).fetchone()
    if not row: return False
    roles = [member.guild.get_role(r) for r in json.loads(row[0]) if member.guild.get_role(r)]
    if roles: await member.add_roles(*roles, reason="Unjailed")
    for ch_name, ch_type in [("jail","text"),("Jail VC","voice")]:
        ch = discord.utils.get(member.guild.text_channels if ch_type=="text" else member.guild.voice_channels, name=ch_name)
        if ch: await ch.set_permissions(member, overwrite=None)
    c.execute("DELETE FROM jailed_members WHERE server_id=? AND user_id=?", (member.guild.id, member.id)); conn.commit()
    try: await member.send(f"✅ Unjailed from **{member.guild.name}**.")
    except: pass
    return True

# ==================== BACKUP ====================

def save_server_backup(guild: discord.Guild):
    backup = {"roles":[],"categories":[],"channels":[],"settings":get_server_config(guild.id)}
    for role in guild.roles:
        if role.name != "@everyone":
            backup["roles"].append({"name":role.name,"color":role.color.value,"hoist":role.hoist,
                                    "mentionable":role.mentionable,"permissions":role.permissions.value,"position":role.position})
    for cat in guild.categories:
        ow = {}
        for t, p in cat.overwrites.items():
            if isinstance(t, discord.Role):
                allow, deny = p.pair()
                ow[str(t.id)] = {"allow":allow.value,"deny":deny.value}
        backup["categories"].append({"name":cat.name,"position":cat.position,"overwrites":ow})
    for ch in list(guild.text_channels)+list(guild.voice_channels):
        ow = {}
        for t, p in ch.overwrites.items():
            if isinstance(t, discord.Role):
                allow, deny = p.pair()
                ow[str(t.id)] = {"allow":allow.value,"deny":deny.value}
        backup["channels"].append({
            "name":ch.name,"type":"text" if isinstance(ch, discord.TextChannel) else "voice",
            "category":ch.category.name if ch.category else None,"position":ch.position,"overwrites":ow,
            "topic":ch.topic if isinstance(ch, discord.TextChannel) else None,
        })
    save_json(BACKUP_DIR / f"{guild.id}.json", backup)
    c.execute("INSERT INTO server_backups (server_id,backup_name,backup_data,created_at,created_by) VALUES (?,?,?,?,?)",
              (guild.id, f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}", json.dumps(backup),
               datetime.now(timezone.utc).isoformat(), bot.owner_id))
    conn.commit()

async def save_member_data(member: discord.Member):
    roles = [r.id for r in member.roles if r.name != "@everyone"]
    c.execute("""INSERT OR REPLACE INTO saved_members (user_id,username,avatar,roles,saved_at,server_id)
                 VALUES (?,?,?,?,?,?)""",
              (member.id, str(member), str(member.avatar.url) if member.avatar else None,
               json.dumps(roles), datetime.now(timezone.utc).isoformat(), member.guild.id))
    conn.commit()

async def restore_member_to_server(member_id: int, target_guild: discord.Guild) -> bool:
    row = c.execute("SELECT roles FROM saved_members WHERE user_id=?", (member_id,)).fetchone()
    if not row: return False
    member = target_guild.get_member(member_id)
    if member:
        roles = [target_guild.get_role(r) for r in json.loads(row["roles"]) if target_guild.get_role(r)]
        if roles: await member.add_roles(*roles, reason="Restored from backup")
        return True
    return False

async def save_all_members(guild: discord.Guild):
    for m in guild.members:
        if not m.bot: await save_member_data(m)

# ==================== VIEW HELPERS ====================

class DeleteStockDropdown(View):
    def __init__(self, stock_files):
        super().__init__(timeout=60)
        options = [discord.SelectOption(label=f[:100], value=f) for f in stock_files[:25]]
        sel = Select(placeholder="Select stock file to delete", options=options)
        sel.callback = self.cb; self.add_item(sel)

    async def cb(self, interaction: discord.Interaction):
        st = self.children[0].values[0]
        fp = get_stock_filename(st)
        if fp.exists(): fp.unlink()
        await interaction.response.send_message(f"✅ Deleted `{st}` stock file.", ephemeral=True)

class RoleSelect(Select):
    def __init__(self, options):
        super().__init__(placeholder="Select a role...", options=options[:25], min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(int(self.values[0]))
        if not role: return
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"Removed **{role.name}**.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"Assigned **{role.name}**.", ephemeral=True)

class RoleView(View):
    def __init__(self, options): super().__init__(timeout=None); self.add_item(RoleSelect(options))

# ==================== VERIFICATION ====================

class VerificationView(View):
    def __init__(self, require_oauth: bool = True):
        super().__init__(timeout=None)
        self.require_oauth = require_oauth

    @discord.ui.button(label="Verify Me", style=discord.ButtonStyle.success, custom_id="xult_verify_button", emoji="✅")
    async def verify_button(self, interaction: discord.Interaction, button: Button):
        await handle_verify(interaction)

async def handle_verify(interaction: discord.Interaction):
    row = c.execute("SELECT role_id,log_channel_id,require_oauth FROM verification WHERE server_id=?",
                    (interaction.guild.id,)).fetchone()
    if not row:
        await interaction.response.send_message("❌ Verification not configured.", ephemeral=True); return
    role = interaction.guild.get_role(row["role_id"])
    if not role:
        await interaction.response.send_message("❌ Verified role not found.", ephemeral=True); return
    if role in interaction.user.roles:
        await interaction.response.send_message("✅ Already verified!", ephemeral=True); return
    if row["require_oauth"]:
        state = f"{interaction.guild.id}:{interaction.user.id}"
        oauth_url = (f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}"
                     f"&redirect_uri={quote(REDIRECT_URI)}&response_type=code"
                     f"&scope=identify+guilds+guilds.join&state={state}")
        v = discord.ui.View(timeout=120)
        v.add_item(discord.ui.Button(label="Verify with Discord", style=discord.ButtonStyle.link, url=oauth_url, emoji="🔗"))
        embed = discord.Embed(title="🔐 Verify Required", description="Click below to verify your Discord account.", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, view=v, ephemeral=True)
        return
    try:
        await interaction.user.add_roles(role, reason="XULT Verification")
        await interaction.response.send_message(f"✅ Verified! You now have **{role.name}**.", ephemeral=True)
        if row["log_channel_id"]:
            ch = interaction.guild.get_channel(row["log_channel_id"])
            if ch:
                e = discord.Embed(title="✅ Member Verified", color=discord.Color.green(), timestamp=datetime.now(timezone.utc))
                e.add_field(name="User", value=f"{interaction.user.mention} (`{interaction.user.id}`)")
                await ch.send(embed=e)
    except discord.Forbidden:
        await interaction.response.send_message("❌ Missing permissions to assign role.", ephemeral=True)

# ==================== EVENTS ====================

@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user} ({bot.user.id})")
    for st in STOCK_TYPES: create_stock_file(st)

    # Register persistent views
    for row in c.execute("SELECT require_oauth FROM verification").fetchall():
        bot.add_view(VerificationView(require_oauth=bool(row["require_oauth"])))
    bot.add_view(TicketPanelView())

    # Clear global commands — everything is per-guild
    bot.tree.clear_commands(guild=None)
    await bot.tree.sync()
    log.info("Cleared all global commands")

    # Sync commands to all guilds
    for guild in bot.guilds:
        try:
            enabled, disabled = await sync_guild_commands(guild)
            log.info(f"  {guild.name}: {enabled} enabled, {disabled} hidden")
        except Exception as e:
            log.error(f"  Failed to sync {guild.name}: {e}")

    # Background tasks
    for task in [daily_coins, random_event_loop, check_youtube, check_twitch,
                 check_twitter_posts, check_unjail, send_daily_messages]:
        if not task.is_running(): task.start()

    bot.loop.create_task(start_api_server())
    log.info("✅ XULT ready")

@bot.event
async def on_guild_join(guild: discord.Guild):
    save_server_backup(guild)
    await save_all_members(guild)
    # Sync all commands to new guild (all enabled by default)
    await sync_guild_commands(guild)
    log.info(f"Joined guild {guild.name} and synced commands")

@bot.event
async def on_member_join(member: discord.Member):
    row = c.execute("SELECT role_id,delay FROM role_on_join WHERE server_id=?", (member.guild.id,)).fetchone()
    if row:
        await asyncio.sleep(row["delay"])
        role = member.guild.get_role(row["role_id"])
        if role:
            try: await member.add_roles(role)
            except: pass
    cfg = get_server_config(member.guild.id)
    if cfg.get("welcome_channel") and cfg.get("welcome_message"):
        ch = member.guild.get_channel(cfg["welcome_channel"])
        if ch:
            msg = cfg["welcome_message"].replace("{user}", member.mention).replace("{server}", member.guild.name)
            await ch.send(msg)
    await save_member_data(member)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        await bot.process_commands(message); return
    c.execute("""INSERT INTO channel_activity (channel_id,server_id,message_count,unique_users,last_message,last_reset)
                 VALUES (?,?,1,1,?,?) ON CONFLICT(channel_id) DO UPDATE SET message_count=message_count+1,last_message=?""",
              (message.channel.id, message.guild.id, datetime.now(timezone.utc).isoformat(),
               datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()))
    conn.commit()
    add_xp(message.author.id, random.randint(1,5))
    add_coins(message.author.id, random.randint(0,2))
    if contains_bad_word(message.content, message.guild.id):
        allowed_chs = [r[0] for r in c.execute("SELECT channel_id FROM allowed_channels WHERE server_id=?", (message.guild.id,)).fetchall()]
        if message.channel.id not in allowed_chs:
            await message.delete()
            c.execute("INSERT INTO warnings (user_id,moderator_id,reason,timestamp,server_id) VALUES (?,?,?,?,?)",
                      (message.author.id, bot.user.id, "Bad language", datetime.now(timezone.utc).isoformat(), message.guild.id))
            conn.commit()
            count = c.execute("SELECT COUNT(*) FROM warnings WHERE user_id=? AND server_id=?", (message.author.id, message.guild.id)).fetchone()[0]
            embed = discord.Embed(title="🚫 Warning!", description=f"{message.author.mention} Watch your language! ({count}/3)", color=discord.Color.red())
            await message.channel.send(embed=embed, delete_after=5)
            if count >= 3:
                try:
                    await message.author.timeout(discord.utils.utcnow()+timedelta(minutes=10), reason="3 warnings")
                    c.execute("DELETE FROM warnings WHERE user_id=? AND server_id=?", (message.author.id, message.guild.id)); conn.commit()
                except: pass
    await bot.process_commands(message)

# ==================== BACKGROUND TASKS ====================

@tasks.loop(hours=24)
async def daily_coins():
    for (uid,) in c.execute("SELECT id FROM users").fetchall():
        add_coins(uid, 50)

@tasks.loop(minutes=60)
async def random_event_loop():
    if not bot.guilds: return
    guild = random.choice(bot.guilds)
    members = [m for m in guild.members if not m.bot]
    if not members: return
    member = random.choice(members)
    reward = random.randint(5,30)
    add_coins(member.id, reward)
    # Find a general channel
    for ch in guild.text_channels:
        if ch.permissions_for(guild.me).send_messages and "general" in ch.name.lower():
            embed = discord.Embed(title="🎉 Random Event!", description=f"{member.mention} got **{reward} coins**!", color=discord.Color.gold())
            await ch.send(embed=embed); break

@tasks.loop(minutes=3)
async def check_youtube():
    rows = c.execute("SELECT server_id,channel_id,last_post_id,role_id FROM tracked_channels WHERE platform='youtube'").fetchall()
    for server_id, channel_id, last_id, role_id in rows:
        guild = bot.get_guild(server_id)
        if not guild: continue
        ch = guild.get_channel(channel_id)
        if not ch: continue
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}") as resp:
                    if resp.status != 200: continue
                    root = ET.fromstring(await resp.text())
            ns = {"yt":"http://www.youtube.com/xml/schemas/2015","atom":"http://www.w3.org/2005/Atom"}
            entry = root.find(".//atom:entry", ns)
            if entry is None: continue
            vid_id = entry.find("yt:videoId", ns)
            if vid_id is None or vid_id.text == last_id: continue
            title = (entry.find("atom:title", ns).text or "New Video")
            c.execute("UPDATE tracked_channels SET last_post_id=? WHERE server_id=? AND platform='youtube' AND channel_id=?",
                      (vid_id.text, server_id, channel_id)); conn.commit()
            embed = discord.Embed(title="🎥 New YouTube Upload!", description=f"**{title}**\n[Watch](https://youtu.be/{vid_id.text})", color=discord.Color.red())
            embed.set_thumbnail(url=f"https://i.ytimg.com/vi/{vid_id.text}/hqdefault.jpg")
            await ch.send(content=f"<@&{role_id}>" if role_id else "", embed=embed)
        except Exception as e:
            log.error(f"YouTube error: {e}")

@tasks.loop(minutes=2)
async def check_twitch():
    if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET: return
    async with aiohttp.ClientSession() as s:
        async with s.post("https://id.twitch.tv/oauth2/token",
                          params={"client_id":TWITCH_CLIENT_ID,"client_secret":TWITCH_CLIENT_SECRET,"grant_type":"client_credentials"}) as r:
            if r.status != 200: return
            oauth = (await r.json()).get("access_token")
            if not oauth: return
    rows = c.execute("SELECT server_id,channel_id,last_post_id,role_id FROM tracked_channels WHERE platform='twitch'").fetchall()
    async with aiohttp.ClientSession() as s:
        for server_id, channel_id, last_id, role_id in rows:
            guild = bot.get_guild(server_id)
            if not guild: continue
            ch = guild.get_channel(channel_id)
            if not ch: continue
            try:
                async with s.get(f"https://api.twitch.tv/helix/streams?user_login={channel_id}",
                                 headers={"Client-ID":TWITCH_CLIENT_ID,"Authorization":f"Bearer {oauth}"}) as r:
                    if r.status != 200: continue
                    data = (await r.json()).get("data",[])
                    if not data: notified_streams.pop(channel_id, None); continue
                    stream = data[0]
                    if notified_streams.get(channel_id) == stream["id"]: continue
                    notified_streams[channel_id] = stream["id"]
                    c.execute("UPDATE tracked_channels SET last_post_id=? WHERE server_id=? AND platform='twitch' AND channel_id=?",
                              (stream["id"], server_id, channel_id)); conn.commit()
                    embed = discord.Embed(title="📡 Live Now!", description=f"[{stream['title']}](https://twitch.tv/{channel_id})", color=discord.Color.purple())
                    embed.add_field(name="Game", value=stream.get("game_name","Unknown"))
                    embed.add_field(name="Viewers", value=stream.get("viewer_count",0))
                    await ch.send(content=f"<@&{role_id}>" if role_id else "", embed=embed)
            except Exception as e:
                log.error(f"Twitch error: {e}")

@tasks.loop(minutes=5)
async def check_twitter_posts():
    if not TWITTER_BEARER_TOKEN: return
    rows = c.execute("SELECT server_id,channel_id,last_post_id,role_id FROM tracked_channels WHERE platform='twitter'").fetchall()
    async with aiohttp.ClientSession() as s:
        for server_id, channel_id, last_id, role_id in rows:
            guild = bot.get_guild(server_id)
            if not guild: continue
            ch = guild.get_channel(channel_id)
            if not ch: continue
            try:
                hdrs = {"Authorization":f"Bearer {TWITTER_BEARER_TOKEN}"}
                async with s.get(f"https://api.twitter.com/2/users/by/username/{quote(channel_id)}", headers=hdrs) as r:
                    if r.status != 200: continue
                    uid = (await r.json()).get("data",{}).get("id")
                    if not uid: continue
                    async with s.get(f"https://api.twitter.com/2/users/{uid}/tweets?max_results=5", headers=hdrs) as r2:
                        if r2.status != 200: continue
                        tweets = (await r2.json()).get("data",[])
                        if not tweets or tweets[0]["id"] == last_id: continue
                        tweet = tweets[0]
                        c.execute("UPDATE tracked_channels SET last_post_id=? WHERE server_id=? AND platform='twitter' AND channel_id=?",
                                  (tweet["id"], server_id, channel_id)); conn.commit()
                        embed = discord.Embed(title=f"📢 New Tweet @{channel_id}", description=tweet.get("text","")[:200], color=discord.Color.blue())
                        await ch.send(content=f"<@&{role_id}>" if role_id else "", embed=embed)
            except Exception as e:
                log.error(f"Twitter error: {e}")
            await asyncio.sleep(2)

@tasks.loop(seconds=30)
async def check_unjail():
    now = datetime.now(timezone.utc)
    for server_id, user_id, _, jail_time_str, duration in c.execute("SELECT server_id,user_id,roles,jail_time,duration FROM jailed_members").fetchall():
        try:
            jail_time = datetime.strptime(jail_time_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            if now >= jail_time + parse_duration(duration):
                guild = bot.get_guild(server_id)
                if guild:
                    member = guild.get_member(user_id)
                    if member: await unjail_member(member)
                else:
                    c.execute("DELETE FROM jailed_members WHERE server_id=? AND user_id=?", (server_id, user_id)); conn.commit()
        except Exception as e:
            log.error(f"Unjail error: {e}")

@tasks.loop(minutes=1)
async def send_daily_messages():
    for server_id, channel_id, role_id, voice_channel_id, tz_str in c.execute("SELECT * FROM four_twenty").fetchall():
        guild = bot.get_guild(server_id)
        if not guild: continue
        try: tz = pytz.timezone(tz_str or "UTC")
        except: tz = pytz.UTC
        now = datetime.now(tz)
        if now.hour in (4, 16) and now.minute == 20:
            ch = guild.get_channel(channel_id)
            if ch:
                vc = guild.get_channel(voice_channel_id) if voice_channel_id else None
                voice_link = f"[Join VC!]({vc.jump_url})" if vc else ""
                embed = discord.Embed(title="It's 4:20! 🌿", description=f"{voice_link}\n{'<@&'+str(role_id)+'>' if role_id else ''}", color=discord.Color.green())
                await ch.send(embed=embed)
                await asyncio.sleep(61)

async def send_auto_update(bot_instance):
    auto_data = load_json(JSON_FILES["auto_update"], {})
    for guild_id, data in auto_data.items():
        ch = bot_instance.get_channel(data.get("channel_id"))
        if not ch: continue
        lines = [f"➜ **{f.stem.capitalize()}**: `{count_stock(f.stem)}`" for f in STOCK_DIR.glob("*.txt")][:20]
        embed = discord.Embed(title="📦 Stock Update", color=discord.Color.green())
        embed.add_field(name="Stock", value="\n".join(lines) if lines else "No stock.", inline=False)
        try:
            role_ping = f"<@&{data['role_id']}> " if data.get("role_id") else ""
            await ch.send(content=f"{role_ping}Stock updated!", embed=embed)
        except: pass

# ==================== SLASH COMMANDS ====================

# ── HELP ──────────────────────────────────────────────────────

@bot.tree.command(name="help", description="Show all commands")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="🤖 XULT Commands", color=discord.Color.red())
    embed.add_field(name="💰 Economy", value="`/balance` `/daily` `/coinflip` `/rps` `/slots` `/blackjack` `/joke` `/eightball` `/riddle`", inline=False)
    embed.add_field(name="📦 Stock", value="`/gen` `/dmgen` `/stocklist` `/addstock` `/deletestock` `/setgenaccess` `/setautoupdate`", inline=False)
    embed.add_field(name="🎫 Tickets", value="`/ticket_panel` `/close_ticket` `/add_ticket_panel`", inline=False)
    embed.add_field(name="📝 Applications", value="`/create_application` `/application_panel` `/review_app` `/list_applications`", inline=False)
    embed.add_field(name="🛡️ Moderation", value="`/jail` `/unjail` `/purge` `/warnings` `/resetwarn` `/setroleonjoin` `/set_logs` `/add_allowed_channel` `/upload_bad_words`", inline=False)
    embed.add_field(name="🔐 Verification", value="`/setup_oauth_verification` `/verify`", inline=False)
    embed.add_field(name="📢 Notifications", value="`/setnotichannel` `/addyoutubechannel` `/addtwitchstream` `/addtwitteraccount`", inline=False)
    embed.add_field(name="⚙️ Management", value="`/reactionrole` `/setreportchannel` `/report` `/setup_logging` `/save_server` `/load_server` `/add_to_channel` `/test`", inline=False)
    embed.add_field(name="🎮 Command Control", value="`/togglecommand` `/commandroles` `/commandchannels` `/listcommands` `/sync_commands`", inline=False)
    embed.add_field(name="🎨 Fun", value="`/gif` `/meme` `/hug` `/slap` `/say`", inline=False)
    embed.set_footer(text="Disabled commands are hidden per-server | Use /sync_commands to apply changes")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ── COMMAND CONTROL ───────────────────────────────────────────

@bot.tree.command(name="sync_commands", description="Apply command enable/disable changes to this server")
@app_commands.default_permissions(administrator=True)
async def sync_commands(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    now = datetime.now()
    cd = command_sync_cooldown.get(interaction.guild.id)
    if cd and now - cd < timedelta(seconds=30):
        remaining = 30 - (now - cd).seconds
        await interaction.response.send_message(f"⏰ Wait {remaining}s.", ephemeral=True); return
    await interaction.response.defer(ephemeral=True)
    command_sync_cooldown[interaction.guild.id] = now
    enabled_count, disabled_count = await sync_guild_commands(interaction.guild)
    embed = discord.Embed(title="✅ Commands Synced", color=discord.Color.green())
    embed.description = (f"**{enabled_count}** commands are now visible in this server.\n"
                         f"**{disabled_count}** commands are hidden (disabled).")
    embed.set_footer(text="Changes take effect immediately in Discord")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="sync_all_commands", description="Enable all commands in this server (Admin)")
@app_commands.default_permissions(administrator=True)
async def sync_all_commands(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    await interaction.response.defer(ephemeral=True)
    # Enable all commands in DB for this guild
    for cmd_name in ALL_COMMANDS:
        update_command_setting(interaction.guild.id, cmd_name, True)
    enabled_count, _ = await sync_guild_commands(interaction.guild)
    await interaction.followup.send(f"✅ All {enabled_count} commands enabled and synced.")

@bot.tree.command(name="togglecommand", description="Enable or disable a command on your server")
@app_commands.describe(command="Command name (without /)", enabled="True to enable, False to disable")
@app_commands.default_permissions(administrator=True)
async def toggle_command(interaction: discord.Interaction, command: str, enabled: bool):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    command = command.lower().lstrip("/")
    if command not in ALL_COMMANDS:
        await interaction.response.send_message(f"❌ Unknown command `/{command}`.", ephemeral=True); return
    await interaction.response.defer(ephemeral=True)
    update_command_setting(interaction.guild.id, command, enabled)
    # Auto-sync so change takes effect immediately
    await sync_guild_commands(interaction.guild)
    status = "✅ Enabled" if enabled else "🚫 Hidden"
    await interaction.followup.send(f"{status}: `/{command}` — change is now live in Discord.")

@bot.tree.command(name="commandroles", description="Restrict a command to specific roles")
@app_commands.describe(command="Command name", roles="Comma-separated role IDs (blank = all)")
@app_commands.default_permissions(administrator=True)
async def command_roles(interaction: discord.Interaction, command: str, roles: str = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    command = command.lower().lstrip("/")
    role_ids = [int(r.strip()) for r in roles.split(',') if r.strip().isdigit()] if roles else []
    update_command_setting(interaction.guild.id, command, True, role_ids)
    msg = f"✅ `/{command}` restricted to {len(role_ids)} role(s)." if role_ids else f"✅ Role restrictions removed from `/{command}`."
    await interaction.response.send_message(msg, ephemeral=True)

@bot.tree.command(name="commandchannels", description="Disable a command in specific channels")
@app_commands.describe(command="Command name", channels="Comma-separated channel IDs (blank = all)")
@app_commands.default_permissions(administrator=True)
async def command_channels(interaction: discord.Interaction, command: str, channels: str = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    command = command.lower().lstrip("/")
    ch_ids = [int(ch.strip()) for ch in channels.split(',') if ch.strip().isdigit()] if channels else []
    update_command_setting(interaction.guild.id, command, True, None, ch_ids)
    msg = f"✅ `/{command}` disabled in {len(ch_ids)} channel(s)." if ch_ids else f"✅ Channel restrictions removed from `/{command}`."
    await interaction.response.send_message(msg, ephemeral=True)

@bot.tree.command(name="listcommands", description="List all commands and their status")
@app_commands.default_permissions(administrator=True)
async def list_commands(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    enabled_cmds = [c for c in ALL_COMMANDS if is_command_enabled(interaction.guild.id, c)]
    disabled_cmds = [c for c in ALL_COMMANDS if not is_command_enabled(interaction.guild.id, c)]
    embed = discord.Embed(title="📋 Command Status", color=discord.Color.blue(),
                         description=f"**{len(enabled_cmds)}** visible · **{len(disabled_cmds)}** hidden")
    for cat, cmds in CMD_CATEGORIES.items():
        enabled_in_cat = [c for c in cmds if is_command_enabled(interaction.guild.id, c)]
        all_in_cat = cmds
        parts = []
        for c_name in all_in_cat:
            parts.append(f"{'✅' if c_name in enabled_in_cat else '❌'} `/{c_name}`")
        if parts:
            embed.add_field(name=cat.capitalize(), value=" ".join(parts), inline=False)
    embed.set_footer(text="Use /sync_commands after /togglecommand to apply")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ── ECONOMY ───────────────────────────────────────────────────

@bot.tree.command(name="balance", description="Check your coins, XP, and level")
async def balance(interaction: discord.Interaction):
    coins = get_balance(interaction.user.id)
    c.execute("UPDATE users SET username=? WHERE id=?", (str(interaction.user), interaction.user.id)); conn.commit()
    embed = discord.Embed(title=f"{interaction.user.display_name}'s Balance", color=discord.Color.gold())
    embed.add_field(name="Coins", value=f"{coins:,}", inline=True)
    embed.add_field(name="XP", value=f"{get_xp(interaction.user.id):,}", inline=True)
    embed.add_field(name="Level", value=get_level(interaction.user.id), inline=True)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="daily", description="Claim daily coins (24h cooldown)")
async def daily(interaction: discord.Interaction):
    row = c.execute("SELECT last_daily FROM users WHERE id=?", (interaction.user.id,)).fetchone()
    if row and row[0]:
        last = datetime.fromisoformat(row[0])
        if datetime.now(timezone.utc) - last < timedelta(hours=24):
            remaining = timedelta(hours=24) - (datetime.now(timezone.utc) - last)
            h, m = divmod(int(remaining.total_seconds())//60, 60)
            await interaction.response.send_message(f"⏳ Daily available in **{h}h {m}m**.", ephemeral=True); return
    reward = random.randint(50, 200)
    add_coins(interaction.user.id, reward)
    c.execute("UPDATE users SET last_daily=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), interaction.user.id)); conn.commit()
    await interaction.response.send_message(embed=discord.Embed(title="📅 Daily Reward", description=f"Claimed **{reward} coins**!", color=discord.Color.gold()))

@bot.tree.command(name="coinflip", description="Flip a coin")
@app_commands.choices(guess=[app_commands.Choice(name="Heads",value="heads"),app_commands.Choice(name="Tails",value="tails")])
async def coinflip(interaction: discord.Interaction, guess: app_commands.Choice[str]):
    result = random.choice(["heads","tails"])
    if guess.value == result:
        add_coins(interaction.user.id, 10)
        embed = discord.Embed(title="🎉 Correct!", description=f"It was **{result}**! +10 coins", color=discord.Color.green())
    else:
        embed = discord.Embed(title="❌ Wrong!", description=f"It was **{result}**", color=discord.Color.red())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rps", description="Rock Paper Scissors")
@app_commands.choices(choice=[app_commands.Choice(name="Rock",value="rock"),app_commands.Choice(name="Paper",value="paper"),app_commands.Choice(name="Scissors",value="scissors")])
async def rps(interaction: discord.Interaction, choice: app_commands.Choice[str]):
    bot_choice = random.choice(["rock","paper","scissors"])
    wins = {"rock":"scissors","scissors":"paper","paper":"rock"}
    if choice.value == bot_choice:
        embed = discord.Embed(title="🤝 Tie!", description=f"Both chose {choice.name}", color=discord.Color.blue())
    elif wins[choice.value] == bot_choice:
        add_coins(interaction.user.id, 10)
        embed = discord.Embed(title="🎉 You win! +10 coins", description=f"{choice.name} beats {bot_choice}", color=discord.Color.green())
    else:
        embed = discord.Embed(title="😢 You lose!", description=f"{bot_choice} beats {choice.name}", color=discord.Color.red())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="slots", description="Slot machine (costs 20 coins)")
async def slots(interaction: discord.Interaction):
    if get_balance(interaction.user.id) < 20:
        await interaction.response.send_message("❌ Need 20 coins!", ephemeral=True); return
    remove_coins(interaction.user.id, 20)
    icons = ["🍒","🍋","🔔","⭐","💎","7️⃣"]
    reels = [random.choice(icons) for _ in range(3)]
    if len(set(reels)) == 1:
        add_coins(interaction.user.id, 500); msg = "JACKPOT! +500 coins!"
    elif len(set(reels)) == 2:
        add_coins(interaction.user.id, 50); msg = "Two in a row! +50 coins!"
    else:
        msg = "No match. Try again!"
    embed = discord.Embed(title="🎰 Slots", description=f"| {' | '.join(reels)} |\n\n{msg}", color=discord.Color.gold())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="blackjack", description="Play blackjack")
@app_commands.describe(bet="Amount to bet")
async def blackjack(interaction: discord.Interaction, bet: int):
    if bet <= 0 or get_balance(interaction.user.id) < bet:
        await interaction.response.send_message("❌ Invalid bet or insufficient coins.", ephemeral=True); return
    deck = [2,3,4,5,6,7,8,9,10,10,10,10,11]*4; random.shuffle(deck)
    player = [deck.pop(), deck.pop()]; dealer = [deck.pop(), deck.pop()]
    def hand_val(hand):
        v = sum(hand); aces = hand.count(11)
        while v > 21 and aces: v -= 10; aces -= 1
        return v
    pv, dv = hand_val(player), hand_val(dealer)
    while dv < 17: dealer.append(deck.pop()); dv = hand_val(dealer)
    if pv > 21: remove_coins(interaction.user.id, bet); result = f"❌ Bust! Lost **{bet}** coins."
    elif dv > 21 or pv > dv: add_coins(interaction.user.id, bet); result = f"🎉 You win! +**{bet}** coins."
    elif pv == dv: result = "🤝 Push — coins returned."
    else: remove_coins(interaction.user.id, bet); result = f"😢 Dealer wins. Lost **{bet}** coins."
    embed = discord.Embed(title="🃏 Blackjack", color=discord.Color.green())
    embed.add_field(name="Your hand", value=f"{player} = **{pv}**")
    embed.add_field(name="Dealer", value=f"{dealer} = **{dv}**")
    embed.add_field(name="Result", value=result, inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="joke", description="Random joke")
async def joke(interaction: discord.Interaction):
    async with aiohttp.ClientSession() as s:
        async with s.get("https://official-joke-api.appspot.com/jokes/random") as r:
            data = await r.json()
            await interaction.response.send_message(embed=discord.Embed(description=f"**{data['setup']}**\n\n{data['punchline']}", color=discord.Color.orange()))

@bot.tree.command(name="eightball", description="Magic 8-ball")
@app_commands.describe(question="Your question")
async def eightball(interaction: discord.Interaction, question: str):
    resp = random.choice(["Yes","No","Maybe","Definitely","Absolutely not","Ask again later","It is certain","Very doubtful"])
    await interaction.response.send_message(embed=discord.Embed(title=f"🎱 {question[:100]}", description=resp, color=discord.Color.dark_blue()))

@bot.tree.command(name="riddle", description="Solve a riddle for coins")
async def riddle(interaction: discord.Interaction):
    global active_riddle, riddle_answer
    if active_riddle:
        await interaction.response.send_message("A riddle is already active!", ephemeral=True); return
    active_riddle, riddle_answer = random.choice(RIDDLES)
    await interaction.response.send_message(f"🧩 {active_riddle}")
    def check(m): return m.content.lower() == riddle_answer.lower() and m.author == interaction.user
    try:
        msg = await bot.wait_for("message", timeout=30.0, check=check)
        add_coins(msg.author.id, 50)
        await interaction.channel.send(f"✅ Correct, {msg.author.mention}! +50 coins!")
    except asyncio.TimeoutError:
        await interaction.channel.send(f"⏰ Time's up! Answer was: **{riddle_answer}**")
    active_riddle = riddle_answer = None

# ── STOCK / GEN ───────────────────────────────────────────────

@bot.tree.command(name="stocklist", description="List available stock types")
async def stocklist(interaction: discord.Interaction):
    embed = discord.Embed(title="📦 Available Stock", color=discord.Color.blue())
    total = 0
    for file in list(STOCK_DIR.glob("*.txt"))[:20]:
        count = count_stock(file.stem)
        info = STOCK_TYPES.get(file.stem, {"name":file.stem.capitalize(),"emoji":"📄"})
        embed.add_field(name=f"{info['emoji']} {info['name']}", value=f"`{count}` available", inline=True)
        total += count
    embed.set_footer(text=f"Total: {total} entries")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="addstock", description="Add stock entries from a text file (Admin only)")
@app_commands.describe(stock_type="Type of stock", file="Text file with entries")
@app_commands.default_permissions(administrator=True)
async def addstock(interaction: discord.Interaction, stock_type: str, file: discord.Attachment = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    if not file or not file.filename.endswith(".txt"):
        await interaction.response.send_message("Upload a .txt file.", ephemeral=True); return
    content = (await file.read()).decode("utf-8").strip()
    if not content:
        await interaction.response.send_message("File is empty.", ephemeral=True); return
    fp = get_stock_filename(stock_type)
    with open(fp, "a", encoding="utf-8") as f:
        f.write(("\n\n" if fp.exists() and fp.stat().st_size > 0 else "") + content)
    count = count_stock(stock_type)
    await interaction.response.send_message(f"✅ Added stock to `{stock_type}`. Now **{count}** entries.", ephemeral=True)
    log_action(interaction.user.id, "ADD_STOCK", f"type={stock_type}")

@bot.tree.command(name="deletestock", description="Delete a stock file (Admin only)")
@app_commands.default_permissions(administrator=True)
async def deletestock(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    files = [f.stem for f in STOCK_DIR.glob("*.txt")][:25]
    if not files:
        await interaction.response.send_message("No stock files.", ephemeral=True); return
    await interaction.response.send_message("Select a file to delete:", view=DeleteStockDropdown(files), ephemeral=True)

@bot.tree.command(name="gen", description="Generate a stock entry")
@app_commands.describe(stock_type="Type of stock to generate")
async def gen(interaction: discord.Interaction, stock_type: str):
    is_prem = await check_user_premium(interaction.user.id)
    gen_access = load_json(JSON_FILES["gen_access"], {})
    if str(interaction.guild.id) in gen_access:
        allowed = gen_access[str(interaction.guild.id)]
        if allowed and not any(r.id in allowed for r in interaction.user.roles):
            await interaction.response.send_message("❌ You don't have permission to use /gen.", ephemeral=True); return
    await interaction.response.defer()
    cd, remaining = is_on_cooldown(interaction.user.id, is_prem)
    if cd:
        await interaction.followup.send(f"⏳ Wait **{remaining}s**.", ephemeral=True); return
    stock = get_stock_entry(stock_type)
    if not stock:
        await interaction.followup.send(f"❌ No `{stock_type}` stock available.", ephemeral=True); return
    if not is_prem: set_cooldown(interaction.user.id)
    try:
        await interaction.user.send(f"```\n{stock}\n```")
        await interaction.followup.send("📩 Sent to your DMs!", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send(f"```\n{stock}\n```", ephemeral=True)
    await send_auto_update(bot)
    c.execute("""INSERT INTO stock_usage (user_id,username,stock_type,stock_content,generated_at,server_id,server_name,channel_id,channel_name,is_dm)
                 VALUES (?,?,?,?,?,?,?,?,?,0)""",
              (interaction.user.id, str(interaction.user), stock_type, stock, datetime.now(timezone.utc).isoformat(),
               interaction.guild.id, interaction.guild.name, interaction.channel.id, interaction.channel.name))
    conn.commit(); log_action(interaction.user.id, "GEN", f"type={stock_type}")

@bot.tree.command(name="dmgen", description="Generate stock via DM only")
@app_commands.describe(stock_type="Type of stock")
async def dmgen(interaction: discord.Interaction, stock_type: str):
    await interaction.response.defer(ephemeral=True)
    is_prem = await check_user_premium(interaction.user.id)
    cd, remaining = is_on_cooldown(interaction.user.id, is_prem)
    if cd:
        await interaction.followup.send(f"⏳ Wait **{remaining}s**.", ephemeral=True); return
    stock = get_stock_entry(stock_type)
    if not stock:
        await interaction.followup.send(f"❌ No `{stock_type}` stock.", ephemeral=True); return
    if not is_prem: set_cooldown(interaction.user.id)
    await interaction.followup.send(f"```\n{stock}\n```", ephemeral=True)

@bot.tree.command(name="setgenaccess", description="Set which roles can use /gen (Admin only)")
@app_commands.describe(role="Role to allow")
@app_commands.default_permissions(administrator=True)
async def setgenaccess(interaction: discord.Interaction, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    data = load_json(JSON_FILES["gen_access"], {})
    gid = str(interaction.guild.id)
    if gid not in data: data[gid] = []
    if role.id not in data[gid]: data[gid].append(role.id)
    save_json(JSON_FILES["gen_access"], data)
    await interaction.response.send_message(f"✅ {role.mention} can now use `/gen`.")

@bot.tree.command(name="setautoupdate", description="Set auto-update stock channel (Admin only)")
@app_commands.describe(channel="Channel for updates", role="Role to ping")
@app_commands.default_permissions(administrator=True)
async def setautoupdate(interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    data = load_json(JSON_FILES["auto_update"], {})
    data[str(interaction.guild.id)] = {"channel_id":channel.id,"role_id":role.id if role else None}
    save_json(JSON_FILES["auto_update"], data)
    await interaction.response.send_message(f"✅ Auto-update → {channel.mention}" + (f" pinging {role.mention}" if role else ""))

# ── MODERATION ────────────────────────────────────────────────

@bot.tree.command(name="jail", description="Jail a member")
@app_commands.describe(member="Member to jail", duration="e.g. 10m, 2h, 1d", reason="Reason")
@app_commands.default_permissions(administrator=True)
async def jail_cmd(interaction: discord.Interaction, member: discord.Member, duration: str = "10m", reason: str = "No reason"):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    await interaction.response.defer()
    try:
        await jail_member(member, duration, reason, interaction.user)
        await interaction.followup.send(f"🔒 {member.mention} jailed for **{duration}**. Reason: {reason}")
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="unjail", description="Unjail a member")
@app_commands.describe(member="Member to unjail")
@app_commands.default_permissions(administrator=True)
async def unjail_cmd(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    await interaction.response.defer()
    if await unjail_member(member):
        await interaction.followup.send(f"✅ {member.mention} unjailed.")
    else:
        await interaction.followup.send(f"{member.mention} is not jailed.")

@bot.tree.command(name="purge", description="Delete messages")
@app_commands.describe(amount="Number of messages (1-100)")
@app_commands.default_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, amount: int = 10):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ Missing permissions.", ephemeral=True); return
    if not 1 <= amount <= 100:
        await interaction.response.send_message("Amount must be 1-100.", ephemeral=True); return
    await interaction.response.send_message(f"⏳ Purging...", ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"✅ Deleted {len(deleted)} messages.", ephemeral=True)

@bot.tree.command(name="warnings", description="View user warnings")
@app_commands.describe(user="User to check")
async def warnings(interaction: discord.Interaction, user: discord.Member):
    rows = c.execute("SELECT reason,timestamp,moderator_id FROM warnings WHERE user_id=? AND server_id=? ORDER BY timestamp DESC",
                     (user.id, interaction.guild.id)).fetchall()
    embed = discord.Embed(title=f"⚠️ Warnings: {user.display_name}", color=discord.Color.orange())
    if not rows:
        embed.description = "No warnings."
    else:
        embed.description = f"**{len(rows)} warning(s)**"
        for i, (reason, ts, mod_id) in enumerate(rows[:10], 1):
            mod = interaction.guild.get_member(mod_id)
            embed.add_field(name=f"#{i}", value=f"**Reason:** {reason}\n**By:** {mod.mention if mod else mod_id}\n**Date:** {ts[:10]}", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="resetwarn", description="Reset user warnings (Admin only)")
@app_commands.describe(user="User to reset", reason="Reason")
@app_commands.default_permissions(administrator=True)
async def resetwarn(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason"):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    c.execute("DELETE FROM warnings WHERE user_id=? AND server_id=?", (user.id, interaction.guild.id)); conn.commit()
    try: await user.send(f"✅ Warnings in **{interaction.guild.name}** reset. Reason: {reason}")
    except: pass
    await interaction.response.send_message(f"✅ Reset warnings for {user.mention}.")

@bot.tree.command(name="setroleonjoin", description="Auto-assign role to new members (Admin)")
@app_commands.describe(role="Role to assign", delay="Delay e.g. 10m (default 0s)")
@app_commands.default_permissions(administrator=True)
async def setroleonjoin(interaction: discord.Interaction, role: discord.Role, delay: str = "0s"):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    try: secs = int(parse_duration(delay).total_seconds())
    except: await interaction.response.send_message("Invalid delay format.", ephemeral=True); return
    c.execute("INSERT OR REPLACE INTO role_on_join VALUES (?,?,?)", (interaction.guild.id, role.id, secs)); conn.commit()
    await interaction.response.send_message(f"✅ New members get {role.mention} after {delay}.")

@bot.tree.command(name="set_logs", description="Set log channel (Admin)")
@app_commands.describe(channel="Log channel")
@app_commands.default_permissions(administrator=True)
async def set_logs(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    c.execute("INSERT OR REPLACE INTO server_configs (server_id,log_channel) VALUES (?,?)", (interaction.guild.id, channel.id)); conn.commit()
    await interaction.response.send_message(f"✅ Log channel → {channel.mention}")

@bot.tree.command(name="add_allowed_channel", description="Allow channel to bypass bad word filter (Admin)")
@app_commands.describe(channel="Channel to allow")
@app_commands.default_permissions(administrator=True)
async def add_allowed_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    c.execute("INSERT OR IGNORE INTO allowed_channels VALUES (?,?)", (interaction.guild.id, channel.id)); conn.commit()
    await interaction.response.send_message(f"✅ {channel.mention} bypasses word filter.")

@bot.tree.command(name="upload_bad_words", description="Upload bad words list from .txt file (Admin)")
@app_commands.describe(file="Text file with one word per line")
@app_commands.default_permissions(administrator=True)
async def upload_bad_words(interaction: discord.Interaction, file: discord.Attachment):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    if not file.filename.endswith(".txt"):
        await interaction.response.send_message("Upload a .txt file.", ephemeral=True); return
    words = [(interaction.guild.id, w.strip().lower()) for w in (await file.read()).decode("utf-8","ignore").splitlines() if w.strip()][:100]
    for w in words: c.execute("INSERT OR IGNORE INTO bad_words VALUES (?,?)", w)
    conn.commit()
    await interaction.response.send_message(f"✅ Added {len(words)} bad words.")

@bot.tree.command(name="sendnotice", description="Send a notification")
@app_commands.describe(message="Message text", channel="Channel", user="User DM", title="Title", ping_role="Role to ping")
async def sendnotice(interaction: discord.Interaction, message: str, channel: discord.TextChannel = None,
                     user: discord.User = None, title: str = "Notification", ping_role: discord.Role = None):
    embed = discord.Embed(title=title, description=message, color=discord.Color.red())
    embed.set_footer(text=f"Sent by {interaction.user.display_name}")
    if user:
        try: await user.send(embed=embed); await interaction.response.send_message("✅ DM sent.", ephemeral=True)
        except: await interaction.response.send_message("❌ Can't DM user.", ephemeral=True)
    elif channel:
        await channel.send(f"<@&{ping_role.id}> " if ping_role else "", embed=embed)
        await interaction.response.send_message(f"✅ Sent to {channel.mention}.", ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed)

# ── NOTIFICATIONS ─────────────────────────────────────────────

@bot.tree.command(name="setnotichannel", description="Set media notification channel (Admin)")
@app_commands.describe(channel="Notification channel", role="Role to ping")
@app_commands.default_permissions(administrator=True)
async def setnotichannel(interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    data = load_json(JSON_FILES["server_settings"], {})
    data[str(interaction.guild.id)] = {"notification_channel_id":channel.id,"notification_role_id":role.id if role else None}
    save_json(JSON_FILES["server_settings"], data)
    await interaction.response.send_message(f"✅ Notification channel → {channel.mention}")

@bot.tree.command(name="addyoutubechannel", description="Track a YouTube channel (Admin)")
@app_commands.describe(channel_id="YouTube channel ID (UCxxxxxx)", notify_channel="Channel to post in", role="Role to ping")
@app_commands.default_permissions(administrator=True)
async def addyoutubechannel(interaction: discord.Interaction, channel_id: str, notify_channel: discord.TextChannel, role: discord.Role = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    c.execute("INSERT OR IGNORE INTO tracked_channels (server_id,platform,channel_id,last_post_id,role_id,notify_channel) VALUES (?,?,?,?,?,?)",
              (interaction.guild.id,'youtube',channel_id,None,role.id if role else None,notify_channel.id)); conn.commit()
    await interaction.response.send_message(f"✅ Tracking YouTube: `{channel_id}` → {notify_channel.mention}")

@bot.tree.command(name="addtwitchstream", description="Track a Twitch stream (Admin)")
@app_commands.describe(channel_name="Twitch username", notify_channel="Channel to post in", role="Role to ping")
@app_commands.default_permissions(administrator=True)
async def addtwitchstream(interaction: discord.Interaction, channel_name: str, notify_channel: discord.TextChannel, role: discord.Role = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    c.execute("INSERT OR IGNORE INTO tracked_channels (server_id,platform,channel_id,last_post_id,role_id,notify_channel) VALUES (?,?,?,?,?,?)",
              (interaction.guild.id,'twitch',channel_name.lower(),None,role.id if role else None,notify_channel.id)); conn.commit()
    await interaction.response.send_message(f"✅ Tracking Twitch: `{channel_name}` → {notify_channel.mention}")

@bot.tree.command(name="addtwitteraccount", description="Track a Twitter/X account (Admin)")
@app_commands.describe(username="Username (without @)", notify_channel="Channel to post in", role="Role to ping")
@app_commands.default_permissions(administrator=True)
async def addtwitteraccount(interaction: discord.Interaction, username: str, notify_channel: discord.TextChannel, role: discord.Role = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    c.execute("INSERT OR IGNORE INTO tracked_channels (server_id,platform,channel_id,last_post_id,role_id,notify_channel) VALUES (?,?,?,?,?,?)",
              (interaction.guild.id,'twitter',username.lower().lstrip('@'),None,role.id if role else None,notify_channel.id)); conn.commit()
    await interaction.response.send_message(f"✅ Tracking Twitter: `@{username}` → {notify_channel.mention}")

# ── SERVER MANAGEMENT ─────────────────────────────────────────

@bot.tree.command(name="reactionrole", description="Create a reaction role dropdown (Admin)")
@app_commands.describe(roles="Comma-separated role names")
@app_commands.default_permissions(administrator=True)
async def reactionrole(interaction: discord.Interaction, roles: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    role_names = [r.strip() for r in roles.split(",")]
    found = [r for r in interaction.guild.roles if r.name in role_names][:25]
    if not found:
        await interaction.response.send_message("No matching roles.", ephemeral=True); return
    options = [discord.SelectOption(label=r.name, value=str(r.id)) for r in found]
    embed = discord.Embed(title="🎭 Role Selection", description="Pick a role from the dropdown.", color=discord.Color.blue())
    await interaction.response.send_message(embed=embed, view=RoleView(options))

@bot.tree.command(name="setreportchannel", description="Set report channel (Admin)")
@app_commands.describe(channel="Reports channel", role="Role to ping")
@app_commands.default_permissions(administrator=True)
async def setreportchannel(interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    c.execute("INSERT OR REPLACE INTO report_channels VALUES (?,?,?)", (interaction.guild.id, channel.id, role.id)); conn.commit()
    await interaction.response.send_message(f"✅ Reports → {channel.mention} | Ping: {role.mention}")

@bot.tree.command(name="report", description="Report something to moderators")
@app_commands.describe(issue="What happened", user="User to report", evidence="Evidence text")
async def report(interaction: discord.Interaction, issue: str, user: discord.User = None, evidence: str = None):
    row = c.execute("SELECT channel_id,role_id FROM report_channels WHERE server_id=?", (interaction.guild.id,)).fetchone()
    if not row:
        await interaction.response.send_message("Report channel not set up.", ephemeral=True); return
    ch = bot.get_channel(row[0])
    if not ch:
        await interaction.response.send_message("Report channel not found.", ephemeral=True); return
    embed = discord.Embed(title="🚨 New Report", color=discord.Color.red(), timestamp=discord.utils.utcnow())
    embed.add_field(name="Reported By", value=interaction.user.mention, inline=False)
    embed.add_field(name="Issue", value=issue, inline=False)
    if user: embed.add_field(name="Reported User", value=user.mention)
    if evidence: embed.add_field(name="Evidence", value=evidence, inline=False)
    await ch.send(f"<@&{row[1]}>", embed=embed)
    c.execute("INSERT INTO reports (server_id,reporter_id,reported_id,reason,evidence,timestamp) VALUES (?,?,?,?,?,?)",
              (interaction.guild.id, interaction.user.id, user.id if user else None, issue, evidence, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    await interaction.response.send_message("✅ Report submitted.", ephemeral=True)

@bot.tree.command(name="setup_logging", description="Configure all log channels (Admin)")
@app_commands.describe(mod_log="Mod log", member_log="Member log", message_log="Message log",
                       ticket_log="Ticket log", app_log="Application log", bot_update_log="Bot update log")
@app_commands.default_permissions(administrator=True)
async def setup_logging(interaction: discord.Interaction, mod_log: discord.TextChannel = None,
                        member_log: discord.TextChannel = None, message_log: discord.TextChannel = None,
                        ticket_log: discord.TextChannel = None, app_log: discord.TextChannel = None,
                        bot_update_log: discord.TextChannel = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    updates = []
    for log_type, ch in [("mod_log",mod_log),("member_log",member_log),("message_log",message_log),
                          ("ticket_log",ticket_log),("app_log",app_log),("bot_update_log",bot_update_log)]:
        if ch:
            update_logging_config(interaction.guild.id, log_type, ch.id)
            updates.append(f"**{log_type}** → {ch.mention}")
    if updates:
        embed = discord.Embed(title="✅ Logging Configured", description="\n".join(updates), color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message("No channels specified.", ephemeral=True)

@bot.tree.command(name="save_server", description="Save server backup (Admin)")
@app_commands.default_permissions(administrator=True)
async def save_server(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    save_server_backup(interaction.guild)
    await save_all_members(interaction.guild)
    await interaction.response.send_message("✅ Server backup saved.", ephemeral=True)

@bot.tree.command(name="load_server", description="Restore server from backup (Admin)")
@app_commands.default_permissions(administrator=True)
async def load_server(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    await interaction.response.defer(ephemeral=True)
    path = BACKUP_DIR / f"{interaction.guild.id}.json"
    if not path.exists():
        await interaction.followup.send("No backup found.", ephemeral=True); return
    backup = load_json(path)
    # Restore roles and channels from backup
    for r in sorted(backup.get("roles",[]), key=lambda x: x["position"]):
        try:
            await interaction.guild.create_role(name=r["name"],permissions=discord.Permissions(r["permissions"]),
                colour=discord.Colour(r["color"]),hoist=r["hoist"],mentionable=r["mentionable"],reason="Restore")
            await asyncio.sleep(0.5)
        except: pass
    await interaction.followup.send("✅ Restore complete.", ephemeral=True)

# ── 4:20 ──────────────────────────────────────────────────────

@bot.tree.command(name="add_to_channel", description="Configure 4:20 messages (Admin)")
@app_commands.describe(daily_channel="Channel", timezone="Timezone e.g. America/New_York", role="Role to ping")
@app_commands.default_permissions(administrator=True)
async def add_to_channel(interaction: discord.Interaction, daily_channel: discord.TextChannel,
                         timezone: str = "UTC", role: discord.Role = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    try: tz = pytz.timezone(timezone)
    except: await interaction.response.send_message(f"Invalid timezone: {timezone}", ephemeral=True); return
    c.execute("INSERT OR REPLACE INTO four_twenty VALUES (?,?,?,?,?)",
              (interaction.guild.id, daily_channel.id, role.id if role else None, None, tz.zone)); conn.commit()
    await interaction.response.send_message(f"✅ 4:20 → {daily_channel.mention} (TZ: {tz.zone})")

@bot.tree.command(name="test", description="Send a test 4:20 message")
async def test(interaction: discord.Interaction):
    row = c.execute("SELECT channel_id,role_id FROM four_twenty WHERE server_id=?", (interaction.guild.id,)).fetchone()
    if not row:
        await interaction.response.send_message("No 4:20 config.", ephemeral=True); return
    ch = interaction.guild.get_channel(row[0])
    if not ch:
        await interaction.response.send_message("Channel not found.", ephemeral=True); return
    embed = discord.Embed(title="It's 4:20! 🌿 (TEST)", color=discord.Color.green())
    await ch.send(f"<@&{row[1]}> " if row[1] else "", embed=embed)
    await interaction.response.send_message("✅ Test sent!", ephemeral=True)

# ── VERIFICATION ──────────────────────────────────────────────

@bot.tree.command(name="setup_oauth_verification", description="Set up verification panel (Admin)")
@app_commands.describe(channel="Channel for verify button", role="Role to grant", log_channel="Log channel", require_oauth="Require Discord OAuth?")
@app_commands.default_permissions(administrator=True)
async def setup_oauth_verification(interaction: discord.Interaction, channel: discord.TextChannel,
                                   role: discord.Role, log_channel: discord.TextChannel = None, require_oauth: bool = True):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    c.execute("INSERT OR REPLACE INTO verification (server_id,channel_id,role_id,log_channel_id,require_oauth) VALUES (?,?,?,?,?)",
              (interaction.guild.id, channel.id, role.id, log_channel.id if log_channel else None, 1 if require_oauth else 0)); conn.commit()
    embed = discord.Embed(title="🔐 Verification Required",
                          description="Click **Verify Me** to access the server.\nThis only takes a few seconds.",
                          color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
    view = VerificationView(require_oauth=require_oauth)
    msg = await channel.send(embed=embed, view=view)
    bot.add_view(view)
    c.execute("UPDATE verification SET message_id=? WHERE server_id=?", (msg.id, interaction.guild.id)); conn.commit()
    await interaction.response.send_message(f"✅ Verification panel created in {channel.mention}.", ephemeral=True)

@bot.tree.command(name="verify", description="Verify your account")
async def verify(interaction: discord.Interaction):
    await handle_verify(interaction)

# ── TICKETS ───────────────────────────────────────────────────

@bot.tree.command(name="ticket_panel", description="Create a ticket panel (Admin)")
@app_commands.default_permissions(administrator=True)
async def ticket_panel(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    embed = discord.Embed(title="🎫 Support Tickets",
                          description="Need help? Click **Create Ticket** to open a support ticket.\nOur team will assist you as soon as possible.",
                          color=discord.Color.blue())
    await interaction.response.send_message(embed=embed, view=TicketPanelView())

@bot.tree.command(name="add_ticket_panel", description="Add ticket panel to a channel (Admin)")
@app_commands.describe(channel="Channel")
@app_commands.default_permissions(administrator=True)
async def add_ticket_panel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    embed = discord.Embed(title="🎫 Support Tickets", description="Click **Create Ticket** for help!", color=discord.Color.blue())
    await channel.send(embed=embed, view=TicketPanelView())
    await interaction.response.send_message(f"✅ Ticket panel added to {channel.mention}.", ephemeral=True)

@bot.tree.command(name="close_ticket", description="Close the current ticket")
async def close_ticket(interaction: discord.Interaction):
    ticket = c.execute("SELECT ticket_id,status FROM tickets WHERE channel_id=?", (interaction.channel.id,)).fetchone()
    if not ticket:
        await interaction.response.send_message("❌ Not a ticket channel.", ephemeral=True); return
    if ticket["status"] != "open":
        await interaction.response.send_message("❌ Ticket already closed.", ephemeral=True); return
    c.execute("UPDATE tickets SET status='closed',closed_at=?,closed_by=? WHERE ticket_id=?",
              (datetime.now(timezone.utc).isoformat(), interaction.user.id, ticket["ticket_id"])); conn.commit()
    embed = discord.Embed(title="🔒 Ticket Closed", color=discord.Color.red())
    embed.add_field(name="Closed By", value=interaction.user.mention)
    await interaction.response.send_message(embed=embed)
    await asyncio.sleep(5)
    await interaction.channel.edit(name=f"closed-{interaction.channel.name}")

# ── APPLICATIONS ──────────────────────────────────────────────

@bot.tree.command(name="create_application", description="Create an application form (Admin)")
@app_commands.describe(form_name="Form name", role="Role on approval", review_channel="Where apps go", questions="Comma-separated questions (max 5)")
@app_commands.default_permissions(administrator=True)
async def create_application(interaction: discord.Interaction, form_name: str, role: discord.Role,
                              review_channel: discord.TextChannel, questions: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    q_list = [q.strip() for q in questions.split(",")[:5]]
    if not q_list:
        await interaction.response.send_message("❌ At least 1 question required.", ephemeral=True); return
    c.execute("INSERT OR REPLACE INTO application_forms (guild_id,form_name,questions,role_id,channel_id,log_channel_id,created_by,created_at) VALUES (?,?,?,?,?,?,?,?)",
              (interaction.guild.id, form_name, json.dumps(q_list), role.id, review_channel.id,
               review_channel.id, interaction.user.id, datetime.now(timezone.utc).isoformat())); conn.commit()
    embed = discord.Embed(title="✅ Application Form Created", color=discord.Color.green())
    embed.add_field(name="Name", value=form_name, inline=True)
    embed.add_field(name="Role", value=role.mention, inline=True)
    embed.add_field(name="Review Channel", value=review_channel.mention, inline=True)
    embed.add_field(name="Questions", value="\n".join(f"{i+1}. {q}" for i,q in enumerate(q_list)), inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="application_panel", description="Create an application panel")
async def application_panel(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    forms = c.execute("SELECT form_name, json_array_length(questions) FROM application_forms WHERE guild_id=?",
                     (interaction.guild.id,)).fetchall()
    if not forms:
        await interaction.response.send_message("❌ No forms. Use `/create_application` first.", ephemeral=True); return
    embed = discord.Embed(title="📝 Applications", description="Click a button to apply!", color=discord.Color.blue())
    for form_name, q_count in forms:
        embed.add_field(name=form_name, value=f"{q_count} questions", inline=True)
    await interaction.response.send_message(embed=embed, view=ApplicationPanelView(forms))

@bot.tree.command(name="review_app", description="Review an application (Admin)")
@app_commands.describe(app_id="Application ID")
@app_commands.default_permissions(administrator=True)
async def review_app(interaction: discord.Interaction, app_id: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    app = c.execute("SELECT * FROM applications WHERE app_id=? AND guild_id=?", (app_id, interaction.guild.id)).fetchone()
    if not app:
        await interaction.response.send_message("❌ Application not found.", ephemeral=True); return
    if app["status"] != "pending":
        await interaction.response.send_message(f"❌ Already {app['status']}.", ephemeral=True); return
    answers = json.loads(app["answers"])
    member = interaction.guild.get_member(app["user_id"])
    embed = discord.Embed(title=f"📝 Review: {app['form_name']}", color=discord.Color.orange())
    embed.add_field(name="Applicant", value=f"{member.mention if member else app['user_id']} ({app['user_id']})", inline=False)
    embed.add_field(name="App ID", value=app["app_id"], inline=True)
    embed.add_field(name="Submitted", value=app["submitted_at"][:19], inline=True)
    for i, (q, a) in enumerate(answers, 1):
        embed.add_field(name=f"Q{i}: {q[:50]}", value=a[:200], inline=False)
    await interaction.response.send_message(embed=embed, view=ApplicationReviewView(app_id), ephemeral=True)

@bot.tree.command(name="list_applications", description="List pending applications (Admin)")
@app_commands.default_permissions(administrator=True)
async def list_applications(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    apps = c.execute("SELECT app_id,form_name,username,submitted_at FROM applications WHERE guild_id=? AND status='pending' ORDER BY submitted_at DESC",
                    (interaction.guild.id,)).fetchall()
    if not apps:
        await interaction.response.send_message("📭 No pending applications.", ephemeral=True); return
    embed = discord.Embed(title="📝 Pending Applications", color=discord.Color.blue())
    for app in apps[:25]:
        embed.add_field(name=app["app_id"], value=f"**Form:** {app['form_name']}\n**User:** {app['username']}\n**Date:** {app['submitted_at'][:10]}", inline=False)
    embed.set_footer(text="Use /review_app <id> to review")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ── FUN ───────────────────────────────────────────────────────

@bot.tree.command(name="gif", description="Get a GIF")
@app_commands.describe(search="Search term")
async def gif(interaction: discord.Interaction, search: str):
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://api.giphy.com/v1/gifs/search?api_key={GIPHY_API_KEY}&q={quote(search)}&limit=1&rating=pg") as r:
            data = await r.json()
    embed = discord.Embed(title=f"🎬 {search}", color=discord.Color.blue())
    if data.get("data"):
        embed.set_image(url=data["data"][0]["images"]["original"]["url"])
    else:
        embed.description = "No GIF found."
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="meme", description="Random meme")
async def meme(interaction: discord.Interaction):
    async with aiohttp.ClientSession() as s:
        async with s.get("https://meme-api.com/gimme") as r:
            data = await r.json()
    embed = discord.Embed(title=f"😂 {data['title'][:100]}", color=discord.Color.orange())
    embed.set_image(url=data['url'])
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="hug", description="Hug a member")
@app_commands.describe(member="Member to hug")
async def hug(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message(embed=discord.Embed(description=f"{interaction.user.mention} hugs {member.mention}! 🤗", color=discord.Color.magenta()))

@bot.tree.command(name="slap", description="Slap a member")
@app_commands.describe(member="Member to slap")
async def slap(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message(embed=discord.Embed(description=f"{interaction.user.mention} slaps {member.mention}! 👋", color=discord.Color.red()))

@bot.tree.command(name="say", description="Bot repeats your message")
@app_commands.describe(text="Text to repeat")
async def say(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(text[:2000])

# ── OWNER ─────────────────────────────────────────────────────

@bot.tree.command(name="owner_panel", description="[Owner] Bot management panel")
async def owner_panel(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Owner only.", ephemeral=True); return
    embed = discord.Embed(title="👑 XULT Owner Panel", color=discord.Color.gold())
    embed.add_field(name="Servers", value=str(len(bot.guilds)), inline=True)
    embed.add_field(name="Latency", value=f"{round(bot.latency*1000,2)}ms", inline=True)
    embed.add_field(name="Uptime", value=str(datetime.now(timezone.utc)-bot.start_time).split('.')[0], inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="owner_stats", description="[Owner] Detailed statistics")
async def owner_stats(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Owner only.", ephemeral=True); return
    embed = discord.Embed(title="📊 XULT Statistics", color=discord.Color.gold())
    embed.add_field(name="Users", value=f"{c.execute('SELECT COUNT(*) FROM users').fetchone()[0]:,}", inline=True)
    embed.add_field(name="Servers", value=f"{len(bot.guilds):,}", inline=True)
    embed.add_field(name="Premium", value=f"{c.execute('SELECT COUNT(*) FROM premium_users WHERE is_active=1').fetchone()[0]:,}", inline=True)
    embed.add_field(name="Stock", value=f"{sum(count_stock(f.stem) for f in STOCK_DIR.glob('*.txt')):,}", inline=True)
    embed.add_field(name="Latency", value=f"{round(bot.latency*1000,2)}ms", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="broadcastupdate", description="[Owner] Broadcast update to all servers")
@app_commands.describe(message="Update message")
async def broadcastupdate(interaction: discord.Interaction, message: str):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Owner only.", ephemeral=True); return
    await interaction.response.defer(ephemeral=True)
    sent = 0
    for config in c.execute("SELECT server_id,bot_update_log FROM logging_config WHERE bot_update_log IS NOT NULL").fetchall():
        guild = bot.get_guild(config["server_id"])
        if guild:
            ch = guild.get_channel(config["bot_update_log"])
            if ch:
                embed = discord.Embed(title="📢 XULT Update", description=message, color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
                try: await ch.send(embed=embed); sent += 1
                except: pass
    await interaction.followup.send(f"✅ Broadcast to {sent} servers.", ephemeral=True)

@bot.tree.command(name="pull", description="[Owner] Pull saved members to a server")
@app_commands.describe(target_server="Server ID or name", count="Number to pull or 'all'")
async def pull_members(interaction: discord.Interaction, target_server: str, count: str = "all"):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Owner only.", ephemeral=True); return
    await interaction.response.defer(ephemeral=True)
    target_guild = next((g for g in bot.guilds if str(g.id)==target_server or g.name.lower()==target_server.lower()), None)
    if not target_guild:
        await interaction.followup.send(f"❌ Server '{target_server}' not found.", ephemeral=True); return
    saved = c.execute("SELECT DISTINCT user_id FROM saved_members").fetchall()
    if not saved:
        await interaction.followup.send("❌ No saved members.", ephemeral=True); return
    members_to_pull = [r[0] for r in (saved if count.lower()=="all" else saved[:int(count)])]
    success = 0
    for uid in members_to_pull:
        if await restore_member_to_server(uid, target_guild): success += 1
        await asyncio.sleep(0.3)
    await interaction.followup.send(f"✅ Pulled {success}/{len(members_to_pull)} members to **{target_guild.name}**.", ephemeral=True)

# ==================== API SERVER ====================

async def require_auth(request) -> Optional[web.Response]:
    if request.headers.get("Authorization","") != f"Bearer {API_KEY}":
        return web.json_response({"error":"Unauthorized"}, status=401)
    return None

async def handle_api_key(request):
    return web.json_response({"key": API_KEY})

async def handle_health(request):
    return web.json_response({"status":"healthy","uptime":str(datetime.now(timezone.utc)-bot.start_time).split(".")[0]})

async def handle_stats(request):
    if err := await require_auth(request): return err
    try:
        total_users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0] or 0
        premium     = c.execute("SELECT COUNT(*) FROM premium_users WHERE is_active=1").fetchone()[0] or 0
        cmds_today  = c.execute("SELECT COUNT(*) FROM stock_usage WHERE generated_at > datetime('now','-1 day')").fetchone()[0] or 0
        total_coins = c.execute("SELECT SUM(coins) FROM users").fetchone()[0] or 0
        activity = []
        for i in range(6,-1,-1):
            day = datetime.now(timezone.utc) - timedelta(days=i)
            cnt = c.execute("SELECT COUNT(*) FROM stock_usage WHERE date(generated_at)=date(?)", (day.isoformat(),)).fetchone()[0] or 0
            activity.append(cnt)
        recent = []
        for row in c.execute("SELECT user_id,username,stock_type,generated_at FROM stock_usage ORDER BY generated_at DESC LIMIT 10").fetchall():
            recent.append({"userId":str(row[0]),"username":row[1] or f"User-{row[0]}","type":row[2],
                           "time":datetime.fromisoformat(row[3]).strftime("%H:%M:%S")})
        return web.json_response({
            "total_users":total_users,"total_servers":len(bot.guilds),"total_commands":cmds_today,
            "premium_users":premium,"total_coins":total_coins,"activity":activity,"recent":recent,
            "latency":round(bot.latency*1000,2),"uptime":str(datetime.now(timezone.utc)-bot.start_time).split(".")[0]
        })
    except Exception as e:
        return web.json_response({"error":str(e)}, status=500)

async def handle_stock(request):
    try:
        data = {}
        for f in STOCK_DIR.glob("*.txt"):
            data[f.stem] = {"count":count_stock(f.stem),
                            "name":STOCK_TYPES.get(f.stem,{}).get("name",f.stem.capitalize()),
                            "emoji":STOCK_TYPES.get(f.stem,{}).get("emoji","📄")}
        return web.json_response(data)
    except Exception as e:
        return web.json_response({"error":str(e)}, status=500)

async def handle_check_premium(request):
    if err := await require_auth(request): return err
    try:
        uid = int(request.match_info["user_id"])
        if uid == OWNER_ID: return web.json_response({"hasPremium":True})
        return web.json_response({"hasPremium": await check_user_premium(uid)})
    except Exception as e:
        return web.json_response({"error":str(e)}, status=500)

async def handle_gen(request):
    if err := await require_auth(request): return err
    try:
        data = await request.json()
        user_id  = data.get("user_id")
        stock_type = data.get("stock_type")
        if not user_id or not stock_type:
            return web.json_response({"error":"Missing user_id or stock_type"}, status=400)
        is_prem = await check_user_premium(int(user_id))
        cd, remaining = is_on_cooldown(int(user_id), is_prem)
        if cd:
            return web.json_response({"error":f"Cooldown: {remaining}s","cooldown":remaining}, status=429)
        stock = get_stock_entry(stock_type)
        if not stock:
            return web.json_response({"error":"No stock available"}, status=404)
        if not is_prem: set_cooldown(int(user_id))
        user = bot.get_user(int(user_id))
        if user:
            try: await user.send(f"🎁 **{stock_type}** from the vending machine:\n```\n{stock}\n```")
            except: pass
        c.execute("INSERT INTO stock_usage (user_id,username,stock_type,stock_content,generated_at,server_id,server_name,channel_id,channel_name,is_dm) VALUES (?,?,?,?,?,?,?,?,?,0)",
                  (user_id, str(user) if user else str(user_id), stock_type, stock, datetime.now(timezone.utc).isoformat(), 0, "Vending Machine", 0, "Web"))
        conn.commit()
        return web.json_response({"success":True,"message":"Stock sent to your DMs!"})
    except Exception as e:
        return web.json_response({"error":str(e)}, status=500)

async def handle_verify_payment(request):
    if err := await require_auth(request): return err
    try:
        data = await request.json()
        user_id = int(data.get("user_id"))
        method  = data.get("method","paypal")
        txn_id  = data.get("transaction_id","manual")
        success = await assign_premium_role(user_id)
        if success:
            c.execute("INSERT OR REPLACE INTO pending_payments (user_id,payment_id,amount,method,status,created_at,verified_at) VALUES (?,?,?,?,?,?,?)",
                      (user_id, txn_id, 3.00, method, "completed", datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()))
            conn.commit()
            return web.json_response({"success":True,"message":"Premium activated!"})
        return web.json_response({"error":"Failed to assign premium role"}, status=500)
    except Exception as e:
        return web.json_response({"error":str(e)}, status=500)

async def handle_servers(request):
    if err := await require_auth(request): return err
    return web.json_response([{"id":str(g.id),"name":g.name,"icon":str(g.icon.url) if g.icon else None,
                               "memberCount":g.member_count,"ownerId":str(g.owner_id)} for g in bot.guilds])

async def handle_server_config(request):
    if err := await require_auth(request): return err
    try:
        server_id = int(request.match_info["server_id"])
        cmds_status = {}
        for cat, cmd_list in CMD_CATEGORIES.items():
            for cmd_name in cmd_list:
                cmds_status[cmd_name] = {
                    "enabled": is_command_enabled(server_id, cmd_name),
                    "allowed_roles": get_command_allowed_roles(server_id, cmd_name),
                    "disabled_channels": get_command_disabled_channels(server_id, cmd_name),
                    "category": cat
                }
        return web.json_response({"server_id":server_id,"commands":cmds_status,"categories":CMD_CATEGORIES})
    except Exception as e:
        return web.json_response({"error":str(e)}, status=500)

async def handle_update_command(request):
    if err := await require_auth(request): return err
    try:
        server_id = int(request.match_info["server_id"])
        command   = request.match_info["command"]
        data = await request.json()
        enabled = data.get("enabled", True)
        update_command_setting(server_id, command, enabled,
                               data.get("allowed_roles",[]), data.get("disabled_channels",[]))
        # Auto-sync the guild so change takes effect immediately
        guild = bot.get_guild(server_id)
        if guild:
            asyncio.create_task(sync_guild_commands(guild))
        return web.json_response({"success":True,"message":f"/{command} {'enabled' if enabled else 'disabled'} and synced"})
    except Exception as e:
        return web.json_response({"error":str(e)}, status=500)

# ── OWNER API ENDPOINTS ────────────────────────────────────────

async def handle_owner_pull(request):
    if err := await require_auth(request): return err
    try:
        data = await request.json()
        target = data.get("target_server","")
        count  = data.get("count","all")
        target_guild = next((g for g in bot.guilds if str(g.id)==str(target) or g.name.lower()==target.lower()), None)
        if not target_guild:
            return web.json_response({"error":f"Server '{target}' not found"}, status=404)
        saved = c.execute("SELECT DISTINCT user_id FROM saved_members").fetchall()
        members_to_pull = [r[0] for r in (saved if str(count).lower()=="all" else saved[:int(count)])]
        success = 0
        for uid in members_to_pull:
            if await restore_member_to_server(uid, target_guild): success += 1
            await asyncio.sleep(0.2)
        return web.json_response({"success":True,"message":f"Pulled {success}/{len(members_to_pull)} members to {target_guild.name}"})
    except Exception as e:
        return web.json_response({"error":str(e)}, status=500)

async def handle_owner_save_all(request):
    if err := await require_auth(request): return err
    try:
        saved = 0
        for guild in bot.guilds:
            save_server_backup(guild)
            await save_all_members(guild)
            saved += 1
        return web.json_response({"success":True,"message":f"Saved {saved} servers"})
    except Exception as e:
        return web.json_response({"error":str(e)}, status=500)

async def handle_owner_manage_coins(request):
    if err := await require_auth(request): return err
    try:
        data = await request.json()
        user_id = int(data.get("user_id"))
        amount  = int(data.get("amount", 0))
        if amount > 0: add_coins(user_id, amount)
        else:          remove_coins(user_id, abs(amount))
        new_bal = get_balance(user_id)
        return web.json_response({"success":True,"message":f"{'Added' if amount>0 else 'Removed'} {abs(amount)} coins","new_balance":new_bal})
    except Exception as e:
        return web.json_response({"error":str(e)}, status=500)

async def handle_owner_ban_user(request):
    if err := await require_auth(request): return err
    try:
        data = await request.json()
        user_id = int(data.get("user_id"))
        reason  = data.get("reason", "No reason")
        c.execute("UPDATE users SET banned=1, banned_reason=? WHERE id=?", (reason, user_id))
        if c.rowcount == 0:
            c.execute("INSERT INTO users (id,banned,banned_reason) VALUES (?,1,?)", (user_id, reason))
        conn.commit()
        log_action(OWNER_ID, "BAN_USER", f"user={user_id} reason={reason}")
        return web.json_response({"success":True,"message":f"User {user_id} banned"})
    except Exception as e:
        return web.json_response({"error":str(e)}, status=500)

async def handle_owner_premium_users(request):
    if err := await require_auth(request): return err
    try:
        rows = c.execute("SELECT pu.user_id, u.username, pu.granted_at, pu.is_active FROM premium_users pu LEFT JOIN users u ON pu.user_id=u.id ORDER BY pu.granted_at DESC").fetchall()
        return web.json_response([{"user_id":str(r[0]),"username":r[1] or f"User-{r[0]}","granted_at":r[2],"is_active":bool(r[3])} for r in rows])
    except Exception as e:
        return web.json_response({"error":str(e)}, status=500)

async def handle_owner_logs(request):
    if err := await require_auth(request): return err
    try:
        rows = c.execute("SELECT user_id,action,details,timestamp FROM logs ORDER BY timestamp DESC LIMIT 100").fetchall()
        return web.json_response([{"userId":str(r[0]),"action":r[1],"details":r[2],"time":r[3]} for r in rows])
    except Exception as e:
        return web.json_response({"error":str(e)}, status=500)

async def handle_owner_broadcast(request):
    if err := await require_auth(request): return err
    try:
        data = await request.json()
        message = data.get("message","")
        if not message:
            return web.json_response({"error":"No message"}, status=400)
        sent = 0
        for config in c.execute("SELECT server_id,bot_update_log FROM logging_config WHERE bot_update_log IS NOT NULL").fetchall():
            guild = bot.get_guild(config["server_id"])
            if guild:
                ch = guild.get_channel(config["bot_update_log"])
                if ch:
                    embed = discord.Embed(title="📢 XULT Broadcast", description=message, color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
                    try: await ch.send(embed=embed); sent += 1
                    except: pass
        return web.json_response({"success":True,"message":f"Broadcast sent to {sent} servers"})
    except Exception as e:
        return web.json_response({"error":str(e)}, status=500)

async def handle_owner_backup_db(request):
    if err := await require_auth(request): return err
    try:
        for guild in bot.guilds:
            save_server_backup(guild)
        filename = f"full_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        return web.json_response({"success":True,"filename":filename,"guilds":len(bot.guilds)})
    except Exception as e:
        return web.json_response({"error":str(e)}, status=500)

async def handle_owner_restore_server(request):
    if err := await require_auth(request): return err
    try:
        data = await request.json()
        server_id = int(data.get("server_id"))
        guild = bot.get_guild(server_id)
        if not guild:
            return web.json_response({"error":"Server not found"}, status=404)
        path = BACKUP_DIR / f"{server_id}.json"
        if not path.exists():
            return web.json_response({"error":"No backup found"}, status=404)
        backup = load_json(path)
        for r in sorted(backup.get("roles",[]), key=lambda x: x["position"]):
            try:
                await guild.create_role(name=r["name"],permissions=discord.Permissions(r["permissions"]),
                    colour=discord.Colour(r["color"]),hoist=r["hoist"],mentionable=r["mentionable"],reason="API Restore")
                await asyncio.sleep(0.5)
            except: pass
        return web.json_response({"success":True,"message":f"Restore started for {guild.name}"})
    except Exception as e:
        return web.json_response({"error":str(e)}, status=500)

async def handle_oauth_callback(request):
    try:
        data = await request.json()
        code = data.get("code"); state = data.get("state"); redirect_uri = data.get("redirect_uri")
        if not code or not state:
            return web.json_response({"success":False,"error":"Missing parameters"}, status=400)
        guild_id, user_id = [int(x) for x in state.split(":")]
        async with aiohttp.ClientSession() as s:
            async with s.post("https://discord.com/api/oauth2/token",
                              data={"client_id":CLIENT_ID,"client_secret":CLIENT_SECRET,"grant_type":"authorization_code",
                                    "code":code,"redirect_uri":redirect_uri}) as r:
                if r.status != 200:
                    return web.json_response({"success":False,"error":"Token exchange failed"}, status=400)
                token_json = await r.json()
            async with s.get("https://discord.com/api/users/@me",
                             headers={"Authorization":f"Bearer {token_json['access_token']}"}) as r:
                if r.status != 200:
                    return web.json_response({"success":False,"error":"Failed to get user"}, status=400)
                user_data = await r.json()
        if int(user_data["id"]) != user_id:
            return web.json_response({"success":False,"error":"User mismatch"}, status=400)
        guild = bot.get_guild(guild_id)
        if not guild:
            return web.json_response({"success":False,"error":"Guild not found"}, status=404)
        row = c.execute("SELECT role_id FROM verification WHERE server_id=?", (guild_id,)).fetchone()
        if not row:
            return web.json_response({"success":False,"error":"Verification not configured"}, status=400)
        role = guild.get_role(row["role_id"])
        member = guild.get_member(user_id)
        if not member:
            return web.json_response({"success":False,"error":"User not in server"}, status=404)
        if role and role not in member.roles:
            await member.add_roles(role, reason="OAuth Verification")
        return web.json_response({"success":True,"username":user_data["username"],"guild_name":guild.name})
    except Exception as e:
        return web.json_response({"success":False,"error":str(e)}, status=500)

# ==================== API STARTUP ====================

async def start_api_server():
    app = web.Application()

    @web.middleware
    async def cors_middleware(request, handler):
        if request.method == "OPTIONS":
            resp = web.Response()
            resp.headers.update({"Access-Control-Allow-Origin":"*","Access-Control-Allow-Methods":"GET,POST,PUT,DELETE,OPTIONS","Access-Control-Allow-Headers":"Content-Type,Authorization"})
            return resp
        resp = await handler(request)
        resp.headers.update({"Access-Control-Allow-Origin":"*","Access-Control-Allow-Headers":"Content-Type,Authorization"})
        return resp

    app.middlewares.append(cors_middleware)

    app.router.add_get("/health",                                     handle_health)
    app.router.add_get("/api/key",                                    handle_api_key)
    app.router.add_get("/api/stats",                                  handle_stats)
    app.router.add_get("/api/stock",                                  handle_stock)
    app.router.add_get("/api/servers",                                handle_servers)
    app.router.add_get("/api/check-premium/{user_id}",                handle_check_premium)
    app.router.add_get("/api/server/{server_id}/config",              handle_server_config)
    app.router.add_post("/api/gen",                                   handle_gen)
    app.router.add_post("/api/verify-payment",                        handle_verify_payment)
    app.router.add_post("/api/verify",                                handle_oauth_callback)
    app.router.add_post("/api/server/{server_id}/command/{command}",  handle_update_command)
    # Owner endpoints
    app.router.add_post("/api/owner/pull",                            handle_owner_pull)
    app.router.add_post("/api/owner/save_all",                        handle_owner_save_all)
    app.router.add_post("/api/owner/manage_coins",                    handle_owner_manage_coins)
    app.router.add_post("/api/owner/ban_user",                        handle_owner_ban_user)
    app.router.add_get("/api/owner/premium_users",                    handle_owner_premium_users)
    app.router.add_get("/api/owner/logs",                             handle_owner_logs)
    app.router.add_post("/api/owner/broadcast",                       handle_owner_broadcast)
    app.router.add_post("/api/owner/backup_db",                       handle_owner_backup_db)
    app.router.add_post("/api/owner/restore_server",                  handle_owner_restore_server)

    port = API_PORT
    for attempt in range(10):
        try:
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", port)
            await site.start()
            log.info(f"✅ API server running on port {port}")
            return
        except OSError:
            port += 1
    log.error("❌ Could not start API server on any port")

# ==================== RUN ====================

if __name__ == "__main__":
    print("=" * 55)
    print("  ⚡  XULT — Ultimate Discord Bot")
    print("=" * 55)
    print(f"  Data:   {DATA_DIR}")
    print(f"  Stock:  {STOCK_DIR}")
    print(f"  API:    port {API_PORT}")
    print(f"  Owner:  {OWNER_ID}")
    print(f"  Key:    {API_KEY[:8]}...")
    print("=" * 55)
    print("  ✅ Commands sync PER GUILD - hidden when disabled")
    print("  ✅ Each server has independent command settings")
    print("  ✅ All owner API endpoints available")
    print("=" * 55)

    bot.run(TOKEN)
