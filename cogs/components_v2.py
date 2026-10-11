from __future__ import annotations

from collections.abc import Iterable

import discord


class ComponentsV2View(discord.ui.LayoutView):
    def __init__(self, *, timeout: float | None = 180):
        super().__init__(timeout=timeout)
        self._message_components: list[discord.ui.Item] = []
        self._control_rows: dict[int, discord.ui.ActionRow] = {}

    def add_item(self, item: discord.ui.Item) -> ComponentsV2View:
        if isinstance(item, (discord.ui.Button, discord.ui.Select)):
            row_index = item.row
            if row_index is None:
                row_index = next(
                    (
                        index
                        for index, row in self._control_rows.items()
                        if sum(child.width for child in row.children) + item.width <= 5
                    ),
                    max(self._control_rows, default=-1) + 1,
                )
            row = self._control_rows.get(row_index)
            if row is None:
                row = discord.ui.ActionRow()
                super().add_item(row)
                self._control_rows[row_index] = row
            row.add_item(item)
            return self

        super().add_item(item)
        return self

    def clear_items(self) -> ComponentsV2View:
        for item in list(self.children):
            if item not in self._message_components:
                self.remove_item(item)
        self._control_rows.clear()
        return self

    def set_message(
        self,
        embeds: discord.Embed | Iterable[discord.Embed] | None = None,
        *,
        content: str | None = None,
    ) -> ComponentsV2View:
        for item in self._message_components:
            self.remove_item(item)
        self._message_components.clear()

        if content:
            self._message_components.append(
                discord.ui.Container(discord.ui.TextDisplay(content))
            )

        if isinstance(embeds, discord.Embed):
            embeds = (embeds,)
        for embed in embeds or ():
            container = self._container_for_embed(embed)
            if container is not None:
                self._message_components.append(container)

        control_rows = list(self._control_rows.values())
        for row in control_rows:
            self.remove_item(row)
        for item in self._message_components:
            super().add_item(item)
        for row in control_rows:
            super().add_item(row)
        if self.content_length() > 4000:
            raise ValueError("Components V2 messages cannot exceed 4000 text characters.")
        return self

    @staticmethod
    def _container_for_embed(embed: discord.Embed) -> discord.ui.Container | None:
        data = embed.to_dict()
        text: list[str] = []

        author = data.get("author")
        if author and author.get("name"):
            name = author["name"]
            if author.get("url"):
                name = f"[{name}]({author['url']})"
            text.append(f"**{name}**")

        title = data.get("title")
        if title:
            if data.get("url"):
                title = f"[{title}]({data['url']})"
            text.append(f"# {title}")

        if data.get("description"):
            text.append(data["description"])

        for field in data.get("fields", ()):
            text.append(f"**{field['name']}**\n{field['value']}")

        footer = data.get("footer")
        if footer and footer.get("text"):
            text.append(f"-# {footer['text']}")
        if embed.timestamp:
            text.append(f"-# <t:{int(embed.timestamp.timestamp())}:F>")

        children: list[discord.ui.Item] = []
        combined_text = "\n\n".join(text)
        while combined_text:
            chunk = combined_text[:4000]
            split_at = chunk.rfind("\n")
            if len(combined_text) > 4000 and split_at > 0:
                chunk = combined_text[:split_at]
            children.append(discord.ui.TextDisplay(chunk))
            combined_text = combined_text[len(chunk):].lstrip()

        media_urls = []
        for key in ("thumbnail", "image"):
            media = data.get(key)
            if media and media.get("url"):
                media_urls.append(media["url"])
        if author and author.get("icon_url"):
            media_urls.append(author["icon_url"])
        if media_urls:
            gallery = discord.ui.MediaGallery()
            for url in media_urls[:10]:
                gallery.add_item(media=url)
            children.append(gallery)

        if not children:
            children.append(discord.ui.TextDisplay("\u200b"))

        return discord.ui.Container(*children, accent_color=embed.color.value if embed.color else None)


def components_v2(
    embeds: discord.Embed | Iterable[discord.Embed] | None = None,
    *,
    view: ComponentsV2View | None = None,
    content: str | None = None,
) -> ComponentsV2View:
    if view is None:
        view = ComponentsV2View()
    elif not isinstance(view, ComponentsV2View):
        raise TypeError("Components V2 messages require a ComponentsV2View.")
    return view.set_message(embeds, content=content)
