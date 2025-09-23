import argparse
import json
import os

from fl.llm import send_message, send_message_from_file, DEFAULT_MODEL
from util.cve_meta import extract_cve_meta_json

def main():
    parser = argparse.ArgumentParser(description="CVE 元数据解析 / LLM 发送工具")
    parser.add_argument("ql_file", nargs="?", default="/home/niuniu/Analysis-of-CWE/CVE-2025-38245/CVE-2025-38245.ql", help="目标 QL 文件路径")
    parser.add_argument("--no-checkout", action="store_true", help="不执行 git checkout")
    parser.add_argument("--prompt-file", help="若提供，则读取该 txt 内容发送给 LLM")
    parser.add_argument("--system", help="可选 system prompt", default=None)
    parser.add_argument("--model", help="模型名称覆盖", default=None)
    parser.add_argument("--temperature", type=float, default=0.0, help="模型温度")

    args = parser.parse_args()

    # 解析元数据
    try:
        meta_json = extract_cve_meta_json(args.ql_file, ensure_ascii=False, checkout=(not args.no_checkout))
        print("解析到的元数据 JSON:\n", meta_json)
    except Exception as e:
        print(f"解析文件失败: {e}")
        return

    # 如果指定 prompt 文件，发送给模型
    if args.prompt_file:
        try:
            model_kwargs = {}
            if args.model:
                model_kwargs["model"] = args.model
            model_kwargs["temperature"] = args.temperature
            effective_model = model_kwargs.get("model", DEFAULT_MODEL)
            reply = send_message_from_file(args.prompt_file, system_prompt=args.system, **model_kwargs)
            print(f"\nLLM 回复 (from file) ({effective_model}):\n", reply)
        except Exception as e:
            print(f"发送 prompt 文件失败: {e}")
    else:
        print("未指定 --prompt-file，跳过 LLM 调用。")

if __name__ == "__main__":
    main()