"""Compare local cleanup models on the user's real transcripts.

Starts the bundled Vulkan llama-server for one GGUF on a private loopback port,
sends the app's own cleanup request (default prompt, <transcript> wrapper,
temperature 0, thinking disabled) for every transcript, and writes timings and
outputs to benchmark-audio/cleanup-<label>.json.

    python -I -X utf8 benchmark-scripts/cleanup-compare.py <label> <model.gguf> [draft.gguf]
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

with open(os.path.join(ROOT, "src", "locales", "en", "prompts.json"), encoding="utf-8") as f:
    SYSTEM = json.load(f)["cleanupPrompt"].replace("{{agentName}}", "Assistant")

# Inputs: what the most accurate speech model produced for each real recording
# (skipping the 2-minute clip), plus three synthetic dictations.
with open(os.path.join(ROOT, "benchmark-audio", "result-unified-8.json"), encoding="utf-8") as f:
    INPUTS = [
        (f"clip{r['clip']}", r["text"])
        for r in json.load(f)["results"]
        if r["seconds"] < 60 and r["text"].strip()
    ]
INPUTS += [
    ("synth-short", "um can you uh send me the report by friday period"),
    (
        "synth-correction",
        "so I was thinking that we should uh move the standup to ten thirty no wait "
        "eleven because sanket and priya are both in the hyderabad office",
    ),
    (
        "synth-list",
        "okay for the review I want three things first the revenue numbers second the "
        "hiring plan we have uh four open roles scratch that five open roles and third "
        "the customer feedback new paragraph thanks everyone",
    ),
]


def user_message(text):
    # Mirrors src/config/prompts/index.ts.
    return f"<transcript>\n{text}\n</transcript>\n\nOutput only the cleaned transcript."


def wait_health(timeout=240):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as r:
                if r.status == 200:
                    return time.time() - start
        except Exception:
            time.sleep(0.3)
    raise RuntimeError("llama-server did not become healthy")


def cleanup(text):
    body = json.dumps(
        {
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user_message(text)},
            ],
            "temperature": 0,
            "max_tokens": 512,
            "stream": False,
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
    msg = data["choices"][0]["message"]
    return elapsed, (msg.get("content") or "").strip(), data.get("usage", {})


def main():
    label, model = sys.argv[1], sys.argv[2]
    draft = sys.argv[3] if len(sys.argv) > 3 else None
    args = [BINARY, "--model", model, "--host", "127.0.0.1", "--port", str(PORT),
            "--threads", os.environ.get("BENCH_THREADS", "4"), "--ctx-size", "8192", "--jinja"]
    if draft:
        args += ["--model-draft", draft, "--spec-type", "draft-mtp", "--spec-draft-n-max", "3"]
    t0 = time.time()
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rows = []
    try:
        load = wait_health()
        cleanup("hello there")  # warm the prompt cache
        for name, text in INPUTS:
            runs = []
            out = ""
            for _ in range(2):
                elapsed, out, usage = cleanup(text)
                runs.append(elapsed)
            rows.append({"name": name, "input": text, "output": out, "ms": round(min(runs) * 1000),
                         "completion_tokens": usage.get("completion_tokens")})
            print(f"{label} {name}: {round(min(runs) * 1000)} ms", file=sys.stderr)
    finally:
        proc.kill()
        proc.wait(timeout=15)
    ms = sorted(r["ms"] for r in rows)
    summary = {"label": label, "model": os.path.basename(model), "loadSeconds": round(load, 1),
               "medianMs": ms[len(ms) // 2], "p90Ms": ms[int(len(ms) * 0.9)], "maxMs": ms[-1]}
    with open(os.path.join(ROOT, "benchmark-audio", f"cleanup-{label}.json"), "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "rows": rows}, f, indent=1, ensure_ascii=False)
    print(json.dumps(summary))
    print(f"(total {time.time() - t0:.0f} s)")


if __name__ == "__main__":
    main()
