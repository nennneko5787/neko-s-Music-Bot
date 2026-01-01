import asyncio
import os
from typing import Any

import asyncpg
import dotenv
import orjson

dotenv.load_dotenv()


class DBService:
    pool: asyncpg.Pool = None

    @classmethod
    def jsonDumps(cls, obj: Any):
        data = orjson.dumps(obj)
        if not isinstance(obj, bytes):
            data = data.decode()
        return data

    @classmethod
    def jsonLoads(cls, obj: Any):
        if isinstance(obj, str):
            obj = obj.encode()
        return orjson.loads(obj)

    @classmethod
    async def initConnection(cls, conn: asyncpg.Connection):
        await conn.set_type_codec(
            "json", schema="pg_catalog", encoder=cls.jsonDumps, decoder=cls.jsonLoads
        )
        await conn.set_type_codec(
            "jsonb", schema="pg_catalog", encoder=cls.jsonDumps, decoder=cls.jsonLoads
        )

    @classmethod
    async def start(cls):
        cls.pool = await asyncpg.create_pool(os.getenv("dsn"), init=cls.initConnection)

    @classmethod
    async def shutdown(cls):
        async with asyncio.timeout(10):
            await cls.pool.close()
