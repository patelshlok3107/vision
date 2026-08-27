"""
VISION Benchmark Harness — AFTER (post-optimization)
Directly hits Django /api/ai/chat/ with streaming NDJSON and measures:
  t_req_start   -> HTTP request initiated
  t_headers     -> first HTTP response header byte received
  t_stream_start-> backend NDJSON "stream_start" event parsed
  t_first_token -> backend NDJSON "token" event with first real char
  t_done        -> backend NDJSON "done" event (generation complete + diagnostics)
Also extracts the backend's own perf_* fields from the diagnostics dict.
"""
import json
import os
import sys
import time
import requests

TOKEN = os.environ.get("VISION_TOKEN")
if not TOKEN:
    # Auto-login with test account
    login_resp = requests.post(
        "http://127.0.0.1:8000/api/auth/login/",
        json={"email": "test@vision.ai", "password": "Vision123!"},
        timeout=10,
    )
    login_resp.raise_for_status()
    TOKEN = login_resp.json()["access"]
    print(f"[AUTO-LOGIN] OK, token length: {len(TOKEN)}")

BASE = "http://127.0.0.1:8000/api/ai/chat/"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/x-ndjson",
}

BENCHMARKS = [
    ("Ultra Short (Ultra-Fast path)", "Hello"),
    ("Simple Definition (Simple path)", "What is HTML?"),
    ("Small Code Snippet (Code path)", "Write a 5-line React component that displays Hello World with a button"),
]


def run_one(label, message, warmup=False):
    payload = json.dumps({"message": message, "request_id": f"bench_{int(time.time()*1000)}"})
    ts = {}
    ts["t_req_start"] = time.perf_counter()
    full_response = []
    diagnostics = {}
    path_label = None
    try:
        with requests.post(BASE, data=payload, headers=HEADERS, stream=True, timeout=120) as r:
            ts["t_headers"] = time.perf_counter()
            if r.status_code != 200:
                print(f"  [FAIL] HTTP {r.status_code}: {r.text[:500]}")
                return None
            for raw_line in r.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                try:
                    j = json.loads(raw_line)
                except json.JSONDecodeError:
                    # non-JSON chunk (shouldn't happen with NDJSON)
                    continue
                jtype = j.get("type")
                if jtype == "stream_start":
                    ts["t_stream_start"] = time.perf_counter()
                    path_label = (j.get("content") or {}).get("path")
                elif jtype == "token":
                    if "t_first_token" not in ts:
                        ts["t_first_token"] = time.perf_counter()
                    tok = j.get("content") or ""
                    if tok:
                        full_response.append(tok)
                elif jtype == "done":
                    ts["t_done"] = time.perf_counter()
                    diagnostics = j.get("diagnostics") or {}
                    path_label = path_label or (diagnostics.get("path"))
                elif jtype == "error":
                    print(f"  [ERROR] {j.get('content')}")
    except Exception as e:
        print(f"  [EXCEPTION] {type(e).__name__}: {e}")
        return None

    if "t_done" not in ts:
        ts["t_done"] = time.perf_counter()
    if "t_stream_start" not in ts:
        ts["t_stream_start"] = ts.get("t_headers", ts["t_req_start"])
    if "t_first_token" not in ts:
        ts["t_first_token"] = ts["t_done"]

    # Compute client-side deltas (ms)
    ms = lambda a, b: round((b - a) * 1000, 1)
    client = {
        "http_headers_ms":   ms(ts["t_req_start"], ts.get("t_headers", ts["t_req_start"])),
        "stream_start_ms":   ms(ts["t_req_start"], ts["t_stream_start"]),
        "ttft_ms":           ms(ts["t_req_start"], ts["t_first_token"]),
        "total_ms":          ms(ts["t_req_start"], ts["t_done"]),
        "gen_ms":            ms(ts["t_first_token"], ts["t_done"]),
    }

    output_chars = sum(len(s) for s in full_response)
    output_tokens_est = max(1, output_chars // 4)
    tok_per_sec = round(output_tokens_est / max(0.001, (client["gen_ms"] / 1000)), 1)

    backend = {
        "path":          path_label,
        "mode":          diagnostics.get("mode"),
        "model":         diagnostics.get("model"),
        "classification_mode": diagnostics.get("classification", {}).get("mode") if isinstance(diagnostics.get("classification"), dict) else None,
        "perf_backend_total_ms":   diagnostics.get("perf_total_ms"),
        "perf_context_ms":         diagnostics.get("perf_context_ms"),
        "perf_ollama_ms":          diagnostics.get("perf_ollama_call_ms"),
        "perf_model_load_ms":      diagnostics.get("perf_model_load_ms"),
        "perf_ttft_ms":            diagnostics.get("perf_ttft_ms"),
        "perf_prompt_tokens":      diagnostics.get("prompt_eval_count") or diagnostics.get("prompt_tokens"),
        "perf_output_tokens":      diagnostics.get("eval_count") or diagnostics.get("output_tokens"),
        "perf_speed_tok_s":        diagnostics.get("eval_rate"),
    }
    # Tokens-per-second fallback if Ollama didn't report
    if not backend["perf_speed_tok_s"] and backend["perf_output_tokens"] and client["gen_ms"]:
        backend["perf_speed_tok_s"] = round(backend["perf_output_tokens"] / (client["gen_ms"]/1000), 1)

    result = {
        "label": label,
        "prompt": message,
        "client": client,
        "backend": backend,
        "response_chars": output_chars,
        "response_preview": ("".join(full_response))[:200].replace("\n", " "),
    }
    if not warmup:
        print(f"\n=== {label} ===")
        print(f"  Prompt: {message[:80]}")
        print(f"  Preview: {result['response_preview'][:120]}")
        print(f"  Response chars: {output_chars}")
        print(f"  Path (client-detected): {path_label} | Backend mode: {backend['mode']} | Model: {backend['model']}")
        print(f"  -- CLIENT TIMING --")
        print(f"    HTTP headers:     {client['http_headers_ms']:>7} ms")
        print(f"    stream_start:     {client['stream_start_ms']:>7} ms  (backend confirms stream is active)")
        print(f"    TTFT:             {client['ttft_ms']:>7} ms  ⭐ FIRST REAL TOKEN")
        print(f"    Generation:       {client['gen_ms']:>7} ms  (after TTFT -> done)")
        print(f"    Total end-to-end: {client['total_ms']:>7} ms")
        print(f"    Est speed:        {tok_per_sec} tok/s (chars/4 ÷ gen_s)")
        print(f"  -- BACKEND PIPELINE (from diagnostics) --")
        for k, v in backend.items():
            if k in ("path", "mode", "model", "classification_mode"):
                continue
            if v is None:
                continue
            if "ms" in k:
                print(f"    {k.replace('perf_',''):22s}: {v:>7} ms")
            elif "tok" in k or "count" in k or k.endswith("_tokens"):
                print(f"    {k.replace('perf_',''):22s}: {v:>7} tokens")
            elif k == "perf_speed_tok_s":
                print(f"    {k.replace('perf_',''):22s}: {v:>7} tok/s")
            else:
                print(f"    {k.replace('perf_',''):22s}: {v}")
    return result


def main():
    # 1) Warm-up: send one tiny question to make Django + Ollama fully warm,
    #    so the benchmark reflects real interactive latency not cold-start.
    print("[1/4] WARMUP (not counted in averages)...")
    warm = run_one("Warmup", "Hi", warmup=True)
    if warm is None:
        print("Warmup failed — aborting.")
        sys.exit(1)
    print(f"  Warmup TTFT: {warm['client']['ttft_ms']} ms  |  Path: {warm['backend']['path']}")
    time.sleep(2)

    # 2) Run each benchmark twice. The first of each pair may still have
    #    some tiny lazy-import cost; the second is fully warm.
    results = []
    for idx, (label, msg) in enumerate(BENCHMARKS, start=2):
        print(f"\n[{idx}/4] RUN A (first try): {label}")
        a = run_one(label + " (A)", msg)
        time.sleep(2)
        print(f"\n[{idx}/4] RUN B (fully warm): {label}")
        b = run_one(label + " (B)", msg)
        results.append((label, msg, a, b))
        time.sleep(2)

    # 3) Summary table
    print("\n" + "=" * 100)
    print("SUMMARY — AFTER OPTIMIZATION (use RUN-B = fully-warm values for apples-to-apples)")
    print("=" * 100)
    header = f"{'Benchmark':<38s} {'PATH':<12s} {'TTFT(ms)':>9s} {'Total(ms)':>10s} {'Tok/s':>7s} {'Model':<10s}"
    print(header)
    print("-" * len(header))
    for label, msg, a, b in results:
        chosen = b or a  # prefer warm run
        if not chosen:
            continue
        c = chosen["client"]
        bk = chosen["backend"]
        speed = bk.get("perf_speed_tok_s") or "?"
        print(f"{label[:38]:<38s} {str(bk.get('path') or bk.get('mode') or '?')[:12]:<12s} "
              f"{c['ttft_ms']:>9.1f} {c['total_ms']:>10.1f} {str(speed):>7s} {str(bk.get('model') or '')[:10]:<10s}")
    print("=" * 100)


if __name__ == "__main__":
    main()
