# Dağıtım Rehberi

## 1. Gizli Anahtarları Yapılandırın

`.env.example` dosyasını `.env` olarak kopyalayın ve değerleri doldurun:

```bash
cp .env.example .env
```

`YOUTUBE_CLIENT_ID` ve `YOUTUBE_CLIENT_SECRET` değerlerini Google Cloud Console'dan alın.  
`youtube_token.json` dosyası OAuth akışından sonra oluşturulur ve repoda **tutulmaz**.

## 2. Docker ile Çalıştırın

```bash
docker build -t youtube-dashboard .
docker run -p 8501:8501 --env-file .env youtube-dashboard
```

## 3. Erişim

Tarayıcıda: http://localhost:8501

## Güvenlik Notu

- `youtube_token.json` ve `credentials.json` dosyaları `.gitignore` ile dışlanmıştır.
- Token dosyası çalıştırma sırasında `YT_TOKEN_PATH` ortam değişkeni ile gösterilen yolda olmalıdır.
- OAuth client secret'i repoda **asla** tutulmamalıdır.
