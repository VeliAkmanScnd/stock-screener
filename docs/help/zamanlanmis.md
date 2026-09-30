# Zamanlanmış taramalar

Tarama ekranındaki **Zamanlanmış tarama** mevcut evren, filtre, Pine ve periyodu kaydeder. Sunucu çalışıyorsa seçilen gün/saatte tekrar tarar. Aynı hisse aynı fiyattan yeniden eşleşirse bildirim gitmez.

VPS’te sunucu düşmesin diye `install-windows-task.ps1` (5 dk watchdog) kurun — README / Genel bakış.

## Oluşturma

1. Taramayı elle bir kez ayarlayın (evren, 15m, Pine, Telegram).
2. **Zamanlanmış tarama**’ya basın.
3. **Preset adı** verin: `Bias TS NASDAQ 15m`. Bu isim Performans kaynağı ve “tarama adı” olur.
4. **Periyot** tarama zaman dilimiyle aynı seçeneklerdir (5m … 1W).
5. Saat / pencere ve haftanın günlerini seçin.
6. Bildirim kanalını seçin: **e-posta**, **Telegram** veya ikisi. En az biri gerekir; e-posta zorunlu değildir.
7. Seçtiğiniz kanala göre adres / bot bilgilerini doldurun.
8. Kaydedin. Mevcut taramalarda **Düzenle** ile aynı seçimler değiştirilebilir.

## Örnek: her 15 dakikada VIOP

- Ad: `Viop taraması`
- Periyot: 15 dakika
- Pencere: **Başlangıç 10 / Bitiş 18 (dahil)** → 10:00–18:45 arası her çeyrek
- Bildirim: Telegram (e-posta kapalı kalabilir)
- Telegram: VIOP bot + VIOP grup chat id

Bitiş 14 veya 15 ise öğleden sonra “sonraki çalışma yarın 10:00” görünür — bu normaldir; BIST/VIOP için bitişi **18** yapın.

Her çalışmada eşleşmeler Performans’a eklenir. TP sonrası açık bir AL varsa, yeni SAT satırı onu **ters sinyal** ile kapatır.

## Örnek: her gün 09:35 BIST

- Ad: `BIST Bias günlük`
- Periyot: 1 gün
- Saat 9, dakika 35, Pzt–Cum
- Ayrı BIST bot + Hisse Günlüğü chat id

## Liste ve durum

Tarama kartındaki zamanlanmış tablo: son çalışma, eşleşme sayısı, seçilen bildirim kanalları, e-posta / Telegram hatası.

- **Şimdi çalıştır** kuyruğa alır (aynı anda tek tarama; SQLite nedeniyle sıralı).
- **Düzenle** boş token ile kayıtlı bot token’ı silmez.
- 15m/5m pencerelerde bir tarama uzun sürse bile bir sonraki `:00/:15/:30/:45` slotu atlanmaz (önceki sürümde yavaş biten tur sonraki slotu kesebiliyordu).
- Sunucu yeniden başlarken takılı `running` kayıtları temizlenir.

## Çalışmıyor gibi görünürse

1. Özet → servis / zamanlayıcı ayakta mı?
2. Zamanlanmış satırda **açık** mı, pencere saati (ör. 10–18 İstanbul) ve haftanın günü uygun mu?
3. Logda `Skipping scheduled scan` var mı?
- Telegram test butonu, yazdığınız token+chat’e deneme mesajı yollar.

## Dikkat

- Planlar yalnızca bu uygulamanın süreci ayaktayken işler (PC veya VPS).
- Aynı tarama hem PC hem VPS’te çalışırsa çift e-posta / çift izleme satırı oluşabilir. Birini kapatın.
- Periyot ile evren zaman dilimini karıştırmayın: kayıt, tarama yaptığınız **mum periyodunu** taşır.
