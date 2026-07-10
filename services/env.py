import os

import dotenv

dotenv.load_dotenv()


def getEnv(key: str) -> str:
    value = os.getenv(key)

    if not value:
        raise KeyError(f'The environment "{key}" was not found')

    return value
