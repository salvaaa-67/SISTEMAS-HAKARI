import asyncio
from io import BytesIO
import json
import os
import re
from pathlib import Path

import aiohttp
import discord
from PIL import Image, UnidentifiedImageError
from discord.ext import commands

from .components_v2 import ComponentsV2View, components_v2
from .database import Pool, create_pool


MANAGED_ROLE_PREFIXES = ("família -", "cargo -")


class RoleEditModal(discord.ui.Modal):
    def __init__(
        self,
        cog,
        owner_id: int,
        role_id: int,
        family: bool,
        guild: discord.Guild,
    ):
        self.cog = cog
        self.owner_id = owner_id
        self.role_id = role_id
        self.family = family
        self.has_gradient_colors = cog.has_gradient_colors(guild)
        role_name = "Editar cargo da família" if family else "Editar seu cargo"
        super().__init__(
            title=role_name,
            custom_id=f"boost:edit:{owner_id}:{role_id}",
        )

        current_role = guild.get_role(role_id)
        current_name = current_role.name if current_role else ""
        current_color = (
            f"#{current_role.color.value:06X}" if current_role else "#000000"
        )
        current_secondary_color = (
            f"#{current_role.secondary_color.value:06X}"
            if current_role
            and current_role.secondary_color
            and self.has_gradient_colors
            else current_color
        )

        self.name_input = discord.ui.TextInput(
            label="Nome do cargo",
            placeholder="Digite o nome do cargo",
            default=current_name,
            max_length=100,
            required=True,
        )
        self.primary_color_input = discord.ui.TextInput(
            label=(
                "Primeira cor do gradiente"
                if self.has_gradient_colors
                else "Cor do cargo"
            ),
            placeholder="#000000 ou 000000",
            default=current_color,
            min_length=6,
            max_length=7,
            required=True,
        )
        self.secondary_color_input: discord.ui.TextInput | None = None
        self.add_item(self.name_input)
        self.add_item(self.primary_color_input)
        if self.has_gradient_colors:
            self.secondary_color_input = discord.ui.TextInput(
                label="Segunda cor do gradiente",
                placeholder="#FFFFFF ou FFFFFF",
                default=current_secondary_color,
                min_length=6,
                max_length=7,
                required=True,
            )
            self.add_item(self.secondary_color_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message(
                "<:wrong:1554659471223947324> Esse formulário pertence a outra pessoa.", ephemeral=True
            )
        can_edit = (
            self.cog.can_manage_family(interaction.user)
            if self.family
            else self.cog.can_manage_personal_role(interaction.user)
        )
        if not can_edit:
            return await interaction.response.send_message(
                "<:wrong:1554659471223947324> Você não tem mais permissão para editar este cargo.", ephemeral=True
            )
        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message(
                "<:wrong:1554659471223947324> Este formulário só pode ser usado no servidor.",
                ephemeral=True,
            )

        color_texts = [self.primary_color_input.value.strip()]
        if self.secondary_color_input is not None:
            color_texts.append(self.secondary_color_input.value.strip())
        if any(
            not re.fullmatch(r"#?[0-9a-fA-F]{6}", color_text)
            for color_text in color_texts
        ):
            if self.has_gradient_colors:
                color_error = (
                    "Informe duas cores hexadecimais válidas, como "
                    "`000000` e `#FFFFFF`."
                )
            else:
                color_error = (
                    "Informe uma cor hexadecimal válida, como `000000`."
                )
            return await interaction.response.send_message(
                f"<:wrong:1554659471223947324> {color_error}",
                ephemeral=True,
            )
        role_name = self.name_input.value.strip()
        if not role_name:
            return await interaction.response.send_message(
                "<:wrong:1554659471223947324> O nome do cargo não pode ficar vazio.", ephemeral=True
            )

        role = guild.get_role(self.role_id)
        if role is None:
            return await interaction.response.send_message(
                "<:wrong:1554659471223947324> Não encontrei esse cargo no servidor.", ephemeral=True
            )

        bot_member = guild.me
        if bot_member is None or not bot_member.guild_permissions.manage_roles:
            return await interaction.response.send_message(
                "<:wrong:1554659471223947324> Preciso da permissão **Gerenciar cargos** para editar este cargo.",
                ephemeral=True,
            )
        if role.managed:
            return await interaction.response.send_message(
                "<:wrong:1554659471223947324> Este cargo é gerenciado pelo Discord ou por uma integração e não pode ser editado pelo bot.",
                ephemeral=True,
            )
        if role >= bot_member.top_role:
            return await interaction.response.send_message(
                "<:wrong:1554659471223947324> O cargo mais alto do bot precisa ficar acima do cargo personalizado.",
                ephemeral=True,
            )

        primary_color = discord.Color(int(color_texts[0].removeprefix("#"), 16))
        reason = f"Personalização solicitada por {interaction.user}"
        try:
            if (
                self.secondary_color_input is not None
                and self.cog.has_gradient_colors(guild)
            ):
                role = await role.edit(
                    name=role_name,
                    color=primary_color,
                    secondary_color=discord.Color(
                        int(
                            self.secondary_color_input.value.strip().removeprefix("#"),
                            16,
                        )
                    ),
                    tertiary_color=None,
                    reason=reason,
                )
            else:
                role = await role.edit(
                    name=role_name,
                    color=primary_color,
                    reason=reason,
                )
        except discord.Forbidden as error:
            print(
                f"Discord negou a edição do cargo {role.id} no servidor "
                f"{guild.id}; bot_top_role={bot_member.top_role.id}, "
                f"manage_roles={bot_member.guild_permissions.manage_roles}, "
                f"code={error.code}: {error}",
                flush=True,
            )
            return await interaction.response.send_message(
                "<:wrong:1554659471223947324> O Discord negou a edição do cargo. "
                "Verifique a permissão **Gerenciar cargos**, a posição do cargo do bot "
                "e se o cargo personalizado não é gerenciado.",
                ephemeral=True,
            )
        except discord.HTTPException:
            return await interaction.response.send_message(
                "<:wrong:1554659471223947324> O Discord não conseguiu atualizar o cargo. Tente novamente.",
                ephemeral=True,
            )

        await interaction.response.send_message(
            f"<:correct:1554659481512841267> Cargo atualizado para **{role.name}**.", ephemeral=True
        )


class FamilyMemberSelect(discord.ui.UserSelect):
    def __init__(self, cog, owner_id: int, adding: bool, member_limit: int):
        self.cog = cog
        self.owner_id = owner_id
        self.adding = adding
        self.member_limit = member_limit
        super().__init__(
            placeholder=(
                "Escolha quem adicionar"
                if adding
                else "Escolha quem remover"
            ),
            min_values=1,
            max_values=member_limit,
            custom_id=f"boost:members:{owner_id}:{'add' if adding else 'remove'}",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message(
                "<:wrong:1554659471223947324> Esse painel pertence a outra pessoa.", ephemeral=True
            )
        if not self.cog.can_manage_family(interaction.user):
            return await interaction.response.send_message(
                "<:wrong:1554659471223947324> Gerenciar a família requer VIP maior ou boost.", ephemeral=True
            )

        state = self.cog.families.get(self.cog.key(interaction.guild_id, self.owner_id))
        role = interaction.guild.get_role(state["role_id"]) if state else None
        if role is None:
            return await interaction.response.send_message(
                "<:wrong:1554659471223947324> A família não está configurada. Use `,familia` para abrir o painel.",
                ephemeral=True,
            )

        chosen_members = [
            member
            for member in self.values
            if isinstance(member, discord.Member) and not member.bot
        ]
        current_members = set(role.members)

        if self.adding:
            new_members = [member for member in chosen_members if member not in current_members]
            if len(current_members) + len(new_members) > self.member_limit:
                return await interaction.response.send_message(
                    f"<:wrong:1554659471223947324> A família pode ter no máximo {self.member_limit} pessoas, contando você.",
                    ephemeral=True,
                )
            try:
                for member in new_members:
                    await member.add_roles(role, reason=f"Adicionado à família de {self.owner_id}")
            except discord.Forbidden:
                return await interaction.response.send_message(
                    "<:wrong:1554659471223947324> Não consegui adicionar os membros. Verifique a hierarquia e as permissões do bot.",
                    ephemeral=True,
                )
            verb = "adicionado(s)"
        else:
            removable = [
                member
                for member in chosen_members
                if member in current_members and member.id != self.owner_id
            ]
            try:
                for member in removable:
                    await member.remove_roles(
                        role, reason=f"Removido da família de {self.owner_id}"
                    )
            except discord.Forbidden:
                return await interaction.response.send_message(
                    "<:wrong:1554659471223947324> Não consegui remover os membros. Verifique a hierarquia e as permissões do bot.",
                    ephemeral=True,
                )
            verb = "removido(s)"

        changed_members = new_members if self.adding else removable
        if chosen_members and not changed_members:
            return await interaction.response.send_message(
                "<:wrong:1554659471223947324> Nenhum membro precisou ser alterado.", ephemeral=True
            )
        await interaction.response.send_message(
            f"<:correct:1554659481512841267> {len(changed_members)} membro(s) {verb}.", ephemeral=True
        )


class Boost(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.storage_path = Path(__file__).resolve().parent.parent / "data" / "boost.json"
        self.families: dict[str, dict] = {}
        self.personal_roles: dict[str, int] = {}
        self.role_icons: dict[str, str] = {}
        self.pending_icon_edits: dict[str, dict] = {}
        self.pool: Pool | None = None

    async def cog_load(self) -> None:
        if self.storage_path.exists():
            try:
                data = json.loads(self.storage_path.read_text(encoding="utf-8"))
                self.families = data.get("families", {})
                self.personal_roles = data.get("personal_roles", {})
            except (OSError, json.JSONDecodeError) as error:
                print(f"Não foi possível carregar os dados do boost: {error}")

        try:
            self.pool = await create_pool()
            await self.pool.execute(
                """
                CREATE TABLE IF NOT EXISTS boost_role_owners (
                    guild_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    family_role_id BIGINT,
                    personal_role_id BIGINT,
                    voice_channel_id BIGINT,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, user_id)
                )
                """
            )
            await self.pool.execute(
                """
                CREATE TABLE IF NOT EXISTS boost_role_icons (
                    guild_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    role_id BIGINT NOT NULL,
                    emoji TEXT NOT NULL,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, user_id, role_id)
                )
                """
            )
            await self.migrate_local_data()
            await self.load_database_data()
            await self.load_role_icons()
        except Exception as error:
            if self.pool is not None:
                await self.pool.close()
                self.pool = None
            print(
                "Não foi possível inicializar o SQLite no cog boost: "
                f"{type(error).__name__}: {error}"
            )
            return

        for key in self.families:
            guild_id, owner_id = map(int, key.split(":"))
            self.bot.add_view(
                self.family_view(guild_id, owner_id, include_icon=True)
            )
        for key in self.personal_roles:
            guild_id, owner_id = map(int, key.split(":"))
            self.bot.add_view(
                self.personal_view(guild_id, owner_id, include_icon=True)
            )

    async def cog_unload(self) -> None:
        if self.pool is not None:
            await self.pool.close()

    def save_local_data(self) -> None:
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.storage_path.with_suffix(".tmp")
            temporary_path.write_text(
                json.dumps(
                    {"families": self.families, "personal_roles": self.personal_roles},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            temporary_path.replace(self.storage_path)
        except OSError as error:
            print(f"Não foi possível atualizar o backup local do boost: {error}")

    async def migrate_local_data(self) -> None:
        if self.pool is None:
            return

        for key in self.families.keys() | self.personal_roles.keys():
            guild_id, owner_id = map(int, key.split(":"))
            family = self.families.get(key, {})
            await self.pool.execute(
                """
                INSERT INTO boost_role_owners (
                    guild_id, user_id, family_role_id, personal_role_id,
                    voice_channel_id
                )
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (guild_id, user_id) DO UPDATE SET
                    family_role_id = COALESCE(
                        boost_role_owners.family_role_id, EXCLUDED.family_role_id
                    ),
                    personal_role_id = COALESCE(
                        boost_role_owners.personal_role_id, EXCLUDED.personal_role_id
                    ),
                    voice_channel_id = COALESCE(
                        boost_role_owners.voice_channel_id, EXCLUDED.voice_channel_id
                    ),
                    updated_at = CURRENT_TIMESTAMP
                """,
                guild_id,
                owner_id,
                family.get("role_id"),
                self.personal_roles.get(key),
                family.get("voice_channel_id"),
            )

    async def load_database_data(self) -> None:
        if self.pool is None:
            return

        self.families.clear()
        self.personal_roles.clear()
        rows = await self.pool.fetch(
            """
            SELECT guild_id, user_id, family_role_id, personal_role_id,
                   voice_channel_id
            FROM boost_role_owners
            """
        )
        for row in rows:
            key = self.key(row["guild_id"], row["user_id"])
            if row["family_role_id"] is not None:
                self.families[key] = {
                    "role_id": row["family_role_id"],
                    "voice_channel_id": row["voice_channel_id"],
                }
            if row["personal_role_id"] is not None:
                self.personal_roles[key] = row["personal_role_id"]

    async def load_role_icons(self) -> None:
        if self.pool is None:
            return
        rows = await self.pool.fetch(
            """
            SELECT guild_id, user_id, role_id, emoji
            FROM boost_role_icons
            """
        )
        self.role_icons = {
            f"{row['guild_id']}:{row['user_id']}:{row['role_id']}": row["emoji"]
            for row in rows
        }

    async def store_role_icon(
        self, guild_id: int, user_id: int, role_id: int, emoji: str
    ) -> None:
        if self.pool is None:
            raise RuntimeError("O banco de dados não está conectado.")
        await self.pool.execute(
            """
            INSERT INTO boost_role_icons (guild_id, user_id, role_id, emoji)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, user_id, role_id) DO UPDATE SET
                emoji = EXCLUDED.emoji,
                updated_at = CURRENT_TIMESTAMP
            """,
            guild_id,
            user_id,
            role_id,
            emoji,
        )
        self.role_icons[f"{guild_id}:{user_id}:{role_id}"] = emoji

    def key(self, guild_id: int, owner_id: int) -> str:
        return f"{guild_id}:{owner_id}"

    def setting(self, guild_id: int, key: str, default=None):
        menu = self.bot.get_cog("Menu")
        return menu.get_value(guild_id, key, default) if menu else default

    def has_gradient_colors(self, guild: discord.Guild) -> bool:
        return guild.premium_tier >= 2

    def has_role_icons(self, guild: discord.Guild | None) -> bool:
        return guild is not None and guild.premium_tier >= 2

    def configured_role_id(self, guild: discord.Guild, key: str):
        value = self.setting(guild.id, key)
        return int(value) if value is not None else None

    def family_member_limit(self, guild_id: int) -> int:
        value = self.setting(guild_id, "family_member_limit", 15)
        return max(1, min(25, int(value)))

    def guild_id_for_role(self, role_id: int) -> int:
        for key, data in self.families.items():
            if data["role_id"] == role_id:
                return int(key.split(":")[0])
        for key, stored_role_id in self.personal_roles.items():
            if stored_role_id == role_id:
                return int(key.split(":")[0])
        return 0

    def is_booster(self, member: discord.abc.User) -> bool:
        if not isinstance(member, discord.Member):
            return False
        return self.has_role(
            member, self.configured_role_id(member.guild, "booster_role")
        )

    def has_role(self, member: discord.abc.User, role_id: int | None) -> bool:
        return role_id is not None and isinstance(member, discord.Member) and any(
            role.id == role_id for role in member.roles
        )

    def can_manage_family(self, member: discord.abc.User) -> bool:
        if not isinstance(member, discord.Member):
            return False
        vip_full_role = self.configured_role_id(member.guild, "vip_full_role")
        vip_personal_role = self.configured_role_id(member.guild, "vip_personal_role")
        booster_role = self.configured_role_id(member.guild, "booster_role")
        return (
            self.has_role(member, vip_full_role)
            and vip_full_role != vip_personal_role
        ) or (
            self.has_role(member, booster_role)
            and booster_role != vip_personal_role
        )

    def can_manage_personal_role(self, member: discord.abc.User) -> bool:
        if not isinstance(member, discord.Member):
            return False
        vip_role = self.configured_role_id(member.guild, "vip_personal_role")
        saved_role_id = self.personal_roles.get(self.key(member.guild.id, member.id))
        has_saved_role = (
            saved_role_id is not None
            and member.guild.get_role(int(saved_role_id)) is not None
        )
        return (
            has_saved_role
            or self.can_manage_family(member)
            or self.has_role(member, vip_role)
        )

    def family_access_message(self, member: discord.abc.User) -> str:
        vip_role = (
            self.configured_role_id(member.guild, "vip_personal_role")
            if isinstance(member, discord.Member)
            else None
        )
        if self.has_role(member, vip_role):
            return (
                "<:wrong:1554659471223947324> Seu VIP atual permite apenas o cargo personalizado. "
                "Gerenciar família requer upgrade para VIP maior ou boost."
            )
        return "<:wrong:1554659471223947324> Gerenciar família requer VIP maior ou boost."

    async def save(self) -> None:
        if self.pool is None:
            raise RuntimeError("O banco de dados não está conectado.")

        records = []
        for key in self.families.keys() | self.personal_roles.keys():
            guild_id, owner_id = map(int, key.split(":"))
            family = self.families.get(key, {})
            records.append(
                (
                    guild_id,
                    owner_id,
                    family.get("role_id"),
                    self.personal_roles.get(key),
                    family.get("voice_channel_id"),
                )
            )

        if records:
            await self.pool.executemany(
                """
                INSERT INTO boost_role_owners (
                    guild_id, user_id, family_role_id, personal_role_id,
                    voice_channel_id
                )
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (guild_id, user_id) DO UPDATE SET
                    family_role_id = EXCLUDED.family_role_id,
                    personal_role_id = EXCLUDED.personal_role_id,
                    voice_channel_id = EXCLUDED.voice_channel_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                records,
            )

        self.save_local_data()

    async def repair_managed_roles(self, guild: discord.Guild) -> None:
        trigger_role_id = self.configured_role_id(guild, "repair_below_role")
        personal_lower_role_id = self.configured_role_id(guild, "role_position_lower")
        family_lower_role_id = self.configured_role_id(guild, "family_position_lower")
        upper_role_id = self.configured_role_id(guild, "role_position_upper")
        trigger_role = guild.get_role(trigger_role_id) if trigger_role_id else None
        personal_lower_role = guild.get_role(personal_lower_role_id) if personal_lower_role_id else None
        family_lower_role = guild.get_role(family_lower_role_id) if family_lower_role_id else None
        upper_role = guild.get_role(upper_role_id) if upper_role_id else None
        bot_member = guild.me
        if (
            trigger_role is None
            or personal_lower_role is None
            or family_lower_role is None
            or upper_role is None
        ):
            print(
                f"Não foi possível verificar cargos gerenciados em {guild.name}: "
                "cargo de referência não encontrado."
            )
            return
        if (
            personal_lower_role.position >= upper_role.position
            or family_lower_role.position >= upper_role.position
        ):
            print(
                f"Não foi possível mover cargos gerenciados em {guild.name}: "
                "os cargos de limite estão em ordem inválida."
            )
            return
        if bot_member is None or bot_member.top_role <= upper_role:
            print(
                f"Não foi possível mover cargos gerenciados em {guild.name}: "
                "o cargo do bot precisa estar acima do limite superior."
            )
            return

        family_role_ids = {
            state["role_id"]
            for key, state in self.families.items()
            if int(key.split(":")[0]) == guild.id
        }
        personal_role_ids = {
            role_id
            for key, role_id in self.personal_roles.items()
            if int(key.split(":")[0]) == guild.id
        }
        managed_roles = sorted(
            (
                role
                for role in guild.roles
                if role.id not in {
                    trigger_role_id,
                    personal_lower_role_id,
                    family_lower_role_id,
                    upper_role_id,
                }
                and (
                    role.id in family_role_ids
                    or role.id in personal_role_ids
                    or role.name.casefold().startswith(MANAGED_ROLE_PREFIXES)
                )
                and role.position < trigger_role.position
            ),
            key=lambda role: role.position,
            reverse=True,
        )

        for role in managed_roles:
            if role >= bot_member.top_role:
                print(
                    f"Não foi possível mover o cargo {role.name!r} em {guild.name}: "
                    "ele está acima ou no mesmo nível do bot."
                )
                continue

            is_family_role = (
                role.id in family_role_ids
                or role.name.casefold().startswith(("família -", "familia -"))
            )
            lower_role_id = (
                family_lower_role_id
                if is_family_role
                else personal_lower_role_id
            )
            lower_role = guild.get_role(lower_role_id)
            if lower_role is None:
                break
            target_position = lower_role.position + 1
            if role.position == target_position:
                continue

            try:
                await role.edit(
                    position=target_position,
                    reason="Corrigindo a posição de um cargo de booster",
                )
            except discord.Forbidden:
                print(
                    f"Sem permissão para mover o cargo {role.name!r} em {guild.name}."
                )
            except discord.HTTPException as error:
                print(
                    f"Falha ao mover o cargo {role.name!r} em {guild.name}: {error}"
                )

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        for guild in self.bot.guilds:
            await self.repair_managed_roles(guild)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        guild_id = role.guild.id
        guild_key_prefix = f"{guild_id}:"

        for key, family in list(self.families.items()):
            if key.startswith(guild_key_prefix) and family.get("role_id") == role.id:
                self.families.pop(key, None)

        for key, role_id in list(self.personal_roles.items()):
            if key.startswith(guild_key_prefix) and role_id == role.id:
                self.personal_roles.pop(key, None)

        for key in list(self.role_icons):
            parts = key.split(":")
            if (
                len(parts) == 3
                and parts[0] == str(guild_id)
                and parts[2] == str(role.id)
            ):
                self.role_icons.pop(key, None)

        for key, pending in list(self.pending_icon_edits.items()):
            if key.startswith(guild_key_prefix) and pending.get("role_id") == role.id:
                self.pending_icon_edits.pop(key, None)

        self.save_local_data()

        if self.pool is None:
            print(
                f"Cargo excluído {role.id} em {guild_id}, mas não foi possível limpar o banco de dados: pool indisponível."
            )
            return

        try:
            async with self.pool.acquire() as connection:
                async with connection.transaction():
                    await connection.execute(
                        """
                        UPDATE boost_role_owners
                        SET family_role_id = CASE
                                WHEN family_role_id = $2 THEN NULL
                                ELSE family_role_id
                            END,
                            personal_role_id = CASE
                                WHEN personal_role_id = $2 THEN NULL
                                ELSE personal_role_id
                            END,
                            voice_channel_id = CASE
                                WHEN family_role_id = $2 THEN NULL
                                ELSE voice_channel_id
                            END,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE guild_id = $1
                          AND (family_role_id = $2 OR personal_role_id = $2)
                        """,
                        guild_id,
                        role.id,
                    )
                    await connection.execute(
                        """
                        DELETE FROM boost_role_owners
                        WHERE guild_id = $1
                          AND family_role_id IS NULL
                          AND personal_role_id IS NULL
                        """,
                        guild_id,
                    )
                    await connection.execute(
                        """
                        DELETE FROM boost_role_icons
                        WHERE guild_id = $1 AND role_id = $2
                        """,
                        guild_id,
                        role.id,
                    )
                    backup_table_exists = await connection.fetchval(
                        "SELECT EXISTS (SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'temporary_role_backups')"
                    )
                    if backup_table_exists:
                        await connection.execute(
                            """
                            DELETE FROM temporary_role_backups
                            WHERE guild_id = $1 AND role_id = $2
                            """,
                            guild_id,
                            role.id,
                        )
        except Exception as error:
            print(
                f"Não foi possível limpar o cargo excluído {role.id} do banco de dados: "
                f"{type(error).__name__}: {error}",
                flush=True,
            )

    async def create_managed_role(
        self, guild: discord.Guild, member: discord.Member, name_prefix: str
    ) -> discord.Role:
        lower_role_id = (
            self.configured_role_id(guild, "family_position_lower")
            if name_prefix.casefold() in {"família", "familia"}
            else self.configured_role_id(guild, "role_position_lower")
        )
        lower_role = guild.get_role(lower_role_id)
        upper_role_id = self.configured_role_id(guild, "role_position_upper")
        upper_role = guild.get_role(upper_role_id) if upper_role_id else None
        bot_member = guild.me
        if lower_role is None or upper_role is None:
            raise ValueError("Não encontrei os cargos de referência configurados.")
        if lower_role.position >= upper_role.position:
            raise ValueError("Os cargos de referência estão em uma ordem inválida.")
        if bot_member is None or bot_member.top_role <= upper_role:
            raise ValueError(
                "Meu cargo precisa estar acima do cargo de referência superior."
            )

        role = await guild.create_role(
            name=f"{name_prefix} - {member.display_name}"[:100],
            reason=f"Cargo de booster criado para {member}",
        )
        try:
            await role.edit(
                position=lower_role.position + 1,
                reason="Posicionando o cargo de booster entre os cargos de referência",
            )
            await self.repair_managed_roles(guild)
        except Exception:
            await role.delete(reason="Não foi possível posicionar o cargo de booster")
            raise
        return role

    async def create_assigned_role(
        self,
        guild: discord.Guild,
        member: discord.Member,
        reason: str,
        name_prefix: str,
    ) -> discord.Role:
        role = await self.create_managed_role(guild, member, name_prefix)
        try:
            await member.add_roles(role, reason=reason)
        except Exception:
            try:
                await role.delete(reason="Não foi possível atribuir o cargo ao dono")
            except discord.HTTPException:
                pass
            raise
        return role

    def family_view(
        self,
        guild_id: int,
        owner_id: int,
        *,
        include_icon: bool | None = None,
    ) -> ComponentsV2View:
        view = ComponentsV2View(timeout=None)
        buttons = [
            ("Editar cargo", discord.ButtonStyle.primary, "edit"),
            ("Criar call", discord.ButtonStyle.success, "voice"),
            ("Adicionar membros", discord.ButtonStyle.secondary, "add"),
            ("Remover membros", discord.ButtonStyle.secondary, "remove"),
        ]
        guild = self.bot.get_guild(guild_id)
        if include_icon is None:
            include_icon = guild is None or self.has_role_icons(guild)
        if include_icon:
            buttons.insert(1, ("Editar ícone", discord.ButtonStyle.secondary, "icon"))
        for label, style, action in buttons:
            button = discord.ui.Button(
                label=label,
                style=style,
                custom_id=f"boost:family:{action}:{guild_id}:{owner_id}",
            )
            button.callback = self._family_callback(action, guild_id, owner_id)
            view.add_item(button)
        return view

    def personal_view(
        self,
        guild_id: int,
        owner_id: int,
        *,
        include_icon: bool | None = None,
    ) -> ComponentsV2View:
        view = ComponentsV2View(timeout=None)
        button = discord.ui.Button(
            label="Editar cargo",
            style=discord.ButtonStyle.primary,
            custom_id=f"boost:personal:edit:{guild_id}:{owner_id}",
        )
        button.callback = self._personal_edit_callback(guild_id, owner_id)
        view.add_item(button)
        guild = self.bot.get_guild(guild_id)
        if include_icon is None:
            include_icon = guild is None or self.has_role_icons(guild)
        if include_icon:
            icon_button = discord.ui.Button(
                label="Editar ícone",
                style=discord.ButtonStyle.secondary,
                custom_id=f"boost:personal:icon:{guild_id}:{owner_id}",
            )
            icon_button.callback = self._personal_icon_callback(guild_id, owner_id)
            view.add_item(icon_button)
        return view

    async def emoji_to_png(self, emoji_text: str) -> bytes:
        custom_emoji = re.fullmatch(
            r"<(?P<animated>a?):[A-Za-z0-9_]{2,32}:(?P<id>\d{15,22})>",
            emoji_text,
        )
        if custom_emoji:
            emoji_id = custom_emoji.group("id")
            extension = "gif" if custom_emoji.group("animated") else "png"
            url = (
                f"https://cdn.discordapp.com/emojis/{emoji_id}.{extension}?size=128"
            )
        else:
            if not emoji_text or len(emoji_text) > 16 or emoji_text.isspace():
                raise ValueError(
                    "Envie um único emoji Unicode ou emoji personalizado do Discord."
                )
            codepoints = "-".join(
                f"{ord(character):x}"
                for character in emoji_text
                if ord(character) not in {0xFE0E, 0xFE0F}
            )
            if not codepoints:
                raise ValueError("Não consegui identificar esse emoji.")
            url = (
                "https://cdn.jsdelivr.net/gh/jdecked/twemoji@latest/"
                f"assets/72x72/{codepoints}.png"
            )

        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status == 404:
                    raise ValueError("Não encontrei a imagem desse emoji.")
                if response.status != 200:
                    raise ValueError("Não consegui baixar a imagem desse emoji.")
                image_data = await response.read()

        if len(image_data) > 8 * 1024 * 1024:
            raise ValueError("A imagem do emoji é grande demais.")

        with Image.open(BytesIO(image_data)) as source:
            image = source.convert("RGBA")
            image.thumbnail((64, 64), Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format="PNG", optimize=True)
            return output.getvalue()

    async def start_icon_edit(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        family: bool,
    ) -> None:
        if not self.has_role_icons(interaction.guild):
            return await interaction.response.send_message(
                "<:wrong:1554659471223947324> Ícones de cargo estão disponíveis a partir do Nível 2 de Boost do servidor.",
                ephemeral=True,
            )

        if self.pool is None:
            return await interaction.response.send_message(
                "<:wrong:1554659471223947324> Não consegui conectar ao banco de dados para registrar o emoji.",
                ephemeral=True,
            )

        key = self.key(interaction.guild_id, interaction.user.id)
        expires_at = asyncio.get_running_loop().time() + 120
        self.pending_icon_edits[key] = {
            "role_id": role.id,
            "family": family,
            "channel_id": interaction.channel_id,
            "expires_at": expires_at,
            "processing": False,
            "interaction": interaction,
        }
        asyncio.create_task(self.expire_icon_edit(key, expires_at))
        await interaction.response.send_message(
            f"Agora envie neste canal o emoji que será usado no cargo **{role.name}**. "
            "A solicitação expira em 2 minutos.",
            ephemeral=True,
        )

    async def expire_icon_edit(self, key: str, expires_at: float) -> None:
        delay = max(0, expires_at - asyncio.get_running_loop().time())
        await asyncio.sleep(delay)
        pending = self.pending_icon_edits.get(key)
        if pending and pending["expires_at"] == expires_at:
            self.pending_icon_edits.pop(key, None)

    async def send_icon_feedback(self, pending: dict, content: str) -> None:
        try:
            await pending["interaction"].followup.send(content, ephemeral=True)
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return

        key = self.key(message.guild.id, message.author.id)
        pending = self.pending_icon_edits.get(key)
        if pending is None:
            return
        if asyncio.get_running_loop().time() >= pending["expires_at"]:
            self.pending_icon_edits.pop(key, None)
            return
        if message.channel.id != pending["channel_id"] or pending["processing"]:
            return
        can_edit = (
            self.can_manage_family(message.author)
            if pending["family"]
            else self.can_manage_personal_role(message.author)
        )
        if not can_edit:
            self.pending_icon_edits.pop(key, None)
            await self.send_icon_feedback(
                pending,
                self.family_access_message(message.author)
                if pending["family"]
                else "<:wrong:1554659471223947324> Você não tem mais permissão para editar o cargo pessoal.",
            )
            return

        if not self.has_role_icons(message.guild):
            self.pending_icon_edits.pop(key, None)
            await self.send_icon_feedback(
                pending,
                "<:wrong:1554659471223947324> Ícones de cargo estão disponíveis a partir do Nível 2 de Boost do servidor.",
            )
            return

        pending["processing"] = True
        try:
            icon_png = await self.emoji_to_png(message.content.strip())
        except ValueError as error:
            pending["processing"] = False
            await self.send_icon_feedback(
                pending, f"<:wrong:1554659471223947324> {error}"
            )
            return
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pending["processing"] = False
            await self.send_icon_feedback(
                pending, "<:wrong:1554659471223947324> Não consegui baixar a imagem do emoji. Tente novamente."
            )
            return
        except (UnidentifiedImageError, OSError):
            pending["processing"] = False
            await self.send_icon_feedback(
                pending, "<:wrong:1554659471223947324> A imagem do emoji não pôde ser convertida para PNG."
            )
            return

        role = message.guild.get_role(pending["role_id"])
        if role is None:
            self.pending_icon_edits.pop(key, None)
            return await self.send_icon_feedback(
                pending, "<:wrong:1554659471223947324> Não encontrei o cargo que você estava editando."
            )

        try:
            await role.edit(
                display_icon=icon_png,
                reason=f"Ícone personalizado solicitado por {message.author}",
            )
        except discord.Forbidden:
            pending["processing"] = False
            return await self.send_icon_feedback(
                pending,
                "<:wrong:1554659471223947324> Não tenho permissão para editar esse cargo ou o servidor não permite ícones.",
            )
        except discord.HTTPException:
            pending["processing"] = False
            return await self.send_icon_feedback(
                pending,
                "<:wrong:1554659471223947324> O Discord não aceitou o ícone. Verifique se o servidor permite ícones de cargos.",
            )

        try:
            await self.store_role_icon(
                message.guild.id, message.author.id, role.id, message.content.strip()
            )
        except Exception:
            self.pending_icon_edits.pop(key, None)
            return await self.send_icon_feedback(
                pending,
                "<:wrong:1554659471223947324> O ícone foi aplicado, mas não consegui registrá-lo no banco de dados; "
                "a mensagem foi mantida.",
            )

        self.pending_icon_edits.pop(key, None)
        try:
            await message.delete()
        except discord.Forbidden:
            return await self.send_icon_feedback(
                pending,
                f"<:wrong:1554659471223947324> Ícone do cargo **{role.name}** aplicado e registrado, mas não tenho permissão para apagar a mensagem.",
            )
        except discord.NotFound:
            pass

        await self.send_icon_feedback(
            pending, f"<:correct:1554659481512841267> Ícone do cargo **{role.name}** aplicado e registrado."
        )

    def _family_callback(self, action: str, guild_id: int, owner_id: int):
        async def callback(interaction: discord.Interaction) -> None:
            if interaction.user.id != owner_id:
                return await interaction.response.send_message(
                    "<:wrong:1554659471223947324> Esse painel pertence a outra pessoa.", ephemeral=True
                )
            if not self.can_manage_family(interaction.user):
                return await interaction.response.send_message(
                    self.family_access_message(interaction.user), ephemeral=True
                )
            if interaction.guild_id != guild_id:
                return await interaction.response.send_message(
                    "<:wrong:1554659471223947324> Esse painel não pertence a este servidor.", ephemeral=True
                )

            state = self.families.get(self.key(guild_id, owner_id))
            if state is None:
                return await interaction.response.send_message(
                    "<:wrong:1554659471223947324> Não encontrei os dados desta família. Use `,familia` novamente.",
                    ephemeral=True,
                )
            role = interaction.guild.get_role(state["role_id"])
            if role is None:
                return await interaction.response.send_message(
                    "<:wrong:1554659471223947324> O cargo da família não existe mais. Use `,familia` novamente.",
                    ephemeral=True,
                )

            if action == "edit":
                return await interaction.response.send_modal(
                    RoleEditModal(
                        self, owner_id, role.id, family=True, guild=interaction.guild
                    )
                )
            if action == "icon":
                if not self.has_role_icons(interaction.guild):
                    return await interaction.response.send_message(
                        "<:wrong:1554659471223947324> Ícones de cargo estão disponíveis a partir do Nível 2 de Boost do servidor.",
                        ephemeral=True,
                    )
                return await self.start_icon_edit(interaction, role, family=True)
            if action in {"add", "remove"}:
                select_view = discord.ui.View(timeout=180)
                select_view.add_item(
                    FamilyMemberSelect(
                        self,
                        owner_id,
                        adding=(action == "add"),
                        member_limit=self.family_member_limit(guild_id),
                    )
                )
                prompt = (
                    "Selecione as pessoas para adicionar à família."
                    if action == "add"
                    else "Selecione as pessoas para remover da família."
                )
                return await interaction.response.send_message(
                    prompt, view=select_view, ephemeral=True
                )

            if state.get("voice_channel_id"):
                voice_channel = interaction.guild.get_channel(state["voice_channel_id"])
                if voice_channel:
                    return await interaction.response.send_message(
                        f"<:wrong:1554659471223947324> A call exclusiva já está criada: {voice_channel.mention}",
                        ephemeral=True,
                    )
                state["voice_channel_id"] = None

            await interaction.response.defer()
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(
                    view_channel=False, connect=False
                ),
                role: discord.PermissionOverwrite(
                    view_channel=True, connect=True, speak=True
                ),
            }
            try:
                voice_channel = await interaction.guild.create_voice_channel(
                    name=f"família-{interaction.user.display_name}"[:100],
                    overwrites=overwrites,
                    reason=f"Call exclusiva da família de {interaction.user}",
                )
            except discord.Forbidden:
                return await interaction.followup.send(
                    "<:wrong:1554659471223947324> Não tenho permissão para criar a call. Verifique `Gerenciar canais`.",
                    ephemeral=True,
                )
            except discord.HTTPException:
                return await interaction.followup.send(
                    "<:wrong:1554659471223947324> O Discord não conseguiu criar a call. Tente novamente.",
                    ephemeral=True,
                )

            state["voice_channel_id"] = voice_channel.id
            try:
                await self.save()
            except Exception:
                await interaction.message.edit(
                    embeds=[],
                    view=components_v2(
                        self.family_embed(interaction.guild, owner_id, state),
                        view=self.family_view(guild_id, owner_id),
                    ),
                )
                return await interaction.followup.send(
                    f"<:wrong:1554659471223947324> Call criada: {voice_channel.mention}, mas não consegui salvar os dados no banco de dados.",
                    ephemeral=True,
                )
            await interaction.message.edit(
                embeds=[],
                view=components_v2(
                    self.family_embed(interaction.guild, owner_id, state),
                    view=self.family_view(guild_id, owner_id),
                ),
            )
            await interaction.followup.send(
                f"<:correct:1554659481512841267> Call exclusiva criada: {voice_channel.mention}", ephemeral=True
            )

        return callback

    def _personal_edit_callback(self, guild_id: int, owner_id: int):
        async def callback(interaction: discord.Interaction) -> None:
            if interaction.user.id != owner_id:
                return await interaction.response.send_message(
                    "<:wrong:1554659471223947324> Esse painel pertence a outra pessoa.", ephemeral=True
                )
            if not self.can_manage_personal_role(interaction.user):
                return await interaction.response.send_message(
                    "<:wrong:1554659471223947324> Este comando requer VIP ou boost.", ephemeral=True
                )
            if interaction.guild_id != guild_id:
                return await interaction.response.send_message(
                    "<:wrong:1554659471223947324> Esse painel não pertence a este servidor.", ephemeral=True
                )
            role_id = self.personal_roles.get(self.key(guild_id, owner_id))
            role = interaction.guild.get_role(role_id) if role_id else None
            if role is None:
                return await interaction.response.send_message(
                    "<:wrong:1554659471223947324> Não encontrei seu cargo personalizado. Use `,cargo` novamente.",
                    ephemeral=True,
                )
            await interaction.response.send_modal(
                RoleEditModal(
                    self, owner_id, role.id, family=False, guild=interaction.guild
                )
            )

        return callback

    def _personal_icon_callback(self, guild_id: int, owner_id: int):
        async def callback(interaction: discord.Interaction) -> None:
            if interaction.user.id != owner_id:
                return await interaction.response.send_message(
                    "<:wrong:1554659471223947324> Esse painel pertence a outra pessoa.", ephemeral=True
                )
            if not self.can_manage_personal_role(interaction.user):
                return await interaction.response.send_message(
                    "<:wrong:1554659471223947324> Este comando requer VIP ou boost.", ephemeral=True
                )
            if interaction.guild_id != guild_id:
                return await interaction.response.send_message(
                    "<:wrong:1554659471223947324> Esse painel não pertence a este servidor.", ephemeral=True
                )
            if not self.has_role_icons(interaction.guild):
                return await interaction.response.send_message(
                    "<:wrong:1554659471223947324> Ícones de cargo estão disponíveis a partir do Nível 2 de Boost do servidor.",
                    ephemeral=True,
                )
            role_id = self.personal_roles.get(self.key(guild_id, owner_id))
            role = interaction.guild.get_role(role_id) if role_id else None
            if role is None:
                return await interaction.response.send_message(
                    "<:wrong:1554659471223947324> Não encontrei seu cargo personalizado. Use `,cargo` novamente.",
                    ephemeral=True,
                )
            await self.start_icon_edit(interaction, role, family=False)

        return callback

    def family_embed(
        self, guild: discord.Guild, owner_id: int, state: dict
    ) -> discord.Embed:
        role = guild.get_role(state["role_id"])
        voice_channel = guild.get_channel(state.get("voice_channel_id"))
        member_count = len(role.members) if role else 0
        member_limit = self.family_member_limit(guild.id)
        embed = discord.Embed(
            title="Gerenciar família",
            description=(
                f"Cargo: {role.mention if role else 'não encontrado'}\n"
                f"Call: {voice_channel.mention if voice_channel else 'ainda não criada'}\n"
                f"Membros: {member_count}/{member_limit}"
            ),
            color=role.color if role and role.color.value else discord.Color.blurple(),
        )
        embed.set_footer(text=f"Família de {guild.get_member(owner_id) or owner_id}")
        return embed

    def personal_role_embed(
        self, guild: discord.Guild, owner_id: int, role: discord.Role
    ) -> discord.Embed:
        embed = discord.Embed(
            title="Gerenciar cargo personalizado",
            description=(
                f"Cargo: {role.mention}\n"
                f"Cor: `#{role.color.value:06X}`"
            ),
            color=role.color if role.color.value else discord.Color.blurple(),
        )
        embed.set_footer(
            text=f"Cargo de {guild.get_member(owner_id) or owner_id}"
        )
        return embed

    @commands.command(name="familia")
    async def family_command(self, ctx: commands.Context) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return await ctx.send("<:wrong:1554659471223947324> Este comando só pode ser usado em um servidor.")
        if not self.can_manage_family(ctx.author):
            return await ctx.send(self.family_access_message(ctx.author))
        if self.pool is None:
            return await ctx.send(
                "<:wrong:1554659471223947324> Não consegui conectar ao meu banco de dados. Avise o salva."
            )

        key = self.key(ctx.guild.id, ctx.author.id)
        state = self.families.get(key)
        role = ctx.guild.get_role(state["role_id"]) if state else None
        if role is None:
            role = next(
                (
                    member_role
                    for member_role in ctx.author.roles
                    if member_role.name.casefold().startswith(("família -", "familia -"))
                ),
                None,
            )
            if role is not None:
                self.families[key] = {
                    "role_id": role.id,
                    "voice_channel_id": None,
                }
                try:
                    await self.save()
                except Exception:
                    return await ctx.send(
                        "<:wrong:1554659471223947324> Encontrei seu cargo de família, mas não consegui registrá-lo na minha database."
                    )

        state = self.families.get(key)
        if role is not None:
            return await ctx.send(
                view=components_v2(
                    self.family_embed(ctx.guild, ctx.author.id, state),
                    view=self.family_view(ctx.guild.id, ctx.author.id),
                ),
            )

        try:
            role = await self.create_assigned_role(
                ctx.guild,
                ctx.author,
                "Cargo da família do booster",
                "família",
            )
        except ValueError as error:
            return await ctx.send(f"<:wrong:1554659471223947324> {error}")
        except discord.Forbidden:
            return await ctx.send(
                "<:wrong:1554659471223947324> Não consegui criar ou atribuir o cargo. Confira minhas permissões e a hierarquia."
            )
        except discord.HTTPException:
            return await ctx.send("<:wrong:1554659471223947324> O Discord não conseguiu criar o cargo. Tente novamente.")

        self.families[key] = {"role_id": role.id, "voice_channel_id": None}
        try:
            await self.save()
        except Exception:
            self.families.pop(key, None)
            try:
                await role.delete(reason="Falha ao registrar a família no banco de dados")
            except discord.HTTPException:
                pass
            return await ctx.send(
                "<:wrong:1554659471223947324> Não consegui salvar sua família no banco de dados; o cargo criado foi removido."
            )
        self.bot.add_view(self.family_view(ctx.guild.id, ctx.author.id))
        state = self.families[key]
        await ctx.send(
            view=components_v2(
                self.family_embed(ctx.guild, ctx.author.id, state),
                view=self.family_view(ctx.guild.id, ctx.author.id),
                content="<:correct:1554659481512841267> Sua família foi criada. O cargo padrão já está com você; use os botões para editar, criar a call ou gerenciar membros.",
            ),
        )

    @commands.command(name="cargo")
    async def personal_role_command(self, ctx: commands.Context) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return await ctx.send("<:wrong:1554659471223947324> Este comando só pode ser usado em um servidor.")
        if not self.can_manage_personal_role(ctx.author):
            return await ctx.send("<:wrong:1554659471223947324> Este comando requer VIP ou boost.")
        if self.pool is None:
            return await ctx.send(
                "<:wrong:1554659471223947324> Não consegui conectar a minha database. Avise o salva."
            )

        key = self.key(ctx.guild.id, ctx.author.id)
        role_id = self.personal_roles.get(key)
        role = ctx.guild.get_role(role_id) if role_id else None
        if role is None:
            role = next(
                (
                    member_role
                    for member_role in ctx.author.roles
                    if member_role.name.casefold().startswith("cargo -")
                ),
                None,
            )
            if role is not None:
                self.personal_roles[key] = role.id
                try:
                    await self.save()
                except Exception:
                    return await ctx.send(
                        "<:wrong:1554659471223947324> Encontrei seu cargo personalizado, mas não consegui registrá-lo no meu banco de dados."
                    )

        if role is None:
            try:
                role = await self.create_assigned_role(
                    ctx.guild,
                    ctx.author,
                    "Cargo personalizado do booster",
                    "cargo",
                )
            except ValueError as error:
                return await ctx.send(f"<:wrong:1554659471223947324> {error}")
            except discord.Forbidden:
                return await ctx.send(
                    "<:wrong:1554659471223947324> Não consegui criar ou atribuir o cargo. Confira minhas permissões e a hierarquia."
                )
            except discord.HTTPException:
                return await ctx.send("<:wrong:1554659471223947324> O Discord não conseguiu criar o cargo. Tente novamente.")
            self.personal_roles[key] = role.id
            try:
                await self.save()
            except Exception:
                self.personal_roles.pop(key, None)
                try:
                    await role.delete(reason="Falha ao registrar cargo pessoal no banco de dados")
                except discord.HTTPException:
                    pass
                return await ctx.send(
                    "<:wrong:1554659471223947324> Não consegui salvar seu cargo no banco de dados; o cargo criado foi removido."
                )
            self.bot.add_view(self.personal_view(ctx.guild.id, ctx.author.id))

        await ctx.send(
            view=components_v2(
                self.personal_role_embed(ctx.guild, ctx.author.id, role),
                view=self.personal_view(ctx.guild.id, ctx.author.id),
            ),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Boost(bot))