---
title: Devre Analizi — Hafta 3
author: Çağrı Burak
date: 2026-10-31
pdf:
  icindekiler: true
---

# Kirchhoff Yasaları #ders

Bir düğüme giren akımların toplamı çıkanlara eşittir: $\sum_{k} I_k = 0$. Gerilim için
$\sum V = 0$. Fiyat 100$ ile 200$ arası (bu formül değil).

> [!note] Tanım: Düğüm
> İki ya da daha fazla elemanın birleştiği nokta. ==Çok önemli: $R_{eş} = R_1 + R_2$==

## Seri ve Paralel Dirençler

$$
R_{eş} = \left( \sum_{i=1}^{n} \frac{1}{R_i} \right)^{-1}
$$ (1)

\begin{align}
V &= I R \\
P &= V I = I^2 R = \frac{V^2}{R}
\end{align}

| Eleman | Birim | Sembol |
|---|---|---|
| Direnç | Ohm | $\Omega$ |
| Kapasitör | Farad | $F$ |

> [!warning]- Sık yapılan hata
> Akım yönünü baştan seçip **tutarlı** kullan. Yanlış: $\frac{1}{R$

```python
def esdeger(*R):
    return 1 / sum(1 / r for r in R)  # %% yorum değil
```

%% Bu satır PDF'te görünmemeli %%

\newpage

## Thévenin Eşdeğeri

[[Norton Teoremi|Norton]] ile ilişkilidir. Kimya da çalışır: $\ce{H2O}$.

### Adımlar

1. Yükü çıkar
2. $V_{th}$'yi bul
3. $R_{th}$'yi bul

- [x] Tamamlandı
- [ ] Ödev 3
