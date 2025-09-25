import json
import re
import os
import subprocess
from typing import Dict, Optional, List, Tuple
from .prompt_pack import generate_prompt_files
from .read_file import read_text
import dotenv
from .ts_func_extract import find_functions_for_patch

# 正则模式：匹配形如 " * @key value" 的行（允许前导空格和星号）
_KEY_VALUE_RE = re.compile(r"^\s*\*\s*@([a-zA-Z0-9_.-]+)\s+(.*)$")
# patch-diff 的起始行形如:  * @patch-diff |
_PATCH_DIFF_START_RE = re.compile(r"^\s*\*\s*@patch-diff\s*\|\s*$")
_PATCH_DESCRIPTION_START_RE = re.compile(r"^\s*\*\s*@patch-description\s*\|\s*$")

TARGET_KEYS = {
    "name": "name",
    "patch-commit": "patch_commit",
    "source-file": "source_file",
}


def extract_cve_meta(path: str) -> Dict[str, Optional[str]]:
    """从指定文件读取注释块提取 CVE 元数据。

    返回字段: name, patch_commit, source_file, patch_diff
    若缺失则为 None。
    patch_diff 可能包含多行，保持原始缩进但去掉前导 " * " 结构。
    """
    content = read_text(path)

    # 只解析第一个以 "/**" 开始并以 "*/" 结束的注释块
    start = content.find("/**")
    end = content.find("*/", start + 3)
    if start == -1 or end == -1:
        return {"name": None, "patch_commit": None, "source_file": None, "patch_diff": None}

    block = content[start:end].splitlines()

    meta: Dict[str, Optional[str]] = {"name": None, "patch_commit": None, "source_file": None, "patch_diff": None, "patch_description": None}

    collecting_patch_diff = False
    collecting_patch_description = False
    patch_diff_lines: List[str] = []
    patch_description_lines: List[str] = []

    for line in block:
        # 优先处理正在收集的多行块
        if collecting_patch_diff or collecting_patch_description:
            if line.strip().startswith("*/"):
                break
            if re.match(r"^\s*\*\s*@([a-zA-Z0-9_.-]+)\b", line):
                # 新的标签开始 -> 结束当前块并重新解析该行
                if collecting_patch_diff:
                    collecting_patch_diff = False
                if collecting_patch_description:
                    collecting_patch_description = False
                # 不 consume 行，继续主循环让其被下面逻辑处理
                # 跳到主循环末尾处理标签匹配
            else:
                cleaned = re.sub(r"^\s*\*\s?", "", line)
                cleaned = cleaned.replace("&#47;", "/")
                if collecting_patch_diff:
                    patch_diff_lines.append(cleaned)
                elif collecting_patch_description:
                    patch_description_lines.append(cleaned)
                continue

        # 启动多行收集（patch-diff）
        if _PATCH_DIFF_START_RE.match(line):
            collecting_patch_diff = True
            continue
        # 启动多行收集（patch-description）
        if _PATCH_DESCRIPTION_START_RE.match(line):
            collecting_patch_description = True
            continue

        # 普通单行键值
        m = _KEY_VALUE_RE.match(line)
        if m:
            key, value = m.group(1), m.group(2).strip()
            if key in TARGET_KEYS:
                meta[TARGET_KEYS[key]] = value if value else None

    if patch_diff_lines:
        # 去掉末尾可能空行
        while patch_diff_lines and patch_diff_lines[-1].strip() == "":
            patch_diff_lines.pop()
        meta["patch_diff"] = "\n".join(patch_diff_lines) if patch_diff_lines else None
    if patch_description_lines:
        while patch_description_lines and patch_description_lines[-1].strip() == "":
            patch_description_lines.pop()
        meta["patch_description"] = "\n".join(patch_description_lines) if patch_description_lines else None

    return meta

def git_checkout(commit_hash: str, repo_path: Optional[str] = None) -> Dict[str, str]:
    """切换到指定 commit 并返回当前 HEAD 信息。

    返回:
        dict 包含:
            commit: 当前 HEAD 提交完整哈希
            branch: 当前分支名称（若处于分离头则为空字符串）
            detached: "true" / "false" 是否处于分离 HEAD
    """
    dotenv.load_dotenv(override=False)
    if repo_path is None:
        repo_path = os.getenv("LINUX_PATH")
    if not repo_path:
        raise RuntimeError("未找到 LINUX_PATH 环境变量且未显式传入 repo_path")
    if not os.path.isdir(repo_path):
        raise RuntimeError(f"仓库路径不存在: {repo_path}")

    # 验证 .git 目录
    if not os.path.isdir(os.path.join(repo_path, '.git')):
        raise RuntimeError(f"路径不是一个 git 仓库: {repo_path}")

    try:
        subprocess.run(["git", "checkout", commit_hash], cwd=repo_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # 获取当前提交哈希
        commit_full = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_path).decode().strip()
        # 获取当前分支（可能为空）
        try:
            branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path).decode().strip()
        except subprocess.CalledProcessError:
            branch = ""
        detached = "true" if branch == "HEAD" or branch == "" else "false"
        if branch == "HEAD":  # 分离头时标准化为空
            branch = ""
        return {"commit": commit_full, "branch": branch, "detached": detached}
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"git 操作失败: {e}") from e


def write_artifacts(meta: Dict[str, Optional[str]], repo_path: Optional[str] = None, base_output_dir: str = "prompt/context") -> Tuple[str, List[str]]:
    """基于解析出的 meta 写出两个文本文件:

    patch.txt:  meta['patch_diff'] 原始内容
    file.txt:   对应源码文件完整内容 (根据 meta['source_file'] + repo_path)

    返回: (目录绝对路径, 写出的文件名列表)
    若必要字段缺失则抛出异常。
    """
    name = meta.get("name")
    patch_diff = meta.get("patch_diff")
    source_file_rel = meta.get("source_file")
    if not (name and patch_diff and source_file_rel):
        raise RuntimeError("生成制品所需字段缺失: name/patch_diff/source_file")

    dotenv.load_dotenv(override=False)
    if repo_path is None:
        repo_path = os.getenv("LINUX_PATH")
    if not repo_path:
        raise RuntimeError("未找到 LINUX_PATH 环境变量")
    if not os.path.isdir(repo_path):
        raise RuntimeError(f"仓库路径不存在: {repo_path}")

    # 解析源码文件路径，防目录穿越
    norm_source_rel = os.path.normpath(source_file_rel.lstrip("/"))
    source_abs = os.path.normpath(os.path.join(repo_path, norm_source_rel))
    if not source_abs.startswith(os.path.abspath(repo_path) + os.sep):
        raise RuntimeError("source_file 超出仓库范围")
    if not os.path.isfile(source_abs):
        raise RuntimeError(f"源码文件不存在: {source_abs}")

    with open(source_abs, 'r', encoding='utf-8', errors='ignore') as f:
        source_content = f.read()

    out_dir = os.path.join(base_output_dir, name)
    os.makedirs(out_dir, exist_ok=True)

    written: List[str] = []
    def _write(filename: str, text: str):
        path = os.path.join(out_dir, filename)
        with open(path, 'w', encoding='utf-8') as wf:
            wf.write(text)
        written.append(filename)

    _write('patch.txt', patch_diff)
    _write('file.txt', source_content)

    # 解析补丁命中的函数/宏定义块，并写入 function.txt
    try:
        blocks = find_functions_for_patch(source_content, patch_diff)
        if blocks:
            _write('function.txt', "\n\n/* ----- separator ----- */\n\n".join(blocks))
        else:
            _write('function.txt', "")
    except Exception as _e:
        _write('function.txt', f"解析函数块失败: {_e}")

    # 打印补丁所在的完整函数块（基于 tree-sitter）
    try:
        find_functions_for_patch(source_content, patch_diff)
    except Exception:
        pass

    return (os.path.abspath(out_dir), written)




def extract_cve_meta_json(path: str, ensure_ascii: bool = False, indent: int = 2, checkout: bool = True) -> str:
    """辅助函数：返回 JSON 字符串；在解析到 patch_commit 后（若 checkout=True）
    会尝试 checkout 到其父提交 (patch_commit^)，而不是该提交本身。

    参数:
        path: 目标文件
        ensure_ascii: 传递给 json.dumps
        indent: JSON 缩进
        checkout: 若为 True 且存在 patch_commit，则执行 git checkout
    """
    data = extract_cve_meta(path)
    if checkout and data.get("patch_commit"):
        original = data["patch_commit"]
        try:
            # 解析父提交 hash
            dotenv.load_dotenv(override=False)
            repo_path = os.getenv("LINUX_PATH")
            if not repo_path:
                raise RuntimeError("未找到 LINUX_PATH 环境变量")
            if not os.path.isdir(repo_path):
                raise RuntimeError(f"仓库路径不存在: {repo_path}")
            try:
                parent_full = subprocess.check_output(["git", "rev-parse", f"{original}^"], cwd=repo_path).decode().strip()
            except subprocess.CalledProcessError as ce:
                raise RuntimeError(f"获取父提交失败: {ce}") from ce

            info = git_checkout(parent_full)
            data["_git_checkout"] = {
                "status": "success",
                "mode": "parent-of-patch-commit",
                "original_patch_commit": original,
                "parent_commit": parent_full,
                **info,
            }
            # 生成衍生文件（注意 artifacts 内容仍基于原始 patch_commit 所描述的 meta 信息）
            try:
                out_dir, files = write_artifacts(data)
                data["_artifacts"] = {"dir": out_dir, "files": files}
                # 生成基于模板的 prompt 文件
                try:
                    prompts = generate_prompt_files(data)
                    data["_prompts"] = {"status": "success", "files": prompts}
                except Exception as gpe:
                    data["_prompts"] = {"status": "failed", "error": str(gpe)}
            except Exception as sub_e:
                data["_artifacts"] = {"error": str(sub_e)}
        except Exception as e:
            data["_git_checkout"] = {
                "status": "failed",
                "mode": "parent-of-patch-commit",
                "original_patch_commit": original,
                "error": str(e),
            }
    return json.dumps(data, ensure_ascii=ensure_ascii, indent=indent)

__all__ = ["extract_cve_meta", "extract_cve_meta_json", "git_checkout", "write_artifacts"]


# ------------------ 辅助：从 patch 中提取结构体与函数名 ------------------
_STRUCT_RE = re.compile(r"\bstruct\s+([A-Za-z_][A-Za-z0-9_]*)")
# 简单函数定义匹配（捕获函数名）：返回类型 + 名称(
_FUNC_DEF_RE = re.compile(
    r"^(?:\+|-|\s)?"                           # diff 前缀
    r"(?:(?:static|inline|__always_inline|extern)\s+)*"  # 可能的修饰符
    r"[A-Za-z_][A-Za-z0-9_\s\*]*?"            # 返回类型部分（宽松）
    r"([A-Za-z_][A-Za-z0-9_]*)\s*\("           # 函数名 + '('
)
_CONTROL_KEYWORDS = {"if", "for", "while", "switch", "return", "sizeof"}

def _extract_structs_functions_from_patch(patch: str):
    structs = set()
    funcs = set()
    for raw_line in patch.splitlines():
        line = raw_line.strip('\n')
        if not line:
            continue
        # 去掉 diff 前缀 + - 空格
        if line.startswith(('+++', '---', '@@')):
            continue
        content = line[1:] if line[:1] in '+- ' else line

        # 结构体
        for sm in _STRUCT_RE.finditer(content):
            structs.add(sm.group(1))

        # 函数候选
        fm = _FUNC_DEF_RE.match(line)
        if fm:
            name = fm.group(1)
            if name not in _CONTROL_KEYWORDS and not name.startswith('__'):  # 过滤内核内部宏展开等
                funcs.add(name)
    return structs, funcs
