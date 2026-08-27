import requests, json, time, sys

login = requests.post('http://localhost:8000/api/auth/login/', json={'email':'test@vision.ai','password':'Vision123!'})
if login.status_code != 200:
    print("LOGIN FAILED:", login.status_code, login.text)
    sys.exit(1)
tok = login.json()['access']
headers = {'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'}

conv = requests.post('http://localhost:8000/api/conversations/', json={}, headers=headers).json()
cid = conv['id']
print(f'=== BEFORE BENCHMARK on conversation {cid} ===')
print()

tests = [
    ('Simple greeting', 'Hello'),
    ('Simple factual', 'What is HTML?'),
    ('Simple math', 'What is 2 + 2?'),
    ('Simple definition', 'What is a variable in programming?'),
    ('Explain briefly', 'Explain recursion briefly'),
]

results = []
for name, msg in tests:
    print(f'Running: {name} -&gt; "{msg}"')
    t0 = time.time()
    first_t = None
    chars = 0
    last_chunk = None
    diag = None
    try:
        r = requests.post('http://localhost:8000/api/ai/chat/', json={'message':msg,'conversation_id':cid,'mode':'fast','memory_enabled':False}, headers=headers, stream=True)
        for line in r.iter_lines(decode_unicode=True):
            if not line: continue
            try: j = json.loads(line)
            except: continue
            if j['type'] == 'token':
                if first_t is None: first_t = time.time() - t0
                chars += len(j.get('content',''))
                last_chunk = time.time() - t0
            elif j['type'] == 'diagnostics':
                diag = j['content']
    except Exception as e:
                    print(f'  ERROR: {e}')
    total = time.time() - t0
    ttft = int(first_t*1000) if first_t else None
    total_ms = int(total*1000)
    if first_t and last_chunk:
        gen_ms = int((last_chunk - first_t)*1000)
    else:
        gen_ms = None
    if first_t and chars > 0 and total > first_t:
        tps = int(chars/4 / (total - first_t))
    else:
        tps = 0
    results.append((name, ttft, total_ms, gen_ms, chars, tps))
    print(f'  TTFT={ttft}ms  total={total_ms}ms  gen={gen_ms}ms chars={chars}  speed={tps}t/s')
    if diag: print(f'  Diagnostics: {diag}')
    print()

print('=== SUMMARY ===')
ttfts = [r[1] for r in results if r[1]]
totals = [r[2] for r in results]
if ttfts: print(f'Average TTFT: {int(sum(ttfts)/len(ttfts))}ms')
print(f'Average Total: {int(sum(totals)/len(totals))}ms')
if ttfts: print(f'Worst TTFT: {max(ttfts)}ms')
print(f'Worst Total: {max(totals)}ms')
print(f'Best TTFT: {min(ttfts) if ttfts else None}ms')
