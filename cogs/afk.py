import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

from .components_v2 import components_v2


class AFK(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.afk_users = {}  # {user_id: motivo}

    # ===== COMANDO AFK =====

    @commands.command(name="afk")
    async def afk_prefix(
        self,
        ctx: commands.Context,
        *,
        reason: str = "sem motivo informado"
    ):
        """Define seu status como AFK."""

        self.afk_users[ctx.author.id] = reason

        embed = discord.Embed(
            title="Status AFK Ativado",
            description=(
                f"{ctx.author.mention} agora está AFK.\n"
                "Quando alguém mencionar você, eu avisarei que você está AFK!"
            ),
            color=discord.Color.red()
        )

        embed.add_field(
            name="Motivo",
            value=reason,
            inline=False
        )

        await ctx.send(view=components_v2(embed))

    @app_commands.command(
        name="afk",
        description="Define seu status como AFK"
    )
    @app_commands.describe(
        reason="Motivo da sua ausência"
    )
    async def afk_slash(
        self,
        interaction: discord.Interaction,
        reason: Optional[str] = None
    ):
        """Define seu status como AFK."""

        reason = reason or "sem motivo informado"

        self.afk_users[interaction.user.id] = reason

        embed = discord.Embed(
            title="Status AFK Ativado",
            description=(
                f"{interaction.user.mention} agora está AFK.\n"
                "Quando alguém mencionar você, eu avisarei que você está AFK!"
            ),
            color=discord.Color.red()
        )

        embed.add_field(
            name="Motivo",
            value=reason,
            inline=False
        )

        await interaction.response.send_message(
            view=components_v2(embed)
        )

    # ===== REMOVER AFK =====

    @commands.command(name="voltei")
    async def back_prefix(self, ctx: commands.Context):
        """Remove seu status de AFK."""

        if ctx.author.id not in self.afk_users:
            return await ctx.send("Você não está AFK.")

        motivo = self.afk_users.pop(ctx.author.id)

        embed = discord.Embed(
            title="Status AFK Removido",
            description=f"{ctx.author.mention} voltou.",
            color=discord.Color.green()
        )

        embed.add_field(
            name="Estava AFK por",
            value=motivo,
            inline=False
        )

        await ctx.send(view=components_v2(embed))

    @app_commands.command(
        name="voltei",
        description="Remove seu status de AFK"
    )
    async def back_slash(
        self,
        interaction: discord.Interaction
    ):
        """Remove seu status de AFK."""

        if interaction.user.id not in self.afk_users:
            return await interaction.response.send_message(
                "Você não está AFK."
            )

        motivo = self.afk_users.pop(interaction.user.id)

        embed = discord.Embed(
            title="Status AFK Removido",
            description=(
                f"O usuário {interaction.user.mention} "
                "saiu do AFK e está de volta."
            ),
            color=discord.Color.green()
        )

        embed.add_field(
            name="Estava AFK por:",
            value=motivo,
            inline=False
        )

        await interaction.response.send_message(
            view=components_v2(embed)
        )

    # ===== LISTENER PARA MENÇÕES =====

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Detecta menções a usuários AFK."""

        if message.author.bot:
            return

        # Se o usuário falar, remove o AFK
        if message.author.id in self.afk_users:
            self.afk_users.pop(message.author.id)

        context = await self.bot.get_context(message)
        if context.valid:
            return

        afk_mentioned = []

        # Verificar resposta a alguém AFK
        if message.reference:
            try:
                replied_message = await message.channel.fetch_message(
                    message.reference.message_id
                )

                user = replied_message.author

                if user.id in self.afk_users:
                    afk_mentioned.append(
                        (user, self.afk_users[user.id])
                    )

            except Exception:
                pass

        # Verificar menções diretas
        for mentioned in message.mentions:

            if mentioned.id in self.afk_users:

                if mentioned not in [
                    user[0] for user in afk_mentioned
                ]:
                    afk_mentioned.append(
                        (
                            mentioned,
                            self.afk_users[mentioned.id]
                        )
                    )

        # Avisar sobre usuários AFK
        if afk_mentioned:

            descriptions = []

            for user, reason in afk_mentioned:
                descriptions.append(
                    f"{user.mention} está **AFK**.\n"
                    f"**Motivo:** {reason}"
                )

            embed = discord.Embed(
                title="⚠️ Usuário AFK",
                description="\n\n".join(descriptions),
                color=discord.Color.orange()
            )

            await message.reply(
                view=components_v2(embed),
                mention_author=False
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(AFK(bot))
