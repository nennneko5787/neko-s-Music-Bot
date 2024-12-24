def formatTime(seconds: int) -> str:
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return (
        f"{days}:{hours:02}:{minutes:02}:{seconds:02}"
        if days
        else f"{hours}:{minutes:02}:{seconds:02}"
    )


def clamp(value, min_value, max_value):
    """
    指定した範囲内に数値を制限する関数。

    :param value: 制限したい数値
    :param min_value: 最小値
    :param max_value: 最大値
    :return: 制限された数値
    """
    return max(min_value, min(value, max_value))
