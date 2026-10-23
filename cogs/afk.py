import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from .components_v2 import components_v2

log = logging.getLogger(__name__)

class AFK(commands.Cog):
    """Cog responsável por gerenciar o status de ausência (AFK) dos usuários."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.afk_users: dict[int, str] = {}  # {user_id: motivo}

    @commands.hybrid_command(
        name="afk",
        description="Define seu status como ausente (AFK)."
    )
    @app_commands.describe(reason="Motivo da sua ausência")
    async def afk(self, ctx: commands.Context, *, reason: Optional[str] = "Sem motivo informado") -> None:
        """Define seu status como AFK."""
        self.afk_users[ctx.author.id] = reason

        embed = discord.Embed(
            title="Status AFK Ativado",
            description=(
                f"{ctx.author.mention} agora está AFK.\n"
                "Quando alguém mencionar você, eu avisarei sobre sua ausência!"
            ),
            color=discord.Color.brand_red()
        )
        embed.add_field(name="Motivo", value=reason, inline=False)

        await ctx.send(view=components_v2(embed))

    @commands.hybrid_command(
        name="voltei",
        description="Remove seu status de ausência (AFK)."
    )
    async def voltei(self, ctx: commands.Context) -> None:
        """Remove seu status de AFK."""
        if ctx.author.id not in self.afk_users:
            await ctx.send("Você não está AFK no momento.", ephemeral=True)
            return

        motivo = self.afk_users.pop(ctx.author.id)

        embed = discord.Embed(
            title="Status AFK Removido",
            description=f"Bem-vindo de volta, {ctx.author.mention}!",
            color=discord.Color.brand_green()
        )
        embed.add_field(name="Você estava AFK por:", value=motivo, inline=False)

        await ctx.send(view=components_v2(embed))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Detecta mensagens para remover AFK do autor ou avisar se mencionou alguém AFK."""
        if message.author.bot or not message.guild:
            return

        # Remove o AFK do autor se ele mandar mensagem
        if message.author.id in self.afk_users:
            self.afk_users.pop(message.author.id)

        # Ignora o processamento se for a execução de um comando
        context = await self.bot.get_context(message)
        if context.valid:
            return

        afk_mentioned: dict[discord.Member | discord.User, str] = {}

        # 1. Verifica usuários que foram mencionados diretamente
        for user in message.mentions:
            if user.id in self.afk_users:
                afk_mentioned[user] = self.afk_users[user.id]

        # 2. Verifica se a mensagem é resposta a alguém que está AFK
        if message.reference and message.reference.resolved:
            replied_msg = message.reference.resolved
            if isinstance(replied_msg, discord.Message) and replied_msg.author.id in self.afk_users:
                afk_mentioned[replied_msg.author] = self.afk_users[replied_msg.author.id]

        if not afk_mentioned:
            return

        # Constrói a mensagem agrupada para todos os AFKs mencionados
        descriptions = [
            f"**{user.display_name}** está AFK.\n**Motivo:** {reason}"
            for user, reason in afk_mentioned.items()
        ]

        embed = discord.Embed(
            title="⚠️ Usuário(s) AFK",
            description="\n\n".join(descriptions),
            color=discord.Color.orange()
        )

        await message.reply(view=components_v2(embed), mention_author=False)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AFK(bot))
    log.info("Cog 'AFK' carregada com sucesso.")
