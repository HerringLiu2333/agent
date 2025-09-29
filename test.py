import argparse
import json
import os
import time
import dotenv

from fl.llm import send_message, send_message_from_file, DEFAULT_MODEL
from util.cve_meta import extract_cve_meta_json

# 全局变量：CVE 名称（用于路径拼接与默认 QL 文件名）
name = "CVE-2025-38487"

def main():
    # 先加载 .env 并读取 QLFILE_PATH（若未设置使用默认）
    dotenv.load_dotenv(override=False)
    ql_base = os.getenv("QLFILE_PATH", "/home/niuniu/Analysis-of-CWE")

    parser = argparse.ArgumentParser(description="CVE 元数据解析 / LLM 发送工具")
    parser.add_argument(
        "ql_file",
        nargs="?",
        default=f"{ql_base}/{name}/{name}.ql",
        help="目标 QL 文件路径",
    )
    parser.add_argument("--no-checkout", action="store_true", help="不执行 git checkout")
    # 不再手动指定 prompt 文件，自动从 prompt/context/<name>/prompt_file.txt 读取
    parser.add_argument("--system", help="可选 system prompt", default=None)
    parser.add_argument("--model", help="模型名称覆盖", default=None)
    parser.add_argument("--temperature", type=float, default=0.0, help="模型温度")

    args = parser.parse_args()

    # 确定项目根（基于当前文件位置）
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "."))

    # 从 prompt/DIR.txt 读取要处理的 name 列表；若不存在则回退到全局 name
    dir_file = os.path.join(project_root, "prompt", "DIR.txt")
    names = []
    if os.path.isfile(dir_file):
        with open(dir_file, "r", encoding="utf-8") as f:
            for line in f:
                ln = line.strip()
                if ln:
                    names.append(ln)
    if not names:
        names = [name]

    # model 参数准备
    model_kwargs = {}
    if args.model:
        model_kwargs["model"] = args.model
    model_kwargs["temperature"] = args.temperature
    effective_model = model_kwargs.get("model", DEFAULT_MODEL)

    for cur_name in names:
        print(f"\n=== 处理: {cur_name} ===")
        # 构造 ql 文件路径并解析元数据
        ql_file_path = f"{ql_base}/{cur_name}/{cur_name}.ql"
        try:
            meta_json = extract_cve_meta_json(ql_file_path, ensure_ascii=False, checkout=(not args.no_checkout))
            # 将 meta_json 写入 prompt/create_prompt.log（追加），便于后续查看与调试
            log_path = os.path.join(project_root, "prompt", "create_prompt.log")
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            try:
                with open(log_path, 'a', encoding='utf-8') as lf:
                    lf.write(f"=== {cur_name} ===\n")
                    lf.write(meta_json + "\n\n")
                print(f"解析成功并已追加到日志: {log_path}")
            except Exception as log_e:
                print(f"写入 create_prompt.log 失败: {log_e}")
        except Exception as e:
            print(f"解析文件失败 ({ql_file_path}): {e}")
            # 跳到下一个 name
            continue

    # for cur_name in names:
    #     # 要处理的三个 prompt 文件及其后缀标识
    #     prompt_variants = [
    #         ("prompt_file.txt", "file"),
    #         ("prompt_function.txt", "function"),
    #         ("prompt_patch.txt", "patch"),
    #     ]

    #     for prompt_fname, suffix in prompt_variants:
    #         prompt_path = os.path.join(project_root, "prompt", "context", cur_name, prompt_fname)
    #         if not os.path.isfile(prompt_path):
    #             print(f"提示文件不存在，跳过: {prompt_path}")
    #             continue

    #         try:
    #             reply = send_message_from_file(prompt_path, system_prompt=args.system, **model_kwargs)
    #             # print(f"LLM 回复 ({effective_model}) for {cur_name}/{suffix}:\n", reply)
    #             # print(f"发送提示文件 ({prompt_path}) 到模型 ({effective_model})...")
    #         except Exception as e:
    #             print(f"发送 prompt 文件失败 ({prompt_path}): {e}")
    #             continue

    #         # 将回复保存到 res/{name}/{name}-{suffix}-{timestamp}
    #         try:
    #             ts = int(time.time())
    #             out_dir = os.path.join(project_root, "res", cur_name)
    #             os.makedirs(out_dir, exist_ok=True)
    #             out_path = os.path.join(out_dir, f"{cur_name}-{suffix}-{ts}")
    #             with open(out_path, 'w', encoding='utf-8') as f:
    #                 f.write(f"{reply}")
    #             print(f"结果已保存到: {out_path}")
    #         except Exception as write_e:
    #             print(f"保存回复到文件失败: {write_e}")

if __name__ == "__main__":
    main()