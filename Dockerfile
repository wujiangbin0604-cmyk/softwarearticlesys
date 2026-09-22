FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt .
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
RUN pip install --no-cache-dir --index-url $PIP_INDEX_URL -r requirements.txt

COPY . .
RUN mkdir -p /app/data

EXPOSE 8000
CMD ["python", "app.py", "--host", "0.0.0.0", "--port", "8000"]
