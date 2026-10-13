import discord
from discord.ext import commands
from discord import app_commands
import random
import time


cooldowns = {}

BOT_DEVELOPER_ID = 1543385262984396852


def has_role(member: discord.Member, roles: set[int]):
    return any(role.id in roles for role in member.roles)


def is_owner(member: discord.Member):
    return member.id == member.guild.owner_id


async def is_bot_owner(bot: commands.Bot, user_id: int):
    return user_id == BOT_DEVELOPER_ID


async def tomate_core(
    channel,
    author: discord.Member,
    send,
    target_user: discord.Member | None = None,
    settings: dict | None = None,
):
    settings = settings or {}
    target_pick_roles = set(settings.get("target_pick_roles", []))
    reduced_cooldown_roles = set(settings.get("reduced_cooldown_roles", []))
    default_cooldown = int(settings.get("default_cooldown", 7))
    reduced_cooldown = int(settings.get("reduced_cooldown", 5))

    # Só quem tem o cargo pode escolher um alvo específico
    if target_user is not None and not has_role(author, target_pick_roles):
        await send(
            "tu precisa do cargo de boosters pra escolher um alvo 😭"
        )
        return

    cooldown_time = (
        reduced_cooldown
        if has_role(author, reduced_cooldown_roles)
        else default_cooldown
    )

    if cooldown_time > 0:
        cooldown_key = (author.guild.id, author.id)
        last_used = cooldowns.get(cooldown_key)

        if last_used:
            remaining = cooldown_time - (time.time() - last_used)

            if remaining > 0:
                seconds = int(remaining)

                await send(
                    f"⏳ você está jogando tomates demais em pouco tempo! "
                    f"tente novamente em **{seconds}** segundos. "
                    f"sabia que boosters podem jogar tomates a cada 5 segundos?"
                )
                return

        cooldowns[cooldown_key] = time.time()

    # Alvo específico
    if target_user is not None:

        messages = [
            msg async for msg in channel.history(limit=5)
            if not msg.author.bot and msg.author.id == target_user.id
        ]

        if not messages:
            await send(
                f"não achei mensagem recente de {target_user.mention} "
                f"pra tacar tomate"
            )
            return

        selected_msg = random.choice(messages)
        target = selected_msg.author

    # Alvo aleatório
    else:

        messages = [
            msg async for msg in channel.history(limit=5)
            if not msg.author.bot
        ]

        if not messages:
            await send("não achei mensagem pra tacar tomate")
            return

        selected_msg = random.choice(messages)
        target = selected_msg.author

    # Dono do servidor não pode ser atingido
    if isinstance(target, discord.Member) and is_owner(target):
        try:
            await selected_msg.add_reaction("🍅")

            await send("taquei tomate no dono do servidor haha sou muito mau")

        except discord.Forbidden:
            await send(
                "não tenho permissão pra reagir mensagens pô"
            )

        return

    chance = random.randint(1, 100)

    if chance <= 35:

        await send(
            f"(**CHANCE: 35%**) "
            f"{target.mention} desviou do tomate!"
        )
        return

    elif chance <= 45:

        await send(
            f"(**CHANCE: 10%**): "
            f"{target.mention} pegou o tomate no ar e jogou de volta "
            f"em {author.mention}!"
        )
        return

    elif chance <= 50:

        await send(
            f"(**CHANCE: 5%**): "
            f"{target.mention} o tomate simplesmente "
            f"foi aniquilado pelo conceito existencial da física "
            f"perto de {target.mention}"
        )
        return

    elif chance <= 75:

        await send(
            "errei o tomate kkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkj"
        )
        return

    elif chance <= 51:

        await send(
            f"(**CHANCE: 1%**) o tomate foi cortado ao meio pelos pensamentos de {target.mention} (caralho megamente)"
        )

    else:

        try:
            await selected_msg.add_reaction("🍅")

            if target.id == author.id:

                await send(
                    f"{author.mention} tentou jogar um tomate e acabou "
                    f"acertando a si mesmo "
                    f"KKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKJ"
                )

            else:

                await send(
                    f"{target.mention} foi atingido pelo tomate"
                )

        except discord.Forbidden:

            await send(
                "CADE MINHA PERMISSÃO DE REAGIR AS MENSAGENS "
                "PORRAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
            )

        except Exception as e:

            await send(
                f"erro ao lançar tomate: `{e}`"
            )


class Tomate(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    def settings_for(self, guild_id: int) -> dict:
        menu = self.bot.get_cog("Menu")
        return menu.config.get(str(guild_id), {}).get("settings", {}) if menu else {}

    @commands.Cog.listener()
    async def on_raw_reaction_add(
        self,
        payload: discord.RawReactionActionEvent
    ):

        if str(payload.emoji) != "🍅":
            return

        if self.bot.user and payload.user_id == self.bot.user.id:
            return

        channel = self.bot.get_channel(payload.channel_id)

        if channel is None:
            return

        try:
            message = await channel.fetch_message(
                payload.message_id
            )

        except discord.NotFound:
            return

        except discord.Forbidden:
            return

        except Exception:
            return

        guild = self.bot.get_guild(payload.guild_id)

        menu = self.bot.get_cog("Menu")
        block_tomatoes = (
            menu.get_value(guild.id, "block_owner_tomatoes", False)
            if menu and guild
            else False
        )
        if block_tomatoes and guild is not None:

            bot_owner = await is_bot_owner(
                self.bot,
                message.author.id
            )

            server_owner = message.author.id == guild.owner_id

            if bot_owner or server_owner:

                try:
                    await message.remove_reaction(
                        payload.emoji,
                        discord.Object(id=payload.user_id)
                    )

                except discord.Forbidden:
                    pass

                except Exception:
                    pass

                return

        # Só processa tomates em mensagens do próprio bot
        if message.author.id != self.bot.user.id:
            return

        try:
            await message.remove_reaction(
                payload.emoji,
                discord.Object(id=payload.user_id)
            )

            await channel.send(
                f"sub5 <@{payload.user_id}> tacando tomate no true mogger🤣🤣🤣"
            )

        except discord.Forbidden:

            await channel.send(
                "CADÊ MINHA PERMISSÃO DE TIRAR REAÇÃO "
                "PORRAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
            )

    @app_commands.command(
        name="tomate",
        description="Lança um tomate em uma mensagem aleatória ou em alguém específico"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        alvo="Usuário que você quer tacar tomate"
    )
    async def tomate(
        self,
        interaction: discord.Interaction,
        alvo: discord.Member | None = None
    ):

        async def send(msg):

            if interaction.response.is_done():
                await interaction.followup.send(msg)

            else:
                await interaction.response.send_message(msg)

        await tomate_core(
            interaction.channel,
            interaction.user,
            send,
            alvo,
            self.settings_for(interaction.guild_id),
        )

    @app_commands.command(
        name="bloquear_tomates",
        description="Bloqueia tomates nas mensagens do dono do servidor e do dono do bot"
    )
    async def bloquear_tomates_cmd(
        self,
        interaction: discord.Interaction
    ):

        guild = interaction.guild

        if guild is None:

            await interaction.response.send_message(
                "esse comando só funciona em servidores.",
                ephemeral=True
            )
            return

        is_server_owner = is_owner(interaction.user)

        is_application_owner = await is_bot_owner(
            self.bot,
            interaction.user.id
        )

        if not is_server_owner and not is_application_owner:

            await interaction.response.send_message(
                "só o dono do servidor ou o dono do bot pode usar este comando.",
                ephemeral=True
            )
            return

        menu = self.bot.get_cog("Menu")
        if menu is None:
            return await interaction.response.send_message(
                "O painel de configurações não está disponível.", ephemeral=True
            )
        bloquear_tomates = not menu.get_value(
            guild.id, "block_owner_tomatoes", False
        )
        await menu.set_value(guild.id, "block_owner_tomatoes", bloquear_tomates)

        status = (
            "ativado"
            if bloquear_tomates
            else "desativado"
        )

        await interaction.response.send_message(
            f"🍅 bloqueio de tomates **{status}**",
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Tomate(bot))
