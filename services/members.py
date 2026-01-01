from objects.members import MemberData

from .db import DBService


async def createMember(memberId: int):
    row = await DBService.pool.fetchrow(
        "INSERT INTO members (id) VALUES ($1) RETURNING *", memberId
    )

    return MemberData.model_validate(dict(row))


async def getMember(memberId: int):
    row = await DBService.pool.fetchrow("SELECT * FROM members WHERE id = $1", memberId)

    if not row:
        return await createMember(memberId)

    return MemberData.model_validate(dict(row))


async def updateMember(member: MemberData):
    await DBService.pool.execute(
        """
            UPDATE only members
            SET expires_at = $2
            WHERE id = $1
        """,
        member.id,
        member.expiresAt,
    )
