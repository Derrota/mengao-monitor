# Mengão Monitor 🦞 - Docker
FROM python:3.11-slim

WORKDIR /app

# Instala dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia código
COPY . .

# Cria diretório para dados persistentes
RUN mkdir -p /data

# Volume para config e banco
VOLUME ["/data"]

# Health check do container
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health', timeout=2)" || exit 1

# Porta do health check
EXPOSE 8080

# Entry point
ENTRYPOINT ["python", "monitor.py"]
CMD ["-c", "/data/config.json", "--health", "--health-port", "8080"]
