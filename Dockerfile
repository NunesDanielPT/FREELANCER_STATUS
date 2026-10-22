FROM python:3.12-alpine
ENV PYTHONUNBUFFERED=1 DB_PATH=/data/claquete.db
WORKDIR /app
COPY *.py .
RUN adduser -D -u 1000 app && mkdir /data && chown app /data
USER app
EXPOSE 8000
CMD ["python", "app.py"]
