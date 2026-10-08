FROM node:24-alpine AS frontend
WORKDIR /ui
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN corepack enable && corepack prepare pnpm@11.25.0 --activate && pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm run build
FROM python:3.12-slim
WORKDIR /app
COPY requirements-lock.txt ./
RUN pip install --no-cache-dir -r requirements-lock.txt
COPY backend/ backend/
COPY fixtures/ fixtures/
COPY --from=frontend /ui/dist frontend/dist
RUN useradd --create-home worker && mkdir data && chown -R worker:worker /app
USER worker
EXPOSE 8770
CMD ["python","-m","uvicorn","backend.api:app","--host","0.0.0.0","--port","8770"]
