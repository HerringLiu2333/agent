#!/usr/bin/env python3
"""仅发送我在代码中显式指定的 prompt 文件。

使用方法：
- 在 SELECTED_PROMPTS 中填写要发送的 prompt 文件路径（可为相对项目根路径或绝对路径）。
- 每个 prompt 发送后会：
  1) 将发送与回复记录到 res/llm.log；
  2) 将回复保存到 res/<相对prompt/context下的目录>/<文件名> 中；
  3) 每次发送之间默认暂停 60 秒以避免速率限制。
"""
import os
from typing import List
from fl.llm import send_message_from_file, DEFAULT_MODEL
import time
from datetime import datetime

# ============== 在此处指定要发送的 prompt 文件 ==============
# 可填写绝对路径或相对项目根的路径。示例：
# "prompt/context/CVE-2024-57944/prompt_file.txt",
# "prompt/context/CVE-2024-57944/prompt_function.txt",
# "prompt/context/CVE-2024-57948/prompt_patch.txt",
SELECTED_PROMPTS: List[str] = [
    # 在这里填入你要发送的 prompt 路径（字符串），示例见上
    "prompt/context/CVE-2025-38301/prompt_patch.txt",
    "prompt/context/CVE-2025-38301/prompt_function.txt",
    "prompt/context/CVE-2025-38301/prompt_file.txt",
    "prompt/context/CVE-2025-38323/prompt_patch.txt",
    "prompt/context/CVE-2025-38323/prompt_function.txt",
    "prompt/context/CVE-2025-38323/prompt_file.txt",
]

# 可选：覆盖模型名与 system prompt（不需要可保持为 None）
MODEL_OVERRIDE: str | None = None
SYSTEM_PROMPT: str | None = None

# 发送间隔（秒），用于简单限流
SLEEP_SECONDS: int = 60


def print_log(project_root: str, message: str) -> None:
    """将一条日志追加到 project_root/res/llm.log，带时间戳。"""
    try:
        res_dir = os.path.join(project_root, 'res')
        os.makedirs(res_dir, exist_ok=True)
        log_path = os.path.join(res_dir, 'llm.log')
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(log_path, 'a', encoding='utf-8') as lf:
            lf.write(f"[{ts}] {message}\n")
    except Exception:
        # 日志写入失败不要抛出异常
        pass


def _to_abs_path(project_root: str, path: str) -> str:
    """将相对路径转换为绝对路径；若本身为绝对路径则直接返回。"""
    return path if os.path.isabs(path) else os.path.join(project_root, path)


def _save_reply(project_root: str, prompt_abs: str, reply: str) -> None:
    """将回复保存到 res 目录，路径规则：
    - 若 prompt 在 prompt/context/ 下：res/<相对context的目录>/<文件名>
    - 否则：res/misc/<去除盘符后的相对路径>/<文件名>
    """
    context_root = os.path.join(project_root, "prompt", "context")
    if os.path.commonpath([os.path.abspath(prompt_abs), os.path.abspath(context_root)]) == os.path.abspath(context_root):
        # 计算相对 prompt/context 的路径
        rel_to_context = os.path.relpath(prompt_abs, context_root)
        save_dir = os.path.join(project_root, "res", os.path.dirname(rel_to_context))
        save_name = os.path.basename(rel_to_context)
    else:
        # 不在 context 下，落到 res/misc 下，保留相对项目根的层级
        rel_to_project = os.path.relpath(prompt_abs, project_root)
        save_dir = os.path.join(project_root, "res", "misc", os.path.dirname(rel_to_project))
        save_name = os.path.basename(rel_to_project)

    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, save_name)
    try:
        with open(save_path, 'w', encoding='utf-8') as wf:
            wf.write(reply)
        print(project_root, f"已将回复保存到: {save_path}")
        print(f"已将回复保存到: {save_path}")
    except Exception as e:
        print(project_root, f"保存回复失败 ({save_path}): {e}")
        print(f"保存回复失败 ({save_path}): {e}")


def send_selected_prompts(project_root: str, selected: List[str], model: str | None, system_prompt: str | None) -> None:
    """仅发送 selected 列表中的 prompt 文件。"""
    if not selected:
        print(project_root, "SELECTED_PROMPTS 为空，未发送任何 prompt。")
        print("SELECTED_PROMPTS 为空，未发送任何 prompt。")
        return

    used_model = model or DEFAULT_MODEL
    for idx, p in enumerate(selected, 1):
        prompt_abs = _to_abs_path(project_root, p)
        if not os.path.isfile(prompt_abs):
            print(project_root, f"提示文件不存在，跳过: {prompt_abs}")
            print(f"提示文件不存在，跳过: {prompt_abs}")
            continue

        print(project_root, f"[{idx}/{len(selected)}] 发送: {prompt_abs} (model={used_model})")
        print(f"[{idx}/{len(selected)}] 发送: {prompt_abs} (model={used_model})")
        try:
            reply = send_message_from_file(prompt_abs, system_prompt=system_prompt, model=used_model)
            print(project_root, f"收到回复（长度={len(reply)}）")
            _save_reply(project_root, prompt_abs, reply)
            # 发送间隔
            if idx < len(selected) and SLEEP_SECONDS > 0:
                time.sleep(SLEEP_SECONDS)
        except Exception as e:
            print(project_root, f"发送失败: {prompt_abs} -> {e}")
            print(f"发送失败: {prompt_abs} -> {e}")


def main():
    # 项目根目录（脚本所在目录的上层）
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "."))

    # 发送指定的 prompt 文件
    send_selected_prompts(
        project_root=project_root,
        selected=SELECTED_PROMPTS,
        model=MODEL_OVERRIDE,
        system_prompt=SYSTEM_PROMPT,
    )


if __name__ == "__main__":
    main()