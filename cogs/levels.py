import math
import os
import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from .components_v2 import ComponentsV2View, components_v2
from .database import Pool, create_pool

MAX_XP = 160000

class ResetConfirmView(ComponentsV2View):
    def __init__(self, cog, guild_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.guild_id = guild_id
        
        self.confirm_btn = discord.ui.Button(label="Confirmar Reset", style=discord.ButtonStyle.danger)
        self.confirm_btn.callback = self.confirm
        self.add_item(self.confirm_btn)
        
        self.cancel_btn = discord.ui.Button(label="Cancelar", style=discord.ButtonStyle.secondary)
        self.cancel_btn.callback = self.cancel
        self.add_item(self.cancel_btn)

    async def confirm(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(title="❌ Erro", description="Somente administradores podem confirmar o reset.", color=discord.Color.red())
            return await interaction.response.send_message(view=components_v2(embed), ephemeral=True)
        
        if self.cog.pool:
            await self.cog.pool.execute("DELETE FROM hakari_levels WHERE guild_id = $1", self.guild_id)
        
        embed = discord.Embed(title="✅ XP Resetado", description="Todo o XP de todos os usuários deste servidor foi resetado com sucesso.", color=discord.Color.red())
        await interaction.response.edit_message(embeds=[], view=components_v2(embed))

    async def cancel(self, interaction: discord.Interaction):
        embed = discord.Embed(title="❌ Cancelado", description="O reset de XP foi cancelado.", color=discord.Color.green())
        await interaction.response.edit_message(embeds=[], view=components_v2(embed))


class Levels(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pool: Pool | None = None
        self.cooldowns = {}
        self.cooldown_time = 60 # 60 segundos de cooldown entre ganho de XP

    async def cog_load(self) -> None:
        try:
            self.pool = await create_pool()
            await self.pool.execute(
                '''
                CREATE TABLE IF NOT EXISTS hakari_levels (
                    guild_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    xp BIGINT NOT NULL DEFAULT 0,
                    level INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                )
                '''
            )
        except Exception as error:
            if self.pool is not None:
                await self.pool.close()
                self.pool = None
            print(f"Não foi possível iniciar o banco do sistema de XP: {error}")

    async def cog_unload(self) -> None:
        if self.pool is not None:
            await self.pool.close()

    def get_level(self, xp: int) -> int:
        return min(xp // 1000, 160)
        
    def get_next_level_xp(self, level: int) -> int:
        return (level + 1) * 1000

    async def set_user_xp(self, guild_id: int, user_id: int, new_xp: int) -> tuple[int, int]:
        new_xp = max(0, min(new_xp, MAX_XP))
        new_level = self.get_level(new_xp)
        
        if self.pool:
            await self.pool.execute(
                '''
                INSERT INTO hakari_levels (guild_id, user_id, xp, level)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (guild_id, user_id) DO UPDATE SET
                    xp = EXCLUDED.xp,
                    level = EXCLUDED.level
                ''',
                guild_id, user_id, new_xp, new_level
            )
        return new_xp, new_level

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if self.pool is None or message.guild is None or message.author.bot:
            return

        menu = self.bot.get_cog("Menu")
        if menu is None or not menu.module_configured(message.guild.id, "levels"):
            return

        guild_id = message.guild.id
        user_id = message.author.id

        # Verifica cooldown para não spammar XP
        current_time = time.time()
        last_time = self.cooldowns.get((guild_id, user_id), 0)
        if current_time - last_time < self.cooldown_time:
            return
        self.cooldowns[(guild_id, user_id)] = current_time

        # Ganho aleatório de XP
        xp_gained = random.randint(15, 25)

        try:
            row = await self.pool.fetchrow("SELECT xp, level FROM hakari_levels WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)
            current_xp = row["xp"] if row else 0
            current_level = row["level"] if row else 0
            
            if current_xp >= MAX_XP:
                return # Máximo de XP já atingido

            new_xp = min(current_xp + xp_gained, MAX_XP)
            new_level = self.get_level(new_xp)
            
            await self.pool.execute(
                '''
                INSERT INTO hakari_levels (guild_id, user_id, xp, level)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (guild_id, user_id) DO UPDATE SET
                    xp = EXCLUDED.xp,
                    level = EXCLUDED.level
                ''',
                guild_id, user_id, new_xp, new_level
            )

            # Verifica se upou de level
            if new_level > current_level:
                level_up_channel_id = menu.get_value(guild_id, "level_up_channel")
                channel = message.channel
                if level_up_channel_id:
                    cfg_channel = message.guild.get_channel(int(level_up_channel_id))
                    if cfg_channel:
                        channel = cfg_channel

                embed = discord.Embed(
                    title="🎉 Subiu de Nível!",
                    description=f"Parabéns {message.author.mention}, você alcançou o **Nível {new_level}**!",
                    color=discord.Color.brand_green()
                )
                embed.set_thumbnail(url=message.author.display_avatar.url)
                await channel.send(view=components_v2(embed))

        except Exception as error:
            print(f"Erro ao adicionar XP para {user_id}: {error}")

    @app_commands.command(name="rank", description="Veja o seu nível ou o de outro membro")
    async def rank(self, interaction: discord.Interaction, membro: discord.Member = None):
        if interaction.guild is None:
            embed = discord.Embed(title="❌ Erro", description="Este comando só funciona em servidores.", color=discord.Color.red())
            return await interaction.response.send_message(view=components_v2(embed), ephemeral=True)
        if self.pool is None:
            embed = discord.Embed(title="❌ Erro", description="O sistema de XP está indisponível.", color=discord.Color.red())
            return await interaction.response.send_message(view=components_v2(embed), ephemeral=True)

        target = membro or interaction.user
        if target.bot:
            embed = discord.Embed(title="❌ Erro", description="Bots não recebem XP.", color=discord.Color.red())
            return await interaction.response.send_message(view=components_v2(embed), ephemeral=True)

        row = await self.pool.fetchrow(
            "SELECT xp, level FROM hakari_levels WHERE guild_id = $1 AND user_id = $2",
            interaction.guild.id, target.id
        )

        xp = row["xp"] if row else 0
        level = row["level"] if row else 0
        next_level_xp = self.get_next_level_xp(level) if level < 160 else MAX_XP

        rank_pos = await self.pool.fetchval(
            "SELECT COUNT(*) FROM hakari_levels WHERE guild_id = $1 AND xp > $2",
            interaction.guild.id, xp
        )
        pos = rank_pos + 1 if rank_pos is not None else 1

        embed = discord.Embed(
            title=f"Rank de {target.display_name}",
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Nível", value=f"**{level}**", inline=True)
        if xp >= MAX_XP:
            embed.add_field(name="XP", value=f"**{xp}** (MÁX)", inline=True)
        else:
            embed.add_field(name="XP", value=f"**{xp}** / {next_level_xp}", inline=True)
        embed.add_field(name="Posição", value=f"#{pos}", inline=True)

        await interaction.response.send_message(view=components_v2(embed))

    @app_commands.command(name="top", description="Veja o ranking de XP do servidor")
    async def top(self, interaction: discord.Interaction):
        if interaction.guild is None:
            embed = discord.Embed(title="❌ Erro", description="Este comando só funciona em servidores.", color=discord.Color.red())
            return await interaction.response.send_message(view=components_v2(embed), ephemeral=True)
        if self.pool is None:
            embed = discord.Embed(title="❌ Erro", description="O sistema de XP está indisponível.", color=discord.Color.red())
            return await interaction.response.send_message(view=components_v2(embed), ephemeral=True)

        rows = await self.pool.fetch(
            "SELECT user_id, xp, level FROM hakari_levels WHERE guild_id = $1 ORDER BY xp DESC LIMIT 10",
            interaction.guild.id
        )

        if not rows:
            embed = discord.Embed(
                title="🏆 Ranking de XP",
                description="Ninguém tem XP neste servidor ainda.",
                color=discord.Color.gold()
            )
            return await interaction.response.send_message(view=components_v2(embed))

        description = ""
        for idx, row in enumerate(rows, start=1):
            description += f"**{idx}.** <@{row['user_id']}> — **Lvl {row['level']}** ({row['xp']} XP)\n"

        embed = discord.Embed(
            title="🏆 Ranking de XP",
            description=description,
            color=discord.Color.gold()
        )

        await interaction.response.send_message(view=components_v2(embed))

    @app_commands.command(name="adicionar_xp", description="Adiciona XP a um membro (Administradores)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(membro="Membro que receberá o XP", quantidade="Quantidade de XP (1 a 160000)")
    async def adicionar_xp(self, interaction: discord.Interaction, membro: discord.Member, quantidade: app_commands.Range[int, 1, 160000]):
        if interaction.guild is None:
            embed = discord.Embed(title="❌ Erro", description="Este comando só funciona em servidores.", color=discord.Color.red())
            return await interaction.response.send_message(view=components_v2(embed), ephemeral=True)
        if self.pool is None:
            embed = discord.Embed(title="❌ Erro", description="O sistema de XP está indisponível.", color=discord.Color.red())
            return await interaction.response.send_message(view=components_v2(embed), ephemeral=True)
        if membro.bot:
            embed = discord.Embed(title="❌ Erro", description="Bots não recebem XP.", color=discord.Color.red())
            return await interaction.response.send_message(view=components_v2(embed), ephemeral=True)

        row = await self.pool.fetchrow("SELECT xp, level FROM hakari_levels WHERE guild_id = $1 AND user_id = $2", interaction.guild.id, membro.id)
        current_xp = row["xp"] if row else 0
        
        new_xp, new_level = await self.set_user_xp(interaction.guild.id, membro.id, current_xp + quantidade)
        
        embed = discord.Embed(
            title="✅ XP Adicionado",
            description=f"Foi adicionado **{quantidade} XP** para {membro.mention}.\nAgora ele possui **{new_xp} XP** (Nível {new_level}).",
            color=discord.Color.green()
        )
        await interaction.response.send_message(view=components_v2(embed))

    @app_commands.command(name="remover_xp", description="Remove XP de um membro (Administradores)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(membro="Membro que perderá o XP", quantidade="Quantidade de XP (1 a 160000)")
    async def remover_xp(self, interaction: discord.Interaction, membro: discord.Member, quantidade: app_commands.Range[int, 1, 160000]):
        if interaction.guild is None:
            embed = discord.Embed(title="❌ Erro", description="Este comando só funciona em servidores.", color=discord.Color.red())
            return await interaction.response.send_message(view=components_v2(embed), ephemeral=True)
        if self.pool is None:
            embed = discord.Embed(title="❌ Erro", description="O sistema de XP está indisponível.", color=discord.Color.red())
            return await interaction.response.send_message(view=components_v2(embed), ephemeral=True)
        if membro.bot:
            embed = discord.Embed(title="❌ Erro", description="Bots não recebem XP.", color=discord.Color.red())
            return await interaction.response.send_message(view=components_v2(embed), ephemeral=True)

        row = await self.pool.fetchrow("SELECT xp, level FROM hakari_levels WHERE guild_id = $1 AND user_id = $2", interaction.guild.id, membro.id)
        current_xp = row["xp"] if row else 0
        
        new_xp, new_level = await self.set_user_xp(interaction.guild.id, membro.id, current_xp - quantidade)
        
        embed = discord.Embed(
            title="🔻 XP Removido",
            description=f"Foi removido **{quantidade} XP** de {membro.mention}.\nAgora ele possui **{new_xp} XP** (Nível {new_level}).",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(view=components_v2(embed))

    @app_commands.command(name="reset", description="Reseta TODO o XP de TODOS os membros do servidor (Administradores)")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset(self, interaction: discord.Interaction):
        if interaction.guild is None:
            embed = discord.Embed(title="❌ Erro", description="Este comando só funciona em servidores.", color=discord.Color.red())
            return await interaction.response.send_message(view=components_v2(embed), ephemeral=True)
        
        embed = discord.Embed(
            title="⚠️ Confirmação de Reset",
            description="Você tem certeza que deseja **RESETAR TODO O XP** de **TODOS** os usuários deste servidor? Esta ação **não pode ser desfeita**.",
            color=discord.Color.orange()
        )
        view = ResetConfirmView(self, interaction.guild.id)
        await interaction.response.send_message(view=components_v2(embed, view=view), ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Levels(bot))
