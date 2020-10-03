FROM python:3.7

WORKDIR /code

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

HEALTHCHECK CMD python /code/health.py
CMD [ "python", "main.py" ]
