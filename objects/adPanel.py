"""
広告用 LayoutView(Components V2)。SPEC_FEATURE_ADS.md §4.1。

Container(gold accent) 内に
  ## <title> / <description> / MediaGallery / [LinkButton] / Separator / -# 広告 / Ad
を並べる。timeout=None、custom_id を持つ Button は含まないため
buttonHandler の網羅性契約とは干渉しない。
"""
from __future__ import annotations

import discord

from .ad import Ad


class AdView(discord.ui.LayoutView):
    def __init__(self, ad: Ad) -> None:
        super().__init__(timeout=None)

        # linkUrl が与えられていればタイトル自体をハイパーリンク化する。
        # LinkButton も併設するので二重の導線になるが、モバイル/デスクトップ双方で
        # 見つけやすくする狙い。
        titleText = (
            f"## [{ad.title}]({ad.linkUrl})" if ad.linkUrl else f"## {ad.title}"
        )

        items: list[discord.ui.Item] = [
            discord.ui.TextDisplay(titleText),
            discord.ui.TextDisplay(ad.description),
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(media=ad.imageUrl, description=ad.title)
            ),
        ]

        if ad.linkUrl:
            items.append(
                discord.ui.ActionRow(
                    discord.ui.Button(
                        style=discord.ButtonStyle.link,
                        url=ad.linkUrl,
                        label="詳しく見る",
                    )
                )
            )

        items.append(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        items.append(discord.ui.TextDisplay("-# 広告 / Ad"))

        container = discord.ui.Container(
            *items,
            accent_color=discord.Color.gold(),
        )
        self.add_item(container)
