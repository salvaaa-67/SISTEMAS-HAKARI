import asyncio
import array
import math
import os
import shlex
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import discord
import imageio_ffmpeg
import yt_dlp
from discord import app_commands
from discord.ext import commands

from .components_v2 import components_v2


YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'format_sort': ['+abr', '+asr'],
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'scsearch1',
    'source_address': '0.0.0.0',
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    },
    'extractor_args': {
        'youtube': {
            'player_client': ['web_creator', 'web'],
            'player_skip': ['js', 'configs', 'webpage']
        }
    }
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}
FFMPEG_EXECUTABLE = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()


class AudioLevelMonitor(discord.AudioSource):
    def __init__(
        self,
        source: discord.AudioSource,
        on_levels: Callable[[int, float], None] | None = None,
    ):
        self.source = source
        self.on_levels = on_levels
        self.frames_checked = 0
        self.sample_count = 0
        self.peak = 0
        self.sum_squares = 0
        self.logged = False

    def read(self) -> bytes:
        data = self.source.read()
        if data and self.frames_checked < 100:
            samples = array.array("h")
            samples.frombytes(data)
            if samples:
                self.peak = max(self.peak, max(abs(sample) for sample in samples))
                self.sample_count += len(samples)
                self.sum_squares += sum(sample * sample for sample in samples)
            self.frames_checked += 1

        if not self.logged and (self.frames_checked >= 100 or not data):
            rms = (
                math.sqrt(self.sum_squares / self.sample_count)
                if self.sample_count
                else 0
            )
            print(
                f"Nível PCM inicial: pico={self.peak}/32768, "
                f"RMS={rms:.0f}/32768, quadros={self.frames_checked}",
                flush=True,
            )
            if self.on_levels:
                self.on_levels(self.peak, rms)
            self.logged = True

        return data

    def is_opus(self) -> bool:
        return self.source.is_opus()

    def cleanup(self) -> None:
        self.source.cleanup()


@contextmanager
def youtube_dl_instance():
    options = YTDL_OPTIONS.copy()
    cookie_file = os.getenv("YOUTUBE_COOKIES_FILE", "").strip()
    temporary_cookie_file = None

    try:
        if cookie_file:
            source_cookie_file = Path(cookie_file)
            if not source_cookie_file.is_file():
                raise FileNotFoundError(
                    "O arquivo configurado em YOUTUBE_COOKIES_FILE não existe."
                )

            with tempfile.NamedTemporaryFile(
                prefix="youtube-cookies-",
                suffix=".txt",
                delete=False,
            ) as temporary_file:
                temporary_cookie_file = Path(temporary_file.name)
                temporary_file.write(source_cookie_file.read_bytes())

            options["cookiefile"] = str(temporary_cookie_file)

        with yt_dlp.YoutubeDL(options) as ytdl:
            yield ytdl
    finally:
        if temporary_cookie_file:
            temporary_cookie_file.unlink(missing_ok=True)


def describe_youtube_error(error: Exception) -> str:
    message = str(error)
    normalized_message = message.lower().replace("’", "'")

    if "confirm you're not a bot" in normalized_message:
        cookie_file = os.getenv("YOUTUBE_COOKIES_FILE", "").strip()
        if not cookie_file:
            return (
                "O YouTube exigiu autenticação, mas YOUTUBE_COOKIES_FILE "
                "não está definida no processo do bot. Configure no Render "
                "o caminho de um Secret File em formato Netscape e reinicie."
            )
        if not Path(cookie_file).is_file():
            return (
                "YOUTUBE_COOKIES_FILE está definida, mas o arquivo não foi "
                "encontrado no servidor. Confira o Secret File e o caminho."
            )
        return (
            "O arquivo de cookies foi encontrado, mas o YouTube ainda os "
            "recusou. Exporte cookies Netscape recentes de uma sessão "
            "conectada ao YouTube e atualize o Secret File no Render."
        )

    if isinstance(error, FileNotFoundError):
        return (
            "O arquivo de cookies configurado não foi encontrado no servidor. "
            "Confira o caminho de YOUTUBE_COOKIES_FILE."
        )

    return message


@dataclass
class Track:
    title: str
    url: str
    requested_by: str
    text_channel_id: int
    artist: str
    duration: float | None
    thumbnail: str | None
    recovery_attempts: int = 0


@dataclass
class MusicState:
    queue: list[Track] = field(default_factory=list)
    current: Track | None = None
    worker: asyncio.Task | None = None
    generation: int = 0
    volume: int = 100
    started_at: float | None = None
    elapsed: float = 0
    preparing: bool = False
    last_error: str | None = None
    last_failed_track: Track | None = None
    pcm_peak: int | None = None
    pcm_rms: float | None = None


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "Desconhecida"
    if seconds > 10 * 60 * 60:
        return "Mais de 10 horas"

    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}min {seconds}s"
    if minutes:
        return f"{minutes}min {seconds}s"
    return f"{seconds}s"


def format_elapsed(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    minutes, remainder = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}min {remainder}s"
    return f"{minutes}min {remainder}s"


def format_clock(seconds: float | None) -> str:
    if seconds is None:
        return "--:--"
    if seconds > 10 * 60 * 60:
        return "Mais de 10 horas"

    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02}:{seconds:02}"
    return f"{minutes}:{seconds:02}"


def extract_track(query: str) -> Track:
    with youtube_dl_instance() as ytdl:
        result = ytdl.extract_info(query, download=False)

    if result is None:
        raise ValueError("Não encontrei essa música.")

    if "entries" in result:
        result = next(
            (entry for entry in result["entries"] if entry is not None),
            None,
        )

    if result is None:
        raise ValueError("Não encontrei resultados para essa busca.")

    webpage_url = result.get("webpage_url") or result.get("original_url")
    if not webpage_url:
        raise ValueError("Não consegui obter o link dessa música.")

    return Track(
        title=result.get("title") or "Música sem título",
        url=webpage_url,
        requested_by="",
        text_channel_id=0,
        artist=str(
            result.get("artist")
            or result.get("creator")
            or result.get("uploader")
            or result.get("channel")
            or "Desconhecido"
        ),
        duration=result.get("duration"),
        thumbnail=result.get("thumbnail"),
    )


def extract_audio_url(url: str) -> tuple[str, dict[str, str]]:
    with youtube_dl_instance() as ytdl:
        result = ytdl.extract_info(url, download=False)

    if result is None:
        raise ValueError("Não foi possível abrir o áudio.")

    if "entries" in result:
        result = next(
            (entry for entry in result["entries"] if entry is not None),
            None,
        )

    audio_url = result.get("url") if result else None
    if not audio_url:
        raise ValueError("O YouTube não retornou um endereço de áudio.")

    audio_headers = result.get("http_headers") or {}
    return audio_url, audio_headers


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.states: dict[int, MusicState] = {}
        print(f"FFmpeg selecionado: {FFMPEG_EXECUTABLE}", flush=True)

    async def _get_requester_voice(
        self,
        interaction: discord.Interaction,
    ) -> discord.VoiceClient | None:
        if interaction.guild is None or not isinstance(
            interaction.user, discord.Member
        ):
            await interaction.response.send_message(
                "<:wrong:1554659471223947324> Esse comando só funciona dentro de um servidor.",
                ephemeral=True,
            )
            return None

        if interaction.user.voice is None or interaction.user.voice.channel is None:
            await interaction.response.send_message(
                "<:wrong:1554659471223947324> Entre em um canal de voz primeiro.",
                ephemeral=True,
            )
            return None

        voice = interaction.guild.voice_client
        if voice is None:
            await interaction.response.send_message(
                "<:wrong:1554659471223947324> Não estou em um canal de voz.",
                ephemeral=True,
            )
            return None
        elif voice.channel != interaction.user.voice.channel:
            await interaction.response.send_message(
                "<:wrong:1554659471223947324> Você precisa estar no mesmo canal de voz que eu.",
                ephemeral=True,
            )
            return None

        return voice

    def _state_for(self, guild_id: int) -> MusicState:
        return self.states.setdefault(guild_id, MusicState())

    def _track_embed(
        self,
        track: Track,
        user: discord.abc.User,
        action: str,
        timestamp,
    ) -> discord.Embed:
        embed = discord.Embed(
            title=f"<a:MusicNotes:1554875954281717761> {track.title}",
            url=track.url,
            color=discord.Color.green(),
            timestamp=timestamp,
        )
        embed.set_author(
            name="<:correct:1554659481512841267> Música adicionada à fila"
        )
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
        embed.add_field(name="Artista", value=track.artist, inline=True)
        embed.add_field(
            name="Duração",
            value=format_duration(track.duration),
            inline=True,
        )
        embed.add_field(
            name="Solicitado por",
            value=user.mention,
            inline=True,
        )
        embed.add_field(
            name="Progresso",
            value=(
                f"🔘──────────── [0:00 / {format_clock(track.duration)}]"
            ),
            inline=False,
        )
        embed.set_footer(text=f"Música {action} por {user.display_name}")
        return embed

    async def _restart_track(
        self,
        guild: discord.Guild,
        state: MusicState,
        voice: discord.VoiceClient,
        track: Track,
    ) -> None:
        worker = state.worker
        if worker and not worker.done():
            worker.cancel()
        if voice.is_playing() or voice.is_paused():
            voice.stop()
        if worker and not worker.done():
            await asyncio.gather(worker, return_exceptions=True)

        track.recovery_attempts += 1
        state.current = None
        state.started_at = None
        state.elapsed = 0
        state.preparing = False
        state.last_error = None
        state.last_failed_track = None
        state.queue.insert(0, track)
        state.worker = asyncio.create_task(self._play_queue(guild, state))

    async def _play_queue(self, guild: discord.Guild, state: MusicState) -> None:
        while state.queue:
            voice = guild.voice_client
            if voice is None or not voice.is_connected():
                break

            generation = state.generation
            track = state.queue.pop(0)
            state.current = track
            state.preparing = True
            state.pcm_peak = None
            state.pcm_rms = None
            channel = self.bot.get_channel(track.text_channel_id)

            try:
                audio_url, audio_headers = await asyncio.to_thread(
                    extract_audio_url,
                    track.url,
                )
                if generation != state.generation:
                    continue

                ffmpeg_options = FFMPEG_OPTIONS.copy()
                header_lines = "".join(
                    f"{name}: {value}\r\n"
                    for name, value in audio_headers.items()
                    if name.lower() not in {
                        "cookie",
                        "authorization",
                        "proxy-authorization",
                    }
                )
                if header_lines:
                    ffmpeg_options["before_options"] += (
                        f" -headers {shlex.quote(header_lines)}"
                    )

                source = discord.FFmpegPCMAudio(
                    audio_url,
                    executable=FFMPEG_EXECUTABLE,
                    **ffmpeg_options,
                )
                finished = asyncio.Event()

                def record_audio_levels(peak: int, rms: float) -> None:
                    state.pcm_peak = peak
                    state.pcm_rms = rms

                def after(error: Exception | None) -> None:
                    if error:
                        print(f"Erro ao reproduzir áudio: {error}", flush=True)
                    self.bot.loop.call_soon_threadsafe(finished.set)

                monitored_source = AudioLevelMonitor(source, record_audio_levels)
                volume_source = discord.PCMVolumeTransformer(
                    monitored_source,
                    volume=state.volume / 100,
                )
                voice.play(
                    volume_source,
                    after=after,
                    bitrate=256,
                    fec=False,
                    bandwidth="full",
                    signal_type="music",
                )
                state.preparing = False
                state.started_at = asyncio.get_running_loop().time()
                state.elapsed = 0
                state.last_error = None
                state.last_failed_track = None
                if channel:
                    await channel.send(
                        f"▶️ Tocando agora: "
                        f"<a:MusicNotes:1554875954281717761> **{track.title}**"
                    )
                await finished.wait()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                state.last_error = f"{type(error).__name__}: {error}"
                state.last_failed_track = track
                print(
                    f"Erro ao reproduzir '{track.title}': {error}",
                    flush=True,
                )
                if channel:
                    await channel.send(
                        f"<:wrong:1554659471223947324> Não consegui reproduzir "
                        f"<a:MusicNotes:1554875954281717761> **{track.title}**. "
                        f"{describe_youtube_error(error)}"
                    )
            finally:
                state.preparing = False
                state.current = None
                state.started_at = None
                state.elapsed = 0

        if not state.queue:
            state.worker = None

    @app_commands.command(name="play", description="Toca uma música do YouTube")
    @app_commands.describe(busca="Link do YouTube ou nome da música")
    async def play(self, interaction: discord.Interaction, busca: str) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "<:wrong:1554659471223947324> Esse comando só funciona dentro de um servidor.",
                ephemeral=True,
            )
            return

        if not isinstance(interaction.user, discord.Member) or interaction.user.voice is None:
            await interaction.response.send_message(
                "<:wrong:1554659471223947324> Entre em um canal de voz primeiro.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        try:
            track = await asyncio.to_thread(extract_track, busca)
        except Exception as error:
            await interaction.followup.send(
                f"<:wrong:1554659471223947324> Não encontrei essa música: "
                f"{describe_youtube_error(error)}"
            )
            return

        try:
            voice = interaction.guild.voice_client
            if voice is None:
                voice = await interaction.user.voice.channel.connect()
            elif voice.channel != interaction.user.voice.channel:
                await interaction.followup.send(
                    "<:wrong:1554659471223947324> Você precisa estar no mesmo canal de voz que eu."
                )
                return
        except (discord.ClientException, discord.HTTPException) as error:
            await interaction.followup.send(
                f"<:wrong:1554659471223947324> Não consegui entrar no canal: {error}"
            )
            return

        track.requested_by = interaction.user.mention
        track.text_channel_id = interaction.channel_id
        state = self._state_for(interaction.guild.id)
        state.queue.append(track)

        if state.worker is None or state.worker.done():
            state.worker = asyncio.create_task(self._play_queue(interaction.guild, state))
        embed = self._track_embed(
            track,
            interaction.user,
            "adicionada",
            interaction.created_at,
        )
        await interaction.followup.send(view=components_v2(embed))

    @app_commands.command(name="pause", description="Pausa a música atual")
    async def pause(self, interaction: discord.Interaction) -> None:
        voice = await self._get_requester_voice(interaction)
        if voice is None:
            return
        if not voice.is_playing():
            await interaction.response.send_message(
                "<:wrong:1554659471223947324> Não há música tocando.",
                ephemeral=True,
            )
            return
        state = self._state_for(interaction.guild.id)
        loop = asyncio.get_running_loop()
        if state.started_at is not None:
            state.elapsed += loop.time() - state.started_at
            state.started_at = None
        voice.pause()
        await interaction.response.send_message(
            f"<:Pause:1554875566530764842> Música pausada em "
            f"{format_elapsed(state.elapsed)}"
        )

    @app_commands.command(name="resume", description="Retoma a música pausada")
    async def resume(self, interaction: discord.Interaction) -> None:
        voice = await self._get_requester_voice(interaction)
        if voice is None:
            return
        if not voice.is_paused():
            await interaction.response.send_message(
                "<:wrong:1554659471223947324> A música não está pausada.",
                ephemeral=True,
            )
            return
        voice.resume()
        state = self._state_for(interaction.guild.id)
        state.started_at = asyncio.get_running_loop().time()
        await interaction.response.send_message(
            "<:resume:1554875578472071188> Música retomada."
        )

    @app_commands.command(name="skip", description="Pula para a próxima música")
    async def skip(self, interaction: discord.Interaction) -> None:
        voice = await self._get_requester_voice(interaction)
        if voice is None:
            return
        state = self.states.get(interaction.guild.id)
        if (
            state is None
            or state.current is None
            or (not voice.is_playing() and not voice.is_paused())
        ):
            await interaction.response.send_message(
                "<:wrong:1554659471223947324> Não há música tocando.",
                ephemeral=True,
            )
            return
        current_track = state.current
        next_track = state.queue[0] if state.queue else None
        next_title = (
            f"<a:MusicNotes:1554875954281717761> **{next_track.title}**"
            if next_track
            else "a fila acabou"
        )
        embed = discord.Embed(
            title="⏭️ Música pulada",
            description=(
                f"<a:MusicNotes:1554875954281717761> **{current_track.title}** "
                f"foi pulada para {next_title}."
            ),
            color=discord.Color.yellow(),
            timestamp=interaction.created_at,
        )
        if current_track.thumbnail:
            embed.set_thumbnail(url=current_track.thumbnail)
        embed.add_field(name="Artista", value=current_track.artist, inline=True)
        if next_track:
            embed.add_field(
                name="Próxima música",
                value=f"<a:MusicNotes:1554875954281717761> {next_track.title}",
                inline=True,
            )
        embed.set_footer(text=f"Música pulada por {interaction.user.display_name}")
        voice.stop()
        await interaction.response.send_message(view=components_v2(embed))

    @app_commands.command(name="stop", description="Para a música e limpa a fila")
    async def stop(self, interaction: discord.Interaction) -> None:
        voice = await self._get_requester_voice(interaction)
        if voice is None:
            return
        state = self._state_for(interaction.guild.id)
        stopped_track = state.current
        cleared_count = len(state.queue)
        state.queue.clear()
        state.current = None
        state.generation += 1
        state.started_at = None
        state.elapsed = 0
        if voice.is_playing() or voice.is_paused():
            voice.stop()

        embed = discord.Embed(
            title="⏹️ Reprodução parada",
            description=(
                f"<a:MusicNotes:1554875954281717761> **{stopped_track.title}** "
                "foi interrompida."
                if stopped_track
                else "O player foi parado."
            ),
            color=discord.Color.red(),
            timestamp=interaction.created_at,
        )
        embed.add_field(
            name="Fila limpa",
            value=f"{cleared_count} música(s) removida(s)",
            inline=True,
        )
        embed.set_footer(text=f"Player parado por {interaction.user.display_name}")
        await interaction.response.send_message(view=components_v2(embed))

    @app_commands.command(name="volume", description="Altera o volume do player")
    @app_commands.describe(percentual="Volume entre 1 e 100")
    async def volume(
        self,
        interaction: discord.Interaction,
        percentual: app_commands.Range[int, 1, 100],
    ) -> None:
        voice = await self._get_requester_voice(interaction)
        if voice is None:
            return

        state = self._state_for(interaction.guild.id)
        old_volume = state.volume
        state.volume = percentual
        source = voice.source
        if isinstance(source, discord.PCMVolumeTransformer):
            source.volume = percentual / 100

        filled_blocks = round(percentual / 10)
        volume_bar = f"{'▰' * filled_blocks}{'▱' * (10 - filled_blocks)}"
        embed = discord.Embed(
            title="🔊 Volume atualizado",
            description=f"`{volume_bar}` **{percentual}%**",
            color=discord.Color.blue(),
            timestamp=interaction.created_at,
        )
        embed.add_field(name="Antes", value=f"{old_volume}%", inline=True)
        embed.add_field(name="Agora", value=f"{percentual}%", inline=True)
        embed.set_footer(text=f"Ajustado por {interaction.user.display_name}")
        await interaction.response.send_message(view=components_v2(embed))

    @app_commands.command(
        name="infoplayer",
        description="Mostra informações e comandos do player de música",
    )
    async def infoplayer(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "<:wrong:1554659471223947324> Esse comando só funciona dentro de um servidor.",
                ephemeral=True,
            )
            return

        voice = interaction.guild.voice_client
        state = self.states.get(interaction.guild.id)
        latency_ms = self.bot.latency * 1000

        if voice is None or not voice.is_connected():
            player_status = "Desconectado da call"
        elif voice.is_playing():
            player_status = "Tocando"
        elif voice.is_paused():
            player_status = "Pausado"
        elif state and state.preparing:
            player_status = "Carregando música"
        else:
            player_status = "Conectado, sem reprodução"

        embed = discord.Embed(
            title="<:info:1554875585359118547> Informações do player",
            description="Status e comandos disponíveis para o player de música.",
            color=discord.Color.green(),
            timestamp=interaction.created_at,
        )
        embed.add_field(name="Fornecedor", value="SoundCloud", inline=True)
        embed.add_field(
            name="Qualidade",
            value="256 Kbps · Áudio de qualidade ótima",
            inline=True,
        )
        embed.add_field(
            name="Latência do bot",
            value=f"{latency_ms:.0f} ms",
            inline=True,
        )
        embed.add_field(name="Estado do SoundCloud", value=player_status, inline=True)
        embed.add_field(
            name="Canal de voz",
            value=voice.channel.mention if voice and voice.is_connected() else "Nenhum",
            inline=True,
        )
        embed.add_field(
            name="Comandos de música",
            value=(
                "`/play` · `/pause` · `/resume` · `/skip` · `/stop`\n"
                "`/volume` · `/queue` · `/leave` · `/autofix` · `/infoplayer`"
            ),
            inline=False,
        )
        embed.add_field(
            name="Auto recuperação",
            value="Se o bot travar, use `/autofix` para tentar consertar o player.",
            inline=False,
        )
        embed.set_footer(text=f"Solicitado por {interaction.user.display_name}")
        await interaction.response.send_message(
            view=components_v2(embed), ephemeral=True
        )

    @app_commands.command(
        name="autofix",
        description="Verifica e tenta recuperar o player de música",
    )
    async def autofix(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not isinstance(
            interaction.user, discord.Member
        ):
            await interaction.response.send_message(
                "<:wrong:1554659471223947324> Esse comando só funciona dentro de um servidor.",
                ephemeral=True,
            )
            return

        member_voice = interaction.user.voice
        if member_voice is None or member_voice.channel is None:
            await interaction.response.send_message(
                "<:wrong:1554659471223947324> Entre em um canal de voz para verificar o player.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        state = self._state_for(guild.id)
        voice = guild.voice_client
        connection_repaired = False

        try:
            if voice is None or not voice.is_connected():
                voice = await member_voice.channel.connect()
                connection_repaired = True
            elif voice.channel != member_voice.channel:
                await voice.move_to(member_voice.channel)
                connection_repaired = True
        except (discord.ClientException, discord.HTTPException) as error:
            await interaction.followup.send(
                "<:wrong:1554659471223947324> Não consegui recuperar a conexão de voz. "
                f"Chame o desenvolvedor para corrigir. ({error})",
                ephemeral=True,
            )
            return

        track_to_retry = state.last_failed_track
        if track_to_retry is None and state.current is not None:
            playback_stopped = (
                not voice.is_playing()
                and not voice.is_paused()
                and not state.preparing
            )
            stream_is_silent = (
                voice.is_playing()
                and state.pcm_rms is not None
                and state.pcm_rms < 50
            )
            if connection_repaired or playback_stopped or stream_is_silent:
                track_to_retry = state.current

        if track_to_retry is not None:
            if track_to_retry.recovery_attempts >= 1:
                detail = state.last_error or "a faixa continuou sem áudio após a retentativa"
                await interaction.followup.send(
                    "<:wrong:1554659471223947324> O player já tentou recuperar "
                    "essa faixa uma vez, mas não "
                    f"conseguiu. Chame o desenvolvedor para corrigir. ({detail})",
                    ephemeral=True,
                )
                return

            await self._restart_track(guild, state, voice, track_to_retry)
            await interaction.followup.send(
                f"Player recuperado; reiniciei "
                f"<a:MusicNotes:1554875954281717761> **{track_to_retry.title}** "
                "uma vez para testar o áudio.",
                ephemeral=True,
            )
            return

        if state.queue and (state.worker is None or state.worker.done()):
            state.worker = asyncio.create_task(self._play_queue(guild, state))
            await interaction.followup.send(
                "Encontrei músicas na fila sem um processo ativo e reiniciei o player.",
                ephemeral=True,
            )
            return

        if state.preparing:
            await interaction.followup.send(
                "O player está carregando a faixa. Aguarde alguns segundos e verifique novamente.",
                ephemeral=True,
            )
            return

        if voice.is_playing() and state.pcm_rms is not None and state.pcm_rms >= 50:
            await interaction.followup.send(
                "A conexão e o stream estão ativos, e o player está recebendo áudio. "
                "Não encontrei uma falha que possa corrigir automaticamente; "
                "se continuar sem som, chame o desenvolvedor.",
                ephemeral=True,
            )
            return

        if voice.is_paused():
            await interaction.followup.send(
                "O player está pausado intencionalmente; use `/resume` para continuar.",
                ephemeral=True,
            )
            return

        result = (
            "Conexão de voz restaurada. Não há música tocando agora."
            if connection_repaired
            else "Não encontrei erro ativo no player nem uma faixa para recuperar."
        )
        await interaction.followup.send(result, ephemeral=True)

    @app_commands.command(name="queue", description="Mostra a fila de músicas")
    async def queue(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "<:wrong:1554659471223947324> Esse comando só funciona dentro de um servidor.",
                ephemeral=True,
            )
            return

        state = self.states.get(interaction.guild.id)
        if state is None or (state.current is None and not state.queue):
            await interaction.response.send_message("A fila está vazia.")
            return

        lines = []
        if state.current:
            lines.append(
                f"▶️ Tocando: <a:MusicNotes:1554875954281717761> "
                f"**{state.current.title}**"
            )
        lines.extend(
            f"{index}. <a:MusicNotes:1554875954281717761> {track.title} "
            f"(pedido por {track.requested_by})"
            for index, track in enumerate(state.queue, start=1)
        )
        await interaction.response.send_message("\n".join(lines)[:1900])

    @app_commands.command(name="leave", description="Desconecta do canal de voz")
    async def leave(self, interaction: discord.Interaction) -> None:
        voice = await self._get_requester_voice(interaction)
        if voice is None:
            return

        await interaction.response.defer(ephemeral=True)
        state = self.states.pop(interaction.guild.id, None)
        if state:
            state.queue.clear()
            if state.worker and not state.worker.done():
                state.worker.cancel()
        voice.stop()
        await voice.disconnect()
        await interaction.delete_original_response()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))