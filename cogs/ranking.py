import asyncio
import os
import re
from urllib.parse import urlsplit

import asyncpg
import discord
from discord.ext import commands, tasks

from .menu import DEVELOPER_ID
from .components_v2 import ComponentsV2View, components_v2


LEGACY_CHANNELS = {
    "call": 1539882453743697972,
    "messages": 1540570978650824704,
}
RANKING_NAMES = {"call": "call", "messages": "mensagens"}


class RankingPostView(ComponentsV2View):
    def __init__(self, ranking: "Ranking", ranking_type: str):
        super().__init__(timeout=None)
        self.ranking = ranking
        self.ranking_type = ranking_type
        button = discord.ui.Button(
            label="Resetar",
            style=discord.ButtonStyle.danger,
            custom_id=f"ranking:reset:{ranking_type}",
        )
        button.callback = self.reset_callback
        self.add_item(button)

    async def reset_callback(self, interaction: discord.Interaction) -> None:
        await self.ranking.request_reset(interaction, self.ranking_type)


class RankingResetConfirmView(discord.ui.View):
    def __init__(self, ranking: "Ranking", guild_id: int, ranking_type: str):
        super().__init__(timeout=60)
        self.ranking = ranking
        self.guild_id = guild_id
        self.ranking_type = ranking_type

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        guild = interaction.guild
        if guild is None or not self.ranking.can_manage(interaction.user.id, guild):
            await interaction.response.send_message(
                "Somente o dono do servidor ou o desenvolvedor pode resetar rankings.",
                ephemeral=True,
            )
            return False
        if guild.id != self.guild_id:
            await interaction.response.send_message(
                "Esta confirmação pertence a outro servidor.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Confirmar reset", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.ranking.reset_ranking(
            interaction, self.guild_id, self.ranking_type
        )

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Reset cancelado.", view=None
        )


class Ranking(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pool: asyncpg.Pool | None = None
        self.sessions_initialized = False
        self.update_locks: dict[tuple[int, str], asyncio.Lock] = {}

    async def cog_load(self) -> None:
        database_url = os.getenv("DATABASE", "").strip()
        database_variable = "DATABASE"
        if not database_url:
            database_url = os.getenv("DATABASE_URL", "").strip()
            database_variable = "DATABASE_URL"
        if not database_url:
            print("Rankings indisponíveis: variável DATABASE não configurada.")
            return

        try:
            self.pool = await asyncpg.create_pool(
                dsn=database_url,
                ssl="require",
                min_size=1,
                max_size=5,
                command_timeout=20,
            )
            await self.pool.execute(
                """
                CREATE TABLE IF NOT EXISTS hakari_rank_call (
                    guild_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    total_seconds BIGINT NOT NULL DEFAULT 0,
                    active_since TIMESTAMPTZ,
                    PRIMARY KEY (guild_id, user_id)
                )
                """
            )
            await self.pool.execute(
                """
                CREATE TABLE IF NOT EXISTS hakari_rank_messages (
                    guild_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    message_count BIGINT NOT NULL DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                )
                """
            )
            await self.pool.execute(
                """
                CREATE TABLE IF NOT EXISTS hakari_rank_posts (
                    guild_id BIGINT NOT NULL,
                    ranking_type TEXT NOT NULL,
                    channel_id BIGINT NOT NULL,
                    message_id BIGINT NOT NULL,
                    PRIMARY KEY (guild_id, ranking_type)
                )
                """
            )
        except Exception as error:
            if self.pool is not None:
                await self.pool.close()
                self.pool = None
            database_host = urlsplit(database_url).hostname or "não identificado"
            print(
                "Não foi possível inicializar os rankings "
                f"(variável={database_variable}, host={database_host}): "
                f"{type(error).__name__}: {error}",
                flush=True,
            )
            return

        for ranking_type in RANKING_NAMES:
            self.bot.add_view(RankingPostView(self, ranking_type))
        self.refresh_rankings.start()

    async def cog_unload(self) -> None:
        self.refresh_rankings.cancel()
        if self.pool is not None:
            await self.pool.close()

    def menu(self):
        return self.bot.get_cog("Menu")

    def setting(self, guild_id: int, key: str, default=None):
        menu = self.menu()
        return menu.get_value(guild_id, key, default) if menu else default

    def can_manage(self, user_id: int, guild: discord.Guild) -> bool:
        return user_id == DEVELOPER_ID or user_id == guild.owner_id

    def update_lock(self, guild_id: int, ranking_type: str) -> asyncio.Lock:
        key = (guild_id, ranking_type)
        if key not in self.update_locks:
            self.update_locks[key] = asyncio.Lock()
        return self.update_locks[key]

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self.pool is None or self.sessions_initialized:
            return

        try:
            await self.pool.execute(
                "UPDATE hakari_rank_call SET active_since = NULL "
                "WHERE active_since IS NOT NULL"
            )
            active_members = [
                (guild.id, member.id)
                for guild in self.bot.guilds
                for channel in (*guild.voice_channels, *guild.stage_channels)
                for member in channel.members
                if not member.bot
            ]
            if active_members:
                await self.pool.executemany(
                    """
                    INSERT INTO hakari_rank_call (
                        guild_id, user_id, total_seconds, active_since
                    )
                    VALUES ($1, $2, 0, NOW())
                    ON CONFLICT (guild_id, user_id) DO UPDATE SET
                        active_since = NOW()
                    """,
                    active_members,
                )
            self.sessions_initialized = True
            await self.update_all_rankings()
        except Exception as error:
            print(
                f"Falha ao iniciar os rankings: {type(error).__name__}: {error}",
                flush=True,
            )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if self.pool is None or member.bot:
            return

        try:
            if before.channel is None and after.channel is not None:
                await self.pool.execute(
                    """
                    INSERT INTO hakari_rank_call (
                        guild_id, user_id, total_seconds, active_since
                    )
                    VALUES ($1, $2, 0, NOW())
                    ON CONFLICT (guild_id, user_id) DO UPDATE SET
                        active_since = COALESCE(
                            hakari_rank_call.active_since, NOW()
                        )
                    """,
                    member.guild.id,
                    member.id,
                )
            elif before.channel is not None and after.channel is None:
                await self.pool.execute(
                    """
                    UPDATE hakari_rank_call
                    SET total_seconds = total_seconds + GREATEST(
                            0,
                            FLOOR(EXTRACT(EPOCH FROM (NOW() - active_since)))::BIGINT
                        ),
                        active_since = NULL
                    WHERE guild_id = $1 AND user_id = $2
                      AND active_since IS NOT NULL
                    """,
                    member.guild.id,
                    member.id,
                )
        except Exception as error:
            print(
                f"Falha ao registrar tempo em call de {member.id}: "
                f"{type(error).__name__}: {error}",
                flush=True,
            )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if self.pool is None or member.bot:
            return
        try:
            await self.pool.execute(
                """
                UPDATE hakari_rank_call
                SET total_seconds = total_seconds + GREATEST(
                        0,
                        FLOOR(EXTRACT(EPOCH FROM (NOW() - active_since)))::BIGINT
                    ),
                    active_since = NULL
                WHERE guild_id = $1 AND user_id = $2
                  AND active_since IS NOT NULL
                """,
                member.guild.id,
                member.id,
            )
        except Exception as error:
            print(
                f"Falha ao fechar tempo em call de membro removido {member.id}: "
                f"{type(error).__name__}: {error}",
                flush=True,
            )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if self.pool is None or message.guild is None or message.author.bot:
            return
        try:
            await self.pool.execute(
                """
                INSERT INTO hakari_rank_messages (guild_id, user_id, message_count)
                VALUES ($1, $2, 1)
                ON CONFLICT (guild_id, user_id) DO UPDATE SET
                    message_count = hakari_rank_messages.message_count + 1
                """,
                message.guild.id,
                message.author.id,
            )
        except Exception as error:
            print(
                f"Falha ao contar mensagem de {message.author.id}: "
                f"{type(error).__name__}: {error}",
                flush=True,
            )

    @tasks.loop(minutes=5)
    async def refresh_rankings(self) -> None:
        await self.update_all_rankings()

    @refresh_rankings.before_loop
    async def before_refresh_rankings(self) -> None:
        await self.bot.wait_until_ready()

    async def update_all_rankings(self) -> None:
        if self.pool is None:
            return
        await asyncio.gather(
            *(
                self.update_ranking(guild, ranking_type)
                for guild in self.bot.guilds
                for ranking_type in RANKING_NAMES
            )
        )

    async def update_ranking(
        self, guild: discord.Guild, ranking_type: str
    ) -> None:
        if self.pool is None:
            return
        async with self.update_lock(guild.id, ranking_type):
            await self.publish_ranking(guild, ranking_type)

    def ranking_config_prefix(self, ranking_type: str) -> str:
        return "ranking_call" if ranking_type == "call" else "ranking_messages"

    def image_url(self, value) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        parsed = urlsplit(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None
        return value.strip()

    def introduction_embed(
        self, guild: discord.Guild, ranking_type: str
    ) -> discord.Embed:
        prefix = f"{self.ranking_config_prefix(ranking_type)}_intro"
        ranking_label = RANKING_NAMES[ranking_type]
        title = self.setting(
            guild.id, f"{prefix}_title", f"Ranking de {ranking_label}"
        )
        description = self.setting(
            guild.id,
            f"{prefix}_description",
            "Acompanhe o top 10 atualizado automaticamente.",
        )
        title = title or f"Ranking de {ranking_label}"
        description = description or "Acompanhe o top 10 atualizado automaticamente."
        footer = self.setting(guild.id, f"{prefix}_footer", "")
        embed = discord.Embed(
            title=title[:256] if title else None,
            description=description[:3000] if description else None,
            color=discord.Color.blurple(),
        )
        if footer:
            embed.set_footer(text=footer[:500])
        thumbnail = self.image_url(
            self.setting(guild.id, f"{prefix}_thumbnail", "")
        )
        image = self.image_url(self.setting(guild.id, f"{prefix}_image", ""))
        title_image = self.image_url(
            self.setting(guild.id, f"{prefix}_title_image", "")
        )
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        if image:
            embed.set_image(url=image)
        if title_image:
            embed.set_author(name="\u200b", icon_url=title_image)
        return embed

    def top_embed(
        self,
        guild: discord.Guild,
        ranking_type: str,
        entries: list[tuple[int, int]],
    ) -> discord.Embed:
        prefix = f"{self.ranking_config_prefix(ranking_type)}_top"
        title = self.setting(guild.id, f"{prefix}_title", "")
        thumbnail = self.image_url(
            self.setting(guild.id, f"{prefix}_thumbnail", "")
        )
        if ranking_type == "call":
            default_title = "Top 10: tempo em call"
            value_name = "tempo em call"
            format_value = self.format_duration
        else:
            default_title = "Top 10: mensagens"
            value_name = "mensagens"
            format_value = self.format_count

        description = "\n".join(
            f"**`{index}.`** <@{user_id}> — {format_value(value)} {value_name}"
            for index, (user_id, value) in enumerate(entries[:10], start=1)
        ) or "Ainda não há dados neste ranking."
        embed = discord.Embed(
            title=(title or default_title)[:256],
            description=description,
            color=discord.Color.gold(),
        )
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        return embed

    def format_duration(self, seconds: int) -> str:
        days, remainder = divmod(max(0, seconds), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        if days:
            return f"{days}d {hours:02}h {minutes:02}m {seconds:02}s"
        return f"{hours:02}h {minutes:02}m {seconds:02}s"

    def format_count(self, count: int) -> str:
        return f"{count:,}".replace(",", ".")

    async def ranking_entries(
        self, guild_id: int, ranking_type: str
    ) -> list[tuple[int, int]]:
        if ranking_type == "call":
            rows = await self.pool.fetch(
                """
                SELECT user_id,
                       total_seconds + CASE
                           WHEN active_since IS NULL THEN 0
                           ELSE GREATEST(
                               0,
                               FLOOR(EXTRACT(EPOCH FROM (NOW() - active_since)))::BIGINT
                           )
                       END AS score
                FROM hakari_rank_call
                WHERE guild_id = $1
                ORDER BY score DESC, user_id
                LIMIT 10
                """,
                guild_id,
            )
        else:
            rows = await self.pool.fetch(
                """
                SELECT user_id, message_count AS score
                FROM hakari_rank_messages
                WHERE guild_id = $1
                ORDER BY message_count DESC, user_id
                LIMIT 10
                """,
                guild_id,
            )
        return [(row["user_id"], row["score"]) for row in rows]

    async def publish_ranking(
        self, guild: discord.Guild, ranking_type: str
    ) -> None:
        prefix = self.ranking_config_prefix(ranking_type)
        channel_id = self.setting(guild.id, f"{prefix}_channel")
        if channel_id is None:
            return
        channel = guild.get_channel(int(channel_id))
        if channel is None:
            try:
                channel = await guild.fetch_channel(int(channel_id))
            except (discord.Forbidden, discord.NotFound, discord.HTTPException) as error:
                print(
                    f"Não encontrei o canal configurado do ranking {ranking_type} "
                    f"em {guild.id}: {error}",
                    flush=True,
                )
                return
        if not isinstance(channel, discord.TextChannel):
            return

        entries = await self.ranking_entries(guild.id, ranking_type)
        embeds = [
            self.introduction_embed(guild, ranking_type),
            self.top_embed(guild, ranking_type, entries),
        ]
        view = RankingPostView(self, ranking_type)
        post = await self.pool.fetchrow(
            """
            SELECT channel_id, message_id FROM hakari_rank_posts
            WHERE guild_id = $1 AND ranking_type = $2
            """,
            guild.id,
            ranking_type,
        )
        message = None
        if post and post["channel_id"] == channel.id:
            try:
                message = await channel.fetch_message(post["message_id"])
            except discord.NotFound:
                pass
            except (discord.Forbidden, discord.HTTPException) as error:
                print(
                    f"Não consegui acessar a mensagem do ranking {ranking_type}: {error}",
                    flush=True,
                )
                return

        try:
            if message is None:
                message = await channel.send(view=components_v2(embeds, view=view))
            else:
                await message.edit(embeds=[], view=components_v2(embeds, view=view))
            await self.pool.execute(
                """
                INSERT INTO hakari_rank_posts (
                    guild_id, ranking_type, channel_id, message_id
                )
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (guild_id, ranking_type) DO UPDATE SET
                    channel_id = EXCLUDED.channel_id,
                    message_id = EXCLUDED.message_id
                """,
                guild.id,
                ranking_type,
                channel.id,
                message.id,
            )
        except (discord.Forbidden, discord.HTTPException) as error:
            print(
                f"Falha ao publicar o ranking {ranking_type} em {guild.id}: {error}",
                flush=True,
            )

    async def request_reset(
        self, interaction: discord.Interaction, ranking_type: str
    ) -> None:
        guild = interaction.guild
        if guild is None or not self.can_manage(interaction.user.id, guild):
            return await interaction.response.send_message(
                "Somente o dono do servidor ou o desenvolvedor pode resetar rankings.",
                ephemeral=True,
            )
        await interaction.response.send_message(
            f"Confirma resetar completamente o ranking de {RANKING_NAMES[ranking_type]}?",
            view=RankingResetConfirmView(self, guild.id, ranking_type),
            ephemeral=True,
        )

    async def reset_ranking(
        self,
        interaction: discord.Interaction,
        guild_id: int,
        ranking_type: str,
    ) -> None:
        if self.pool is None:
            return await interaction.response.edit_message(
                content="O banco de dados está indisponível.", view=None
            )
        guild = interaction.guild
        if guild is None:
            return await interaction.response.edit_message(
                content="Este painel só funciona dentro do servidor.", view=None
            )

        async with self.update_lock(guild_id, ranking_type):
            if ranking_type == "call":
                await self.pool.execute(
                    "DELETE FROM hakari_rank_call WHERE guild_id = $1", guild_id
                )
                active_members = [
                    (guild_id, member.id)
                    for channel in (*guild.voice_channels, *guild.stage_channels)
                    for member in channel.members
                    if not member.bot
                ]
                if active_members:
                    await self.pool.executemany(
                        """
                        INSERT INTO hakari_rank_call (
                            guild_id, user_id, total_seconds, active_since
                        )
                        VALUES ($1, $2, 0, NOW())
                        ON CONFLICT (guild_id, user_id) DO UPDATE SET
                            total_seconds = 0,
                            active_since = NOW()
                        """,
                        active_members,
                    )
            else:
                await self.pool.execute(
                    "DELETE FROM hakari_rank_messages WHERE guild_id = $1", guild_id
                )
            await self.publish_ranking(guild, ranking_type)

        await interaction.response.edit_message(
            content=f"Ranking de {RANKING_NAMES[ranking_type]} resetado.", view=None
        )

    async def legacy_channel(
        self, guild: discord.Guild, channel_id: int
    ) -> discord.abc.Messageable | None:
        channel = guild.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                return None
        if getattr(getattr(channel, "guild", None), "id", None) != guild.id:
            return None
        if not hasattr(channel, "history"):
            return None
        return channel

    def legacy_texts(self, message: discord.Message) -> list[str]:
        texts = [message.content]
        for embed in message.embeds:
            texts.extend((embed.title or "", embed.description or ""))
            texts.extend((embed.footer.text or "", embed.author.name or ""))
            for field in embed.fields:
                texts.extend((field.name, field.value))
        return texts

    def parse_call_duration(self, text: str) -> int | None:
        token_pattern = re.compile(
            r"(\d+)\s*(days?|dias?|d|hours?|horas?|hrs?|h|minutes?|minutos?|mins?|m|seconds?|segundos?|secs?|segs?|s)\b",
            re.IGNORECASE,
        )
        tokens = token_pattern.findall(text)
        total = 0
        for amount, unit in tokens:
            unit = unit.casefold()
            if unit.startswith(("d", "dia")):
                total += int(amount) * 86400
            elif unit.startswith(("h", "hora")):
                total += int(amount) * 3600
            elif unit.startswith(("m", "min")):
                total += int(amount) * 60
            else:
                total += int(amount)

        clock = re.search(r"(\d{1,3}):(\d{2}):(\d{2})", text)
        if clock:
            hours, minutes, seconds = clock.groups()
            return total + int(hours) * 3600 + int(minutes) * 60 + int(seconds)
        if tokens:
            return total

        clock = re.search(
            r"(?:(\d+)\s*d\s*)?(\d{1,3}):(\d{2}):(\d{2})", text, re.I
        )
        if clock:
            days, hours, minutes, seconds = clock.groups()
            return int(days or 0) * 86400 + int(hours) * 3600 + int(minutes) * 60 + int(seconds)
        short_clock = re.search(r"\b(\d{1,3}):(\d{2})\b", text)
        if short_clock:
            return int(short_clock.group(1)) * 60 + int(short_clock.group(2))
        return None

    def parse_message_count(self, text: str) -> int | None:
        values = re.findall(r"(?<!\d)\d[\d.,]*", text)
        if not values:
            return None
        count = int(re.sub(r"\D", "", values[-1]))
        return count if count >= 0 else None

    def parse_legacy_line(
        self, guild: discord.Guild, line: str, ranking_type: str
    ) -> tuple[int, int] | None:
        match = re.search(r"<@!?(\d+)>", line)
        if match:
            user_id = int(match.group(1))
            value_text = line[match.end():]
        else:
            parts = re.split(r"\s+[—–-]\s+", line, maxsplit=1)
            if len(parts) != 2:
                return None
            name = re.sub(r"^\s*\**\s*`?\d+\.?`?\**\s*", "", parts[0]).strip()
            member = next(
                (
                    candidate
                    for candidate in guild.members
                    if candidate.name.casefold() == name.casefold()
                    or candidate.display_name.casefold() == name.casefold()
                ),
                None,
            )
            if member is None:
                return None
            user_id = member.id
            value_text = parts[1]

        value = (
            self.parse_call_duration(value_text)
            if ranking_type == "call"
            else self.parse_message_count(value_text)
        )
        return (user_id, value) if value is not None else None

    def parse_legacy_message(
        self, guild: discord.Guild, message: discord.Message, ranking_type: str
    ) -> list[tuple[int, int]]:
        entries: dict[int, int] = {}
        for text in self.legacy_texts(message):
            for line in text.splitlines():
                parsed = self.parse_legacy_line(guild, line, ranking_type)
                if parsed:
                    entries[parsed[0]] = parsed[1]
        return list(entries.items())

    async def find_legacy_entries(
        self, guild: discord.Guild, ranking_type: str
    ) -> list[tuple[int, int]]:
        channel = await self.legacy_channel(guild, LEGACY_CHANNELS[ranking_type])
        if channel is None:
            raise ValueError(
                f"Não consegui acessar o canal antigo do ranking de {RANKING_NAMES[ranking_type]}."
            )
        async for message in channel.history(limit=100):
            entries = self.parse_legacy_message(guild, message, ranking_type)
            if entries:
                return entries
        return []

    async def import_legacy_entries(
        self,
        guild_id: int,
        ranking_type: str,
        entries: list[tuple[int, int]],
    ) -> None:
        if ranking_type == "call":
            await self.pool.executemany(
                """
                INSERT INTO hakari_rank_call (
                    guild_id, user_id, total_seconds, active_since
                )
                VALUES ($1, $2, $3, NULL)
                ON CONFLICT (guild_id, user_id) DO UPDATE SET
                    total_seconds = EXCLUDED.total_seconds
                """,
                [(guild_id, user_id, value) for user_id, value in entries],
            )
        else:
            await self.pool.executemany(
                """
                INSERT INTO hakari_rank_messages (guild_id, user_id, message_count)
                VALUES ($1, $2, $3)
                ON CONFLICT (guild_id, user_id) DO UPDATE SET
                    message_count = EXCLUDED.message_count
                """,
                [(guild_id, user_id, value) for user_id, value in entries],
            )

    @commands.command(name="sincronizar_rankings_legados")
    async def sync_legacy_rankings(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            return await ctx.send("Este comando só pode ser usado em um servidor.")
        if ctx.author.id != DEVELOPER_ID:
            return await ctx.send("Somente o desenvolvedor pode sincronizar os rankings.")
        if self.pool is None:
            return await ctx.send("O banco dos rankings está indisponível.")

        status = await ctx.send("Importando os dados antigos dos dois rankings...")
        imported = {}
        failures = []
        for ranking_type in RANKING_NAMES:
            try:
                entries = await self.find_legacy_entries(ctx.guild, ranking_type)
                if entries:
                    await self.import_legacy_entries(
                        ctx.guild.id, ranking_type, entries
                    )
                imported[ranking_type] = len(entries)
            except Exception as error:
                failures.append(
                    f"{RANKING_NAMES[ranking_type]}: {type(error).__name__}: {error}"
                )

        await self.update_all_rankings()
        result = (
            f"Importação concluída. Call: {imported.get('call', 0)} pessoa(s); "
            f"mensagens: {imported.get('messages', 0)} pessoa(s)."
        )
        if failures:
            result += "\nFalhas: " + " | ".join(failures)
        await status.edit(content=result)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Ranking(bot))