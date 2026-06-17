# ---------- FRONTEND BUILD (Angular) ----------
FROM --platform=$BUILDPLATFORM docker.io/library/node:lts-slim AS node_builder

WORKDIR /angular

# 1. Copier uniquement manifests pour cache npm
COPY angular/package.json angular/package-lock.json ./

# 2. Installer dépendances (layer cacheable)
RUN npm config set update-notifier false && \
  npm config set fund false && \
  npm config set audit false && \
  npm ci

# 3. Copier le reste du code Angular
COPY angular/ ./

# 4. Build Angular
RUN npm run build self-host-planning-poker


# ---------- BACKEND BUILD (Python Flask) ----------
FROM docker.io/library/python:3.11.7-alpine3.18

RUN adduser -H -D -u 1001 -G root default

WORKDIR /app

# 1. Copier requirements séparément (cache pip)
COPY flask/requirements.txt ./requirements.txt


# 2. Installer dépendances Python (cache layer)
RUN pip install --upgrade pip && \
  pip install --no-cache-dir -r requirements.txt \
  -i https://pypi.org/simple

# 3. Copier backend Flask
COPY flask/ ./

# 4. Copier frontend build Angular
COPY --chown=1001:0 --from=node_builder /angular/dist/self-host-planning-poker ./static

# 5. Préparer dossier data
RUN mkdir /data && \
  chown -R 1001:0 /app /data && \
  chmod -R g+w /app /data

USER 1001

EXPOSE 8000

CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "app:app", "--bind", "0.0.0.0:8000"]
