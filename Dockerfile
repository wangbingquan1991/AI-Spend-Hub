FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 AI_SPEND_DB=/data/spend.sqlite3 AI_SPEND_PORT=8765
WORKDIR /app
RUN groupadd --gid 10001 ai && useradd --uid 10001 --gid ai --create-home ai && mkdir /data && chown ai:ai /data
COPY --chown=ai:ai app.py /app/app.py
COPY --chown=ai:ai web /app/web
COPY --chown=ai:ai tools /app/tools
USER ai
EXPOSE 8765
CMD ["python", "app.py"]
