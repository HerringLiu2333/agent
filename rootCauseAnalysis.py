#!/usr/bin/env python3
"""生成 prompt/PROMPT_DIR.txt，列出 prompt/context 下的目录树（仅保留三类提示文件）。

用法:
    python rootCauseAnalysis.py

输出:
    prompt/PROMPT_DIR.txt

格式示例:
CVE-2024-57944/
    prompt_file.txt
    prompt_function.txt
    prompt_patch.txt
CVE-2024-57948/
    prompt_file.txt

只会列出存在的文件（仅限 prompt_file.txt, prompt_function.txt, prompt_patch.txt）。
"""
import os
from typing import List
from fl.llm import send_message, send_message_from_file, DEFAULT_MODEL
import time
from datetime import datetime


def llm_log(project_root: str, message: str) -> None:
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


TARGET_FILES = ["prompt_file.txt", "prompt_function.txt", "prompt_patch.txt"]


def build_prompt_tree(context_root: str) -> List[str]:
    lines: List[str] = []
    if not os.path.isdir(context_root):
        return lines

    # 使用 os.walk 获取递归目录结构，按目录深度排序
    for root, dirs, files in os.walk(context_root):
        rel = os.path.relpath(root, context_root)
        # 将当前目录相对路径转为更友好的显示
        if rel == ".":
            # 顶层 context 本身不写入，直接列出其子目录
            prefix = ""
            display_name = ""
        else:
            display_name = rel.replace(os.sep, "/") + "/"
            indent_level = rel.count(os.sep)
            prefix = "    " * indent_level
        # 只保留目标文件
        present = [f for f in TARGET_FILES if f in files]
        if present:
            # 写入目录行（如果是子目录）
            if display_name:
                lines.append(f"{prefix}{display_name}")
            # 写入文件行，缩进比目录多一级
            file_indent = prefix + "    "
            for p in sorted(present):
                lines.append(f"{file_indent}{p}")
    return lines


def send_prompts_from_prompt_dir(project_root: str, prompt_dir_rel: str = "prompt/PROMPT_DIR.txt", model: str = None, system_prompt: str = None) -> None:
    """读取 PROMPT_DIR.txt 并对其中每个 prompt 文件调用 LLM，写日志并保存回复。

    功能要点：
    - 按目录块（目录行 + 其下文件行）遍历 PROMPT_DIR.txt；
    - 跳过已包含 '[SENT]' 标记的目录块；
    - 每次成功发送单个 prompt 后暂停 60 秒；
    - 每个目录块处理完后在目录行末追加 ' [SENT]' 并写回文件以支持断点续跑；
    - 所有信息写入 res/llm.log（包含时间戳）。
    """
    out_path = os.path.join(project_root, prompt_dir_rel)
    if not os.path.isfile(out_path):
        llm_log(project_root, f"{out_path} 不存在，跳过发送步骤。")
        print(project_root, f"{out_path} 不存在，跳过发送步骤。")
        return

    model_kwargs = {}
    if model:
        model_kwargs["model"] = model

    try:
        with open(out_path, 'r', encoding='utf-8') as rf:
            lines = rf.readlines()
    except Exception as e:
        llm_log(project_root, f"读取 {out_path} 失败: {e}")
        print(project_root, f"读取 {out_path} 失败: {e}")
        return

    i = 0
    while i < len(lines):
        raw = lines[i].rstrip('\n')
        # 跳过空行或注释
        if not raw or raw.strip().startswith('#'):
            i += 1
            continue

        # 目录行以 '/' 结尾
        if raw.strip().endswith('/'):
            dir_line = raw
            # 如果已经标记为已发送，则跳过该目录块（包含其下的文件行）
            if '[SENT]' in dir_line:
                i += 1
                while i < len(lines) and not lines[i].strip().endswith('/'):
                    i += 1
                continue

            cur_dir = dir_line.strip().rstrip('/')
            llm_log(project_root, f"开始处理目录: {cur_dir}")
            print(project_root, f"开始处理目录: {cur_dir}")

            # 处理该目录下的文件行（直到遇到下一个目录行或 EOF）
            j = i + 1
            while j < len(lines):
                ln = lines[j].rstrip('\n')
                # 如果遇到下一个目录则结束本目录块
                if ln.strip().endswith('/'):
                    break
                # 跳过空行或注释
                if not ln or ln.strip().startswith('#'):
                    j += 1
                    continue

                fname = ln.strip()
                prompt_path = os.path.join(project_root, 'prompt', 'context', cur_dir, fname)
                if not os.path.isfile(prompt_path):
                    llm_log(project_root, f"提示文件不存在，跳过: {prompt_path}")
                    print(project_root, f"提示文件不存在，跳过: {prompt_path}")
                    j += 1
                    continue

                try:
                    used_model = model_kwargs.get("model", DEFAULT_MODEL)
                    llm_log(project_root, f"发送 {cur_dir}/{fname} 到模型 ({used_model})...")
                    print(project_root, f"发送 {cur_dir}/{fname} 到模型 ({used_model})...")
                    reply = send_message_from_file(prompt_path, system_prompt=system_prompt, **model_kwargs)
                    llm_log(project_root, f"回复 ({cur_dir}/{fname}):\n{reply}")

                    # 将回复保存到 res/{name}/{prompt_filename}
                    out_dir_res = os.path.join(project_root, 'res', cur_dir)
                    os.makedirs(out_dir_res, exist_ok=True)
                    save_path = os.path.join(out_dir_res, fname)
                    try:
                        with open(save_path, 'w', encoding='utf-8') as wf:
                            wf.write(reply)
                        llm_log(project_root, f"已将回复保存到: {save_path}")
                        print(project_root, f"已将回复保存到: {save_path}")
                    except Exception as save_e:
                        llm_log(project_root, f"保存回复失败 ({save_path}): {save_e}")
                        print(project_root, f"保存回复失败 ({save_path}): {save_e}")

                    # 发送后暂停 60 秒以防触发速率限制
                    time.sleep(60)
                except Exception as e:
                    llm_log(project_root, f"发送或读取回复失败 ({prompt_path}): {e}")
                    print(project_root, f"发送或读取回复失败 ({prompt_path}): {e}")
                j += 1

            # 本目录处理结束后，在目录行末追加标记并将整个 PROMPT_DIR.txt 写回磁盘（支持断点续跑）
            try:
                if '[SENT]' not in lines[i]:
                    lines[i] = lines[i].rstrip('\n') + ' [SENT]\n'
                    with open(out_path, 'w', encoding='utf-8') as wf:
                        wf.writelines(lines)
                    llm_log(project_root, f"已标记为已发送: {cur_dir}")
            except Exception as e:
                llm_log(project_root, f"标记 PROMPT_DIR 失败: {e}")

            # 继续从下一个目录行开始处理
            i = j
        else:
            # 非目录行（可能是文件行或者其它），安全跳过
            i += 1

    llm_log(project_root, "send_prompts_from_prompt_dir 完成。")


def main():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "."))
    context_root = os.path.join(project_root, "prompt", "context")
    out_path = os.path.join(project_root, "prompt", "PROMPT_DIR.txt")

    # 如果已存在则不再生成
    if os.path.exists(out_path):
        llm_log(project_root, f"{out_path} 已存在，跳过生成。")
        print(project_root, f"{out_path} 已存在，跳过生成。")
    else: 
        lines = build_prompt_tree(context_root)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as wf:
            if not lines:
                wf.write("# No prompt files found under prompt/context\n")
            else:
                for ln in lines:
                    wf.write(ln + "\n")
        llm_log(project_root, f"Wrote {len(lines)} lines to: {out_path}")
        print(project_root, f"Wrote {len(lines)} lines to: {out_path}")
        
    # 生成成功后调用独立的发送函数（不与生成逻辑耦合）
    send_prompts_from_prompt_dir(project_root)


if __name__ == "__main__":
    main()
