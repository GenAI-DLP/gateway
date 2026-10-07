# gateway/relay/Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# main.py에 FastAPI app 객체가 있다고 가정 (uvicorn main:app)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]