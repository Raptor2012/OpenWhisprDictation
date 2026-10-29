"""Warm cleanup latency of the local Gemma cleanup model through llama-server.

Starts the bundled Vulkan llama-server on a private loopback port with the same
arguments the app uses, then times the app's default cleanup prompt on three
raw transcripts. Run with:  python -I benchmark-scripts/cleanup-bench.py
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(os.environ.get("BENCH_PORT", "8299"))
BINARY = os.environ.get(
    "BENCH_LLAMA",
    os.path.join(ROOT, "resources", "bin", "llama-vulkan", "llama-server-vulkan.exe"),
)
MODELS = os.path.join(os.path.expanduser("~"), ".cache", "openwhispr", "models")
MODEL = os.path.join(MODELS, "gemma-4-E4B_q4_0-it.gguf")
DRAFT = os.path.join(MODELS, "mtp-gemma-4-E4B-it.gguf")

with open(os.path.join(ROOT, "src", "locales", "en", "prompts.json"), encoding="utf-8") as f:
    SYSTEM = json.load(f)["cleanupPrompt"].replace("{{agentName}}", "Assistant")

TRANSCRIPTS = {
    "short (12 words)": "um can you uh send me the report by friday period",
    "medium (41 words)": (
        "so I was thinking that we should uh move the standup to ten thirty no wait "
        "eleven because sanket and priya are both in the hyderabad office and um the "
        "traffic there is like really bad in the morning you know"
    ),
    "long (92 words)": (
        "okay so for the quarterly review I want to cover three things first the "
        "revenue numbers which came in at about two point four million um that is "
        "twelve percent over the forecast second the hiring plan we have uh four open "
        "roles in engineering and two in sales and I think we should actually "
        "prioritize the backend role scratch that the platform role because the "
        "migration is blocked on it and third um the customer feedback from the "
        "beta where like most people asked for better offline support and faster "
        "startup so let's put that on the roadmap new paragraph thanks everyone"
    ),
}


def wait_health(timeout=180):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as r:
                if r.status == 200:
                    return time.time() - start
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("llama-server did not become healthy")


def cleanup(text):
    body = json.dumps(
        {
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"<transcript>{text}</transcript>"},
            ],
            "temperature": 0.1,
            "max_tokens": 400,
            "stream": False,
            # The app sends this so Gemma/Qwen templates skip the thinking channel.
            "chat_template_kwargs": {"enable_thinking": False},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode("utf-8"))
    elapsed = time.perf_counter() - t0
    return elapsed, data["choices"][0]["message"]["content"].strip(), data.get("usage", {})


def main():
    for p in (BINARY, MODEL, DRAFT):
        if not os.path.exists(p):
            print("missing:", p)
            sys.exit(1)
    args = [
        BINARY, "--model", MODEL, "--host", "127.0.0.1", "--port", str(PORT), "--threads", "4",
        "--ctx-size", "16384", "--jinja", "--model-draft", DRAFT, "--spec-type", "draft-mtp",
        "--spec-draft-n-max", "3",
    ]
    t_start = time.time()
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ready = wait_health()
        print(f"server ready (model load) in {ready:.2f} s")
        cleanup("hello there")  # warm-up
        results = {}
        for label, text in TRANSCRIPTS.items():
            runs = []
            out = ""
            usage = {}
            for _ in range(3):
                elapsed, out, usage = cleanup(text)
                runs.append(elapsed)
            results[label] = runs
            print(f"\n{label}: " + ", ".join(f"{r:.3f}" for r in runs) + " s; tokens " + json.dumps(usage))
            print("  output:", out.replace("\n", " / "))
        print("\nsummary (seconds, 3 runs each):")
        for label, runs in results.items():
            print(f"  {label}: min {min(runs):.3f} / median {sorted(runs)[1]:.3f} / max {max(runs):.3f}")
    finally:
        proc.kill()
        proc.wait(timeout=10)
        print(f"\nserver stopped; total {time.time() - t_start:.1f} s")


if __name__ == "__main__":
    main()
