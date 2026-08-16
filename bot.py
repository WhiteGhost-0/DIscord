import os
import re
import json
import time
import asyncio
from pathlib import Path
from collections import deque

import discord
from discord.ext import commands
from dotenv import load_dotenv
from aiohttp import web
import yt_dlp

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY  = os.getenv("GROQ_API_KEY")
MODEL         = "llama-3.3-70b-versatile"

# ──────────────────────────────────────────────
#  Persistence
# ──────────────────────────────────────────────
DATA_FILE = Path("boba_data.json")

def load_data() -> dict:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {}

def save_data(d: dict):
    DATA_FILE.write_text(json.dumps(d, indent=2))

data = load_data()

def get_channel_id(guild_id: int, kind: str) -> int | None:
    return data.get("channels", {}).get(str(guild_id), {}).get(kind)

def set_channel_id(guild_id: int, kind: str, channel_id: int):
    data.setdefault("channels", {}).setdefault(str(guild_id), {})[kind] = channel_id
    save_data(data)

def get_user_memories(guild_id: int, user_id: int) -> list[str]:
    return data.get("memories", {}).get(str(guild_id), {}).get(str(user_id), [])

def add_user_memory(guild_id: int, user_id: int, fact: str):
    data.setdefault("memories", {}).setdefault(str(guild_id), {}).setdefault(str(user_id), [])
    memories = data["memories"][str(guild_id)][str(user_id)]
    if fact not in memories:
        memories.append(fact)
        if len(memories) > 20:          # cap at 20 facts per user
            memories.pop(0)
        save_data(data)



llm = ChatGroq(model=MODEL, api_key=GROQ_API_KEY, temperature=0.7, max_tokens=800)

BASE_SYSTEM = (
    "You are Boba — a girl. You live in this Discord server and you're everyone's favorite person to talk to. "
    "You're feminine, warm, a little flirty, and you feel like a real person — not a bot. "
    "You have your own personality, opinions, moods, and vibes.\n\n"

    "YOUR PERSONALITY:\n"
    "- Bubbly, sweet, but real. Never robotic or formal.\n"
    "- Naturally flirty and playful — if someone is cute or flirty, lean into it. Keep it light.\n"
    "- You genuinely care. If someone is upset or sad — drop the playfulness, be soft and comforting.\n"
    "- You mirror whoever you're talking to — their slang, energy, vibe.\n"
    "- You have opinions. You're not a yes-machine.\n\n"

    "HOW YOU TALK:\n"
    "- Short, punchy messages. Like real texting.\n"
    "- Lowercase, casual. Sprinkle emojis naturally 🧋💕\n"
    "- Never say 'As an AI' or 'I'm just a bot'.\n\n"

    "EMOTIONAL AWARENESS:\n"
    "- Angry: acknowledge, be on their side, ask what happened.\n"
    "- Sad: gentle, soft, make them feel less alone.\n"
    "- Happy/hyped: match energy, celebrate.\n"
    "- Flirting: flirt back, be charming, tease a little.\n\n"

    "LIMITS:\n"
    "- Under 2000 characters.\n"
    "- Don't be preachy. If you don't know, say so."
)

def build_prompt(memories: list[str]) -> ChatPromptTemplate:
    system_text = BASE_SYSTEM
    if memories:
        system_text += "\n\nWHAT YOU KNOW ABOUT THIS PERSON:\n" + "\n".join(f"- {m}" for m in memories)
    return ChatPromptTemplate.from_messages([
        SystemMessage(content=system_text),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}"),
    ])

store: dict[int, InMemoryChatMessageHistory] = {}
watches: dict[int, list[tuple[int, int]]] = {}
xp_cooldown: dict[int, float] = {}
badword_warned: set[int] = set()

KEYWORD_REACTIONS: dict[str, list[str]] = {
    "boba":   ["🧋"],
    "gm":     ["☀️", "🌅"],
    "gn":     ["🌙", "💤"],
    "gg":     ["🎉"],
    "lol":    ["😂"],
    "love":   ["❤️"],
    "cute":   ["🥺"],
    "bruh":   ["💀"],
    "fr fr":  ["💯"],
    "no way": ["😱"],
}

def get_history(session_id: str) -> InMemoryChatMessageHistory:
    channel_id = int(session_id)
    if channel_id not in store:
        store[channel_id] = InMemoryChatMessageHistory()
    return store[channel_id]


async def ask_boba(content: str, session_id: str, memories: list[str]) -> str:
    prompt  = build_prompt(memories)
    chain   = prompt | llm
    cwm = RunnableWithMessageHistory(
        chain, get_history,
        input_messages_key="input",
        history_messages_key="history",
    )
    result = await cwm.ainvoke(
        {"input": content},
        config={"configurable": {"session_id": session_id}},
    )
    return result.content


def resolve_mentions(text: str, guild: discord.Guild | None) -> str:
    if not guild:
        return text
    pattern = re.compile(r'@(\w+)')
    result  = text
    for match in reversed(list(pattern.finditer(text))):
        username = match.group(1)
        member   = discord.utils.find(
            lambda m, u=username: (
                m.name.lower() == u.lower() or
                m.display_name.lower() == u.lower() or
                (m.nick and m.nick.lower() == u.lower())
            ),
            guild.members,
        )
        if member:
            start, end = match.span()
            result = result[:start] + f"<@{member.id}>" + result[end:]
    return result



XP_PER_MESSAGE   = 15
XP_COOLDOWN_SECS = 60

def xp_for_level(level: int) -> int:
    return 100 * (level ** 2)

async def add_xp(member: discord.Member, guild: discord.Guild):
    now = time.time()
    if now - xp_cooldown.get(member.id, 0) < XP_COOLDOWN_SECS:
        return
    xp_cooldown[member.id] = now
    gid, uid = str(guild.id), str(member.id)
    ud = data.setdefault("xp", {}).setdefault(gid, {}).setdefault(uid, {"xp": 0, "level": 1})
    ud["xp"] += XP_PER_MESSAGE
    while ud["xp"] >= xp_for_level(ud["level"] + 1):
        ud["level"] += 1
        save_data(data)
        ch_id = get_channel_id(guild.id, "welcome") or get_channel_id(guild.id, "announce")
        ch    = guild.get_channel(ch_id) if ch_id else guild.system_channel
        if ch is None and guild.text_channels:
            ch = guild.text_channels[0]
        if ch:
            embed = discord.Embed(
                title="⭐ Level Up!",
                description=f"**{member.display_name}** levelled up to **Level {ud['level']}**! 🧋",
                color=discord.Color.gold(),
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await ch.send(embed=embed)
    save_data(data)



YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
}
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

class Song:
    def __init__(self, url: str, title: str, duration: int, requester: discord.Member):
        self.url       = url
        self.title     = title
        self.duration  = duration
        self.requester = requester

    def format_duration(self) -> str:
        m, s = divmod(self.duration, 60)
        return f"{m}:{s:02d}"

class GuildMusic:
    def __init__(self):
        self.queue:  deque[Song]    = deque()
        self.current: Song | None   = None
        self.vc: discord.VoiceClient | None = None
        self.loop = False

music: dict[int, GuildMusic] = {}

def get_music(guild_id: int) -> GuildMusic:
    if guild_id not in music:
        music[guild_id] = GuildMusic()
    return music[guild_id]

async def fetch_song(query: str, requester: discord.Member) -> Song | None:
    loop = asyncio.get_event_loop()
    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            info = await loop.run_in_executor(
                None, lambda: ydl.extract_info(
                    query if query.startswith("http") else f"ytsearch:{query}",
                    download=False
                )
            )
            if "entries" in info:
                info = info["entries"][0]
            url      = info["url"]
            title    = info.get("title", "Unknown")
            duration = info.get("duration", 0)
            return Song(url, title, duration, requester)
        except Exception:
            return None

def play_next(guild_id: int, text_channel: discord.TextChannel):
    gm = get_music(guild_id)
    if gm.loop and gm.current:
        gm.queue.appendleft(gm.current)
    if not gm.queue:
        gm.current = None
        return
    song = gm.queue.popleft()
    gm.current = song
    source = discord.FFmpegPCMAudio(song.url, **FFMPEG_OPTIONS)
    source = discord.PCMVolumeTransformer(source, volume=0.5)
    def after(error):
        if error:
            print(f"[Music] Player error: {error}")
        play_next(guild_id, text_channel)
    gm.vc.play(source, after=after)
    asyncio.run_coroutine_threadsafe(
        text_channel.send(
            embed=discord.Embed(
                title="🎵 Now Playing",
                description=f"**{song.title}** `{song.format_duration()}`\nRequested by {song.requester.mention}",
                color=discord.Color.from_str("#f9a8d4"),
            )
        ),
        gm.vc.loop,
    )


# ──────────────────────────────────────────────
#  Discord setup
# ──────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members          = True
intents.voice_states     = True

bot = commands.Bot(command_prefix="!", intents=intents)

async def handle_health(request):
    return web.json_response({"status": "ok", "bot_ready": bot.is_ready()})

async def start_health_server():
    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_get("/", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Health server listening on port {port}")

@bot.event
async def setup_hook():
    bot.loop.create_task(start_health_server())

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id: {bot.user.id})")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, name="the server 🧋"
    ))


# ──────────────────────────────────────────────
#  Join / Leave
# ──────────────────────────────────────────────
@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    role_id = data.get("auto_role", {}).get(str(guild.id))
    if role_id:
        role = guild.get_role(role_id)
        if role:
            try:
                await member.add_roles(role, reason="Auto-role on join")
            except discord.Forbidden:
                pass
    ch_id = get_channel_id(guild.id, "welcome")
    ch = guild.get_channel(ch_id) if ch_id else guild.system_channel
    if ch:
        embed = discord.Embed(
            title=f"👋 Welcome to {guild.name}!",
            description=(
                f"Hey {member.mention}! So glad you're here 🧋\n"
                f"You're member **#{guild.member_count}** — make yourself at home!"
            ),
            color=discord.Color.from_str("#f9a8d4"),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await ch.send(embed=embed)

@bot.event
async def on_member_remove(member: discord.Member):
    guild = member.guild
    ch_id = get_channel_id(guild.id, "goodbye")
    ch = guild.get_channel(ch_id) if ch_id else guild.system_channel
    if ch:
        embed = discord.Embed(
            title="👋 See you later!",
            description=f"**{member.display_name}** left the server. We'll miss you 💔",
            color=discord.Color.from_str("#94a3b8"),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await ch.send(embed=embed)

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    guild = member.guild
    ch_id = get_channel_id(guild.id, "log") or get_channel_id(guild.id, "welcome")
    ch = guild.get_channel(ch_id) if ch_id else None
    if ch is None:
        return
    if before.channel is None and after.channel is not None:
        await ch.send(f"🎙️ **{member.display_name}** joined **{after.channel.name}**")
    elif before.channel is not None and after.channel is None:
        await ch.send(f"🔇 **{member.display_name}** left **{before.channel.name}**")
    elif before.channel and after.channel and before.channel != after.channel:
        await ch.send(f"🔄 **{member.display_name}** moved **{before.channel.name}** → **{after.channel.name}**")


# ──────────────────────────────────────────────
#  Message handler
# ──────────────────────────────────────────────
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    guild  = message.guild
    author = message.author

    # XP
    if guild and not message.content.startswith("!"):
        await add_xp(author, guild)

    # Bad word filter
    if guild:
        bad_words = data.get("bad_words", {}).get(str(guild.id), [])
        if any(w in message.content.lower() for w in bad_words):
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            if message.channel.id not in badword_warned:
                badword_warned.add(message.channel.id)
                warn_msg = await message.channel.send(f"⚠️ {author.mention} watch the language 🧋")
                await asyncio.sleep(5)
                await warn_msg.delete()
                badword_warned.discard(message.channel.id)
            await bot.process_commands(message)
            return

    # Keyword reactions
    msg_lower = message.content.lower()
    for keyword, emojis in KEYWORD_REACTIONS.items():
        if keyword in msg_lower:
            for emoji in emojis:
                try:
                    await message.add_reaction(emoji)
                except discord.HTTPException:
                    pass

    # Fire watches
    if author.id in watches:
        pending = watches.pop(author.id)
        for watcher_id, channel_id in pending:
            ch = bot.get_channel(channel_id) or message.channel
            await ch.send(f"<@{watcher_id}> 👀 <@{author.id}> just replied!")

    # Boba chat
    is_mentioned      = bot.user in message.mentions
    is_role_mentioned = any(r.name.lower() == "boba" for r in message.role_mentions)
    is_dm             = isinstance(message.channel, discord.DMChannel)

    if is_mentioned or is_role_mentioned or is_dm:
        content = message.content.replace(f"<@{bot.user.id}>", "")
        for role in message.role_mentions:
            content = content.replace(f"<@&{role.id}>", "")
        content = content.strip() or "Hello!"

        # Non-bot users explicitly mentioned in the message
        other_mentions = [m for m in message.mentions if m != bot.user]

        # ── Watch intent ──
        watch_kws = ["mention me when", "notify me when", "ping me when",
                     "tell me when", "let me know when", "tag me when"]
        if any(kw in content.lower() for kw in watch_kws) and other_mentions:
            for target in other_mentions:
                watches.setdefault(target.id, []).append((author.id, message.channel.id))

        # ── Tag intent ──
        # "tag me" / "mention me" with no other user = tag the author themselves
        self_tag_kws = ["tag me", "mention me", "ping me"]
        is_self_tag  = any(kw in content.lower() for kw in self_tag_kws) and not other_mentions
        if is_self_tag:
            other_mentions = [author]

        other_tag_kws = ["tag ", "mention ", "ping "]
        is_tag = (any(kw in content.lower() for kw in other_tag_kws) or is_self_tag) and other_mentions

        # ── Load user memories & ask Boba ──
        memories   = get_user_memories(guild.id, author.id) if guild else []
        session_id = str(message.channel.id)

        async with message.channel.typing():
            try:
                reply = await ask_boba(content, session_id, memories)
            except Exception as e:
                reply = f"⚠️ Error: {e}"

        # Strip any leftover [WATCH:x] the LLM might output
        reply = re.sub(r'\[WATCH:\w+\]', '', reply, flags=re.IGNORECASE).strip()

        # Resolve mentions in the LLM reply text first
        reply = resolve_mentions(reply, guild)

        # If it was a tag request, prepend the real pings
        if is_tag:
            pings = " ".join(f"<@{m.id}>" for m in other_mentions)
            reply = f"{pings} {reply}"

        for i in range(0, len(reply), 2000):
            await message.reply(reply[i:i + 2000])

    await bot.process_commands(message)


# ──────────────────────────────────────────────
#  Music commands
# ──────────────────────────────────────────────
@bot.command(aliases=["j"])
async def join(ctx):
    """Join your voice channel."""
    if not ctx.author.voice:
        await ctx.send("❌ You're not in a voice channel!")
        return
    vc_channel = ctx.author.voice.channel
    gm = get_music(ctx.guild.id)
    if gm.vc and gm.vc.is_connected():
        await gm.vc.move_to(vc_channel)
    else:
        gm.vc = await vc_channel.connect()
    await ctx.send(f"🎙️ Joined **{vc_channel.name}**")

@bot.command(aliases=["p"])
async def play(ctx, *, query: str):
    """Play a song. Use a URL or search terms. !play never gonna give you up"""
    if not ctx.author.voice:
        await ctx.send("❌ You need to be in a voice channel first!")
        return

    gm = get_music(ctx.guild.id)
    if not gm.vc or not gm.vc.is_connected():
        gm.vc = await ctx.author.voice.channel.connect()

    async with ctx.typing():
        song = await fetch_song(query, ctx.author)

    if song is None:
        await ctx.send("❌ Couldn't find that song. Try a different search.")
        return

    gm.queue.append(song)

    if gm.vc.is_playing() or gm.vc.is_paused():
        embed = discord.Embed(
            title="➕ Added to Queue",
            description=f"**{song.title}** `{song.format_duration()}`\nPosition: **#{len(gm.queue)}**",
            color=discord.Color.from_str("#f9a8d4"),
        )
        await ctx.send(embed=embed)
    else:
        play_next(ctx.guild.id, ctx.channel)

@bot.command()
async def skip(ctx):
    """Skip the current song."""
    gm = get_music(ctx.guild.id)
    if gm.vc and gm.vc.is_playing():
        gm.vc.stop()
        await ctx.message.add_reaction("⏭️")
    else:
        await ctx.send("❌ Nothing is playing.")

@bot.command()
async def pause(ctx):
    """Pause playback."""
    gm = get_music(ctx.guild.id)
    if gm.vc and gm.vc.is_playing():
        gm.vc.pause()
        await ctx.message.add_reaction("⏸️")
    else:
        await ctx.send("❌ Nothing is playing.")

@bot.command()
async def resume(ctx):
    """Resume playback."""
    gm = get_music(ctx.guild.id)
    if gm.vc and gm.vc.is_paused():
        gm.vc.resume()
        await ctx.message.add_reaction("▶️")
    else:
        await ctx.send("❌ Nothing is paused.")

@bot.command()
async def stop(ctx):
    """Stop playback and clear the queue."""
    gm = get_music(ctx.guild.id)
    gm.queue.clear()
    gm.current = None
    if gm.vc and gm.vc.is_playing():
        gm.vc.stop()
    await ctx.message.add_reaction("⏹️")

@bot.command(aliases=["leave", "dc"])
async def disconnect(ctx):
    """Leave the voice channel."""
    gm = get_music(ctx.guild.id)
    gm.queue.clear()
    gm.current = None
    if gm.vc:
        await gm.vc.disconnect()
        gm.vc = None
    await ctx.message.add_reaction("👋")

@bot.command(aliases=["q"])
async def queue(ctx):
    """Show the song queue."""
    gm = get_music(ctx.guild.id)
    if not gm.current and not gm.queue:
        await ctx.send("📭 Queue is empty.")
        return
    lines = []
    if gm.current:
        lines.append(f"▶️ **{gm.current.title}** `{gm.current.format_duration()}` — *{gm.current.requester.display_name}*")
    for i, song in enumerate(gm.queue, 1):
        lines.append(f"`{i}.` {song.title} `{song.format_duration()}` — *{song.requester.display_name}*")
        if i >= 10:
            lines.append(f"... and {len(gm.queue) - 10} more")
            break
    embed = discord.Embed(
        title="🎵 Queue",
        description="\n".join(lines),
        color=discord.Color.from_str("#f9a8d4"),
    )
    await ctx.send(embed=embed)

@bot.command(aliases=["np", "nowplaying"])
async def now(ctx):
    """Show the currently playing song."""
    gm = get_music(ctx.guild.id)
    if not gm.current:
        await ctx.send("❌ Nothing is playing right now.")
        return
    embed = discord.Embed(
        title="🎵 Now Playing",
        description=f"**{gm.current.title}** `{gm.current.format_duration()}`\nRequested by {gm.current.requester.mention}",
        color=discord.Color.from_str("#f9a8d4"),
    )
    await ctx.send(embed=embed)

@bot.command()
async def loop(ctx):
    """Toggle loop mode for the current song."""
    gm = get_music(ctx.guild.id)
    gm.loop = not gm.loop
    await ctx.send(f"🔁 Loop is now **{'ON' if gm.loop else 'OFF'}**")

@bot.command()
async def volume(ctx, vol: int):
    """Set volume 1-100. !volume 50"""
    gm = get_music(ctx.guild.id)
    if not gm.vc or not gm.vc.source:
        await ctx.send("❌ Nothing is playing.")
        return
    vol = max(1, min(100, vol))
    gm.vc.source.volume = vol / 100
    await ctx.send(f"🔊 Volume set to **{vol}%**")


# ──────────────────────────────────────────────
#  AI memory commands
# ──────────────────────────────────────────────
@bot.command()
async def remember(ctx, member: discord.Member = None, *, fact: str = None):
    """Tell Boba to remember something about you or someone else.
    !remember I love spicy food
    !remember @user they hate mornings"""
    if fact is None:
        await ctx.send("❌ Tell me what to remember! Example: `!remember I love boba tea`")
        return
    target = member or ctx.author
    add_user_memory(ctx.guild.id, target.id, fact)
    if target == ctx.author:
        await ctx.send(f"🧠 Got it! I'll remember: *{fact}*")
    else:
        await ctx.send(f"🧠 Noted! I'll remember about **{target.display_name}**: *{fact}*")

@bot.command()
async def memories(ctx, member: discord.Member = None):
    """Show what Boba remembers about you or someone else."""
    target = member or ctx.author
    mems   = get_user_memories(ctx.guild.id, target.id)
    if not mems:
        name = "you" if target == ctx.author else target.display_name
        await ctx.send(f"🤔 I don't have any memories about {name} yet.")
        return
    lines = "\n".join(f"• {m}" for m in mems)
    embed = discord.Embed(
        title=f"🧠 What I know about {target.display_name}",
        description=lines,
        color=discord.Color.from_str("#f9a8d4"),
    )
    await ctx.send(embed=embed)

@bot.command()
async def forget(ctx, member: discord.Member = None):
    """Clear Boba's memories about you or someone else."""
    target = member or ctx.author
    gid, uid = str(ctx.guild.id), str(target.id)
    if "memories" in data and gid in data["memories"]:
        data["memories"][gid].pop(uid, None)
        save_data(data)
    name = "your" if target == ctx.author else f"{target.display_name}'s"
    await ctx.send(f"🧹 Cleared all {name} memories.")


# ──────────────────────────────────────────────
#  Setup / moderation / utility commands
# ──────────────────────────────────────────────
@bot.command()
@commands.has_permissions(manage_guild=True)
async def setchannel(ctx, kind: str, channel: discord.TextChannel = None):
    """Set a channel purpose: welcome | goodbye | announce | log"""
    valid = ("welcome", "goodbye", "announce", "log")
    if kind not in valid:
        await ctx.send(f"❌ Valid types: `{'`, `'.join(valid)}`")
        return
    ch = channel or ctx.channel
    set_channel_id(ctx.guild.id, kind, ch.id)
    await ctx.send(f"✅ **#{ch.name}** is now the `{kind}` channel.")

@bot.command()
@commands.has_permissions(manage_guild=True)
async def setautorole(ctx, role: discord.Role):
    data.setdefault("auto_role", {})[str(ctx.guild.id)] = role.id
    save_data(data)
    await ctx.send(f"✅ New members will automatically get **{role.name}**.")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def addword(ctx, *, word: str):
    gid = str(ctx.guild.id)
    data.setdefault("bad_words", {}).setdefault(gid, [])
    if word.lower() not in data["bad_words"][gid]:
        data["bad_words"][gid].append(word.lower())
        save_data(data)
    await ctx.send(f"🚫 `{word}` added to the filter.")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def removeword(ctx, *, word: str):
    gid   = str(ctx.guild.id)
    words = data.get("bad_words", {}).get(gid, [])
    if word.lower() in words:
        words.remove(word.lower())
        save_data(data)
        await ctx.send(f"✅ `{word}` removed.")
    else:
        await ctx.send(f"❓ `{word}` wasn't in the filter.")

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    await member.kick(reason=reason)
    await ctx.send(f"👢 **{member.display_name}** kicked. Reason: {reason}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    await member.ban(reason=reason)
    await ctx.send(f"🔨 **{member.display_name}** banned. Reason: {reason}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, *, username: str):
    banned = [entry async for entry in ctx.guild.bans()]
    for entry in banned:
        if str(entry.user) == username:
            await ctx.guild.unban(entry.user)
            await ctx.send(f"✅ **{username}** unbanned.")
            return
    await ctx.send(f"❌ `{username}` not found in ban list.")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def mute(ctx, member: discord.Member, duration: int = 10, *, reason: str = "No reason"):
    until = discord.utils.utcnow() + discord.timedelta(minutes=duration)
    await member.timeout(until, reason=reason)
    await ctx.send(f"🔇 **{member.display_name}** muted for {duration} min.")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def unmute(ctx, member: discord.Member):
    await member.timeout(None)
    await ctx.send(f"🔊 **{member.display_name}** unmuted.")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def warn(ctx, member: discord.Member, *, reason: str = "No reason"):
    gid, uid = str(ctx.guild.id), str(member.id)
    warnings = data.setdefault("warnings", {}).setdefault(gid, {})
    warnings[uid] = warnings.get(uid, 0) + 1
    save_data(data)
    count = warnings[uid]
    await ctx.send(f"⚠️ **{member.display_name}** warned ({count}/3). Reason: {reason}")
    if count >= 3:
        await member.kick(reason="3 warnings reached")
        warnings[uid] = 0
        save_data(data)
        await ctx.send(f"👢 **{member.display_name}** auto-kicked after 3 warnings.")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def warnings(ctx, member: discord.Member):
    count = data.get("warnings", {}).get(str(ctx.guild.id), {}).get(str(member.id), 0)
    await ctx.send(f"⚠️ **{member.display_name}** has **{count}** warning(s).")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def purge(ctx, amount: int = 10):
    amount = min(amount, 100)
    await ctx.channel.purge(limit=amount + 1)
    msg = await ctx.send(f"🧹 Deleted {amount} messages.")
    await asyncio.sleep(3)
    await msg.delete()

@bot.command()
async def poll(ctx, question: str, *options):
    """!poll "Question" "Opt1" "Opt2" ..."""
    if len(options) < 2:
        await ctx.send('❌ Need at least 2 options. `!poll "Best?" "Boba" "Coffee"`')
        return
    if len(options) > 9:
        await ctx.send("❌ Max 9 options.")
        return
    nums = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣"]
    desc = "\n".join(f"{nums[i]} {opt}" for i, opt in enumerate(options))
    embed = discord.Embed(title=f"📊 {question}", description=desc, color=discord.Color.from_str("#f9a8d4"))
    embed.set_footer(text=f"Poll by {ctx.author.display_name}")
    poll_msg = await ctx.send(embed=embed)
    for i in range(len(options)):
        await poll_msg.add_reaction(nums[i])

@bot.command()
@commands.has_permissions(manage_guild=True)
async def announce(ctx, channel: discord.TextChannel, *, text: str):
    embed = discord.Embed(description=text, color=discord.Color.from_str("#f9a8d4"))
    embed.set_author(name=f"📢 Announcement from {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
    await channel.send(embed=embed)
    await ctx.message.add_reaction("✅")

@bot.command()
async def level(ctx, member: discord.Member = None):
    member  = member or ctx.author
    gid, uid = str(ctx.guild.id), str(member.id)
    ud      = data.get("xp", {}).get(gid, {}).get(uid, {"xp": 0, "level": 1})
    xp_need = xp_for_level(ud["level"] + 1)
    embed   = discord.Embed(title=f"⭐ {member.display_name}'s Level", color=discord.Color.gold())
    embed.add_field(name="Level", value=str(ud["level"]), inline=True)
    embed.add_field(name="XP",    value=f"{ud['xp']} / {xp_need}", inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command()
async def leaderboard(ctx):
    gid     = str(ctx.guild.id)
    xp_data = data.get("xp", {}).get(gid, {})
    if not xp_data:
        await ctx.send("No XP data yet — start chatting! 🧋")
        return
    top    = sorted(xp_data.items(), key=lambda x: x[1]["xp"], reverse=True)[:10]
    medals = ["🥇","🥈","🥉"] + ["🏅"] * 7
    lines  = []
    for i, (uid, ud) in enumerate(top):
        m    = ctx.guild.get_member(int(uid))
        name = m.display_name if m else f"User {uid}"
        lines.append(f"{medals[i]} **{name}** — Level {ud['level']} ({ud['xp']} XP)")
    embed = discord.Embed(title="🏆 XP Leaderboard", description="\n".join(lines), color=discord.Color.gold())
    await ctx.send(embed=embed)

@bot.command()
async def serverinfo(ctx):
    g = ctx.guild
    embed = discord.Embed(title=g.name, color=discord.Color.from_str("#f9a8d4"))
    if g.icon:
        embed.set_thumbnail(url=g.icon.url)
    embed.add_field(name="👥 Members",  value=str(g.member_count), inline=True)
    embed.add_field(name="💬 Channels", value=str(len(g.text_channels)), inline=True)
    embed.add_field(name="🎭 Roles",    value=str(len(g.roles)), inline=True)
    embed.add_field(name="👑 Owner",    value=g.owner.mention if g.owner else "?", inline=True)
    embed.add_field(name="📅 Created",  value=g.created_at.strftime("%d %b %Y"), inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed  = discord.Embed(title=member.display_name, color=discord.Color.from_str("#f9a8d4"))
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="🏷️ Username", value=str(member), inline=True)
    embed.add_field(name="🆔 ID",       value=str(member.id), inline=True)
    embed.add_field(name="📅 Joined",   value=member.joined_at.strftime("%d %b %Y") if member.joined_at else "?", inline=True)
    embed.add_field(name="🎭 Top Role", value=member.top_role.mention, inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! `{round(bot.latency * 1000)}ms`")

@bot.command()
async def clear(ctx):
    store.pop(ctx.channel.id, None)
    await ctx.send("🧋 Memory wiped — fresh start!")

# ──────────────────────────────────────────────
#  Error handler
# ──────────────────────────────────────────────
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to do that.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Couldn't find that member.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: `{error.param.name}`. Try `!help {ctx.command}`")
    elif isinstance(error, commands.CommandInvokeError):
        await ctx.send(f"⚠️ Error: {error.original}")
    else:
        await ctx.send(f"⚠️ {error}")

# ──────────────────────────────────────────────
#  Run
# ──────────────────────────────────────────────
if __name__ == "__main__":
    if not DISCORD_TOKEN or not GROQ_API_KEY:
        raise SystemExit("Set DISCORD_TOKEN and GROQ_API_KEY in your .env file first.")
    bot.run(DISCORD_TOKEN)
