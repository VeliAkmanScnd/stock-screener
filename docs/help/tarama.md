# Tarama

Tarama sekmesi, seçilen evrendeki sembolleri zaman dilimine göre indirir, filtreleri ve isteğe bağlı Pine AL koşulunu uygular. Sonuçlar tabloda görünür; aynı anda Performans’a yazılabilir ve Telegram’a gidebilir.

Aynı tarama aynı hisseyi **aynı fiyattan** yeniden yakalarsa satır gösterilmez; Telegram ve e-posta da gitmez. Fiyat değişirse sinyal yeniden gelir.

## Adım adım

1. **Hisse evreni** seçin. Özel liste için sembolleri yazıp kaydedebilirsiniz.
2. **Zaman dilimi** seçin. 15m tarama, 15 dakikalık kapanmış son bara bakar.
3. **Maks. taranacak hisse** ile evreni kısaltın (deneme için 30–50 yeter).
4. Teknik filtreleri işaretleyin veya Pine script seçin.
5. Telegram’a gitsin istiyorsanız kutuyu açık bırakın.
6. **Taramayı Başlat**.

## Örnek: BIST günlük EMA

- Evren: **BIST**
- Zaman: **Günlük (1D)**
- Filtre: EMA kesişimi 9 / 21, RSI 40–70
- Başlat → eşleşenler (ör. THYAO, AKBNK) sonuç tablosunda
- **TV listesi indir** ile TradingView izleme listesine aktarın
- **Performansa ekle** yedek yoldur; başarılı tarama zaten otomatik ekler

## Örnek: NASDAQ 15m Bias×TS

- Evren: **NASDAQ**
- Zaman: **15 dakika**
- Kayıtlı Pine: Bias×TS, yön AL (veya her iki yön)
- Telegram açık, BIST grubu için ayrı bot token + chat id girilmiş olsun
- Sinyal **kapanmış son barda** varsa eşleşir. Oluşan (henüz kapanmamış) bar sayılmaz.

## Özel liste

`THYAO, AKBNK` veya satır satır yazın. **Liste piyasası** doğru olsun: BIST hissesi için BIST, `F_THYAO1026` için VIOP.

Kayıtlı listeler bu tarayıcıda saklanır. Başka PC / VPS’te görünmez.

## Pine Script

- `.txt` yükleyin, isim verin, kaydedin.
- **Sadece Pine AL** kutusu, teknik filtrelerle birleştirir veya yalnızca Pine kullanır.
- Destek: `plotshape` AL, `alertcondition`, `ta.ema` / `ta.rsi` benzeri ifadeler, Bias×TS özel motoru.
- Ayarlar (periyot, uzaklık, tarama yönü) script seçilince çıkar.

Karmaşık Pine çalışmazsa **Manuel koşul** yazın: `crossover(ema(close,9), ema(close,21))`.

## Sonuçlar

- Sembol ve fiyat
- Tarama özeti: hangi filtre / Pine kullanıldı
- TV `.txt` dışa aktarma
- Telegram: her eşleşme ayrı kart (Fiyat, Yön AL|SAT, Kar AL, Stop)

Boş sonuçta Telegram mesajı gitmez.
