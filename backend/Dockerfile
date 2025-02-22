FROM python:3.13

COPY requirements.txt /
RUN pip install -r /requirements.txt

COPY src /app

WORKDIR /
CMD ["python3", "-m", "app"]
