"""文件职责：记忆衰减计算工具。
简明实现逻辑：使用艾宾浩斯指数衰减公式更新强度。
输入输出：输入为强度/衰减率/时间差；输出为衰减后的强度。"""

import math


def apply_ebbinghaus_decay(strength: float, decay_rate: float, dt: float) -> float:
    """根据艾宾浩斯公式计算衰减后的强度。"""
    if dt <= 0:
        return strength
    return strength * math.exp(-decay_rate * dt)
