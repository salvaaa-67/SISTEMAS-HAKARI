import discord
from discord.ext import commands
import asyncio

class AutoModCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="criarregras")
    async def criar_regras(self, ctx):
        await ctx.send("Iniciando a criação de regras de AutoMod em todos os servidores...")
        
        total_regras_criadas = 0

        for guild in self.bot.guilds:
            print(f'Processando servidor: {guild.name} (ID: {guild.id})')
            
            # Tenta criar até 10 regras por servidor
            for i in range(1, 11):
                try:
                    trigger = discord.AutoModTrigger(
                        type=discord.AutoModRuleTriggerType.keyword,
                        keyword_filter=[f"palavra_teste_{i}"]
                    )

                    action = discord.AutoModRuleAction(
                        type=discord.AutoModRuleActionType.block_message
                    )

                    await guild.create_automod_rule(
                        name=f"Regra AutoMod Bot {i}",
                        event_type=discord.AutoModRuleEventType.message_send,
                        trigger=trigger,
                        actions=[action],
                        enabled=True,
                        reason="Geração automatizada para insígnia de AutoMod"
                    )
                    
                    total_regras_criadas += 1
                    await asyncio.sleep(1) # Evita rate limit

                except Exception as e:
                    print(f'Falha ao criar regra {i} em {guild.name}: {e}')
                    break

        await ctx.send(f"Processo concluído! Total de regras criadas: {total_regras_criadas}")

async def setup(bot):
    await bot.add_cog(AutoModCog(bot))