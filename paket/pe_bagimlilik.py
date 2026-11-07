"""Bir .exe'nin aynı klasördeki DLL bağımlılıklarını (özyinelemeli) bulur.

Paketleme sırasında Tesseract'ın yalnızca gereken DLL'lerini kopyalamak için: eğitim araçlarının
(pango, cairo...) DLL'leri paketi gereksiz büyütür. Saf Python PE okuyucu; bağımlılık yok.
"""

from __future__ import annotations

import struct
from pathlib import Path


def imports(path: Path) -> list[str]:
    """PE dosyasının içe aktardığı DLL adları (normal + gecikmeli yükleme)."""
    data = path.read_bytes()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        return []
    coff = pe + 4
    n_sections = struct.unpack_from("<H", data, coff + 2)[0]
    opt_size = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    magic = struct.unpack_from("<H", data, opt)[0]
    dirs = opt + (112 if magic == 0x20B else 96)
    sections = []
    sec = opt + opt_size
    for i in range(n_sections):
        off = sec + 40 * i
        vsize, vaddr, rsize, raddr = struct.unpack_from("<IIII", data, off + 8)
        sections.append((vaddr, max(vsize, rsize), raddr))

    def rva(r: int) -> int | None:
        for vaddr, size, raddr in sections:
            if vaddr <= r < vaddr + size:
                return r - vaddr + raddr
        return None

    def cstr(off: int) -> str:
        end = data.index(b"\0", off)
        return data[off:end].decode("ascii", "replace")

    names: list[str] = []
    for index, entry_size, name_field in ((1, 20, 12), (13, 32, 4)):  # içe aktarma, gecikmeli
        table_rva = struct.unpack_from("<I", data, dirs + 8 * index)[0]
        off = rva(table_rva) if table_rva else None
        while off is not None:
            name_rva = struct.unpack_from("<I", data, off + name_field)[0]
            if not name_rva:
                break
            name_off = rva(name_rva)
            if name_off is not None:
                names.append(cstr(name_off))
            off += entry_size
    return names


def local_closure(exe: Path) -> list[Path]:
    """`exe`'nin klasöründe bulunan DLL bağımlılıkları (sistem DLL'leri hariç), özyinelemeli."""
    folder = exe.parent
    local = {p.name.lower(): p for p in folder.glob("*.dll")}
    seen: dict[str, Path] = {}
    stack = [exe]
    while stack:
        for name in imports(stack.pop()):
            key = name.lower()
            if key in local and key not in seen:
                seen[key] = local[key]
                stack.append(local[key])
    return sorted(seen.values())


if __name__ == "__main__":
    import sys

    deps = local_closure(Path(sys.argv[1]))
    total = sum(p.stat().st_size for p in deps)
    for p in deps:
        print(p.name)
    print(f"{len(deps)} DLL, {total / 1024 / 1024:.1f} MB")
