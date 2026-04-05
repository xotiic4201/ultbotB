"""
XULT - Ultimate Discord Bot
Improved & production-ready version
"""

import asyncio, aiohttp, json, logging, os, random, re, secrets, sqlite3, time, unicodedata
import difflib, pytz
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List
from urllib.parse import quote

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import View, Button, Select
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("xult")

# ─────────────────────────── CONFIG ───────────────────────────

TOKEN             = os.getenv("DISCORD_BOT_TOKEN")
CLIENT_ID         = os.getenv("CLIENT_ID", "")
CLIENT_SECRET     = os.getenv("CLIENT_SECRET", "")
REDIRECT_URI      = os.getenv("REDIRECT_URI", "")
YOUTUBE_API_KEY   = os.getenv("YOUTUBE_API_KEY", "")
TWITCH_CLIENT_ID  = os.getenv("TWITCH_CLIENT_ID", "")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")
TWITTER_BEARER    = os.getenv("TWITTER_BEARER_TOKEN", "")
GIPHY_API_KEY     = os.getenv("GIPHY_API_KEY", "")
BOT_OWNER_ID      = int(os.getenv("BOT_OWNER_ID", "0"))
PREMIUM_ROLE_ID   = int(os.getenv("PREMIUM_ROLE_ID", "0"))
MAIN_SERVER_ID    = int(os.getenv("MAIN_SERVER_ID", "0"))
GEN_LOG_CHANNEL   = int(os.getenv("GEN_LOG_CHANNEL_ID", "0"))
TARGET_SERVER_ID  = int(os.getenv("TARGET_SERVER_ID", "0"))
API_PORT          = int(os.getenv("PORT", os.getenv("API_PORT", "10000")))
API_KEY           = os.getenv("API_KEY", secrets.token_hex(32))

if not TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN not set!")

BASE_DIR   = Path.cwd()
DATA_DIR   = BASE_DIR / "data";   DATA_DIR.mkdir(exist_ok=True)
BACKUP_DIR = DATA_DIR / "backups"; BACKUP_DIR.mkdir(exist_ok=True)
KEYS_DIR   = BASE_DIR / "keys";   KEYS_DIR.mkdir(exist_ok=True)

# Persist API key to disk so dashboard can bootstrap
(DATA_DIR / "api_key.txt").write_text(API_KEY)

# ─────────────────────────── DATABASE ────────────────────────

db = sqlite3.connect(DATA_DIR / "xult.db", check_same_thread=False)
db.row_factory = sqlite3.Row
cur = db.cursor()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, username TEXT, coins INTEGER DEFAULT 0,
    xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1, last_daily TIMESTAMP,
    banned INTEGER DEFAULT 0, banned_reason TEXT
);
CREATE TABLE IF NOT EXISTS premium_users (
    user_id INTEGER PRIMARY KEY, granted_at TIMESTAMP, is_active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS server_configs (
    server_id INTEGER PRIMARY KEY, log_channel INTEGER, welcome_channel INTEGER,
    welcome_message TEXT, leave_channel INTEGER, leave_message TEXT,
    auto_role INTEGER, mod_role INTEGER, muted_role INTEGER, config TEXT
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
CREATE TABLE IF NOT EXISTS key_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT,
    key_type TEXT, key_content TEXT, used_at TIMESTAMP,
    server_id INTEGER, server_name TEXT, channel_name TEXT, is_dm INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS user_cooldowns (
    user_id INTEGER PRIMARY KEY, last_used TIMESTAMP
);
CREATE TABLE IF NOT EXISTS tracked_channels (
    server_id INTEGER, platform TEXT, target TEXT, last_id TEXT, notify_channel INTEGER, role_id INTEGER,
    PRIMARY KEY (server_id, platform, target)
);
CREATE TABLE IF NOT EXISTS reaction_roles (
    message_id INTEGER, channel_id INTEGER, role_id INTEGER, emoji TEXT,
    PRIMARY KEY (message_id, emoji)
);
CREATE TABLE IF NOT EXISTS role_on_join (
    server_id INTEGER PRIMARY KEY, role_id INTEGER, delay INTEGER
);
CREATE TABLE IF NOT EXISTS bad_words (server_id INTEGER, word TEXT, PRIMARY KEY (server_id, word));
CREATE TABLE IF NOT EXISTS allowed_channels (server_id INTEGER, channel_id INTEGER, PRIMARY KEY (server_id, channel_id));
CREATE TABLE IF NOT EXISTS four_twenty (
    server_id INTEGER PRIMARY KEY, channel_id INTEGER, role_id INTEGER,
    voice_channel_id INTEGER, timezone TEXT DEFAULT 'UTC'
);
CREATE TABLE IF NOT EXISTS verification (
    server_id INTEGER PRIMARY KEY, channel_id INTEGER, role_id INTEGER, log_channel_id INTEGER
);
CREATE TABLE IF NOT EXISTS report_channels (server_id INTEGER PRIMARY KEY, channel_id INTEGER, role_id INTEGER);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT, server_id INTEGER, reporter_id INTEGER,
    reported_id INTEGER, reason TEXT, evidence TEXT, status TEXT DEFAULT 'pending', timestamp TIMESTAMP
);
CREATE TABLE IF NOT EXISTS channel_activity (
    channel_id INTEGER PRIMARY KEY, server_id INTEGER,
    message_count INTEGER DEFAULT 0, last_message TIMESTAMP
);
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
    action TEXT, details TEXT, timestamp TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY, user_id INTEGER, access_token TEXT, expires_at TIMESTAMP
);
"""
for stmt in _SCHEMA.strip().split(";"):
    if stmt.strip():
        cur.execute(stmt)
db.commit()

# ─────────────────────────── JSON HELPERS ─────────────────────

JSON_FILES = {k: DATA_DIR / f"{k}.json" for k in [
    "server_settings", "gen_access", "auto_update", "log_channels",
    "bad_words", "four_twenty", "verification"
]}
for f in JSON_FILES.values():
    if not f.exists():
        f.write_text("{}")

def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text()) or (default if default is not None else {})
    except Exception:
        return default if default is not None else {}

def save_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2))

def log_action(user_id: int, action: str, details: str = ""):
    cur.execute("INSERT INTO logs (user_id, action, details, timestamp) VALUES (?,?,?,?)",
                (user_id, action, details, datetime.utcnow().isoformat()))
    db.commit()

# ─────────────────────────── BOT ─────────────────────────────

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
bot.start_time = datetime.utcnow()
bot.owner_id = BOT_OWNER_ID

# ─────────────────────────── ECONOMY HELPERS ──────────────────

def ensure_user(user_id: int):
    cur.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (user_id,))
    db.commit()

def get_balance(user_id: int) -> int:
    ensure_user(user_id)
    return cur.execute("SELECT coins FROM users WHERE id=?", (user_id,)).fetchone()[0]

def add_coins(user_id: int, amount: int):
    ensure_user(user_id)
    cur.execute("UPDATE users SET coins = MAX(0, coins + ?) WHERE id=?", (amount, user_id))
    db.commit()

def add_xp(user_id: int, amount: int) -> bool:
    """Returns True if levelled up."""
    ensure_user(user_id)
    row = cur.execute("SELECT xp, level FROM users WHERE id=?", (user_id,)).fetchone()
    new_xp = row["xp"] + amount
    new_level = int(new_xp ** 0.5)
    levelled = new_level > row["level"]
    cur.execute("UPDATE users SET xp=?, level=? WHERE id=?", (new_xp, max(row["level"], new_level), user_id))
    db.commit()
    return levelled

# ─────────────────────────── KEY DISTRIBUTION ─────────────────

def key_file(key_type: str) -> Path:
    return KEYS_DIR / f"{key_type.lower().strip().replace(' ','_')}.txt"

def count_keys(key_type: str) -> int:
    f = key_file(key_type)
    if not f.exists():
        return 0
    lines = [l.strip() for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    return len(lines)

def pop_key(key_type: str) -> Optional[str]:
    f = key_file(key_type)
    if not f.exists():
        return None
    lines = [l.strip() for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        return None
    key, remaining = lines[0], lines[1:]
    f.write_text("\n".join(remaining), encoding="utf-8")
    return key

def append_keys(key_type: str, new_keys: List[str]):
    f = key_file(key_type)
    existing = [l.strip() for l in f.read_text(encoding="utf-8").splitlines() if l.strip()] if f.exists() else []
    all_keys = existing + new_keys
    f.write_text("\n".join(all_keys), encoding="utf-8")

# ─────────────────────────── COOLDOWNS ────────────────────────

COOLDOWN_SECONDS = 5

def is_on_cooldown(user_id: int) -> tuple[bool, int]:
    row = cur.execute("SELECT last_used FROM user_cooldowns WHERE user_id=?", (user_id,)).fetchone()
    if row and row[0]:
        elapsed = time.time() - datetime.fromisoformat(row[0]).timestamp()
        if elapsed < COOLDOWN_SECONDS:
            return True, int(COOLDOWN_SECONDS - elapsed)
    return False, 0

def set_cooldown(user_id: int):
    cur.execute("INSERT OR REPLACE INTO user_cooldowns (user_id, last_used) VALUES (?,?)",
                (user_id, datetime.utcnow().isoformat()))
    db.commit()

# ─────────────────────────── SERVER CONFIG ────────────────────

def get_server_config(guild_id: int) -> dict:
    row = cur.execute("SELECT * FROM server_configs WHERE server_id=?", (guild_id,)).fetchone()
    if row:
        d = dict(row)
        d["config"] = json.loads(d["config"]) if d.get("config") else {}
        return d
    return {"server_id": guild_id, "config": {}}

# ─────────────────────────── MODERATION ───────────────────────

def parse_duration(s: str) -> timedelta:
    s = s.lower()
    matches = re.findall(r"(\d+)([smhd])", s)
    if not matches:
        raise ValueError("Use formats like 10m, 2h, 1d")
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return timedelta(seconds=sum(int(n) * units[u] for n, u in matches))

GLOBAL_BAD_WORDS = [
    "nigger", "nigga", "niggers", "niggas",
    "chink", "chinks", "kike", "kikes",
    "fag", "fags", "faggot",
    "discord.gg/",
]

def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return re.sub(r"[^a-z0-9\s]", "", text.lower())

def contains_bad_word(content: str, guild_id: int) -> bool:
    norm = _normalize(content)
    words = norm.split()
    all_bad = list(GLOBAL_BAD_WORDS)
    rows = cur.execute("SELECT word FROM bad_words WHERE server_id=?", (guild_id,)).fetchall()
    all_bad += [r[0] for r in rows]
    for bad in all_bad:
        for w in words:
            if difflib.get_close_matches(w, [bad], n=1, cutoff=0.85):
                return True
    return False

# ─────────────────────────── CHANNEL DETECTION ────────────────

MAIN_CHAT_KEYWORDS = [
    "general", "chat", "main", "discussion", "lounge",
    "talk", "global", "public", "community", "social",
    "offtopic", "off-topic", "town-square", "gen",
]

def _clean_channel_name(name: str) -> str:
    name = unicodedata.normalize("NFKD", name)
    return re.sub(r"[^\w\s-]", "", name).lower().strip()

def find_main_chat(guild: discord.Guild) -> Optional[discord.TextChannel]:
    permed = [c for c in guild.text_channels if c.permissions_for(guild.me).send_messages]
    # keyword match
    for ch in permed:
        if any(k in _clean_channel_name(ch.name) for k in MAIN_CHAT_KEYWORDS):
            return ch
    # most active
    row = cur.execute(
        "SELECT channel_id FROM channel_activity WHERE server_id=? ORDER BY message_count DESC LIMIT 1",
        (guild.id,)
    ).fetchone()
    if row:
        ch = guild.get_channel(row[0])
        if ch and ch.permissions_for(guild.me).send_messages:
            return ch
    # first by position
    return sorted(permed, key=lambda c: c.position)[0] if permed else None

# ─────────────────────────── SERVER BACKUP ────────────────────

def save_server_backup(guild: discord.Guild):
    data = {
        "roles": [{"name": r.name, "color": r.color.value, "hoist": r.hoist,
                   "mentionable": r.mentionable, "permissions": r.permissions.value,
                   "position": r.position} for r in guild.roles],
        "channels": [{"name": c.name, "type": "text" if isinstance(c, discord.TextChannel) else "voice",
                      "category": c.category.name if c.category else None,
                      "position": c.position} for c in guild.channels],
    }
    save_json(BACKUP_DIR / f"{guild.id}.json", data)

# ─────────────────────────── VIEWS ────────────────────────────

class VerifyButton(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify", style=discord.ButtonStyle.green, custom_id="verify_btn")
    async def verify(self, interaction: discord.Interaction, button: Button):
        row = cur.execute("SELECT role_id, log_channel_id FROM verification WHERE server_id=?",
                          (interaction.guild.id,)).fetchone()
        if not row:
            await interaction.response.send_message("Verification not configured.", ephemeral=True)
            return
        role = interaction.guild.get_role(row["role_id"])
        if not role:
            await interaction.response.send_message("Verified role not found.", ephemeral=True)
            return
        if role in interaction.user.roles:
            await interaction.response.send_message("Already verified!", ephemeral=True)
            return
        await interaction.user.add_roles(role)
        await interaction.response.send_message(f"✅ Verified! You received **{role.name}**.", ephemeral=True)
        if row["log_channel_id"]:
            lch = interaction.guild.get_channel(row["log_channel_id"])
            if lch:
                await lch.send(f"✅ {interaction.user.mention} verified.")
        log_action(interaction.user.id, "VERIFY", f"guild={interaction.guild.id}")


class RoleSelectView(View):
    def __init__(self, roles: List[discord.Role]):
        super().__init__(timeout=None)
        opts = [discord.SelectOption(label=r.name, value=str(r.id)) for r in roles[:25]]
        sel = Select(placeholder="Choose a role…", options=opts)
        sel.callback = self.on_select
        self.add_item(sel)

    async def on_select(self, interaction: discord.Interaction):
        rid = int(self.children[0].values[0])
        role = interaction.guild.get_role(rid)
        if not role:
            await interaction.response.send_message("Role not found.", ephemeral=True)
            return
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"Removed **{role.name}**.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"Gave you **{role.name}**.", ephemeral=True)


# ─────────────────────────── EVENTS ───────────────────────────

@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user} ({bot.user.id})")
    bot.add_view(VerifyButton())
    try:
        synced = await bot.tree.sync()
        log.info(f"Synced {len(synced)} slash commands")
    except Exception as e:
        log.error(f"Sync error: {e}")
    for task in [daily_coins, random_event, check_unjail, four_twenty_loop,
                 check_youtube, check_twitch, check_twitter]:
        if not task.is_running():
            task.start()
    bot.loop.create_task(start_api())
    log.info("All tasks started")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    # Track activity
    cur.execute("""
        INSERT INTO channel_activity (channel_id, server_id, message_count, last_message)
        VALUES (?,?,1,?)
        ON CONFLICT(channel_id) DO UPDATE SET message_count=message_count+1, last_message=?
    """, (message.channel.id, message.guild.id, datetime.utcnow().isoformat(), datetime.utcnow().isoformat()))
    db.commit()

    # XP & coins
    levelled = add_xp(message.author.id, random.randint(1, 5))
    add_coins(message.author.id, random.randint(0, 2))
    if levelled:
        row = cur.execute("SELECT level FROM users WHERE id=?", (message.author.id,)).fetchone()
        if row:
            await message.channel.send(
                f"🎉 {message.author.mention} levelled up to **level {row['level']}**!", delete_after=10
            )

    # Bad word filter
    allowed = [r[0] for r in cur.execute("SELECT channel_id FROM allowed_channels WHERE server_id=?",
                                          (message.guild.id,)).fetchall()]
    if message.channel.id not in allowed and contains_bad_word(message.content, message.guild.id):
        await message.delete()
        cur.execute("INSERT INTO warnings (user_id, moderator_id, reason, timestamp, server_id) VALUES (?,?,?,?,?)",
                    (message.author.id, bot.user.id, "Inappropriate language",
                     datetime.utcnow().isoformat(), message.guild.id))
        db.commit()
        warn_count = cur.execute("SELECT COUNT(*) FROM warnings WHERE user_id=? AND server_id=?",
                                 (message.author.id, message.guild.id)).fetchone()[0]
        embed = discord.Embed(description=f"⚠️ {message.author.mention}, watch your language! Warning **{warn_count}/3**.",
                              color=discord.Color.red())
        await message.channel.send(embed=embed, delete_after=8)
        if warn_count >= 3:
            try:
                await message.author.timeout(discord.utils.utcnow() + timedelta(minutes=10),
                                             reason="3 language warnings")
                cur.execute("DELETE FROM warnings WHERE user_id=? AND server_id=?",
                            (message.author.id, message.guild.id))
                db.commit()
            except discord.Forbidden:
                pass

    await bot.process_commands(message)


@bot.event
async def on_member_join(member: discord.Member):
    row = cur.execute("SELECT role_id, delay FROM role_on_join WHERE server_id=?",
                      (member.guild.id,)).fetchone()
    if row:
        await asyncio.sleep(row["delay"])
        role = member.guild.get_role(row["role_id"])
        if role:
            try:
                await member.add_roles(role)
            except discord.Forbidden:
                pass
    cfg = get_server_config(member.guild.id)
    if cfg.get("welcome_channel") and cfg.get("welcome_message"):
        ch = member.guild.get_channel(cfg["welcome_channel"])
        if ch:
            msg = cfg["welcome_message"].replace("{user}", member.mention).replace("{server}", member.guild.name)
            await ch.send(msg)


@bot.event
async def on_member_remove(member: discord.Member):
    cfg = get_server_config(member.guild.id)
    if cfg.get("leave_channel") and cfg.get("leave_message"):
        ch = member.guild.get_channel(cfg["leave_channel"])
        if ch:
            msg = cfg["leave_message"].replace("{user}", member.name).replace("{server}", member.guild.name)
            await ch.send(msg)


@bot.event
async def on_message_delete(message: discord.Message):
    if not message.guild or message.author.bot:
        return
    cfg = get_server_config(message.guild.id)
    if cfg.get("log_channel"):
        lch = message.guild.get_channel(cfg["log_channel"])
        if lch:
            embed = discord.Embed(title="🗑 Message Deleted", color=discord.Color.orange())
            embed.add_field(name="Author", value=message.author.mention, inline=True)
            embed.add_field(name="Channel", value=message.channel.mention, inline=True)
            embed.add_field(name="Content", value=(message.content or "*(empty)*")[:1024], inline=False)
            await lch.send(embed=embed)


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if not before.guild or before.author.bot or before.content == after.content:
        return
    cfg = get_server_config(before.guild.id)
    if cfg.get("log_channel"):
        lch = before.guild.get_channel(cfg["log_channel"])
        if lch:
            embed = discord.Embed(title="✏️ Message Edited", color=discord.Color.blue())
            embed.add_field(name="Before", value=before.content[:512] or "*(empty)*", inline=False)
            embed.add_field(name="After", value=after.content[:512] or "*(empty)*", inline=False)
            embed.add_field(name="Author", value=before.author.mention, inline=True)
            embed.add_field(name="Channel", value=before.channel.mention, inline=True)
            await lch.send(embed=embed)


# ─────────────────────────── BACKGROUND TASKS ─────────────────

@tasks.loop(hours=24)
async def daily_coins():
    cur.execute("SELECT id FROM users")
    for (uid,) in cur.fetchall():
        add_coins(uid, 50)
    log.info("Daily coin bonus distributed")


@tasks.loop(minutes=60)
async def random_event():
    for guild in random.sample(bot.guilds, min(3, len(bot.guilds))):
        members = [m for m in guild.members if not m.bot]
        if not members:
            continue
        winner = random.choice(members)
        reward = random.randint(10, 50)
        add_coins(winner.id, reward)
        ch = find_main_chat(guild)
        if ch:
            embed = discord.Embed(
                title="🎉 Random Event",
                description=f"{winner.mention} received **{reward} coins** — just for being here!",
                color=discord.Color.gold()
            )
            await ch.send(embed=embed)


@tasks.loop(seconds=30)
async def check_unjail():
    rows = cur.execute(
        "SELECT server_id, user_id, roles, jail_time, duration FROM jailed_members"
    ).fetchall()
    for row in rows:
        try:
            jail_time = datetime.fromisoformat(row["jail_time"])
            release = jail_time + parse_duration(row["duration"])
            if datetime.utcnow() < release:
                continue
            guild = bot.get_guild(row["server_id"])
            if guild:
                member = guild.get_member(row["user_id"])
                if member:
                    role_ids = json.loads(row["roles"])
                    roles = [guild.get_role(r) for r in role_ids if guild.get_role(r)]
                    if roles:
                        await member.add_roles(*roles, reason="Auto-unjail")
                    for ch in guild.text_channels + guild.voice_channels:
                        await ch.set_permissions(member, overwrite=None)
                    try:
                        await member.send(f"✅ You've been unjailed from **{guild.name}**.")
                    except discord.Forbidden:
                        pass
            cur.execute("DELETE FROM jailed_members WHERE server_id=? AND user_id=?",
                        (row["server_id"], row["user_id"]))
            db.commit()
        except Exception as e:
            log.error(f"check_unjail error: {e}")


@tasks.loop(minutes=1)
async def four_twenty_loop():
    rows = cur.execute("SELECT server_id, channel_id, role_id, voice_channel_id, timezone FROM four_twenty").fetchall()
    for row in rows:
        try:
            tz = pytz.timezone(row["timezone"] or "UTC")
            now = datetime.now(tz)
            if now.hour in (4, 16) and now.minute == 20:
                guild = bot.get_guild(row["server_id"])
                if not guild:
                    continue
                ch = guild.get_channel(row["channel_id"])
                if not ch:
                    continue
                vc = guild.get_channel(row["voice_channel_id"]) if row["voice_channel_id"] else None
                role_mention = f"<@&{row['role_id']}>" if row["role_id"] else ""
                embed = discord.Embed(
                    title="It's 4:20! 🌿",
                    description=f"{'[Join VC](' + vc.jump_url + ')' if vc else ''} {role_mention}",
                    color=discord.Color.green()
                )
                await ch.send(embed=embed)
                await asyncio.sleep(61)
        except Exception as e:
            log.error(f"four_twenty_loop: {e}")


# ─── Notification loops ────────────────────────────────────────

@tasks.loop(minutes=5)
async def check_youtube():
    rows = cur.execute(
        "SELECT server_id, target, last_id, notify_channel, role_id FROM tracked_channels WHERE platform='youtube'"
    ).fetchall()
    for row in rows:
        guild = bot.get_guild(row["server_id"])
        if not guild:
            continue
        ch = guild.get_channel(row["notify_channel"])
        if not ch:
            continue
        try:
            url = f"https://www.youtube.com/feeds/videos.xml?channel_id={row['target']}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        continue
                    xml_text = await resp.text()
            root = ET.fromstring(xml_text)
            ns = {"yt": "http://www.youtube.com/xml/schemas/2015",
                  "atom": "http://www.w3.org/2005/Atom"}
            entry = root.find(".//atom:entry", ns)
            if entry is None:
                continue
            vid_id = entry.find("yt:videoId", ns)
            if vid_id is None or vid_id.text == row["last_id"]:
                continue
            title_el = entry.find("atom:title", ns)
            title = title_el.text if title_el is not None else "New Video"
            embed = discord.Embed(
                title="🎥 New YouTube Upload",
                description=f"**{title}**\nhttps://youtu.be/{vid_id.text}",
                color=discord.Color.red()
            )
            embed.set_thumbnail(url=f"https://i.ytimg.com/vi/{vid_id.text}/hqdefault.jpg")
            role_ping = f"<@&{row['role_id']}>" if row["role_id"] else ""
            await ch.send(role_ping, embed=embed)
            cur.execute(
                "UPDATE tracked_channels SET last_id=? WHERE server_id=? AND platform='youtube' AND target=?",
                (vid_id.text, row["server_id"], row["target"])
            )
            db.commit()
        except Exception as e:
            log.error(f"check_youtube: {e}")


@tasks.loop(minutes=2)
async def check_twitch():
    if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
        return
    rows = cur.execute(
        "SELECT server_id, target, last_id, notify_channel, role_id FROM tracked_channels WHERE platform='twitch'"
    ).fetchall()
    if not rows:
        return
    try:
        async with aiohttp.ClientSession() as session:
            token_resp = await session.post(
                "https://id.twitch.tv/oauth2/token",
                params={"client_id": TWITCH_CLIENT_ID, "client_secret": TWITCH_CLIENT_SECRET,
                        "grant_type": "client_credentials"}
            )
            token_data = await token_resp.json()
            oauth = token_data.get("access_token")
            if not oauth:
                return
            headers = {"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {oauth}"}
            for row in rows:
                guild = bot.get_guild(row["server_id"])
                if not guild:
                    continue
                ch = guild.get_channel(row["notify_channel"])
                if not ch:
                    continue
                async with session.get(
                    f"https://api.twitch.tv/helix/streams?user_login={row['target']}",
                    headers=headers
                ) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    streams = data.get("data", [])
                    if not streams:
                        continue
                    stream = streams[0]
                    if stream["id"] == row["last_id"]:
                        continue
                    embed = discord.Embed(
                        title="📡 Live on Twitch",
                        description=f"[{stream['title']}](https://twitch.tv/{row['target']})",
                        color=discord.Color.purple()
                    )
                    embed.add_field(name="Game", value=stream.get("game_name", "—"), inline=True)
                    embed.add_field(name="Viewers", value=stream.get("viewer_count", 0), inline=True)
                    thumb = stream.get("thumbnail_url", "").replace("{width}", "320").replace("{height}", "180")
                    if thumb:
                        embed.set_thumbnail(url=thumb)
                    role_ping = f"<@&{row['role_id']}>" if row["role_id"] else ""
                    await ch.send(role_ping, embed=embed)
                    cur.execute(
                        "UPDATE tracked_channels SET last_id=? WHERE server_id=? AND platform='twitch' AND target=?",
                        (stream["id"], row["server_id"], row["target"])
                    )
                    db.commit()
    except Exception as e:
        log.error(f"check_twitch: {e}")


@tasks.loop(minutes=5)
async def check_twitter():
    if not TWITTER_BEARER:
        return
    rows = cur.execute(
        "SELECT server_id, target, last_id, notify_channel, role_id FROM tracked_channels WHERE platform='twitter'"
    ).fetchall()
    headers = {"Authorization": f"Bearer {TWITTER_BEARER}"}
    async with aiohttp.ClientSession() as session:
        for row in rows:
            guild = bot.get_guild(row["server_id"])
            if not guild:
                continue
            ch = guild.get_channel(row["notify_channel"])
            if not ch:
                continue
            try:
                user_resp = await session.get(
                    f"https://api.twitter.com/2/users/by/username/{quote(row['target'])}",
                    headers=headers
                )
                ud = await user_resp.json()
                uid = ud.get("data", {}).get("id")
                if not uid:
                    continue
                tweets_resp = await session.get(
                    f"https://api.twitter.com/2/users/{uid}/tweets?tweet.fields=created_at&max_results=5",
                    headers=headers
                )
                td = await tweets_resp.json()
                tweets = td.get("data", [])
                if not tweets or tweets[0]["id"] == row["last_id"]:
                    continue
                tweet = tweets[0]
                embed = discord.Embed(
                    title=f"🐦 New tweet from @{row['target']}",
                    description=tweet.get("text", "")[:400],
                    url=f"https://twitter.com/{row['target']}/status/{tweet['id']}",
                    color=discord.Color.blue()
                )
                role_ping = f"<@&{row['role_id']}>" if row["role_id"] else ""
                await ch.send(role_ping, embed=embed)
                cur.execute(
                    "UPDATE tracked_channels SET last_id=? WHERE server_id=? AND platform='twitter' AND target=?",
                    (tweet["id"], row["server_id"], row["target"])
                )
                db.commit()
            except Exception as e:
                log.error(f"check_twitter: {e}")
            await asyncio.sleep(1)


# ─────────────────────────── SLASH COMMANDS ───────────────────

# ── Permissions helpers ──

def admin_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild and interaction.user.guild_permissions.administrator:
            return True
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return False
    return app_commands.check(predicate)

def mod_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild and interaction.user.guild_permissions.manage_messages:
            return True
        await interaction.response.send_message("❌ Manage Messages permission required.", ephemeral=True)
        return False
    return app_commands.check(predicate)


# ─── HELP ─────────────────────────────────────────────────────

@bot.tree.command(name="help", description="Show all available commands")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="⚡ XULT — Command Reference",
        description="All commands use `/`. Use the dashboard for advanced configuration.",
        color=discord.Color.red()
    )
    fields = {
        "💰 Economy": "`/balance` `/daily` `/coinflip` `/rps` `/slots` `/blackjack` `/leaderboard`",
        "🎲 Fun": "`/joke` `/eightball` `/riddle` `/gif` `/meme` `/hug` `/slap` `/say`",
        "🔑 Key Generator": "`/gen` `/addkeys` `/deletekeys` `/keylist` `/setgenaccess`",
        "🛡️ Moderation": "`/jail` `/unjail` `/warn` `/warnings` `/clearwarns` `/purge` `/setroleonjoin`",
        "📢 Notifications": "`/addyoutube` `/addtwitch` `/addtwitter` `/setnotichannel`",
        "⚙️ Server Setup": "`/setlogs` `/setlogchannels` `/reactionrole` `/setupverification`",
        "📋 Misc": "`/sendnotice` `/report` `/setreportchannel` `/save_server` `/load_server`",
    }
    for name, value in fields.items():
        embed.add_field(name=name, value=value, inline=False)
    embed.set_footer(text="Dashboard: configure everything visually at your Vercel URL")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ─── ECONOMY ──────────────────────────────────────────────────

@bot.tree.command(name="balance", description="Check your coins and level")
async def balance(interaction: discord.Interaction):
    ensure_user(interaction.user.id)
    row = cur.execute("SELECT coins, xp, level FROM users WHERE id=?", (interaction.user.id,)).fetchone()
    cur.execute("UPDATE users SET username=? WHERE id=?", (str(interaction.user), interaction.user.id))
    db.commit()
    embed = discord.Embed(title=f"💰 {interaction.user.display_name}", color=discord.Color.gold())
    embed.add_field(name="Coins", value=f"{row['coins']:,}", inline=True)
    embed.add_field(name="XP", value=f"{row['xp']:,}", inline=True)
    embed.add_field(name="Level", value=row["level"], inline=True)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="daily", description="Claim your daily coins (24h cooldown)")
async def daily(interaction: discord.Interaction):
    ensure_user(interaction.user.id)
    row = cur.execute("SELECT last_daily FROM users WHERE id=?", (interaction.user.id,)).fetchone()
    if row["last_daily"]:
        last = datetime.fromisoformat(row["last_daily"])
        if datetime.utcnow() - last < timedelta(hours=24):
            remaining = timedelta(hours=24) - (datetime.utcnow() - last)
            h, m = divmod(int(remaining.total_seconds()) // 60, 60)
            await interaction.response.send_message(
                f"⏳ Daily available in **{h}h {m}m**.", ephemeral=True)
            return
    reward = random.randint(50, 200)
    add_coins(interaction.user.id, reward)
    cur.execute("UPDATE users SET last_daily=? WHERE id=?",
                (datetime.utcnow().isoformat(), interaction.user.id))
    db.commit()
    embed = discord.Embed(
        title="📅 Daily Reward",
        description=f"You claimed **{reward} coins**! Come back in 24 hours.",
        color=discord.Color.gold()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="coinflip", description="Flip a coin for 10 coins")
@app_commands.describe(guess="heads or tails")
@app_commands.choices(guess=[
    app_commands.Choice(name="Heads", value="heads"),
    app_commands.Choice(name="Tails", value="tails"),
])
async def coinflip(interaction: discord.Interaction, guess: app_commands.Choice[str]):
    result = random.choice(["heads", "tails"])
    won = guess.value == result
    if won:
        add_coins(interaction.user.id, 10)
    embed = discord.Embed(
        title="🎉 Correct!" if won else "❌ Wrong!",
        description=f"You guessed **{guess.name}** — it landed **{result}**." + (" +10 coins!" if won else ""),
        color=discord.Color.green() if won else discord.Color.red()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="rps", description="Rock, paper, scissors for 10 coins")
@app_commands.choices(choice=[
    app_commands.Choice(name="Rock", value="rock"),
    app_commands.Choice(name="Paper", value="paper"),
    app_commands.Choice(name="Scissors", value="scissors"),
])
async def rps(interaction: discord.Interaction, choice: app_commands.Choice[str]):
    bot_choice = random.choice(["rock", "paper", "scissors"])
    wins = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
    if choice.value == bot_choice:
        result, color = "🤝 Tie!", discord.Color.blue()
    elif wins[choice.value] == bot_choice:
        add_coins(interaction.user.id, 10)
        result, color = "🎉 You win! +10 coins", discord.Color.green()
    else:
        result, color = "😢 You lose!", discord.Color.red()
    embed = discord.Embed(title=result,
                          description=f"You: **{choice.name}** | Bot: **{bot_choice}**",
                          color=color)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="slots", description="Play the slot machine")
async def slots(interaction: discord.Interaction):
    cost = 20
    bal = get_balance(interaction.user.id)
    if bal < cost:
        await interaction.response.send_message(f"❌ Need {cost} coins to play (you have {bal}).", ephemeral=True)
        return
    add_coins(interaction.user.id, -cost)
    icons = ["🍒", "🍋", "🔔", "⭐", "💎", "7️⃣"]
    reels = [random.choice(icons) for _ in range(3)]
    unique = len(set(reels))
    if unique == 1:  # jackpot
        winnings = 500
        msg = "🎰 JACKPOT! +500 coins!"
    elif unique == 2:  # two match
        winnings = 50
        msg = "🎰 Two in a row! +50 coins!"
    else:
        winnings = 0
        msg = "🎰 No match. Try again!"
    if winnings:
        add_coins(interaction.user.id, winnings)
    embed = discord.Embed(
        title="🎰 Slot Machine",
        description=f"| {' | '.join(reels)} |\n\n{msg}",
        color=discord.Color.gold() if winnings else discord.Color.dark_gray()
    )
    embed.set_footer(text=f"Balance: {get_balance(interaction.user.id):,} coins")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="blackjack", description="Play blackjack for coins")
@app_commands.describe(bet="How many coins to bet")
async def blackjack(interaction: discord.Interaction, bet: int):
    if bet <= 0:
        await interaction.response.send_message("❌ Bet must be positive.", ephemeral=True)
        return
    if get_balance(interaction.user.id) < bet:
        await interaction.response.send_message("❌ Insufficient coins.", ephemeral=True)
        return
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
        dealer.append(deck.pop())
        dv = hand_value(dealer)

    if pv > 21:
        add_coins(interaction.user.id, -bet)
        result = f"❌ Bust! You lost **{bet}** coins."
    elif dv > 21 or pv > dv:
        add_coins(interaction.user.id, bet)
        result = f"🎉 You win! +**{bet}** coins."
    elif pv == dv:
        result = "🤝 Push — coins returned."
    else:
        add_coins(interaction.user.id, -bet)
        result = f"😢 Dealer wins. You lost **{bet}** coins."

    embed = discord.Embed(title="🃏 Blackjack", color=discord.Color.green())
    embed.add_field(name="Your hand", value=f"{player} = **{pv}**", inline=True)
    embed.add_field(name="Dealer", value=f"{dealer} = **{dv}**", inline=True)
    embed.add_field(name="Result", value=result, inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="leaderboard", description="Top 10 richest users")
async def leaderboard(interaction: discord.Interaction):
    rows = cur.execute("SELECT username, coins FROM users ORDER BY coins DESC LIMIT 10").fetchall()
    embed = discord.Embed(title="🏆 Coin Leaderboard", color=discord.Color.gold())
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, row in enumerate(rows, 1):
        prefix = medals[i-1] if i <= 3 else f"**{i}.**"
        lines.append(f"{prefix} {row['username'] or 'Unknown'} — **{row['coins']:,}** coins")
    embed.description = "\n".join(lines) if lines else "No data yet."
    await interaction.response.send_message(embed=embed)


# ─── FUN ──────────────────────────────────────────────────────

RIDDLES = [
    ("What has keys but can't open locks?", "keyboard"),
    ("What runs but never walks?", "water"),
    ("What has hands but cannot clap?", "clock"),
    ("What can you catch but not throw?", "cold"),
    ("What has a face and two hands but no arms?", "clock"),
    ("What gets wetter as it dries?", "towel"),
    ("What has cities but no houses?", "map"),
    ("What has to be broken before you can use it?", "egg"),
    ("What is always coming but never arrives?", "tomorrow"),
    ("What has a head and a tail but no body?", "coin"),
    ("What has teeth but cannot bite?", "comb"),
    ("What is so fragile that saying its name breaks it?", "silence"),
    ("What belongs to you but others use it more than you?", "name"),
    ("What has words but never speaks?", "book"),
]
_active_riddle: dict = {}


@bot.tree.command(name="riddle", description="Answer a riddle for 50 coins")
async def riddle(interaction: discord.Interaction):
    key = interaction.channel_id
    if key in _active_riddle:
        await interaction.response.send_message("A riddle is already active in this channel!", ephemeral=True)
        return
    question, answer = random.choice(RIDDLES)
    _active_riddle[key] = answer
    await interaction.response.send_message(f"🧩 **Riddle:** {question}\n\nType your answer in chat (30 seconds)!")

    def check(m):
        return (m.channel.id == interaction.channel_id
                and not m.author.bot
                and m.content.strip().lower() == answer.lower())

    try:
        msg = await bot.wait_for("message", timeout=30.0, check=check)
        add_coins(msg.author.id, 50)
        await msg.reply(f"✅ Correct! **{msg.author.display_name}** earned **50 coins**!")
    except asyncio.TimeoutError:
        await interaction.channel.send(f"⏰ Time's up! The answer was **{answer}**.")
    finally:
        _active_riddle.pop(key, None)


@bot.tree.command(name="joke", description="Get a random joke")
async def joke(interaction: discord.Interaction):
    async with aiohttp.ClientSession() as s:
        async with s.get("https://official-joke-api.appspot.com/jokes/random") as r:
            data = await r.json()
    embed = discord.Embed(description=f"**{data['setup']}**\n\n{data['punchline']}", color=discord.Color.orange())
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="eightball", description="Ask the magic 8-ball")
@app_commands.describe(question="Your question")
async def eightball(interaction: discord.Interaction, question: str):
    responses = ["Yes", "No", "Maybe", "Definitely", "Absolutely not",
                 "Ask again later", "It is certain", "Very doubtful",
                 "Without a doubt", "Don't count on it"]
    embed = discord.Embed(
        title=f"🎱 {question[:100]}",
        description=f"**{random.choice(responses)}**",
        color=discord.Color.dark_blue()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="gif", description="Search GIPHY for a GIF")
@app_commands.describe(search="Search term")
async def gif(interaction: discord.Interaction, search: str):
    if not GIPHY_API_KEY:
        await interaction.response.send_message("GIPHY API key not configured.", ephemeral=True)
        return
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://api.giphy.com/v1/gifs/search?api_key={GIPHY_API_KEY}&q={search}&limit=5&rating=pg") as r:
            data = await r.json()
    items = data.get("data", [])
    if not items:
        await interaction.response.send_message("No GIF found.", ephemeral=True)
        return
    choice = random.choice(items)
    embed = discord.Embed(title=f"🎬 {search}", color=discord.Color.blue())
    embed.set_image(url=choice["images"]["original"]["url"])
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="meme", description="Get a random meme")
async def meme(interaction: discord.Interaction):
    async with aiohttp.ClientSession() as s:
        async with s.get("https://meme-api.com/gimme") as r:
            data = await r.json()
    embed = discord.Embed(title=data.get("title", "Meme")[:100], color=discord.Color.orange())
    embed.set_image(url=data.get("url", ""))
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="hug", description="Hug someone")
@app_commands.describe(member="Who to hug")
async def hug(interaction: discord.Interaction, member: discord.Member):
    embed = discord.Embed(description=f"{interaction.user.mention} hugs {member.mention} 🤗", color=discord.Color.pink())
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="slap", description="Slap someone")
@app_commands.describe(member="Who to slap")
async def slap(interaction: discord.Interaction, member: discord.Member):
    embed = discord.Embed(description=f"{interaction.user.mention} slapped {member.mention} 👋", color=discord.Color.red())
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="say", description="Have the bot repeat something")
@app_commands.describe(text="What to say")
async def say(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(text[:2000])


# ─── KEY GENERATOR ────────────────────────────────────────────

@bot.tree.command(name="keylist", description="Show available key types and counts")
async def keylist(interaction: discord.Interaction):
    types = list(KEYS_DIR.glob("*.txt"))
    embed = discord.Embed(title="🔑 Available Keys", color=discord.Color.blue())
    if not types:
        embed.description = "No key types configured."
    else:
        for f in types:
            count = count_keys(f.stem)
            embed.add_field(name=f.stem.replace("_", " ").title(), value=f"`{count}` available", inline=True)
    embed.set_footer(text="Use /gen <type> to get a key")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="gen", description="Generate a key or code")
@app_commands.describe(key_type="Type of key to generate")
async def gen(interaction: discord.Interaction, key_type: str):
    if not interaction.guild:
        await interaction.response.send_message("Use this command in a server.", ephemeral=True)
        return

    gen_access = load_json(JSON_FILES["gen_access"]).get(str(interaction.guild.id), [])
    if gen_access and not any(r.id in gen_access for r in interaction.user.roles):
        await interaction.response.send_message("❌ You don't have access to /gen.", ephemeral=True)
        return

    on_cd, remaining = is_on_cooldown(interaction.user.id)
    if on_cd:
        await interaction.response.send_message(f"⏳ Wait **{remaining}s** before using /gen again.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    key = pop_key(key_type)
    if key is None:
        await interaction.followup.send(f"❌ No keys available for **{key_type}**.", ephemeral=True)
        return

    set_cooldown(interaction.user.id)

    try:
        await interaction.user.send(f"🔑 Here's your **{key_type}** key:\n```\n{key}\n```")
        await interaction.followup.send("📩 Key sent to your DMs!", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send(f"```\n{key}\n```", ephemeral=True)

    # Log usage
    cur.execute("""INSERT INTO key_usage
        (user_id, username, key_type, key_content, used_at, server_id, server_name, channel_name, is_dm)
        VALUES (?,?,?,?,?,?,?,?,0)""",
        (interaction.user.id, str(interaction.user), key_type, key, datetime.utcnow().isoformat(),
         interaction.guild.id, interaction.guild.name, interaction.channel.name))
    db.commit()
    log_action(interaction.user.id, "GEN", f"type={key_type} guild={interaction.guild.id}")

    # Forward to log channel
    target = bot.get_guild(TARGET_SERVER_ID)
    if target:
        lch = target.get_channel(GEN_LOG_CHANNEL)
        if lch:
            embed = discord.Embed(title="🔑 Key Generated", color=discord.Color.blue())
            embed.add_field(name="User", value=f"{interaction.user} ({interaction.user.id})", inline=False)
            embed.add_field(name="Type", value=key_type, inline=True)
            embed.add_field(name="Server", value=interaction.guild.name, inline=True)
            await lch.send(embed=embed)


@bot.tree.command(name="addkeys", description="Add keys/codes from a text file (one per line)")
@app_commands.describe(key_type="Type name", file="Text file with keys (one per line)")
@admin_only()
async def addkeys(interaction: discord.Interaction, key_type: str, file: discord.Attachment = None):
    if not file or not file.filename.endswith(".txt"):
        await interaction.response.send_message("Upload a .txt file with one key per line.", ephemeral=True)
        return
    content = (await file.read()).decode("utf-8", errors="ignore")
    new_keys = [l.strip() for l in content.splitlines() if l.strip()]
    if not new_keys:
        await interaction.response.send_message("File is empty.", ephemeral=True)
        return
    append_keys(key_type, new_keys)
    await interaction.response.send_message(f"✅ Added **{len(new_keys)}** keys to **{key_type}**.", ephemeral=True)
    log_action(interaction.user.id, "ADDKEYS", f"type={key_type} count={len(new_keys)}")


@bot.tree.command(name="deletekeys", description="Delete a key type and all its keys")
@app_commands.describe(key_type="Type to delete")
@admin_only()
async def deletekeys(interaction: discord.Interaction, key_type: str):
    f = key_file(key_type)
    if not f.exists():
        await interaction.response.send_message("Key type not found.", ephemeral=True)
        return
    f.unlink()
    await interaction.response.send_message(f"✅ Deleted **{key_type}** keys.", ephemeral=True)


@bot.tree.command(name="setgenaccess", description="Set roles that can use /gen")
@app_commands.describe(role="Role to allow")
@admin_only()
async def setgenaccess(interaction: discord.Interaction, role: discord.Role):
    data = load_json(JSON_FILES["gen_access"])
    gid = str(interaction.guild.id)
    data.setdefault(gid, [])
    if role.id not in data[gid]:
        data[gid].append(role.id)
        save_json(JSON_FILES["gen_access"], data)
    await interaction.response.send_message(f"✅ {role.mention} can now use `/gen`.")


# ─── MODERATION ───────────────────────────────────────────────

@bot.tree.command(name="warn", description="Warn a member")
@app_commands.describe(member="Member to warn", reason="Reason")
@mod_only()
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    cur.execute("INSERT INTO warnings (user_id, moderator_id, reason, timestamp, server_id) VALUES (?,?,?,?,?)",
                (member.id, interaction.user.id, reason, datetime.utcnow().isoformat(), interaction.guild.id))
    db.commit()
    count = cur.execute("SELECT COUNT(*) FROM warnings WHERE user_id=? AND server_id=?",
                        (member.id, interaction.guild.id)).fetchone()[0]
    embed = discord.Embed(
        title="⚠️ Warning Issued",
        description=f"{member.mention} warned. Total: **{count}/3**. Reason: {reason}",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed)
    try:
        await member.send(f"⚠️ You were warned in **{interaction.guild.name}**: {reason}")
    except discord.Forbidden:
        pass
    if count >= 3:
        try:
            await member.timeout(discord.utils.utcnow() + timedelta(minutes=10),
                                 reason=f"3 warnings accumulated")
        except discord.Forbidden:
            pass


@bot.tree.command(name="warnings", description="View warnings for a member")
@app_commands.describe(member="Member to check")
async def warnings_cmd(interaction: discord.Interaction, member: discord.Member):
    rows = cur.execute(
        "SELECT reason, timestamp, moderator_id FROM warnings WHERE user_id=? AND server_id=? ORDER BY timestamp DESC",
        (member.id, interaction.guild.id)
    ).fetchall()
    embed = discord.Embed(title=f"⚠️ Warnings — {member.display_name}", color=discord.Color.orange())
    if not rows:
        embed.description = "No warnings."
    else:
        embed.description = f"**{len(rows)} warning(s)**"
        for i, row in enumerate(rows[:5], 1):
            mod = interaction.guild.get_member(row["moderator_id"])
            embed.add_field(
                name=f"#{i}",
                value=f"**{row['reason']}**\nBy: {mod.mention if mod else row['moderator_id']} • {row['timestamp'][:10]}",
                inline=False
            )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="clearwarns", description="Clear all warnings for a member")
@app_commands.describe(member="Member")
@mod_only()
async def clearwarns(interaction: discord.Interaction, member: discord.Member):
    cur.execute("DELETE FROM warnings WHERE user_id=? AND server_id=?", (member.id, interaction.guild.id))
    db.commit()
    await interaction.response.send_message(f"✅ Warnings cleared for {member.mention}.")


@bot.tree.command(name="jail", description="Jail a member (restricts all channels)")
@app_commands.describe(member="Member to jail", duration="Duration e.g. 30m 2h 1d", reason="Reason")
@admin_only()
async def jail(interaction: discord.Interaction, member: discord.Member,
               duration: str = "10m", reason: str = "No reason provided"):
    await interaction.response.defer()
    try:
        initial_roles = [r for r in member.roles if r != interaction.guild.default_role]
        await member.remove_roles(*initial_roles, reason="Jailed")
        for ch in interaction.guild.text_channels + interaction.guild.voice_channels:
            await ch.set_permissions(member, read_messages=False, send_messages=False,
                                     connect=False, speak=False)
        cur.execute("""INSERT OR REPLACE INTO jailed_members
            (server_id, user_id, roles, jail_time, duration, reason, jailed_by) VALUES (?,?,?,?,?,?,?)""",
            (interaction.guild.id, member.id, json.dumps([r.id for r in initial_roles]),
             datetime.utcnow().isoformat(), duration, reason, interaction.user.id))
        db.commit()
        await interaction.followup.send(
            f"🔒 {member.mention} jailed for **{duration}**. Reason: {reason}")
        try:
            await member.send(f"🔒 You have been jailed in **{interaction.guild.name}** for **{duration}**.\nReason: {reason}")
        except discord.Forbidden:
            pass
        log_action(interaction.user.id, "JAIL", f"target={member.id} duration={duration}")
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


@bot.tree.command(name="unjail", description="Unjail a member")
@app_commands.describe(member="Member to unjail")
@admin_only()
async def unjail(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer()
    row = cur.execute("SELECT roles FROM jailed_members WHERE server_id=? AND user_id=?",
                      (interaction.guild.id, member.id)).fetchone()
    if not row:
        await interaction.followup.send(f"{member.mention} is not jailed.")
        return
    roles = [interaction.guild.get_role(r) for r in json.loads(row["roles"])]
    roles = [r for r in roles if r]
    if roles:
        await member.add_roles(*roles, reason="Unjailed")
    for ch in interaction.guild.text_channels + interaction.guild.voice_channels:
        await ch.set_permissions(member, overwrite=None)
    cur.execute("DELETE FROM jailed_members WHERE server_id=? AND user_id=?",
                (interaction.guild.id, member.id))
    db.commit()
    await interaction.followup.send(f"✅ {member.mention} has been unjailed.")
    try:
        await member.send(f"✅ You have been unjailed from **{interaction.guild.name}**.")
    except discord.Forbidden:
        pass


@bot.tree.command(name="purge", description="Delete messages from a channel")
@app_commands.describe(amount="Number of messages (1-100)")
@mod_only()
async def purge(interaction: discord.Interaction, amount: int = 10):
    if not 1 <= amount <= 100:
        await interaction.response.send_message("Amount must be 1-100.", ephemeral=True)
        return
    await interaction.response.send_message(f"⏳ Purging {amount} messages…", ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"✅ Deleted {len(deleted)} messages.", ephemeral=True)


@bot.tree.command(name="setroleonjoin", description="Assign a role to new members after a delay")
@app_commands.describe(role="Role to assign", delay="Delay e.g. 10m 1h")
@admin_only()
async def setroleonjoin(interaction: discord.Interaction, role: discord.Role, delay: str = "0s"):
    try:
        secs = int(parse_duration(delay).total_seconds())
    except ValueError as e:
        await interaction.response.send_message(str(e), ephemeral=True)
        return
    cur.execute("INSERT OR REPLACE INTO role_on_join (server_id, role_id, delay) VALUES (?,?,?)",
                (interaction.guild.id, role.id, secs))
    db.commit()
    await interaction.response.send_message(
        f"✅ New members will receive {role.mention} after **{delay}**.", ephemeral=True)


# ─── SERVER SETUP ─────────────────────────────────────────────

@bot.tree.command(name="setlogs", description="Set the moderation log channel")
@app_commands.describe(channel="Log channel")
@admin_only()
async def setlogs(interaction: discord.Interaction, channel: discord.TextChannel):
    cur.execute("INSERT OR REPLACE INTO server_configs (server_id, log_channel) VALUES (?,?)",
                (interaction.guild.id, channel.id))
    db.commit()
    await interaction.response.send_message(f"✅ Log channel set to {channel.mention}.", ephemeral=True)


@bot.tree.command(name="setlogchannels", description="Set granular log channels for different events")
@app_commands.describe(
    member_ch="Member join/leave", chat_ch="Message edit/delete",
    voice_ch="Voice state", mod_ch="Moderation actions",
    server_ch="Server changes", bot_ch="Bot announcements"
)
@admin_only()
async def setlogchannels(
    interaction: discord.Interaction,
    member_ch: discord.TextChannel, chat_ch: discord.TextChannel,
    voice_ch: discord.TextChannel, mod_ch: discord.TextChannel,
    server_ch: discord.TextChannel, bot_ch: discord.TextChannel
):
    data = load_json(JSON_FILES["log_channels"])
    data[str(interaction.guild.id)] = {
        "member": member_ch.id, "chat": chat_ch.id, "voice": voice_ch.id,
        "mod": mod_ch.id, "server": server_ch.id, "bot_update": bot_ch.id
    }
    save_json(JSON_FILES["log_channels"], data)
    await interaction.response.send_message("✅ Log channels configured.", ephemeral=True)


@bot.tree.command(name="reactionrole", description="Create a role selection dropdown")
@app_commands.describe(roles="Comma-separated role names")
@admin_only()
async def reactionrole(interaction: discord.Interaction, roles: str):
    role_names = [r.strip() for r in roles.split(",")]
    found = [r for r in interaction.guild.roles if r.name in role_names]
    if not found:
        await interaction.response.send_message("No matching roles found.", ephemeral=True)
        return
    embed = discord.Embed(title="🎭 Role Selection", description="Pick a role from the dropdown below.",
                          color=discord.Color.blue())
    await interaction.response.send_message(embed=embed, view=RoleSelectView(found))


@bot.tree.command(name="setupverification", description="Configure the verification system")
@app_commands.describe(verify_channel="Where the verify button goes",
                       verified_role="Role given after verification",
                       log_channel="Where verification events are logged")
@admin_only()
async def setupverification(
    interaction: discord.Interaction,
    verify_channel: discord.TextChannel,
    verified_role: discord.Role,
    log_channel: discord.TextChannel
):
    cur.execute("INSERT OR REPLACE INTO verification (server_id, channel_id, role_id, log_channel_id) VALUES (?,?,?,?)",
                (interaction.guild.id, verify_channel.id, verified_role.id, log_channel.id))
    db.commit()
    embed = discord.Embed(title="🔒 Verify to get access",
                          description="Click the button below to verify yourself.",
                          color=discord.Color.green())
    await verify_channel.send(embed=embed, view=VerifyButton())
    await interaction.response.send_message("✅ Verification system set up.", ephemeral=True)


@bot.tree.command(name="setreportchannel", description="Set the channel for user reports")
@app_commands.describe(channel="Reports channel", role="Moderator role to ping")
@admin_only()
async def setreportchannel(interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role):
    cur.execute("INSERT OR REPLACE INTO report_channels (server_id, channel_id, role_id) VALUES (?,?,?)",
                (interaction.guild.id, channel.id, role.id))
    db.commit()
    await interaction.response.send_message(f"✅ Reports → {channel.mention} | Ping: {role.mention}", ephemeral=True)


@bot.tree.command(name="report", description="Report a user or issue to moderators")
@app_commands.describe(issue="What happened", user="User you're reporting (optional)")
async def report(interaction: discord.Interaction, issue: str, user: discord.Member = None):
    row = cur.execute("SELECT channel_id, role_id FROM report_channels WHERE server_id=?",
                      (interaction.guild.id,)).fetchone()
    if not row:
        await interaction.response.send_message("No report channel configured.", ephemeral=True)
        return
    ch = bot.get_channel(row["channel_id"])
    if not ch:
        await interaction.response.send_message("Report channel not found.", ephemeral=True)
        return
    embed = discord.Embed(title="🚨 New Report", color=discord.Color.red(), timestamp=discord.utils.utcnow())
    embed.add_field(name="Reporter", value=interaction.user.mention, inline=True)
    if user:
        embed.add_field(name="Reported User", value=user.mention, inline=True)
    embed.add_field(name="Issue", value=issue[:1024], inline=False)
    await ch.send(f"<@&{row['role_id']}>", embed=embed)
    await interaction.response.send_message("✅ Report submitted.", ephemeral=True)


@bot.tree.command(name="sendnotice", description="Send an announcement embed")
@app_commands.describe(title="Embed title", message="Embed body",
                       channel="Target channel", ping_role="Role to ping")
@mod_only()
async def sendnotice(
    interaction: discord.Interaction, title: str, message: str,
    channel: discord.TextChannel = None, ping_role: discord.Role = None
):
    embed = discord.Embed(title=title, description=message, color=discord.Color.red())
    embed.set_footer(text=f"Sent by {interaction.user.display_name}")
    target = channel or interaction.channel
    ping = ping_role.mention if ping_role else ""
    await target.send(ping, embed=embed)
    await interaction.response.send_message(f"✅ Notice sent to {target.mention}.", ephemeral=True)


@bot.tree.command(name="save_server", description="Save a backup of this server's structure")
@admin_only()
async def save_server(interaction: discord.Interaction):
    save_server_backup(interaction.guild)
    await interaction.response.send_message("✅ Server backup saved.", ephemeral=True)


@bot.tree.command(name="load_server", description="Restore server structure from backup")
@admin_only()
async def load_server(interaction: discord.Interaction):
    path = BACKUP_DIR / f"{interaction.guild.id}.json"
    if not path.exists():
        await interaction.response.send_message("No backup found.", ephemeral=True)
        return
    await interaction.response.send_message("⏳ Restoring… this may take a while.", ephemeral=True)


# ─── NOTIFICATIONS ────────────────────────────────────────────

@bot.tree.command(name="setnotichannel", description="Set the channel for media notifications")
@app_commands.describe(channel="Notification channel", role="Role to ping")
@admin_only()
async def setnotichannel(interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role = None):
    data = load_json(JSON_FILES["server_settings"])
    data[str(interaction.guild.id)] = {
        "notification_channel_id": channel.id,
        "notification_role_id": role.id if role else None
    }
    save_json(JSON_FILES["server_settings"], data)
    await interaction.response.send_message(
        f"✅ Notifications → {channel.mention}" + (f" | Ping: {role.mention}" if role else ""), ephemeral=True)


@bot.tree.command(name="addyoutube", description="Track a YouTube channel")
@app_commands.describe(channel_id="YouTube channel ID (UCxxxxxx)", notify_channel="Where to post",
                       role="Role to ping")
@admin_only()
async def addyoutube(interaction: discord.Interaction, channel_id: str,
                     notify_channel: discord.TextChannel, role: discord.Role = None):
    cur.execute("""INSERT OR REPLACE INTO tracked_channels
        (server_id, platform, target, notify_channel, role_id) VALUES (?,?,?,?,?)""",
        (interaction.guild.id, "youtube", channel_id, notify_channel.id, role.id if role else None))
    db.commit()
    await interaction.response.send_message(f"✅ Tracking YouTube `{channel_id}` → {notify_channel.mention}", ephemeral=True)


@bot.tree.command(name="addtwitch", description="Track a Twitch streamer")
@app_commands.describe(username="Twitch username", notify_channel="Where to post", role="Role to ping")
@admin_only()
async def addtwitch(interaction: discord.Interaction, username: str,
                    notify_channel: discord.TextChannel, role: discord.Role = None):
    cur.execute("""INSERT OR REPLACE INTO tracked_channels
        (server_id, platform, target, notify_channel, role_id) VALUES (?,?,?,?,?)""",
        (interaction.guild.id, "twitch", username.lower(), notify_channel.id, role.id if role else None))
    db.commit()
    await interaction.response.send_message(f"✅ Tracking Twitch `{username}` → {notify_channel.mention}", ephemeral=True)


@bot.tree.command(name="addtwitter", description="Track a Twitter/X account")
@app_commands.describe(username="Twitter username (no @)", notify_channel="Where to post", role="Role to ping")
@admin_only()
async def addtwitter(interaction: discord.Interaction, username: str,
                     notify_channel: discord.TextChannel, role: discord.Role = None):
    cur.execute("""INSERT OR REPLACE INTO tracked_channels
        (server_id, platform, target, notify_channel, role_id) VALUES (?,?,?,?,?)""",
        (interaction.guild.id, "twitter", username.lower().lstrip("@"),
         notify_channel.id, role.id if role else None))
    db.commit()
    await interaction.response.send_message(f"✅ Tracking Twitter `@{username}` → {notify_channel.mention}", ephemeral=True)


# ─── 4:20 ─────────────────────────────────────────────────────

@bot.tree.command(name="set420", description="Configure 4:20 announcements")
@app_commands.describe(channel="Announcement channel", timezone="Timezone e.g. America/New_York",
                       role="Role to ping", voice_channel="Voice channel link")
@admin_only()
async def set420(interaction: discord.Interaction, channel: discord.TextChannel,
                 timezone: str = "UTC", role: discord.Role = None,
                 voice_channel: discord.VoiceChannel = None):
    try:
        pytz.timezone(timezone)
    except Exception:
        await interaction.response.send_message("Invalid timezone.", ephemeral=True)
        return
    cur.execute("""INSERT OR REPLACE INTO four_twenty
        (server_id, channel_id, role_id, voice_channel_id, timezone) VALUES (?,?,?,?,?)""",
        (interaction.guild.id, channel.id, role.id if role else None,
         voice_channel.id if voice_channel else None, timezone))
    db.commit()
    await interaction.response.send_message(
        f"✅ 4:20 set: {channel.mention} | TZ: {timezone}" + (f" | Ping: {role.mention}" if role else ""),
        ephemeral=True)


# ─── OWNER COMMANDS ───────────────────────────────────────────

@bot.tree.command(name="broadcast", description="[Owner] Broadcast a message to all servers")
@app_commands.describe(message="Message to broadcast")
async def broadcast(interaction: discord.Interaction, message: str):
    if interaction.user.id != BOT_OWNER_ID:
        await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    log_channels = load_json(JSON_FILES["log_channels"])
    count = 0
    for gid, channels in log_channels.items():
        guild = bot.get_guild(int(gid))
        if not guild:
            continue
        ch_id = channels.get("bot_update")
        ch = guild.get_channel(int(ch_id)) if ch_id else find_main_chat(guild)
        if ch:
            try:
                embed = discord.Embed(title="📢 XULT Update", description=message, color=discord.Color.red())
                embed.set_footer(text="XULT Bot")
                await ch.send(embed=embed)
                count += 1
            except Exception:
                pass
    await interaction.followup.send(f"✅ Broadcast to {count} servers.", ephemeral=True)


# ─────────────────────────── API SERVER ───────────────────────

def json_resp(data, status=200):
    return web.Response(
        text=json.dumps(data), content_type="application/json", status=status
    )

def require_auth(handler):
    async def wrapper(request):
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {API_KEY}":
            return json_resp({"error": "Unauthorized"}, 401)
        return await handler(request)
    return wrapper

async def cors_mw(app, handler):
    async def middleware(request):
        if request.method == "OPTIONS":
            r = web.Response()
            r.headers.update({
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type,Authorization",
            })
            return r
        resp = await handler(request)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp
    return middleware

# Public
async def h_health(req): return json_resp({"status": "ok", "uptime": str(datetime.utcnow() - bot.start_time)})
async def h_key(req): return json_resp({"key": API_KEY})

# Stats
@require_auth
async def h_stats(req):
    users = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    premium = cur.execute("SELECT COUNT(*) FROM premium_users WHERE is_active=1").fetchone()[0]
    cmds_today = cur.execute(
        "SELECT COUNT(*) FROM key_usage WHERE used_at > datetime('now','-1 day')"
    ).fetchone()[0]
    activity = []
    for i in range(6, -1, -1):
        d = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        n = cur.execute("SELECT COUNT(*) FROM key_usage WHERE date(used_at)=?", (d,)).fetchone()[0]
        activity.append(n)
    recent = []
    for row in cur.execute(
        "SELECT user_id, username, key_type, used_at FROM key_usage ORDER BY used_at DESC LIMIT 10"
    ).fetchall():
        recent.append({"userId": row["user_id"], "username": row["username"] or f"User-{row['user_id']}",
                       "type": row["key_type"], "time": (row["used_at"] or "")[:19]})
    return json_resp({
        "total_users": users, "total_servers": len(bot.guilds),
        "total_commands": cmds_today, "premium_users": premium,
        "activity": activity, "recent": recent,
        "latency": round(bot.latency * 1000, 2),
        "uptime": str(datetime.utcnow() - bot.start_time).split(".")[0]
    })

@require_auth
async def h_stock(req):
    data = {}
    for f in KEYS_DIR.glob("*.txt"):
        data[f.stem] = {"count": count_keys(f.stem), "name": f.stem.replace("_", " ").title()}
    return json_resp(data)

@require_auth
async def h_servers(req):
    return json_resp([{
        "id": str(g.id), "name": g.name,
        "icon": str(g.icon.url) if g.icon else None,
        "memberCount": g.member_count, "ownerId": str(g.owner_id)
    } for g in bot.guilds])

@require_auth
async def h_server_config(req):
    sid = int(req.match_info["server_id"])
    cfg = get_server_config(sid)
    gen = load_json(JSON_FILES["gen_access"]).get(str(sid), [])
    au = load_json(JSON_FILES["log_channels"]).get(str(sid), {})
    tracked = {}
    for r in cur.execute("SELECT platform, target, role_id FROM tracked_channels WHERE server_id=?", (sid,)).fetchall():
        tracked.setdefault(r["platform"], []).append({"channel": r["target"], "role": r["role_id"]})
    return json_resp({"server_id": sid, "config": cfg, "gen_access": gen, "logs": au, "tracked": tracked})

@require_auth
async def h_update_gen_access(req):
    sid = req.match_info["server_id"]
    body = await req.json()
    data = load_json(JSON_FILES["gen_access"])
    data[sid] = body.get("roles", [])
    save_json(JSON_FILES["gen_access"], data)
    return json_resp({"ok": True})

@require_auth
async def h_update_logs(req):
    sid = req.match_info["server_id"]
    body = await req.json()
    data = load_json(JSON_FILES["log_channels"])
    data[sid] = body
    save_json(JSON_FILES["log_channels"], data)
    return json_resp({"ok": True})

@require_auth
async def h_owner_users(req):
    rows = cur.execute("SELECT id, username, coins, xp, level, banned FROM users ORDER BY coins DESC").fetchall()
    out = []
    for row in rows:
        prem = cur.execute("SELECT is_active FROM premium_users WHERE user_id=?", (row["id"],)).fetchone()
        warns = cur.execute("SELECT COUNT(*) FROM warnings WHERE user_id=?", (row["id"],)).fetchone()[0]
        gens = cur.execute("SELECT COUNT(*) FROM key_usage WHERE user_id=?", (row["id"],)).fetchone()[0]
        out.append({
            "id": row["id"], "username": row["username"] or f"User-{row['id']}",
            "coins": row["coins"], "xp": row["xp"], "level": row["level"],
            "banned": bool(row["banned"]), "premium": bool(prem and prem["is_active"]),
            "warnings": warns, "generations": gens
        })
    return json_resp(out)

@require_auth
async def h_owner_logs(req):
    rows = cur.execute("SELECT user_id, action, details, timestamp FROM logs ORDER BY timestamp DESC LIMIT 100").fetchall()
    return json_resp([{"userId": r["user_id"], "action": r["action"], "details": r["details"], "time": r["timestamp"]} for r in rows])

@require_auth
async def h_owner_stock_usage(req):
    rows = cur.execute(
        "SELECT user_id, username, key_type, key_content, used_at, server_name, channel_name, is_dm FROM key_usage ORDER BY used_at DESC LIMIT 100"
    ).fetchall()
    return json_resp([{
        "userId": r["user_id"], "username": r["username"] or f"User-{r['user_id']}",
        "type": r["key_type"], "content": (r["key_content"] or "")[:30] + "…",
        "time": r["used_at"], "server": r["server_name"], "is_dm": bool(r["is_dm"])
    } for r in rows])

@require_auth
async def h_user_premium(req):
    uid = int(req.match_info["user_id"])
    body = await req.json()
    action = body.get("action", "toggle")
    if action == "add":
        cur.execute("INSERT OR REPLACE INTO premium_users (user_id, granted_at, is_active) VALUES (?,?,1)",
                    (uid, datetime.utcnow().isoformat()))
    elif action == "remove":
        cur.execute("DELETE FROM premium_users WHERE user_id=?", (uid,))
    else:
        row = cur.execute("SELECT is_active FROM premium_users WHERE user_id=?", (uid,)).fetchone()
        if row:
            cur.execute("UPDATE premium_users SET is_active=? WHERE user_id=?", (1 - row["is_active"], uid))
        else:
            cur.execute("INSERT INTO premium_users (user_id, granted_at, is_active) VALUES (?,?,1)",
                        (uid, datetime.utcnow().isoformat()))
    db.commit()
    return json_resp({"ok": True})

@require_auth
async def h_user_ban(req):
    uid = int(req.match_info["user_id"])
    body = await req.json()
    banned = 1 if body.get("action") == "ban" else 0
    cur.execute("UPDATE users SET banned=? WHERE id=?", (banned, uid))
    db.commit()
    return json_resp({"ok": True})

@require_auth
async def h_user_clear_warns(req):
    uid = int(req.match_info["user_id"])
    cur.execute("DELETE FROM warnings WHERE user_id=?", (uid,))
    db.commit()
    return json_resp({"ok": True})


async def start_api():
    app = web.Application(middlewares=[cors_mw])
    app.router.add_get("/health", h_health)
    app.router.add_get("/api/key", h_key)
    app.router.add_get("/api/stats", h_stats)
    app.router.add_get("/api/stock", h_stock)
    app.router.add_get("/api/user/servers", h_servers)
    app.router.add_get("/api/server/{server_id}/config", h_server_config)
    app.router.add_post("/api/server/{server_id}/gen_access", h_update_gen_access)
    app.router.add_post("/api/server/{server_id}/logs", h_update_logs)
    app.router.add_get("/api/owner/users", h_owner_users)
    app.router.add_get("/api/owner/logs", h_owner_logs)
    app.router.add_get("/api/owner/stock/usage", h_owner_stock_usage)
    app.router.add_post("/api/owner/users/{user_id}/premium", h_user_premium)
    app.router.add_post("/api/owner/users/{user_id}/ban", h_user_ban)
    app.router.add_post("/api/owner/users/{user_id}/warnings/reset", h_user_clear_warns)

    port = API_PORT
    for _ in range(10):
        try:
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", port)
            await site.start()
            log.info(f"API server listening on :{port}")
            return
        except OSError:
            port += 1
    log.error("Could not start API server — no free port found")


# ─────────────────────────── ENTRY POINT ──────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  ⚡  XULT — Ultimate Discord Bot")
    print("=" * 55)
    print(f"  Data:   {DATA_DIR}")
    print(f"  Keys:   {KEYS_DIR}")
    print(f"  API:    port {API_PORT}")
    print(f"  Owner:  {BOT_OWNER_ID}")
    print("=" * 55)
    bot.run(TOKEN)
