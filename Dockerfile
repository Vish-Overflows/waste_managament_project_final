FROM python:3.11-slim

WORKDIR /app

COPY . /app

ENV PORT=10000

EXPOSE 10000

CMD ["python", "server.py", "--host", "0.0.0.0"]
