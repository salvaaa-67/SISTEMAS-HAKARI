import asyncio
import json
import os
import re
import shutil
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

import aiohttp
import asyncpg
import discord
from discord import app_commands
from discord.ext import commands

from .components_v2 import ComponentsV2View, components_v2
from .quotes import (
    DEFAULT_QUOTE_STYLE,
    FONT_URLS,
    build_quote_image,
    fetch_quote_font,
    quote_style_with_defaults,
)


DEVELOPER_ID = 1344736884089426022
RANKING_INTRO_DESCRIPTION_MAX_LENGTH = 1500
MAX_AI_AUDIO_VOICES = 25

FISH_PUBLIC_VOICE_SPECS = (
    {
        "key": "hakari",
        "label": "Hakari (Jujutsu Kaisen) [Padrão]",
        "id": "5baee412f62d4bd89a0246d3124a97d8",
        "queries": ("Hakari",),
        "match_terms": ("hakari",),
        "default": True,
    },
    {
        "key": "neymar",
        "label": "Neymar (Jogador de futebol)",
        "id": "2bd0cd1a49474aeab129894f4512e8a6",
        "queries": ("Neymar",),
        "match_terms": ("neymar",),
    },
    {
        "key": "sukuna",
        "label": "Sukuna (Jujutsu Kaisen)",
        "id": "3a164c7d00b2437682042ebd01755521",
        "queries": ("Sukuna",),
        "match_terms": ("sukuna",),
    },
    {
        "key": "satoru_gojo",
        "label": "Gojo (Jujutsu Kaisen)",
        "id": "96a2c896ed7846848cdd83e484b23eb3",
        "queries": ("Gojo", "Satoru Gojo"),
        "match_terms": ("gojo",),
    },
    {
        "key": "verity",
        "label": "Verity (Minecraft Mod)",
        "id": "8d21b053e2804e2a890e1cf62f267b6f",
        "queries": ("Verity",),
        "match_terms": ("verity",),
    },
    {
        "key": "luffy",
        "label": "Luffy (One Piece)",
        "id": "dbe7bddfe9c04a72a4fd566206099ae4",
        "queries": ("Luffy",),
        "match_terms": ("luffy",),
    },
    {
        "key": "zoro",
        "label": "Zoro (One Piece)",
        "id": "17ad4763428044f99c1ae7d1743294dd",
        "queries": ("Zoro",),
        "match_terms": ("zoro",),
    },
    {
        "key": "patrick_jane",
        "label": "Patrick Jane (The Mentalist)",
        "id": "1a975db6f1be40f4bed2bcc5e495301d",
        "queries": ("Patrick Jane", "Patrick"),
        "match_terms": ("patrick",),
    },
    {
        "key": "darth_vader",
        "label": "Darth Vader (Star Wars)",
        "id": "ecbaa33bef134b0580fa2d438202aeae",
        "queries": ("Darth Vader", "Vader"),
        "match_terms": ("vader",),
    },
    {
        "key": "goku",
        "label": "Goku (Dragon Ball)",
        "id": "dece2a4c7f8d476b8da3c3a6707298d4",
        "queries": ("Goku",),
        "match_terms": ("goku",),
    },
    {
        "key": "cristiano_ronaldo",
        "label": "Cristiano Ronaldo (Jogador de futebol)",
        "id": "f800d4c9e73b4dbd849be082315629c4",
        "queries": ("Cristiano Ronaldo", "Ronaldo"),
        "match_terms": ("cristiano", "ronaldo"),
    },
    {
        "key": "messi",
        "label": "Messi (Jogador de futebol)",
        "id": "5e310993c0134ce2aa96f12d7d05aeb2",
        "queries": ("Messi",),
        "match_terms": ("messi",),
    },
    {
        "key": "itachi_uchiha",
        "label": "Itachi Uchiha (Naruto)",
        "id": "5a6cb585b094dedb241365e7e271973",
        "queries": ("Itachi Uchiha", "Itachi"),
        "match_terms": ("itachi",),
    },
    {
        "key": "sasuke_uchiha",
        "label": "Sasuke Uchiha (Naruto)",
        "id": "aedb06f6daa84a1db52c7479c7235910",
        "queries": ("Sasuke Uchiha", "Sasuke"),
        "match_terms": ("sasuke",),
    },
    {
        "key": "light_yagami",
        "label": "Light Yagami (Death Note)",
        "id": "567a99893e144be1a4eb89b55eb10234",
        "queries": ("Light Yagami", "Light"),
        "match_terms": ("light", "yagami"),
    },
    {
        "key": "denji",
        "label": "Denji (Chainsaw Man)",
        "id": "b2966fe298c342a3b6fe6c575ea9c6a6",
        "queries": ("Denji",),
        "match_terms": ("denji",),
    },
    {
        "key": "power",
        "label": "Power (Chainsaw Man)",
        "id": "9e93341200f042b2a7c46fdb5e8bac4e",
        "queries": ("Power Chainsaw Man", "Power"),
        "match_terms": ("power",),
    },
    {
        "key": "reze",
        "label": "Reze (Chainsaw Man)",
        "id": "159479ec69e74135a0a56ed9d1c7e48d",
        "queries": ("Reze",),
        "match_terms": ("reze",),
    },
    {
        "key": "saitama",
        "label": "Saitama (One Punch Man)",
        "id": "c5062a07fda44449a6241a037ecddd25",
        "queries": ("Saitama",),
        "match_terms": ("saitama",),
    },
    {
        "key": "marin_kitagawa",
        "label": "Marin Kitagawa (My Dress Up Darling)",
        "id": "962d6c55da8742fe8f82b6a2556c90ad",
        "queries": ("Marin Kitagawa", "Marin"),
        "match_terms": ("marin",),
    },
)

FALLBACK_MENU_BANNER = "https://i.postimg.cc/kgv8f49w/banner-hakari-bot.png"
MENU_WEBSITE_URL = "https://sistemas-hakari-igw0.onrender.com/"
CONFIG_PATH = Path(__file__).resolve().parent.parent / "data" / "guild_config.json"
WELCOME_ASSETS_DIR = CONFIG_PATH.parent / "welcome_assets"
MODULES = {
    "admin": "Moderação",
    "afk": "AFK",
    "boost": "Boost",
    "musica": "Música",
    "quotes": "Quotes",
    "resenha": "Resenha",
    "sohakari": "So Hakari",
    "tomate": "Tomates",
    "utilidades": "Utilidades",
    "welcome": "Boas-vindas",
    "insta": "Instagram",
    "roblox": "Avatares Roblox",
    "ia_audio": "IA em áudio",
}

SETTINGS = {
    "admin": {
        "label": "Moderação",
        "description": "Configure o que acontece além da advertência.",
        "items": {
            "warn_additional_punishment": (
                "Punição adicional da advertência",
                "choice",
            ),
            "warn_timeout_minutes": (
                "Duração do silenciamento (minutos)",
                "number",
            ),
        },
    },
    "boost": {
        "label": "Sistema de Boost",
        "description": (
            "Configure acessos e posições dos cargos. O cargo do bot deve ficar "
            "acima do limite superior."
        ),
        "items": {
            "booster_role": ("Cargo que dá acesso de booster", "role"),
            "vip_full_role": ("Cargo VIP com acesso à família", "role"),
            "vip_personal_role": ("Cargo VIP com acesso ao cargo pessoal", "role"),
            "role_position_upper": ("Limite superior dos cargos criados", "role"),
            "role_position_lower": ("Referência abaixo dos cargos pessoais", "role"),
            "family_position_lower": ("Referência abaixo dos cargos da família", "role"),
            "repair_below_role": ("Cargo que aciona o ajuste automático", "role"),
            "family_member_limit": ("Máximo de pessoas por família", "number"),
        },
    },
    "tomate": {
        "label": "Sistema de Tomates",
        "description": "Defina os cargos com vantagens e ajuste os intervalos entre ações.",
        "items": {
            "target_pick_roles": ("Cargos que escolhem o alvo", "roles"),
            "reduced_cooldown_roles": ("Cargos com intervalo reduzido", "roles"),
            "default_cooldown": ("Intervalo padrão em segundos", "number"),
            "reduced_cooldown": ("Intervalo reduzido em segundos", "number"),
            "block_owner_tomatoes": ("Bloquear tomates no dono", "toggle"),
        },
    },
    "welcome": {
        "label": "Boas-vindas",
        "description": "Escolha o canal e personalize o texto, as menções e as imagens de entrada.",
        "items": {
            "welcome_channel": ("Canal de boas-vindas", "channel"),
            "welcome_ping_role": ("Cargo para ping", "role"),
            "welcome_ping_member": ("Mencionar o novo membro", "toggle"),
            "welcome_text": ("Textos da embed", "welcome_text"),
            "welcome_assets": ("Thumbnail, imagem e ícone", "welcome_assets"),
        },
    },
    "insta": {
        "label": "Instagram fictício",
        "description": "Selecione onde as publicações de imagem serão recebidas e exibidas.",
        "items": {
            "insta_channel": ("Canal dos posts", "channel"),
        },
    },
    "quotes": {
        "label": "Quotes",
        "description": "Configure o canal e personalize as imagens de Quotes.",
        "items": {
            "quotes_channel": ("Canal dos Quotes", "channel"),
            "quotes_style": ("Estilo da imagem", "quotes_style"),
        },
    },
    "roblox": {
        "label": "Avatares Roblox",
        "description": "Escolha o canal onde os avatares consultados serão publicados.",
        "items": {
            "roblox_channel": ("Canal das skins Roblox", "channel"),
        },
    },
    "ranking_call": {
        "label": "Ranking de call",
        "description": "Configure o canal e a aparência do ranking de tempo em chamadas.",
        "items": {
            "ranking_call_channel": ("Canal do ranking", "channel"),
            "ranking_call_intro": ("Embed de apresentação", "rank_intro"),
            "ranking_call_top": ("Embed do top 10", "rank_top"),
        },
    },
    "ranking_messages": {
        "label": "Ranking de mensagens",
        "description": "Configure o canal e a aparência do ranking de mensagens.",
        "items": {
            "ranking_messages_channel": ("Canal do ranking", "channel"),
            "ranking_messages_intro": ("Embed de apresentação", "rank_intro"),
            "ranking_messages_top": ("Embed do top 10", "rank_top"),
        },
    },
    "modules": {
        "label": "Módulos",
        "description": "Ative ou desative os recursos disponíveis para este servidor.",
        "items": {
            f"module_{module}": (f"Ativar {label}", "toggle")
            for module, label in MODULES.items()
            if module != "ia_audio"
        },
    },
    "ia_audio": {
        "label": "IA em áudio",
        "description": (
            "Escolha uma voz pronta específica da biblioteca licenciada do "
            "Fish Audio e ative respostas faladas quando mencionarem o bot."
        ),
        "items": {
            "module_ia_audio": ("Ativar respostas de IA em áudio", "toggle"),
            "ia_audio_voice_id": ("Escolher voz Fish Audio", "fish_voices"),
        },
    },
    "logs": {
        "label": "Registros",
        "description": (
            "Escolha o canal para receber ações do Registro de Auditoria. "
            "O bot precisa das permissões Ver registro de auditoria e "
            "Enviar mensagens/links de incorporação."
        ),
        "items": {
            "audit_log_channel": ("Canal de registros", "channel"),
        },
    },
}

AUDIT_ACTION_LABELS = {
    "guild_update": "servidor atualizado",
    "channel_create": "canal criado",
    "channel_update": "canal atualizado",
    "channel_delete": "canal excluído",
    "overwrite_create": "permissão de canal criada",
    "overwrite_update": "permissão de canal atualizada",
    "overwrite_delete": "permissão de canal removida",
    "kick": "membro expulso",
    "member_prune": "membros removidos por inatividade",
    "ban": "membro banido",
    "unban": "banimento removido",
    "member_update": "membro atualizado",
    "member_role_update": "cargos de membro atualizados",
    "member_move": "membro movido de canal de voz",
    "member_disconnect": "membro desconectado do canal de voz",
    "bot_add": "bot adicionado",
    "role_create": "cargo criado",
    "role_update": "cargo atualizado",
    "role_delete": "cargo excluído",
    "invite_create": "convite criado",
    "invite_update": "convite atualizado",
    "invite_delete": "convite excluído",
    "webhook_create": "webhook criado",
    "webhook_update": "webhook atualizado",
    "webhook_delete": "webhook excluído",
    "emoji_create": "emoji criado",
    "emoji_update": "emoji atualizado",
    "emoji_delete": "emoji excluído",
    "message_delete": "mensagem excluída",
    "message_bulk_delete": "mensagens excluídas em massa",
    "message_pin": "mensagem fixada",
    "message_unpin": "mensagem desafixada",
    "integration_create": "integração criada",
    "integration_update": "integração atualizada",
    "integration_delete": "integração removida",
    "stage_instance_create": "palco criado",
    "stage_instance_update": "palco atualizado",
    "stage_instance_delete": "palco encerrado",
    "sticker_create": "figurinha criada",
    "sticker_update": "figurinha atualizada",
    "sticker_delete": "figurinha excluída",
    "scheduled_event_create": "evento agendado criado",
    "scheduled_event_update": "evento agendado atualizado",
    "scheduled_event_delete": "evento agendado excluído",
    "thread_create": "tópico criado",
    "thread_update": "tópico atualizado",
    "thread_delete": "tópico excluído",
    "app_command_permission_update": "permissões de comandos atualizadas",
    "soundboard_sound_create": "som do soundboard criado",
    "soundboard_sound_update": "som do soundboard atualizado",
    "soundboard_sound_delete": "som do soundboard excluído",
    "automod_rule_create": "regra de AutoMod criada",
    "automod_rule_update": "regra de AutoMod atualizada",
    "automod_rule_delete": "regra de AutoMod excluída",
    "automod_block_message": "mensagem bloqueada pelo AutoMod",
    "automod_flag_message": "mensagem sinalizada pelo AutoMod",
    "automod_timeout_member": "membro silenciado pelo AutoMod",
    "automod_quarantine_user": "usuário colocado em quarentena pelo AutoMod",
    "onboarding_prompt_create": "pergunta de integração criada",
    "onboarding_prompt_update": "pergunta de integração atualizada",
    "onboarding_prompt_delete": "pergunta de integração excluída",
    "onboarding_create": "integração do servidor configurada",
    "onboarding_update": "integração do servidor atualizada",
    "home_settings_create": "configuração da página inicial criada",
    "home_settings_update": "configuração da página inicial atualizada",
}


def audit_action_label(action: discord.AuditLogAction) -> str:
    return AUDIT_ACTION_LABELS.get(
        action.name,
        action.name.replace("_", " "),
    )


BOOST_SETTING_DESCRIPTIONS = {
    "booster_role": "Quem tiver este cargo poderá usar os recursos de booster.",
    "vip_full_role": "Este cargo libera o gerenciamento da família, como o boost.",
    "vip_personal_role": "Este cargo libera a criação de um cargo personalizado.",
    "role_position_upper": (
        "Define o limite acima dos cargos criados. O cargo do bot precisa ficar "
        "acima deste cargo na hierarquia."
    ),
    "role_position_lower": (
        "Os cargos pessoais ficam logo acima deste cargo. Ele precisa ficar "
        "abaixo do limite superior."
    ),
    "family_position_lower": (
        "Os cargos de família ficam logo acima deste cargo. Ele precisa ficar "
        "abaixo do limite superior."
    ),
    "repair_below_role": (
        "Quando os cargos gerenciados estão abaixo deste cargo, o bot verifica "
        "e corrige suas posições."
    ),
    "family_member_limit": (
        "Quantidade máxima de pessoas na família, incluindo quem a criou."
    ),
}

BOOST_SETTING_OPTION_DESCRIPTIONS = {
    "booster_role": "Libera os recursos de booster para quem tiver este cargo.",
    "vip_full_role": "Libera o gerenciamento da família para quem tiver este cargo.",
    "vip_personal_role": "Libera a criação de um cargo personalizado.",
    "role_position_upper": "Limite superior; o cargo do bot deve ficar acima dele.",
    "role_position_lower": "Os cargos pessoais ficam logo acima deste cargo.",
    "family_position_lower": "Os cargos de família ficam logo acima deste cargo.",
    "repair_below_role": "Referência para o bot verificar e corrigir posições.",
    "family_member_limit": "Máximo de pessoas na família, incluindo você.",
}

WARN_PUNISHMENT_CHOICES = {
    "none": "Somente advertência",
    "timeout": "Advertência + silenciamento",
    "kick": "Advertência + expulsão",
    "ban": "Advertência + banimento",
}


class NumberSettingModal(discord.ui.Modal):
    def __init__(self, menu: "Menu", guild_id: int, key: str, label: str):
        super().__init__(title=f"Configurar {label}")
        self.menu = menu
        self.guild_id = guild_id
        self.key = key
        max_value = {
            "family_member_limit": 25,
            "warn_timeout_minutes": 40320,
        }.get(key, 9999)
        self.value_input = discord.ui.TextInput(
            label=label,
            placeholder=f"Digite um número entre 1 e {max_value}",
            min_length=1,
            max_length=len(str(max_value)),
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            value = int(self.value_input.value)
            max_value = {
                "family_member_limit": 25,
                "warn_timeout_minutes": 40320,
            }.get(self.key, 9999)
            if value < 1 or value > max_value:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(
                f"Informe um número entre 1 e {max_value}.", ephemeral=True
            )
        await self.menu.set_value(self.guild_id, self.key, value)
        await interaction.response.send_message(
            f"Configuração salva: **{value}**.", ephemeral=True
        )


class WelcomeTextModal(discord.ui.Modal):
    def __init__(self, menu: "Menu", guild_id: int):
        super().__init__(title="Editar texto de boas-vindas")
        self.menu = menu
        self.guild_id = guild_id
        self.title_input = discord.ui.TextInput(
            label="Título da embed",
            default=menu.get_value(guild_id, "welcome_embed_title", "") or "",
            max_length=256,
            required=False,
        )
        self.description_input = discord.ui.TextInput(
            label="Descrição",
            default=menu.get_value(guild_id, "welcome_embed_description", "") or "",
            placeholder="Placeholders: {user}, {server}, {member_count}",
            style=discord.TextStyle.paragraph,
            max_length=4000,
            required=False,
        )
        self.footer_input = discord.ui.TextInput(
            label="Texto do footer",
            default=menu.get_value(guild_id, "welcome_footer", "") or "",
            max_length=2048,
            required=False,
        )
        self.author_input = discord.ui.TextInput(
            label="Nome do autor junto ao ícone do título",
            default=menu.get_value(guild_id, "welcome_author_name", "") or "",
            max_length=256,
            required=False,
        )
        for field in (
            self.title_input,
            self.description_input,
            self.footer_input,
            self.author_input,
        ):
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.menu.set_values(
            self.guild_id,
            {
                "welcome_embed_title": self.title_input.value,
                "welcome_embed_description": self.description_input.value,
                "welcome_footer": self.footer_input.value,
                "welcome_author_name": self.author_input.value,
            },
        )
        await interaction.response.send_message(
            "Textos de boas-vindas salvos para este servidor.", ephemeral=True
        )


class WelcomeAssetsModal(discord.ui.Modal):
    def __init__(self, menu: "Menu", guild_id: int):
        super().__init__(title="Enviar imagens de boas-vindas")
        self.menu = menu
        self.guild_id = guild_id
        self.thumbnail_upload = discord.ui.FileUpload(
            required=False, min_values=0, max_values=1
        )
        self.image_upload = discord.ui.FileUpload(
            required=False, min_values=0, max_values=1
        )
        self.author_icon_upload = discord.ui.FileUpload(
            required=False, min_values=0, max_values=1
        )
        self.add_item(
            discord.ui.Label(text="Thumbnail da embed", component=self.thumbnail_upload)
        )
        self.add_item(
            discord.ui.Label(text="Imagem grande da embed", component=self.image_upload)
        )
        self.add_item(
            discord.ui.Label(
                text="Ícone ao lado do título",
                component=self.author_icon_upload,
            )
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        saved = []
        try:
            for key, upload in (
                ("welcome_thumbnail", self.thumbnail_upload),
                ("welcome_image", self.image_upload),
                ("welcome_author_icon", self.author_icon_upload),
            ):
                if upload.values:
                    filename = await self.menu.store_welcome_asset(
                        self.guild_id, key, upload.values[0]
                    )
                    saved.append(filename)
        except ValueError as error:
            return await interaction.response.send_message(str(error), ephemeral=True)
        if not saved:
            return await interaction.response.send_message(
                "Nenhum arquivo foi enviado; as imagens atuais foram mantidas.",
                ephemeral=True,
            )
        await interaction.response.send_message(
            "Imagens salvas para este servidor: " + ", ".join(saved),
            ephemeral=True,
        )


class RankingIntroTextModal(discord.ui.Modal):
    def __init__(self, menu: "Menu", guild_id: int, prefix: str):
        super().__init__(title="Texto da embed de apresentação")
        self.menu = menu
        self.guild_id = guild_id
        self.prefix = prefix
        self.title_input = discord.ui.TextInput(
            label="Title",
            default=menu.get_value(guild_id, f"{prefix}_title", "") or "",
            max_length=256,
            required=False,
        )
        self.description_input = discord.ui.TextInput(
            label="Description (máx. 1500 caracteres)",
            default=(
                menu.get_value(guild_id, f"{prefix}_description", "") or ""
            )[:RANKING_INTRO_DESCRIPTION_MAX_LENGTH],
            style=discord.TextStyle.paragraph,
            max_length=RANKING_INTRO_DESCRIPTION_MAX_LENGTH,
            required=False,
        )
        self.footer_input = discord.ui.TextInput(
            label="Footer",
            default=menu.get_value(guild_id, f"{prefix}_footer", "") or "",
            max_length=2048,
            required=False,
        )
        for field in (self.title_input, self.description_input, self.footer_input):
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.menu.set_values(
            self.guild_id,
            {
                f"{self.prefix}_title": self.title_input.value,
                f"{self.prefix}_description": self.description_input.value,
                f"{self.prefix}_footer": self.footer_input.value,
            },
        )
        await interaction.response.send_message(
            "Texto da embed salvo.", ephemeral=True
        )


class RankingIntroImagesModal(discord.ui.Modal):
    def __init__(self, menu: "Menu", guild_id: int, prefix: str):
        super().__init__(title="Imagens da embed de apresentação")
        self.menu = menu
        self.guild_id = guild_id
        self.prefix = prefix
        self.thumbnail_input = discord.ui.TextInput(
            label="Thumbnail (URL)",
            default=menu.get_value(guild_id, f"{prefix}_thumbnail", "") or "",
            max_length=400,
            required=False,
        )
        self.image_input = discord.ui.TextInput(
            label="Image (URL)",
            default=menu.get_value(guild_id, f"{prefix}_image", "") or "",
            max_length=400,
            required=False,
        )
        self.title_image_input = discord.ui.TextInput(
            label="Title Image (URL)",
            default=menu.get_value(guild_id, f"{prefix}_title_image", "") or "",
            max_length=400,
            required=False,
        )
        for field in (
            self.thumbnail_input,
            self.image_input,
            self.title_image_input,
        ):
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.menu.set_values(
            self.guild_id,
            {
                f"{self.prefix}_thumbnail": self.thumbnail_input.value.strip(),
                f"{self.prefix}_image": self.image_input.value.strip(),
                f"{self.prefix}_title_image": self.title_image_input.value.strip(),
            },
        )
        await interaction.response.send_message(
            "Imagens da embed salvas.", ephemeral=True
        )


class RankingTopModal(discord.ui.Modal):
    def __init__(self, menu: "Menu", guild_id: int, prefix: str):
        super().__init__(title="Configurar embed do top 10")
        self.menu = menu
        self.guild_id = guild_id
        self.prefix = prefix
        self.title_input = discord.ui.TextInput(
            label="Title",
            default=menu.get_value(guild_id, f"{prefix}_title", "") or "",
            max_length=256,
            required=False,
        )
        self.thumbnail_input = discord.ui.TextInput(
            label="Thumbnail (URL)",
            default=menu.get_value(guild_id, f"{prefix}_thumbnail", "") or "",
            max_length=400,
            required=False,
        )
        self.add_item(self.title_input)
        self.add_item(self.thumbnail_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.menu.set_values(
            self.guild_id,
            {
                f"{self.prefix}_title": self.title_input.value,
                f"{self.prefix}_thumbnail": self.thumbnail_input.value.strip(),
            },
        )
        await interaction.response.send_message(
            "Embed do ranking salva.", ephemeral=True
        )


class RankingIntroConfigView(discord.ui.View):
    def __init__(self, menu: "Menu", guild_id: int, prefix: str):
        super().__init__(timeout=300)
        self.menu = menu
        self.guild_id = guild_id
        self.prefix = prefix
        self.add_item(RankingIntroTextButton())
        self.add_item(RankingIntroImagesButton())


class RankingIntroTextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Editar texto", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: RankingIntroConfigView = self.view
        await interaction.response.send_modal(
            RankingIntroTextModal(view.menu, view.guild_id, view.prefix)
        )


class RankingIntroImagesButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Editar imagens", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: RankingIntroConfigView = self.view
        await interaction.response.send_modal(
            RankingIntroImagesModal(view.menu, view.guild_id, view.prefix)
        )


class RankingIntroButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Editar embed", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: MenuView = self.view
        prefix = view.setting
        await interaction.response.send_message(
            "Escolha quais campos da embed deseja editar.",
            view=RankingIntroConfigView(view.menu, interaction.guild_id, prefix),
            ephemeral=True,
        )


class RankingTopButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Editar embed", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: MenuView = self.view
        prefix = view.setting
        await interaction.response.send_modal(
            RankingTopModal(view.menu, interaction.guild_id, prefix)
        )


class CategorySelect(discord.ui.Select):
    def __init__(self, view: "MenuView"):
        options = [
            discord.SelectOption(
                label=details["label"],
                value=key,
                description=(
                    details.get("description")
                    or f"{len(details['items'])} opções · selecione para configurar"
                )[:100],
                default=key == view.category,
            )
            for key, details in SETTINGS.items()
        ]
        super().__init__(
            placeholder="Selecione uma área para configurar",
            min_values=1,
            max_values=1,
            options=options,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        view: MenuView = self.view
        view.category = self.values[0]
        view.setting = None
        view.rebuild()
        await interaction.edit_original_response(
            embeds=[], view=view.message_view(interaction.guild)
        )


class SettingSelect(discord.ui.Select):
    def __init__(self, view: "MenuView"):
        category = SETTINGS[view.category]
        options = [
            discord.SelectOption(
                label=label,
                value=key,
                description=(
                    BOOST_SETTING_OPTION_DESCRIPTIONS[key]
                    if view.category == "boost"
                    else "Escolha a ação aplicada junto com a advertência."
                    if kind == "choice"
                    else "Ative ou desative este recurso."
                    if kind == "toggle"
                    else "Selecione uma ou mais opções para aplicar."
                    if kind == "roles"
                    else "Selecione o item que será usado por este módulo."
                    if kind in {"role", "channel"}
                    else "Revise o status atual e abra o editor."
                    if kind in {
                        "rank_intro",
                        "rank_top",
                        "welcome_text",
                        "welcome_assets",
                        "quotes_style",
                        "fish_voices",
                    }
                    else "Defina o valor numérico desta configuração."
                    if kind == "number"
                    else f"Tipo: {kind}"
                ),
                default=key == view.setting,
            )
            for key, (label, kind) in category["items"].items()
        ]
        super().__init__(
            placeholder="Escolha uma configuração",
            min_values=1,
            max_values=1,
            options=options,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        view: MenuView = self.view
        view.setting = self.values[0]
        view.rebuild()
        await interaction.edit_original_response(
            embeds=[], view=view.message_view(interaction.guild)
        )


class RoleSettingSelect(discord.ui.RoleSelect):
    def __init__(self, view: "MenuView", multiple: bool):
        placeholder = (
            f"Escolha: {SETTINGS[view.category]['items'][view.setting][0]}"
            if view.category == "boost"
            else "Selecione cargo(s) deste servidor"
        )
        super().__init__(
            placeholder=placeholder,
            min_values=0,
            max_values=10 if multiple else 1,
        )
        self.multiple = multiple

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        view: MenuView = self.view
        if self.multiple:
            value = [role.id for role in self.values]
        else:
            value = self.values[0].id if self.values else None
        await view.menu.set_value(interaction.guild_id, view.setting, value)
        view.rebuild()
        await interaction.edit_original_response(
            embeds=[], view=view.message_view(interaction.guild)
        )


class ChoiceSettingSelect(discord.ui.Select):
    def __init__(self, view: "MenuView"):
        current_value = view.menu.get_value(
            view.guild_id, view.setting, "none"
        )
        options = [
            discord.SelectOption(
                label=label,
                value=value,
                default=value == current_value,
            )
            for value, label in WARN_PUNISHMENT_CHOICES.items()
        ]
        super().__init__(
            placeholder="Escolha a punição adicional",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        view: MenuView = self.view
        await view.menu.set_value(
            interaction.guild_id, view.setting, self.values[0]
        )
        view.rebuild()
        await interaction.edit_original_response(
            embeds=[], view=view.message_view(interaction.guild)
        )


class ChannelSettingSelect(discord.ui.ChannelSelect):
    def __init__(self, view: "MenuView"):
        placeholder = {
            "welcome": "Selecione o canal de boas-vindas",
            "insta": "Selecione o canal do Instagram fictício",
            "quotes": "Selecione o canal dos Quotes",
            "roblox": "Selecione o canal das skins Roblox",
            "ranking_call": "Selecione o canal do ranking de call",
            "ranking_messages": "Selecione o canal do ranking de mensagens",
            "logs": "Selecione o canal que receberá os registros",
        }.get(view.category, "Selecione o canal deste módulo")
        super().__init__(
            placeholder=placeholder,
            min_values=0,
            max_values=1,
            channel_types=[discord.ChannelType.text],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        view: MenuView = self.view
        channel_id = self.values[0].id if self.values else None
        await view.menu.set_value(interaction.guild_id, view.setting, channel_id)
        view.rebuild()
        await interaction.edit_original_response(
            embeds=[], view=view.message_view(interaction.guild)
        )


QUOTE_AVATAR_POSITIONS = {
    "left": "Esquerda",
    "right": "Direita",
    "top": "Em cima",
    "bottom": "Em baixo",
    "hidden": "Removido",
}
QUOTE_STYLE_SELECTS = {
    "font": {
        "default": "Padrão do bot",
        **{key: name for key, (name, _) in FONT_URLS.items()},
    },
    "avatar_position": QUOTE_AVATAR_POSITIONS,
    "background_mode": {"solid": "Cor sólida", "gradient": "Gradiente"},
    "avatar_grayscale": {"true": "Preto e branco", "false": "Colorido"},
}


class QuoteStyleSelect(discord.ui.Select):
    def __init__(self, setting: str, placeholder: str, options: dict[str, str], current: str):
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=label,
                    value=value,
                    default=value == current,
                )
                for value, label in options.items()
            ],
        )
        self.setting = setting

    async def callback(self, interaction: discord.Interaction) -> None:
        view: QuoteStyleView = self.view
        value = self.values[0]
        if self.setting == "avatar_grayscale":
            value = value == "true"
        style = view.style()
        style[self.setting] = value
        await view.menu.set_value(interaction.guild_id, "quotes_style", style)
        refreshed_view = QuoteStyleView(view.menu, interaction.guild_id)
        await interaction.response.edit_message(
            embed=refreshed_view.embed(), view=refreshed_view
        )


class QuoteColorsModal(discord.ui.Modal):
    def __init__(self, view: "QuoteStyleView"):
        super().__init__(title="Cores da imagem de Quotes")
        self.style_view = view
        self.menu = view.menu
        self.guild_id = view.guild_id
        self.background_input = discord.ui.TextInput(
            label="Cor de fundo (HEX)",
            placeholder="#000000",
            default=view.style()["background_color"],
            min_length=7,
            max_length=7,
        )
        self.gradient_input = discord.ui.TextInput(
            label="Segunda cor do gradiente (HEX)",
            placeholder="#252542",
            default=view.style()["gradient_color"],
            min_length=7,
            max_length=7,
        )
        self.text_input = discord.ui.TextInput(
            label="Cor do texto (HEX)",
            placeholder="#EEEEF1",
            default=view.style()["text_color"],
            min_length=7,
            max_length=7,
        )
        self.signature_input = discord.ui.TextInput(
            label="Cor da assinatura (HEX)",
            placeholder="#CDCDD3",
            default=view.style()["signature_color"],
            min_length=7,
            max_length=7,
        )
        for field in (
            self.background_input,
            self.gradient_input,
            self.text_input,
            self.signature_input,
        ):
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        values = {
            "background_color": self.background_input.value.strip().upper(),
            "gradient_color": self.gradient_input.value.strip().upper(),
            "text_color": self.text_input.value.strip().upper(),
            "signature_color": self.signature_input.value.strip().upper(),
        }
        if any(
            re.fullmatch(r"#[0-9A-F]{6}", value) is None
            for value in values.values()
        ):
            return await interaction.response.send_message(
                "Use cores no formato hexadecimal #RRGGBB, por exemplo #12ABEF.",
                ephemeral=True,
            )
        style = self.style_view.style()
        style.update(values)
        await self.menu.set_value(self.guild_id, "quotes_style", style)
        await interaction.response.send_message(
            "Cores dos Quotes salvas.", ephemeral=True
        )


class QuoteColorsButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Editar cores",
            style=discord.ButtonStyle.primary,
            row=4,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(QuoteColorsModal(self.view))


class QuotePreviewButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Prévia efêmera",
            style=discord.ButtonStyle.success,
            row=4,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: QuoteStyleView = self.view
        user = view.menu.bot.user
        if user is None:
            return await interaction.response.send_message(
                "Não foi possível carregar o avatar do bot para a prévia.",
                ephemeral=True,
            )
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            style = view.style()
            font_data = await fetch_quote_font(style["font"])
            avatar_data = await user.display_avatar.read()
            image_data = await asyncio.to_thread(
                build_quote_image,
                avatar_data,
                "Este texto é onde a sua fonte customizada aparece.",
                user.display_name,
                style,
                font_data,
            )
        except (
            aiohttp.ClientError,
            asyncio.TimeoutError,
            discord.HTTPException,
            OSError,
            ValueError,
        ) as error:
            print(
                f"Quotes: falha ao gerar prévia em {view.guild_id}: "
                f"{type(error).__name__}: {error}",
                flush=True,
            )
            return await interaction.followup.send(
                "Não foi possível gerar a prévia. Confira a fonte selecionada e tente novamente.",
                ephemeral=True,
            )
        await interaction.followup.send(
            file=discord.File(BytesIO(image_data), filename="hakari_quote_preview.png"),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


class QuoteStyleResetButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Restaurar padrão",
            style=discord.ButtonStyle.secondary,
            row=4,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: QuoteStyleView = self.view
        await view.menu.set_value(
            interaction.guild_id, "quotes_style", DEFAULT_QUOTE_STYLE.copy()
        )
        refreshed_view = QuoteStyleView(view.menu, interaction.guild_id)
        await interaction.response.edit_message(
            embed=refreshed_view.embed(), view=refreshed_view
        )


class QuoteStyleView(discord.ui.View):
    def __init__(self, menu: "Menu", guild_id: int):
        super().__init__(timeout=300)
        self.menu = menu
        self.guild_id = guild_id
        style = self.style()
        self.add_item(
            QuoteStyleSelect(
                "font",
                "Fonte (20 fontes online)",
                QUOTE_STYLE_SELECTS["font"],
                style["font"],
            )
        )
        self.add_item(
            QuoteStyleSelect(
                "avatar_position",
                "Posição da foto de perfil",
                QUOTE_STYLE_SELECTS["avatar_position"],
                style["avatar_position"],
            )
        )
        self.add_item(
            QuoteStyleSelect(
                "background_mode",
                "Fundo",
                QUOTE_STYLE_SELECTS["background_mode"],
                style["background_mode"],
            )
        )
        self.add_item(
            QuoteStyleSelect(
                "avatar_grayscale",
                "Aparência da foto de perfil",
                QUOTE_STYLE_SELECTS["avatar_grayscale"],
                str(style["avatar_grayscale"]).lower(),
            )
        )
        self.add_item(QuoteColorsButton())
        self.add_item(QuotePreviewButton())
        self.add_item(QuoteStyleResetButton())

    def style(self) -> dict:
        return quote_style_with_defaults(
            self.menu.get_value(
                self.guild_id, "quotes_style", DEFAULT_QUOTE_STYLE
            )
        )

    def embed(self) -> discord.Embed:
        style = self.style()
        font_label = QUOTE_STYLE_SELECTS["font"][style["font"]]
        avatar_label = QUOTE_AVATAR_POSITIONS[style["avatar_position"]]
        background = (
            f"Gradiente: {style['background_color']} → {style['gradient_color']}"
            if style["background_mode"] == "gradient"
            else style["background_color"]
        )
        embed = discord.Embed(
            title="Estilo das imagens de Quotes",
            description=(
                "As alterações são aplicadas automaticamente aos próximos Quotes. "
                "As 20 fontes customizadas são carregadas do Google Fonts quando usadas."
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Fonte",
            value=font_label,
            inline=True,
        )
        embed.add_field(
            name="Foto de perfil",
            value=(
                f"{avatar_label} · "
                f"{'preto e branco' if style['avatar_grayscale'] else 'colorida'}"
            ),
            inline=True,
        )
        embed.add_field(name="Fundo", value=background, inline=True)
        embed.add_field(
            name="Texto / assinatura",
            value=f"{style['text_color']} / {style['signature_color']}",
            inline=True,
        )
        return embed


class QuoteStyleButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Estilizar imagem",
            style=discord.ButtonStyle.primary,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: MenuView = self.view
        style_view = QuoteStyleView(view.menu, interaction.guild_id)
        await interaction.response.send_message(
            embed=style_view.embed(),
            view=style_view,
            ephemeral=True,
        )


class FishVoiceSelect(discord.ui.Select):
    def __init__(self, view: "FishVoiceConfigView"):
        options = [
            discord.SelectOption(
                label=voice["label"][:100],
                value=voice["id"],
                default=voice["id"] == view.selected_voice_id,
            )
            for voice in view.voices[:25]
        ]
        super().__init__(
            placeholder="Selecione um personagem para a voz do bot",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.config_view = view

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.config_view
        selected_voice_id = self.values[0]
        selected_voice = next(
            voice for voice in view.voices
            if voice["id"] == selected_voice_id
        )
        await view.menu.set_values(
            view.guild_id,
            {
                "ia_audio_voice_id": selected_voice_id,
                "ia_audio_voice_name": selected_voice["label"],
            },
        )
        was_enabled = bool(
            view.menu.get_value(view.guild_id, "module_ia_audio", False)
        )
        await interaction.response.edit_message(
            content=(
                f"Personagem selecionado: **{selected_voice.get('label') or 'Voz Fish Audio'}**."
                if not was_enabled
                else f"Personagem selecionado: **{selected_voice.get('label') or 'Voz Fish Audio'}**. "
                "Ela será usada nas próximas respostas."
            ),
            view=FishVoiceConfigView(
                view.menu,
                view.guild_id,
                view.voices,
                selected_voice_id,
            ),
        )


class ClearFishVoicesButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Limpar seleção",
            style=discord.ButtonStyle.secondary,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: FishVoiceConfigView = self.view
        await view.menu.set_values(
            view.guild_id,
            {
                "ia_audio_voice_id": None,
                "ia_audio_voice_name": None,
            },
        )
        was_enabled = bool(
            view.menu.get_value(view.guild_id, "module_ia_audio", False)
        )
        if was_enabled:
            await view.menu.set_value(view.guild_id, "module_ia_audio", False)
        status = "Seleção de personagens limpa."
        if was_enabled:
            status += " O sistema foi desativado."
        await interaction.response.edit_message(
            content=status,
            view=FishVoiceConfigView(
                view.menu,
                view.guild_id,
                view.voices,
                None,
            ),
        )


class FishVoiceConfigView(discord.ui.View):
    def __init__(
        self,
        menu: "Menu",
        guild_id: int,
        voices: list[dict],
        selected_voice_id: str | None,
    ):
        super().__init__(timeout=300)
        self.menu = menu
        self.guild_id = guild_id
        self.voices = voices
        self.selected_voice_id = selected_voice_id
        if self.voices:
            self.add_item(FishVoiceSelect(self))
        self.add_item(ClearFishVoicesButton())


class FishVoiceConfigButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Carregar personagens (Vozes)",
            style=discord.ButtonStyle.primary,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: MenuView = self.view
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            voices = await view.menu.fetch_fish_audio_voices()
        except (
            aiohttp.ClientError,
            asyncio.TimeoutError,
            RuntimeError,
            ValueError,
        ) as error:
            print(
                f"Não foi possível carregar as vozes Fish Audio "
                f"(guild={interaction.guild_id}): "
                f"{type(error).__name__}: {error}",
                flush=True,
            )
            return await interaction.followup.send(
                "Não consegui carregar as vozes Fish Audio. Verifique se "
                "`FISH_API_KEY` está configurada no Render e tente novamente.",
                ephemeral=True,
            )

        if not voices:
            return await interaction.followup.send(
                "Nenhum dos personagens solicitados está disponível na biblioteca "
                "licenciada do Fish Audio. Verifique os logs do bot.",
                ephemeral=True,
            )

        selected_voice_id = view.menu.ai_audio_voice_id(interaction.guild_id)
        selected_voice = next(
            (
                voice
                for voice in voices
                if voice["id"] == selected_voice_id
            ),
            None,
        )
        if selected_voice is None:
            selected_voice = next(
                (voice for voice in voices if voice.get("default")),
                None,
            )
            if selected_voice is not None:
                selected_voice_id = selected_voice["id"]
                await view.menu.set_values(
                    interaction.guild_id,
                    {
                        "ia_audio_voice_id": selected_voice_id,
                        "ia_audio_voice_name": selected_voice["label"],
                    },
                )
            else:
                await view.menu.set_values(
                    interaction.guild_id,
                    {
                        "ia_audio_voice_id": None,
                        "ia_audio_voice_name": None,
                    },
                )
                if view.menu.get_value(
                    interaction.guild_id,
                    "module_ia_audio",
                    False,
                ):
                    await view.menu.set_value(
                        interaction.guild_id,
                        "module_ia_audio",
                        False,
                    )

        await interaction.followup.send(
            content=(
                (
                    "Use o menu abaixo para escolher o personagem. Hakari é selecionado por padrão "
                    "quando está disponível; todas as opções são vozes licenciadas."
                    if selected_voice is not None
                    else "A voz padrão Hakari não está disponível; escolha um "
                    "dos outros personagens listados através do menu abaixo. O sistema precisa de uma voz "
                    "selecionada para ser ativado."
                )
            ),
            view=FishVoiceConfigView(
                view.menu,
                interaction.guild_id,
                voices[:MAX_AI_AUDIO_VOICES],
                selected_voice_id,
            ),
            ephemeral=True,
        )


class NumberSettingButton(discord.ui.Button):
    def __init__(self, view: "MenuView", label: str):
        super().__init__(label=f"Definir: {label}", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: MenuView = self.view
        label = SETTINGS[view.category]["items"][view.setting][0]
        await interaction.response.send_modal(
            NumberSettingModal(view.menu, interaction.guild_id, view.setting, label)
        )


class WelcomeTextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Editar textos", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: MenuView = self.view
        await interaction.response.send_modal(
            WelcomeTextModal(view.menu, interaction.guild_id)
        )


class WelcomeAssetsButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Enviar imagens", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: MenuView = self.view
        await interaction.response.send_modal(
            WelcomeAssetsModal(view.menu, interaction.guild_id)
        )


class ToggleSettingButton(discord.ui.Button):
    def __init__(self, view: "MenuView", enabled: bool):
        label = "Desativar" if enabled else "Ativar"
        super().__init__(label=label, style=discord.ButtonStyle.success if not enabled else discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: MenuView = self.view
        current = bool(view.menu.get_value(interaction.guild_id, view.setting, False))
        if (
            view.setting == "module_ia_audio"
            and not current
            and not view.menu.ai_audio_voice_id(interaction.guild_id)
        ):
            return await interaction.response.send_message(
                "Escolha um personagem em `IA em áudio` antes de ativar "
                "o sistema.",
                ephemeral=True,
            )
        await view.menu.set_value(interaction.guild_id, view.setting, not current)
        view.rebuild()
        await interaction.response.edit_message(
            embeds=[], view=view.message_view(interaction.guild)
        )


class AccessButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Gerenciar acessos", style=discord.ButtonStyle.secondary, row=4)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: MenuView = self.view
        if not view.menu.can_manage_access(interaction.user.id, interaction.guild):
            return await interaction.response.send_message(
                "Somente o dono do servidor ou o desenvolvedor pode gerenciar acessos.",
                ephemeral=True,
            )
        await interaction.response.edit_message(
            embeds=[],
            view=components_v2(
                view.menu.access_embed(interaction.guild),
                view=AccessView(view.menu, interaction.guild_id),
                hero_url=view.menu.banner_url(),
            ),
        )


class BackButton(discord.ui.Button):
    def __init__(self, menu: "Menu"):
        super().__init__(label="Voltar ao painel", style=discord.ButtonStyle.secondary, row=4)
        self.menu = menu

    async def callback(self, interaction: discord.Interaction) -> None:
        view = MenuView(self.menu, interaction.guild_id, interaction.user.id)
        await interaction.response.edit_message(
            embeds=[], view=view.message_view(interaction.guild)
        )


class RestrictedAreaButton(discord.ui.Button):
    def __init__(self, menu: "Menu"):
        super().__init__(label="Área Restrita", style=discord.ButtonStyle.danger, row=4)
        self.menu = menu

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != DEVELOPER_ID:
            return await interaction.response.send_message(
                "A Área Restrita é exclusiva do desenvolvedor.", ephemeral=True
            )
        await interaction.response.edit_message(
            embeds=[],
            view=components_v2(
                self.menu.restricted_embed(interaction.guild_id),
                view=DeveloperToolsView(self.menu, interaction.guild_id),
                hero_url=self.menu.banner_url(),
            ),
        )


class DeveloperActionSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="1. Escolha uma ação restrita",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label="Desligar bot", value="shutdown"),
                discord.SelectOption(label="Dessincronizar comando global", value="unsync"),
                discord.SelectOption(label="Resetar todas as configurações", value="reset"),
                discord.SelectOption(label="Sincronizar comandos globais", value="sync"),
                discord.SelectOption(label="Sair de um servidor", value="leave_server"),
            ],
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != DEVELOPER_ID:
            return await interaction.response.send_message(
                "A Área Restrita é exclusiva do desenvolvedor.", ephemeral=True
            )
        view: DeveloperToolsView = self.view
        view.action = self.values[0]
        await interaction.response.defer()


class DeveloperCommandSelect(discord.ui.Select):
    def __init__(self, menu: "Menu"):
        commands_list = menu.bot.tree.get_commands()[:25]
        options = [
            discord.SelectOption(
                label=command.name[:100],
                value=command.name,
                description=(command.description or "Sem descrição")[:100],
            )
            for command in commands_list
        ]
        super().__init__(
            placeholder="Comando global (usado ao dessincronizar)",
            min_values=1,
            max_values=1,
            options=options or [
                discord.SelectOption(label="Nenhum comando global", value="_none")
            ],
            disabled=not options,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != DEVELOPER_ID:
            return await interaction.response.send_message(
                "A Área Restrita é exclusiva do desenvolvedor.", ephemeral=True
            )
        await interaction.response.defer()


class RunDeveloperActionButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Continuar", style=discord.ButtonStyle.primary, row=3)

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != DEVELOPER_ID:
            return await interaction.response.send_message(
                "A Área Restrita é exclusiva do desenvolvedor.", ephemeral=True
            )
        view: DeveloperToolsView = self.view
        if view.action is None:
            return await interaction.response.send_message(
                "Escolha uma ação primeiro.", ephemeral=True
            )
        command_name = (
            view.command_select.values[0]
            if view.command_select.values
            else ""
        )
        if view.action == "unsync" and command_name == "_none":
            return await interaction.response.send_message(
                "Não há comandos globais para dessincronizar.", ephemeral=True
            )
        labels = {
            "shutdown": "desligar o bot",
            "unsync": f"dessincronizar globalmente `/{command_name}`",
            "reset": "apagar as configurações de todos os servidores",
            "sync": "sincronizar novamente todos os comandos globais",
            "leave_server": "sair de um servidor e apagar suas configurações",
        }
        if view.action == "leave_server":
            if view.target_guild_id is None:
                return await interaction.response.send_message(
                    "Selecione o servidor no menu de servidores antes de continuar.",
                    ephemeral=True,
                )
            target_guild = view.menu.bot.get_guild(view.target_guild_id)
            if target_guild is None:
                return await interaction.response.send_message(
                    "O servidor selecionado não está mais conectado ao bot. "
                    "Reabra a Área Restrita e tente novamente.",
                    ephemeral=True,
                )
            description = (
                f"O bot sairá de **{target_guild.name}** (`{target_guild.id}`) "
                "e todas as configurações do `/menu`, permissões de acesso e "
                "imagens de boas-vindas desse servidor serão apagadas.\n\n"
                "Esta ação não pode ser desfeita."
            )
        else:
            description = (
                f"Você está prestes a **{labels[view.action]}**.\n\n"
                "Esta ação pode afetar o funcionamento do bot. "
                "Confirme somente se tiver certeza."
            )
        await interaction.response.edit_message(
            embeds=[],
            view=components_v2(
                discord.Embed(
                    title="Confirmação · ação restrita",
                    description=description,
                    color=discord.Color.red(),
                ),
                view=ConfirmDeveloperActionView(
                    view.menu,
                    view.guild_id,
                    view.action,
                    command_name,
                    view.target_guild_id,
                ),
                hero_url=view.menu.banner_url(),
            ),
        )


class DeveloperToolsView(ComponentsV2View):
    def __init__(self, menu: "Menu", guild_id: int):
        super().__init__(timeout=300)
        self.menu = menu
        self.guild_id = guild_id
        self.action = None
        self.guild_page = 0
        self.target_guild_id: int | None = None
        self.action_select = DeveloperActionSelect()
        self.command_select = DeveloperCommandSelect(menu)
        self.guild_select = DeveloperGuildSelect(menu, self)
        self.previous_page_button = DeveloperGuildPageButton(-1)
        self.next_page_button = DeveloperGuildPageButton(1)
        self.add_item(self.action_select)
        self.add_item(self.command_select)
        self.add_item(self.guild_select)
        self.add_item(self.previous_page_button)
        self.add_item(self.next_page_button)
        self.add_item(RunDeveloperActionButton())
        self.add_item(BackButton(menu))
        self.refresh_guild_page_buttons()

    def refresh_guild_page_buttons(self) -> None:
        page_count = self.guild_select.page_count
        self.previous_page_button.disabled = self.guild_page == 0
        self.next_page_button.disabled = self.guild_page >= page_count - 1


class DeveloperGuildSelect(discord.ui.Select):
    def __init__(self, menu: "Menu", view: "DeveloperToolsView"):
        self.menu = menu
        self.developer_view = view
        self.guilds = sorted(
            menu.bot.guilds, key=lambda guild: (guild.name.casefold(), guild.id)
        )
        self.page_count = max(1, (len(self.guilds) + 24) // 25)
        super().__init__(
            placeholder=(
                f"Servidor para sair · página 1 de {self.page_count}"
                if self.guilds
                else "Nenhum servidor conectado"
            ),
            min_values=1,
            max_values=1,
            options=self.options_for_page(0),
            disabled=not self.guilds,
            row=2,
        )

    def options_for_page(self, page: int) -> list[discord.SelectOption]:
        if not self.guilds:
            return [
                discord.SelectOption(
                    label="Nenhum servidor conectado", value="_none"
                )
            ]
        start = page * 25
        return [
            discord.SelectOption(
                label=guild.name[:100] or "Servidor sem nome",
                value=str(guild.id),
                description=f"ID: {guild.id}",
                default=guild.id == self.developer_view.target_guild_id,
            )
            for guild in self.guilds[start : start + 25]
        ]

    def set_page(self, page: int) -> None:
        self.developer_view.guild_page = page
        self.options = self.options_for_page(page)
        self.placeholder = (
            f"Servidor para sair · página {page + 1} de {self.page_count}"
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != DEVELOPER_ID:
            return await interaction.response.send_message(
                "A Área Restrita é exclusiva do desenvolvedor.", ephemeral=True
            )
        if not self.values or self.values[0] == "_none":
            return await interaction.response.send_message(
                "Não há servidores conectados para selecionar.", ephemeral=True
            )
        self.developer_view.target_guild_id = int(self.values[0])
        await interaction.response.defer()


class DeveloperGuildPageButton(discord.ui.Button):
    def __init__(self, direction: int):
        self.direction = direction
        label = "Página anterior" if direction < 0 else "Próxima página"
        super().__init__(label=label, style=discord.ButtonStyle.secondary, row=3)

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != DEVELOPER_ID:
            return await interaction.response.send_message(
                "A Área Restrita é exclusiva do desenvolvedor.", ephemeral=True
            )
        view: DeveloperToolsView = self.view
        page_count = view.guild_select.page_count
        view.guild_page = min(
            max(0, view.guild_page + self.direction), page_count - 1
        )
        view.target_guild_id = None
        view.guild_select.set_page(view.guild_page)
        view.refresh_guild_page_buttons()
        await interaction.response.edit_message(
            embeds=[],
            view=components_v2(
                view.menu.restricted_embed(view.guild_id),
                view=view,
                hero_url=view.menu.banner_url(),
            ),
        )


class ConfirmDeveloperActionButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Confirmar", style=discord.ButtonStyle.danger, row=0)

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != DEVELOPER_ID:
            return await interaction.response.send_message(
                "A Área Restrita é exclusiva do desenvolvedor.", ephemeral=True
            )
        view: ConfirmDeveloperActionView = self.view
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            result = await view.menu.execute_restricted_action(
                interaction.user.id,
                view.action,
                view.command_name,
                view.target_guild_id,
            )
        except Exception as error:
            return await interaction.followup.send(
                f"A ação falhou: {type(error).__name__}: {error}", ephemeral=True
            )
        await interaction.followup.send(result, ephemeral=True)
        if view.action == "shutdown":
            await view.menu.bot.close()


class CancelDeveloperActionButton(discord.ui.Button):
    def __init__(self, menu: "Menu", guild_id: int):
        super().__init__(label="Cancelar", style=discord.ButtonStyle.secondary, row=0)
        self.menu = menu
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != DEVELOPER_ID:
            return await interaction.response.send_message(
                "A Área Restrita é exclusiva do desenvolvedor.", ephemeral=True
            )
        await interaction.response.edit_message(
            embeds=[],
            view=components_v2(
                self.menu.restricted_embed(self.guild_id),
                view=DeveloperToolsView(self.menu, self.guild_id),
                hero_url=self.menu.banner_url(),
            ),
        )


class ConfirmDeveloperActionView(ComponentsV2View):
    def __init__(
        self,
        menu: "Menu",
        guild_id: int,
        action: str,
        command_name: str,
        target_guild_id: int | None = None,
    ):
        super().__init__(timeout=60)
        self.menu = menu
        self.action = action
        self.command_name = command_name
        self.target_guild_id = target_guild_id
        self.add_item(ConfirmDeveloperActionButton())
        self.add_item(CancelDeveloperActionButton(menu, guild_id))


class AccessModeSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Escolha a ação para os usuários selecionados",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label="Conceder acesso", value="grant"),
                discord.SelectOption(label="Remover acesso", value="revoke"),
            ],
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()


class AccessUserSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(
            placeholder="Selecione usuários deste servidor",
            min_values=1,
            max_values=10,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: AccessView = self.view
        if not view.menu.can_manage_access(interaction.user.id, interaction.guild):
            return await interaction.response.send_message(
                "Somente o dono do servidor ou o desenvolvedor pode gerenciar acessos.",
                ephemeral=True,
            )
        mode = view.mode_select.values[0] if view.mode_select.values else None
        if mode is None:
            return await interaction.response.send_message(
                "Escolha primeiro conceder ou remover acesso.", ephemeral=True
            )
        current = set(view.menu.access_for(interaction.guild_id))
        for user in self.values:
            if mode == "grant":
                current.add(user.id)
            else:
                current.discard(user.id)
        await interaction.response.defer()
        await view.menu.set_access(interaction.guild_id, current)
        await interaction.edit_original_response(
            embeds=[],
            view=components_v2(
                view.menu.access_embed(interaction.guild),
                view=view,
                hero_url=view.menu.banner_url(),
            )
        )


class AccessView(ComponentsV2View):
    def __init__(self, menu: "Menu", guild_id: int):
        super().__init__(timeout=300)
        self.menu = menu
        self.mode_select = AccessModeSelect()
        self.add_item(self.mode_select)
        self.add_item(AccessUserSelect())
        self.add_item(BackButton(menu))


class MenuView(ComponentsV2View):
    def __init__(self, menu: "Menu", guild_id: int, user_id: int | None = None):
        super().__init__(timeout=300)
        self.menu = menu
        self.guild_id = guild_id
        self.user_id = user_id
        self.category = None
        self.setting = None
        self.rebuild()

    def embed(self, guild: discord.Guild) -> discord.Embed:
        embed = self.menu.overview_embed(guild)
        if not self.category:
            return embed
        category = SETTINGS[self.category]
        embed.add_field(
            name=f"🧭 Área selecionada · {category['label']}",
            value=category.get(
                "description",
                "Escolha uma configuração abaixo para consultar ou editar.",
            ),
            inline=False,
        )
        if not self.setting:
            return embed
        label, kind = SETTINGS[self.category]["items"][self.setting]
        description = (
            BOOST_SETTING_DESCRIPTIONS.get(self.setting)
            if self.category == "boost"
            else None
        )
        value = self.menu.get_value(
            guild.id,
            self.setting,
            (
                "none"
                if self.setting == "warn_additional_punishment"
                else 10
                if self.setting == "warn_timeout_minutes"
                else None
            ),
        )
        if kind == "rank_intro":
            prefix = self.setting
            configured = any(
                self.menu.get_value(guild.id, f"{prefix}_{suffix}")
                for suffix in (
                    "title",
                    "description",
                    "footer",
                    "thumbnail",
                    "image",
                    "title_image",
                )
            )
            display = "Embed configurada" if configured else "Embed não configurada"
        elif kind == "rank_top":
            prefix = self.setting
            configured = any(
                self.menu.get_value(guild.id, f"{prefix}_{suffix}")
                for suffix in ("title", "thumbnail")
            )
            display = "Embed configurada" if configured else "Embed não configurada"
        elif kind == "welcome_text":
            configured = bool(
                self.menu.get_value(guild.id, "welcome_embed_title")
                or self.menu.get_value(guild.id, "welcome_embed_description")
            )
            display = "Textos configurados" if configured else "Textos não configurados"
        elif kind == "welcome_assets":
            thumbnail = self.menu.get_value(guild.id, "welcome_thumbnail_filename")
            image = self.menu.get_value(guild.id, "welcome_image_filename")
            author_icon = self.menu.get_value(guild.id, "welcome_author_icon_filename")
            display = (
                f"Thumbnail: {thumbnail or 'não enviada'}\n"
                f"Imagem: {image or 'não enviada'}\n"
                f"Ícone do título: {author_icon or 'não enviado'}"
            )
        elif kind == "fish_voices":
            display = (
                self.menu.get_value(guild.id, "ia_audio_voice_name")
                or "Nenhum personagem selecionado"
            )
        elif kind == "quotes_style":
            style = quote_style_with_defaults(
                self.menu.get_value(
                    guild.id, "quotes_style", DEFAULT_QUOTE_STYLE
                )
            )
            display = (
                f"Fonte: {QUOTE_STYLE_SELECTS['font'][style['font']]}\n"
                f"Foto de perfil: "
                f"{QUOTE_AVATAR_POSITIONS[style['avatar_position']]}\n"
                f"Fundo: {style['background_mode']}"
            )
        elif value is None:
            display = "Desconfigurado"
        elif kind == "role":
            role = guild.get_role(int(value))
            display = role.mention if role else "Cargo removido do servidor"
        elif kind == "roles":
            mentions = [
                role.mention
                for role_id in value
                if (role := guild.get_role(int(role_id))) is not None
            ]
            display = ", ".join(mentions) if mentions else "Nenhum cargo configurado"
        elif kind == "channel":
            channel = guild.get_channel(int(value)) if value else None
            display = channel.mention if channel else "Canal não configurado"
        elif kind == "toggle":
            display = "Ativado" if value else "Desativado"
        elif kind == "choice":
            display = WARN_PUNISHMENT_CHOICES.get(str(value), "Somente advertência")
        else:
            display = str(value)
        setting_text = f"**Valor atual:** {display}"
        if description:
            setting_text += f"\n\n{description}"
        embed.add_field(
            name=f"🛠️ Configuração · {label}",
            value=setting_text,
            inline=False,
        )
        embed.set_footer(text="Use o seletor para trocar a opção; as alterações são salvas automaticamente.")
        return embed

    def message_view(self, guild: discord.Guild) -> ComponentsV2View:
        return components_v2(
            self.embed(guild),
            view=self,
        )

    def rebuild(self) -> None:
        self.clear_items()
        self.add_item(
            discord.ui.Button(
                label="Abrir site",
                url=MENU_WEBSITE_URL,
                row=0,
            )
        )
        self.add_item(CategorySelect(self))
        if self.category:
            self.add_item(SettingSelect(self))
        if self.setting:
            kind = SETTINGS[self.category]["items"][self.setting][1]
            if kind == "role":
                self.add_item(RoleSettingSelect(self, multiple=False))
            elif kind == "roles":
                self.add_item(RoleSettingSelect(self, multiple=True))
            elif kind == "choice":
                self.add_item(ChoiceSettingSelect(self))
            elif kind == "channel":
                self.add_item(ChannelSettingSelect(self))
            elif kind == "quotes_style":
                self.add_item(QuoteStyleButton())
            elif kind == "number":
                label = SETTINGS[self.category]["items"][self.setting][0]
                self.add_item(NumberSettingButton(self, label))
            elif kind == "welcome_text":
                self.add_item(WelcomeTextButton())
            elif kind == "welcome_assets":
                self.add_item(WelcomeAssetsButton())
            elif kind == "rank_intro":
                self.add_item(RankingIntroButton())
            elif kind == "rank_top":
                self.add_item(RankingTopButton())
            elif kind == "toggle":
                enabled = self.menu.get_value(self.guild_id, self.setting, False)
                self.add_item(ToggleSettingButton(self, bool(enabled)))
            elif kind == "fish_voices":
                self.add_item(FishVoiceConfigButton())
        self.add_item(AccessButton())
        if self.user_id == DEVELOPER_ID:
            self.add_item(RestrictedAreaButton(self.menu))


class Menu(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config: dict[str, dict] = {}
        self.invites: dict[int, str] = {}
        self.pool: asyncpg.Pool | None = None
        self.message_cache: OrderedDict[
            tuple[int, int, int], discord.Message
        ] = OrderedDict()
        self.recent_delete_audit_entries: dict[
            tuple[int, int], list[tuple[discord.AuditLogEntry, bool]]
        ] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if (
            message.guild is None
            or self.get_value(message.guild.id, "audit_log_channel") is None
        ):
            return

        key = (message.guild.id, message.channel.id, message.id)
        self.message_cache[key] = message
        self.message_cache.move_to_end(key)
        while len(self.message_cache) > 2000:
            self.message_cache.popitem(last=False)

    @commands.Cog.listener()
    async def on_raw_message_delete(
        self, payload: discord.RawMessageDeleteEvent
    ) -> None:
        if payload.guild_id is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        key = (payload.guild_id, payload.channel_id, payload.message_id)
        cached_message = self.message_cache.pop(key, None)
        message = payload.cached_message or cached_message
        await self.send_deleted_messages_log(
            guild,
            payload.channel_id,
            [message] if message is not None else [],
            [payload.message_id],
            bulk=False,
        )

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(
        self, payload: discord.RawBulkMessageDeleteEvent
    ) -> None:
        if payload.guild_id is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        messages_by_id = {
            message.id: message for message in payload.cached_messages
        }
        for message_id in payload.message_ids:
            key = (payload.guild_id, payload.channel_id, message_id)
            cached_message = self.message_cache.pop(key, None)
            if cached_message is not None:
                messages_by_id.setdefault(message_id, cached_message)

        await self.send_deleted_messages_log(
            guild,
            payload.channel_id,
            list(messages_by_id.values()),
            sorted(payload.message_ids),
            bulk=True,
        )

    async def find_message_delete_actor(
        self,
        guild: discord.Guild,
        channel_id: int,
        deleted_at: datetime,
        *,
        bulk: bool,
    ) -> discord.User | discord.Member | None:
        entries = self.recent_delete_audit_entries.get(
            (guild.id, channel_id), []
        )
        for index, (entry, used) in enumerate(entries):
            if used or abs((entry.created_at - deleted_at).total_seconds()) > 15:
                continue
            if bulk != (
                entry.action is discord.AuditLogAction.message_bulk_delete
            ):
                continue
            entries[index] = (entry, True)
            return entry.user
        return None

    async def send_deleted_messages_log(
        self,
        guild: discord.Guild,
        channel_id: int,
        messages: list[discord.Message],
        message_ids: list[int],
        *,
        bulk: bool,
    ) -> None:
        log_channel_id = self.get_value(guild.id, "audit_log_channel")
        log_channel = (
            guild.get_channel(int(log_channel_id))
            if log_channel_id is not None
            else None
        )
        if log_channel is None or not hasattr(log_channel, "send"):
            if log_channel_id is not None:
                print(
                    f"Canal de registros {log_channel_id} não encontrado "
                    f"no servidor {guild.id}.",
                    flush=True,
                )
            return

        deleted_at = datetime.now(timezone.utc)
        await asyncio.sleep(1)
        actor = await self.find_message_delete_actor(
            guild, channel_id, deleted_at, bulk=bulk
        )
        channel = guild.get_channel_or_thread(channel_id)
        channel_text = (
            f"{channel.mention} (`{channel.name}` · `{channel_id}`)"
            if channel is not None
            else f"<#{channel_id}> (`{channel_id}`)"
        )
        title = (
            f"🗑️ {len(message_ids)} mensagens deletadas"
            if bulk
            else "🗑️ Mensagem deletada"
        )
        embed = discord.Embed(
            title=title,
            color=discord.Color.from_rgb(220, 54, 77),
            timestamp=deleted_at,
        )
        embed.add_field(
            name="Ação realizada por",
            value=(
                f"{actor.mention} (`{actor}` · `{actor.id}`)"
                if actor is not None
                else "Não identificado pelo Registro de Auditoria"
            ),
            inline=False,
        )
        embed.add_field(name="Canal", value=channel_text, inline=False)

        display_messages = messages[:4]
        author_ids = []
        if display_messages:
            for index, message in enumerate(display_messages, start=1):
                author = message.author
                author_mention = getattr(author, "mention", None)
                author_text = (
                    f"{author_mention} (`{author}` · `{author.id}`)"
                    if author_mention
                    else f"`{author}`"
                )
                author_ids.append(str(author.id))
                source_parts = [message.content.strip()] if message.content.strip() else []
                for original_embed in message.embeds[:2]:
                    embed_parts = [
                        part
                        for part in (
                            original_embed.title,
                            original_embed.description,
                        )
                        if part
                    ]
                    if embed_parts:
                        source_parts.append(" · ".join(embed_parts))
                content = "\n".join(source_parts) or "*(sem texto)*"
                if len(content) > 650:
                    content = content[:647] + "..."
                attachments = [
                    f"[{attachment.filename}]({attachment.url[:160]})"
                    for attachment in message.attachments[:3]
                ]
                if attachments:
                    content += "\n" + " · ".join(attachments)
                origin = f"**Autor:** {author_text}\n> {content}"
                if len(origin) > 1024:
                    origin = origin[:1021] + "..."
                embed.add_field(
                    name=f"Origem · mensagem {index}",
                    value=origin,
                    inline=False,
                )
                embed.set_thumbnail(url=author.display_avatar.url)
        else:
            embed.add_field(
                name="Origem",
                value="A mensagem não estava no cache; o conteúdo e o autor não estão disponíveis.",
                inline=False,
            )

        links = [
            f"[{message_id}](https://discord.com/channels/"
            f"{guild.id}/{channel_id}/{message_id})"
            for message_id in message_ids[:10]
        ]
        embed.add_field(
            name="Links das mensagens",
            value=" · ".join(links) if links else "Indisponíveis",
            inline=False,
        )
        embed.set_footer(
            text=(
                f"IDs dos usuários: {', '.join(dict.fromkeys(author_ids)) or 'indisponíveis'} · "
                f"ID do servidor: {guild.id} · ID do canal: {channel_id} · "
                f"IDs das mensagens: {', '.join(map(str, message_ids[:10]))}"
            )[:2048]
        )

        try:
            await log_channel.send(
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.HTTPException) as error:
            print(
                f"Não foi possível enviar o registro de mensagem apagada "
                f"no servidor {guild.id}: {type(error).__name__}: {error}",
                flush=True,
            )

    @commands.Cog.listener()
    async def on_audit_log_entry_create(
        self, entry: discord.AuditLogEntry
    ) -> None:
        if entry.action in {
            discord.AuditLogAction.message_delete,
            discord.AuditLogAction.message_bulk_delete,
        }:
            channel_id = (
                getattr(getattr(entry.extra, "channel", None), "id", None)
                if entry.action is discord.AuditLogAction.message_delete
                else getattr(self._get_audit_entry_target(entry), "id", None)
            )
            if channel_id is not None:
                key = (entry.guild.id, channel_id)
                recent_entries = self.recent_delete_audit_entries.setdefault(
                    key, []
                )
                recent_entries.append((entry, False))
                expiry = datetime.now(timezone.utc) - timedelta(minutes=1)
                self.recent_delete_audit_entries[key] = [
                    (cached_entry, used)
                    for cached_entry, used in recent_entries
                    if cached_entry.created_at >= expiry
                ][-50:]
            return

        guild = entry.guild
        channel_id = self.get_value(guild.id, "audit_log_channel")
        if channel_id is None:
            return

        channel = guild.get_channel(int(channel_id))
        if channel is None or not hasattr(channel, "send"):
            print(
                f"Canal de registros {channel_id} não encontrado "
                f"no servidor {guild.id}.",
                flush=True,
            )
            return

        action_label = audit_action_label(entry.action)
        actor = entry.user
        target = self._get_audit_entry_target(entry)
        actor_text = (
            f"{actor.mention} (`{actor}` · `{actor.id}`)"
            if actor is not None
            else "Discord ou integração (responsável indisponível)"
        )
        target_text = (
            f"{target.mention} (`{target}` · `{target.id}`)"
            if isinstance(target, (discord.Member, discord.User, discord.Role))
            else (
                f"`{target}` (ID `{target.id}`)"
                if target is not None and hasattr(target, "id")
                else "Não informado pelo Discord"
            )
        )

        embed = discord.Embed(
            title=f"Registro de auditoria · {action_label}",
            color=discord.Color.blurple(),
            timestamp=entry.created_at,
        )
        embed.add_field(name="Responsável", value=actor_text, inline=False)
        embed.add_field(name="Alvo", value=target_text, inline=False)
        before = vars(entry.changes.before)
        after = vars(entry.changes.after)
        changed_values = []
        for key in dict.fromkeys((*before, *after)):
            old_value = before.get(key, "—")
            new_value = after.get(key, "—")
            if old_value == new_value:
                continue
            changed_values.append(
                f"**{key.replace('_', ' ').capitalize()}:** "
                f"`{str(old_value)[:180]}` → `{str(new_value)[:180]}`"
            )
        if changed_values:
            embed.add_field(
                name="Alterações",
                value="\n".join(changed_values)[:1024],
                inline=False,
            )
        if entry.reason:
            embed.add_field(name="Motivo", value=entry.reason[:1024], inline=False)
        embed.set_footer(
            text=f"Servidor: {guild.id} · Registro: {entry.id}"
        )

        try:
            await channel.send(
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.HTTPException) as error:
            print(
                f"Não foi possível enviar o registro de auditoria "
                f"{entry.id} no servidor {guild.id}: "
                f"{type(error).__name__}: {error}",
                flush=True,
            )

    def _get_audit_entry_target(
        self, entry: discord.AuditLogEntry
    ) -> object | None:
        try:
            return entry.target
        except TypeError as error:
            print(
                f"Registro de auditoria {entry.id} no servidor {entry.guild.id} "
                f"com alvo inválido ({entry.action}): {type(error).__name__}: {error}",
                flush=True,
            )
            return None

    async def cog_load(self) -> None:
        if CONFIG_PATH.exists():
            try:
                self.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                print(f"Não foi possível carregar as configurações locais: {error}")

        database_url = os.getenv("DATABASE") or os.getenv("DATABASE_URL")
        if not database_url:
            return
        try:
            self.pool = await asyncpg.create_pool(
                dsn=database_url,
                ssl="require",
                min_size=1,
                max_size=3,
                command_timeout=20,
            )
            await self.pool.execute(
                """
                CREATE TABLE IF NOT EXISTS hakari_guild_config (
                    guild_id BIGINT PRIMARY KEY,
                    config JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await self.pool.execute(
                """
                CREATE TABLE IF NOT EXISTS hakari_welcome_assets (
                    guild_id BIGINT NOT NULL,
                    asset_key TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    data BYTEA NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (guild_id, asset_key)
                )
                """
            )
            if self.config:
                await self.pool.executemany(
                    """
                    INSERT INTO hakari_guild_config (guild_id, config)
                    VALUES ($1, $2::jsonb)
                    ON CONFLICT (guild_id) DO NOTHING
                    """,
                    [
                        (int(guild_id), json.dumps(value))
                        for guild_id, value in self.config.items()
                    ],
                )
            rows = await self.pool.fetch(
                "SELECT guild_id, config FROM hakari_guild_config"
            )
            for row in rows:
                stored_config = row["config"]
                self.config[str(row["guild_id"])] = (
                    json.loads(stored_config)
                    if isinstance(stored_config, str)
                    else stored_config
                )
        except Exception as error:
            if self.pool is not None:
                await self.pool.close()
                self.pool = None
            print(
                "Não foi possível iniciar a persistência SQL do menu; "
                f"usando arquivo local ({type(error).__name__})."
            )

    async def save(self) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = CONFIG_PATH.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(self.config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary_path.replace(CONFIG_PATH)
        if self.pool is not None:
            try:
                await self.pool.executemany(
                    """
                    INSERT INTO hakari_guild_config (guild_id, config)
                    VALUES ($1, $2::jsonb)
                    ON CONFLICT (guild_id) DO UPDATE SET
                        config = EXCLUDED.config,
                        updated_at = NOW()
                    """,
                    [
                        (int(guild_id), json.dumps(value))
                        for guild_id, value in self.config.items()
                    ],
                )
            except Exception as error:
                print(
                    "Não foi possível salvar as configurações no SQL: "
                    f"{type(error).__name__}: {error}"
                )

    async def cog_unload(self) -> None:
        if self.pool is not None:
            await self.pool.close()

    def get_value(self, guild_id: int, key: str, default=None):
        return self.config.get(str(guild_id), {}).get("settings", {}).get(key, default)

    def ai_audio_voice_id(self, guild_id: int) -> str | None:
        value = self.get_value(guild_id, "ia_audio_voice_id")
        return value if isinstance(value, str) and value else None

    async def fetch_fish_audio_voices(self) -> list[dict[str, str | bool]]:
        api_key = os.getenv("FISH_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("A variável FISH_API_KEY não está configurada.")

        timeout = aiohttp.ClientTimeout(total=60, connect=10)
        available_voices = []
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for voice_spec in FISH_PUBLIC_VOICE_SPECS:
                matching_model = None
                if voice_spec.get("id"):
                    async with session.get(
                        f"https://api.fish.audio/model/{voice_spec['id']}",
                        headers={"Authorization": f"Bearer {api_key}"},
                    ) as response:
                        if response.status == 200:
                            model = await response.json()
                            if (
                                isinstance(model, dict)
                                and model.get("state") == "trained"
                                and model.get("type") == "tts"
                                and model.get("visibility") == "public"
                                and isinstance(model.get("_id"), str)
                            ):
                                matching_model = model
                        elif response.status != 404:
                            details = (await response.text())[:300]
                            raise RuntimeError(
                                "Fish Audio retornou HTTP "
                                f"{response.status} ao validar "
                                f"{voice_spec['label']}: {details}"
                            )
                        else:
                            print(
                                "Fish Audio não encontrou o ID fixado para "
                                f"{voice_spec['label']}; buscando pelo nome.",
                                flush=True,
                            )

                if matching_model is None:
                    for query in voice_spec.get("queries", ()):
                        async with session.get(
                            "https://api.fish.audio/model",
                            headers={"Authorization": f"Bearer {api_key}"},
                            params={
                                "self": "false",
                                "title": query,
                                "page_size": "50",
                                "sort_by": "score",
                            },
                        ) as response:
                            if response.status == 404:
                                continue
                            if response.status >= 400:
                                details = (await response.text())[:300]
                                raise RuntimeError(
                                    "Fish Audio retornou HTTP "
                                    f"{response.status} ao buscar "
                                    f"{voice_spec['label']}: {details}"
                                )
                            data = await response.json()

                        if not isinstance(data, dict) or not isinstance(
                            data.get("items"), list
                        ):
                            raise ValueError(
                                "A busca Fish Audio retornou um formato "
                                f"inválido para {voice_spec['label']}."
                            )

                        matching_model = next(
                            (
                                model
                                for model in data["items"]
                                if isinstance(model, dict)
                                and model.get("state") == "trained"
                                and model.get("type") == "tts"
                                and model.get("visibility") == "public"
                                and isinstance(model.get("_id"), str)
                                and any(
                                    term.casefold()
                                    in (model.get("title") or "").casefold()
                                    for term in voice_spec["match_terms"]
                                )
                            ),
                            None,
                        )
                        if matching_model is not None:
                            break

                if matching_model is None:
                    print(
                        f"Personagem indisponível na Fish Audio, não será exibido: {voice_spec['label']}",
                        flush=True,
                    )
                    continue

                available_voices.append(
                    {
                        "id": matching_model["_id"],
                        "label": voice_spec["label"],
                        "default": voice_spec.get("default", False),
                    }
                )

        return available_voices

    async def set_values(self, guild_id: int, values: dict) -> None:
        guild_config = self.config.setdefault(str(guild_id), {})
        guild_config.setdefault("settings", {}).update(values)
        await self.save()

    async def set_value(self, guild_id: int, key: str, value) -> None:
        guild_config = self.config.setdefault(str(guild_id), {})
        guild_config.setdefault("settings", {})[key] = value
        await self.save()

    def welcome_asset_path(self, guild_id: int, asset_key: str, filename: str) -> Path:
        suffix = Path(filename).suffix.lower()
        return WELCOME_ASSETS_DIR / f"{guild_id}_{asset_key}{suffix}"

    async def store_welcome_asset(
        self, guild_id: int, asset_key: str, attachment: discord.Attachment
    ) -> str:
        if asset_key not in {
            "welcome_thumbnail",
            "welcome_image",
            "welcome_author_icon",
        }:
            raise ValueError("Tipo de imagem inválido.")
        suffix = Path(attachment.filename).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            raise ValueError("Envie uma imagem PNG, JPG, WEBP ou GIF.")
        if attachment.size > 8 * 1024 * 1024:
            raise ValueError("Cada imagem deve ter no máximo 8 MB.")
        data = await attachment.read()
        if not data or len(data) > 8 * 1024 * 1024:
            raise ValueError("Não consegui ler a imagem ou ela excede 8 MB.")
        valid_image = (
            suffix == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n")
        ) or (
            suffix in {".jpg", ".jpeg"} and data.startswith(b"\xff\xd8\xff")
        ) or (
            suffix == ".webp"
            and data.startswith(b"RIFF")
            and data[8:12] == b"WEBP"
        ) or (suffix == ".gif" and data.startswith((b"GIF87a", b"GIF89a")))
        if not valid_image:
            raise ValueError("O conteúdo do arquivo não corresponde a uma imagem suportada.")

        if self.pool is not None:
            await self.pool.execute(
                """
                INSERT INTO hakari_welcome_assets (guild_id, asset_key, filename, data)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (guild_id, asset_key) DO UPDATE SET
                    filename = EXCLUDED.filename,
                    data = EXCLUDED.data,
                    updated_at = NOW()
                """,
                guild_id,
                asset_key,
                Path(attachment.filename).name,
                data,
            )
        else:
            asset_path = self.welcome_asset_path(
                guild_id, asset_key, attachment.filename
            )
            asset_path.parent.mkdir(parents=True, exist_ok=True)
            asset_path.write_bytes(data)

        await self.set_value(
            guild_id, f"{asset_key}_filename", Path(attachment.filename).name
        )
        return Path(attachment.filename).name

    async def get_welcome_asset(
        self, guild_id: int, asset_key: str
    ) -> tuple[str, bytes] | None:
        if asset_key not in {
            "welcome_thumbnail",
            "welcome_image",
            "welcome_author_icon",
        }:
            return None
        filename = self.get_value(guild_id, f"{asset_key}_filename")
        if not filename:
            return None
        if self.pool is not None:
            row = await self.pool.fetchrow(
                """
                SELECT filename, data FROM hakari_welcome_assets
                WHERE guild_id = $1 AND asset_key = $2
                """,
                guild_id,
                asset_key,
            )
            if row:
                return row["filename"], bytes(row["data"])
        asset_path = self.welcome_asset_path(guild_id, asset_key, filename)
        if not asset_path.exists():
            return None
        return filename, asset_path.read_bytes()

    def access_for(self, guild_id: int) -> list[int]:
        return self.config.get(str(guild_id), {}).get("menu_users", [])

    async def set_access(self, guild_id: int, users: set[int]) -> None:
        guild_config = self.config.setdefault(str(guild_id), {})
        guild_config["menu_users"] = sorted(users - {DEVELOPER_ID})
        await self.save()

    def can_access(self, user_id: int, guild_id: int) -> bool:
        guild = self.bot.get_guild(guild_id)
        return (
            user_id == DEVELOPER_ID
            or (guild is not None and guild.owner_id == user_id)
            or user_id in self.access_for(guild_id)
        )

    def can_manage_access(
        self, user_id: int, guild: discord.Guild | None
    ) -> bool:
        return user_id == DEVELOPER_ID or (
            guild is not None and guild.owner_id == user_id
        )

    def module_configured(self, guild_id: int, module: str) -> bool:
        if module not in MODULES or not self.get_value(
            guild_id, f"module_{module}", False
        ):
            return False
        if module == "ia_audio":
            return self.ai_audio_voice_id(guild_id) is not None
        if module == "boost":
            required_settings = (
                "booster_role",
                "vip_full_role",
                "vip_personal_role",
                "role_position_upper",
                "role_position_lower",
                "family_position_lower",
                "repair_below_role",
            )
            return all(
                self.get_value(guild_id, key) is not None
                for key in required_settings
            )
        if module == "welcome":
            return bool(
                self.get_value(guild_id, "welcome_channel")
                and self.get_value(guild_id, "welcome_embed_description")
            )
        if module == "insta":
            return bool(self.get_value(guild_id, "insta_channel"))
        if module == "roblox":
            return bool(self.get_value(guild_id, "roblox_channel"))
        return True

    def overview_embed(self, guild: discord.Guild) -> discord.Embed:
        embed = discord.Embed(
            title="salve salve meu cria, tudo na paz? vai querer configurar o que pro Hakari hoje?",
            description=(
                "encontrou um b.o no bot? chame o [Salvador](https://discord.com/users/1344736884089426022)"
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Veja algumas sugestões:",
            value=(
                "1. **Instagram**\n"
                "configure o Insta no seu servidor!\n"
                "2. **Avatar Roblox**\n"
                "configure o módulo de mostrar avatares Roblox!\n"
                "3. **E muito mais está por vir...**\n"
                "mas você tem que ter paciência hein! **fazer um bot Discord NÃO é fácil.**"
            ),
            inline=False,
        )
        embed.add_field(
            name="Website",
            value=(
                "Conheça o site oficial com mais informações sobre o bot."
            ),
            inline=False,
        )
        embed.add_field(
            name="Escolha por onde começar",
            value=(
                "Só você pode usar os elementos neste painel — "
                "apenas o desenvolvedor ou você que tem acesso ao painel pode conceder acesso clicando em `Gerenciar acessos`."
            ),
            inline=False,
        )
        if self.bot.user:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_image(url=self.banner_url())
        embed.set_footer(
            text="six seven"
        )
        return embed

    @staticmethod
    def banner_url() -> str:
        return FALLBACK_MENU_BANNER

    def invite_link(self, guild: discord.Guild) -> str:
        if guild.vanity_url:
            return guild.vanity_url
        return self.invites.get(guild.id, "Gerando convite...")

    async def ensure_invite(self, guild: discord.Guild) -> None:
        if guild.vanity_url or guild.id in self.invites:
            return
        for channel in guild.text_channels:
            permissions = channel.permissions_for(guild.me) if guild.me else None
            if permissions and permissions.create_instant_invite:
                try:
                    invite = await channel.create_invite(
                        max_age=0,
                        max_uses=0,
                        unique=False,
                        reason="Link exibido no painel de configuração do bot",
                    )
                    self.invites[guild.id] = invite.url
                    return
                except discord.HTTPException:
                    continue
        self.invites[guild.id] = "Sem permissão para gerar convite"

    def access_embed(self, guild: discord.Guild) -> discord.Embed:
        users = self.access_for(guild.id)
        mentions = "\n".join(f"<@{user_id}>" for user_id in users) or "Nenhum usuário adicional"
        embed = discord.Embed(
            title=f"Acessos do menu | {guild.name}",
            description=(
                f"**Desenvolvedor:** <@{DEVELOPER_ID}>\n"
                f"**Acesso neste servidor:**\n{mentions}"
            ),
            color=discord.Color.blurple(),
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id is None or not self.can_access(interaction.user.id, interaction.guild_id):
            await interaction.response.send_message(
                "Você não tem permissão para acessar o painel neste servidor.",
                ephemeral=True,
            )
            return False
        return True

    def restricted_embed(self, guild_id: int | None = None) -> discord.Embed:
        embed = discord.Embed(
            title="Área Restrita do Desenvolvedor",
            description=(
                "Painel de operações globais e por servidor. Escolha uma ação e "
                "revise a confirmação antes de executá-la."
            ),
            color=discord.Color.red(),
        )
        embed.add_field(
            name="📡 Estado do bot",
            value=(
                f"**Servidores:** {len(self.bot.guilds)}\n"
                f"**Latência:** {round(self.bot.latency * 1000)} ms\n"
                f"**Servidor do painel:** `{guild_id}`"
                if guild_id is not None
                else (
                    f"**Servidores:** {len(self.bot.guilds)}\n"
                    f"**Latência:** {round(self.bot.latency * 1000)} ms"
                )
            ),
            inline=True,
        )
        embed.add_field(
            name="🧰 Ações disponíveis",
            value=(
                "• Desligar o bot\n"
                "• Dessincronizar um comando global\n"
                "• Resetar as configurações de todos os servidores\n"
                "• Sincronizar comandos globais\n"
                "• Sair de um servidor e apagar somente os dados dele\n"
                "Para essa ação, selecione um servidor; use a paginação para ver todos."
            ),
            inline=True,
        )
        embed.add_field(
            name="🧩 Cogs carregadas",
            value=(", ".join(self.bot.cogs.keys()) or "Nenhuma")[:1024],
            inline=False,
        )
        embed.set_footer(
            text="Apenas o desenvolvedor pode usar este painel · ações destrutivas exigem confirmação"
        )
        return embed

    async def execute_restricted_action(
        self,
        actor_id: int,
        action: str,
        command_name: str,
        target_guild_id: int | None = None,
    ) -> str:
        if actor_id != DEVELOPER_ID:
            raise PermissionError("ACESSO NEGADO: ÁREA EXCLUSIVA DO DESENVOLVEDOR.")
        if action == "shutdown":
            return "Encerrando o bot."
        if action == "leave_server":
            if target_guild_id is None:
                raise ValueError("Informe o servidor do qual o bot deve sair.")
            guild = self.bot.get_guild(target_guild_id)
            if guild is None:
                raise ValueError(
                    f"O bot não está conectado ao servidor `{target_guild_id}`."
                )
            await self.reset_guild_config(target_guild_id)
            self.invites.pop(target_guild_id, None)
            await guild.leave()
            return (
                f"O bot saiu de **{guild.name}** (`{target_guild_id}`); "
                "as configurações do `/menu`, permissões de acesso e imagens "
                "de boas-vindas desse servidor foram apagadas."
            )
        if action == "reset":
            if self.pool is not None:
                await self.pool.execute("DELETE FROM hakari_guild_config")
                await self.pool.execute("DELETE FROM hakari_welcome_assets")
            self.config.clear()
            shutil.rmtree(WELCOME_ASSETS_DIR, ignore_errors=True)
            await self.save()
            return "Configurações do painel e permissões de acesso resetadas em todos os servidores."
        if action == "sync":
            global_count, synced_guilds, total_guilds = (
                await self.bot.sync_all_slash_commands()
            )
            return (
                f"{global_count} comandos globais sincronizados e copiados para "
                f"{synced_guilds}/{total_guilds} servidores."
            )
        if action == "unsync":
            command = self.bot.tree.get_command(command_name)
            if command is None:
                raise ValueError(f"O comando `/{command_name}` não está registrado localmente.")
            self.bot.tree.remove_command(command_name)
            try:
                synced_commands = await self.bot.tree.sync()
                synced_guilds, total_guilds = (
                    await self.bot.sync_commands_to_all_guilds()
                )
            except Exception:
                self.bot.tree.add_command(command)
                await self.bot.tree.sync()
                await self.bot.sync_commands_to_all_guilds()
                raise
            return (
                f"`/{command_name}` removido globalmente e das guilds; "
                f"restam {len(synced_commands)} comandos globais. "
                f"Sincronização de guilds: {synced_guilds}/{total_guilds}."
            )
        raise ValueError("Ação restrita desconhecida.")

    async def reset_guild_config(self, guild_id: int) -> None:
        if self.pool is not None:
            async with self.pool.acquire() as connection:
                async with connection.transaction():
                    await connection.execute(
                        "DELETE FROM hakari_guild_config WHERE guild_id = $1",
                        guild_id,
                    )
                    await connection.execute(
                        "DELETE FROM hakari_welcome_assets WHERE guild_id = $1",
                        guild_id,
                    )

        self.config.pop(str(guild_id), None)
        for asset_key in (
            "welcome_thumbnail",
            "welcome_image",
            "welcome_author_icon",
        ):
            for suffix in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
                asset_path = WELCOME_ASSETS_DIR / (
                    f"{guild_id}_{asset_key}{suffix}"
                )
                try:
                    asset_path.unlink()
                except FileNotFoundError:
                    pass
        await self.save()

    @app_commands.command(name="menu", description="Abre o painel avançado de configuração do servidor")
    @app_commands.guild_only()
    async def menu_command(self, interaction: discord.Interaction) -> None:
        if not self.can_access(interaction.user.id, interaction.guild_id):
            return await interaction.response.send_message(
                "Você não tem permissão para acessar o painel neste servidor.",
                ephemeral=True,
            )
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.ensure_invite(interaction.guild)
        view = MenuView(self, interaction.guild_id, interaction.user.id)
        await interaction.followup.send(
            view=components_v2(
                view.embed(interaction.guild),
                view=view,
            ),
            ephemeral=True,
        )

    @app_commands.command(name="menu_sync", description="Atualiza os comandos globais do bot")
    @app_commands.guild_only()
    async def sync_command(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != DEVELOPER_ID:
            return await interaction.response.send_message(
                "Somente o desenvolvedor pode atualizar os comandos.", ephemeral=True
            )
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            global_count, synced_guilds, total_guilds = (
                await self.bot.sync_all_slash_commands()
            )
        except discord.HTTPException as error:
            return await interaction.followup.send(
                f"Falha ao sincronizar comandos: {error}", ephemeral=True
            )
        await interaction.followup.send(
            f"{global_count} comandos globais sincronizados e copiados para "
            f"{synced_guilds}/{total_guilds} servidores.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Menu(bot))