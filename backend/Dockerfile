
FROM python:3.12-slim

# Create a dedicated non-root user.
ARG APP_UID=1000
ARG APP_GID=1000

RUN groupadd --gid ${APP_GID} appuser && \
    useradd --uid ${APP_UID} \
            --gid ${APP_GID} \
            --create-home \
            --shell /usr/sbin/nologin \
            appuser

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .

# Install dependencies as root during image build.
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files with correct ownership.
COPY --chown=appuser:appuser app ./app

# Prepare AWS configuration directory.
RUN mkdir -p /home/appuser/.aws && \
    chown -R appuser:appuser /home/appuser/.aws

# Switch to non-root user.
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

