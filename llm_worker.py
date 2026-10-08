# আলাদা প্রসেসে LLM চালায়: ক্র্যাশ করলেও মূল প্রসেস বাঁচে। stdout-এর আসল fd-তে শুধু '@@...' লাইন।
import os, sys, json

proto = os.fdopen(os.dup(1), "w", buffering=1)
os.dup2(2, 1)

import faulthandler
faulthandler.enable()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config


def send(o):
    proto.write("@@" + (o if isinstance(o, str) else json.dumps(o)) + "\n")
    proto.flush()


def main():
    from llama_cpp import Llama
    llm = Llama(model_path=str(config.LLM_PATH), n_ctx=4096, n_threads=config.LLM_THREADS, verbose=False)
    send("READY")
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            out = llm.create_chat_completion(messages=r["messages"], max_tokens=int(r["max_tokens"]),
                                             temperature=float(r["temperature"]), top_p=0.92, repeat_penalty=1.12)
            send({"text": out["choices"][0]["message"]["content"] or ""})
        except Exception as e:
            send({"error": repr(e)[:300]})


if __name__ == "__main__":
    main()
