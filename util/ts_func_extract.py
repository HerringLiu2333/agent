import re
from typing import List, Tuple

_HUNK_RE = re.compile(
    r"@@\s*-(?P<old_start>\d+)(?:,(?P<old_count>\d+))?\s+\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))?\s*@@"
)


def extract_old_ranges(patch_diff: str) -> List[Tuple[int, int]]:
    """从统一 diff 的 @@ 块中提取旧文件的行号区间。

    返回若干 (old_start, old_end)，其中 end = start + count - 1。
    当 old_count 为 0（纯插入）时，old_end = old_start - 1。
    当 old_count 省略时，默认按 1 处理。
    """
    if not patch_diff:
        return []
    ranges: List[Tuple[int, int]] = []
    for m in _HUNK_RE.finditer(patch_diff):
        old_start = int(m.group("old_start"))
        old_count_str = m.group("old_count")
        old_count = int(old_count_str) if old_count_str is not None else 1
        old_end = old_start + old_count - 1 if old_count > 0 else old_start - 1
        ranges.append((old_start, old_end))
    return ranges


def print_old_ranges(patch_diff: str) -> None:
    """按 "oldstart=<n>, oldend=<m>" 格式打印每个 hunk 的旧文件行号区间。"""
    for old_start, old_end in extract_old_ranges(patch_diff):
        print(f"oldstart={old_start}, oldend={old_end}")


# ---------------- Tree-sitter based function block extraction ---------------- #
import tree_sitter_c as tsc
from tree_sitter import Language, Parser

C_LANGUAGE = Language(tsc.language())
parser = Parser(C_LANGUAGE)


def _collect_function_defs(node, out):
    """DFS 收集语法树中的 function_definition 节点。"""
    if node.type == "function_definition":
        out.append(node)
    for i in range(len(node.children)):
        _collect_function_defs(node.children[i], out)


def _build_line_offsets(text: str) -> Tuple[List[int], List[str]]:
    """构建每一行起始的字节偏移，用于行号到字节范围的映射。"""
    lines = text.splitlines(True)
    offsets: List[int] = []
    pos = 0
    for ln in lines:
        offsets.append(pos)  # 行号从 1 开始，行 i 的偏移为 offsets[i-1]
        pos += len(ln)
    return offsets, lines


# 通用宏定义块匹配：匹配形如 MACRO_NAME(...){...} 的大写宏，并提取其完整代码块
_MACRO_HEAD_RE = re.compile(r"^\s*[A-Z_][A-Z0-9_]*\s*\(", re.M)


def _find_macro_blocks(source_text: str) -> List[Tuple[int, int]]:
    """查找所有形如 MACRO_NAME(...){...} 的宏定义代码块，返回 (start_byte, end_byte)。

    策略：
    - 使用正则匹配以大写开头的宏调用行（如 SYSCALL_DEFINE5(...)、FOO_BAR(...) 等）。
    - 从匹配位置开始向后找到第一个 '{'，并进行大括号配对直到对应的 '}'。
    - 仅当找到了成对的大括号时，才认为是一个完整的宏代码块。
    - 注意：不会解析宏展开内部的语义，仅做文本层面的括号匹配。
    """
    blocks: List[Tuple[int, int]] = []
    if not source_text:
        return blocks

    text = source_text
    for m in _MACRO_HEAD_RE.finditer(text):
        start_char = m.start()
        brace_pos = text.find('{', m.end())
        if brace_pos == -1:
            continue
        depth = 0
        i = brace_pos
        end_char = None
        while i < len(text):
            ch = text[i]
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end_char = i + 1
                    break
            i += 1
        if end_char is None:
            continue
        start_b = len(text[:start_char].encode('utf-8', errors='ignore'))
        end_b = len(text[:end_char].encode('utf-8', errors='ignore'))
        blocks.append((start_b, end_b))
    return blocks


def find_functions_for_patch(source_text: str, patch_diff: str) -> List[str]:
    """解析源码，返回覆盖补丁旧行区间的完整函数或宏定义代码块列表。

    - 从补丁解析 (oldstart, oldend)。
    - 使用 tree-sitter 查找与区间相交的 function_definition，并打印完整函数文本。
    - 同时扫描并匹配所有形如 MACRO_NAME(...){...} 的宏定义块，若与区间相交也打印。
    - 若多个 hunk 命中同一代码块，去重后仅打印一次。
    """
    if not source_text or not patch_diff:
        return []

    ranges = extract_old_ranges(patch_diff)
    if not ranges:
        return []

    source_bytes = source_text.encode("utf-8", errors="ignore")
    tree = parser.parse(source_bytes)
    func_nodes = []
    _collect_function_defs(tree.root_node, func_nodes)
    macro_blocks = _find_macro_blocks(source_text)

    line_offsets, lines = _build_line_offsets(source_text)
    total_len = len(source_bytes)

    def range_to_bytes(old_start: int, old_end: int) -> Tuple[int, int]:
        # 纯插入（old_count=0）时，取 old_start 行起点作为锚，构造极小区间
        if old_end < old_start:
            anchor_idx = max(1, old_start)
            start_byte = line_offsets[anchor_idx - 1] if anchor_idx - 1 < len(line_offsets) else total_len
            return start_byte, min(start_byte + 1, total_len)
        start_idx = max(1, old_start)
        end_idx = max(old_start, old_end)
        start_byte = line_offsets[start_idx - 1] if start_idx - 1 < len(line_offsets) else total_len
        if end_idx - 1 < len(line_offsets):
            end_line = lines[end_idx - 1]
            end_byte = line_offsets[end_idx - 1] + len(end_line)
        else:
            end_byte = total_len
        return start_byte, min(end_byte, total_len)

    seen_funcs = set()
    snippets: List[str] = []
    for old_start, old_end in ranges:
        rs, re = range_to_bytes(old_start, old_end)
        if re <= rs:
            continue
        # 命中普通函数定义
        for fn in func_nodes:
            if not (fn.end_byte <= rs or fn.start_byte >= re):  # intersects
                key = (fn.start_byte, fn.end_byte)
                if key in seen_funcs:
                    continue
                seen_funcs.add(key)
                snippet = source_bytes[fn.start_byte:fn.end_byte].decode("utf-8", errors="ignore")
                snippets.append(snippet)
        # 命中宏定义函数块（通用大写宏）
        for mb_start, mb_end in macro_blocks:
            if not (mb_end <= rs or mb_start >= re):
                key = (mb_start, mb_end)
                if key in seen_funcs:
                    continue
                seen_funcs.add(key)
                snippet = source_bytes[mb_start:mb_end].decode("utf-8", errors="ignore")
                snippets.append(snippet)
    return snippets