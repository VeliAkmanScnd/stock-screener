# Zamanlanmış taramalar

Tarama ekranındaki **Zamanlanmış tarama** mevcut evren, filtre, Pine ve periyodu kaydeder. Sunucu çalışıyorsa seçilen gün/saatte tekrar tarar.

## Oluşturma

1. Taramayı elle bir kez ayarlayın (evren, 15m, Pine, Telegram).
2. **Zamanlanmış tarama**’ya basın.
3. **Preset adı** verin: `Bias TS NASDAQ 15m`. Bu isim İzleme kaynağı ve Performans “tarama adı” olur.
4. **Periyot** tarama zaman dilimiyle aynı seçeneklerdir (5m … 1W).
5. Saat / pencere ve haftanın günlerini seçin.
6. E-posta ve Telegram alanlarını doldurun.
7. Kaydedin.

## Örnek: her 15 dakikada VIOP

- Ad: `Viop taraması`
- Periyot: 15 dakika
- Pencere: 10:00–18:00, dakika 0/15/30/45 (ekrana göre)
- Telegram: VIOP bot + VIOP grup chat id
- E-posta isteğe bağlı

Her çalışmada eşleşmeler İzleme’ye eklenir. TP sonrası açık bir AL varsa, yeni SAT satırı onu **ters sinyal** ile kapatır.

## Örnek: her gün 09:35 BIST

- Ad: `BIST Bias günlük`
- Periyot: 1 gün
- Saat 9, dakika 35, Pzt–Cum
- Ayrı BIST bot + Hisse Günlüğü chat id

## Liste ve durum

Tarama kartındaki zamanlanmış tablo: son çalışma, eşleşme sayısı, e-posta / Telegram hatası.

- **Şimdi çalıştır** kuyruğa alır (aynı anda tek tarama).
- **Düzenle** boş token ile kayıtlı bot token’ı silmez.
- Telegram test butonu, yazdığınız token+chat’e deneme mesajı yollar.

## Dikkat

- Planlar yalnızca bu uygulamanın süreci ayaktayken işler (PC veya VPS).
- Aynı tarama hem PC hem VPS’te çalışırsa çift e-posta / çift izleme satırı oluşabilir. Birini kapatın.
- Periyot ile evren zaman dilimini karıştırmayın: kayıt, tarama yaptığınız **mum periyodunu** taşır.
