FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

ARG INSTALL_CHROMA=false

COPY requirements.txt requirements-optional-chroma.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && if [ "$INSTALL_CHROMA" = "true" ]; then \
         python -m pip install --no-cache-dir -r requirements-optional-chroma.txt; \
       fi \
    && addgroup --system studymate \
    && adduser --system --ingroup studymate --home /app studymate

COPY --chown=studymate:studymate app ./app
COPY --chown=studymate:studymate migrations ./migrations
COPY --chown=studymate:studymate alembic.ini ./

RUN mkdir -p /app/storage/uploads /app/storage/chroma \
    && chown -R studymate:studymate /app/storage

USER studymate

EXPOSE 8000

# The application lifespan validates production security settings first, then
# upgrades through Alembic before accepting requests.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
