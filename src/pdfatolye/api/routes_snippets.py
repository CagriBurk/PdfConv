"""Markdown → PDF "Şablon ekle" menüsündeki kullanıcı şablonları (bkz. `pdfatolye.snippets`).

Oturum çerezi her uçta zorunlu (SessionGuard). Yazma işlemleri telefon modunda eşleşmiş cihaza da
açık: imzalar ve dosyalar gibi kullanıcının kendi içeriğidir, yalnızca sabit şablon klasörüne
düz metin yazılır; ayarlar gibi bilgisayarın yapılandırmasını değiştirmez.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from pdfatolye.snippets import DIR_NAME, MAX_BODY_CHARS, SnippetStore

router = APIRouter(prefix="/api/md/snippets")

# Asıl sınırlar `snippets` modülünde (Türkçe mesajla); bunlar yalnızca aşırı büyük isteği keser.
NAME_LIMIT = 500
BODY_LIMIT = MAX_BODY_CHARS * 4


class NewSnippet(BaseModel):
    name: str = Field(max_length=NAME_LIMIT)
    body: str = Field(max_length=BODY_LIMIT)


class SnippetChange(BaseModel):
    new_name: str | None = Field(default=None, max_length=NAME_LIMIT)
    body: str | None = Field(default=None, max_length=BODY_LIMIT)


def _store(request: Request) -> SnippetStore:
    return SnippetStore(request.app.state.settings.data_dir / DIR_NAME)


@router.get("")
def list_snippets(request: Request) -> dict:
    store = _store(request)
    return {"folder": str(store.root), "items": [s.to_dict() for s in store.list()]}


@router.post("")
def add_snippet(request: Request, body: NewSnippet) -> dict:
    return _store(request).add(body.name, body.body).to_dict()


@router.put("/{name}")
def update_snippet(request: Request, name: str, body: SnippetChange) -> dict:
    return _store(request).update(name, new_name=body.new_name, body=body.body).to_dict()


@router.delete("/{name}")
def delete_snippet(request: Request, name: str) -> dict:
    _store(request).delete(name)
    return {"ok": True}
