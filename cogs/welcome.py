from io import BytesIO
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from .components_v2 import components_v2


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def menu_for(self, guild_id: int):
        menu = self.bot.get_cog("Menu")
        if menu is None or not menu.module_configured(guild_id, "welcome"):
            return None
        return menu

    def render_text(self, value: str, member: discord.Member, ping_member: bool) -> str:
        replacements = {
            "{user}": member.mention if ping_member else member.display_name,
            "{mention}": member.mention if ping_member else member.display_name,
            "{username}": member.name,
            "{server}": member.guild.name,
            "{member_count}": str(member.guild.member_count or len(member.guild.members)),
        }
        for placeholder, replacement in replacements.items():
            value = value.replace(placeholder, replacement)
        return value

    async def build_welcome(
        self, member: discord.Member
    ) -> tuple[discord.TextChannel, str, discord.Embed, list[discord.File], discord.AllowedMentions] | None:
        menu = self.menu_for(member.guild.id)
        if menu is None:
            return None

        channel_id = menu.get_value(member.guild.id, "welcome_channel")
        channel = member.guild.get_channel(int(channel_id)) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            return None

        ping_member = bool(menu.get_value(member.guild.id, "welcome_ping_member", False))
        role_id = menu.get_value(member.guild.id, "welcome_ping_role")
        ping_role = member.guild.get_role(int(role_id)) if role_id else None
        content_parts = []
        if ping_role is not None:
            content_parts.append(ping_role.mention)
        if ping_member:
            content_parts.append(member.mention)

        render = lambda text: self.render_text(text or "", member, ping_member)
        title = render(menu.get_value(member.guild.id, "welcome_embed_title", ""))
        description = render(
            menu.get_value(member.guild.id, "welcome_embed_description", "")
        )
        embed = discord.Embed(
            title=title or None,
            description=description or None,
            color=discord.Color.blurple(),
        )
        footer = render(menu.get_value(member.guild.id, "welcome_footer", ""))
        if footer:
            embed.set_footer(text=footer)

        files = []
        author_name = render(menu.get_value(member.guild.id, "welcome_author_name", ""))
        author_asset = await menu.get_welcome_asset(member.guild.id, "welcome_author_icon")
        if author_name or author_asset:
            author_icon_url = member.display_avatar.url
            if author_asset:
                original_name, data = author_asset
                filename = f"welcome_author_icon{Path(original_name).suffix.lower()}"
                files.append(discord.File(BytesIO(data), filename=filename))
                author_icon_url = f"attachment://{filename}"
            embed.set_author(name=author_name or member.display_name, icon_url=author_icon_url)

        for asset_key, setter in (
            ("welcome_thumbnail", embed.set_thumbnail),
            ("welcome_image", embed.set_image),
        ):
            asset = await menu.get_welcome_asset(member.guild.id, asset_key)
            if asset:
                original_name, data = asset
                filename = f"{asset_key}{Path(original_name).suffix.lower()}"
                files.append(discord.File(BytesIO(data), filename=filename))
                setter(url=f"attachment://{filename}")

        allowed_mentions = discord.AllowedMentions(
            users=[member] if ping_member else False,
            roles=[ping_role] if ping_role is not None else False,
            everyone=False,
            replied_user=False,
        )
        return (
            channel,
            " ".join(content_parts),
            embed,
            files,
            allowed_mentions,
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        message = await self.build_welcome(member)
        if message is None:
            return
        channel, content, embed, files, allowed_mentions = message
        try:
            await channel.send(
                view=components_v2(embed, content=content or None),
                files=files,
                allowed_mentions=allowed_mentions,
            )
        except discord.HTTPException as error:
            print(
                f"Não foi possível enviar boas-vindas em {member.guild.id}: {error}"
            )

    @app_commands.command(
        name="boasvindas",
        description="Mostra uma prévia privada da mensagem de boas-vindas",
    )
    @app_commands.guild_only()
    async def welcome_preview(self, interaction: discord.Interaction) -> None:
        message = await self.build_welcome(interaction.user)
        if message is None:
            return await interaction.response.send_message(
                "Boas-vindas ainda não está configurado neste servidor.",
                ephemeral=True,
            )
        _, content, embed, files, _ = message
        await interaction.response.send_message(
            view=components_v2(embed, content=content or None),
            files=files,
            allowed_mentions=discord.AllowedMentions.none(),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Welcome(bot))
