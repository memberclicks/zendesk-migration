FROM python:3.6-slim
LABEL maintainer="agunn-mc"

# Required env
#ENV ZENDESK_SOURCE_EMAIL
#ENV ZENDESK_SOURCE_PASSWORD
#ENV ZENDESK_SOURCE_INSTANCE
#ENV ZENDESK_TARGET_EMAIL
#ENV ZENDESK_TARGET_PASSWORD
#ENV ZENDESK_TARGET_INSTANCE

ENV PYTHONUNBUFFERED=0

WORKDIR /usr/src

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY migrate/ .

CMD ["python", "ticket_migration.py"]
