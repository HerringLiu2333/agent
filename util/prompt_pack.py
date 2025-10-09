import os
import json
from typing import Dict, List, Optional

TEMPLATE_PLACEHOLDERS = {
    '{{CVE_NAME}}': 'name',
    '{{PATCH_DESCRIPTION}}': 'patch_description',
    '{{PATCH_DIFF}}': 'patch_diff',
    '{{FILE_CONTENT}}': '__FILE_CONTENT__',          # 特殊处理：文件全文
    '{{FUNCTION_CONTENT}}': '__FUNCTION_CONTENT__',  # 特殊处理：函数/宏代码块
}

def _read_text(path: str) -> str:
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

def _render_template(
    tmpl: str,
    meta: Dict[str, Optional[str]],
    file_content: str = '',
    function_content: str = '',
) -> str:
    """根据占位符渲染模板。

    支持占位符：
    - {{CVE_NAME}}, {{PATCH_DESCRIPTION}}, {{PATCH_DIFF}}
    - {{FILE_CONTENT}}（来自 file.txt）
    - {{FUNCTION_CONTENT}}（来自 function.txt）
    """
    rendered = tmpl
    for placeholder, key in TEMPLATE_PLACEHOLDERS.items():
        if key == '__FILE_CONTENT__':
            value = file_content
        elif key == '__FUNCTION_CONTENT__':
            value = function_content
        else:
            value = meta.get(key) or ''
        rendered = rendered.replace(placeholder, value)
    return rendered

def generate_prompt_files(meta: Dict[str, Optional[str]], base_context_dir: str = 'prompt/context', temp_dir: str = 'prompt/temp') -> Dict[str, str]:
    """Generate prompt files based on templates in temp_dir (prompt_file.txt, prompt_patch.txt).

    The generated files are written into prompt/context/<name>/ with same filenames.
    Returns mapping {filename: absolute_path}. Raises if required inputs missing.
    """
    name = meta.get('name')
    patch_diff = meta.get('patch_diff')
    if not name:
        raise RuntimeError('meta.name 缺失')
    if not patch_diff:
        raise RuntimeError('meta.patch_diff 缺失')

    cve_dir = os.path.join(base_context_dir, name)
    patch_path = os.path.join(cve_dir, 'patch.txt')
    file_path = os.path.join(cve_dir, 'file.txt')
    function_path = os.path.join(cve_dir, 'function.txt')

    # 目标输出路径（若已存在则跳过处理）
    out_file_prompt = os.path.join(cve_dir, 'prompt_file.txt')
    out_patch_prompt = os.path.join(cve_dir, 'prompt_patch.txt')
    out_function_prompt = os.path.join(cve_dir, 'prompt_function.txt')

    # 若三个输出文件均已存在，则直接返回映射并跳过后续渲染
    if os.path.isfile(out_file_prompt) and os.path.isfile(out_patch_prompt) and os.path.isfile(out_function_prompt):
        return {
            'prompt_file.txt': os.path.abspath(out_file_prompt),
            'prompt_patch.txt': os.path.abspath(out_patch_prompt),
            'prompt_function.txt': os.path.abspath(out_function_prompt),
        }

    if not os.path.isfile(patch_path) or not os.path.isfile(file_path) or not os.path.isfile(function_path):
        raise RuntimeError('缺少 patch.txt / file.txt / function.txt，请先生成 artifacts')

    patch_content = _read_text(patch_path)
    file_content = _read_text(file_path)
    function_content = _read_text(function_path)

    # templates
    tpl_file = os.path.join(temp_dir, 'prompt_file.txt')
    tpl_patch = os.path.join(temp_dir, 'prompt_patch.txt')
    tpl_function = os.path.join(temp_dir, 'prompt_function.txt')
    if not (os.path.isfile(tpl_file) and os.path.isfile(tpl_patch) and os.path.isfile(tpl_function)):
        raise RuntimeError('缺少模板 prompt_file.txt / prompt_patch.txt / prompt_function.txt')

    t_file = _read_text(tpl_file)
    t_patch = _read_text(tpl_patch)
    t_function = _read_text(tpl_function)

    rendered_file = _render_template(t_file, meta, file_content=file_content, function_content=function_content)
    rendered_patch = _render_template(t_patch, meta, file_content=file_content, function_content=function_content)
    rendered_function = _render_template(t_function, meta, file_content=file_content, function_content=function_content)

    written: Dict[str, str] = {}
    os.makedirs(cve_dir, exist_ok=True)

    # 仅写入缺失的目标文件，已存在则跳过
    if not os.path.isfile(out_file_prompt):
        with open(out_file_prompt, 'w', encoding='utf-8') as wf:
            wf.write(rendered_file)
    written['prompt_file.txt'] = os.path.abspath(out_file_prompt)

    if not os.path.isfile(out_patch_prompt):
        with open(out_patch_prompt, 'w', encoding='utf-8') as wf:
            wf.write(rendered_patch)
    written['prompt_patch.txt'] = os.path.abspath(out_patch_prompt)

    if not os.path.isfile(out_function_prompt):
        with open(out_function_prompt, 'w', encoding='utf-8') as wf:
            wf.write(rendered_function)
    written['prompt_function.txt'] = os.path.abspath(out_function_prompt)

    return written

__all__ = ['generate_prompt_files']
