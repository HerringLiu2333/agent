import os
import json
from typing import Dict, List, Optional

TEMPLATE_PLACEHOLDERS = {
    '{{CVE_NAME}}': 'name',
    '{{PATCH_DESCRIPTION}}': 'patch_description',
    '{{PATCH_DIFF}}': 'patch_diff',
    '{{FILE_CONTENT}}': '__FILE_CONTENT__',  # special handling
}

def _read_text(path: str) -> str:
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

def _render_template(tmpl: str, meta: Dict[str, Optional[str]], file_content: str) -> str:
    rendered = tmpl
    for placeholder, key in TEMPLATE_PLACEHOLDERS.items():
        if key == '__FILE_CONTENT__':
            value = file_content
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

    if not os.path.isfile(patch_path) or not os.path.isfile(file_path):
        raise RuntimeError('缺少 patch.txt 或 file.txt，请先生成 artifacts')

    patch_content = _read_text(patch_path)
    file_content = _read_text(file_path)

    # templates
    tpl_file = os.path.join(temp_dir, 'prompt_file.txt')
    tpl_patch = os.path.join(temp_dir, 'prompt_patch.txt')
    if not os.path.isfile(tpl_file) or not os.path.isfile(tpl_patch):
        raise RuntimeError('缺少模板 prompt_file.txt 或 prompt_patch.txt')

    t_file = _read_text(tpl_file)
    t_patch = _read_text(tpl_patch)

    rendered_file = _render_template(t_file, meta, file_content)
    rendered_patch = _render_template(t_patch, meta, file_content)

    written: Dict[str, str] = {}
    os.makedirs(cve_dir, exist_ok=True)
    out_file_prompt = os.path.join(cve_dir, 'prompt_file.txt')
    out_patch_prompt = os.path.join(cve_dir, 'prompt_patch.txt')

    with open(out_file_prompt, 'w', encoding='utf-8') as wf:
        wf.write(rendered_file)
    written['prompt_file.txt'] = os.path.abspath(out_file_prompt)

    with open(out_patch_prompt, 'w', encoding='utf-8') as wf:
        wf.write(rendered_patch)
    written['prompt_patch.txt'] = os.path.abspath(out_patch_prompt)

    return written

__all__ = ['generate_prompt_files']
