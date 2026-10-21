"""
Copy the deployment file set (deploy_manifest.txt) to a target folder.

Usage:
    python make_deploy_copy.py <target_dir>
    python make_deploy_copy.py D:\\deploy\\sales-admin-autocount

The target gets the same relative paths (routers/..., docs/...).
.env and *.db are intentionally not in the manifest - create them on the
server (.env.example is the template).
"""

import shutil
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
MANIFEST = SRC / "deploy_manifest.txt"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python make_deploy_copy.py <target_dir>")
        return 2

    target = Path(sys.argv[1]).resolve()
    files = [
        ln.split("#", 1)[0].strip() for ln in MANIFEST.read_text().splitlines()
        if ln.split("#", 1)[0].strip()
    ]

    copied, missing = [], []
    for rel in files:
        src = SRC / rel
        if not src.exists():
            missing.append(rel)
            continue
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel)

    print(f"Copied {len(copied)} files -> {target}")
    for rel in missing:
        print(f"  MISSING (skipped): {rel}")
    print("\nOn the server:")
    print("  1. copy .env.example to .env and fill in AOTG/LLM/mail/Telegram creds")
    print("  2. set ENVIRONMENT=production and a non-SQLite DATABASE_URL")
    print("  3. pip install -r requirements.txt")
    print("  4. python init_db.py && python load_aotg_catalog.py --load --spec-file docs/Autocount_API_Definition.json")
    print("  5. python sync_item_catalog.py        # pull item catalogue into the SKU index")
    print("     python setup_test_deployment.py --add-staff <telegram_id> --roles admin")
    print("  6. uvicorn main:app --host 0.0.0.0 --port 8000   (app)")
    print("     python gmail_poller.py                       (separate process)")
    print("     python outlook_poller.py                     (separate process)")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
