# İzleme

İzleme, taramadan gelen her hisseyi bir pozisyon gibi tutar: giriş fiyatı, hedef, stop, güncel fiyat, endeks karşılaştırması ve grafik.

## Otomatik ekleme

Zamanlanmış veya manuel tarama eşleşme üretince satır açılır.

Aynı hisse + aynı periyot + aynı yön zaten açıksa ikinci kez eklenmez.

## Periyot TP/SL benchmark

Yeni kayıt, taramanın zaman dilimine göre hedef/stop alır (kutu **Periyoda göre TP/SL benchmark kullan** açıkken):

| Periyot | Hedef | Stop |
| --- | --- | --- |
| 15 dakika | +2% | −1.5% |
| 1 saat | +3% | −2% |
| 1 gün | +8% | −5% |

15m, 1s ve 1g **önerilen** olarak işaretlidir. Kutuyu kapatırsanız **Özel hedef / stop %** (varsayılan 8 / 5) tüm periyotlara uygulanır.

## Örnek

NASDAQ 15m taraması TER’i 80.00’den getirdi.

- Hedef: 81.60 (+2%)
- Stop: 78.80 (−1.5%)
- Saat 11:00’de 1s bar high 81.70 → **TP sonrası**
- Sonraki SAT sinyali veya 10 işlem günü dolana kadar izlenir
- Stop, high/low ile de kontrol edilir; aynı saatte hem TP hem SL varsa **stop** yazılır

## Aktif ve Geçmiş

- **Aktif:** `active` ve `TP sonrası`
- **Geçmiş:** stop, ters sinyal, arşiv, manuel kapatma

Kolonlar: yön, filtre, max %, endeks. Satırdan **Grafik** ile fiyat eğrisi açılır.

## Fiyat güncelleme

Pzt–Cum **saat başı** 10:00–23:00 (İstanbul). İntraday pozisyonlarda son saatlik barların high/low’u kullanılır; günlük taramada günlük bar yeterlidir.

**Fiyatları güncelle** butonu aynı işi şimdi yapar.

## Manuel işlemler

- **TP/SL:** tek satırın hedefini değiştirin
- **Kaldır / Listeyi kapat:** manuel kapatma
- **Geçmiş → seçilenleri aktife al:** yeniden açar (daha önce TP olduysa yine TP sonrası)
