# Performans takibi

Performans sekmesi, taramadan gelen hisselerin **nereye kadar gittiğini** ve **hangi taramanın daha verimli** olduğunu gösterir. İzleme motoru veriyi toplar; bu sekme raporlar.

## Ne izlenir?

Bir hisse taramada görününce saat başı fiyatı güncellenir.

1. **Stop** gelirse kapanır. SL’ye varış saati tutulur.
2. **TP** gelirse kapanmaz. Durum **TP sonrası** olur. Aynı zaman diliminde **ters sinyal** gelene kadar (ör. 15m AL sonrası 15m SAT) veya süre dolana kadar devam eder.
3. En fazla **10 işlem günü** (yaklaşık 2 hafta). Sonra **arşiv**. Böylece maksimum gidilen yer (max %) kaybolmaz.
4. TP ve SL süreleri saat cinsinden saklanır.

Ters sinyal, o periyottaki taramanın **yeniden çalışıp** aksi yön basmasına bağlıdır. Tarama o gün çalışmazsa süre dolunca arşivlenir.

## Benchmark (sayfada da durur)

Yeni izleme bu tablodaki TP/SL ile açılır:

| Periyot | Hedef | Stop | R |
| --- | --- | --- | --- |
| 5 dakika | +1.5% | −1.0% | 1.50R |
| **15 dakika** | **+2%** | **−1.5%** | **1.33R** |
| 30 dakika | +2.5% | −1.8% | 1.39R |
| **1 saat** | **+3%** | **−2%** | **1.50R** |
| 4 saat | +5% | −3% | 1.67R |
| **1 gün** | **+8%** | **−5%** | **1.60R** |
| 1 hafta | +12% | −7% | 1.71R |

Kalın satırlar önerilen karşılaştırma setidir. 15m ile 1g’yi aynı +8/−5 ile kıyaslamayın; 15m’de +8 neredeyse her zaman bir yöne gider.

## Rapor nasıl okunur?

**Sınıflandır**

- **Zaman dilimi** — 15m mi 1s mi 1g mi daha iyi?
- **Tarama adı** — kaydedilmiş zamanlanmış taramanın adı (ör. “Viop taraması”)
- **Tarama × periyot** — aynı isim farklı periyotta ayrı satır
- **İndikatör / filtre** — Bias×TS, EMA, teknik filtreler

**Tarih** boşsa tüm geçmiş gelir.

**Sembol başına ilk sinyal:** aynı hisse birden fazla taramada varsa yalnızca ilk kayıt kalır. Şişirmeyi keser.

## Sıralama: beklenen R

Sıra, **kapanmış** işlemlerin ortalamasına göredir (stop, ters sinyal, arşiv, manuel).

`R = (çıkış − giriş) / stop mesafesi` (SAT’ta işaret ters).

**Beklenen R** = kapanmış işlemlerin ortalama R’si.

- `+0.40R` → ortalama her işlem 0.40 stop kadar kâr
- `−0.20R` → ortalama zarar

**20 kapanmış işlemden az** grup “yetersiz” olur, sıra numarası almaz. İlk hafta “15m en iyi” demeyin.

Açık pozisyonlar **Açık** kolonundadır; sıralamaya girmez.

## Örnek 1 — 15m vs 1 gün

Diyelim ki 40 kapanmış 15m ve 40 kapanmış 1g kaydınız var.

| Grup | Kapanan | Beklenen R | TP % | Ort. max % |
| --- | --- | --- | --- | --- |
| 15 dakika | 40 | +0.35R | 48% | +3.1% |
| 1 gün | 40 | +0.12R | 41% | +6.8% |

1g daha uzağa gitmiş (max %) ama, stop’a göre **15m daha verimli**. Karar: 15m taramayı sık çalıştır, 1g’yi daha seyrek.

## Örnek 2 — tarama adı

| Grup | Kapanan | Beklenen R | Not |
| --- | --- | --- | --- |
| Bias×TS NASDAQ | 55 | +0.28R | Sıra 1 |
| EMA 9/21 BIST | 22 | +0.31R | yetersiz (22≥20, sınırda) |
| Viop taraması | 12 | +0.90R | yetersiz, sıralanmaz |

12 işlemde +0.90R şans olabilir. 20’yi bekleyin.

## Örnek 3 — tek hisse hikâyesi

THYAO, “Viop taraması”, 15m, AL, giriş 92.00.

- 6 saat sonra 93.84 (+2%) → TP, `hours_to_tp ≈ 6`
- İzleme devam, max 95.20 (max % ≈ +3.5)
- 2 gün sonra 15m SAT → **ters sinyal**, çıkış 94.10
- Rapor: TP sayıldı, süre 6 sa, hold ~2 gün, R pozitif

## Geçmiş kayıtlar

Alt tablo aynı filtrelere göre tekil satırlardır: yön, periyot, tarama, filtre, max %, **R**, TP/SL süreleri, durum.

Durumlar: Aktif, TP sonrası, Stop, Ters sinyal, Arşiv, Manuel, Süre doldu.
