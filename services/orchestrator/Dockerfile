FROM python:3.12-slim
WORKDIR /app
COPY packages/shared-types/python /deps/shared-types-python
COPY services/orchestrator/pyproject.toml .
RUN pip install --no-cache-dir .
COPY services/orchestrator/src ./src
USER nobody
EXPOSE 50051
CMD ["python", "-m", "src.server"]
