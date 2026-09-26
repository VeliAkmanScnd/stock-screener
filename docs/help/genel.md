# Genel bakış

TradeLABtr, ABD, BIST, VIOP ve Binance evrenlerinde teknik + Pine filtreleriyle hisse tarayan, eşleşmeleri izleyen ve performansını ölçen bir web uygulamasıdır.

Sunucu **açıkken** çalışır. Pencereyi kapatırsanız zamanlanmış taramalar ve saatlik fiyat güncellemesi durur.

## Sekmeler

| Sekme | Ne işe yarar |
| --- | --- |
| **Tarama** | Evren, periyot, filtre ve Pine seçip tarama çalıştırırsınız. |
| **İzleme** | Taramadan gelen hisselerin fiyatı, TP/SL ve grafiği. |
| **Performans** | Hangi periyot / tarama / filtrenin daha verimli olduğunu sıralar. |
| **Yardım** | Bu dökümanlar. |
| **Kullanıcılar** | Yalnızca admin görür. |

## Tipik bir gün

1. **Tarama**’da evreni seçin (ör. NASDAQ), zaman dilimini **15 dakika** yapın.
2. Pine veya teknik filtreleri açın, **Taramayı Başlat**.
3. Eşleşmeler otomatik **İzleme**’ye düşer. Telegram açıksa her hisse ayrı kart gider.
4. Saat başı fiyat (intraday’de high/low) güncellenir.
5. Birkaç gün sonra **Performans**’ta 15m ile 1s taramayı **beklenen R** ile karşılaştırın.

## Örnek senaryo

Bias×TS ile NASDAQ 15m tarama 3 hisse getirdi: TER, RIGL, XYZ.

- Her biri **+2% hedef / −1.5% stop** ile izlemeye yazılır (15m benchmark).
- TER +2%’ye 4 saatte ulaşır → durum **TP sonrası**; ters SAT sinyali veya 10 işlem günü beklenir.
- RIGL −1.5% stop olur → kapanır, SL süresi kaydedilir.
- XYZ 10 iş günü dolunca **arşiv** olur; max % raporda durur.

## İndirme

Bu sayfanın üstündeki **Bu başlığı indir** yalnızca açık dökümanı `.md` olarak kaydeder. **Tümünü indir** bütün Yardım dosyalarını zip’ler.
