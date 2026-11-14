from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands, tasks

from .database import Pool, create_pool


DEFAULT_TICKET_CONFIG = {
    "panel": {
        "title": "Central de atendimento",
        "description": "Selecione abaixo o assunto para abrir um ticket.",
        "image_url": "",
        "buttons": [],
    },
    "ticket": {
        "title": "Ticket de {tipo}",
        "description": "Olá {usuario}! Descreva seu caso para que a equipe possa ajudar.",
        "image_url": "",
    },
    "types": [
        {"name": "Denúncia", "description": "Relate uma denúncia.", "emoji": "🚨"},
        {"name": "Suporte Geral", "description": "Precisa de ajuda?", "emoji": "🛟"},
        {"name": "Dúvidas", "description": "Tire suas dúvidas.", "emoji": "❔"},
    ],
    "form_title": "Abrir ticket",
    "form_fields": [],
}


def ticket_config_defaults() -> dict:
    import copy

    return copy.deepcopy(DEFAULT_TICKET_CONFIG)


def validate_ticket_config(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("A configuração precisa ser um objeto JSON.")
    config = ticket_config_defaults()
    config.update(value)

    for section in ("panel", "ticket"):
        if not isinstance(config.get(section), dict):
            raise ValueError(f"`{section}` precisa ser um objeto JSON.")
        defaults = DEFAULT_TICKET_CONFIG[section]
        config[section] = {**defaults, **config[section]}
        for key in ("title", "description", "image_url"):
            field = config[section].get(key)
            maximum = 256 if key == "title" else 4000 if key == "description" else 500
            if not isinstance(field, str) or len(field) > maximum:
                raise ValueError(
                    f"`{section}.{key}` precisa ser texto com até {maximum} caracteres."
                )
        image_url = config[section]["image_url"].strip()
        if image_url and not _is_https_url(image_url):
            raise ValueError(f"`{section}.image_url` precisa ser uma URL HTTPS.")
        config[section]["image_url"] = image_url

    types = config.get("types")
    if not isinstance(types, list) or not 1 <= len(types) <= 25:
        raise ValueError("Configure entre 1 e 25 tipos de ticket.")
    normalized_types = []
    seen = set()
    for ticket_type in types:
        if not isinstance(ticket_type, dict):
            raise ValueError("Cada tipo precisa ser um objeto JSON.")
        name = ticket_type.get("name")
        description = ticket_type.get("description", "")
        emoji = ticket_type.get("emoji", "")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
            raise ValueError("O nome de cada tipo deve ter entre 1 e 100 caracteres.")
        if not isinstance(description, str) or len(description) > 100:
            raise ValueError("A descrição de cada tipo pode ter até 100 caracteres.")
        if not isinstance(emoji, str) or len(emoji) > 100:
            raise ValueError("O emoji de cada tipo pode ter até 100 caracteres.")
        slug = _ticket_slug(name)
        if slug in seen:
            raise ValueError("Os nomes dos tipos precisam ser únicos.")
        seen.add(slug)
        normalized_types.append(
            {"name": name.strip(), "description": description.strip(), "emoji": emoji}
        )
    config["types"] = normalized_types

    panel_buttons = config["panel"].get("buttons", [])
    if not isinstance(panel_buttons, list) or len(panel_buttons) > 4:
        raise ValueError("Configure até 4 botões de link no painel.")
    normalized_buttons = []
    for button in panel_buttons:
        if not isinstance(button, dict):
            raise ValueError("Cada botão precisa de rótulo e URL.")
        label, url = button.get("label"), button.get("url")
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 80:
            raise ValueError("O rótulo de cada botão deve ter de 1 a 80 caracteres.")
        if not isinstance(url, str) or not _is_https_url(url):
            raise ValueError("A URL de cada botão precisa começar com https://.")
        normalized_buttons.append({"label": label.strip(), "url": url.strip()})
    config["panel"]["buttons"] = normalized_buttons

    form_title = config.get("form_title")
    if not isinstance(form_title, str) or not 1 <= len(form_title.strip()) <= 45:
        raise ValueError("`form_title` precisa ter entre 1 e 45 caracteres.")
    config["form_title"] = form_title.strip()
    fields = config.get("form_fields")
    if not isinstance(fields, list) or len(fields) > 5:
        raise ValueError("Configure até 5 campos para o formulário.")
    normalized_fields = []
    for field in fields:
        if not isinstance(field, dict):
            raise ValueError("Cada campo do formulário precisa ser um objeto JSON.")
        label = field.get("label")
        placeholder = field.get("placeholder", "")
        style = field.get("style", "paragraph")
        required = field.get("required", True)
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 45:
            raise ValueError("O rótulo de cada campo deve ter de 1 a 45 caracteres.")
        if not isinstance(placeholder, str) or len(placeholder) > 100:
            raise ValueError("O placeholder de cada campo pode ter até 100 caracteres.")
        if style not in {"short", "paragraph"} or not isinstance(required, bool):
            raise ValueError("Use `short` ou `paragraph` e `required: true/false`.")
        normalized_fields.append(
            {
                "label": label.strip(),
                "placeholder": placeholder,
                "style": style,
                "required": required,
            }
        )
    config["form_fields"] = normalized_fields
    return config


def _is_https_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme == "https" and bool(parsed.netloc)


def _ticket_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")
    return slug[:90] or "atendimento"


class TicketOpenModal(discord.ui.Modal):
    def __init__(
        self,
        cog: "Ticket",
        guild_id: int,
        ticket_type: dict,
        config: dict,
    ):
        super().__init__(title=config["form_title"])
        self.cog = cog
        self.guild_id = guild_id
        self.ticket_type = ticket_type
        self.inputs: list[tuple[str, discord.ui.TextInput]] = []
        for field in config["form_fields"]:
            text_input = discord.ui.TextInput(
                label=field["label"],
                placeholder=field["placeholder"] or None,
                required=field["required"],
                style=(
                    discord.TextStyle.short
                    if field["style"] == "short"
                    else discord.TextStyle.paragraph
                ),
                max_length=4000 if field["style"] == "paragraph" else 400,
            )
            self.inputs.append((field["label"], text_input))
            self.add_item(text_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or interaction.guild.id != self.guild_id:
            return await interaction.response.send_message(
                "Este formulário não pertence a este servidor.", ephemeral=True
            )
        answers = [(label, item.value) for label, item in self.inputs]
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            channel = await self.cog.create_ticket(
                interaction.guild, interaction.user, self.ticket_type, answers
            )
        except (discord.Forbidden, discord.HTTPException, RuntimeError) as error:
            print(
                f"Não foi possível abrir ticket (guild={self.guild_id}, "
                f"user={interaction.user.id}): {type(error).__name__}: {error}",
                flush=True,
            )
            return await interaction.followup.send(
                f"Não consegui abrir seu ticket: {error}", ephemeral=True
            )
        await interaction.followup.send(
            f"Seu ticket foi aberto: {channel.mention}", ephemeral=True
        )


class TicketTypeSelect(discord.ui.Select):
    def __init__(self, cog: "Ticket", config: dict):
        options = [
            discord.SelectOption(
                label=item["name"],
                value=_ticket_slug(item["name"]),
                description=item["description"] or None,
                emoji=item["emoji"] or None,
            )
            for item in config["types"]
        ]
        super().__init__(
            placeholder="Escolha o tipo de atendimento",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="tickets:open",
        )
        self.cog = cog
        self.ticket_types = config["types"]

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return await interaction.response.send_message(
                "Abra um ticket dentro de um servidor.", ephemeral=True
            )
        ticket_type = next(
            (
                item
                for item in self.ticket_types
                if _ticket_slug(item["name"]) == self.values[0]
            ),
            None,
        )
        if ticket_type is None:
            return await interaction.response.send_message(
                "Esse tipo de ticket não está mais disponível.", ephemeral=True
            )
        config = self.cog.ticket_config(interaction.guild.id)
        if config["form_fields"]:
            return await interaction.response.send_modal(
                TicketOpenModal(
                    self.cog, interaction.guild.id, ticket_type, config
                )
            )
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            channel = await self.cog.create_ticket(
                interaction.guild, interaction.user, ticket_type, []
            )
        except (discord.Forbidden, discord.HTTPException, RuntimeError) as error:
            print(
                f"Não foi possível abrir ticket (guild={interaction.guild.id}, "
                f"user={interaction.user.id}): {type(error).__name__}: {error}",
                flush=True,
            )
            return await interaction.followup.send(
                f"Não consegui abrir seu ticket: {error}", ephemeral=True
            )
        await interaction.followup.send(
            f"Seu ticket foi aberto: {channel.mention}", ephemeral=True
        )


class TicketPanelView(discord.ui.View):
    def __init__(self, cog: "Ticket", config: dict):
        super().__init__(timeout=None)
        self.add_item(TicketTypeSelect(cog, config))
        for index, button in enumerate(config["panel"]["buttons"]):
            self.add_item(
                discord.ui.Button(
                    label=button["label"],
                    url=button["url"],
                    row=1 + index // 5,
                )
            )


class TicketActionsSelect(discord.ui.Select):
    def __init__(self, cog: "Ticket"):
        super().__init__(
            placeholder="Painel do Ticket · selecione uma ação",
            min_values=1,
            max_values=1,
            custom_id="tickets:actions",
            options=[
                discord.SelectOption(label="Assumir Ticket", value="claim", emoji="🙋"),
                discord.SelectOption(label="Fechar Ticket", value="close", emoji="🔒"),
                discord.SelectOption(label="Expulsar Usuário", value="kick", emoji="👢"),
                discord.SelectOption(label="Banir Usuário", value="ban", emoji="⛔"),
                discord.SelectOption(label="Castigar Usuário", value="timeout", emoji="🔇"),
            ],
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not isinstance(
            interaction.user, discord.Member
        ):
            return await interaction.response.send_message(
                "Esta ação só pode ser usada no servidor.", ephemeral=True
            )
        ticket = await self.cog.get_open_ticket(interaction.channel_id)
        if ticket is None:
            return await interaction.response.send_message(
                "Este canal não está registrado como ticket aberto.", ephemeral=True
            )
        if not self.cog.can_manage_ticket(interaction.user, interaction.guild.id):
            return await interaction.response.send_message(
                "Somente a equipe de suporte configurada ou um administrador "
                "pode usar o Painel do Ticket.",
                ephemeral=True,
            )
        action = self.values[0]
        if action == "claim":
            await self.cog.claim_ticket(interaction)
        elif action == "close":
            await interaction.response.defer(ephemeral=True, thinking=True)
            try:
                await self.cog.close_ticket(
                    interaction.channel, ticket, interaction.user
                )
            except (discord.Forbidden, discord.HTTPException, RuntimeError) as error:
                return await interaction.followup.send(
                    f"Não consegui fechar o ticket: {error}", ephemeral=True
                )
            await interaction.followup.send("Ticket fechado.", ephemeral=True)
        else:
            await interaction.response.defer(ephemeral=True, thinking=True)
            await self.cog.moderate_opener(interaction, ticket, action)


class CallSupportButton(discord.ui.Button):
    def __init__(self, cog: "Ticket"):
        super().__init__(
            label="Chamar Atendentes",
            style=discord.ButtonStyle.primary,
            custom_id="tickets:call_support",
            row=1,
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return await interaction.response.send_message(
                "Esta ação só pode ser usada no servidor.", ephemeral=True
            )
        ticket = await self.cog.get_open_ticket(interaction.channel_id)
        if ticket is None:
            return await interaction.response.send_message(
                "Este canal não está registrado como ticket aberto.", ephemeral=True
            )
        if interaction.user.id != int(ticket["opener_id"]):
            return await interaction.response.send_message(
                "Somente quem abriu o ticket pode chamar os atendentes.",
                ephemeral=True,
            )
        mentions = self.cog.support_mentions(interaction.guild.id)
        if not mentions:
            return await interaction.response.send_message(
                "Nenhum cargo de suporte está configurado.", ephemeral=True
            )
        await interaction.response.send_message(
            f"{mentions} — atendimento solicitado em {interaction.channel.mention}.",
            allowed_mentions=discord.AllowedMentions(roles=True, users=False),
        )


class TicketManagerView(discord.ui.View):
    def __init__(self, cog: "Ticket"):
        super().__init__(timeout=None)
        self.add_item(TicketActionsSelect(cog))
        self.add_item(CallSupportButton(cog))


class InactivityWarningView(discord.ui.View):
    def __init__(self, cog: "Ticket"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Fechar",
        style=discord.ButtonStyle.danger,
        custom_id="tickets:idle_close",
    )
    async def close_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        if _button.disabled:
            return
        ticket = await self.cog.get_open_ticket(interaction.channel_id)
        if ticket is None:
            return await interaction.response.send_message(
                "Este ticket já foi fechado.", ephemeral=True
            )
        await interaction.response.defer()
        try:
            await self.cog.close_ticket(
                interaction.channel, ticket, interaction.user
            )
        except (discord.Forbidden, discord.HTTPException, RuntimeError) as error:
            await interaction.followup.send(
                f"Não consegui fechar o ticket: {error}", ephemeral=True
            )

    @discord.ui.button(
        label="Não fechar",
        style=discord.ButtonStyle.secondary,
        custom_id="tickets:idle_keep",
    )
    async def keep_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        if _button.disabled:
            return
        await interaction.response.defer()
        await interaction.message.delete()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            return False
        if not self.cog.can_manage_ticket(interaction.user, interaction.guild.id):
            await interaction.response.send_message(
                "Somente a equipe de suporte configurada ou um administrador "
                "pode responder a este aviso.",
                ephemeral=True,
            )
            return False
        return True


class Ticket(commands.Cog):
    ticket = app_commands.Group(
        name="ticket", description="Gerencie o painel de tickets do servidor"
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pool: Pool | None = None

    async def cog_load(self) -> None:
        self.pool = await create_pool()
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS amie_tickets (
                channel_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                opener_id INTEGER NOT NULL,
                ticket_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                claimed_by INTEGER,
                opened_at INTEGER NOT NULL,
                closed_at INTEGER,
                last_activity_at INTEGER NOT NULL,
                inactivity_warned INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self.bot.add_view(TicketPanelView(self, ticket_config_defaults()))
        self.bot.add_view(TicketManagerView(self))
        self.bot.add_view(InactivityWarningView(self))

    async def cog_unload(self) -> None:
        if self.check_inactive_tickets.is_running():
            self.check_inactive_tickets.cancel()
        if self.pool is not None:
            await self.pool.close()

    def menu(self):
        return self.bot.get_cog("Menu")

    def setting(self, guild_id: int, key: str, default=None):
        menu = self.menu()
        if menu is None:
            return default
        return menu.get_value(guild_id, key, default)

    def ticket_config(self, guild_id: int) -> dict:
        configured = self.setting(guild_id, "tickets_config", None)
        try:
            return validate_ticket_config(configured or {})
        except ValueError as error:
            print(
                f"Configuração de tickets inválida (guild={guild_id}): {error}",
                flush=True,
            )
            return ticket_config_defaults()

    def support_role_ids(self, guild_id: int) -> set[int]:
        value = self.setting(guild_id, "tickets_support_roles", [])
        if not isinstance(value, list):
            return set()
        return {int(role_id) for role_id in value if str(role_id).isdigit()}

    def support_mentions(self, guild_id: int) -> str:
        return " ".join(
            f"<@&{role_id}>" for role_id in sorted(self.support_role_ids(guild_id))
        )

    def can_manage_ticket(self, member: discord.Member | discord.User, guild_id: int) -> bool:
        return isinstance(member, discord.Member) and (
            member.guild_permissions.administrator
            or any(role.id in self.support_role_ids(guild_id) for role in member.roles)
        )

    async def get_open_ticket(self, channel_id: int):
        if self.pool is None:
            raise RuntimeError("O banco de tickets ainda não está disponível.")
        return await self.pool.fetchrow(
            "SELECT * FROM amie_tickets WHERE channel_id = $1 AND status = 'open'",
            channel_id,
        )

    def panel_embed(self, guild_id: int) -> discord.Embed:
        panel = self.ticket_config(guild_id)["panel"]
        embed = discord.Embed(
            title=panel["title"],
            description=panel["description"],
            color=discord.Color.blurple(),
        )
        if panel["image_url"]:
            embed.set_image(url=panel["image_url"])
        return embed

    async def create_ticket(
        self,
        guild: discord.Guild,
        opener: discord.User | discord.Member,
        ticket_type: dict,
        answers: list[tuple[str, str]],
    ) -> discord.TextChannel:
        if self.pool is None:
            raise RuntimeError("O banco de tickets ainda não está disponível.")
        if not self.setting(guild.id, "module_tickets", False):
            raise RuntimeError("O sistema de tickets está desativado no `/menu`.")
        role_ids = self.support_role_ids(guild.id)
        support_roles = [
            role for role_id in role_ids if (role := guild.get_role(role_id)) is not None
        ]
        if not support_roles:
            raise RuntimeError("Configure ao menos um cargo de suporte no `/menu`.")
        bot_member = guild.me
        if bot_member is None:
            raise RuntimeError("Não consegui localizar o bot neste servidor.")
        overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            opener: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            ),
            bot_member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True,
            ),
        }
        for role in support_roles:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True,
            )
        channel = await guild.create_text_channel(
            name=f"ticket-{_ticket_slug(ticket_type['name'])}",
            overwrites=overwrites,
            reason=f"Ticket de {opener} ({opener.id})",
        )
        now = int(datetime.now(timezone.utc).timestamp())
        try:
            await self.pool.execute(
                """
                INSERT INTO amie_tickets (
                    channel_id, guild_id, opener_id, ticket_type, status,
                    opened_at, last_activity_at
                ) VALUES ($1, $2, $3, $4, 'open', $5, $5)
                """,
                channel.id,
                guild.id,
                opener.id,
                ticket_type["name"],
                now,
            )
            config = self.ticket_config(guild.id)
            ticket_embed_config = config["ticket"]
            roles_text = self.support_mentions(guild.id)
            title = (
                ticket_embed_config["title"]
                .replace("{tipo}", ticket_type["name"])
                .replace("{usuario}", opener.display_name)
            )
            description = (
                ticket_embed_config["description"]
                .replace("{tipo}", ticket_type["name"])
                .replace("{usuario}", opener.mention)
                .replace("{cargos_suporte}", roles_text)
            )
            embed = discord.Embed(
                title=title[:256] or "Ticket",
                description=description[:4000] or None,
                color=discord.Color.blurple(),
                timestamp=datetime.fromtimestamp(now, timezone.utc),
            )
            if ticket_embed_config["image_url"]:
                embed.set_image(url=ticket_embed_config["image_url"])
            embed.add_field(name="Tipo de atendimento", value=ticket_type["name"])
            embed.add_field(
                name="Equipe de suporte",
                value=roles_text or "Nenhum cargo configurado",
                inline=False,
            )
            if answers:
                for label, answer in answers:
                    embed.add_field(
                        name=label[:256],
                        value=(answer or "*(sem resposta)*")[:1024],
                        inline=False,
                    )
            embed.set_footer(text=f"Ticket aberto por {opener} · ID {opener.id}")
            content = f"{opener.mention} {roles_text}".strip()
            await channel.send(
                content=content or None,
                embed=embed,
                view=TicketManagerView(self),
                allowed_mentions=discord.AllowedMentions(
                    users=True, roles=True, everyone=False
                ),
            )
        except BaseException:
            await channel.delete(reason="Falha ao inicializar ticket")
            await self.pool.execute(
                "DELETE FROM amie_tickets WHERE channel_id = $1", channel.id
            )
            raise
        return channel

    async def claim_ticket(self, interaction: discord.Interaction) -> None:
        if self.pool is None:
            raise RuntimeError("O banco de tickets ainda não está disponível.")
        await self.pool.execute(
            "UPDATE amie_tickets SET claimed_by = $1 WHERE channel_id = $2 AND status = 'open'",
            interaction.user.id,
            interaction.channel_id,
        )
        await interaction.response.send_message(
            f"{interaction.user.mention} assumiu este ticket.",
            allowed_mentions=discord.AllowedMentions(users=True),
        )

    async def moderate_opener(
        self, interaction: discord.Interaction, ticket, action: str
    ) -> None:
        guild = interaction.guild
        if guild is None:
            return
        try:
            member = guild.get_member(int(ticket["opener_id"]))
            if member is None:
                member = await guild.fetch_member(int(ticket["opener_id"]))
            if action == "kick":
                await member.kick(reason=f"Ticket moderado por {interaction.user}")
                result = f"{member} foi expulso do servidor."
            elif action == "ban":
                await guild.ban(
                    member, reason=f"Ticket moderado por {interaction.user}"
                )
                result = f"{member} foi banido do servidor."
            else:
                await member.timeout(
                    discord.utils.utcnow() + timedelta(minutes=10),
                    reason=f"Ticket moderado por {interaction.user}",
                )
                result = f"{member} recebeu castigo de 10 minutos."
        except discord.NotFound:
            return await interaction.followup.send(
                "A pessoa que abriu o ticket não está mais no servidor.",
                ephemeral=True,
            )
        except (discord.Forbidden, discord.HTTPException) as error:
            print(
                f"Falha na ação {action} de ticket (guild={guild.id}, "
                f"actor={interaction.user.id}): {type(error).__name__}: {error}",
                flush=True,
            )
            return await interaction.followup.send(
                f"Não consegui executar a ação: {error}", ephemeral=True
            )
        await interaction.followup.send(result, ephemeral=True)

    async def close_ticket(
        self,
        channel: discord.abc.GuildChannel | None,
        ticket,
        closed_by: discord.User | discord.Member | None,
    ) -> None:
        if self.pool is None:
            raise RuntimeError("O banco de tickets ainda não está disponível.")
        guild = channel.guild if channel is not None else self.bot.get_guild(int(ticket["guild_id"]))
        if guild is None:
            raise RuntimeError("O servidor do ticket não está disponível.")
        log_channel_id = self.setting(guild.id, "tickets_log_channel")
        log_channel = guild.get_channel(int(log_channel_id)) if log_channel_id else None
        opened_at = datetime.fromtimestamp(int(ticket["opened_at"]), timezone.utc)
        closed_at = datetime.now(timezone.utc)
        opener = guild.get_member(int(ticket["opener_id"]))
        embed = discord.Embed(
            title="Ticket fechado",
            color=discord.Color.dark_grey(),
            timestamp=closed_at,
        )
        embed.add_field(
            name="Pessoa que assumiu",
            value=(
                f"<@{ticket['claimed_by']}>"
                if ticket["claimed_by"]
                else "Ninguém assumiu"
            ),
            inline=True,
        )
        embed.add_field(
            name="Pessoa que abriu",
            value=(
                opener.mention
                if opener is not None
                else f"<@{ticket['opener_id']}>"
            ),
            inline=True,
        )
        embed.add_field(name="Tipo de atendimento", value=ticket["ticket_type"], inline=True)
        embed.add_field(
            name="Abertura",
            value=f"<t:{int(opened_at.timestamp())}:F>",
            inline=True,
        )
        embed.add_field(name="Fechamento", value=f"<t:{int(closed_at.timestamp())}:F>", inline=True)
        embed.add_field(
            name="Fechado por",
            value=closed_by.mention if closed_by is not None else "Saída do servidor",
            inline=True,
        )
        if isinstance(log_channel, (discord.TextChannel, discord.Thread)):
            try:
                await log_channel.send(
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except (discord.Forbidden, discord.HTTPException) as error:
                print(
                    f"Não foi possível enviar log de fechamento "
                    f"(guild={guild.id}, ticket={ticket['channel_id']}): "
                    f"{type(error).__name__}: {error}",
                    flush=True,
                )
        else:
            print(
                f"Canal de logs de tickets não configurado ou inválido "
                f"(guild={guild.id}, ticket={ticket['channel_id']}).",
                flush=True,
            )
        await self.pool.execute(
            "UPDATE amie_tickets SET status = 'closing' WHERE channel_id = $1 AND status = 'open'",
            int(ticket["channel_id"]),
        )
        if channel is not None:
            try:
                await channel.delete(reason=f"Ticket fechado por {closed_by or 'sistema'}")
            except (discord.Forbidden, discord.HTTPException):
                await self.pool.execute(
                    "UPDATE amie_tickets SET status = 'open' WHERE channel_id = $1",
                    int(ticket["channel_id"]),
                )
                raise
        await self.pool.execute(
            "UPDATE amie_tickets SET status = 'closed', closed_at = $1 WHERE channel_id = $2",
            int(closed_at.timestamp()),
            int(ticket["channel_id"]),
        )

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self.reconcile_tickets()
        if not self.check_inactive_tickets.is_running():
            self.check_inactive_tickets.start()

    async def reconcile_tickets(self) -> None:
        if self.pool is None:
            return
        rows = await self.pool.fetch(
            """
            SELECT channel_id, guild_id FROM amie_tickets
            WHERE status IN ('open', 'closing')
            """
        )
        now = int(datetime.now(timezone.utc).timestamp())
        for row in rows:
            guild = self.bot.get_guild(int(row["guild_id"]))
            channel = (
                guild.get_channel(int(row["channel_id"])) if guild is not None else None
            )
            if channel is None:
                await self.pool.execute(
                    """
                    UPDATE amie_tickets SET status = 'closed',
                        closed_at = COALESCE(closed_at, $1)
                    WHERE channel_id = $2 AND status IN ('open', 'closing')
                    """,
                    now,
                    int(row["channel_id"]),
                )
            else:
                await self.pool.execute(
                    """
                    UPDATE amie_tickets SET status = 'open'
                    WHERE channel_id = $1 AND status = 'closing'
                    """,
                    int(row["channel_id"]),
                )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if self.pool is None:
            return
        rows = await self.pool.fetch(
            """
            SELECT * FROM amie_tickets
            WHERE guild_id = $1 AND opener_id = $2 AND status = 'open'
            """,
            member.guild.id,
            member.id,
        )
        for ticket in rows:
            channel = member.guild.get_channel(int(ticket["channel_id"]))
            try:
                await self.close_ticket(channel, ticket, None)
            except (discord.Forbidden, discord.HTTPException, RuntimeError) as error:
                print(
                    f"Não foi possível fechar ticket após saída de membro "
                    f"(guild={member.guild.id}, user={member.id}, "
                    f"channel={ticket['channel_id']}): "
                    f"{type(error).__name__}: {error}",
                    flush=True,
                )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if self.pool is None:
            return
        now = int(datetime.now(timezone.utc).timestamp())
        ticket = await self.pool.fetchrow(
            """
            SELECT * FROM amie_tickets
            WHERE channel_id = $1 AND status = 'open'
            """,
            channel.id,
        )
        if ticket is not None:
            await self.pool.execute(
                """
                UPDATE amie_tickets SET status = 'closing'
                WHERE channel_id = $1 AND status = 'open'
                """,
                channel.id,
            )
            await self.log_deleted_ticket(channel.guild, ticket, now)
        await self.pool.execute(
            """
            UPDATE amie_tickets SET status = 'closed', closed_at = COALESCE(closed_at, $1)
            WHERE channel_id = $2 AND status IN ('open', 'closing')
            """,
            now,
            channel.id,
        )

    async def log_deleted_ticket(self, guild: discord.Guild, ticket, closed_at: int) -> None:
        log_channel_id = self.setting(guild.id, "tickets_log_channel")
        log_channel = guild.get_channel(int(log_channel_id)) if log_channel_id else None
        if not isinstance(log_channel, (discord.TextChannel, discord.Thread)):
            print(
                f"Canal de logs de tickets não configurado ou inválido "
                f"(guild={guild.id}, ticket={ticket['channel_id']}).",
                flush=True,
            )
            return
        opener = guild.get_member(int(ticket["opener_id"]))
        embed = discord.Embed(
            title="Ticket removido",
            color=discord.Color.dark_grey(),
            timestamp=datetime.fromtimestamp(closed_at, timezone.utc),
        )
        embed.add_field(
            name="Pessoa que assumiu",
            value=f"<@{ticket['claimed_by']}>" if ticket["claimed_by"] else "Ninguém assumiu",
            inline=True,
        )
        embed.add_field(
            name="Pessoa que abriu",
            value=opener.mention if opener is not None else f"<@{ticket['opener_id']}>",
            inline=True,
        )
        embed.add_field(
            name="Tipo de atendimento", value=ticket["ticket_type"], inline=True
        )
        embed.add_field(
            name="Abertura",
            value=f"<t:{int(ticket['opened_at'])}:F>",
            inline=True,
        )
        embed.add_field(name="Fechamento", value=f"<t:{closed_at}:F>", inline=True)
        embed.add_field(name="Fechado por", value="Canal removido", inline=True)
        try:
            await log_channel.send(
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.HTTPException) as error:
            print(
                f"Não foi possível enviar log de canal de ticket removido "
                f"(guild={guild.id}, ticket={ticket['channel_id']}): "
                f"{type(error).__name__}: {error}",
                flush=True,
            )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot or self.pool is None:
            return
        await self.pool.execute(
            """
            UPDATE amie_tickets SET last_activity_at = $1
            WHERE channel_id = $2 AND status = 'open'
            """,
            int(datetime.now(timezone.utc).timestamp()),
            message.channel.id,
        )

    @tasks.loop(minutes=1)
    async def check_inactive_tickets(self) -> None:
        if self.pool is None:
            return
        threshold = int(datetime.now(timezone.utc).timestamp()) - 3600
        rows = await self.pool.fetch(
            """
            SELECT * FROM amie_tickets
            WHERE status = 'open' AND inactivity_warned = 0
              AND last_activity_at <= $1
            """,
            threshold,
        )
        for ticket in rows:
            guild = self.bot.get_guild(int(ticket["guild_id"]))
            channel = (
                guild.get_channel(int(ticket["channel_id"])) if guild else None
            )
            if not isinstance(channel, discord.TextChannel):
                await self.pool.execute(
                    """
                    UPDATE amie_tickets SET status = 'closed', closed_at = $1
                    WHERE channel_id = $2 AND status = 'open'
                    """,
                    int(datetime.now(timezone.utc).timestamp()),
                    int(ticket["channel_id"]),
                )
                continue
            mentions = self.support_mentions(guild.id)
            try:
                await channel.send(
                    content=(
                        f"{mentions} este ticket está inativo há mais de uma hora. "
                        "Deseja fechá-lo?"
                    ).strip(),
                    view=InactivityWarningView(self),
                    allowed_mentions=discord.AllowedMentions(
                        roles=True, users=False
                    ),
                )
            except (discord.Forbidden, discord.HTTPException) as error:
                print(
                    f"Não foi possível enviar aviso de inatividade "
                    f"(ticket={ticket['channel_id']}): "
                    f"{type(error).__name__}: {error}",
                    flush=True,
                )
                continue
            await self.pool.execute(
                "UPDATE amie_tickets SET inactivity_warned = 1 WHERE channel_id = $1 AND status = 'open'",
                int(ticket["channel_id"]),
            )

    @check_inactive_tickets.before_loop
    async def before_check_inactive_tickets(self) -> None:
        await self.bot.wait_until_ready()

    @ticket.command(name="painel", description="Publica o painel de abertura de tickets")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def publish_panel(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message(
                "Use este comando dentro de um servidor.", ephemeral=True
            )
        if not self.setting(guild.id, "module_tickets", False):
            return await interaction.response.send_message(
                "Ative o Sistema de tickets no `/menu` antes de publicar o painel.",
                ephemeral=True,
            )
        if not self.support_role_ids(guild.id):
            return await interaction.response.send_message(
                "Configure os cargos de suporte no `/menu` antes de publicar o painel.",
                ephemeral=True,
            )
        log_channel_id = self.setting(guild.id, "tickets_log_channel")
        log_channel = guild.get_channel(int(log_channel_id)) if log_channel_id else None
        if not isinstance(log_channel, (discord.TextChannel, discord.Thread)):
            return await interaction.response.send_message(
                "Configure um canal de logs de tickets no `/menu` antes de publicar.",
                ephemeral=True,
            )
        panel_channel_id = self.setting(guild.id, "tickets_panel_channel")
        panel_channel = (
            guild.get_channel(int(panel_channel_id))
            if panel_channel_id
            else interaction.channel
        )
        if not isinstance(panel_channel, discord.TextChannel):
            return await interaction.response.send_message(
                "Configure um canal de texto para o painel no `/menu`.",
                ephemeral=True,
            )
        try:
            message = await panel_channel.send(
                embed=self.panel_embed(guild.id),
                view=TicketPanelView(self, self.ticket_config(guild.id)),
            )
        except (discord.Forbidden, discord.HTTPException) as error:
            print(
                f"Não foi possível publicar painel de tickets (guild={guild.id}): "
                f"{type(error).__name__}: {error}",
                flush=True,
            )
            return await interaction.response.send_message(
                f"Não consegui publicar o painel: {error}", ephemeral=True
            )
        await interaction.response.send_message(
            f"Painel publicado em {message.jump_url}", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Ticket(bot))
