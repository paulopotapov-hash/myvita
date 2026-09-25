FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements-runtime.txt .
RUN pip install --no-cache-dir --no-compile -r requirements-runtime.txt

COPY . .

# Never run the app as root.
RUN groupadd -r myvita && useradd -r -g myvita myvita \
    && chown -R myvita:myvita /app \
    && find /app -type d -exec chmod 0555 {} + \
    && find /app -type f -exec chmod 0444 {} +
USER myvita

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
