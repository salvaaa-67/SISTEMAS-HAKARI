import asyncio
import base64
import json
import os
import re
import struct
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path

import aiohttp
import discord
import imageio_ffmpeg
from discord.ext import commands


GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
FISH_API_URL = "https://api.fish.audio"
GROQ_MODEL = "openai/gpt-oss-20b"
FISH_TTS_MODEL = "s2.1-pro-free"
MAX_RESPONSE_WORDS = 130
MAX_AUDIO_SECONDS = 59
FFMPEG_EXECUTABLE = imageio_ffmpeg.get_ffmpeg_exe()


class FishVoiceNotFoundError(RuntimeError):
    pass


class MentionAudio(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._request_semaphore = asyncio.Semaphore(2)

    async def _request_json(
        self,
        session: aiohttp.ClientSession,
        url: str,
        *,
        headers: dict[str, str],
        json_body: dict | None = None,
        params: dict[str, str] | None = None,
    ) -> dict:
        if json_body is None:
            request = session.get(url, headers=headers, params=params)
        else:
            request = session.post(url, headers=headers, json=json_body)

        async with request as response:
            if response.status >= 400:
                details = (await response.text())[:500]
                if (
                    response.status == 404
                    and url == GROQ_API_URL
                    and json_body is not None
                ):
                    raise RuntimeError(
                        "A Groq não encontrou o modelo "
                        f"`{json_body.get('model', 'desconhecido')}` "
                        f"(HTTP 404): {details}"
                    )
                raise RuntimeError(
                    f"API retornou HTTP {response.status}: {details}"
                )
            data = await response.json()
            if not isinstance(data, dict):
                raise ValueError("A API retornou uma resposta JSON inválida.")
            return data

    async def _generate_text(
        self,
        session: aiohttp.ClientSession,
        groq_api_key: str,
        prompt: str,
    ) -> str:
        data = await self._request_json(
            session,
            GROQ_API_URL,
            headers={"Authorization": f"Bearer {groq_api_key}"},
            json_body={
                "model": GROQ_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Responda em português brasileiro, de forma natural, "
                            f" com no máximo {MAX_RESPONSE_WORDS} "
                            "palavras. A resposta será falada em áudio; evite "
                            "listas, markdown, emojis e URLs. Não seja seco "
                            "demais: fale com diversão e seja amigável com "
                            "os usuários. Lembre-se: NÃO toque em assuntos "
                            "sensíveis como um usuario perguntar qual a sua API, "
                            "TOKEN, etc, oriente ele a perguntar outra coisa."
                        ),
                    },
                    {"role": "user", "content": prompt[:2000]},
                ],
                "max_completion_tokens": 512,
                "reasoning_effort": "low",
                "include_reasoning": False,
                "temperature": 0.7,
            },
        )
        try:
            choice = data["choices"][0]
            message = choice["message"]
            text = message["content"]
            if not isinstance(text, str):
                raise TypeError("O conteúdo da resposta não é texto.")
            text = text.strip()
        except (KeyError, IndexError, TypeError, AttributeError) as error:
            raise ValueError("A resposta do Groq veio em formato inválido.") from error

        words = text.split()
        if not words:
            finish_reason = choice.get("finish_reason", "desconhecido")
            raise ValueError(
                "O Groq não retornou texto final "
                f"(finish_reason={finish_reason})."
            )
        return " ".join(words[:MAX_RESPONSE_WORDS])

    async def _generate_audio(
        self,
        session: aiohttp.ClientSession,
        fish_api_key: str,
        text: str,
        voice_id: str,
    ) -> bytes:
        if not voice_id:
            raise ValueError("Nenhuma voz Fish Audio foi configurada.")
        payload = {
            "text": text,
            "format": "mp3",
            "prosody": {
                "speed": 1.05,
                "normalize_loudness": True,
            },
            "reference_id": voice_id,
        }

        async with session.post(
            f"{FISH_API_URL}/v1/tts",
            headers={
                "Authorization": f"Bearer {fish_api_key}",
                "Content-Type": "application/json",
                "model": FISH_TTS_MODEL,
            },
            json=payload,
        ) as response:
            if response.status == 404:
                details = (await response.text())[:500]
                raise FishVoiceNotFoundError(
                    "Fish Audio não encontrou a voz selecionada "
                    f"(reference_id={voice_id}). Reabra /menu e selecione "
                    f"uma voz disponível. Detalhes: {details}"
                )
            if response.status >= 400:
                details = (await response.text())[:500]
                raise RuntimeError(
                    f"Fish Audio retornou HTTP {response.status}: {details}"
                )
            audio_data = await response.read()

        if not audio_data:
            raise ValueError("O Fish Audio retornou um arquivo de áudio vazio.")
        return audio_data

    @staticmethod
    def _prepare_voice_message(audio_data: bytes) -> tuple[bytes, float, str]:
        with tempfile.TemporaryDirectory(prefix="hakari_ia_") as temp_dir:
            input_path = Path(temp_dir) / "resposta_original.mp3"
            output_path = Path(temp_dir) / "resposta.ogg"
            input_path.write_bytes(audio_data)
            result = subprocess.run(
                [
                    FFMPEG_EXECUTABLE,
                    "-y",
                    "-i",
                    str(input_path),
                    "-t",
                    str(MAX_AUDIO_SECONDS),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "48000",
                    "-c:a",
                    "libopus",
                    "-b:a",
                    "64k",
                    "-application",
                    "voip",
                    "-f",
                    "ogg",
                    str(output_path),
                ],
                capture_output=True,
                timeout=30,
                check=False,
            )
            if result.returncode != 0 or not output_path.is_file():
                raise RuntimeError(
                    "Não foi possível limitar a duração do áudio: "
                    + result.stderr.decode("utf-8", errors="replace")[-500:]
                )
            pcm_result = subprocess.run(
                [
                    FFMPEG_EXECUTABLE,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(output_path),
                    "-f",
                    "s16le",
                    "-acodec",
                    "pcm_s16le",
                    "-ac",
                    "1",
                    "-ar",
                    "8000",
                    "pipe:1",
                ],
                capture_output=True,
                timeout=30,
                check=False,
            )
            if pcm_result.returncode != 0:
                raise RuntimeError(
                    "Não foi possível analisar o áudio para a mensagem de voz: "
                    + pcm_result.stderr.decode("utf-8", errors="replace")[-500:]
                )

            pcm_data = pcm_result.stdout
            if not pcm_data or len(pcm_data) % 2:
                raise ValueError("O áudio convertido não contém amostras válidas.")

            sample_count = len(pcm_data) // 2
            samples = struct.unpack(f"<{sample_count}h", pcm_data)
            duration = sample_count / 8000
            bucket_peaks = []
            for bucket in range(256):
                start = bucket * sample_count // 256
                end = (bucket + 1) * sample_count // 256
                bucket_peaks.append(
                    max((abs(sample) for sample in samples[start:end]), default=0)
                )

            max_peak = max(bucket_peaks)
            waveform = bytes(
                round(peak * 255 / max_peak) if max_peak else 0
                for peak in bucket_peaks
            )
            return (
                output_path.read_bytes(),
                duration,
                base64.b64encode(waveform).decode("ascii"),
            )

    @staticmethod
    async def _send_voice_message(
        channel: discord.abc.Messageable,
        audio_data: bytes,
        duration: float,
        waveform: str,
    ) -> discord.Message:
        file = discord.File(BytesIO(audio_data), filename="resposta-hakari.ogg")
        state = channel._state
        with discord.http.handle_message_parameters(
            file=file,
            flags=discord.MessageFlags(voice=True),
            allowed_mentions=discord.AllowedMentions.none(),
        ) as params:
            payload = json.loads(params.multipart[0]["value"])
            payload["attachments"][0].update(
                {"duration_secs": duration, "waveform": waveform}
            )
            params.multipart[0]["value"] = json.dumps(
                payload,
                separators=(",", ":"),
            )
            data = await state.http.send_message(channel.id, params=params)
        return state.create_message(channel=channel, data=data)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if (
            message.author.bot
            or message.webhook_id is not None
            or message.guild is None
            or self.bot.user is None
            or not any(user.id == self.bot.user.id for user in message.mentions)
        ):
            return

        menu = self.bot.get_cog("Menu")
        if menu is None or not menu.module_configured(
            message.guild.id,
            "ia_audio",
        ):
            return

        prompt = re.sub(
            rf"<@!?{self.bot.user.id}>",
            "",
            message.content,
        ).strip()
        if not prompt:
            return

        voice_id = menu.ai_audio_voice_id(message.guild.id)
        if voice_id is None:
            return

        groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
        fish_api_key = os.getenv("FISH_API_KEY", "").strip()

        if not groq_api_key or not fish_api_key:
            await message.reply(
                "Para responder em áudio, configure `GROQ_API_KEY` e "
                "`FISH_API_KEY` nas variáveis do Render.",
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        timeout = aiohttp.ClientTimeout(total=90, connect=10)
        try:
            async with self._request_semaphore:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    text = await self._generate_text(
                        session,
                        groq_api_key,
                        prompt,
                    )
                    audio_data = await self._generate_audio(
                        session,
                        fish_api_key,
                        text,
                        voice_id,
                    )
                voice_audio, duration, waveform = await asyncio.to_thread(
                    self._prepare_voice_message,
                    audio_data,
                )

            await self._send_voice_message(
                message.channel,
                voice_audio,
                duration,
                waveform,
            )
        except FishVoiceNotFoundError as error:
            print(
                f"Voz Fish Audio inválida (guild={message.guild.id}, "
                f"user={message.author.id}): {error}",
                flush=True,
            )
            await menu.set_values(
                message.guild.id,
                {
                    "ia_audio_voice_id": None,
                    "ia_audio_voice_name": None,
                    "module_ia_audio": False,
                },
            )
            await message.reply(
                "A voz configurada não está mais disponível no Fish Audio. "
                "Desativei a IA em áudio neste servidor; abra `/menu` → "
                "**IA em áudio** para escolher uma voz disponível e reativar.",
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (
            aiohttp.ClientError,
            asyncio.TimeoutError,
            OSError,
            RuntimeError,
            ValueError,
            subprocess.SubprocessError,
        ) as error:
            print(
                f"Erro ao gerar resposta de IA em áudio "
                f"(guild={message.guild.id if message.guild else 'DM'}, "
                f"user={message.author.id}): "
                f"{type(error).__name__}: {error}",
                flush=True,
            )
            await message.reply(
                "Não consegui gerar o áudio agora. Tente novamente mais tarde.",
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException as error:
            print(
                f"Erro ao enviar áudio ao Discord "
                f"(channel={message.channel.id}): {error}",
                flush=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MentionAudio(bot))