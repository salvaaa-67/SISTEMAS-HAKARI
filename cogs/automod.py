from __future__ import annotations

import asyncio
import io
import logging
import secrets
from collections import Counter

import discord
from discord import app_commands
from discord.ext import commands


log = logging.getLogger(__name__)

RULE_LIMITS = {
    discord.AutoModRuleTriggerType.keyword: 6,
    discord.AutoModRuleTriggerType.spam: 1,
    discord.AutoModRuleTriggerType.keyword_preset: 1,
    discord.AutoModRuleTriggerType.mention_spam: 1,
    discord.AutoModRuleTriggerType.member_profile: 1,
}


class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.guild_semaphore = asyncio.Semaphore(3)

    def build_rules(
        self, guild_id: int, batch_id: str
    ) -> list[tuple[str, discord.AutoModRuleEventType, discord.AutoModTrigger, list[discord.AutoModRuleAction]]]:
        rules: list[
            tuple[
                str,
                discord.AutoModRuleEventType,
                discord.AutoModTrigger,
                list[discord.AutoModRuleAction],
            ]
        ] = []

        def add_rule(
            event_type: discord.AutoModRuleEventType,
            trigger: discord.AutoModTrigger,
            action: discord.AutoModRuleAction,
        ) -> None:
            index = len(rules) + 1
            name = f"HAKARI AutoMod {batch_id} {index:02d}"
            rules.append((name, event_type, trigger, [action]))

        for _ in range(RULE_LIMITS[discord.AutoModRuleTriggerType.keyword]):
            token = f"hakari-{guild_id}-{secrets.token_hex(6)}"
            add_rule(
                discord.AutoModRuleEventType.message_send,
                discord.AutoModTrigger(keyword_filter=[token]),
                discord.AutoModRuleAction(
                    custom_message="Mensagem bloqueada por uma regra de teste do AutoMod."
                ),
            )
        add_rule(
            discord.AutoModRuleEventType.message_send,
            discord.AutoModTrigger(type=discord.AutoModRuleTriggerType.spam),
            discord.AutoModRuleAction(
                custom_message="Mensagem bloqueada por uma regra de teste do AutoMod."
            ),
        )

        presets = (
            discord.AutoModPresets.profanity,
            discord.AutoModPresets.sexual_content,
            discord.AutoModPresets.slurs,
        )
        add_rule(
            discord.AutoModRuleEventType.message_send,
            discord.AutoModTrigger(presets=secrets.choice(presets)),
            discord.AutoModRuleAction(
                custom_message="Mensagem bloqueada por uma regra de teste do AutoMod."
            ),
        )
        add_rule(
            discord.AutoModRuleEventType.message_send,
            discord.AutoModTrigger(mention_limit=secrets.choice((5, 8, 10, 15))),
            discord.AutoModRuleAction(
                custom_message="Mensagem bloqueada por uma regra de teste do AutoMod."
            ),
        )

        profile_token = f"hakari-{guild_id}-{secrets.token_hex(6)}"
        add_rule(
            discord.AutoModRuleEventType.member_update,
            discord.AutoModTrigger(
                type=discord.AutoModRuleTriggerType.member_profile,
                keyword_filter=[profile_token],
            ),
            discord.AutoModRuleAction(
                type=discord.AutoModRuleActionType.block_member_interactions
            ),
        )

        return rules

    async def apply_to_guild(
        self, guild: discord.Guild, batch_id: str
    ) -> tuple[str, str, int]:
        async with self.guild_semaphore:
            bot_member = guild.me
            if bot_member is None or not bot_member.guild_permissions.manage_guild:
                return guild.name, "sem permissão Gerenciar Servidor", 0

            try:
                existing_rules = await guild.fetch_automod_rules()
            except discord.HTTPException as error:
                log.warning(
                    "Não foi possível consultar regras de AutoMod em %s: %s",
                    guild.id,
                    error,
                )
                return guild.name, f"falha ao consultar regras ({error})", 0

            counts = Counter(rule.trigger.type for rule in existing_rules)
            requested_counts = Counter(RULE_LIMITS)
            unavailable = [
                trigger_type.name
                for trigger_type, requested in requested_counts.items()
                if counts[trigger_type] + requested > RULE_LIMITS[trigger_type]
            ]
            if unavailable:
                return (
                    guild.name,
                    "sem espaço para o conjunto completo "
                    f"(limites atingidos: {', '.join(unavailable)})",
                    0,
                )

            created_rules: list[discord.AutoModRule] = []
            try:
                for name, event_type, trigger, actions in self.build_rules(
                    guild.id, batch_id
                ):
                    rule = await guild.create_automod_rule(
                        name=name,
                        event_type=event_type,
                        trigger=trigger,
                        actions=actions,
                        enabled=True,
                        reason="Lote de teste AutoMod solicitado pelo dono do bot.",
                    )
                    created_rules.append(rule)
            except discord.HTTPException as error:
                rollback_failures = []
                for rule in reversed(created_rules):
                    try:
                        await rule.delete(
                            reason="Reversão do lote incompleto de teste AutoMod."
                        )
                    except discord.HTTPException as rollback_error:
                        rollback_failures.append(str(rollback_error))
                        log.exception(
                            "Falha ao reverter regra AutoMod %s no servidor %s",
                            rule.id,
                            guild.id,
                        )

                status = (
                    f"falha ao criar regras ({error}); "
                    f"{len(created_rules) - len(rollback_failures)} revertidas"
                )
                if rollback_failures:
                    status += (
                        f"; {len(rollback_failures)} não puderam ser removidas "
                        "— consulte os logs"
                    )
                log.warning("AutoMod em %s: %s", guild.id, status)
                return guild.name, status, 0

            return guild.name, "10 regras criadas", len(created_rules)

    @app_commands.command(
        name="automod",
        description="Aplica 10 regras de teste do AutoMod em todos os servidores.",
    )
    @app_commands.guild_only()
    async def automod(
        self, interaction: discord.Interaction, confirmar: bool
    ) -> None:
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message(
                "Somente o dono do bot pode usar este comando.",
                ephemeral=True,
            )

        if not confirmar:
            return await interaction.response.send_message(
                "Nenhuma regra foi criada. Execute `/automod` novamente com "
                "`confirmar: true` para aplicar dez regras por servidor. "
                "Elas permanecerão ativas até serem removidas manualmente.",
                ephemeral=True,
            )

        await interaction.response.defer(ephemeral=True, thinking=True)

        guilds = list(self.bot.guilds)
        if not guilds:
            return await interaction.followup.send(
                "O bot não está em nenhum servidor.", ephemeral=True
            )

        batch_id = secrets.token_hex(3)
        results = await asyncio.gather(
            *(self.apply_to_guild(guild, batch_id) for guild in guilds)
        )

        created_total = sum(created for _, _, created in results)
        successful_guilds = sum(created == 10 for _, _, created in results)
        lines = [
            f"Lote: `HAKARI AutoMod {batch_id}`",
            f"Regras criadas: **{created_total}** em **{successful_guilds}/{len(guilds)}** servidores.",
            "As regras ficam ativas até remoção manual.",
            "",
        ]
        lines.extend(
            f"- {guild_name}: {status}" for guild_name, status, _ in results
        )
        report = "\n".join(lines)

        if len(report) <= 1900:
            await interaction.followup.send(report, ephemeral=True)
            return

        report_file = discord.File(
            io.BytesIO(report.encode("utf-8")),
            filename=f"automod-{batch_id}-relatorio.txt",
        )
        await interaction.followup.send(
            content=(
                f"Lote `HAKARI AutoMod {batch_id}` concluído: "
                f"{created_total} regras criadas em "
                f"{successful_guilds}/{len(guilds)} servidores. "
                "As regras permanecem ativas até remoção manual."
            ),
            file=report_file,
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoMod(bot))
