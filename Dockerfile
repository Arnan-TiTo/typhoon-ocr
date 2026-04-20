# ============================================================
# Typhoon OCR - Docker Image
# Gradio demo app for Thai/English OCR using OpenTyphoon API
# ============================================================

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        poppler-utils \
        gcc \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Install the typhoon_ocr package from local source
RUN pip install --no-cache-dir ./packages/typhoon_ocr

# Expose Gradio default port
EXPOSE 7860

# Set environment variables for Gradio
ENV GRADIO_SERVER_NAME="0.0.0.0"
ENV GRADIO_SERVER_PORT="7860"

# Run the Gradio app
CMD ["python", "app.py"]
