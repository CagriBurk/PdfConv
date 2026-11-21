"""Kim neyi görür (GUVENLIK_PLANI.md, adım 5).

Bu bilgisayar her şeyi görür. Telefon modunda eşleşmiş bir cihaz yalnızca kendi yüklediği
dosyaları, onlardan üretilen çıktıları, kendi imzalarını ve kendi işlerini görür; Obsidian
kasası ona kapalıdır. Böylece Wi-Fi'de ele geçirilen bir cihaz oturumu bu bilgisayardaki
belgeleri açamaz.

İsteğin sahibi `SessionGuard` tarafından bağlam değişkenine yazılır; FastAPI eşzamanlı uçları
iş parçacığı havuzunda çalıştırırken bağlamı taşır. İşler kendi iş parçacığında, işi başlatanın
kimliğiyle çalışır (`JobManager._run`). Bağlam yoksa (komut satırı, temizlik, testler) erişim
tamdır.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextvars import ContextVar

# None: bu bilgisayar (her şeyi görür). Metin: eşleşmiş cihazın kimliği.
_owner: ContextVar[str | None] = ContextVar("toolia_sahip", default=None)


def current() -> str | None:
    return _owner.get()


def is_device() -> bool:
    return _owner.get() is not None


def can_see(owner: str | None) -> bool:
    """Şu anki istek sahibi `owner`'a ait bir şeyi görebilir mi?"""
    viewer = _owner.get()
    return viewer is None or viewer == owner


@contextlib.contextmanager
def acting_as(owner: str | None) -> Iterator[None]:
    token = _owner.set(owner)
    try:
        yield
    finally:
        _owner.reset(token)
