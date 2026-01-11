FROM python:3.11-slim

RUN apt-get update && apt-get install -y iputils-ping && rm -rf /var/lib/apt/lists/*

WORKDIR /agent
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

# Fichier de config persisté dans un volume Docker
ENV AGENT_CONFIG=/agent/config/config.json

EXPOSE 8080

# Lance l'UI locale (qui démarre aussi la boucle de collecte en tâche de fond)
CMD ["uvicorn", "src.webapp:app", "--host", "0.0.0.0", "--port", "8080"]