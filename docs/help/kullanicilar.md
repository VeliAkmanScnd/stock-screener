# Kullanıcılar ve giriş

İlk kurulumda `.env` içindeki admin oluşur. Giriş: `/login`.

## Admin

**Kullanıcılar** sekmesi yalnızca adminde görünür.

- Yeni kullanıcı + geçici şifre
- Şifre sıfırla
- Kullanıcı sil (kendiniz hariç)

Kullanıcı ilk girişte kendi şifresini belirler: en az 8 karakter, büyük/küçük harf, rakam, özel karakter.

## Ne kime özel?

Performans pozisyonları, R raporu ve (kullanıcıya ait) zamanlanmış taramalar hesaba bağlıdır. Admin, sistemdeki tüm zamanlanmış taramaları görebilir.

## VPS ve PC

Aynı GitHub kodunu çekin; **veritabanı ayrıdır**. PC’de gördüğünüz performans satırları VPS’te yoksa bu normaldir. Telegram’ın iki yerden çift gitmemesi için zamanlanmış taramayı tek makinede açık tutun.

`.env` asla git’e eklenmez. Token ve SMTP’yi her makinede kendiniz yazın.
