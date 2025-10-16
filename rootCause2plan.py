#!/usr/bin/env python3
"""从 prompt/DIR.txt 构建基于模板的 rootCause2plan 输出文件。

函数 makePrompt(project_root=None) 会：
- 读取 prompt/DIR.txt 中的每个名称（例如 CVE-...）
- 对于每个名称，从 prompt/context/{name}/ 读取 prompt_file.txt, prompt_function.txt, prompt_patch.txt（若存在）
- 从 res/{name}/ 读取同名的 LLM 回复文件（若存在）
- 读取 prompt/temp/ 下的模板文件 rootCause2plan_file.txt, rootCause2plan_function.txt, rootCause2plan_patch.txt
- 用占位符替换将结果写回 prompt/context/{name}/ 同名文件（模板文件名保持不变）

占位符支持：
- {{NAME}}: CVE 名称
- {{PROMPT_FILE}}, {{PROMPT_FUNCTION}}, {{PROMPT_PATCH}}: 原 prompt 内容
- {{RES_PROMPT_FILE}}, {{RES_PROMPT_FUNCTION}}, {{RES_PROMPT_PATCH}}: LLM 的回复内容

如果模板中没有占位符，则会在文件末尾附加一个小节包含提取到的内容。
"""
import os
import re
from typing import Optional
# 新增导入：发送 LLM、计时与时间戳日志
from fl.llm import send_message, send_message_from_file, DEFAULT_MODEL
import time
from datetime import datetime


# 新增：与 rootCauseAnalysis.py 一致的简单日志函数
def llm_log(project_root: str, message: str) -> None:
    try:
        res_dir = os.path.join(project_root, 'res')
        os.makedirs(res_dir, exist_ok=True)
        log_path = os.path.join(res_dir, 'llm.log')
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(log_path, 'a', encoding='utf-8') as lf:
            lf.write(f"[{ts}] {message}\n")
    except Exception:
        pass


def _read_text(path: str) -> Optional[str]:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return None


def makePrompt(project_root: Optional[str] = None) -> None:
    """生成基于 rootCause2plan_* 模板的填充文件并保存到 prompt/context/{name}/ 下。

    参数:
        project_root: 项目根路径，默认使用脚本所在目录。
    """
    if project_root is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '.'))

    dir_list_path = os.path.join(project_root, 'prompt', 'DIR.txt')
    temp_dir = os.path.join(project_root, 'prompt', 'temp')
    context_dir = os.path.join(project_root, 'prompt', 'context')
    res_dir = os.path.join(project_root, 'res')

    # 模板文件及对应的输入文件名
    templates = [
        ('rootCause2plan_file.txt', 'prompt_file.txt', 'prompt_file.txt'),
        ('rootCause2plan_function.txt', 'prompt_function.txt', 'prompt_function.txt'),
        ('rootCause2plan_patch.txt', 'prompt_patch.txt', 'prompt_patch.txt'),
    ]

    # 读取 DIR.txt
    try:
        with open(dir_list_path, 'r', encoding='utf-8') as df:
            names = [ln.strip() for ln in df if ln.strip()]
    except Exception:
        # 无 DIR.txt 则直接返回
        return

    for name in names:
        # 构造每个路径
        ctx_name_dir = os.path.join(context_dir, name)
        res_name_dir = os.path.join(res_dir, name)
        os.makedirs(ctx_name_dir, exist_ok=True)

        # 读取 prompt/context 中的 prompt_* 文件与 res 中的回复
        prompt_contents = {}
        res_contents = {}
        for _, prompt_fn, _ in templates:
            ppath = os.path.join(ctx_name_dir, prompt_fn)
            prompt_contents[prompt_fn] = _read_text(ppath) or f"<MISSING {prompt_fn} in {ctx_name_dir}>"
        for _, _, res_fn in templates:
            rpath = os.path.join(res_name_dir, res_fn)
            res_contents[res_fn] = _read_text(rpath) or f"<MISSING {res_fn} in {res_name_dir}>"

        # 对每个模板进行填充并保存
        for tpl_name, prompt_fn, res_fn in templates:
            tpl_path = os.path.join(temp_dir, tpl_name)
            tpl_text = _read_text(tpl_path)
            out_path = os.path.join(ctx_name_dir, tpl_name)

            if tpl_text is None:
                # 如果模板不存在，写入一份包含提取内容的默认文件
                fallback = [
                    f"# Template missing: {tpl_name}",
                    f"# Generated for: {name}",
                    "",
                    "-- PROMPT SOURCE --",
                    prompt_contents.get(prompt_fn, ''),
                    "",
                    "-- LLM RESPONSE (res) --",
                    res_contents.get(res_fn, ''),
                ]
                try:
                    with open(out_path, 'w', encoding='utf-8') as of:
                        of.write('\n'.join(fallback))
                except Exception:
                    pass
                continue

            filled = tpl_text

            content = prompt_contents.get(prompt_fn, '')
            start_index = content.rfind("[PATCH_DESCRIPTION]")
            end_index = content.rfind("[OUTPUT FORMAT]")
            if start_index != -1 and end_index != -1:
                # 提取从 [PATCH_DESCRIPTION] 开始到 [OUTPUT FORMAT] 之前的内容
                target_section = content[start_index:end_index]
            else:
                # 如果都没有找到，返回空字符串或适当处理
                target_section = ""

            # 基本占位符替换
            replacements = {
                '{{CVE_NAME}}': name,
                '{{INFO}}': target_section,
                # 新增：将对应 res 文件的内容直接作为 ROOTCAUSE_ANALYSIS 占位符
                '{{ROOTCAUSE_ANALYSIS}}': res_contents.get(res_fn, ''),
            }
            for k, v in replacements.items():
                if k in filled:
                    filled = filled.replace(k, v)

            # 写回到 prompt/context/{name}/{tpl_name}
            try:
                with open(out_path, 'w', encoding='utf-8') as of:
                    of.write(filled)
            except Exception:
                # 忽略单个写入错误
                pass


# 新增：列举 rootCause2plan_* 文件的目录树
TARGET_2PLAN_FILES = [
    "rootCause2plan_file.txt",
    "rootCause2plan_function.txt",
    "rootCause2plan_patch.txt",
]


def build_prompt2plan_tree(context_root: str):
    lines = []
    if not os.path.isdir(context_root):
        return lines
    for root, dirs, files in os.walk(context_root):
        rel = os.path.relpath(root, context_root)
        if rel == ".":
            prefix = ""
            display_name = ""
        else:
            display_name = rel.replace(os.sep, "/") + "/"
            indent_level = rel.count(os.sep)
            prefix = "    " * indent_level
        present = [f for f in TARGET_2PLAN_FILES if f in files]
        if present:
            if display_name:
                lines.append(f"{prefix}{display_name}")
            file_indent = prefix + "    "
            for p in sorted(present):
                lines.append(f"{file_indent}{p}")
    return lines


# 新增：发送 prompt/context 下的 rootCause2plan_* 文件，支持断点续传

def send_prompts2plan_from_dir(project_root: str, prompt_dir_rel: str = "prompt/PROMPT2plan_DIR.txt", model: str = None, system_prompt: str = None) -> None:
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
        if not raw or raw.strip().startswith('#'):
            i += 1
            continue
        if raw.strip().endswith('/'):
            dir_line = raw
            if '[SENT]' in dir_line:
                i += 1
                while i < len(lines) and not lines[i].strip().endswith('/'):
                    i += 1
                continue

            cur_dir = dir_line.strip().rstrip('/')
            llm_log(project_root, f"开始处理目录: {cur_dir}")
            print(project_root, f"开始处理目录: {cur_dir}")

            j = i + 1
            while j < len(lines):
                ln = lines[j].rstrip('\n')
                if ln.strip().endswith('/'):
                    break
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

                    time.sleep(60)
                except Exception as e:
                    llm_log(project_root, f"发送或读取回复失败 ({prompt_path}): {e}")
                    print(project_root, f"发送或读取回复失败 ({prompt_path}): {e}")
                j += 1

            try:
                if '[SENT]' not in lines[i]:
                    lines[i] = lines[i].rstrip('\n') + ' [SENT]\n'
                    with open(out_path, 'w', encoding='utf-8') as wf:
                        wf.writelines(lines)
                    llm_log(project_root, f"已标记为已发送: {cur_dir}")
            except Exception as e:
                llm_log(project_root, f"标记 PROMPT2plan_DIR 失败: {e}")
            i = j
        else:
            i += 1

    llm_log(project_root, "send_prompts2plan_from_dir 完成。")


# 新增：主流程，先生成 rootCause2plan_*，再生成/发送 PROMPT2plan_DIR.txt

def main():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '.'))
    context_root = os.path.join(project_root, 'prompt', 'context')
    out_path = os.path.join(project_root, 'prompt', 'PROMPT2plan_DIR.txt')

    # 先根据模板生成 rootCause2plan_* 文件
    makePrompt(project_root)

    # 生成 PROMPT2plan_DIR.txt（如已存在则跳过，支持断点续跑）
    if os.path.exists(out_path):
        llm_log(project_root, f"{out_path} 已存在，跳过生成。")
        print(project_root, f"{out_path} 已存在，跳过生成。")
    else:
        lines = build_prompt2plan_tree(context_root)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as wf:
            if not lines:
                wf.write('# No rootCause2plan files found under prompt/context\n')
            else:
                for ln in lines:
                    wf.write(ln + '\n')
        llm_log(project_root, f"Wrote {len(lines)} lines to: {out_path}")
        print(project_root, f"Wrote {len(lines)} lines to: {out_path}")

    # 调用发送流程
    send_prompts2plan_from_dir(project_root)


if __name__ == '__main__':
    main()
