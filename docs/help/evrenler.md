# Evrenler ve veri

## ABD

S&P 500, NASDAQ, NYSE veya birleşik **ABD (tümü)**. Veri Yahoo Finance. Saat dilimi New York; kapanmamış son bar taramada düşülür.

## BIST

Borsa İstanbul hisseleri (Yahoo `.IS`). Liste BigPara’dan gelir. İntraday gecikmeli olabilir.

İsteğe bağlı **borsapy** (TradingView oturumu) veya Twelve Data. TradingView canlı için `.env` içine `sessionid` / `sessionid_sign` ve BIST piyasa verisi aboneliği gerekir. Ayrıntı Tarama kartındaki “TradingView canlı BIST” kutusundadır.

## VIOP

Vadeli kontratlar `F_AEFES1026` gibi. Tarama OHLCV’si TradingView sürekli serisinden gelir (`AEFES1!` / `TOASO1!`) — grafikteki Bias×TS ile aynı mumlar. Continuous yoksa dayanak (nakit) yedeklenir; o zaman sinyal TV’den sapabilir.

Telegram’da da `AEFES1!` görünür. Özel listede VIOP seçin, kontrat kodlarını yazın.

## Binance

Spot USDT. Sembol `BTC` yeter (`BTCUSDT` olur). Veri Binance klines.

## Özel liste

Karışık evren tek listede olmaz. Liste piyasasını tek seçin. Kayıtlar tarayıcı `localStorage`’ındadır.

## Zaman dilimi ve kapanış

Tarama, **kapanmış son bar** ister. 15m’de 10:14’te oluşan mum henüz kapanmadıysa sinyal sayılmaz; 10:15 sonrası kapanmış 10:00–10:15 barı kullanılır.

BIST/VIOP: Europe/Istanbul. ABD: America/New_York. Binance: UTC.
