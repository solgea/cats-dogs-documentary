FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/cddocs ./src/cddocs
COPY dashboard.py .

# Secret'ler ortam değişkeninden gelir, repoda saklanmaz
ENV YOUTUBE_CLIENT_ID=""
ENV YOUTUBE_CLIENT_SECRET=""
ENV YT_TOKEN_PATH="/app/youtube_token.json"

EXPOSE 8501

CMD ["streamlit", "run", "dashboard.py", "--server.headless", "true", "--server.port", "8501"]
