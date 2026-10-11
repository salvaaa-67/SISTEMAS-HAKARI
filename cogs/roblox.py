import os

import aiohttp
import asyncpg
import discord
from discord import app_commands
from discord.ext import commands

from .components_v2 import ComponentsV2View, components_v2


ROBLOX_ICON = "<:c_roblox:1555606064890773554>"
ROBLOX_USERS_API = "https://users.roblox.com/v1/usernames/users"
ROBLOX_AVATAR_API = "https://thumbnails.roblox.com/v1/users/avatar"
ROBLOX_TIMEOUT = aiohttp.ClientTimeout(total=15, connect=5)


class RobloxAvatarView(ComponentsV2View):
    def __init__(self, cog: "Roblox", post_id: int):
        super().__init__(timeout=None)
        self.add_item(RobloxLikeButton(cog, post_id))


class RobloxLikeButton(discord.ui.Button):
    def __init__(self, cog: "Roblox", post_id: int):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            custom_id=f"roblox:like:{post_id}",
            emoji="🤍",
        )
        self.cog = cog
        self.post_id = post_id

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.cog.pool is None:
            return await interaction.response.send_message(
                "O sistema Roblox está indisponível porque o banco de dados não conectou.",
                ephemeral=True,
            )
        await interaction.response.defer()
        post = await self.cog.get_post(self.post_id)
        if post is None or post["guild_id"] != interaction.guild_id:
            return await interaction.followup.send(
                "Este avatar não está disponível neste servidor.", ephemeral=True
            )

        inserted = await self.cog.pool.fetchval(
            """
            INSERT INTO roblox_avatar_likes (post_id, user_id)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING
            RETURNING user_id
            """,
            self.post_id,
            interaction.user.id,
        )
        if inserted is None:
            await self.cog.pool.execute(
                "DELETE FROM roblox_avatar_likes WHERE post_id = $1 AND user_id = $2",
                self.post_id,
                interaction.user.id,
            )
            response = "Curtida removida."
        else:
            response = "Você curtiu este avatar."

        like_count = await self.cog.like_count(self.post_id)
        await interaction.message.edit(
            embeds=[],
            view=components_v2(
                self.cog.avatar_embed(post, like_count),
                view=RobloxAvatarView(self.cog, self.post_id),
            ),
        )
        await interaction.followup.send(response, ephemeral=True)


class Roblox(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pool: asyncpg.Pool | None = None
        self.views_registered = False

    async def cog_load(self) -> None:
        database_url = os.getenv("DATABASE") or os.getenv("DATABASE_URL")
        if not database_url:
            print("Avatares Roblox indisponíveis: DATABASE não configurada.")
            return
        try:
            self.pool = await asyncpg.create_pool(
                dsn=database_url,
                ssl="require",
                min_size=1,
                max_size=3,
                command_timeout=20,
            )
            await self.pool.execute(
                """
                CREATE TABLE IF NOT EXISTS roblox_avatar_posts (
                    post_id BIGINT PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    channel_id BIGINT NOT NULL,
                    roblox_user_id BIGINT NOT NULL,
                    username TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    avatar_url TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await self.pool.execute(
                """
                CREATE TABLE IF NOT EXISTS roblox_avatar_likes (
                    post_id BIGINT NOT NULL REFERENCES roblox_avatar_posts(post_id) ON DELETE CASCADE,
                    user_id BIGINT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (post_id, user_id)
                )
                """
            )
        except Exception as error:
            if self.pool is not None:
                await self.pool.close()
                self.pool = None
            print(
                "Não foi possível iniciar o banco de avatares Roblox: "
                f"{type(error).__name__}: {error}"
            )

    async def cog_unload(self) -> None:
        if self.pool is not None:
            await self.pool.close()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self.pool is None or self.views_registered:
            return
        rows = await self.pool.fetch("SELECT post_id FROM roblox_avatar_posts")
        for row in rows:
            self.bot.add_view(
                RobloxAvatarView(self, row["post_id"]),
                message_id=row["post_id"],
            )
        self.views_registered = True

    def menu_for(self, guild_id: int):
        menu = self.bot.get_cog("Menu")
        if menu is None or not menu.module_configured(guild_id, "roblox"):
            return None
        return menu

    async def get_post(self, post_id: int):
        if self.pool is None:
            return None
        return await self.pool.fetchrow(
            "SELECT * FROM roblox_avatar_posts WHERE post_id = $1", post_id
        )

    async def like_count(self, post_id: int) -> int:
        return int(
            await self.pool.fetchval(
                "SELECT COUNT(*) FROM roblox_avatar_likes WHERE post_id = $1",
                post_id,
            )
            or 0
        )

    def avatar_embed(self, post, like_count: int) -> discord.Embed:
        embed = discord.Embed(
            title=f"{ROBLOX_ICON} {post['display_name']}",
            description=f"@{post['username']} - {like_count} Curtidas",
            color=discord.Color.blurple(),
        )
        embed.set_image(url=post["avatar_url"])
        return embed

    async def lookup_avatar(self, username: str) -> dict | None:
        headers = {"User-Agent": "HakariRobloxAvatar/1.0"}
        async with aiohttp.ClientSession(
            timeout=ROBLOX_TIMEOUT, headers=headers
        ) as session:
            async with session.post(
                ROBLOX_USERS_API,
                json={"usernames": [username], "excludeBannedUsers": True},
            ) as response:
                response.raise_for_status()
                user_data = await response.json()
            users = user_data.get("data", [])
            if not users:
                return None
            user = users[0]
            params = {
                "userIds": str(user["id"]),
                "size": "720x720",
                "format": "Png",
                "isCircular": "false",
            }
            async with session.get(ROBLOX_AVATAR_API, params=params) as response:
                response.raise_for_status()
                avatar_data = await response.json()
        images = avatar_data.get("data", [])
        if not images or images[0].get("state") != "Completed":
            return None
        return {
            "roblox_user_id": int(user["id"]),
            "username": user["name"],
            "display_name": user.get("displayName") or user["name"],
            "avatar_url": images[0]["imageUrl"],
        }

    @app_commands.command(
        name="robloxavatar",
        description="Publica o avatar de um usuário Roblox no canal configurado",
    )
    @app_commands.describe(usuario="Nome de usuário no Roblox")
    @app_commands.guild_only()
    async def roblox_avatar(
        self, interaction: discord.Interaction, usuario: str
    ) -> None:
        if interaction.guild_id is None:
            return await interaction.response.send_message(
                "Use este comando em um servidor.", ephemeral=True
            )
        menu = self.menu_for(interaction.guild_id)
        if menu is None:
            return await interaction.response.send_message(
                "O módulo de avatares Roblox não está configurado neste servidor.",
                ephemeral=True,
            )
        if self.pool is None:
            return await interaction.response.send_message(
                "O sistema Roblox está indisponível porque o banco de dados não conectou.",
                ephemeral=True,
            )
        channel_id = menu.get_value(interaction.guild_id, "roblox_channel")
        channel = interaction.guild.get_channel(int(channel_id)) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message(
                "O canal de avatares Roblox não está disponível. Revise o /menu.",
                ephemeral=True,
            )
        bot_member = interaction.guild.me
        channel_permissions = (
            channel.permissions_for(bot_member) if bot_member is not None else None
        )
        if (
            channel_permissions is None
            or not channel_permissions.send_messages
            or not channel_permissions.embed_links
        ):
            return await interaction.response.send_message(
                "Preciso das permissões Enviar Mensagens e Incorporar Links no canal Roblox configurado.",
                ephemeral=True,
            )

        username = usuario.strip()
        if not username or len(username) > 20:
            return await interaction.response.send_message(
                "Informe um nome de usuário Roblox válido.", ephemeral=True
            )
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            profile = await self.lookup_avatar(username)
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            return await interaction.followup.send(
                f"Não consegui consultar o Roblox ({type(error).__name__}).",
                ephemeral=True,
            )
        except (KeyError, ValueError):
            return await interaction.followup.send(
                "O Roblox retornou uma resposta inválida. Tente novamente.",
                ephemeral=True,
            )
        if profile is None:
            return await interaction.followup.send(
                f"Não encontrei o usuário Roblox **{discord.utils.escape_markdown(username)}**.",
                ephemeral=True,
            )

        embed = self.avatar_embed(profile, 0)
        try:
            post_message = await channel.send(
                view=components_v2(embed),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.Forbidden:
            return await interaction.followup.send(
                "O Discord negou o envio no canal configurado.", ephemeral=True
            )
        except discord.HTTPException:
            return await interaction.followup.send(
                "Não consegui publicar o avatar no canal configurado.",
                ephemeral=True,
            )

        try:
            await self.pool.execute(
                """
                INSERT INTO roblox_avatar_posts (
                    post_id, guild_id, channel_id, roblox_user_id,
                    username, display_name, avatar_url
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                post_message.id,
                interaction.guild_id,
                channel.id,
                profile["roblox_user_id"],
                profile["username"],
                profile["display_name"],
                profile["avatar_url"],
            )
            view = RobloxAvatarView(self, post_message.id)
            await post_message.edit(
                embeds=[], view=components_v2(embed, view=view)
            )
        except Exception as error:
            try:
                await post_message.delete()
            except discord.HTTPException:
                pass
            return await interaction.followup.send(
                f"Não consegui registrar a publicação ({type(error).__name__}).",
                ephemeral=True,
            )

        self.bot.add_view(view, message_id=post_message.id)
        await interaction.followup.send(
            f"Avatar de **{discord.utils.escape_markdown(profile['username'])}** publicado em {channel.mention}.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Roblox(bot))
