# Telegram ve e-posta

Bildirimler taramada eşleşme olduğunda gider. Boş taramada Telegram sessiz kalır.

## Kart formatı

Her eşleşme **ayrı mesajdır**. Dosya (txt) eklenmez, tarama adı başlıkta yazmaz.

Örnek (VIOP):

```
Kontrat: AEFES1!
Fiyat: 184.50
Yön: AL
Kar AL: +4%
Stop: −3%
```

BIST’te sembol `THYAO`, ABD’de `TER` olur. SAT’ta Kar AL aşağı, Stop yukarı hesaplanır.

Telegram kartındaki +4/−3, **İzleme benchmark’ından bağımsızdır**. İzleme 15m için +2/−1.5 kullanır.

## Bot ve grup

1. BotFather’dan bot alın. Token’ı `bot` yazmadan girin: `123456:AAH...`
2. Botu gruba ekleyin, gruba bir mesaj yazın.
3. `https://api.telegram.org/botTOKEN/getUpdates` açın.
4. `chat.id` bulun. Gruplar negatiftir (`-5…` veya `-100…`).

`.env` içindeki `TELEGRAM_BOT_TOKEN` ve `TELEGRAM_CHAT_ID` varsayılandır (çoğu kurulumda VIOP grubu).

## İki grup örneği

| Tarama | Token | Chat id |
| --- | --- | --- |
| VIOP 15m | VIOP bot | −5300663135 |
| BIST günlük | Hisse günlüğü bot | −5005450345 |

Tarama formunda token + chat id **ikisi birden** dolu olsun. Sadece chat id yazıp VIOP botuyla BIST grubuna göndermek “chat not found” verir.

Token ve id’yi yapıştırırken `TOKEN-5005…` tek satır olursa uygulama ayırır; yine de ayrı kutulara yazın.

## Kutular

- **Sonucu Telegram’a gönder** — kapalıysa gitmez (manuel ve zamanlanmış).
- Zamanlanmış düzenlemede boş token, kayıtlı token’ı silmez.
- **Telegram dene** kayıtlı/yazılı kimlikle test mesajı yollar.

## E-posta

SMTP `.env` ile kurulur. Zamanlanmış tarama TV listesini e-postaya ekleyebilir. Birden fazla adres için `;` kullanın.

Telegram gitti, e-posta gitmedi (veya tersi) durumları zamanlanmış tablodaki `last_status` ile görünür (`success_no_telegram` gibi).
