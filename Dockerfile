FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    BANDILKI_DATABASE=/data/bandilki.sqlite3

WORKDIR /app
COPY server.py schema.sql ./
COPY user/ ./user/
COPY admin/ ./admin/
COPY images/ ./images/

RUN mkdir -p /data
VOLUME ["/data"]
EXPOSE 8000

CMD ["python", "server.py"]
