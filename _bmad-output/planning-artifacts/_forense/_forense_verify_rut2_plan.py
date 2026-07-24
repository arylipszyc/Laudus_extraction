# Story 12.1 Task 3 — verificación mecánica de cobertura del plan RUT2 (descartable, NO commitear)
import json
import sys
from collections import Counter

PLAN = r"c:\dev\bmad-workspace-new\family-office-eag\_bmad-output\planning-artifacts\rut2-plan-cuentas-laudus-2026-07-10.json"

with open(PLAN, encoding="utf-8") as f:
    accounts = json.load(f)

numbers = [a["accountNumber"] for a in accounts]
total = len(accounts)

# 1. Toda cuenta tiene raíz en {1,2,3,4,6,7,8} (cero huérfanas)
VALID_ROOTS = set("1234678")
orphans = [n for n in numbers if n[0] not in VALID_ROOTS]

# 2. Hojas = cuenta sin descendiente por prefijo de accountNumber
number_set = set(numbers)
def is_leaf(n):
    return not any(m != n and m.startswith(n) for m in number_set)
leaves = [n for n in numbers if is_leaf(n)]

# 3. Conteos por raíz y por sub-entidad
by_root = Counter(n[0] for n in numbers)
ffcc = sum(v for k, v in by_root.items() if k in "1234")
jab = sum(v for k, v in by_root.items() if k in "678")

# 4. Duplicados de accountNumber (sanidad)
dupes = [n for n, c in Counter(numbers).items() if c > 1]

print(f"total cuentas          : {total}")
print(f"huérfanas (raíz inválida): {len(orphans)} {orphans if orphans else ''}")
print(f"hojas                  : {len(leaves)}")
print(f"duplicados accountNumber: {len(dupes)} {dupes if dupes else ''}")
print(f"FFCC (raíces 1-4)      : {ffcc}")
print(f"JAB  (raíces 6-8)      : {jab}")
print("por raíz               :", dict(sorted(by_root.items())))
by_root_leaves = Counter(n[0] for n in leaves)
print("hojas por raíz         :", dict(sorted(by_root_leaves.items())))
ffcc_leaves = sum(v for k, v in by_root_leaves.items() if k in "1234")
jab_leaves = sum(v for k, v in by_root_leaves.items() if k in "678")
print(f"hojas FFCC / JAB       : {ffcc_leaves} / {jab_leaves}")

# TC marcadas presentes y son hojas
for tc in ("871005", "873005"):
    status = "hoja" if tc in set(leaves) else ("EXISTE pero NO hoja" if tc in number_set else "NO EXISTE")
    print(f"TC {tc}              : {status}")

# Asserts duros (los números esperados del story file / Dev Notes)
expected = {"total": 357, "leaves": 309, "ffcc": 118, "jab": 239,
            "by_root": {"1": 30, "2": 4, "3": 11, "4": 73, "6": 16, "7": 4, "8": 219}}
ok = (total == expected["total"] and len(leaves) == expected["leaves"]
      and not orphans and not dupes
      and ffcc == expected["ffcc"] and jab == expected["jab"]
      and dict(by_root) == expected["by_root"])
print("\nVERIFICACION:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
