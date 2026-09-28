# TradeLABtr Stock Screener

Amerikan borsaları (S&P 500, NASDAQ, NYSE), **Borsa İstanbul (BIST)** ve **Binance Spot (USDT)** için Python tabanlı web tarama uygulaması.

## Özellikler

- **Teknik filtreler:** EMA kesişimi, fiyat/EMA, RSI, ADX, CCI, momentum, ALMA, ATR genişlemesi
- **Pine Script:** `.txt` dosyası yükleme, SQLite’da kalıcı kayıt, **AL** (alış) koşulunun otomatik çıkarımı
- **Tarama:** ABD → yfinance; BIST → yfinance (`.IS`); **Binance** → Binance klines (USDT çiftleri, örn. `BTC`)
- **VIOP / Hisse hesaplayıcı:** üst menüde ayrı sekmeler; lot ve K/Z hesabı, BIST/Nasdaq/NYSE hacim-volatilite-hype sıralaması
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

```powershell
cd C:\Users\Dell\Projects\stock-screener
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

### Sunucuyu başlatma (Windows PowerShell)

`activate` tek başına çalışmaz. Aşağıdakilerden birini kullanın:

```powershell
# Önerilen — venv activate gerekmez
.\start.ps1

# veya proje kökünden
.\.venv\Scripts\python.exe run.py

# venv activate etmek isterseniz (Scripts klasörünün içinde değil, proje kökünden)
.\.venv\Scripts\Activate.ps1
python run.py
```

Zamanlanmış taramalar **yalnızca sunucu çalışırken** tetiklenir; pencereyi kapatırsanız planlar durur.

Tarayıcı: http://127.0.0.1:8000

## VPS (Windows) baslatma

1. `git pull`
2. `.env` yoksa `copy .env.example .env` — icinde `HOST=0.0.0.0` olmali
3. Cift tik: `start-tradelab.bat` (pencere acik kalsin; kapanirsa hata metni gorunur)
4. Log: `storage\server.log`
5. Firewall’da `PORT` (varsayilan 8000) acik olmali

`start-tradelab.bat` venv yoksa veya python dusurse pencereyi kapatmaz. Port 8000 doluysa once eski `python run.py` / TradeLABtr penceresini kapatin.

## VIOP ve Hisse hesaplayıcı

Giriş yaptıktan sonra üst menüde **VIOP** ve **Hisse** sekmeleri açılır.

- **VIOP:** teminat tutarına göre vadeli kontrat lotu ve yüzde hareketin kar/zararı
- **Hisse:** nakit alım tutarına göre lot (1 lot = 1 pay) ve K/Z; altta BIST / Nasdaq / NYSE sıralaması

Arayüz `calc/out` altında statik olarak durur. Nasdaq / NYSE isim listesi ve hacim-volatilite sıralaması FastAPI içinde **yfinance** ile gelir (Node gerekmez). Node.js varsa `calc/api-server.mjs` hype (haber/Reddit) için ek kaynak olur.

Arayüzü yeniden derlemek:

```bash
cd calc
npm install
CALC_BASE_PATH=/calc npm run build
```

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
    calc_sidecar.py    # VIOP/Hisse sıralama API (Node)
calc/                  # VIOP + Hisse hesaplayıcı (statik UI + Node API)
static/ + templates/   # Web arayüzü
storage/               # DB ve Pine dosyaları
```
