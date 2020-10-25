FROM python:3.7-slim

WORKDIR /code

COPY requirements.txt .
RUN apt update && \
    apt -y install build-essential libpq-dev && \
    pip install --no-cache-dir -r requirements.txt && \
    apt -y remove build-essential && \
    apt -y autoremove && \
    apt clean

COPY . .

HEALTHCHECK CMD python /code/health.py
CMD [ "python", "main.py" ]
