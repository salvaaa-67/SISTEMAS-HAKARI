import logging
import random

import discord
from discord.ext import commands
from discord import app_commands

from .components_v2 import ComponentsV2View, components_v2
from .database import Pool, create_pool

log = logging.getLogger(__name__)


class HelpPager(ComponentsV2View):
    def __init__(self, pages: list[str]) -> None:
        super().__init__(timeout=180)
        self.pages = pages
        self.page_index = 0
        self.previous_button = discord.ui.Button(
            label="Anterior",
            style=discord.ButtonStyle.secondary,
            disabled=True,
        )
        self.next_button = discord.ui.Button(
            label="Próxima",
            style=discord.ButtonStyle.primary,
            disabled=len(pages) <= 1,
        )
        self.previous_button.callback = self.previous_page
        self.next_button.callback = self.next_page
        self.add_item(self.previous_button)
        self.add_item(self.next_button)
        self.set_message(content=self.pages[0])

    async def previous_page(self, interaction: discord.Interaction) -> None:
        await self.change_page(interaction, -1)

    async def next_page(self, interaction: discord.Interaction) -> None:
        await self.change_page(interaction, 1)

    async def change_page(
        self, interaction: discord.Interaction, offset: int
    ) -> None:
        self.page_index = (self.page_index + offset) % len(self.pages)
        self.previous_button.disabled = self.page_index == 0
        self.next_button.disabled = self.page_index == len(self.pages) - 1
        self.set_message(content=self.pages[self.page_index])
        await interaction.response.edit_message(view=self)


class MarriageProposalView(ComponentsV2View):
    MARRIAGE_IMAGE = (
        "https://i.postimg.cc/tYQ3yBss/"
        "Love-La-Bride-HD-Wallpaper-by-Takano-Yuki-1487582-Zerochan-Anime-Image-Board.jpg"
    )

    def __init__(
        self,
        utilities: "Utilities",
        guild_id: int,
        proposer: discord.Member,
        recipient: discord.Member,
    ) -> None:
        super().__init__(timeout=120)
        self.utilities = utilities
        self.guild_id = guild_id
        self.proposer = proposer
        self.recipient = recipient
        self.message: discord.Message | None = None
        self.accept_button = discord.ui.Button(
            label="Aceitar",
            style=discord.ButtonStyle.success,
            emoji="💍",
        )
        self.decline_button = discord.ui.Button(
            label="Recusar",
            style=discord.ButtonStyle.danger,
            emoji="💔",
        )
        self.accept_button.callback = self.accept
        self.decline_button.callback = self.decline
        self.add_item(self.accept_button)
        self.add_item(self.decline_button)
        self.set_message(
            content=(
                f"💌 {recipient.mention}, {proposer.mention} está te pedindo em casamento!\n"
                "Aceite ou recuse em até 2 minutos."
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.recipient.id:
            await interaction.response.send_message(
                "Este pedido só pode ser respondido pela pessoa convidada.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        self._disable_buttons()
        self.set_message(content="⌛ O pedido de casamento expirou sem resposta.")
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException as error:
                log.warning("Não foi possível atualizar o pedido de casamento expirado: %s", error)

    def _disable_buttons(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.ActionRow):
                for child in item.children:
                    if isinstance(child, discord.ui.Button):
                        child.disabled = True

    async def accept(self, interaction: discord.Interaction) -> None:
        result, married_at = await self.utilities._accept_marriage(
            self.guild_id,
            self.proposer.id,
            self.recipient.id,
        )
        self._disable_buttons()
        if result == "accepted" and married_at is not None:
            self.set_message(
                content=(
                    f"💞 {self.proposer.mention} e {self.recipient.mention} aceitaram "
                    f"se casar! Desde <t:{married_at}:F> (<t:{married_at}:R>)."
                ),
                hero_url=self.MARRIAGE_IMAGE,
            )
        elif result == "already_married" and married_at is not None:
            self.set_message(
                content=(
                    f"💍 {self.proposer.mention} e {self.recipient.mention} já estão "
                    f"casados desde <t:{married_at}:F> (<t:{married_at}:R>)."
                ),
                hero_url=self.MARRIAGE_IMAGE,
            )
        else:
            self.set_message(
                content="Uma das pessoas já está casada. O pedido não foi aceito."
            )
        await interaction.response.edit_message(view=self)
        self.stop()

    async def decline(self, interaction: discord.Interaction) -> None:
        self._disable_buttons()
        self.set_message(content=f"💌 {self.recipient.mention} recusou o pedido de casamento.")
        await interaction.response.edit_message(view=self)
        self.stop()


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

    @commands.hybrid_command(name="userinfo", description="Exibe informações detalhadas de um usuário")
    @app_commands.guild_only()
    async def userinfo(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
    ) -> None:
        member = member or ctx.author
        if not isinstance(member, discord.Member):
            return await ctx.send("Use este comando em um servidor para consultar cargos e data de entrada.")
        embed = discord.Embed(
            title=f"Informações de {member}",
            color=discord.Color.blue(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(
            name="Avatar",
            value=f"[Abrir imagem]({member.display_avatar.url})",
            inline=True,
        )
        embed.add_field(name="ID", value=str(member.id), inline=True)
        embed.add_field(
            name="Conta criada",
            value=f"<t:{int(member.created_at.timestamp())}:F>",
            inline=True,
        )
        if member.joined_at is not None:
            embed.add_field(
                name="Entrou no servidor",
                value=f"<t:{int(member.joined_at.timestamp())}:F>",
                inline=True,
            )
        embed.add_field(name="Bot", value="Sim" if member.bot else "Não", inline=True)
        roles = [role.mention for role in reversed(member.roles) if not role.is_default()]
        embed.add_field(
            name=f"Cargos ({len(roles)})",
            value=", ".join(roles)[:1024] or "Nenhum",
            inline=False,
        )

        try:
            profile = await self.bot.fetch_user(member.id)
        except discord.HTTPException as error:
            log.warning("Falha ao carregar o perfil de %s: %s", member.id, error)
            embed.add_field(
                name="Perfil",
                value="Não foi possível carregar o banner e as cores do perfil.",
                inline=False,
            )
        else:
            if profile.banner is not None:
                embed.set_image(url=profile.banner.url)
                embed.add_field(name="Banner", value="Exibido acima", inline=True)
            profile_colors: list[str] = []
            seen_colors: set[int] = set()
            for label, attribute in (
                ("Cor do perfil", "accent_color"),
                ("Cor principal", "primary_color"),
                ("Cor secundária", "secondary_color"),
                ("Cor terciária", "tertiary_color"),
            ):
                color = getattr(profile, attribute, None)
                if color is None or color.value in seen_colors:
                    continue
                seen_colors.add(color.value)
                profile_colors.append(f"{label}: `#{color.value:06X}`")
            if profile_colors:
                embed.add_field(
                    name="Cores do perfil",
                    value="\n".join(profile_colors),
                    inline=False,
                )

        await ctx.send(view=components_v2(embed))


class Utilities(commands.Cog):
    AFFECTION_ACTIONS = {
        "abraço": (
            "deu um abraço apertado em",
            "https://i.postimg.cc/JGVNmps0/Pin-on-Anime.gif",
        ),
        "beijo": (
            "deu um beijo carinhoso em",
            "https://i.postimg.cc/0bRYxVz6/yuri.gif",
        ),
        "cafuné": (
            "fez um cafuné em",
            "https://i.postimg.cc/4m6z3pcs/Head-pat.gif",
        ),
        "carinho": (
            "fez carinho em",
            "https://i.postimg.cc/4m6z3pcs/Head-pat.gif",
        ),
    }

    def __init__(self, bot):
        self.bot = bot
        self.pool: Pool | None = None

    async def cog_load(self) -> None:
        self.pool = await create_pool()
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS amie_marriages (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                partner_id INTEGER NOT NULL,
                married_at INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id),
                UNIQUE (guild_id, partner_id)
            )
            """
        )

    async def cog_unload(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def _accept_marriage(
        self,
        guild_id: int,
        proposer_id: int,
        recipient_id: int,
    ) -> tuple[str, int | None]:
        if self.pool is None:
            raise RuntimeError("O armazenamento de casamentos não está disponível.")
        married_at = int(discord.utils.utcnow().timestamp())
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                existing = await connection.fetchrow(
                    "SELECT user_id, partner_id, married_at FROM amie_marriages "
                    "WHERE guild_id = $1 AND "
                    "(user_id = $2 OR partner_id = $2 OR user_id = $3 OR partner_id = $3)",
                    guild_id,
                    proposer_id,
                    recipient_id,
                )
                if existing is not None:
                    if {
                        existing["user_id"],
                        existing["partner_id"],
                    } == {proposer_id, recipient_id}:
                        return "already_married", int(existing["married_at"])
                    return "unavailable", None
                await connection.execute(
                    "INSERT INTO amie_marriages "
                    "(guild_id, user_id, partner_id, married_at) VALUES ($1, $2, $3, $4)",
                    guild_id,
                    proposer_id,
                    recipient_id,
                    married_at,
                )
        return "accepted", married_at

    def _help_pages(self) -> list[str]:
        category_names = {
            "Admin": "Moderação",
            "ServerInfo": "Servidor",
            "UserInfo": "Usuários",
            "Utilities": "Utilidades",
            "AFK": "Utilidades",
        }
        groups: dict[str, list[str]] = {}
        hybrid_names: set[str] = set()
        prefix = self.bot.command_prefix
        if not isinstance(prefix, str):
            prefix = prefix[0] if prefix else ","

        for command in sorted(self.bot.commands, key=lambda item: item.name):
            if command.hidden:
                continue
            category = category_names.get(command.cog_name or "", command.cog_name or "Outros")
            description = (
                command.help
                or getattr(getattr(command, "app_command", None), "description", None)
                or "Sem descrição"
            )
            slash = getattr(command, "app_command", None)
            suffix = f" · `/{command.qualified_name}`" if slash is not None else ""
            groups.setdefault(category, []).append(
                f"`{prefix}{command.qualified_name}`{suffix} — {description}"
            )
            if slash is not None:
                hybrid_names.add(command.qualified_name)

        def add_app_commands(
            command: app_commands.Command | app_commands.Group,
            parent: str = "",
        ) -> None:
            qualified_name = f"{parent} {command.name}".strip()
            if isinstance(command, app_commands.Group):
                for child in command.commands:
                    add_app_commands(child, qualified_name)
                return
            if qualified_name in hybrid_names:
                return
            binding = getattr(command, "binding", None)
            cog_name = type(binding).__name__ if binding is not None else ""
            category = category_names.get(cog_name, cog_name or "Comandos de barra")
            description = command.description or "Sem descrição"
            groups.setdefault(category, []).append(
                f"`/{qualified_name}` — {description}"
            )

        for command in self.bot.tree.get_commands():
            if isinstance(command, (app_commands.Command, app_commands.Group)):
                add_app_commands(command)

        sections = [
            f"## {category}\n" + "\n".join(sorted(lines))
            for category, lines in sorted(groups.items())
        ]
        pages: list[str] = []
        current = "# Ajuda do bot\n"
        for section in sections:
            if len(current) + len(section) + 2 > 3500:
                if current.strip() != "# Ajuda do bot":
                    pages.append(current.rstrip())
                current = "# Ajuda do bot\n"
            if len(current) + len(section) + 2 > 3500:
                lines = section.splitlines()
                header = lines[0]
                current += header + "\n"
                for line in lines[1:]:
                    if len(current) + len(line) + 1 > 3500:
                        pages.append(current.rstrip())
                        current = "# Ajuda do bot (continuação)\n" + header + "\n"
                    current += line + "\n"
            else:
                current += section + "\n\n"
        if current.strip() != "# Ajuda do bot":
            pages.append(current.rstrip())
        return pages or ["# Ajuda do bot\nNenhum comando disponível."]

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

    @commands.hybrid_command(name="ajuda", description="Exibe todos os comandos separados por categoria")
    async def ajuda(self, ctx: commands.Context) -> None:
        await ctx.send(view=HelpPager(self._help_pages()))

    @commands.hybrid_command(name="ship", description="Calcula a compatibilidade de duas pessoas")
    async def ship(
        self,
        ctx: commands.Context,
        first: discord.Member,
        second: discord.Member,
    ) -> None:
        percentage = random.randint(1, 100)
        if percentage < 20:
            reaction = "🚫 Nem com muita sorte!"
            color = discord.Color.dark_red()
        elif percentage < 40:
            reaction = "😬 Vai ser complicado."
            color = discord.Color.red()
        elif percentage < 60:
            reaction = "🙂 Talvez role uma amizade."
            color = discord.Color.orange()
        elif percentage < 80:
            reaction = "💛 Tem potencial!"
            color = discord.Color.gold()
        else:
            reaction = "💞 Casal perfeito!"
            color = discord.Color.magenta()
        embed = discord.Embed(
            title="Ship de casal",
            description=(
                f"{first.mention} + {second.mention}\n\n"
                f"**Compatibilidade: {percentage}%**\n{reaction}"
            ),
            color=color,
        )
        await ctx.send(view=components_v2(embed))

    @commands.hybrid_command(name="roleta", description="Escolhe aleatoriamente entre 1 e 20 opções")
    @app_commands.describe(options="Separe as opções com | (exemplo: pizza | sushi | hambúrguer)")
    async def roleta(self, ctx: commands.Context, *, options: str) -> None:
        choices = [choice.strip() for choice in options.replace("\n", "|").split("|") if choice.strip()]
        if not 1 <= len(choices) <= 20:
            return await ctx.send("Informe de 1 a 20 opções, separadas por `|`.")
        selected = random.choice(choices)
        embed = discord.Embed(
            title="Roleta",
            description=f"🎯 A opção sorteada foi: **{selected}**",
            color=discord.Color.blurple(),
        )
        await ctx.send(view=components_v2(embed))

    @commands.hybrid_command(name="casar", description="Casa com alguém do servidor")
    @app_commands.guild_only()
    async def casar(self, ctx: commands.Context, member: discord.Member) -> None:
        guild = ctx.guild
        if guild is None or not isinstance(ctx.author, discord.Member):
            return await ctx.send("Este comando só pode ser usado em um servidor.")
        if member.id == ctx.author.id:
            return await ctx.send("Você não pode se casar consigo mesmo.")
        if member.bot or ctx.author.bot:
            return await ctx.send("Contas de bot não podem se casar.")
        if self.pool is None:
            raise RuntimeError("O armazenamento de casamentos não está disponível.")
        existing = await self.pool.fetchrow(
            "SELECT user_id, partner_id, married_at FROM amie_marriages "
            "WHERE guild_id = $1 AND "
            "(user_id = $2 OR partner_id = $2 OR user_id = $3 OR partner_id = $3)",
            guild.id,
            ctx.author.id,
            member.id,
        )
        if existing is not None and {
            existing["user_id"],
            existing["partner_id"],
        } != {ctx.author.id, member.id}:
            return await ctx.send(
                "Uma das pessoas já está casada. Use `,divorciar` antes de iniciar outro casamento."
            )
        if existing is not None:
            already_married_at = int(existing["married_at"])
            embed = discord.Embed(
                title="Casamento",
                description=(
                    f"💍 {ctx.author.mention} e {member.mention} já estão casados "
                    f"desde <t:{already_married_at}:F> (<t:{already_married_at}:R>)."
                ),
                color=discord.Color.magenta(),
            )
            return await ctx.send(view=components_v2(embed))
        proposal = MarriageProposalView(self, guild.id, ctx.author, member)
        proposal.message = await ctx.send(view=proposal)

    @commands.hybrid_command(
        name="acao",
        description="Faz um gesto carinhoso com seu cônjuge",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        action="Escolha um gesto carinhoso",
        member="A pessoa com quem você está casado",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Abraço", value="abraço"),
            app_commands.Choice(name="Beijo", value="beijo"),
            app_commands.Choice(name="Cafuné", value="cafuné"),
            app_commands.Choice(name="Carinho", value="carinho"),
        ]
    )
    async def acao(
        self,
        ctx: commands.Context,
        action: str,
        member: discord.Member,
    ) -> None:
        guild = ctx.guild
        if guild is None:
            return await ctx.send("Este comando só pode ser usado em um servidor.")
        if member.id == ctx.author.id:
            return await ctx.send("Escolha outra pessoa para fazer esse gesto.")
        if self.pool is None:
            raise RuntimeError("O armazenamento de casamentos não está disponível.")
        if action not in self.AFFECTION_ACTIONS:
            return await ctx.send("Escolha uma das ações carinhosas disponíveis.")
        marriage = await self.pool.fetchrow(
            "SELECT user_id, partner_id FROM amie_marriages "
            "WHERE guild_id = $1 AND "
            "((user_id = $2 AND partner_id = $3) OR (user_id = $3 AND partner_id = $2))",
            guild.id,
            ctx.author.id,
            member.id,
        )
        if marriage is None:
            return await ctx.send(
                "Vocês precisam estar casados um com o outro para usar essa ação."
            )
        action_text, image_url = self.AFFECTION_ACTIONS[action]
        embed = discord.Embed(
            title="Um momento fofo 💕",
            description=f"{ctx.author.mention} {action_text} {member.mention}!",
            color=discord.Color.magenta(),
        )
        embed.set_image(url=image_url)
        await ctx.send(view=components_v2(embed))

    @commands.hybrid_command(name="divorciar", description="Encerra seu casamento registrado")
    @app_commands.guild_only()
    async def divorciar(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        if guild is None:
            return await ctx.send("Este comando só pode ser usado em um servidor.")
        if self.pool is None:
            raise RuntimeError("O armazenamento de casamentos não está disponível.")
        marriage = await self.pool.fetchrow(
            "SELECT user_id, partner_id FROM amie_marriages "
            "WHERE guild_id = $1 AND (user_id = $2 OR partner_id = $2)",
            guild.id,
            ctx.author.id,
        )
        if marriage is None:
            return await ctx.send("Você não tem um casamento registrado neste servidor.")
        await self.pool.execute(
            "DELETE FROM amie_marriages WHERE guild_id = $1 AND user_id = $2",
            guild.id,
            marriage["user_id"],
        )
        partner_id = (
            marriage["partner_id"]
            if marriage["user_id"] == ctx.author.id
            else marriage["user_id"]
        )
        embed = discord.Embed(
            title="Divórcio registrado",
            description=f"O casamento com <@{partner_id}> foi encerrado.",
            color=discord.Color.dark_grey(),
        )
        await ctx.send(view=components_v2(embed))

    @commands.hybrid_command(name="serverinvite", description="Mostra o convite mais usado do servidor")
    @app_commands.guild_only()
    async def serverinvite(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        if guild is None:
            return await ctx.send("Este comando só pode ser usado em um servidor.")
        if guild.vanity_url is not None:
            invite_url = guild.vanity_url
            invite_details = "Convite personalizado do servidor."
        else:
            try:
                invites = await guild.invites()
            except discord.Forbidden:
                return await ctx.send(
                    "Não tenho permissão para consultar os convites deste servidor."
                )
            except discord.HTTPException as error:
                log.warning("Falha ao consultar convites do servidor %s: %s", guild.id, error)
                return await ctx.send(f"Não foi possível consultar os convites: {error}")
            if not invites:
                return await ctx.send("Este servidor não possui convites ativos.")
            most_used = max(invites, key=lambda invite: invite.uses or 0)
            invite_url = most_used.url
            invite_details = f"Convite ativo mais usado ({most_used.uses or 0} usos)."
        embed = discord.Embed(
            title="Convite do servidor",
            description=f"[Entrar no servidor]({invite_url})\n{invite_details}",
            color=discord.Color.green(),
        )
        await ctx.send(view=components_v2(embed))

async def setup(bot):
    await bot.add_cog(ServerInfo(bot))
    await bot.add_cog(UserInfo(bot))
    await bot.add_cog(Utilities(bot))
