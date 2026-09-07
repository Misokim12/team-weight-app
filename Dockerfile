FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["sh", "-c", "flask --app app init-db && gunicorn -w 2 -b 0.0.0.0:8000 app:app"]
