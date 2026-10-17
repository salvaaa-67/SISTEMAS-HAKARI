import asyncio
import os
import re
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
MAX_RESPONSE_WORDS = 40
MAX_AUDIO_SECONDS = 29
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
                            f"clara e direta, com no máximo {MAX_RESPONSE_WORDS} "
                            "palavras. A resposta será falada em áudio; evite "
                            "listas, markdown, emojis e URLs."
                        ),
                    },
                    {"role": "user", "content": prompt[:2000]},
                ],
                "max_tokens": 110,
                "temperature": 0.7,
            },
        )
        try:
            text = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError, AttributeError) as error:
            raise ValueError("A resposta do Groq veio em formato inválido.") from error

        words = text.split()
        if not words:
            raise ValueError("O Groq retornou uma resposta vazia.")
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
    def _trim_audio(audio_data: bytes) -> bytes:
        with tempfile.TemporaryDirectory(prefix="hakari_ia_") as temp_dir:
            input_path = Path(temp_dir) / "resposta_original.mp3"
            output_path = Path(temp_dir) / "resposta.mp3"
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
                    "-codec:a",
                    "libmp3lame",
                    "-b:a",
                    "128k",
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
            return output_path.read_bytes()

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
                bounded_audio = await asyncio.to_thread(
                    self._trim_audio,
                    audio_data,
                )

            await message.channel.send(
                file=discord.File(
                    BytesIO(bounded_audio),
                    filename="resposta-hakari.mp3",
                ),
                allowed_mentions=discord.AllowedMentions.none(),
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