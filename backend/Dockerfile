FROM python:3.13

COPY requirements.txt /
RUN pip install -r /requirements.txt

COPY src /app

WORKDIR /

ENV PYTHONUNBUFFERED=1
CMD ["python3", "-m", "app"]
