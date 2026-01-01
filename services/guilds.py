from objects.guilds import GuildData

from .db import DBService


async def createGuild(guildId: int) -> GuildData:
    row = await DBService.pool.fetchrow(
        "INSERT INTO guilds (id) VALUES ($1) RETURNING *", guildId
    )

    return GuildData.model_validate(dict(row))


async def getGuild(guildId: int) -> GuildData:
    row = await DBService.pool.fetchrow("SELECT * FROM guilds WHERE id = $1", guildId)

    if not row:
        return await createGuild(guildId)

    return GuildData.model_validate(dict(row))


async def updateGuild(guild: GuildData):
    await DBService.pool.execute(
        """
            UPDATE only guilds
            SET played_musics = $2
            WHERE id = $1
        """,
        guild.id,
        [m.model_dump() for m in guild.playedMusics],
    )
