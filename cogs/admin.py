import datetime
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands

from .components_v2 import components_v2

from .menu import DEVELOPER_ID, WARN_PUNISHMENT_CHOICES


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
                "O cog boost está sem conexão com o banco de dados.", ephemeral=True
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
                        role, reason="Falha ao registrar associação no banco de dados"
                    )
                except discord.HTTPException:
                    pass
            print(
                f"Falha ao registrar associação Boost: {type(error).__name__}: {error}",
                flush=True,
            )
            return await interaction.response.send_message(
                "Não consegui salvar a associação no banco de dados. Consulte os logs do bot.",
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

    def _can_act(self, actor: discord.Member, target: discord.Member, guild: discord.Guild) -> tuple[bool, str]:
        """Verifica se um membro pode agir em outro"""
        if target == actor:
            return False, "<:wrong:1554659471223947324> você não pode usar punições contra si mesmo"
        if target.top_role >= actor.top_role and guild.owner_id != actor.id:
            return False, "<:wrong:1554659471223947324> você não pode agir em alguém com cargo igual ou superior ao seu"
        if target.top_role >= guild.me.top_role:
            return False, "<:wrong:1554659471223947324> o bot não tem cargo suficiente para agir nesse membro"
        return True, ""

    def _parse_duration(self, duration: str) -> Optional[int]:
        """Converte duração em segundos (ex: 10m, 1h, 30s)"""
        multipliers = {"sec": 1, "min": 60, "h": 3600, "d": 86400}
        try:
            amount = duration[:-1]
            unit = duration[-1:].lower()
            if not amount.isdigit() or unit not in multipliers:
                return None
            return int(amount) * multipliers[unit]
        except:
            return None

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
        embed = discord.Embed(
            title="⚠️ Aviso",
            description=f"{member.mention} recebeu uma advertência.",
            color=discord.Color.gold()
        )
        embed.add_field(name="motivo", value=reason, inline=False)
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
        embed = discord.Embed(
            title="⚠️ Aviso",
            description=f"{member.mention} recebeu uma advertência.",
            color=discord.Color.gold()
        )
        embed.add_field(name="Motivo", value=reason, inline=False)
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

async def setup(bot):
    await bot.add_cog(Admin(bot))