"""Benchmark local cleanup models for OpenWhispr dictation: latency per transcript, warm."""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVER = Path.home() / 'AppData/Local/Programs/OpenWhisprDictation/resources/bin/llama-vulkan/llama-server-vulkan.exe'
PROMPT = json.loads((HERE / 'cleanup-prompt.json').read_text('utf-8'))['prompt']
SAMPLES = [
    "um so basically what i want is uh a function that takes the list and like returns the the top three items sorted by score",
    "hey can you check the uh the deploy pipeline it failed again on the on the windows runner i think it's the node version period",
    "okay so new paragraph the meeting is moved to uh january fifteenth at five thirty pm and we need three hundred dollars for the venue",
    "wait no scratch that i meant the second branch not the first one and also rename the file to config dot yaml",
    "i'm not sure this is the right approach you know maybe we should just cache the result and and move on",
]


def post(port, body, timeout=120):
    request = urllib.request.Request('http://127.0.0.1:%d/v1/chat/completions' % port, json.dumps(body).encode(),
                                     {'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def wait_ready(port, deadline=180):
    start = time.time()
    while time.time() - start < deadline:
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d/health' % port, timeout=2) as r:
                if json.loads(r.read().decode()).get('status') == 'ok':
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def run(port, model_label):
    results = []
    body = {'messages': [{'role': 'system', 'content': PROMPT},
                         {'role': 'user', 'content': '<transcript>' + SAMPLES[0] + '</transcript>'}],
            'temperature': 0.3, 'max_tokens': 256, 'chat_template_kwargs': {'enable_thinking': False}}
    post(port, body)  # warm-up: prompt cache and kernels
    for sample in SAMPLES:
        body['messages'][1]['content'] = '<transcript>' + sample + '</transcript>'
        best = None
        for _ in range(2):
            t0 = time.perf_counter()
            reply = post(port, body)
            ms = (time.perf_counter() - t0) * 1000
            text = reply['choices'][0]['message']['content'].strip()
            usage = reply.get('usage', {})
            if best is None or ms < best['ms']:
                best = {'ms': ms, 'out': text, 'completion_tokens': usage.get('completion_tokens'),
                        'prompt_tokens': usage.get('prompt_tokens')}
        results.append(best)
    return {'model': model_label, 'median_ms': sorted(r['ms'] for r in results)[len(results) // 2],
            'mean_ms': sum(r['ms'] for r in results) / len(results), 'samples': results}


def main():
    out = []
    # Current model: the app's own server on 8221.
    if wait_ready(8221, 3):
        print('benchmarking gemma-4-E4B q4_0 on the running server', flush=True)
        out.append(run(8221, 'gemma-4-E4B-it-qat-q4_0 (current)'))
    for path in sys.argv[1:]:
        label = Path(path).stem
        print('starting', label, flush=True)
        proc = subprocess.Popen([str(SERVER), '-m', path, '--host', '127.0.0.1', '--port', '8231', '-ngl', '99',
                                 '-c', '4096', '-np', '1', '--jinja', '--no-webui', *os.environ.get('BENCH_EXTRA', '').split()],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            if not wait_ready(8231):
                print('  server did not become ready', flush=True)
                continue
            out.append(run(8231, label))
        finally:
            proc.terminate()
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()
            time.sleep(1)
    (HERE / 'cleanup-benchmark.json').write_text(json.dumps(out, indent=2), 'utf-8')
    print('\n%-42s %10s %10s' % ('model', 'median ms', 'mean ms'))
    for r in out:
        print('%-42s %10.0f %10.0f' % (r['model'], r['median_ms'], r['mean_ms']))
    for r in out:
        print('\n==', r['model'])
        for s in r['samples']:
            print('  %5.0f ms | %s' % (s['ms'], s['out'].replace('\n', ' / ')[:160]))


if __name__ == '__main__':
    main()
