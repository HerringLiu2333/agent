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

    # 解析元数据
    try:
        meta_json = extract_cve_meta_json(args.ql_file, ensure_ascii=False, checkout=(not args.no_checkout))
        # print("解析到的元数据 JSON:\n", meta_json)
    except Exception as e:
        print(f"解析文件失败: {e}")
        return

    # 自动定位 prompt 文件并发送给模型
    prompt_file = f"/home/niuniu/agent/prompt/context/{name}/prompt_file.txt"
    try:
        model_kwargs = {}
        if args.model:
            model_kwargs["model"] = args.model
        model_kwargs["temperature"] = args.temperature
        effective_model = model_kwargs.get("model", DEFAULT_MODEL)
        reply = send_message_from_file(prompt_file, system_prompt=args.system, **model_kwargs)
        print(f"\nLLM 回复 (from file) ({effective_model}):\n", reply)
        # print(f"\nSending prompt file ({prompt_file}) to LLM ({effective_model})...")

        # 将模型名称与回复内容落盘到 res/{name}/{name}+{timestamp}
        try:
            ts = int(time.time())
            out_dir = f"/home/niuniu/agent/res/{name}"
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f"{name}-{ts}")
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(f"{reply}")
                print(f"结果已保存到: {out_path}")
        except Exception as write_e:
            print(f"保存回复到文件失败: {write_e}")
    except Exception as e:
        print(f"发送 prompt 文件失败: {e}")

if __name__ == "__main__":
    main()