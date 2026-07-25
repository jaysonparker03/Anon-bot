FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir aiogram==3.4.1 aiosqlite==0.20.0 pydantic-core==2.16.3
COPY . /app/
CMD ["python", "main.py"]
