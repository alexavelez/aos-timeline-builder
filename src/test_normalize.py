from datetime import date

from src.normalize import normalize_date


def show(label: str, nd):
    print(f"{label:15} → value={nd.value}, precision={nd.precision}, is_present={nd.is_present}")


print("\n=== DAY PRECISION ===")
show("YYYY-MM-DD", normalize_date("2023-07-15"))
show("YYYY/MM/DD", normalize_date("2023/07/15"))
show("MM/DD/YYYY", normalize_date("07/15/2023"))

print("\n=== MONTH PRECISION ===")
show("YYYY-MM", normalize_date("2022-07"))
show("YYYY/MM", normalize_date("2022/07"))
show("MM/YYYY", normalize_date("07/2022"))
show("MM-YYYY", normalize_date("07-2022"))

print("\n=== YEAR PRECISION ===")
show("YYYY", normalize_date("2021"))

print("\n=== PRESENT ===")
show("Present", normalize_date("Present"))
show("current", normalize_date("current"))

print("\n=== INVALID / UNKNOWN ===")
show("bad day", normalize_date("2023-02-31"))
show("text", normalize_date("Summer 2022"))
show("empty", normalize_date(""))
show("none", normalize_date(None))
