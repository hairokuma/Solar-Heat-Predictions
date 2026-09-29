FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x entrypoint.sh

ENV DATABASE_PATH=/data/app.db
ENV FLASK_APP=wsgi:app
VOLUME ["/data"]

EXPOSE 5000

ENTRYPOINT ["./entrypoint.sh"]
