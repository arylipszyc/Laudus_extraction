FROM python:3.13-slim

RUN pip install --no-cache-dir beancount fava

WORKDIR /data
EXPOSE 5000

CMD ["fava", "--host", "0.0.0.0", "--port", "5000", "/data/eag.beancount"]
