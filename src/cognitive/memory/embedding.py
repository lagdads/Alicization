"""文件职责：提供文本向量化与相似度计算工具。
简明实现逻辑：使用简单哈希分桶构造向量，并计算余弦相似度。
输入输出：输入为文本或向量；输出为向量或相似度分数。"""

import hashlib
import math
from typing import Iterable, List


def _hash_token(token: str) -> int:
    """对 token 进行哈希，返回整数。"""
    digest = hashlib.md5(token.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _tokenize(text: str) -> List[str]:
    """按空白切分并归一化文本。"""
    return [token for token in text.lower().split() if token]


def embed_text(text: str, dim: int) -> List[float]:
    """用哈希分桶方式生成稀疏向量并归一化。"""
    vector = [0.0] * dim
    tokens = _tokenize(text)
    if not tokens:
        return vector
    for token in tokens:
        index = _hash_token(token) % dim
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:
        return vector
    return [value / norm for value in vector]


def cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    """计算两个向量的余弦相似度。"""
    a_list = list(a)
    b_list = list(b)
    if not a_list or not b_list:
        return 0.0
    dot = sum(x * y for x, y in zip(a_list, b_list))
    norm_a = math.sqrt(sum(x * x for x in a_list))
    norm_b = math.sqrt(sum(y * y for y in b_list))
    if norm_a <= 0 or norm_b <= 0:
        return 0.0
    return dot / (norm_a * norm_b)
