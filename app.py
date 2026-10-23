import asyncio
import os
import random
import sys
import traceback
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands, tasks

from keep_alive import keep_alive


# ============================================================
# CONFIGURAÇÕES
# ============================================================

TOKEN = os.getenv("TOKEN", "").strip()
APPLICATION_ID_TEXT = os.getenv("APPLICATION_ID", "").strip()

COMMAND_PREFIX = ","

BASE_DIR = Path(__file__).resolve().parent
COGS_DIR = BASE_DIR / "cogs"


# ============================================================
# VALIDAÇÃO DAS VARIÁVEIS
# ============================================================

def get_application_id() -> int:
    if not APPLICATION_ID_TEXT:
        raise RuntimeError(
            "A variável APPLICATION_ID não foi configurada no Render."
        )

    try:
        return int(APPLICATION_ID_TEXT)
    except ValueError as error:
        raise RuntimeError(
            "A variável APPLICATION_ID precisa conter somente números."
        ) from error


APPLICATION_ID = get_application_id()


# ============================================================
# INTENTS
# ============================================================

intents = discord.Intents.all()


# ============================================================
# CLASSE PRINCIPAL DO BOT
# ============================================================

class HakariBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix=COMMAND_PREFIX,
            intents=intents,
            application_id=APPLICATION_ID,
            help_command=None,
            case_insensitive=True,
        )
        self.guild_command_sync_attempted = False
        self.guild_command_sync_semaphore = asyncio.Semaphore(5)

    async def setup_hook(self) -> None:
        """
        Executado automaticamente antes do bot ficar pronto.

        Aqui são carregadas as Cogs, registradas as Views persistentes
        e sincronizados os slash commands.
        """

        print("=" * 60, flush=True)
        print("🔧 setup_hook iniciado.", flush=True)
        print("=" * 60, flush=True)

        await self.load_all_cogs()
        await self.sync_slash_commands()

    async def load_all_cogs(self) -> None:
        print(f"📁 Procurando Cogs em: {COGS_DIR}...", flush=True)
        print(f"📁 Pasta existe: {COGS_DIR.is_dir()}", flush=True)

        if not COGS_DIR.is_dir():
            print(
                "❌ A pasta 'cogs' não foi encontrada!",
                flush=True,
            )
            return

        cog_files = sorted(
            file
            for file in COGS_DIR.iterdir()
            if file.is_file()
            and file.suffix == ".py"
            and not file.name.startswith("__")
            and file.stem != "components_v2"
        )

        if not cog_files:
            print(
                "⚠️ Nenhum arquivo Python foi encontrado na pasta cogs!",
                flush=True,
            )
            return

        print(
            "📄 Cogs encontradas: "
            + ", ".join(file.name for file in cog_files),
            flush=True,
        )

        loaded_count = 0
        failed_count = 0

        for file in cog_files:
            extension_name = f"cogs.{file.stem}"

            try:
                await self.load_extension(extension_name)

                loaded_count += 1

                print(
                    f"✅ Cog carregada: {extension_name}!",
                    flush=True,
                )

            except commands.ExtensionAlreadyLoaded:
                print(
                    f"⚠️ Cog já estava carregada: {extension_name}!",
                    flush=True,
                )

            except commands.NoEntryPointError:
                failed_count += 1

                print(
                    f"❌ {extension_name} não possui a função "
                    "`async def setup(bot)`.",
                    flush=True,
                )

            except commands.ExtensionFailed as error:
                failed_count += 1

                original_error = error.original

                print(
                    f"❌ Erro dentro da Cog {extension_name}: "
                    f"{type(original_error).__name__}: {original_error}",
                    flush=True,
                )

                traceback.print_exception(
                    type(original_error),
                    original_error,
                    original_error.__traceback__,
                )

            except Exception as error:
                failed_count += 1

                print(
                    f"❌ Erro ao carregar {extension_name}: "
                    f"{type(error).__name__}: {error}",
                    flush=True,
                )

                traceback.print_exc()

        print("-" * 60, flush=True)
        print(
            f"📦 Resultado: {loaded_count} carregadas e "
            f"{failed_count} com erro.",
            flush=True,
        )
        print(
            f"📦 Cogs ativas: {list(self.cogs.keys())}",
            flush=True,
        )
        print("-" * 60, flush=True)

    async def sync_slash_commands(self) -> None:
        try:
            synced_commands = await self.tree.sync()

            print(
                f"✅ {len(synced_commands)} slash commands "
                "sincronizados globalmente.",
                flush=True,
            )

            if synced_commands:
                command_names = ", ".join(
                    f"/{command.name}"
                    for command in synced_commands
                )

                print(
                    f"📋 Comandos sincronizados: {command_names}",
                    flush=True,
                )

        except discord.Forbidden as error:
            print(
                "❌ O Discord negou a sincronização dos comandos. "
                "Confira se o bot foi convidado com os escopos "
                "`bot` e `applications.commands`.",
                flush=True,
            )
            print(f"Detalhes: {error}", flush=True)

        except discord.HTTPException as error:
            print(
                f"❌ Erro HTTP ao sincronizar comandos: {error}",
                flush=True,
            )

        except Exception as error:
            print(
                f"❌ Erro inesperado ao sincronizar comandos: "
                f"{type(error).__name__}: {error}",
                flush=True,
            )

            traceback.print_exc()

    async def sync_guild_commands(self, guild: discord.Guild) -> list[app_commands.AppCommand]:
        guild_object = discord.Object(id=guild.id)
        self.tree.clear_commands(guild=guild_object)
        self.tree.copy_global_to(guild=guild_object)
        async with self.guild_command_sync_semaphore:
            return await self.tree.sync(guild=guild_object)

    async def sync_commands_to_all_guilds(self) -> tuple[int, int]:
        guilds = list(self.guilds)
        results = await asyncio.gather(
            *(self.sync_guild_commands(guild) for guild in guilds),
            return_exceptions=True,
        )
        synced_guilds = 0
        for guild, result in zip(guilds, results):
            if isinstance(result, BaseException):
                print(
                    f"⚠️ Não foi possível sincronizar comandos em {guild.id}: {result}",
                    flush=True,
                )
            else:
                synced_guilds += 1
        return synced_guilds, len(guilds)

    async def sync_all_slash_commands(self) -> tuple[int, int, int]:
        global_commands = await self.tree.sync()
        synced_guilds, total_guilds = await self.sync_commands_to_all_guilds()
        return len(global_commands), synced_guilds, total_guilds


# ============================================================
# INSTÂNCIA DO BOT
# ============================================================

bot = HakariBot()


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
) -> None:
    original_error = getattr(error, "original", error)
    command_name = (
        interaction.command.qualified_name
        if interaction.command is not None
        else "desconhecido"
    )
    print(
        f"Erro em comando slash /{command_name} "
        f"(guild={interaction.guild_id}, user={interaction.user.id}): "
        f"{type(original_error).__name__}: {original_error}",
        flush=True,
    )
    if isinstance(original_error, discord.HTTPException):
        response = getattr(original_error, "response", None)
        headers = getattr(response, "headers", {})
        request_info = getattr(response, "request_info", None)
        method = getattr(request_info, "method", None)
        url = getattr(request_info, "url", None)
        route = getattr(url, "path", None)
        retry_after = headers.get("Retry-After")
        bucket = headers.get("X-RateLimit-Bucket")
        if method or route or retry_after or bucket:
            print(
                f"Detalhes HTTP do comando /{command_name}: "
                f"method={method or 'indisponível'}, "
                f"route={route or 'indisponível'}, "
                f"retry_after={retry_after or 'indisponível'}, "
                f"bucket={bucket or 'indisponível'}",
                flush=True,
            )
    traceback.print_exception(
        type(original_error),
        original_error,
        original_error.__traceback__,
    )


# ============================================================
# STATUS ROTATIVO

@tasks.loop(seconds=35)
async def trocar_status() -> None:
    try:
        # Bot conta quantos arquivos tem na pasta cogs
        total_cogs = len([f for f in os.listdir("cogs") if f.endswith(".py")])

        # A lista fica aqui dentro para calcular a latência atual a cada 35s
        status_atualizados = [
            "Hakari Bot V2.19.2",
            "Desenvolvido por Salvador",
            f"Latência: {round(bot.latency * 1000)}ms",
            f"Atualmente tendo {total_cogs} sistemas ativos",
            "Use /menu para me configurar! As alterações valem apenas para o seu servidor",
            "Minha linguagem é PYTHON, e a sua?",
            "Sim, tudo tem que configurar no /menu primeiro para depooooois usar 😭",
            "A música favorita do meu desenvolvedor é Flamewall de Camellia, e a sua?"
        ]

        await bot.change_presence(
            status=discord.Status.idle,
            activity=discord.CustomActivity(
                name=random.choice(status_atualizados)
            ),
        )

    except discord.HTTPException as error:
        print(
            f"⚠️ Não foi possível trocar o status: {error}",
            flush=True,
        )

    except Exception as error:
        print(
            f"⚠️ Erro inesperado ao trocar status: "
            f"{type(error).__name__}: {error}",
            flush=True,
        )



@trocar_status.before_loop
async def antes_de_trocar_status() -> None:
    await bot.wait_until_ready()


@trocar_status.error
async def erro_no_status(error: BaseException) -> None:
    print(
        f"❌ Erro no loop de status: "
        f"{type(error).__name__}: {error}",
        flush=True,
    )


# ============================================================
# EVENTOS
# ============================================================

@bot.event
async def on_ready() -> None:
    if bot.user is None:
        return

    if not bot.guild_command_sync_attempted:
        bot.guild_command_sync_attempted = True
        synced_guilds, total_guilds = await bot.sync_commands_to_all_guilds()
        print(
            f"🔁 Comandos sincronizados em {synced_guilds}/{total_guilds} servidores.",
            flush=True,
        )

    print("=" * 60, flush=True)
    print(
        f"✅ Logado como {bot.user} | ID: {bot.user.id}",
        flush=True,
    )
    print(
        f"🌐 Conectado em {len(bot.guilds)} servidor(es).",
        flush=True,
    )
    print(
        f"📦 Cogs carregadas: {len(bot.cogs)}",
        flush=True,
    )
    print(
        f"⚡ Latência: {round(bot.latency * 1000)} ms",
        flush=True,
    )
    print("=" * 60, flush=True)

    if not trocar_status.is_running():
        trocar_status.start()
        print("🔄 Sistema de status iniciado.", flush=True)


@bot.event
async def on_guild_join(guild: discord.Guild) -> None:
    try:
        synced_commands = await bot.sync_guild_commands(guild)
    except discord.HTTPException as error:
        print(
            f"⚠️ Não foi possível sincronizar comandos em {guild.id}: {error}",
            flush=True,
        )
        return
    print(
        f"✅ {len(synced_commands)} comandos sincronizados em {guild.id}.",
        flush=True,
    )


@bot.event
async def on_connect() -> None:
    print(
        "🔌 Conexão com o Gateway do Discord estabelecida.",
        flush=True,
    )


@bot.event
async def on_disconnect() -> None:
    print(
        "⚠️ O bot foi desconectado do Gateway. "
        "O discord.py tentará reconectar automaticamente.",
        flush=True,
    )


@bot.event
async def on_resumed() -> None:
    print(
        "♻️ Sessão com o Discord retomada.",
        flush=True,
    )


@bot.event
async def on_command_error(
    ctx: commands.Context,
    error: commands.CommandError,
) -> None:
    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, commands.MissingPermissions):
        await ctx.send(
            "❌ Você não possui permissão para usar esse comando."
        )
        return

    if isinstance(error, commands.BotMissingPermissions):
        await ctx.send(
            "❌ Eu não possuo as permissões necessárias para isso."
        )
        return

    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            f"❌ Está faltando o argumento `{error.param.name}`."
        )
        return

    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(
            f"⏳ Aguarde {error.retry_after:.1f} segundos "
            "para usar esse comando novamente."
        )
        return

    original_error = getattr(error, "original", error)

    print(
        f"❌ Erro no comando de prefixo "
        f"{getattr(ctx.command, 'qualified_name', 'desconhecido')}: "
        f"{type(original_error).__name__}: {original_error}",
        flush=True,
    )

    traceback.print_exception(
        type(original_error),
        original_error,
        original_error.__traceback__,
    )


@bot.event
async def on_error(
    event: str,
    *args,
    **kwargs,
) -> None:
    print(
        f"❌ Erro não tratado no evento: {event}",
        flush=True,
    )

    exc_type, exc_value, exc_traceback = sys.exc_info()

    traceback.print_exception(
        exc_type,
        exc_value,
        exc_traceback,
    )


# ============================================================
# INICIALIZAÇÃO
# ============================================================

async def main() -> None:
    if not TOKEN:
        raise RuntimeError(
            "A variável TOKEN não foi configurada no Render."
        )

    print("🚀 Inicializando Hakari...", flush=True)
    print(f"📁 Diretório principal: {BASE_DIR}", flush=True)
    print(f"📁 Diretório das Cogs: {COGS_DIR}", flush=True)
    print(f"🆔 Application ID: {APPLICATION_ID}", flush=True)

    print("🌐 Iniciando servidor Flask...", flush=True)
    keep_alive(bot)

    print("🤖 Iniciando conexão com o Discord...", flush=True)

    try:
        async with bot:
            await bot.start(TOKEN)

    except discord.LoginFailure as error:
        print(
            "❌ O Discord recusou o token do bot.",
            flush=True,
        )
        raise error

    except discord.PrivilegedIntentsRequired as error:
        print(
            "❌ Os Intents privilegiados não estão habilitados no "
            "Discord Developer Portal.",
            flush=True,
        )
        raise error

    except Exception as error:
        print(
            f"❌ Erro fatal ao iniciar o bot: "
            f"{type(error).__name__}: {error}",
            flush=True,
        )

        traceback.print_exc()
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        print(
            "⚠️ Hakari encerrado manualmente.",
            flush=True,
        )

    except Exception as error:
        print(
            f"💥 O processo foi encerrado: "
            f"{type(error).__name__}: {error}",
            flush=True,
        )
