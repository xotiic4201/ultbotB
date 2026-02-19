#!/usr/bin/env python3
"""
XULT - Ultimate Discord Bot with Complete Feature Set
Includes: Economy, Moderation, Notifications, Stock, 4:20, Candy Vending
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
import sqlite3
import asyncio
import aiohttp
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from aiohttp import web
import secrets

# ==================== CONFIG ====================

TOKEN = "YOUR_BOT_TOKEN_HERE"  # CHANGE THIS
API_PORT = 5000
API_KEY = secrets.token_hex(32)

# Your main server for premium checks
MAIN_SERVER_ID = 1309396933789483038  # CHANGE THIS
PREMIUM_ROLE_ID = 1353956858263765033  # CHANGE THIS

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
STOCK_DIR = DATA_DIR / "stock"
STOCK_DIR.mkdir(exist_ok=True)

# ==================== DATABASE ====================

conn = sqlite3.connect(DATA_DIR / "xult.db")
c = conn.cursor()

# Users table
c.execute("""CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    coins INTEGER DEFAULT 100,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    last_daily TIMESTAMP
)""")

# Premium users
c.execute("""CREATE TABLE IF NOT EXISTS premium_users (
    user_id INTEGER PRIMARY KEY,
    guild_id INTEGER,
    role_id INTEGER,
    granted_at TIMESTAMP,
    is_active INTEGER DEFAULT 1
)""")

# Command logs
c.execute("""CREATE TABLE IF NOT EXISTS command_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    user_id INTEGER,
    command TEXT,
    executed_at TIMESTAMP
)""")

# Stock usage
c.execute("""CREATE TABLE IF NOT EXISTS stock_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    stock_type TEXT,
    stock_content TEXT,
    guild_id INTEGER,
    generated_at TIMESTAMP
)""")

# Cooldowns
c.execute("""CREATE TABLE IF NOT EXISTS user_cooldowns (
    user_id INTEGER PRIMARY KEY,
    last_generated TIMESTAMP,
    generation_count INTEGER DEFAULT 0
)""")

# Guilds
c.execute("""CREATE TABLE IF NOT EXISTS guilds (
    id INTEGER PRIMARY KEY,
    name TEXT,
    joined_at TIMESTAMP
)""")

# Warnings
c.execute("""CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    user_id INTEGER,
    moderator_id INTEGER,
    reason TEXT,
    warned_at TIMESTAMP
)""")

# Jailed users
c.execute("""CREATE TABLE IF NOT EXISTS jailed (
    user_id INTEGER,
    guild_id INTEGER,
    roles TEXT,
    jailed_at TIMESTAMP,
    released_at TIMESTAMP,
    PRIMARY KEY (user_id, guild_id)
)""")

# Lottery entries
c.execute("""CREATE TABLE IF NOT EXISTS lottery (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    entered_at TIMESTAMP
)""")

# Notifications
c.execute("""CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    type TEXT,
    target TEXT,
    channel_id INTEGER,
    role_id INTEGER
)""")

# 4:20 reminders
c.execute("""CREATE TABLE IF NOT EXISTS four_twenty (
    guild_id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    role_id INTEGER,
    voice_channel_id INTEGER,
    timezone TEXT DEFAULT 'UTC',
    enabled INTEGER DEFAULT 1
)""")

conn.commit()

# ==================== BOT SETUP ====================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.start_time = datetime.now()

# ==================== STOCK FUNCTIONS ====================

def get_stock_file(stock_type: str):
    return STOCK_DIR / f"{stock_type.lower().strip()}.txt"

def count_stock(stock_type: str) -> int:
    file = get_stock_file(stock_type)
    if not file.exists():
        return 0
    content = file.read_text(encoding="utf-8").strip()
    return len([x for x in content.split("\n\n") if x.strip()]) if content else 0

def get_stock_entry(stock_type: str):
    """Get first entry and remove it"""
    file = get_stock_file(stock_type)
    if not file.exists():
        return None
    
    content = file.read_text(encoding="utf-8").strip()
    if not content:
        return None
    
    entries = [x.strip() for x in content.split("\n\n") if x.strip()]
    if not entries:
        return None
    
    first = entries[0]
    remaining = "\n\n".join(entries[1:])
    file.write_text(remaining, encoding="utf-8")
    
    return first

# ==================== BOT EVENTS ====================

@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')
    print(f'Bot ID: {bot.user.id}')
    print(f'🔑 API Key: {API_KEY}')
    print(f'📡 API Server starting on port {API_PORT}')
    
    # Save API key
    with open(DATA_DIR / "api_key.txt", "w") as f:
        f.write(API_KEY)
    
    # Store guilds
    for guild in bot.guilds:
        c.execute("INSERT OR IGNORE INTO guilds (id, name, joined_at) VALUES (?, ?, ?)",
                 (guild.id, guild.name, datetime.now().isoformat()))
    conn.commit()
    
    # Sync commands
    try:
        await bot.tree.sync()
        print("✅ Slash commands synced")
    except Exception as e:
        print(f"Error syncing commands: {e}")
    
    # Start background tasks
    check_lottery.start()
    check_unjail.start()
    send_four_twenty.start()
    
    # Start API server
    bot.loop.create_task(start_api_server())
    
    print("✅ Bot ready!")

# ==================== BACKGROUND TASKS ====================

@tasks.loop(hours=24)
async def check_lottery():
    """Daily lottery draw"""
    c.execute("SELECT user_id FROM lottery ORDER BY RANDOM() LIMIT 1")
    winner = c.fetchone()
    if winner:
        user_id = winner[0]
        c.execute("UPDATE users SET coins = coins + 1000 WHERE id = ?", (user_id,))
        c.execute("DELETE FROM lottery")
        conn.commit()
        
        # Try to DM winner
        user = bot.get_user(user_id)
        if user:
            await user.send("🎉 You won the lottery! 1000 coins added!")

@tasks.loop(seconds=30)
async def check_unjail():
    """Check for users to unjail"""
    now = datetime.now()
    c.execute("SELECT user_id, guild_id, roles FROM jailed WHERE released_at < ?", (now.isoformat(),))
    for user_id, guild_id, roles_json in c.fetchall():
        guild = bot.get_guild(guild_id)
        if guild:
            member = guild.get_member(user_id)
            if member:
                roles = [guild.get_role(int(r)) for r in json.loads(roles_json) if guild.get_role(int(r))]
                if roles:
                    await member.add_roles(*roles, reason="Auto-unjail")
        
        c.execute("DELETE FROM jailed WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
        conn.commit()

@tasks.loop(minutes=1)
async def send_four_twenty():
    """Check for 4:20 and send messages"""
    now = datetime.now()
    
    # Check if it's 4:20 (either AM or PM)
    if now.hour == 4 and now.minute == 20 or now.hour == 16 and now.minute == 20:
        c.execute("SELECT guild_id, channel_id, role_id, voice_channel_id FROM four_twenty WHERE enabled = 1")
        for guild_id, channel_id, role_id, vc_id in c.fetchall():
            guild = bot.get_guild(guild_id)
            if not guild:
                continue
            
            channel = guild.get_channel(channel_id)
            if not channel:
                continue
            
            role_mention = f"<@&{role_id}>" if role_id else ""
            vc = guild.get_channel(vc_id) if vc_id else None
            vc_link = f"https://discord.com/channels/{guild_id}/{vc_id}" if vc else None
            
            embed = discord.Embed(
                title="🌿 It's 4:20!",
                description=f"Time to blaze! {role_mention}",
                color=0x00ff00
            )
            if vc_link:
                embed.add_field(name="Voice Channel", value=f"[Join here]({vc_link})")
            
            try:
                await channel.send(embed=embed)
            except:
                pass

# ==================== BOT COMMANDS ====================

@bot.tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"🏓 Pong! `{latency}ms`")

# ==================== ECONOMY COMMANDS ====================

@bot.tree.command(name="balance", description="Check your coins")
async def balance(interaction: discord.Interaction):
    c.execute("INSERT OR IGNORE INTO users (id, username) VALUES (?, ?)", 
              (interaction.user.id, str(interaction.user)))
    c.execute("SELECT coins, xp, level FROM users WHERE id = ?", (interaction.user.id,))
    row = c.fetchone()
    conn.commit()
    
    embed = discord.Embed(title=f"{interaction.user.name}'s Balance", color=0x00ff00)
    embed.add_field(name="💰 Coins", value=row[0] if row else 100)
    embed.add_field(name="✨ XP", value=row[1] if row else 0)
    embed.add_field(name="📊 Level", value=row[2] if row else 1)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="daily", description="Claim your daily coins")
async def daily(interaction: discord.Interaction):
    user_id = interaction.user.id
    c.execute("SELECT last_daily FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    
    if row and row[0]:
        last = datetime.fromisoformat(row[0])
        if datetime.now() - last < timedelta(hours=24):
            remaining = timedelta(hours=24) - (datetime.now() - last)
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            await interaction.response.send_message(f"⏳ Come back in {hours}h {minutes}m!")
            return
    
    c.execute("UPDATE users SET coins = coins + 100, last_daily = ? WHERE id = ?", 
              (datetime.now().isoformat(), user_id))
    conn.commit()
    await interaction.response.send_message("✅ You claimed 100 daily coins!")

@bot.tree.command(name="lottery", description="Enter the lottery (100 coins)")
async def lottery(interaction: discord.Interaction):
    user_id = interaction.user.id
    
    # Check if already entered
    c.execute("SELECT * FROM lottery WHERE user_id = ?", (user_id,))
    if c.fetchone():
        await interaction.response.send_message("❌ You're already in the lottery!")
        return
    
    # Check coins
    c.execute("SELECT coins FROM users WHERE id = ?", (user_id,))
    coins = c.fetchone()[0]
    if coins < 100:
        await interaction.response.send_message("❌ You need 100 coins to enter!")
        return
    
    c.execute("UPDATE users SET coins = coins - 100 WHERE id = ?", (user_id,))
    c.execute("INSERT INTO lottery (user_id, entered_at) VALUES (?, ?)", 
              (user_id, datetime.now().isoformat()))
    conn.commit()
    
    await interaction.response.send_message("🎟️ You entered the lottery! Draw happens daily!")

# ==================== MODERATION COMMANDS ====================

@bot.tree.command(name="jail", description="Jail a user")
@app_commands.describe(user="User to jail", duration="Duration (e.g., 10m, 1h, 1d)", reason="Reason")
async def jail(interaction: discord.Interaction, user: discord.Member, duration: str = "10m", reason: str = "No reason"):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ You need Moderate Members permission!", ephemeral=True)
        return
    
    # Parse duration
    duration_seconds = 600  # default 10m
    if duration.endswith('m'):
        duration_seconds = int(duration[:-1]) * 60
    elif duration.endswith('h'):
        duration_seconds = int(duration[:-1]) * 3600
    elif duration.endswith('d'):
        duration_seconds = int(duration[:-1]) * 86400
    
    release_time = datetime.now() + timedelta(seconds=duration_seconds)
    
    # Store current roles
    roles = [role.id for role in user.roles if role.name != "@everyone"]
    
    # Remove all roles
    await user.edit(roles=[], reason=f"Jailed: {reason}")
    
    # Store in database
    c.execute("INSERT OR REPLACE INTO jailed (user_id, guild_id, roles, jailed_at, released_at) VALUES (?, ?, ?, ?, ?)",
              (user.id, interaction.guild.id, json.dumps(roles), datetime.now().isoformat(), release_time.isoformat()))
    conn.commit()
    
    await interaction.response.send_message(f"🔒 Jailed {user.mention} for {duration}. Reason: {reason}")

@bot.tree.command(name="unjail", description="Unjail a user")
async def unjail(interaction: discord.Interaction, user: discord.Member):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ You need Moderate Members permission!", ephemeral=True)
        return
    
    c.execute("SELECT roles FROM jailed WHERE user_id = ? AND guild_id = ?", (user.id, interaction.guild.id))
    row = c.fetchone()
    
    if row:
        roles = [interaction.guild.get_role(int(r)) for r in json.loads(row[0]) if interaction.guild.get_role(int(r))]
        if roles:
            await user.add_roles(*roles, reason="Unjailed")
        
        c.execute("DELETE FROM jailed WHERE user_id = ? AND guild_id = ?", (user.id, interaction.guild.id))
        conn.commit()
    
    await interaction.response.send_message(f"✅ Unjailed {user.mention}")

@bot.tree.command(name="warn", description="Warn a user")
async def warn(interaction: discord.Interaction, user: discord.Member, reason: str):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ You need Moderate Members permission!", ephemeral=True)
        return
    
    c.execute("INSERT INTO warnings (guild_id, user_id, moderator_id, reason, warned_at) VALUES (?, ?, ?, ?, ?)",
              (interaction.guild.id, user.id, interaction.user.id, reason, datetime.now().isoformat()))
    conn.commit()
    
    # Check warning count
    c.execute("SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?", 
              (interaction.guild.id, user.id))
    count = c.fetchone()[0]
    
    await interaction.response.send_message(f"⚠️ Warned {user.mention}. Reason: {reason} (Warning #{count})")
    
    # Auto-jail after 3 warnings
    if count >= 3:
        await jail(interaction, user, "1h", "3 warnings reached")

@bot.tree.command(name="warnings", description="Check user warnings")
async def get_warnings(interaction: discord.Interaction, user: discord.Member):
    c.execute("SELECT reason, warned_at, moderator_id FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY warned_at DESC",
              (interaction.guild.id, user.id))
    warnings = c.fetchall()
    
    if not warnings:
        await interaction.response.send_message(f"{user.mention} has no warnings.")
        return
    
    embed = discord.Embed(title=f"Warnings for {user.name}", color=0xffaa00)
    for i, (reason, warned_at, mod_id) in enumerate(warnings[:5], 1):
        mod = bot.get_user(mod_id)
        embed.add_field(name=f"Warning {i}", value=f"Reason: {reason}\nDate: {warned_at[:10]}\nMod: {mod.name if mod else 'Unknown'}", inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="purge", description="Delete messages")
async def purge(interaction: discord.Interaction, amount: int = 100):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ You need Manage Messages permission!", ephemeral=True)
        return
    
    await interaction.response.defer()
    deleted = await interaction.channel.purge(limit=min(amount, 100))
    await interaction.followup.send(f"✅ Deleted {len(deleted)} messages", ephemeral=True)

# ==================== STOCK COMMANDS ====================

@bot.tree.command(name="gen", description="Generate stock (premium only)")
async def gen(interaction: discord.Interaction, stock_type: str):
    # Check premium
    guild = bot.get_guild(MAIN_SERVER_ID)
    if guild:
        member = guild.get_member(interaction.user.id)
        premium_role = guild.get_role(PREMIUM_ROLE_ID)
        if not (member and premium_role and premium_role in member.roles):
            await interaction.response.send_message("❌ Premium role required!", ephemeral=True)
            return
    
    # Check cooldown
    c.execute("SELECT last_generated FROM user_cooldowns WHERE user_id = ?", (interaction.user.id,))
    row = c.fetchone()
    if row and row[0]:
        last = datetime.fromisoformat(row[0])
        if datetime.now() - last < timedelta(seconds=5):
            remaining = 5 - (datetime.now() - last).seconds
            await interaction.response.send_message(f"⏳ Please wait {remaining}s", ephemeral=True)
            return
    
    # Get stock
    content = get_stock_entry(stock_type)
    if not content:
        await interaction.response.send_message("❌ Out of stock!", ephemeral=True)
        return
    
    # Update cooldown
    c.execute("INSERT OR REPLACE INTO user_cooldowns (user_id, last_generated, generation_count) VALUES (?, ?, COALESCE((SELECT generation_count + 1 FROM user_cooldowns WHERE user_id = ?), 1))",
              (interaction.user.id, datetime.now().isoformat(), interaction.user.id))
    conn.commit()
    
    # DM the content
    try:
        await interaction.user.send(f"```\n{content}\n```")
        await interaction.response.send_message("✅ Stock sent to your DMs!")
    except:
        await interaction.response.send_message("❌ Couldn't DM you. Enable DMs and try again.", ephemeral=True)

# ==================== NOTIFICATION COMMANDS ====================

@bot.tree.command(name="track_youtube", description="Track a YouTube channel")
async def track_youtube(interaction: discord.Interaction, channel_id: str, notification_channel: discord.TextChannel, role: discord.Role = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only!", ephemeral=True)
        return
    
    c.execute("INSERT INTO notifications (guild_id, type, target, channel_id, role_id) VALUES (?, ?, ?, ?, ?)",
              (interaction.guild.id, "youtube", channel_id, notification_channel.id, role.id if role else None))
    conn.commit()
    
    await interaction.response.send_message(f"✅ Tracking YouTube channel: {channel_id}")

@bot.tree.command(name="track_twitch", description="Track a Twitch streamer")
async def track_twitch(interaction: discord.Interaction, username: str, notification_channel: discord.TextChannel, role: discord.Role = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only!", ephemeral=True)
        return
    
    c.execute("INSERT INTO notifications (guild_id, type, target, channel_id, role_id) VALUES (?, ?, ?, ?, ?)",
              (interaction.guild.id, "twitch", username, notification_channel.id, role.id if role else None))
    conn.commit()
    
    await interaction.response.send_message(f"✅ Tracking Twitch streamer: {username}")

@bot.tree.command(name="track_twitter", description="Track a Twitter/X account")
async def track_twitter(interaction: discord.Interaction, username: str, notification_channel: discord.TextChannel, role: discord.Role = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only!", ephemeral=True)
        return
    
    c.execute("INSERT INTO notifications (guild_id, type, target, channel_id, role_id) VALUES (?, ?, ?, ?, ?)",
              (interaction.guild.id, "twitter", username, notification_channel.id, role.id if role else None))
    conn.commit()
    
    await interaction.response.send_message(f"✅ Tracking Twitter/X account: @{username}")

# ==================== 4:20 COMMANDS ====================

@bot.tree.command(name="setup_420", description="Setup 4:20 reminders")
async def setup_420(interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role = None, voice_channel: discord.VoiceChannel = None, timezone: str = "UTC"):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only!", ephemeral=True)
        return
    
    c.execute("INSERT OR REPLACE INTO four_twenty (guild_id, channel_id, role_id, voice_channel_id, timezone, enabled) VALUES (?, ?, ?, ?, ?, 1)",
              (interaction.guild.id, channel.id, role.id if role else None, voice_channel.id if voice_channel else None, timezone))
    conn.commit()
    
    await interaction.response.send_message(f"✅ 4:20 reminders set in {channel.mention}")

# ==================== CANDY VENDING COMMAND ====================

@bot.tree.command(name="candy", description="Open candy vending machine")
async def candy(interaction: discord.Interaction):
    guild = bot.get_guild(MAIN_SERVER_ID)
    if not guild:
        await interaction.response.send_message("❌ Main server not found", ephemeral=True)
        return
    
    member = guild.get_member(interaction.user.id)
    premium_role = guild.get_role(PREMIUM_ROLE_ID)
    
    if member and premium_role and premium_role in member.roles:
        # Cache premium
        c.execute("INSERT OR IGNORE INTO premium_users (user_id, guild_id, role_id, granted_at, is_active) VALUES (?, ?, ?, ?, 1)",
                 (interaction.user.id, MAIN_SERVER_ID, PREMIUM_ROLE_ID, datetime.now().isoformat()))
        conn.commit()
        
        embed = discord.Embed(
            title="🍬 Candy Vending Machine",
            description="Visit the dashboard to use the candy vending machine!",
            color=0xff69b4
        )
        embed.add_field(name="Dashboard", value="http://localhost:8000#vending", inline=False)
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("❌ Premium role required!", ephemeral=True)

# ==================== API SERVER ====================

async def handle_api_stats(request):
    """GET /api/stats - Get bot statistics"""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {API_KEY}":
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0] or 0
        
        total_servers = len(bot.guilds)
        
        c.execute("SELECT COUNT(*) FROM premium_users WHERE is_active = 1")
        premium_users = c.fetchone()[0] or 0
        
        c.execute("SELECT COUNT(*) FROM stock_usage WHERE generated_at > datetime('now', '-1 day')")
        commands_today = c.fetchone()[0] or 0
        
        # Activity data for chart
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
            if file.name.endswith('.meta.json'):
                continue
            
            stock_type = file.stem
            count = count_stock(stock_type)
            
            # Candy defaults
            defaults = {
                "nitro": {"name": "Nitro Blast", "flavor": "Blue Raspberry", "emoji": "💎"},
                "spotify": {"name": "Spotify Sours", "flavor": "Green Apple", "emoji": "🎵"},
                "netflix": {"name": "Netflix Nibs", "flavor": "Cherry", "emoji": "🎬"},
                "steam": {"name": "Steam Drops", "flavor": "Cola", "emoji": "🎮"},
                "discord": {"name": "Discord Dots", "flavor": "Blueberry", "emoji": "💬"},
                "minecraft": {"name": "Minecraft Blocks", "flavor": "Melon", "emoji": "⛏️"}
            }
            
            d = defaults.get(stock_type, {"name": stock_type.capitalize(), "flavor": "Mixed", "emoji": "🍬"})
            
            stock_data[stock_type] = {
                "count": count,
                "name": d["name"],
                "flavor": d["flavor"],
                "emoji": d["emoji"],
                "cooldown": 5
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
        
        if not user_id or not stock_type:
            return web.json_response({"error": "Missing parameters"}, status=400)
        
        # Check premium
        c.execute("SELECT * FROM premium_users WHERE user_id = ? AND is_active = 1", (user_id,))
        if not c.fetchone():
            guild = bot.get_guild(MAIN_SERVER_ID)
            if guild:
                member = guild.get_member(int(user_id))
                premium_role = guild.get_role(PREMIUM_ROLE_ID)
                if member and premium_role and premium_role in member.roles:
                    c.execute("INSERT INTO premium_users (user_id, guild_id, role_id, granted_at, is_active) VALUES (?, ?, ?, ?, 1)",
                             (user_id, MAIN_SERVER_ID, PREMIUM_ROLE_ID, datetime.now().isoformat()))
                    conn.commit()
                else:
                    return web.json_response({"success": False, "error": "Premium role required"})
        
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
        c.execute("INSERT INTO stock_usage (user_id, stock_type, stock_content, generated_at) VALUES (?, ?, ?, ?)",
                 (user_id, stock_type, content, datetime.now().isoformat()))
        
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
        
        c.execute("SELECT * FROM premium_users WHERE user_id = ? AND is_active = 1", (user_id,))
        if c.fetchone():
            return web.json_response({"hasPremium": True})
        
        guild = bot.get_guild(MAIN_SERVER_ID)
        if guild:
            member = guild.get_member(user_id)
            premium_role = guild.get_role(PREMIUM_ROLE_ID)
            if member and premium_role and premium_role in member.roles:
                c.execute("INSERT INTO premium_users (user_id, guild_id, role_id, granted_at, is_active) VALUES (?, ?, ?, ?, 1)",
                         (user_id, MAIN_SERVER_ID, PREMIUM_ROLE_ID, datetime.now().isoformat()))
                conn.commit()
                return web.json_response({"hasPremium": True})
        
        return web.json_response({"hasPremium": False})
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
        
        # Get rank
        c.execute("SELECT COUNT(*) FROM users WHERE coins > (SELECT coins FROM users WHERE id = ?)", (user_id,))
        rank = c.fetchone()[0] + 1
        
        return web.json_response({
            "coins": row[0] if row else 100,
            "xp": row[1] if row else 0,
            "level": row[2] if row else 1,
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
                "username": username,
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
        
        file = get_stock_file(stock_type)
        
        # Append content
        if file.exists():
            current = file.read_text(encoding="utf-8").strip()
            if current:
                file.write_text(current + "\n\n" + content, encoding="utf-8")
            else:
                file.write_text(content, encoding="utf-8")
        else:
            file.write_text(content, encoding="utf-8")
        
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def start_api_server():
    """Start the API server"""
    app = web.Application()
    
    app.router.add_get('/api/stats', handle_api_stats)
    app.router.add_get('/api/stock', handle_api_stock)
    app.router.add_post('/api/stock/generate/{type}', handle_api_generate)
    app.router.add_post('/api/stock/add', handle_api_stock_add)
    app.router.add_get('/api/check-premium/{user_id}', handle_api_check_premium)
    app.router.add_get('/api/user/{user_id}', handle_api_user)
    app.router.add_get('/api/leaderboard', handle_api_leaderboard)
    
    # Try ports
    for port in range(API_PORT, API_PORT + 5):
        try:
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, '0.0.0.0', port)
            await site.start()
            print(f"✅ API server running on http://0.0.0.0:{port}")
            return
        except OSError:
            continue
    
    print("❌ Could not start API server")

# ==================== RUN ====================

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 Starting XULT Bot - Complete Edition")
    print("=" * 50)
    print(f"📁 Data directory: {DATA_DIR}")
    print(f"🔑 API Key: {API_KEY}")
    print("=" * 50)
    
    if TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ ERROR: Set your bot token in the script!")
        exit(1)
    
    bot.run(TOKEN)
