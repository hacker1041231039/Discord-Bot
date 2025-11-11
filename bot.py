import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import os
import asyncio

os.environ["PATH"] += os.pathsep + r"D:/Discord Bot/ffmpeg/bin"

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Struktur queue per guild
music_queues = {}
panel_messages = {}  # pesan panel aktif per guild

# ======================
# Ready event
# ======================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"🔁 Synced {len(synced)} commands")
    except Exception as e:
        print(f"Error syncing commands: {e}")

# ======================
# Fungsi bantu untuk play/next
# ======================
async def play_next(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if music_queues.get(guild_id):
        next_song = music_queues[guild_id].pop(0)
        await play_audio(interaction, next_song['url'], next_song['title'])
    else:
        voice_client = interaction.guild.voice_client
        if voice_client:
            await voice_client.disconnect()
            print(f"💤 Auto disconnect dari {voice_client.channel.name}")

async def play_audio(interaction, url, title):
    voice_client = interaction.guild.voice_client
    if not voice_client:
        await interaction.followup.send("❌ Bot belum bergabung ke voice channel.")
        return

    ffmpeg_opts = {
        'options': '-vn',
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
    }

    source = discord.FFmpegPCMAudio(
        url,
        executable=r"D:/Discord Bot/ffmpeg/bin/ffmpeg.exe",
        **ffmpeg_opts
    )

    def after_play(err):
        if err:
            print(f"Error saat play: {err}")
        fut = asyncio.run_coroutine_threadsafe(play_next(interaction), bot.loop)
        try:
            fut.result()
        except Exception as e:
            print(f"Error after play: {e}")

    voice_client.play(source, after=after_play)
    embed = discord.Embed(
        title="🎶 Sekarang Memutar",
        description=f"**{title}**",
        color=discord.Color.blue()
    )
    msg = await interaction.followup.send(embed=embed, view=MusicControlView(interaction))
    panel_messages[interaction.guild.id] = msg
    await refresh_panel(interaction, title)


# ======================
# /join command
# ======================
@bot.tree.command(name="join", description="Bot bergabung ke voice channel kamu")
async def join_channel(interaction: discord.Interaction):
    if interaction.user.voice is None:
        await interaction.response.send_message("❌ Kamu harus berada di voice channel dulu!")
        return

    channel = interaction.user.voice.channel
    if interaction.guild.voice_client:
        await interaction.response.send_message("⚠️ Aku sudah berada di voice channel.")
        return

    await channel.connect()
    await interaction.response.send_message(f"✅ Bergabung ke **{channel.name}**")

# ======================
# /play command
# ======================
@bot.tree.command(name="play", description="Memutar lagu dari judul atau link YouTube")
@app_commands.describe(query="Judul atau link YouTube")
async def play_song(interaction: discord.Interaction, query: str):
    await interaction.response.defer()

    voice_client = interaction.guild.voice_client
    if voice_client is None:
        if interaction.user.voice is None:
            await interaction.followup.send("❌ Kamu harus berada di voice channel atau gunakan /join dulu.")
            return
        else:
            channel = interaction.user.voice.channel
            voice_client = await channel.connect()

    guild_id = interaction.guild.id
    if guild_id not in music_queues:
        music_queues[guild_id] = []

    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'default_search': 'ytsearch'
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            if not any(x in query for x in ["youtube.com", "youtu.be"]):
                query = f"ytsearch:{query}"
            info = ydl.extract_info(query, download=False)
            if 'entries' in info:
                info = info['entries'][0]

            url = info['url']
            title = info.get('title', 'Tanpa Judul')

        # Jika sedang memutar musik → masukkan ke antrian
        if voice_client.is_playing() or voice_client.is_paused():
            music_queues[guild_id].append({'url': url, 'title': title})
            await interaction.followup.send(f"➕ Lagu **{title}** ditambahkan ke antrian.")
        else:
            await play_audio(interaction, url, title)

    except Exception as e:
        print(f"Error: {e}")
        await interaction.followup.send("❌ Gagal memutar lagu. Pastikan link/judul valid dan FFmpeg sudah terpasang.")

# ======================
# /queue command
# ======================
@bot.tree.command(name="queue", description="Menampilkan daftar antrian lagu")
async def show_queue(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    queue = music_queues.get(guild_id, [])
    if not queue:
        await interaction.response.send_message("📭 Antrian kosong.")
        return

    msg = "\n".join([f"{i+1}. {q['title']}" for i, q in enumerate(queue)])
    await interaction.response.send_message(f"📜 **Daftar Antrian Lagu:**\n{msg}")

# ======================
# /skip command
# ======================
@bot.tree.command(name="skip", description="Melewati lagu saat ini")
async def skip_song(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await interaction.response.send_message("⏭️ Lagu dilewati.")
    else:
        await interaction.response.send_message("❌ Tidak ada lagu yang sedang diputar.")

# ======================
# /pause command
# ======================
@bot.tree.command(name="pause", description="Menjeda lagu yang sedang diputar")
async def pause_song(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        await interaction.response.send_message("⏸️ Lagu dijeda.")
    else:
        await interaction.response.send_message("❌ Tidak ada lagu yang sedang diputar.")

# ======================
# /resume command
# ======================
@bot.tree.command(name="resume", description="Melanjutkan lagu yang dijeda")
async def resume_song(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        await interaction.response.send_message("▶️ Lagu dilanjutkan.")
    else:
        await interaction.response.send_message("❌ Tidak ada lagu yang dijeda.")

# ======================
# /leave command
# ======================
@bot.tree.command(name="leave", description="Bot keluar dari voice channel")
async def leave_channel(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client is None:
        await interaction.response.send_message("❌ Aku tidak sedang di voice channel.")
        return

    await voice_client.disconnect()
    await interaction.response.send_message("👋 Keluar dari voice channel.")

# ======================
# Auto leave kalau channel kosong
# ======================
@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return

    voice_client = member.guild.voice_client
    if voice_client and len(voice_client.channel.members) == 1:
        await voice_client.disconnect()
        print(f"💤 Keluar otomatis dari {voice_client.channel.name} (channel kosong)")


# ======================
# Tampilan tombol interaktif (panel musik)
# ======================
class MusicControlView(discord.ui.View):
    def __init__(self, interaction: discord.Interaction):
        super().__init__(timeout=None)
        self.interaction = interaction

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.secondary, emoji="⏸️")
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            await interaction.response.send_message("⏸️ Lagu dijeda.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Tidak ada lagu yang sedang diputar.", ephemeral=True)

    @discord.ui.button(label="Resume", style=discord.ButtonStyle.success, emoji="▶️")
    async def resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            await interaction.response.send_message("▶️ Lagu dilanjutkan.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Tidak ada lagu yang dijeda.", ephemeral=True)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.primary, emoji="⏭️")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.stop()
            await interaction.response.send_message("⏭️ Lagu dilewati.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Tidak ada lagu yang sedang diputar.", ephemeral=True)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, emoji="⏹️")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = interaction.guild.voice_client
        guild_id = interaction.guild.id
        if voice_client:
            if guild_id in music_queues:
                music_queues[guild_id].clear()
            voice_client.stop()
            await interaction.response.send_message("⏹️ Pemutaran dihentikan dan antrian dikosongkan.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Bot tidak sedang memutar lagu.", ephemeral=True)

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.secondary, emoji="🚪")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = interaction.guild.voice_client
        if voice_client:
            await voice_client.disconnect()
            await interaction.response.send_message("👋 Bot keluar dari voice channel.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Bot tidak sedang di voice channel.", ephemeral=True)

# ======================
# Auto-refresh panel saat lagu berganti
# ======================
async def refresh_panel(interaction: discord.Interaction, title: str):
    guild_id = interaction.guild.id
    voice_client = interaction.guild.voice_client

    if not voice_client or not voice_client.is_connected():
        return

    volume = volume_levels.get(guild_id, 1.0)
    embed = discord.Embed(
        title="🎶 Sekarang Memutar",
        description=f"**{title}**",
        color=discord.Color.blurple()
    )
    embed.add_field(name="Volume", value=f"{int(volume * 100)}%", inline=True)

    queue = music_queues.get(guild_id, [])
    if queue:
        upcoming = "\n".join([f"{i+1}. {q['title']}" for i, q in enumerate(queue[:5])])
        embed.add_field(name="Lagu Berikutnya", value=upcoming, inline=False)

    # Perbarui panel lama (kalau ada)
    if guild_id in panel_messages:
        msg = panel_messages[guild_id]
        try:
            await msg.edit(embed=embed, view=MusicControlView(interaction))
        except discord.errors.NotFound:
            panel_messages[guild_id] = await interaction.followup.send(embed=embed, view=MusicControlView(interaction))
    else:
        msg = await interaction.followup.send(embed=embed, view=MusicControlView(interaction))
        panel_messages[guild_id] = msg

# ======================
# Jalankan bot
# ======================
bot.run("MTMzOTk3NDI5MTI3NzYxNTEzNA.GYYhjv.wy-7kwylDF9PoZyopsRoftMumOxHqlHju-awUQ")
