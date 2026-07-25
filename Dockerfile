FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir --upgrade pip
COPY requirements.txt /app/
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt
COPY . /app/
CMD ["python", "main.py"]
