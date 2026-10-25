import random
from discord.ext import commands

class DearOuDef(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="dear_ou_def", help="DEAR OU DEF?")
    async def averiguar(self, ctx):
        mensagem = await ctx.send("<a:loading:1554658916741283990> pensando...")

        opcoes = [
            "ah, eu prefiro a dear, dear fofinha",
            "prefiro o def, dear pcd"
        ]

        escolha = random.choice(opcoes)

        await mensagem.edit(content=f"{escolha}")

async def setup(bot):
    await bot.add_cog(DearOuDef(bot))