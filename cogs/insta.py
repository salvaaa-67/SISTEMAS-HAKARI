import asyncio
import os
import tempfile
from pathlib import Path

import aiohttp
import asyncpg
import discord
from discord.ext import commands

from .components_v2 import ComponentsV2View, components_v2


MAX_IMAGE_BYTES = 1024 ** 3
ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
COMMENTS_PER_PAGE = 100


class CommentModal(discord.ui.Modal):
    def __init__(self, cog: "Insta", post_id: int):
        super().__init__(title="Comentar publicação")
        self.cog = cog
        self.post_id = post_id
        self.comment_input = discord.ui.TextInput(
            label="Seu comentário",
            placeholder="Escreva um comentário",
            style=discord.TextStyle.paragraph,
            max_length=500,
            required=True,
        )
        self.add_item(self.comment_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if self.cog.pool is None:
            return await interaction.response.send_message(
                "O Instagram está indisponível porque o banco de dados não conectou.",
                ephemeral=True,
            )
        post = await self.cog.get_post(self.post_id)
        if post is None or post["guild_id"] != interaction.guild_id:
            return await interaction.response.send_message(
                "Esta publicação não existe mais.", ephemeral=True
            )
        await self.cog.pool.execute(
            """
            INSERT INTO insta_comments (post_id, user_id, username, comment)
            VALUES ($1, $2, $3, $4)
            """,
            self.post_id,
            interaction.user.id,
            interaction.user.display_name,
            self.comment_input.value.strip(),
        )
        await interaction.response.send_message(
            "Comentário publicado.", ephemeral=True
        )


class InstaPostView(ComponentsV2View):
    def __init__(self, cog: "Insta", post_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.post_id = post_id
        self.add_item(LikeButton(cog, post_id))
        self.add_item(CommentButton(cog, post_id))
        self.add_item(CommentsButton(cog, post_id))
        self.add_item(DeletePostButton(cog, post_id))


class LikeButton(discord.ui.Button):
    def __init__(self, cog: "Insta", post_id: int):
        super().__init__(
            style=discord.ButtonStyle.primary,
            custom_id=f"insta:like:{post_id}",
            emoji=discord.PartialEmoji.from_str(
                "<:White_Heart:1555601989633712159>"
            ),
        )
        self.cog = cog
        self.post_id = post_id

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.cog.pool is None:
            return await interaction.response.send_message(
                "O Instagram está indisponível porque o banco de dados não conectou.",
                ephemeral=True,
            )
        await interaction.response.defer()
        post = await self.cog.get_post(self.post_id)
        if post is None or post["guild_id"] != interaction.guild_id:
            return await interaction.followup.send(
                "Esta publicação não está disponível neste servidor.",
                ephemeral=True,
            )
        inserted = await self.cog.pool.fetchval(
            """
            INSERT INTO insta_likes (post_id, user_id)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING
            RETURNING user_id
            """,
            self.post_id,
            interaction.user.id,
        )
        if inserted is None:
            await self.cog.pool.execute(
                "DELETE FROM insta_likes WHERE post_id = $1 AND user_id = $2",
                self.post_id,
                interaction.user.id,
            )
            message = "Curtida removida"
        else:
            message = "Você curtiu esta publicação."
        count = await self.cog.like_count(self.post_id)
        embed = self.cog.post_embed(
            interaction.guild,
            post["author_name"],
            post["author_avatar"],
            post["caption"],
            post["image_filename"],
            count,
        )
        await interaction.message.edit(
            embeds=[],
            view=components_v2(
                embed, view=InstaPostView(self.cog, self.post_id)
            ),
        )
        await interaction.followup.send(message, ephemeral=True)


class CommentButton(discord.ui.Button):
    def __init__(self, cog: "Insta", post_id: int):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            custom_id=f"insta:comment:{post_id}",
            emoji=discord.PartialEmoji.from_str(
                "<:ChatWhite1:1555602133519171645>"
            ),
        )
        self.cog = cog
        self.post_id = post_id

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.cog.pool is None:
            return await interaction.response.send_message(
                "O Instagram está indisponível porque o banco de dados não conectou.",
                ephemeral=True,
            )
        post = await self.cog.get_post(self.post_id)
        if post is None or post["guild_id"] != interaction.guild_id:
            return await interaction.response.send_message(
                "Esta publicação não está disponível neste servidor.",
                ephemeral=True,
            )
        await interaction.response.send_modal(
            CommentModal(self.cog, self.post_id)
        )


class CommentsButton(discord.ui.Button):
    def __init__(self, cog: "Insta", post_id: int):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            custom_id=f"insta:comments:{post_id}",
            emoji=discord.PartialEmoji.from_str(
                "<:chat_icon_white:1555602208337432699>"
            ),
        )
        self.cog = cog
        self.post_id = post_id

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.cog.pool is None:
            return await interaction.response.send_message(
                "O Instagram está indisponível porque o banco de dados não conectou.",
                ephemeral=True,
            )
        post = await self.cog.get_post(self.post_id)
        if post is None or post["guild_id"] != interaction.guild_id:
            return await interaction.response.send_message(
                "Esta publicação não está disponível neste servidor.",
                ephemeral=True,
            )
        comments = await self.cog.get_comments(self.post_id)
        view = CommentsView(self.cog, self.post_id, interaction.user.id, comments)
        await interaction.response.send_message(
            view=components_v2(view.embed(), view=view), ephemeral=True
        )


class DeletePostButton(discord.ui.Button):
    def __init__(self, cog: "Insta", post_id: int):
        super().__init__(
            style=discord.ButtonStyle.danger,
            custom_id=f"insta:delete:{post_id}",
            emoji=discord.PartialEmoji.from_str(
                "<:ml_trash_can:1555603158141505657>"
            ),
        )
        self.cog = cog
        self.post_id = post_id

    async def callback(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(
                "Somente membros com a permissão Gerenciar Servidor podem apagar posts.",
                ephemeral=True,
            )
        if self.cog.pool is None:
            return await interaction.response.send_message(
                "O Instagram está indisponível porque o banco de dados não conectou.",
                ephemeral=True,
            )
        post = await self.cog.get_post(self.post_id)
        if post is None or post["guild_id"] != interaction.guild_id:
            return await interaction.response.send_message(
                "Esta publicação não está disponível neste servidor.",
                ephemeral=True,
            )
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await interaction.message.delete()
        except discord.HTTPException:
            return await interaction.followup.send(
                "Não consegui apagar a mensagem da publicação.", ephemeral=True
            )
        await self.cog.pool.execute(
            "DELETE FROM insta_posts WHERE post_id = $1", self.post_id
        )
        await interaction.followup.send("Publicação apagada.", ephemeral=True)


class CommentsView(ComponentsV2View):
    def __init__(
        self,
        cog: "Insta",
        post_id: int,
        owner_id: int,
        comments: list[asyncpg.Record],
        page: int = 0,
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.post_id = post_id
        self.owner_id = owner_id
        self.comments = comments
        self.page = page
        self.previous_button = discord.ui.Button(
            label="Anterior", style=discord.ButtonStyle.secondary, disabled=page <= 0
        )
        self.next_button = discord.ui.Button(
            label="Próxima",
            style=discord.ButtonStyle.secondary,
            disabled=(page + 1) * COMMENTS_PER_PAGE >= len(comments),
        )
        self.previous_button.callback = self.previous
        self.next_button.callback = self.next
        self.add_item(self.previous_button)
        self.add_item(self.next_button)

    def embed(self) -> discord.Embed:
        start = self.page * COMMENTS_PER_PAGE
        page_comments = self.comments[start : start + COMMENTS_PER_PAGE]
        if page_comments:
            lines = [
                f"**{comment['username']}**: {discord.utils.escape_markdown(comment['comment'])}"
                for comment in page_comments
            ]
            description = "\n\n".join(lines)
        else:
            description = "Ainda não há comentários nesta publicação."
        total_pages = max(1, (len(self.comments) + COMMENTS_PER_PAGE - 1) // COMMENTS_PER_PAGE)
        embed = discord.Embed(
            title="Comentários da publicação",
            description=description,
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"Página {self.page + 1}/{total_pages} · {len(self.comments)} comentário(s)")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Esta lista de comentários pertence a outra pessoa.", ephemeral=True
            )
            return False
        return True

    async def previous(self, interaction: discord.Interaction) -> None:
        self.page = max(0, self.page - 1)
        view = self.refresh()
        await interaction.response.edit_message(
            embeds=[], view=components_v2(self.embed(), view=view)
        )

    async def next(self, interaction: discord.Interaction) -> None:
        max_page = max(0, (len(self.comments) - 1) // COMMENTS_PER_PAGE)
        self.page = min(max_page, self.page + 1)
        view = self.refresh()
        await interaction.response.edit_message(
            embeds=[], view=components_v2(self.embed(), view=view)
        )

    def refresh(self) -> "CommentsView":
        return CommentsView(
            self.cog, self.post_id, self.owner_id, self.comments, self.page
        )


class Insta(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pool: asyncpg.Pool | None = None
        self.views_registered = False

    async def cog_load(self) -> None:
        database_url = os.getenv("DATABASE") or os.getenv("DATABASE_URL")
        if not database_url:
            print("Instagram indisponível: DATABASE não configurada.")
            return
        try:
            self.pool = await asyncpg.create_pool(
                dsn=database_url,
                ssl="require",
                min_size=1,
                max_size=5,
                command_timeout=30,
            )
            await self.pool.execute(
                """
                CREATE TABLE IF NOT EXISTS insta_posts (
                    post_id BIGINT PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    channel_id BIGINT NOT NULL,
                    author_id BIGINT NOT NULL,
                    author_name TEXT NOT NULL,
                    author_avatar TEXT NOT NULL,
                    caption TEXT NOT NULL DEFAULT '',
                    image_filename TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await self.pool.execute(
                """
                CREATE TABLE IF NOT EXISTS insta_likes (
                    post_id BIGINT NOT NULL REFERENCES insta_posts(post_id) ON DELETE CASCADE,
                    user_id BIGINT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (post_id, user_id)
                )
                """
            )
            await self.pool.execute(
                """
                CREATE TABLE IF NOT EXISTS insta_comments (
                    comment_id BIGSERIAL PRIMARY KEY,
                    post_id BIGINT NOT NULL REFERENCES insta_posts(post_id) ON DELETE CASCADE,
                    user_id BIGINT NOT NULL,
                    username TEXT NOT NULL,
                    comment TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        except Exception as error:
            if self.pool is not None:
                await self.pool.close()
                self.pool = None
            print(
                "Não foi possível iniciar o banco do Instagram: "
                f"{type(error).__name__}: {error}"
            )

    async def cog_unload(self) -> None:
        if self.pool is not None:
            await self.pool.close()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self.pool is None or self.views_registered:
            return
        rows = await self.pool.fetch("SELECT post_id FROM insta_posts")
        for row in rows:
            self.bot.add_view(
                InstaPostView(self, row["post_id"]),
                message_id=row["post_id"],
            )
        self.views_registered = True

    async def get_post(self, post_id: int):
        if self.pool is None:
            return None
        return await self.pool.fetchrow(
            "SELECT * FROM insta_posts WHERE post_id = $1", post_id
        )

    async def like_count(self, post_id: int) -> int:
        return int(
            await self.pool.fetchval(
                "SELECT COUNT(*) FROM insta_likes WHERE post_id = $1", post_id
            )
            or 0
        )

    async def get_comments(self, post_id: int) -> list[asyncpg.Record]:
        return await self.pool.fetch(
            """
            SELECT username, comment, created_at
            FROM insta_comments
            WHERE post_id = $1
            ORDER BY created_at ASC, comment_id ASC
            """,
            post_id,
        )

    def menu_for(self, guild_id: int):
        menu = self.bot.get_cog("Menu")
        if menu is None or not menu.module_configured(guild_id, "insta"):
            return None
        return menu

    def is_image(self, attachment: discord.Attachment) -> bool:
        suffix = Path(attachment.filename).suffix.lower()
        return (
            suffix in ALLOWED_IMAGE_SUFFIXES
            and (attachment.content_type is None or attachment.content_type.startswith("image/"))
        )

    def has_image_signature(self, suffix: str, data: bytes) -> bool:
        return (
            suffix == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n")
        ) or (
            suffix in {".jpg", ".jpeg"} and data.startswith(b"\xff\xd8\xff")
        ) or (
            suffix == ".webp" and data.startswith(b"RIFF") and data[8:12] == b"WEBP"
        ) or (
            suffix == ".gif" and data.startswith((b"GIF87a", b"GIF89a"))
        )

    async def download_attachment(self, attachment: discord.Attachment, path: Path) -> None:
        if attachment.size > MAX_IMAGE_BYTES:
            raise ValueError("O arquivo ultrapassa o limite de 1 GB.")
        timeout = aiohttp.ClientTimeout(total=None, connect=30, sock_read=120)
        received = 0
        header = bytearray()
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(attachment.url) as response:
                response.raise_for_status()
                with path.open("wb") as image_file:
                    async for chunk in response.content.iter_chunked(1024 * 1024):
                        received += len(chunk)
                        if received > MAX_IMAGE_BYTES:
                            raise ValueError("O arquivo ultrapassa o limite de 1 GB.")
                        if len(header) < 12:
                            header.extend(chunk[: 12 - len(header)])
                        image_file.write(chunk)
        if received == 0:
            raise ValueError("O arquivo enviado está vazio.")
        if not self.has_image_signature(Path(attachment.filename).suffix.lower(), bytes(header)):
            raise ValueError("O arquivo não contém uma imagem válida.")

    def post_embed(
        self,
        guild: discord.Guild,
        author_name: str,
        author_avatar: str,
        caption: str,
        image_filename: str,
        likes: int,
    ) -> discord.Embed:
        embed = discord.Embed(
            description=caption[:4000] or None,
            color=discord.Color.blurple(),
        )
        embed.set_author(name=author_name, icon_url=author_avatar)
        embed.set_image(url=f"attachment://{image_filename}")
        embed.set_footer(text=f"Curtidas: {likes} · {guild.name}")
        return embed

    async def reject_message(self, message: discord.Message, reason: str) -> None:
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        try:
            await message.channel.send(reason, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot or not message.attachments:
            return
        images = [attachment for attachment in message.attachments if self.is_image(attachment)]
        if not images:
            return

        menu = self.menu_for(message.guild.id)
        if menu is None or int(menu.get_value(message.guild.id, "insta_channel", 0) or 0) != message.channel.id:
            return
        if self.pool is None:
            await message.reply(
                "O Instagram está indisponível porque o banco de dados não conectou.",
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        if len(message.attachments) != 1 or len(images) != 1:
            await self.reject_message(message, "Envie apenas uma foto por publicação.")
            return

        attachment = images[0]
        if attachment.size > MAX_IMAGE_BYTES:
            await self.reject_message(message, "Não aceito arquivos acima de 1 GB.")
            return
        bot_member = message.guild.me
        if bot_member is None or not message.channel.permissions_for(bot_member).manage_messages:
            await message.reply(
                "Preciso da permissão Gerenciar Mensagens neste canal para publicar e apagar a foto original.",
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        suffix = Path(attachment.filename).suffix.lower()
        safe_filename = f"insta_{attachment.id}{suffix}"
        caption = message.content[:4000]
        try:
            with tempfile.TemporaryDirectory(prefix="hakari_insta_") as temp_dir:
                image_path = Path(temp_dir) / safe_filename
                await self.download_attachment(attachment, image_path)
                embed = self.post_embed(
                    message.guild,
                    message.author.display_name,
                    message.author.display_avatar.url,
                    caption,
                    safe_filename,
                    0,
                )
                published = await message.channel.send(
                    view=components_v2(embed),
                    file=discord.File(image_path, filename=safe_filename),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        except ValueError as error:
            await self.reject_message(message, str(error))
            return
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            await message.reply(
                f"Não consegui salvar a foto: {type(error).__name__}.",
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        except discord.HTTPException:
            await message.reply(
                "O Discord não aceitou o tamanho deste arquivo para a publicação.",
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        try:
            await self.pool.execute(
                """
                INSERT INTO insta_posts (
                    post_id, guild_id, channel_id, author_id, author_name,
                    author_avatar, caption, image_filename
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                published.id,
                message.guild.id,
                message.channel.id,
                message.author.id,
                message.author.display_name,
                message.author.display_avatar.url,
                caption,
                safe_filename,
            )
        except Exception as error:
            try:
                await published.delete()
            except discord.HTTPException:
                pass
            await message.reply(
                f"Não consegui registrar a publicação no banco ({type(error).__name__}); sua mensagem original foi mantida.",
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        view = InstaPostView(self, published.id)
        try:
            await published.edit(
                embeds=[], view=components_v2(embed, view=view)
            )
        except discord.HTTPException:
            await self.pool.execute(
                "DELETE FROM insta_posts WHERE post_id = $1", published.id
            )
            try:
                await published.delete()
            except discord.HTTPException:
                pass
            await message.reply(
                "Não consegui ativar os botões da publicação; a foto original foi mantida.",
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        self.bot.add_view(view, message_id=published.id)
        try:
            await message.delete()
        except discord.HTTPException:
            await message.channel.send(
                "A publicação foi criada, mas não consegui apagar a mensagem original.",
                allowed_mentions=discord.AllowedMentions.none(),
            )

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Insta(bot))
