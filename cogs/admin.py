import asyncio
import datetime
import io
import logging
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands
from discord.ext import tasks

from .components_v2 import components_v2
from .database import Pool, create_pool

from .menu import DEVELOPER_ID, WARN_PUNISHMENT_CHOICES

log = logging.getLogger(__name__)


class AssetCreationModal(discord.ui.Modal):
    def __init__(
        self,
        guild: discord.Guild,
        attachment: discord.Attachment,
        *,
        sticker: bool,
        initial_name: str | None = None,
    ) -> None:
        super().__init__(title="Criar sticker" if sticker else "Criar emoji")
        self.guild = guild
        self.attachment = attachment
        self.sticker = sticker
        self.asset_name = discord.ui.TextInput(
            label="Nome",
            min_length=2,
            max_length=30,
            placeholder="Escolha um nome para o arquivo",
            default=(
                initial_name[:30]
                if initial_name is not None and len(initial_name) >= 2
                else None
            ),
        )
        self.add_item(self.asset_name)
        self.asset_description: discord.ui.TextInput | None = None
        if sticker:
            self.asset_description = discord.ui.TextInput(
                label="Descrição",
                max_length=100,
                placeholder="Descreva o sticker",
                required=False,
                min_length=2,
            )
            self.add_item(self.asset_description)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            image_data = await self.attachment.read()
            if self.sticker:
                description = (
                    self.asset_description.value
                    if self.asset_description is not None
                    else ""
                )
                image_file = discord.File(
                    io.BytesIO(image_data),
                    filename=self.attachment.filename,
                )
                try:
                    await self.guild.create_sticker(
                        name=self.asset_name.value,
                        description=description or "Sticker do servidor",
                        emoji="🙂",
                        file=image_file,
                        reason=f"Criado por {interaction.user}",
                    )
                finally:
                    image_file.close()
            else:
                await self.guild.create_custom_emoji(
                    name=self.asset_name.value,
                    image=image_data,
                    reason=f"Criado por {interaction.user}",
                )
        except discord.Forbidden:
            await interaction.followup.send(
                "O Discord negou a criação. Verifique a permissão do bot e os limites do servidor.",
                ephemeral=True,
            )
        except discord.HTTPException as error:
            log.warning("Falha ao criar recurso do servidor: %s", error)
            await interaction.followup.send(
                f"Não foi possível criar o recurso: {error}",
                ephemeral=True,
            )
        else:
            label = "Sticker" if self.sticker else "Emoji"
            await interaction.followup.send(
                view=components_v2(
                    discord.Embed(
                        title=f"{label} criado",
                        description=f"`{self.asset_name.value}` foi adicionado ao servidor.",
                        color=discord.Color.green(),
                    )
                ),
                ephemeral=True,
            )


class NukeChannelView(discord.ui.View):
    def __init__(self, channel: discord.TextChannel, requester_id: int) -> None:
        super().__init__(timeout=60)
        self.channel = channel
        self.requester_id = requester_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Somente quem iniciou a confirmação pode usar estes botões.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        del _button
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            replacement = await self.channel.clone(
                reason=f"Canal recriado por {interaction.user}"
            )
            await replacement.edit(position=self.channel.position)
            await self.channel.delete(reason=f"Canal recriado por {interaction.user}")
        except discord.Forbidden:
            await interaction.followup.send(
                "Não tenho permissão para clonar ou excluir este canal.",
                ephemeral=True,
            )
        except discord.HTTPException as error:
            log.warning("Falha ao recriar o canal %s: %s", self.channel.id, error)
            await interaction.followup.send(
                f"Não foi possível concluir a recriação do canal: {error}",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"Canal recriado: {replacement.mention}",
                ephemeral=True,
            )
        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        del _button
        await interaction.response.edit_message(
            content="Recriação cancelada.",
            view=None,
        )
        self.stop()


class BoostAssignmentView(discord.ui.View):
    def __init__(self, admin: "Admin"):
        super().__init__(timeout=180)
        self.admin = admin

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != DEVELOPER_ID:
            await interaction.response.send_message(
                "Somente o desenvolvedor pode usar este painel.", ephemeral=True
            )
            return False
        return True


class BoostAssignmentModeSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Escolha o tipo de cargo",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label="Setar cargo personalizado", value="personal"
                ),
                discord.SelectOption(label="Setar família", value="family"),
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: BoostAssignmentView = self.view
        details_view = BoostAssignmentDetailsView(view.admin, self.values[0])
        await interaction.response.edit_message(
            content=details_view.status_text(interaction.guild),
            view=details_view,
        )


class BoostAssignmentModePanel(BoostAssignmentView):
    def __init__(self, admin: "Admin"):
        super().__init__(admin)
        self.add_item(BoostAssignmentModeSelect())


class BoostAssignmentRoleSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(
            placeholder="Selecione o cargo",
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: BoostAssignmentDetailsView = self.view
        view.role_id = self.values[0].id
        await interaction.response.edit_message(
            content=view.status_text(interaction.guild), view=view
        )


class BoostAssignmentMemberSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(
            placeholder="Selecione a pessoa dona do cargo",
            min_values=1,
            max_values=1,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: BoostAssignmentDetailsView = self.view
        view.user_id = self.values[0].id
        await interaction.response.edit_message(
            content=view.status_text(interaction.guild), view=view
        )


class BoostAssignmentConfirmButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Confirmar associação",
            style=discord.ButtonStyle.success,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: BoostAssignmentDetailsView = self.view
        await view.confirm(interaction)


class BoostAssignmentDetailsView(BoostAssignmentView):
    def __init__(self, admin: "Admin", mode: str):
        super().__init__(admin)
        self.mode = mode
        self.role_id: int | None = None
        self.user_id: int | None = None
        self.add_item(BoostAssignmentRoleSelect())
        self.add_item(BoostAssignmentMemberSelect())
        self.add_item(BoostAssignmentConfirmButton())

    def status_text(self, guild: discord.Guild | None) -> str:
        mode_label = (
            "cargo personalizado" if self.mode == "personal" else "família"
        )
        role = guild.get_role(self.role_id) if guild and self.role_id else None
        role_text = role.mention if role else "não selecionado"
        user_text = f"<@{self.user_id}>" if self.user_id else "não selecionada"
        return (
            f"Tipo: **{mode_label}**\n"
            f"Cargo: {role_text}\n"
            f"Pessoa dona: {user_text}\n\n"
            "Selecione o cargo e a pessoa, depois confirme."
        )

    async def confirm(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None or self.role_id is None or self.user_id is None:
            return await interaction.response.send_message(
                "Selecione um cargo e uma pessoa antes de confirmar.",
                ephemeral=True,
            )

        boost = self.admin.bot.get_cog("Boost")
        if boost is None or boost.pool is None:
            return await interaction.response.send_message(
                "O cog boost está sem conexão com o NeonDB.", ephemeral=True
            )

        role = guild.get_role(self.role_id)
        member = guild.get_member(self.user_id)
        bot_member = guild.me
        if role is None or member is None:
            return await interaction.response.send_message(
                "O cargo ou a pessoa selecionada não está mais neste servidor.",
                ephemeral=True,
            )
        if role.is_default() or role.managed:
            return await interaction.response.send_message(
                "Não é possível registrar o cargo padrão ou um cargo gerenciado.",
                ephemeral=True,
            )
        if bot_member is None or role >= bot_member.top_role:
            return await interaction.response.send_message(
                "Meu cargo precisa estar acima do cargo selecionado.",
                ephemeral=True,
            )

        key = boost.key(guild.id, member.id)
        previous_family = boost.families.get(key)
        previous_personal = boost.personal_roles.get(key)
        added_role = role not in member.roles
        if added_role:
            try:
                await member.add_roles(
                    role,
                    reason=f"Associação de cargo Boost pelo desenvolvedor {interaction.user}",
                )
            except discord.Forbidden:
                return await interaction.response.send_message(
                    "Não tenho permissão para atribuir esse cargo.", ephemeral=True
                )
            except discord.HTTPException as error:
                return await interaction.response.send_message(
                    f"O Discord não aceitou a atribuição do cargo: {error}",
                    ephemeral=True,
                )

        if self.mode == "family":
            voice_channel_id = (
                previous_family.get("voice_channel_id")
                if previous_family is not None
                else None
            )
            boost.families[key] = {
                "role_id": role.id,
                "voice_channel_id": voice_channel_id,
            }
        else:
            boost.personal_roles[key] = role.id

        try:
            await boost.save()
        except Exception as error:
            if previous_family is None:
                boost.families.pop(key, None)
            else:
                boost.families[key] = previous_family
            if previous_personal is None:
                boost.personal_roles.pop(key, None)
            else:
                boost.personal_roles[key] = previous_personal
            if added_role:
                try:
                    await member.remove_roles(
                        role, reason="Falha ao registrar associação no NeonDB"
                    )
                except discord.HTTPException:
                    pass
            print(
                f"Falha ao registrar associação Boost: {type(error).__name__}: {error}",
                flush=True,
            )
            return await interaction.response.send_message(
                "Não consegui salvar a associação no NeonDB. Consulte os logs do bot.",
                ephemeral=True,
            )

        type_label = "família" if self.mode == "family" else "cargo personalizado"
        await interaction.response.edit_message(
            content=(
                f"Associação salva: {role.mention} foi registrado como {type_label} "
                f"de {member.mention}, e o cargo foi atribuído."
            ),
            view=None,
        )


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pool: Pool | None = None
        self._temporary_ban_lock = asyncio.Lock()

    async def cog_load(self) -> None:
        self.pool = await create_pool()
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS amie_moderation_warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                member_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS amie_ban_history (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                ban_count INTEGER NOT NULL DEFAULT 0,
                last_banned_at INTEGER NOT NULL,
                unban_at INTEGER,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )
    async def cog_unload(self) -> None:
        self.expire_temporary_bans.cancel()
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    @tasks.loop(seconds=30)
    async def expire_temporary_bans(self) -> None:
        if self.pool is None:
            return
        now = int(discord.utils.utcnow().timestamp())
        expired = await self.pool.fetch(
            "SELECT guild_id, user_id FROM amie_ban_history "
            "WHERE unban_at IS NOT NULL AND unban_at <= $1",
            now,
        )
        for row in expired:
            async with self._temporary_ban_lock:
                latest_unban_at = await self.pool.fetchval(
                    "SELECT unban_at FROM amie_ban_history "
                    "WHERE guild_id = $1 AND user_id = $2",
                    row["guild_id"],
                    row["user_id"],
                )
                if latest_unban_at is None or latest_unban_at > now:
                    continue
                guild = self.bot.get_guild(row["guild_id"])
                if guild is None:
                    continue
                try:
                    await guild.unban(
                        discord.Object(id=row["user_id"]),
                        reason="Fim do banimento temporário",
                    )
                except discord.NotFound:
                    await self.pool.execute(
                        "UPDATE amie_ban_history SET unban_at = NULL "
                        "WHERE guild_id = $1 AND user_id = $2",
                        row["guild_id"],
                        row["user_id"],
                    )
                except discord.Forbidden as error:
                    log.error(
                        "Sem permissão para retirar ban temporário do usuário %s no servidor %s: %s",
                        row["user_id"],
                        row["guild_id"],
                        error,
                    )
                except discord.HTTPException as error:
                    log.error(
                        "Falha ao retirar ban temporário do usuário %s no servidor %s: %s",
                        row["user_id"],
                        row["guild_id"],
                        error,
                    )
                else:
                    await self.pool.execute(
                        "UPDATE amie_ban_history SET unban_at = NULL "
                        "WHERE guild_id = $1 AND user_id = $2",
                        row["guild_id"],
                        row["user_id"],
                    )

    @expire_temporary_bans.before_loop
    async def before_expire_temporary_bans(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not self.expire_temporary_bans.is_running():
            self.expire_temporary_bans.start()

    def _can_act(self, actor: discord.Member, target: discord.Member, guild: discord.Guild) -> tuple[bool, str]:
        """Verifica se um membro pode agir em outro"""
        if target == actor:
            return False, "<:wrong:1554659471223947324> você não pode usar punições contra si mesmo"
        if target.top_role >= actor.top_role and guild.owner_id != actor.id:
            return False, "<:wrong:1554659471223947324> você não pode agir em alguém com cargo igual ou superior ao seu"
        bot_member = guild.me
        if bot_member is None:
            return False, "Não consegui verificar meu cargo neste servidor."
        if target.top_role >= bot_member.top_role:
            return False, "<:wrong:1554659471223947324> o bot não tem cargo suficiente para agir nesse membro"
        return True, ""

    def _parse_duration(self, duration: str) -> Optional[int]:
        """Converte durações como 30s, 10m, 2h e 7d em segundos."""
        normalized = duration.strip().lower()
        units = (
            ("sec", 1),
            ("min", 60),
            ("s", 1),
            ("m", 60),
            ("h", 3600),
            ("d", 86400),
        )
        for suffix, multiplier in units:
            if normalized.endswith(suffix):
                amount = normalized[: -len(suffix)]
                if amount.isdigit() and int(amount) > 0:
                    return int(amount) * multiplier
                return None
        return None

    def _moderation_pool(self) -> Pool:
        if self.pool is None:
            raise RuntimeError("O armazenamento de moderação ainda não está disponível.")
        return self.pool

    async def _record_warning(
        self,
        guild_id: int,
        member_id: int,
        moderator_id: int,
        reason: str,
    ) -> int:
        pool = self._moderation_pool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "INSERT INTO amie_moderation_warnings "
                    "(guild_id, member_id, moderator_id, reason, created_at) "
                    "VALUES ($1, $2, $3, $4, $5)",
                    guild_id,
                    member_id,
                    moderator_id,
                    reason,
                    int(discord.utils.utcnow().timestamp()),
                )
                warning_id = await connection.fetchval("SELECT last_insert_rowid()")
        if warning_id is None:
            raise RuntimeError("Não foi possível recuperar o ID da advertência criada.")
        return int(warning_id)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        if self.pool is None:
            return
        await self.pool.execute(
            """
            INSERT INTO amie_ban_history
                (guild_id, user_id, ban_count, last_banned_at)
            VALUES ($1, $2, 1, $3)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                ban_count = amie_ban_history.ban_count + 1,
                last_banned_at = excluded.last_banned_at
            """,
            guild.id,
            user.id,
            int(discord.utils.utcnow().timestamp()),
        )

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        if self.pool is None:
            return
        await self.pool.execute(
            "UPDATE amie_ban_history SET unban_at = NULL "
            "WHERE guild_id = $1 AND user_id = $2",
            guild.id,
            user.id,
        )

    async def _apply_warning_punishment(
        self,
        actor: discord.Member,
        member: discord.Member,
        guild: discord.Guild,
        reason: str,
    ) -> tuple[bool, str]:
        menu = self.bot.get_cog("Menu")
        punishment = (
            menu.get_value(guild.id, "warn_additional_punishment", "none")
            if menu
            else "none"
        )
        if punishment not in WARN_PUNISHMENT_CHOICES:
            return False, "A punição adicional configurada é inválida. Revise o /menu."
        if punishment == "none":
            return True, ""

        permission_by_punishment = {
            "timeout": ("moderate_members", "silenciar"),
            "kick": ("kick_members", "expulsar"),
            "ban": ("ban_members", "banir"),
        }
        permission, action_label = permission_by_punishment[punishment]
        if not getattr(actor.guild_permissions, permission):
            return (
                False,
                f"Você precisa da permissão para {action_label} membros para aplicar "
                "a punição adicional configurada.",
            )
        bot_member = guild.me
        if bot_member is None or not getattr(
            bot_member.guild_permissions, permission
        ):
            return (
                False,
                f"Não tenho permissão para {action_label} membros.",
            )

        if punishment == "timeout":
            try:
                duration_minutes = int(
                    menu.get_value(guild.id, "warn_timeout_minutes", 10)
                    if menu
                    else 10
                )
            except (TypeError, ValueError):
                return (
                    False,
                    "A duração do silenciamento está inválida. Configure de 1 "
                    "a 40320 minutos no /menu.",
                )
            if not 1 <= duration_minutes <= 40320:
                return (
                    False,
                    "A duração do silenciamento está inválida. Configure de 1 "
                    "a 40320 minutos no /menu.",
                )
            try:
                until = discord.utils.utcnow() + datetime.timedelta(
                    minutes=duration_minutes
                )
                await member.timeout(
                    until, reason=f"Advertência por {actor}: {reason}"
                )
                return True, f"Também foi silenciado por {duration_minutes} minutos."
            except (discord.Forbidden, discord.HTTPException) as error:
                return False, f"Não foi possível aplicar a punição adicional: {error}"

        try:
            if punishment == "kick":
                await member.kick(reason=f"Advertência por {actor}: {reason}")
                return True, "Também foi expulso."
            await member.ban(reason=f"Advertência por {actor}: {reason}")
            return True, "Também foi banido."
        except (discord.Forbidden, discord.HTTPException) as error:
            return False, f"Não foi possível aplicar a punição adicional: {error}"

    # ===== WARN COMMAND =====
    @commands.command(name="warn")
    @commands.has_permissions(manage_roles=True)
    async def warn_prefix(self, ctx: commands.Context, member: discord.Member, *, reason: str = "sem motivo informado"):
        """Avisa um membro (prefixo)"""
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return await ctx.send("Este comando só pode ser usado em um servidor.")
        allowed, message = self._can_act(ctx.author, member, ctx.guild)
        if not allowed:
            return await ctx.send(message)

        applied, punishment_message = await self._apply_warning_punishment(
            ctx.author, member, ctx.guild, reason
        )
        warning_id = await self._record_warning(
            ctx.guild.id, member.id, ctx.author.id, reason
        )
        embed = discord.Embed(
            title="⚠️ Aviso",
            description=f"{member.mention} recebeu uma advertência.",
            color=discord.Color.gold()
        )
        embed.add_field(name="motivo", value=reason, inline=False)
        embed.add_field(name="ID da advertência", value=str(warning_id), inline=False)
        if punishment_message:
            embed.add_field(
                name=(
                    "Punição adicional"
                    if applied
                    else "Punição adicional não aplicada"
                ),
                value=punishment_message,
                inline=False,
            )
        embed.set_footer(text=f"aviso por {ctx.author}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(view=components_v2(embed))

        try:
            await member.send(
                f"Você recebeu uma advertência em {ctx.guild.name}. "
                f"Motivo: {reason} "
                + (
                    punishment_message
                    if applied
                    else f"A punição adicional não foi aplicada: {punishment_message}"
                    if punishment_message
                    else ""
                )
            )
        except discord.Forbidden:
            pass

    @app_commands.command(name="warn", description="Avisa um membro")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_roles=True)
    async def warn_slash(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Sem motivo informado"):
        """Avisa um membro (slash)"""
        if interaction.guild is None or not isinstance(
            interaction.user, discord.Member
        ):
            return await interaction.response.send_message(
                "Este comando só pode ser usado em um servidor.", ephemeral=True
            )
        allowed, message = self._can_act(interaction.user, member, interaction.guild)
        if not allowed:
            return await interaction.response.send_message(message, ephemeral=True)

        applied, punishment_message = await self._apply_warning_punishment(
            interaction.user, member, interaction.guild, reason
        )
        warning_id = await self._record_warning(
            interaction.guild.id, member.id, interaction.user.id, reason
        )
        embed = discord.Embed(
            title="⚠️ Aviso",
            description=f"{member.mention} recebeu uma advertência.",
            color=discord.Color.gold()
        )
        embed.add_field(name="Motivo", value=reason, inline=False)
        embed.add_field(name="ID da advertência", value=str(warning_id), inline=False)
        if punishment_message:
            embed.add_field(
                name=(
                    "Punição adicional"
                    if applied
                    else "Punição adicional não aplicada"
                ),
                value=punishment_message,
                inline=False,
            )
        embed.set_footer(text=f"Aviso por {interaction.user}", icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(view=components_v2(embed))

        try:
            await member.send(
                f"Você recebeu uma advertência em {interaction.guild.name}. "
                f"Motivo: {reason} "
                + (
                    punishment_message
                    if applied
                    else f"A punição adicional não foi aplicada: {punishment_message}"
                    if punishment_message
                    else ""
                )
            )
        except discord.Forbidden:
            pass

    # ===== MUTE COMMAND =====
    @commands.command(name="mute")
    @commands.has_permissions(moderate_members=True)
    async def mute_prefix(self, ctx: commands.Context, member: discord.Member, duration: str, *, reason: str = "Sem motivo informado"):
        """Muta um membro (prefixo)"""
        allowed, message = self._can_act(ctx.author, member, ctx.guild)
        if not allowed:
            return await ctx.send(message)

        seconds = self._parse_duration(duration)
        if seconds is None:
            return await ctx.send("use uma duração válida, por exemplo: `10min`, `1h`, `30sec`")

        until = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)
        try:
            await member.timeout(until, reason=reason)
        except Exception as exc:
            return await ctx.send(f"não foi possível mutar: {exc}")

        await ctx.send(f"{member.mention} foi mutado por {duration}, motivo: {reason}")

    @app_commands.command(name="mute", description="Muta um membro")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def mute_slash(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "Sem motivo informado"):
        """Muta um membro (slash)"""
        allowed, message = self._can_act(interaction.user, member, interaction.guild)
        if not allowed:
            return await interaction.response.send_message(message, ephemeral=True)

        seconds = self._parse_duration(duration)
        if seconds is None:
            return await interaction.response.send_message("use uma duração válida, por exemplo: `10min`, `1h`, `30sec`.", ephemeral=True)

        until = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)
        try:
            await member.timeout(until, reason=reason)
        except Exception as exc:
            return await interaction.response.send_message(f"não foi possível mutar: {exc}", ephemeral=True)

        await interaction.response.send_message(f"{member.mention} foi mutado por {duration}, motivo: {reason}")

    # ===== KICK COMMAND =====
    @commands.command(name="kick")
    @commands.has_permissions(kick_members=True)
    async def kick_prefix(self, ctx: commands.Context, member: discord.Member, *, reason: str = "sem motivo informado"):
        """Expulsa um membro (prefixo)"""
        allowed, message = self._can_act(ctx.author, member, ctx.guild)
        if not allowed:
            return await ctx.send(message)

        try:
            await member.kick(reason=reason)
        except Exception as exc:
            return await ctx.send(f"não foi possível expulsar: {exc}")

        await ctx.send(f"{member.mention} foi expulso, motivo: {reason}")

    @app_commands.command(name="kick", description="Expulsa um membro")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick_slash(self, interaction: discord.Interaction, member: discord.Member, reason: str = "sem motivo informado"):
        """Expulsa um membro (slash)"""
        allowed, message = self._can_act(interaction.user, member, interaction.guild)
        if not allowed:
            return await interaction.response.send_message(message, ephemeral=True)

        try:
            await member.kick(reason=reason)
        except Exception as exc:
            return await interaction.response.send_message(f"não foi possível expulsar: {exc}", ephemeral=True)

        await interaction.response.send_message(f"{member.mention} foi expulso, motivo: {reason}")

    # ===== BAN COMMAND =====
    @commands.command(name="ban")
    @commands.has_permissions(ban_members=True)
    async def ban_prefix(self, ctx: commands.Context, member: discord.Member, *, reason: str = "sem motivo informado"):
        """Bane um membro (prefixo)"""
        allowed, message = self._can_act(ctx.author, member, ctx.guild)
        if not allowed:
            return await ctx.send(message)

        try:
            await member.ban(reason=reason)
        except Exception as exc:
            return await ctx.send(f"não foi possível banir: {exc}")

        await ctx.send(f"{member.mention} foi banido, motivo: {reason}")

    @app_commands.command(name="ban", description="Bane um membro")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban_slash(self, interaction: discord.Interaction, member: discord.Member, reason: str = "sem motivo informado"):
        """Bane um membro (slash)"""
        allowed, message = self._can_act(interaction.user, member, interaction.guild)
        if not allowed:
            return await interaction.response.send_message(message, ephemeral=True)

        try:
            await member.ban(reason=reason)
        except Exception as exc:
            return await interaction.response.send_message(f"mão foi possível banir: {exc}", ephemeral=True)

        await interaction.response.send_message(f"{member.mention} foi banido, motivo: {reason}")

    @commands.hybrid_command(name="addcargo", description="Adiciona um cargo a um membro")
    @commands.has_permissions(manage_roles=True)
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.guild_only()
    async def addcargo(
        self,
        ctx: commands.Context,
        member: discord.Member,
        role: discord.Role,
    ) -> None:
        guild = ctx.guild
        if guild is None or not isinstance(ctx.author, discord.Member):
            return await ctx.send("Este comando só pode ser usado em um servidor.")
        if role.is_default() or role.managed:
            return await ctx.send("Não é possível atribuir esse cargo.")
        if guild.owner_id != ctx.author.id and role >= ctx.author.top_role:
            return await ctx.send("Seu cargo precisa estar acima do cargo selecionado.")
        bot_member = guild.me
        if bot_member is None or role >= bot_member.top_role:
            return await ctx.send("Meu cargo precisa estar acima do cargo selecionado.")
        if role in member.roles:
            return await ctx.send(f"{member.mention} já possui {role.mention}.")
        try:
            await member.add_roles(role, reason=f"Cargo adicionado por {ctx.author}")
        except discord.Forbidden:
            return await ctx.send("Não tenho permissão para atribuir esse cargo.")
        except discord.HTTPException as error:
            log.warning("Falha ao atribuir cargo %s a %s: %s", role.id, member.id, error)
            return await ctx.send(f"Não foi possível atribuir o cargo: {error}")
        await ctx.send(
            view=components_v2(
                discord.Embed(
                    title="Cargo adicionado",
                    description=f"{role.mention} foi atribuído a {member.mention}.",
                    color=discord.Color.green(),
                )
            )
        )

    @commands.hybrid_command(name="addemoji", description="Adiciona um emoji ao servidor")
    @commands.has_permissions(manage_emojis_and_stickers=True)
    @app_commands.checks.has_permissions(manage_emojis_and_stickers=True)
    @app_commands.guild_only()
    @app_commands.describe(attachment="Imagem/GIF anexado ao comando", name="Nome inicial do emoji")
    async def addemoji(
        self,
        ctx: commands.Context,
        attachment: discord.Attachment,
        name: str | None = None,
    ) -> None:
        guild = ctx.guild
        if guild is None:
            return await ctx.send("Este comando só pode ser usado em um servidor.")
        if ctx.interaction is not None:
            return await ctx.interaction.response.send_modal(
                AssetCreationModal(
                    guild,
                    attachment,
                    sticker=False,
                    initial_name=name,
                )
            )
        emoji_name = name or attachment.filename.rsplit(".", 1)[0]
        try:
            await guild.create_custom_emoji(
                name=emoji_name,
                image=await attachment.read(),
                reason=f"Criado por {ctx.author}",
            )
        except discord.Forbidden:
            return await ctx.send("O Discord negou a criação. Verifique a permissão do bot.")
        except discord.HTTPException as error:
            log.warning("Falha ao criar emoji no servidor %s: %s", guild.id, error)
            return await ctx.send(f"Não foi possível criar o emoji: {error}")
        await ctx.send(
            view=components_v2(
                discord.Embed(
                    title="Emoji criado",
                    description=f"`{emoji_name}` foi adicionado ao servidor.",
                    color=discord.Color.green(),
                )
            )
        )

    @commands.hybrid_command(name="addsticker", description="Adiciona um sticker ao servidor")
    @commands.has_permissions(manage_emojis_and_stickers=True)
    @app_commands.checks.has_permissions(manage_emojis_and_stickers=True)
    @app_commands.guild_only()
    @app_commands.describe(attachment="Imagem/GIF anexado ao comando", name="Nome inicial do sticker")
    async def addsticker(
        self,
        ctx: commands.Context,
        attachment: discord.Attachment,
        name: str | None = None,
    ) -> None:
        guild = ctx.guild
        if guild is None:
            return await ctx.send("Este comando só pode ser usado em um servidor.")
        if ctx.interaction is not None:
            return await ctx.interaction.response.send_modal(
                AssetCreationModal(
                    guild,
                    attachment,
                    sticker=True,
                    initial_name=name,
                )
            )
        sticker_name = name or attachment.filename.rsplit(".", 1)[0]
        sticker_file = discord.File(
            io.BytesIO(await attachment.read()),
            filename=attachment.filename,
        )
        try:
            try:
                await guild.create_sticker(
                    name=sticker_name,
                    description="Sticker do servidor",
                    emoji="🙂",
                    file=sticker_file,
                    reason=f"Criado por {ctx.author}",
                )
            except discord.Forbidden:
                return await ctx.send(
                    "O Discord negou a criação. Verifique a permissão do bot."
                )
            except discord.HTTPException as error:
                log.warning("Falha ao criar sticker no servidor %s: %s", guild.id, error)
                return await ctx.send(f"Não foi possível criar o sticker: {error}")
        finally:
            sticker_file.close()
        await ctx.send(
            view=components_v2(
                discord.Embed(
                    title="Sticker criado",
                    description=f"`{sticker_name}` foi adicionado ao servidor.",
                    color=discord.Color.green(),
                )
            )
        )

    @commands.hybrid_command(name="adv", description="Adverte um membro")
    @commands.has_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def adv(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "Sem motivo informado",
    ) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return await ctx.send("Este comando só pode ser usado em um servidor.")
        allowed, message = self._can_act(ctx.author, member, ctx.guild)
        if not allowed:
            return await ctx.send(message)
        warning_id = await self._record_warning(
            ctx.guild.id, member.id, ctx.author.id, reason
        )
        embed = discord.Embed(
            title="Advertência aplicada",
            description=f"{member.mention} recebeu uma advertência.",
            color=discord.Color.gold(),
        )
        embed.add_field(name="Motivo", value=reason, inline=False)
        embed.add_field(name="ID da advertência", value=str(warning_id), inline=False)
        await ctx.send(view=components_v2(embed))

    @commands.hybrid_command(name="advrm", description="Remove uma advertência de um membro")
    @commands.has_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def advrm(
        self,
        ctx: commands.Context,
        member: discord.Member,
        warning_id: int | None = None,
    ) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return await ctx.send("Este comando só pode ser usado em um servidor.")
        allowed, message = self._can_act(ctx.author, member, ctx.guild)
        if not allowed:
            return await ctx.send(message)
        pool = self._moderation_pool()
        if warning_id is None:
            warning = await pool.fetchrow(
                "SELECT id FROM amie_moderation_warnings "
                "WHERE guild_id = $1 AND member_id = $2 ORDER BY id DESC LIMIT 1",
                ctx.guild.id,
                member.id,
            )
        else:
            warning = await pool.fetchrow(
                "SELECT id FROM amie_moderation_warnings "
                "WHERE guild_id = $1 AND member_id = $2 AND id = $3",
                ctx.guild.id,
                member.id,
                warning_id,
            )
        if warning is None:
            return await ctx.send("Não encontrei advertências para remover.")
        await pool.execute(
            "DELETE FROM amie_moderation_warnings WHERE id = $1 AND guild_id = $2",
            warning["id"],
            ctx.guild.id,
        )
        await ctx.send(
            view=components_v2(
                discord.Embed(
                    title="Advertência removida",
                    description=(
                        f"A advertência `{warning['id']}` de {member.mention} foi removida."
                    ),
                    color=discord.Color.green(),
                )
            )
        )

    @commands.hybrid_command(name="bantempo", description="Bane um membro por tempo determinado")
    @commands.has_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.guild_only()
    @app_commands.describe(duration="Duração: 30s, 10m, 2h ou 7d")
    async def bantempo(
        self,
        ctx: commands.Context,
        member: discord.Member,
        duration: str,
        *,
        reason: str = "Sem motivo informado",
    ) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return await ctx.send("Este comando só pode ser usado em um servidor.")
        allowed, message = self._can_act(ctx.author, member, ctx.guild)
        if not allowed:
            return await ctx.send(message)
        seconds = self._parse_duration(duration)
        if seconds is None:
            return await ctx.send("Duração inválida. Use, por exemplo, `30s`, `10m`, `2h` ou `7d`.")
        now = discord.utils.utcnow()
        try:
            unban_at = now + datetime.timedelta(seconds=seconds)
        except OverflowError:
            return await ctx.send("A duração informada é longa demais.")
        async with self._temporary_ban_lock:
            await self._moderation_pool().execute(
                """
                INSERT INTO amie_ban_history
                    (guild_id, user_id, ban_count, last_banned_at, unban_at)
                VALUES ($1, $2, 0, $3, $4)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    unban_at = excluded.unban_at
                """,
                ctx.guild.id,
                member.id,
                int(now.timestamp()),
                int(unban_at.timestamp()),
            )
            try:
                await ctx.guild.ban(member, reason=reason)
            except discord.Forbidden:
                await self._moderation_pool().execute(
                    "UPDATE amie_ban_history SET unban_at = NULL "
                    "WHERE guild_id = $1 AND user_id = $2",
                    ctx.guild.id,
                    member.id,
                )
                return await ctx.send("Não tenho permissão para banir este membro.")
            except discord.HTTPException as error:
                await self._moderation_pool().execute(
                    "UPDATE amie_ban_history SET unban_at = NULL "
                    "WHERE guild_id = $1 AND user_id = $2",
                    ctx.guild.id,
                    member.id,
                )
                log.warning("Falha ao banir temporariamente %s: %s", member.id, error)
                return await ctx.send(f"Não foi possível aplicar o banimento: {error}")
        await ctx.send(
            view=components_v2(
                discord.Embed(
                    title="Banimento temporário aplicado",
                    description=f"{member.mention} será desbanido <t:{int(unban_at.timestamp())}:F>.",
                    color=discord.Color.orange(),
                ).add_field(name="Motivo", value=reason, inline=False)
            )
        )

    @commands.hybrid_command(name="infoban", description="Mostra informações do banimento de um usuário")
    @commands.has_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.guild_only()
    async def infoban(self, ctx: commands.Context, user: discord.User) -> None:
        guild = ctx.guild
        if guild is None:
            return await ctx.send("Este comando só pode ser usado em um servidor.")
        try:
            ban_entry = await guild.fetch_ban(user)
        except discord.NotFound:
            return await ctx.send(f"{user} não está banido neste servidor.")
        except discord.Forbidden:
            return await ctx.send("Não tenho permissão para consultar os banimentos.")
        except discord.HTTPException as error:
            log.warning("Falha ao consultar banimento de %s: %s", user.id, error)
            return await ctx.send(f"Não foi possível consultar o banimento: {error}")

        row = await self._moderation_pool().fetchrow(
            "SELECT ban_count, last_banned_at, unban_at FROM amie_ban_history "
            "WHERE guild_id = $1 AND user_id = $2",
            guild.id,
            user.id,
        )
        ban_time = (
            int(row["last_banned_at"])
            if row is not None
            else int(discord.utils.utcnow().timestamp())
        )
        ban_count = int(row["ban_count"]) if row is not None else 0
        audit_available = True
        audit_count = 0
        try:
            async for entry in guild.audit_logs(
                limit=1000, action=discord.AuditLogAction.ban
            ):
                if getattr(entry.target, "id", None) == user.id:
                    if audit_count == 0:
                        ban_time = int(entry.created_at.timestamp())
                    audit_count += 1
        except discord.Forbidden:
            audit_available = False
        ban_count = max(ban_count, audit_count)

        description = (
            f"**Usuário:** {user.mention} (`{user.id}`)\n"
            f"**Banido em:** <t:{ban_time}:F>\n"
            f"**Banimentos registrados:** {ban_count or 'Sem histórico local'}"
        )
        if row is not None and row["unban_at"] is not None:
            description += f"\n**Desbanimento previsto:** <t:{row['unban_at']}:F>"
        elif row is not None and row["unban_at"] is None:
            description += "\n**Duração:** Permanente"
        if not audit_available:
            description += "\n-# Não tenho acesso ao registro de auditoria do servidor."
        embed = discord.Embed(
            title="Informações do banimento",
            description=description,
            color=discord.Color.red(),
        )
        if ban_entry.reason:
            embed.add_field(name="Motivo", value=ban_entry.reason, inline=False)
        await ctx.send(view=components_v2(embed))

    @commands.hybrid_command(name="unban", description="Remove o banimento de um usuário")
    @commands.has_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.guild_only()
    async def unban(
        self,
        ctx: commands.Context,
        user: discord.User,
        *,
        reason: str = "Sem motivo informado",
    ) -> None:
        if ctx.guild is None:
            return await ctx.send("Este comando só pode ser usado em um servidor.")
        try:
            await ctx.guild.unban(user, reason=reason)
        except discord.NotFound:
            return await ctx.send(f"{user} não está banido neste servidor.")
        except discord.Forbidden:
            return await ctx.send("Não tenho permissão para remover banimentos.")
        except discord.HTTPException as error:
            log.warning("Falha ao desbanir %s: %s", user.id, error)
            return await ctx.send(f"Não foi possível remover o banimento: {error}")
        await self._moderation_pool().execute(
            "UPDATE amie_ban_history SET unban_at = NULL "
            "WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id,
            user.id,
        )
        await ctx.send(
            view=components_v2(
                discord.Embed(
                    title="Usuário desbanido",
                    description=f"{user.mention} foi desbanido.",
                    color=discord.Color.green(),
                )
            )
        )

    @commands.hybrid_command(name="lock", description="Bloqueia mensagens de @everyone neste canal")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def lock(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        channel = ctx.channel
        if guild is None or not isinstance(channel, discord.TextChannel):
            return await ctx.send("Use este comando em um canal de texto do servidor.")
        overwrite = channel.overwrites_for(guild.default_role)
        overwrite.send_messages = False
        try:
            await channel.set_permissions(
                guild.default_role,
                overwrite=overwrite,
                reason=f"Canal bloqueado por {ctx.author}",
            )
        except discord.Forbidden:
            return await ctx.send("Não tenho permissão para alterar este canal.")
        except discord.HTTPException as error:
            log.warning("Falha ao bloquear canal %s: %s", channel.id, error)
            return await ctx.send(f"Não foi possível bloquear o canal: {error}")
        await ctx.send(
            view=components_v2(
                discord.Embed(
                    title="Canal bloqueado",
                    description=f"@everyone não pode mais enviar mensagens em {channel.mention}.",
                    color=discord.Color.orange(),
                )
            )
        )

    @commands.hybrid_command(name="unlock", description="Libera mensagens de @everyone neste canal")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def unlock(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        channel = ctx.channel
        if guild is None or not isinstance(channel, discord.TextChannel):
            return await ctx.send("Use este comando em um canal de texto do servidor.")
        overwrite = channel.overwrites_for(guild.default_role)
        overwrite.send_messages = True
        try:
            await channel.set_permissions(
                guild.default_role,
                overwrite=overwrite,
                reason=f"Canal liberado por {ctx.author}",
            )
        except discord.Forbidden:
            return await ctx.send("Não tenho permissão para alterar este canal.")
        except discord.HTTPException as error:
            log.warning("Falha ao liberar canal %s: %s", channel.id, error)
            return await ctx.send(f"Não foi possível liberar o canal: {error}")
        await ctx.send(
            view=components_v2(
                discord.Embed(
                    title="Canal liberado",
                    description=f"@everyone pode enviar mensagens em {channel.mention}.",
                    color=discord.Color.green(),
                )
            )
        )

    @commands.hybrid_command(name="mutecall", description="Silencia um membro na chamada de voz")
    @commands.has_permissions(mute_members=True)
    @app_commands.checks.has_permissions(mute_members=True)
    @app_commands.guild_only()
    async def mutecall(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "Sem motivo informado",
    ) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return await ctx.send("Este comando só pode ser usado em um servidor.")
        allowed, message = self._can_act(ctx.author, member, ctx.guild)
        if not allowed:
            return await ctx.send(message)
        if member.voice is None or member.voice.channel is None:
            return await ctx.send("Este membro não está em uma chamada de voz.")
        try:
            await member.edit(mute=True, reason=reason)
        except discord.Forbidden:
            return await ctx.send("Não tenho permissão para silenciar este membro na chamada.")
        except discord.HTTPException as error:
            log.warning("Falha ao silenciar em chamada %s: %s", member.id, error)
            return await ctx.send(f"Não foi possível silenciar o membro: {error}")
        await ctx.send(
            view=components_v2(
                discord.Embed(
                    title="Membro silenciado na chamada",
                    description=f"{member.mention} foi silenciado em {member.voice.channel.mention}.",
                    color=discord.Color.orange(),
                )
            )
        )

    @commands.hybrid_command(name="unmute", description="Remove o silêncio de um membro na chamada")
    @commands.has_permissions(mute_members=True)
    @app_commands.checks.has_permissions(mute_members=True)
    @app_commands.guild_only()
    async def unmute(self, ctx: commands.Context, member: discord.Member) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return await ctx.send("Este comando só pode ser usado em um servidor.")
        allowed, message = self._can_act(ctx.author, member, ctx.guild)
        if not allowed:
            return await ctx.send(message)
        if member.voice is None or member.voice.channel is None:
            return await ctx.send("Este membro não está em uma chamada de voz.")
        try:
            await member.edit(mute=False, reason=f"Silêncio removido por {ctx.author}")
        except discord.Forbidden:
            return await ctx.send("Não tenho permissão para remover o silêncio deste membro.")
        except discord.HTTPException as error:
            log.warning("Falha ao remover silêncio em chamada %s: %s", member.id, error)
            return await ctx.send(f"Não foi possível remover o silêncio: {error}")
        await ctx.send(
            view=components_v2(
                discord.Embed(
                    title="Silêncio removido",
                    description=f"{member.mention} pode falar novamente na chamada.",
                    color=discord.Color.green(),
                )
            )
        )

    @commands.hybrid_command(name="nukechat", description="Recria o canal após confirmação")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def nukechat(self, ctx: commands.Context) -> None:
        if not isinstance(ctx.channel, discord.TextChannel):
            return await ctx.send("Use este comando em um canal de texto.")
        await ctx.send(
            "Isso clonará o canal e excluirá o atual. A ação não pode ser desfeita. Confirmar?",
            view=NukeChannelView(ctx.channel, ctx.author.id),
        )


async def setup(bot):
    await bot.add_cog(Admin(bot))