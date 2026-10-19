import discord
from discord.ext import commands
from discord import app_commands

from .components_v2 import components_v2


class ServerInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="serverinfo")
    async def serverinfo_prefix(self, ctx):
        """Exibe informações do servidor (prefixo)"""
        guild = ctx.guild

        embed = discord.Embed(
            title=f"🏰 {guild.name}",
            color=discord.Color.orange()
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        if guild.banner:
            embed.set_image(url=guild.banner.url)

        embed.add_field(
            name="👑 Dono com Posse",
            value=str(guild.owner),
            inline=False
        )

        embed.add_field(
            name="👥 Membros",
            value=guild.member_count,
            inline=True
        )

        embed.add_field(
            name="🚀 Boosts",
            value=guild.premium_subscription_count,
            inline=True
        )

        embed.add_field(
            name="⭐ Nível Boost",
            value=guild.premium_tier,
            inline=True
        )

        embed.add_field(
            name="📆 Criado em",
            value=guild.created_at.strftime("%d/%m/%Y"),
            inline=False
        )

        await ctx.send(view=components_v2(embed))

    @app_commands.command(name="serverinfo", description="Exibe informações do servidor")
    async def serverinfo_slash(self, interaction: discord.Interaction):
        """Exibe informações do servidor (slash)"""
        guild = interaction.guild

        embed = discord.Embed(
            title=f"🏰 {guild.name}",
            color=discord.Color.orange()
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        if guild.banner:
            embed.set_image(url=guild.banner.url)

        embed.add_field(
            name="👑 Dono com Posse",
            value=str(guild.owner),
            inline=False
        )

        embed.add_field(
            name="👥 Membros",
            value=guild.member_count,
            inline=True
        )

        embed.add_field(
            name="🚀 Boosts",
            value=guild.premium_subscription_count,
            inline=True
        )

        embed.add_field(
            name="⭐ Nível Boost",
            value=guild.premium_tier,
            inline=True
        )

        embed.add_field(
            name="📆 Criado em",
            value=guild.created_at.strftime("%d/%m/%Y"),
            inline=False
        )

        await interaction.response.send_message(view=components_v2(embed))


class UserInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="userinfo")
    async def userinfo_prefix(self, ctx, member: discord.Member = None):
        """Exibe informações de um usuário (prefixo)"""
        member = member or ctx.author

        embed = discord.Embed(
            title=f"👤 Informações de {member}",
            color=discord.Color.blue()
        )

        embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(
            name="🆔 ID",
            value=member.id,
            inline=False
        )

        embed.add_field(
            name="📅 Conta criada",
            value=member.created_at.strftime("%d/%m/%Y"),
            inline=True
        )

        embed.add_field(
            name="📥 Entrou no servidor",
            value=member.joined_at.strftime("%d/%m/%Y"),
            inline=True
        )

        embed.add_field(
            name="🤖 Bot?",
            value=str(member.bot),
            inline=True
        )

        await ctx.send(view=components_v2(embed))

    @app_commands.command(name="userinfo", description="Exibe informações de um usuário")
    async def userinfo_slash(
        self,
        interaction: discord.Interaction,
        member: discord.Member = None
    ):
        """Exibe informações de um usuário (slash)"""
        member = member or interaction.user

        embed = discord.Embed(
            title=f"👤 informações de {member}",
            color=discord.Color.blue()
        )

        embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(
            name="🆔 ID",
            value=member.id,
            inline=False
        )

        embed.add_field(
            name="📅 conta criada",
            value=member.created_at.strftime("%d/%m/%Y"),
            inline=True
        )

        embed.add_field(
            name="📥 entrou no servidor",
            value=member.joined_at.strftime("%d/%m/%Y"),
            inline=True
        )

        embed.add_field(
            name="🤖 bot?",
            value=str(member.bot),
            inline=True
        )

        await interaction.response.send_message(view=components_v2(embed))


class Utilities(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ping")
    async def ping_prefix(self, ctx):
        """Exibe a latência da API do Discord (prefixo)"""
        latency = round(self.bot.latency * 1000)

        embed = discord.Embed(
            title="🏓 PONG PORRA!",
            description=(
                f"eu respondo seus comandos em até: **{latency} milissegundos**!"
            ),
            color=(
                discord.Color.green()
                if latency < 100
                else discord.Color.yellow()
                if latency < 200
                else discord.Color.red()
            )
        )

        await ctx.send(view=components_v2(embed))

    @app_commands.command(
        name="ping",
        description="Exibe a latência da API do Discord"
    )
    async def ping_slash(self, interaction: discord.Interaction):
        """Exibe a latência da API do Discord (slash)"""
        latency = round(self.bot.latency * 1000)

        embed = discord.Embed(
            title="🏓 Pong!",
            description=(
                f"Eu respondo seus comandos em até: **{latency} milissegundos**."
            ),
            color=(
                discord.Color.green()
                if latency < 100
                else discord.Color.yellow()
                if latency < 200
                else discord.Color.red()
            )
        )

        await interaction.response.send_message(view=components_v2(embed))

    @commands.command(name="ajuda")
    async def ajuda_prefix(self, ctx):
        """Exibe informações do bot e comandos disponíveis (prefixo)"""
        embed = discord.Embed(
            title="📚 Ajuda do Bot",
            color=discord.Color.blurple()
        )

        embed.add_field(
            name="🤖 Informações",
            value=(
                f"**Nome:** {self.bot.user.name}\n"
                f"**Prefixo:** `{self.bot.command_prefix}`\n"
                f"**Suporta:** `/` (slash commands)"
            ),
            inline=False
        )

        commands_list = []

        for cog in self.bot.cogs.values():
            for command in cog.get_commands():
                commands_list.append(
                    f"`{self.bot.command_prefix}{command.name}` - "
                    f"{command.help or 'Sem descrição'}"
                )

        if commands_list:
            embed.add_field(
                name="📋 Comandos de Prefixo",
                value="\n".join(commands_list[:20]),
                inline=False
            )
            embed.set_footer(
                text="Use / para ver slash commands!"
            )

        await ctx.send(view=components_v2(embed))

    @app_commands.command(
        name="ajuda",
        description="Exibe informações do bot e comandos disponíveis"
    )
    async def ajuda_slash(self, interaction: discord.Interaction):
        """Exibe informações do bot e comandos disponíveis (slash)"""
        embed = discord.Embed(
            title="📚 Ajuda do Bot",
            color=discord.Color.blurple()
        )

        embed.add_field(
            name="🤖 Informações",
            value=(
                f"**Nome:** {self.bot.user.name}\n"
                f"**Prefixo:** `{self.bot.command_prefix}`\n"
                f"**Suporta:** `/` (slash commands)"
            ),
            inline=False
        )

        commands_list = []

        for cog in self.bot.cogs.values():
            for command in cog.get_commands():
                commands_list.append(
                    f"`{self.bot.command_prefix}{command.name}` - "
                    f"{command.help or 'Sem descrição'}"
                )

        if commands_list:
            embed.add_field(
                name="📋 Comandos de Prefixo",
                value="\n".join(commands_list[:20]),
                inline=False
            )
            embed.set_footer(
                text="Use / para ver mais slash commands!"
            )

        await interaction.response.send_message(view=components_v2(embed))


async def setup(bot):
    await bot.add_cog(ServerInfo(bot))
    await bot.add_cog(UserInfo(bot))
    await bot.add_cog(Utilities(bot))
