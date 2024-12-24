import time


def formatTime(seconds: int):
    if seconds < 3600:
        return time.strftime("%M:%S", time.gmtime(seconds))
    elif seconds < 86400:
        return time.strftime("%H:%M:%S", time.gmtime(seconds))
    else:
        return time.strftime("%d:%H:%M:%S", time.gmtime(seconds))


def clamp(value: float | int, min_value: float | int, max_value: float | int):
    """
    指定した範囲内に数値を制限する関数。

    :param value: 制限したい数値
    :param min_value: 最小値
    :param max_value: 最大値
    :return: 制限された数値
    """
    return max(min_value, min(value, max_value))
