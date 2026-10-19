import asyncio
import re
from io import BytesIO
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands
from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError


IMAGE_SIZE = (1200, 800)
DEFAULT_QUOTE_STYLE = {
    "background_mode": "solid",
    "background_color": "#000000",
    "gradient_color": "#252542",
    "text_color": "#EEEEF1",
    "signature_color": "#CDCDD3",
    "font": "default",
    "avatar_position": "left",
    "avatar_grayscale": True,
}
FONT_URLS = {
    "roboto": ("Roboto", "roboto/Roboto[wdth,wght].ttf"),
    "open_sans": ("Open Sans", "opensans/OpenSans[wdth,wght].ttf"),
    "lato": ("Lato", "lato/Lato-Regular.ttf"),
    "montserrat": ("Montserrat", "montserrat/Montserrat[wght].ttf"),
    "poppins": ("Poppins", "poppins/Poppins-Regular.ttf"),
    "oswald": ("Oswald", "oswald/Oswald[wght].ttf"),
    "playfair_display": ("Playfair Display", "playfairdisplay/PlayfairDisplay[wght].ttf"),
    "merriweather": (
        "Merriweather",
        "merriweather/Merriweather[opsz,wdth,wght].ttf",
    ),
    "lora": ("Lora", "lora/Lora[wght].ttf"),
    "raleway": ("Raleway", "raleway/Raleway[wght].ttf"),
    "nunito": ("Nunito", "nunito/Nunito[wght].ttf"),
    "fira_sans": ("Fira Sans", "firasans/FiraSans-Regular.ttf"),
    "pacifico": ("Pacifico", "pacifico/Pacifico-Regular.ttf"),
    "bebas_neue": ("Bebas Neue", "bebasneue/BebasNeue-Regular.ttf"),
    "anton": ("Anton", "anton/Anton-Regular.ttf"),
    "comfortaa": ("Comfortaa", "comfortaa/Comfortaa[wght].ttf"),
    "caveat": ("Caveat", "caveat/Caveat[wght].ttf"),
    "dancing_script": ("Dancing Script", "dancingscript/DancingScript[wght].ttf"),
    "lobster": ("Lobster", "lobster/Lobster-Regular.ttf"),
    "bangers": ("Bangers", "bangers/Bangers-Regular.ttf"),
}
FONT_CACHE: dict[str, bytes] = {}
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


async def fetch_quote_font(font_name: str) -> bytes | None:
    if font_name == "default":
        return None
    if font_name not in FONT_URLS:
        raise ValueError(f"Fonte de Quotes desconhecida: {font_name}")
    if font_name in FONT_CACHE:
        return FONT_CACHE[font_name]

    _, font_path = FONT_URLS[font_name]
    url = f"https://raw.githubusercontent.com/google/fonts/main/ofl/{font_path}"
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            response.raise_for_status()
            font_data = await response.read()
    if not font_data or len(font_data) > 8 * 1024 * 1024:
        raise ValueError(f"Arquivo inválido para a fonte {font_name}.")
    ImageFont.truetype(BytesIO(font_data), 24)
    FONT_CACHE[font_name] = font_data
    return font_data


def load_font(
    size: int,
    bold: bool = False,
    font_data: bytes | None = None,
) -> ImageFont.ImageFont:
    if font_data is not None:
        return ImageFont.truetype(BytesIO(font_data), size)
    for font_path in FONT_PATHS[bold]:
        if Path(font_path).is_file():
            return ImageFont.truetype(font_path, size)
    return ImageFont.load_default()


def quote_style_with_defaults(style: dict | None) -> dict:
    resolved = DEFAULT_QUOTE_STYLE.copy()
    if isinstance(style, dict):
        resolved.update(style)
    if resolved["background_mode"] not in {"solid", "gradient"}:
        resolved["background_mode"] = DEFAULT_QUOTE_STYLE["background_mode"]
    if resolved["font"] not in {"default", *FONT_URLS}:
        resolved["font"] = DEFAULT_QUOTE_STYLE["font"]
    if resolved["avatar_position"] not in {
        "left",
        "right",
        "top",
        "bottom",
        "hidden",
    }:
        resolved["avatar_position"] = DEFAULT_QUOTE_STYLE["avatar_position"]
    for color_key in (
        "background_color",
        "gradient_color",
        "text_color",
        "signature_color",
    ):
        try:
            ImageColor.getrgb(resolved[color_key])
        except (TypeError, ValueError):
            resolved[color_key] = DEFAULT_QUOTE_STYLE[color_key]
    resolved["avatar_grayscale"] = bool(resolved["avatar_grayscale"])
    return resolved


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


def build_quote_image(
    avatar_data: bytes | None,
    quote: str,
    author: str,
    style: dict | None = None,
    font_data: bytes | None = None,
) -> bytes:
    style = quote_style_with_defaults(style)
    first_color = ImageColor.getrgb(style["background_color"])
    canvas = Image.new("RGB", IMAGE_SIZE, first_color)
    if style["background_mode"] == "gradient":
        second_color = ImageColor.getrgb(style["gradient_color"])
        gradient_draw = ImageDraw.Draw(canvas)
        for y in range(IMAGE_SIZE[1]):
            blend = y / max(IMAGE_SIZE[1] - 1, 1)
            color = tuple(
                round(start + (end - start) * blend)
                for start, end in zip(first_color, second_color)
            )
            gradient_draw.line((0, y, IMAGE_SIZE[0], y), fill=color)
    draw = ImageDraw.Draw(canvas)

    position = style["avatar_position"]
    text_left, text_width = 100, 1000
    if avatar_data and position != "hidden":
        if position in {"left", "right"}:
            avatar_size = 360
            avatar_origin = (70, 220) if position == "left" else (770, 220)
            text_left, text_width = (
                (500, 630) if position == "left" else (70, 630)
            )
        else:
            avatar_size = 250
            avatar_origin = (475, 35) if position == "top" else (475, 515)
            text_left, text_width = 100, 1000

        with Image.open(BytesIO(avatar_data)) as avatar_source:
            avatar = ImageOps.fit(
                avatar_source.convert("RGB"),
                (avatar_size, avatar_size),
                method=Image.Resampling.LANCZOS,
            )
        if style["avatar_grayscale"]:
            avatar = ImageOps.grayscale(avatar).convert("RGB")
        mask = Image.new("L", avatar.size, 0)
        ImageDraw.Draw(mask).ellipse(
            (0, 0, avatar_size - 1, avatar_size - 1), fill=255
        )
        canvas.paste(avatar, avatar_origin, mask)

    quote = " ".join(quote.split()) or "[Mensagem sem texto]"
    max_lines = 7 if position in {"left", "right"} else 9
    text_center = text_left + text_width // 2
    font = load_font(42, font_data=font_data)
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
    text_block_height = len(lines) * line_height
    if position == "top":
        text_area_top, text_area_bottom = 320, IMAGE_SIZE[1] - 30
    elif position == "bottom":
        text_area_top, text_area_bottom = 30, 475
    else:
        text_area_top, text_area_bottom = 40, IMAGE_SIZE[1] - 70
    text_y = text_area_top + max(
        0, (text_area_bottom - text_area_top - text_block_height) // 2
    )
    for line in lines:
        draw.text(
            (text_center, text_y),
            line,
            font=font,
            fill=style["text_color"],
            anchor="mt",
        )
        text_y += line_height

    signature_y = text_y + 12
    signature_font = load_font(23, font_data=font_data)
    signature = f"- {author}"
    while (
        draw.textbbox((0, 0), signature, font=signature_font)[2] > text_width
        and getattr(signature_font, "size", 18) > 14
    ):
        signature_font = load_font(signature_font.size - 1)
    draw.text(
        (text_center, signature_y),
        signature,
        font=signature_font,
        fill=style["signature_color"],
        anchor="mt",
    )
    brand_font = load_font(18, bold=True, font_data=font_data)
    draw.text(
        (IMAGE_SIZE[0] - 52, IMAGE_SIZE[1] - 38),
        "HAKARI",
        font=brand_font,
        fill=style["signature_color"],
        anchor="rs",
    )

    output = BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    return output.getvalue()


class QuoteMessageView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Remover Quote",
        style=discord.ButtonStyle.danger,
        custom_id="quotes:remove:v1",
    )
    async def remove_quote(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        guild = interaction.guild
        is_owner = guild is not None and interaction.user.id == guild.owner_id
        is_administrator = (
            isinstance(interaction.user, discord.Member)
            and interaction.user.guild_permissions.administrator
        )
        if not is_owner and not is_administrator:
            return await interaction.response.send_message(
                "Somente administradores ou o dono do servidor podem remover este Quote.",
                ephemeral=True,
            )
        if interaction.message is None:
            return await interaction.response.send_message(
                "Não foi possível encontrar a mensagem deste Quote.",
                ephemeral=True,
            )
        try:
            await interaction.message.delete()
        except discord.NotFound:
            await interaction.response.send_message(
                "Este Quote já foi removido.", ephemeral=True
            )
        except discord.HTTPException as error:
            print(
                f"Quotes: falha ao remover mensagem em {interaction.guild_id}: "
                f"{type(error).__name__}: {error}",
                flush=True,
            )
            await interaction.response.send_message(
                "Não foi possível remover este Quote. Verifique as permissões do bot.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "Quote removido.", ephemeral=True
            )


class Quotes(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(QuoteMessageView())

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

        content_without_mention = re.sub(
            rf"<@!?{self.bot.user.id}>",
            "",
            message.content,
        ).strip()
        if content_without_mention:
            return

        menu = self.bot.get_cog("Menu")
        if menu is None or not menu.module_configured(message.guild.id, "quotes"):
            return

        destination = message.channel
        destination_channel_id = menu.get_value(
            message.guild.id, "quotes_channel"
        )
        if destination_channel_id is not None:
            destination = message.guild.get_channel(int(destination_channel_id))
            if not isinstance(destination, discord.TextChannel):
                print(
                    f"Quotes: canal configurado não encontrado em {message.guild.id}.",
                    flush=True,
                )
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
            style = menu.get_value(
                message.guild.id, "quotes_style", DEFAULT_QUOTE_STYLE
            )
            font_data = await fetch_quote_font(
                quote_style_with_defaults(style)["font"]
            )
            image_data = await asyncio.to_thread(
                build_quote_image,
                avatar_data,
                original.content,
                original.author.display_name,
                style,
                font_data,
            )
            await destination.send(
                file=discord.File(BytesIO(image_data), filename="hakari_quote.png"),
                view=QuoteMessageView(),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (
            aiohttp.ClientError,
            asyncio.TimeoutError,
            discord.HTTPException,
            UnidentifiedImageError,
            OSError,
            ValueError,
        ) as error:
            print(
                f"Quotes: não foi possível criar a citação em {message.guild.id}: "
                f"{type(error).__name__}: {error}",
                flush=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Quotes(bot))
