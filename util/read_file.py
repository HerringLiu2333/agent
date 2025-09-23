import os
from typing import Union

class FileReadError(Exception):
    pass

def read_text(path: Union[str, os.PathLike], encoding: str = "utf-8") -> str:
    """读取文本文件内容并返回字符串。

    参数:
        path: 文件绝对路径或相对路径。
        encoding: 文本编码，默认 utf-8。

    返回:
        文件全部文本内容。

    Raises:
        FileNotFoundError: 文件不存在。
        FileReadError: 其他 IO 错误。
    """
    path = os.fspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"文件不存在: {path}")
    try:
        with open(path, "r", encoding=encoding) as f:
            return f.read()
    except UnicodeDecodeError as e:
        raise FileReadError(f"解码失败（尝试编码 {encoding}）: {e}") from e
    except OSError as e:
        raise FileReadError(f"读取文件失败: {e}") from e

__all__ = ["read_text", "FileReadError"]
