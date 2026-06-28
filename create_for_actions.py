"""
GitHub Actions上で実行するアカウント作成スクリプト。
プロキシなし（GitHub=Azureのデータセンターip）でアカウントを作成し、
SSH経由でVPSのプールに追加する。
"""
from __future__ import annotations
import json, os, random, subprocess, sys, time
from datetime import datetime, timezone, timedelta
import httpx

JST = timezone(timedelta(hours=9))

BASE_URL = "https://api.find.nepopo.jp/2.0"
APP_KEY = os.environ["HIMATALK_APP_KEY"]
APP_SECRET = os.environ["HIMATALK_APP_SECRET"]
VPS_HOST = os.environ["VPS_HOST"]
VPS_USER = os.environ.get("VPS_USER", "root")
POOL_A = "/root/himatalkbot_a/accounts.json"
POOL_B = "/root/himatalkbot_b/accounts.json"

HEADERS = {
    "User-Agent": "%E3%81%B2%E3%81%BE%E3%83%88%E3%83%BC%E3%82%AF%EF%BC%8B/81 CFNetwork/1240.0.4 Darwin/20.6.0",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "*/*",
    "Accept-Language": "ja-jp",
    "Cache-Control": "no-cache",
    "Accept-Encoding": "gzip, deflate, br",
}


SSH_ARGS = [
    "-i", os.path.expanduser("~/.ssh/id_rsa"),
    "-o", "StrictHostKeyChecking=no",
    "-o", "ConnectTimeout=15",
    "-o", "BatchMode=yes",
]


def ssh(cmd: str) -> str:
    r = subprocess.run(
        ["ssh", *SSH_ARGS, f"{VPS_USER}@{VPS_HOST}", cmd],
        capture_output=True, text=True, timeout=30
    )
    if r.returncode != 0:
        print(f"  [ssh error] rc={r.returncode} stderr={r.stderr[:300]}", flush=True)
    return r.stdout.strip()


def ssh_write(path: str, data: str) -> None:
    r = subprocess.run(
        ["ssh", *SSH_ARGS, f"{VPS_USER}@{VPS_HOST}", f"cat > {path}"],
        input=data, capture_output=True, text=True, timeout=30
    )
    if r.returncode != 0:
        print(f"  [ssh write error] rc={r.returncode} stderr={r.stderr[:300]}", flush=True)
    else:
        print(f"  [ssh write ok] {path}", flush=True)


def get_current_ip(client) -> str:
    try:
        return client.get("https://api.ipify.org", timeout=10).text.strip()
    except Exception:
        return "unknown"


def rand_name():
    kana = "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん"
    return "".join(random.choices(kana, k=random.randint(3, 5)))


def create_female(client, ip: str):
    now = datetime.now(JST).strftime("%Y%m%d%H%M")
    r1 = client.post(f"{BASE_URL}/user/register4.php", data={
        "app_key": APP_KEY, "app_secret": APP_SECRET, "lang": "ja-JP",
        "user_sex": "2", "user_name": rand_name(), "app_version": "2.4.0",
        "now": now, "personID": "",
    }, headers=HEADERS)
    print(f"  [register4] {r1.status_code} {r1.text[:100]}", flush=True)
    d1 = r1.json()
    act_id, act_key = d1.get("actId"), d1.get("actKey")
    if not act_id or not act_key:
        return None
    time.sleep(2)
    r2 = client.post(f"{BASE_URL}/user/activate.php", data={
        "actId": str(act_id), "actKey": act_key, "app_key": APP_KEY,
    }, headers=HEADERS)
    print(f"  [activate]  {r2.status_code} {r2.text[:100]}", flush=True)
    d2 = r2.json()
    uid, key = d2.get("uid"), d2.get("key")
    if not uid or not key:
        return None
    return {"user_id": str(uid), "user_key": key, "sex": "2", "created_ip": ip}


def load_remote_pool(path: str) -> list:
    out = ssh(f"cat {path} 2>/dev/null || echo '[]'")
    try:
        return json.loads(out)
    except Exception:
        return []


def save_remote_pool(path: str, data: list) -> None:
    ssh_write(path, json.dumps(data, ensure_ascii=False))


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else random.randint(3, 5)
    print(f"[{datetime.now(JST)}] 作成数: {count}個", flush=True)

    created = []
    with httpx.Client(timeout=30) as client:
        ip = get_current_ip(client)
        print(f"GitHub Actions IP: {ip}", flush=True)
        for i in range(count):
            print(f"\n[{i+1}/{count}]", flush=True)
            try:
                acc = create_female(client, ip)
            except Exception as e:
                print(f"  例外: {e}", flush=True)
                continue
            if acc:
                created.append(acc)
                print(f"  完了: uid={acc['user_id']}", flush=True)
            else:
                print(f"  失敗", flush=True)
            if i < count - 1:
                time.sleep(3)

    if not created:
        print("生成できず終了", flush=True)
        sys.exit(0)

    pool_a = load_remote_pool(POOL_A)
    pool_b = load_remote_pool(POOL_B)
    print(f"\nVPS現在: A={len(pool_a)}個 B={len(pool_b)}個", flush=True)

    for acc in created:
        if len(pool_a) <= len(pool_b):
            pool_a.append(acc)
            dest = "A"
        else:
            pool_b.append(acc)
            dest = "B"
        print(f"→ Bot {dest} に追加: uid={acc['user_id']}", flush=True)

    save_remote_pool(POOL_A, pool_a)
    save_remote_pool(POOL_B, pool_b)
    print(f"\n完了: A={len(pool_a)}個 B={len(pool_b)}個", flush=True)


if __name__ == "__main__":
    main()
