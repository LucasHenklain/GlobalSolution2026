# Imagem única do VigIA: o mesmo código serve ao app, ao dashboard, ao pipeline, à IA e ao emulador.
# Cada serviço do docker-compose.yml só muda o comando.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependências primeiro: esta camada só é refeita quando o requirements.txt muda.
COPY requirements.txt .
# Rede com inspeção TLS (proxy corporativo): passe o certificado da empresa como segredo de build
#   docker compose build --secret id=ca_extra,src=caminho/da/cadeia.pem   (opcional; sem o segredo, nada muda)
RUN --mount=type=secret,id=ca_extra,required=false \
    if [ -s /run/secrets/ca_extra ]; then \
        cat /etc/ssl/certs/ca-certificates.crt /run/secrets/ca_extra > /tmp/ca.pem && export PIP_CERT=/tmp/ca.pem; \
    fi && \
    pip install -r requirements.txt && rm -f /tmp/ca.pem

COPY comum ./comum
COPY dados ./dados
COPY ia ./ia
COPY mvp ./mvp
COPY devops ./devops
COPY pyproject.toml ./

# Usuário sem privilégios: se o app for comprometido, o invasor não vira root no container.
RUN useradd --create-home --uid 10001 vigia \
    && mkdir -p /dados_vigia/lake /dados_vigia/var /dados_vigia/modelos \
    && chown -R vigia:vigia /dados_vigia /app
USER vigia

ENV VIGIA_LAKE=/dados_vigia/lake \
    VIGIA_DB=/dados_vigia/var/vigia.db \
    VIGIA_MODELOS=/dados_vigia/modelos

EXPOSE 8000 8501
CMD ["python", "-m", "uvicorn", "mvp.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
