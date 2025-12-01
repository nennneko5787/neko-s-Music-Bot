def formatTime(seconds):
    seconds = int(max(0, seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    if d > 0:
        return f"{d:02}:{h:02}:{m:02}:{s:02}"
    elif h > 0:
        return f"{h:02}:{m:02}:{s:02}"
    else:
        return f"{m:02}:{s:02}"


def clamp(value: float | int, min_value: float | int, max_value: float | int):
    """
    指定した範囲内に数値を制限する関数。

    :param value: 制限したい数値
    :param min_value: 最小値
    :param max_value: 最大値
    :return: 制限された数値
    """
    return max(min_value, min(value, max_value))
