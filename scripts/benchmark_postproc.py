"""Benchmark post-processing backends for Resonance."""

import json
import time
import sys
import os

# Add src to path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

SYSTEM_PROMPT = (
    "You are a transcription post-processor. Fix grammar, punctuation, and "
    "capitalization. Interpret spoken formatting commands:\n"
    "- 'new line' / 'next line' -> insert a line break\n"
    "- 'bullet' / 'bullets' -> markdown bullet list\n"
    "- 'number one ... number two ...' -> numbered list\n"
    "- 'scratch that' / 'delete that' -> remove preceding content\n"
    "- 'period' / 'comma' / 'colon' -> insert punctuation\n"
    "Output only the corrected text. No explanations."
)

TEST_INPUTS = [
    "hello how are you doing today",
    "i went to the store and bought some milk and bread and eggs",
    "the quick brown fox jumps over the lazy dog period",
    "bullet buy groceries bullet clean the house bullet walk the dog",
    "dear john new line i hope this message finds you well new line sincerely mary",
    "number one first item number two second item number three third item",
    "i think we should scratch that actually lets go with the other option instead",
]


def benchmark_onnx():
    """Benchmark onnxruntime-genai backend."""
    try:
        import onnxruntime_genai as og
    except ImportError:
        print("onnxruntime-genai not installed. Run: uv pip install onnxruntime-genai")
        return

    from utils.resource_path import get_app_data_path
    model_dir = get_app_data_path("models/postproc-onnx")

    if not os.path.isdir(model_dir) or not any(
        f.endswith('.onnx') or f.endswith('.onnx_data')
        for f in os.listdir(model_dir)
        if os.path.isfile(os.path.join(model_dir, f))
    ):
        print(f"ONNX model not found at {model_dir}")
        print("Download with:")
        print(f"  huggingface-cli download hazemmabbas/Qwen2.5-0.5B-int4-block-32-acc-3-Instruct-onnx-cpu --local-dir {model_dir}")
        return

    print("Loading ONNX model...")
    t0 = time.perf_counter()
    model = og.Model(model_dir)
    tokenizer = og.Tokenizer(model)
    load_time = time.perf_counter() - t0
    print(f"Model loaded in {load_time:.2f}s\n")

    print("--- ONNX Runtime GenAI Benchmark ---\n")

    total_time = 0
    total_tokens = 0

    for i, text in enumerate(TEST_INPUTS):
        messages = json.dumps([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ])
        prompt = tokenizer.apply_chat_template(messages)
        input_tokens = tokenizer.encode(prompt)

        params = og.GeneratorParams(model)
        params.set_search_options(max_length=256, temperature=0.1)

        t0 = time.perf_counter()
        generator = og.Generator(model, params)
        generator.append_tokens(input_tokens)

        output_tokens = []
        while not generator.is_done():
            generator.generate_next_token()
            output_tokens.append(generator.get_next_tokens()[0])

        result = tokenizer.decode(output_tokens).strip()
        elapsed = time.perf_counter() - t0
        tps = len(output_tokens) / elapsed if elapsed > 0 else 0

        total_time += elapsed
        total_tokens += len(output_tokens)

        print(f"[{i+1}] {elapsed:.2f}s ({len(output_tokens)} tokens, {tps:.1f} tok/s)")
        print(f"    IN:  {text}")
        print(f"    OUT: {result}")
        print()

        del generator

    avg_time = total_time / len(TEST_INPUTS)
    avg_tps = total_tokens / total_time if total_time > 0 else 0
    print(f"--- Summary: avg {avg_time:.2f}s/sample, {avg_tps:.1f} tok/s ---\n")

    del model


def benchmark_llama_server():
    """Benchmark llama-server subprocess backend."""
    import subprocess
    import json
    import urllib.request

    from utils.resource_path import get_app_data_path
    model_path = None
    models_dir = get_app_data_path("models/postproc-gguf")

    if os.path.isdir(models_dir):
        for f in os.listdir(models_dir):
            if f.endswith('.gguf'):
                model_path = os.path.join(models_dir, f)
                break

    if not model_path:
        print(f"No GGUF model found in {models_dir}")
        print("Download with:")
        print(f"  huggingface-cli download Qwen/Qwen2.5-0.5B-Instruct-GGUF qwen2.5-0.5b-instruct-q4_k_m.gguf --local-dir {models_dir}")
        return

    # Check for llama-server binary
    server_dir = get_app_data_path("bin")
    server_exe = os.path.join(server_dir, "llama-server.exe")
    if not os.path.isfile(server_exe):
        print(f"llama-server.exe not found at {server_exe}")
        print("Download from: https://github.com/ggml-org/llama.cpp/releases")
        print(f"Extract llama-server.exe and all DLLs to: {server_dir}")
        return

    # Use absolute paths for Windows subprocess
    server_exe = os.path.abspath(server_exe)
    model_path = os.path.abspath(model_path)

    print(f"Starting llama-server with model {os.path.basename(model_path)}...")

    port = 8787
    proc = subprocess.Popen(
        [server_exe, "-m", model_path, "--port", str(port), "-ngl", "0", "--log-disable"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to start
    for _ in range(30):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/health")
            resp = urllib.request.urlopen(req, timeout=1)
            if resp.status == 200:
                break
        except Exception:
            time.sleep(0.5)
    else:
        print("llama-server failed to start within 15s")
        proc.kill()
        return

    print("llama-server ready\n")
    print("--- llama-server Benchmark ---\n")

    total_time = 0
    total_tokens = 0

    for i, text in enumerate(TEST_INPUTS):
        payload = json.dumps({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "temperature": 0.1,
            "max_tokens": 256,
        }).encode()

        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        t0 = time.perf_counter()
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        elapsed = time.perf_counter() - t0

        result = data["choices"][0]["message"]["content"]
        tokens = data.get("usage", {}).get("completion_tokens", 0)

        total_time += elapsed
        total_tokens += tokens

        print(f"[{i+1}] {elapsed:.2f}s ({tokens} tokens)")
        print(f"    IN:  {text}")
        print(f"    OUT: {result}")
        print()

    proc.kill()
    proc.wait()

    avg_time = total_time / len(TEST_INPUTS)
    avg_tps = total_tokens / total_time if total_time > 0 else 0
    print(f"--- Summary: avg {avg_time:.2f}s/sample, {avg_tps:.1f} tok/s ---\n")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        backend = sys.argv[1]
    else:
        backend = "all"

    if backend in ("onnx", "all"):
        benchmark_onnx()

    if backend in ("llama", "all"):
        benchmark_llama_server()

    if backend not in ("onnx", "llama", "all"):
        print(f"Usage: python {sys.argv[0]} [onnx|llama|all]")
