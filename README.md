# TradeLABtr Stock Screener

Amerikan borsaları (S&P 500, NASDAQ, NYSE), **Borsa İstanbul (BIST)** ve **Binance Spot (USDT)** için Python tabanlı web tarama uygulaması.

## Özellikler

- **Teknik filtreler:** EMA kesişimi, fiyat/EMA, RSI, ADX, CCI, momentum, ALMA, ATR genişlemesi
- **Pine Script:** `.txt` dosyası yükleme, SQLite’da kalıcı kayıt, **AL** (alış) koşulunun otomatik çıkarımı
- **Tarama:** ABD → yfinance; BIST → yfinance (`.IS`); **Binance** → Binance klines (USDT çiftleri, örn. `BTC`)
- **BIST sembol listesi:** BigPara public API (API anahtarı gerekmez)
- **TradingView:** Sonuçları `.txt` izleme listesi olarak indir

## BIST

- **Liste:** BigPara `hisse/list`
- **OHLCV / piyasa değeri:** Yahoo Finance (`.IS`); intraday veriler gecikmeli olabilir
- İsteğe bağlı `TWELVE_DATA_API_KEY` (.env) ileride alternatif sağlayıcı için saklanır; varsayılan tarama yfinance kullanır

### VERDA API

[Borsa İstanbul VERDA](https://www.borsaistanbul.com) kurumsal müşterilere **dosya indirme** API’si sunar (yetki + kullanıcı hesabı gerekir). Canlı OHLCV taraması bu projede yfinance ile yapılır; VERDA ileride dosya tabanlı sembol listesi için eklenebilir.

## Giriş ve kullanıcılar

İlk kurulumda boş veritabanına `.env` içindeki admin oluşturulur:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=Admin!12345
SESSION_SECRET=uzun-rastgele-bir-metin
```

- Giriş: http://127.0.0.1:8000/login
- Admin, **Kullanıcılar** sekmesinden yeni kullanıcı ve geçici şifre tanımlar.
- Kullanıcı ilk girişte kendi şifresini belirler (min 8 karakter, büyük/küçük harf, rakam, özel karakter).

## Kurulum

```bash
cd C:\Users\Dell\Projects\stock-screener
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python run.py
```

Tarayıcı: http://127.0.0.1:8000

## Pine Script sınırları

TradingView Pine Script’in tamamı çalıştırılmaz. Desteklenen yapılar:

- `plotshape(..., title="AL")` veya `text="AL"`
- `alertcondition(..., message="...AL...")`
- `al = ...` / `buySignal = ...` gibi değişkenler
- `ta.ema`, `ta.rsi`, `ta.cci`, `ta.adx`, `ta.atr`, `ta.mom`, `ta.alma`, `ta.crossover` benzeri ifadeler

Karmaşık Pine kodları için **Manuel koşul** alanını kullanın veya indikatörü sadeleştirin.

## Örnek Pine

`examples/sample_pine_al.txt` dosyasını yükleyerek test edebilirsiniz.

## API

| Endpoint | Açıklama |
|----------|----------|
| `POST /api/pine/upload` | Pine dosyası yükle ve kaydet |
| `GET /api/pine/scripts` | Kayıtlı script listesi |
| `POST /api/scan` | Tarama çalıştır |

## Proje yapısı

```
app/
  main.py              # FastAPI
  services/
    indicators.py      # EMA, ALMA, RSI, ADX, ATR, CCI, Mom
    pine_parser.py     # AL koşul çıkarımı
    pine_evaluator.py  # Koşul değerlendirme
    screener.py        # Tarama motoru
static/ + templates/   # Web arayüzü
storage/               # DB ve Pine dosyaları
```
