FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends nfdump tshark iputils-ping traceroute \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY collector/ collector/
COPY mcp_server/ mcp_server/

# Mode simulé par défaut ; en réel, injecter les secrets via l'environnement.
ENV COLLECTOR_MODE=simulated
# Conteneur sans terminal : Streamable HTTP par défaut (stdio reste
# disponible avec -e MCP_TRANSPORT=stdio et un terminal attache).
ENV MCP_TRANSPORT=http
ENV MCP_HTTP_HOST=0.0.0.0
ENV MCP_HTTP_PORT=8000
EXPOSE 8000

RUN useradd -m noc \
    && chown -R noc:noc /app
USER noc

# Serveur MCP du socle (bloc 3) : outils de collecte + resources.
# Tests : docker compose run --rm tests
CMD ["python", "-m", "mcp_server.server"]
