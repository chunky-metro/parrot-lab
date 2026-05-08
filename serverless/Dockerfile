FROM python:3.11-slim

WORKDIR /app

# v1 deps are pure-python wheels; no build essentials needed.
# M3 will add: build-essential libsndfile1 ffmpeg (for librosa + audio decode).

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
