FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir redis requests

COPY backends.py scaler.py ./

CMD ["python", "-u", "scaler.py"]
