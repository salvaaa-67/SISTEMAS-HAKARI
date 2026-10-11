import asyncio
from io import BytesIO
from pathlib import Path

import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError


IMAGE_SIZE = (1200, 675)
FONT_PATHS = {
    False: (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
    ),
    True: (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
    ),
}


def load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    for font_path in FONT_PATHS[bold]:
        if Path(font_path).is_file():
            return ImageFont.truetype(font_path, size)
    return ImageFont.load_default()


def wrap_text(
    text: str,
    font: ImageFont.ImageFont,
    draw: ImageDraw.ImageDraw,
    width: int,
) -> list[str]:
    lines = []
    current_line = ""
    for word in text.split():
        while draw.textbbox(
            (0, 0), word, font=font
        )[2] > width:
            split_at = len(word)
            while split_at > 1 and draw.textbbox(
                (0, 0), word[:split_at], font=font
            )[2] > width:
                split_at -= 1
            if current_line:
                lines.append(current_line)
                current_line = ""
            lines.append(word[:split_at])
            word = word[split_at:]
        candidate = f"{current_line} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= width:
            current_line = candidate
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines


def build_quote_image(avatar_data: bytes, quote: str, author: str) -> bytes:
    canvas = Image.new("RGB", IMAGE_SIZE, (9, 10, 14))
    draw = ImageDraw.Draw(canvas)
    draw.ellipse((36, 98, 505, 567), fill=(15, 16, 22))
    draw.line((540, 135, 540, 540), fill=(48, 49, 57), width=2)

    with Image.open(BytesIO(avatar_data)) as avatar_source:
        avatar = ImageOps.fit(
            avatar_source.convert("RGB"),
            (370, 370),
            method=Image.Resampling.LANCZOS,
        )
    avatar = ImageOps.grayscale(avatar).convert("RGB")
    mask = Image.new("L", avatar.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, 369, 369), fill=255)
    canvas.paste(avatar, (85, 147), mask)
    draw.ellipse((81, 143, 459, 521), outline=(66, 68, 76), width=3)

    quote = " ".join(quote.split()) or "[Mensagem sem texto]"
    max_lines = 7
    text_width = 590
    font = load_font(42)
    lines = wrap_text(quote, font, draw, text_width)
    while len(lines) > max_lines and getattr(font, "size", 18) > 22:
        font = load_font(font.size - 2)
        lines = wrap_text(quote, font, draw, text_width)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last_line = lines[-1]
        while last_line and draw.textbbox(
            (0, 0), f"{last_line}...", font=font
        )[2] > text_width:
            last_line = last_line[:-1].rstrip()
        lines[-1] = f"{last_line}..."

    line_height = getattr(font, "size", 18) + 12
    text_y = (IMAGE_SIZE[1] - len(lines) * line_height) // 2 - 34
    for line in lines:
        draw.text((590, text_y), line, font=font, fill=(238, 238, 241))
        text_y += line_height

    signature_y = text_y + 12
    signature_font = load_font(23)
    signature = f"- {author}"
    while (
        draw.textbbox((0, 0), signature, font=signature_font)[2] > text_width
        and getattr(signature_font, "size", 18) > 14
    ):
        signature_font = load_font(signature_font.size - 1)
    draw.text(
        (590, signature_y),
        signature,
        font=signature_font,
        fill=(205, 205, 211),
    )
    brand_font = load_font(18, bold=True)
    draw.text(
        (IMAGE_SIZE[0] - 52, IMAGE_SIZE[1] - 38),
        "HAKARI",
        font=brand_font,
        fill=(115, 117, 127),
        anchor="rs",
    )

    output = BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    return output.getvalue()


class Quotes(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if (
            message.guild is None
            or message.author.bot
            or message.reference is None
            or self.bot.user is None
            or not any(user.id == self.bot.user.id for user in message.mentions)
        ):
            return

        menu = self.bot.get_cog("Menu")
        if menu is None or not menu.module_configured(message.guild.id, "quotes"):
            return

        reference = message.reference
        original = reference.resolved
        if not isinstance(original, discord.Message):
            if reference.message_id is None:
                return
            channel = message.guild.get_channel_or_thread(
                reference.channel_id or message.channel.id
            )
            if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                return
            try:
                original = await channel.fetch_message(reference.message_id)
            except discord.NotFound:
                print(
                    f"Quotes: mensagem respondida não encontrada em {message.guild.id}.",
                    flush=True,
                )
                return
            except discord.HTTPException as error:
                print(
                    f"Quotes: falha ao buscar mensagem em {message.guild.id}: {error}",
                    flush=True,
                )
                return

        try:
            avatar_data = await original.author.display_avatar.read()
            image_data = await asyncio.to_thread(
                build_quote_image,
                avatar_data,
                original.content,
                original.author.display_name,
            )
            await message.channel.send(
                file=discord.File(BytesIO(image_data), filename="hakari_quote.png"),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.HTTPException, UnidentifiedImageError, OSError, ValueError) as error:
            print(
                f"Quotes: não foi possível criar a citação em {message.guild.id}: "
                f"{type(error).__name__}: {error}",
                flush=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Quotes(bot))
