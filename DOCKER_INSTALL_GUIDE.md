# คู่มือการติดตั้ง Typhoon OCR บน Docker
# Typhoon OCR Docker Installation Guide

---

## สารบัญ / Table of Contents
1. [ข้อกำหนดเบื้องต้น / Prerequisites](#1-ข้อกำหนดเบื้องต้น--prerequisites)
2. [การตั้งค่า / Configuration](#2-การตั้งค่า--configuration)
3. [การ Build และรัน / Build & Run](#3-การ-build-และรัน--build--run)
4. [การใช้งาน / Usage](#4-การใช้งาน--usage)
5. [คำสั่งที่ใช้บ่อย / Common Commands](#5-คำสั่งที่ใช้บ่อย--common-commands)
6. [การแก้ไขปัญหา / Troubleshooting](#6-การแก้ไขปัญหา--troubleshooting)

---

## 1. ข้อกำหนดเบื้องต้น / Prerequisites

### ซอฟต์แวร์ที่ต้องติดตั้ง / Required Software

| Software | Version | Download |
|----------|---------|----------|
| Docker Desktop | 4.x+ | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) |
| Git | 2.x+ | [git-scm.com](https://git-scm.com/) |

### API Key
- ลงทะเบียนที่ [opentyphoon.ai](https://opentyphoon.ai) เพื่อรับ API Key
- Register at [opentyphoon.ai](https://opentyphoon.ai) to get your API Key

---

## 2. การตั้งค่า / Configuration

### 2.1 Clone Repository (ถ้ายังไม่ได้ clone)

```bash
git clone https://github.com/scb-10x/typhoon-ocr.git typhoon/scr
cd typhoon/scr
```

### 2.2 ตั้งค่าไฟล์ .env / Configure .env

แก้ไขไฟล์ `.env` และใส่ API Key ของคุณ:

Edit the `.env` file and enter your API Key:

```env
# Typhoon OCR Configuration
TYPHOON_BASE_URL=https://api.opentyphoon.ai/v1
TYPHOON_API_KEY=your-actual-api-key-here    # <-- ใส่ API Key ตรงนี้
TYPHOON_OCR_MODEL=typhoon-ocr-preview
```

> ⚠️ **สำคัญ**: ต้องเปลี่ยน `your-actual-api-key-here` เป็น API Key จริงจาก opentyphoon.ai

---

## 3. การ Build และรัน / Build & Run

### 3.1 Build Docker Image

```bash
cd d:\@Project\miniApp2GitVAC\AnalystData\TYPHOONOCR\typhoon\scr
docker-compose build
```

ใช้เวลาประมาณ 2-5 นาที (ขึ้นอยู่กับความเร็ว internet)

### 3.2 รัน Container / Start Container

```bash
docker-compose up -d
```

### 3.3 ตรวจสอบสถานะ / Check Status

```bash
docker ps --filter name=typhoon-ocr
```

ควรเห็นผลลัพธ์:
```
CONTAINER ID   IMAGE                 COMMAND         STATUS                   PORTS
xxxxxxxxxxxx   scr-typhoon-ocr-app   "python app.py" Up X minutes (healthy)   0.0.0.0:7860->7860/tcp
```

---

## 4. การใช้งาน / Usage

### เข้าถึง Gradio Web UI

เปิด Browser ไปที่: **http://localhost:7860**

### วิธีใช้งาน / How to Use

1. **อัปโหลดไฟล์** — คลิก "Upload Image file or PDF file" แล้วเลือกไฟล์ PDF หรือรูปภาพ (.pdf, .png, .jpg, .jpeg)
2. **เลือก Task** — เลือกโหมดการประมวลผล:
   - `default` — ใช้กับเอกสารทั่วไป, อินโฟกราฟิก
   - `structure` — ใช้กับเอกสารที่มี layout ซับซ้อน (ตาราง, ฟอร์ม)
3. **ระบุหน้า** — สำหรับ PDF หลายหน้า ระบุเลขหน้าที่ต้องการ
4. **กด Run** — คลิกปุ่ม "🚀 Run" เพื่อเริ่มการ OCR
5. **ดูผลลัพธ์** — ผลลัพธ์จะแสดงเป็น Markdown ทางด้านขวา

### ภาษาที่รองรับ / Supported Languages
- 🇹🇭 ภาษาไทย (Thai)
- 🇺🇸 ภาษาอังกฤษ (English)

---

## 5. คำสั่งที่ใช้บ่อย / Common Commands

| คำสั่ง / Command | คำอธิบาย / Description |
|---|---|
| `docker-compose up -d` | เริ่มรัน container ใน background |
| `docker-compose down` | หยุดและลบ container |
| `docker-compose restart` | รีสตาร์ท container |
| `docker-compose logs -f` | ดู logs แบบ real-time |
| `docker-compose build --no-cache` | Build ใหม่ทั้งหมด (ไม่ใช้ cache) |
| `docker ps --filter name=typhoon-ocr` | ตรวจสอบสถานะ container |

---

## 6. การแก้ไขปัญหา / Troubleshooting

### ปัญหา: Container ไม่สามารถเริ่มได้

```bash
# ตรวจสอบ logs
docker-compose logs typhoon-ocr

# ตรวจสอบว่า port 7860 ไม่ถูกใช้งานอยู่
netstat -ano | findstr :7860
```

### ปัญหา: ไม่สามารถเชื่อมต่อ API ได้

1. ตรวจสอบว่าใส่ API Key ถูกต้องในไฟล์ `.env`
2. ตรวจสอบ internet connection ของ Docker container:
```bash
docker exec typhoon-ocr python -c "import urllib.request; print(urllib.request.urlopen('https://api.opentyphoon.ai').status)"
```

### ปัญหา: Error processing document

ปัญหานี้เกิดจาก `poppler-utils` ไม่ได้ติดตั้ง — แต่ใน Docker image ของเราติดตั้งไว้แล้ว ถ้ายังพบปัญหา:
```bash
docker exec typhoon-ocr dpkg -l | grep poppler
```

### ปัญหา: Gradio Warning เกี่ยวกับ theme

```
UserWarning: The parameters have been moved from the Blocks constructor to the launch() method
```
นี่เป็น Warning ที่ไม่กระทบการทำงาน (Gradio 6.0 เปลี่ยน API) — สามารถเพิกเฉยได้

---

## โครงสร้างไฟล์ / File Structure

```
typhoon/scr/
├── Dockerfile          # Docker build instructions
├── docker-compose.yml  # Docker Compose configuration
├── .env                # Environment variables (API keys)
├── .dockerignore       # Files to exclude from Docker build
├── app.py              # Gradio web application
├── requirements.txt    # Python dependencies
├── packages/
│   └── typhoon_ocr/    # Core OCR library
├── examples/           # Example documents
└── tests/              # Test files
```

---

## ข้อมูลเพิ่มเติม / Additional Resources

- **GitHub**: [github.com/scb-10x/typhoon-ocr](https://github.com/scb-10x/typhoon-ocr)
- **Model Weights**: [huggingface.co/scb10x/typhoon-ocr-7b](https://huggingface.co/scb10x/typhoon-ocr-7b)
- **API Documentation**: [opentyphoon.ai](https://opentyphoon.ai)
- **Blog**: [opentyphoon.ai/blog/en/typhoon-ocr-release](https://opentyphoon.ai/blog/en/typhoon-ocr-release)
- **License**: Apache 2.0
