#!/usr/bin/env python3
"""从 .env 的 QLFILE_PATH 中读取顶层子目录名称，并将结果写入项目根的 prompt/DIR.txt。"""
import os
import dotenv
from typing import List


def list_directories(base_path: str) -> List[str]:
    """返回 base_path 下的顶层目录名（不递归）。"""
    names = []
    try:
        with os.scandir(base_path) as it:
            for entry in it:
                if entry.is_dir():
                    names.append(entry.name)
    except FileNotFoundError:
        raise
    return sorted(names)


def write_dir_file(names: List[str], out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for n in names:
            f.write(n + "\n")


def main() -> int:
    dotenv.load_dotenv(override=False)
    ql_base = os.getenv("QLFILE_PATH")
    if not ql_base:
        print("QLFILE_PATH 未在环境变量或 .env 中找到")
        return 1
    ql_base = os.path.expanduser(ql_base)
    ql_base = os.path.abspath(ql_base)
    if not os.path.isdir(ql_base):
        print(f"QLFILE_PATH 路径不存在或不是目录: {ql_base}")
        return 1

    try:
        dirs = list_directories(ql_base)
    except Exception as e:
        print(f"列出目录失败: {e}")
        return 1

    # 输出到项目根的 prompt/DIR.txt
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    out_path = os.path.join(project_root, "prompt", "DIR.txt")

    try:
        write_dir_file(dirs, out_path)
        print(f"已将 {len(dirs)} 个目录写入: {out_path}")
    except Exception as e:
        print(f"写入文件失败: {e}")
        return 1

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
