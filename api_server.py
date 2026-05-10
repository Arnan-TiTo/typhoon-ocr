"""
Typhoon OCR Local API Server
=============================
FastAPI REST API server ที่ใช้ LM Studio (หรือ OpenAI-compatible API อื่นๆ) 
เพื่อ OCR ไฟล์ PDF/รูปภาพ ผ่าน Typhoon OCR model

Usage:
    python api_server.py

Swagger UI:
    http://localhost:8000/docs
"""

import base64
import json
import os
import socket
import sys
import tempfile
import traceback
import urllib.error
import urllib.request
from io import BytesIO
from typing import Optional
import fitz  # PyMuPDF - pure Python PDF rendering (no poppler needed)

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from openai import OpenAI
from dotenv import load_dotenv
from PIL import Image
from pypdf import PdfReader

from typhoon_ocr import prepare_ocr_messages
from thai_ocr_corrector import ThaiOCRCorrector, get_corrector

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
LMSTUDIO_BASE_URL = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
LMSTUDIO_API_KEY = os.getenv("LMSTUDIO_API_KEY", "lm-studio")
LMSTUDIO_MODEL = os.getenv("LMSTUDIO_MODEL", "qwen/qwen2.5-vl-7b")

# Allow fallback to remote Typhoon API if needed
BASE_URL = os.getenv("TYPHOON_BASE_URL", LMSTUDIO_BASE_URL)
API_KEY = os.getenv("TYPHOON_API_KEY", LMSTUDIO_API_KEY)
MODEL = os.getenv("TYPHOON_OCR_MODEL", LMSTUDIO_MODEL)

# Use LM Studio by default (override with USE_REMOTE=true for remote API)
USE_REMOTE = os.getenv("USE_REMOTE", "false").lower() == "true"

if USE_REMOTE:
    active_base_url = BASE_URL
    active_api_key = API_KEY
    active_model = MODEL
else:
    active_base_url = LMSTUDIO_BASE_URL
    active_api_key = LMSTUDIO_API_KEY
    active_model = LMSTUDIO_MODEL

# Correction model (separate from OCR model, for text correction)
CORRECTION_MODEL = os.getenv("CORRECTION_MODEL", active_model)

# ---------------------------------------------------------------------------
# OpenAI client (LM Studio compatible)
# ---------------------------------------------------------------------------
client = OpenAI(base_url=active_base_url, api_key=active_api_key)

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Typhoon OCR API (LM Studio)",
    description=(
        "REST API สำหรับ OCR ไฟล์ PDF/รูปภาพ โดยใช้ Typhoon OCR model ผ่าน LM Studio\n\n"
        "- รับไฟล์ PDF หรือ Image (png, jpg, jpeg)\n"
        "- ใช้ model typhoon-ocr-7b บน LM Studio (localhost:1234)\n"
        "- คืนข้อความ Markdown ที่ OCR ได้"
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Allowed file extensions
# ---------------------------------------------------------------------------
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


def _is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Return True when a TCP port is already accepting connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((host, port)) == 0


def _describe_existing_service(port: int) -> str:
    """Best-effort description of the service already bound to the port."""
    url = f"http://127.0.0.1:{port}/openapi.json"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            payload = json.load(response)
        title = payload.get("info", {}).get("title")
        if title == app.title:
            return f"{title} is already running at http://localhost:{port}/docs"
        if title:
            return f"Another HTTP API is already running on port {port}: {title}"
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        pass
    return f"Another process is already using port {port}"


def _get_extension(filename: str) -> str:
    return os.path.splitext(filename.lower())[1]


def _get_pdf_page_count(path: str) -> int:
    """Get the total number of pages in a PDF file."""
    reader = PdfReader(path)
    return len(reader.pages)


def _pdf_page_to_temp_image(pdf_path: str, page_num: int, dpi: int = 150, max_dim: int = 1200) -> str:
    """Convert a single PDF page to a temporary PNG image using PyMuPDF."""
    doc = fitz.open(pdf_path)
    page = doc.load_page(page_num - 1)  # 0-indexed
    # Render page at specified DPI
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    # Create temp file path, close it first so PyMuPDF can write to it (Windows)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    tmp_path = tmp.name
    tmp.close()  # Must close before PyMuPDF writes on Windows
    pix.save(tmp_path)
    doc.close()
    # Resize image to max_dim to prevent LM Studio from rejecting large images
    img = Image.open(tmp_path)
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        new_size = (int(w * scale), int(h * scale))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
        img.save(tmp_path)
    else:
        img.close()
    return tmp_path


def _save_upload_to_temp(upload: UploadFile) -> str:
    """Save an uploaded file to a temporary location and return the path."""
    ext = _get_extension(upload.filename or ".pdf")
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        content = upload.file.read()
        tmp.write(content)
        return tmp.name


def _parse_ocr_output(text_output: str) -> str:
    """Parse OCR output — extract natural_text and clean up repetition."""
    import re

    if not text_output:
        return text_output

    # Try to extract natural_text from JSON (even if truncated)
    try:
        json_data = json.loads(text_output)
        if isinstance(json_data, dict) and "natural_text" in json_data:
            text_output = json_data["natural_text"]
    except (json.JSONDecodeError, TypeError, ValueError):
        # Try regex fallback for truncated JSON
        m = re.search(r'"natural_text"\s*:\s*"(.*)', text_output, re.DOTALL)
        if m:
            raw = m.group(1)
            # Remove trailing incomplete JSON
            raw = re.sub(r'"\s*\}?\s*$', '', raw)
            # Unescape JSON string
            try:
                text_output = json.loads('"' + raw + '"')
            except (json.JSONDecodeError, ValueError):
                text_output = raw.replace('\\n', '\n').replace('\\"', '"')

    # Remove repeated lines (barcode/tracking number repetition)
    lines = text_output.split('\n')
    cleaned = []
    repeat_count = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            cleaned.append(line)
            repeat_count = 0
            continue
        # Check if same as previous non-empty line
        prev = cleaned[-1].strip() if cleaned else ""
        if stripped == prev:
            repeat_count += 1
            if repeat_count < 2:  # Allow max 2 consecutive same lines
                cleaned.append(line)
        else:
            repeat_count = 0
            cleaned.append(line)

    return '\n'.join(cleaned)


def _ocr_single_page(
    file_path: str,
    task_type: str = "v1.5",
    page_num: int = 1,
    figure_language: str = "Thai",
    image_dim: int = 1200,
    max_tokens: int = 4096,
    repetition_penalty: float = 1.5,
) -> str:
    """
    OCR a single page from a PDF or image file via LM Studio.
    Uses PyMuPDF to convert PDF pages to images (no poppler needed).
    """
    ext = _get_extension(file_path)
    temp_image_path = None

    try:
        # For PDFs: convert page to image first using PyMuPDF
        if ext == ".pdf":
            temp_image_path = _pdf_page_to_temp_image(file_path, page_num, max_dim=image_dim)
            ocr_path = temp_image_path
            ocr_page = 1  # Image is always page 1
        else:
            ocr_path = file_path
            ocr_page = 1

        # Prepare messages using typhoon_ocr package (with image path, no poppler)
        messages = prepare_ocr_messages(
            pdf_or_image_path=ocr_path,
            task_type=task_type,
            target_image_dim=image_dim,
            target_text_length=8000,
            page_num=ocr_page,
            figure_language=figure_language,
        )

        # Send to LM Studio (OpenAI-compatible API)
        response = client.chat.completions.create(
            model=active_model,
            messages=messages,
            max_tokens=max_tokens,
            extra_body={
                "repetition_penalty": repetition_penalty,
                "temperature": 0.1,
                "top_p": 0.6,
            },
        )

        text_output = response.choices[0].message.content
        return _parse_ocr_output(text_output)
    finally:
        # Clean up temp image
        if temp_image_path and os.path.exists(temp_image_path):
            try:
                os.unlink(temp_image_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health", tags=["System"])
async def health_check():
    """
    Health check — ตรวจสอบสถานะ server และการเชื่อมต่อ LM Studio
    """
    lm_studio_ok = False
    lm_studio_models = []
    try:
        models = client.models.list()
        lm_studio_models = [m.id for m in models.data]
        lm_studio_ok = True
    except Exception as e:
        lm_studio_models = [f"Error: {str(e)}"]

    return {
        "status": "ok",
        "backend": "lm-studio" if not USE_REMOTE else "remote",
        "base_url": active_base_url,
        "model": active_model,
        "lm_studio_connected": lm_studio_ok,
        "available_models": lm_studio_models,
    }


@app.post("/ocr", tags=["OCR"])
async def ocr_file(
    file: UploadFile = File(..., description="PDF or Image file"),
    task_type: str = Form("v1.5", description="OCR type: default, structure, v1.5"),
    page_num: int = Form(1, description="Page number (PDF only, starts at 1)"),
    figure_language: str = Form("Thai", description="Figure language: Thai / English"),
    image_dim: int = Form(1200, description="Max image dimension in px (smaller=faster, larger=more detail)"),
    max_tokens: int = Form(4096, description="Max output tokens (smaller=less repetition)"),
    repetition_penalty: float = Form(1.5, description="Repetition penalty (1.0=off, 1.5=moderate, 2.0=strong)"),
):
    """
    OCR single page — tunable parameters

    **Tips for local model:**
    - image_dim: 800-1200 (smaller = faster + less hallucination)
    - max_tokens: 2048-4096 (smaller = less repetition)
    - repetition_penalty: 1.3-2.0 (higher = less repetition but may lose detail)
    """
    ext = _get_extension(file.filename or "")
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported: {ext}")
    if task_type not in ("default", "structure", "v1.5"):
        raise HTTPException(status_code=400, detail="Invalid task_type")

    tmp_path = None
    try:
        tmp_path = _save_upload_to_temp(file)
        total_pages = 1
        if ext == ".pdf":
            total_pages = _get_pdf_page_count(tmp_path)
            if page_num < 1 or page_num > total_pages:
                raise HTTPException(status_code=400, detail=f"page_num must be 1-{total_pages}")

        text = _ocr_single_page(
            file_path=tmp_path,
            task_type=task_type,
            page_num=page_num,
            figure_language=figure_language,
            image_dim=image_dim,
            max_tokens=max_tokens,
            repetition_penalty=repetition_penalty,
        )

        return {
            "status": "success",
            "text": text,
            "page": page_num,
            "total_pages": total_pages,
            "task_type": task_type,
            "model": active_model,
            "params": {"image_dim": image_dim, "max_tokens": max_tokens, "repetition_penalty": repetition_penalty},
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"OCR error: {str(e)}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@app.post("/ocr/pages", tags=["OCR"])
async def ocr_all_pages(
    file: UploadFile = File(..., description="PDF/Image file"),
    task_type: str = Form("v1.5", description="OCR type: default, structure, v1.5"),
    figure_language: str = Form("Thai", description="Figure language: Thai / English"),
    image_dim: int = Form(1200, description="Max image dimension in px"),
    max_tokens: int = Form(4096, description="Max output tokens"),
    repetition_penalty: float = Form(1.5, description="Repetition penalty (1.0-2.0)"),
):
    """
    OCR all pages — tunable parameters

    **Tips for local model:**
    - image_dim: 800-1200 (smaller = faster + less hallucination)
    - max_tokens: 2048-4096 (smaller = less repetition)
    - repetition_penalty: 1.3-2.0 (higher = less repetition)
    """
    ext = _get_extension(file.filename or "")
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported: {ext}")
    if task_type not in ("default", "structure", "v1.5"):
        raise HTTPException(status_code=400, detail="Invalid task_type")

    tmp_path = None
    page_images = []

    try:
        tmp_path = _save_upload_to_temp(file)

        if ext == ".pdf":
            total_pages = _get_pdf_page_count(tmp_path)
        else:
            total_pages = 1

        print(f"[OCR/pages] Starting: {total_pages} pages, task={task_type}, dim={image_dim}, tokens={max_tokens}, rep={repetition_penalty}")

        # Step 1: Split PDF into page images
        if ext == ".pdf":
            for page_num in range(1, total_pages + 1):
                try:
                    img_path = _pdf_page_to_temp_image(tmp_path, page_num, max_dim=image_dim)
                    page_images.append((page_num, img_path))
                except Exception as e:
                    page_images.append((page_num, None))
                    print(f"[OCR/pages] Page {page_num}: Failed to render - {e}")
        else:
            page_images.append((1, tmp_path))

        # Step 2: OCR each page
        results = []
        for page_num, img_path in page_images:
            if img_path is None:
                results.append({"page": page_num, "status": "error", "text": "Failed to render"})
                continue

            print(f"[OCR/pages] Page {page_num}/{total_pages}: Sending...", flush=True)

            try:
                messages = prepare_ocr_messages(
                    pdf_or_image_path=img_path,
                    task_type=task_type,
                    target_image_dim=image_dim,
                    target_text_length=8000,
                    page_num=1,
                    figure_language=figure_language,
                )

                response = client.chat.completions.create(
                    model=active_model,
                    messages=messages,
                    max_tokens=max_tokens,
                    extra_body={
                        "repetition_penalty": repetition_penalty,
                        "temperature": 0.1,
                        "top_p": 0.6,
                    },
                )

                text_output = response.choices[0].message.content
                text_output = _parse_ocr_output(text_output)

                results.append({"page": page_num, "status": "success", "text": text_output})
                print(f"[OCR/pages] Page {page_num}/{total_pages}: OK")

            except Exception as e:
                results.append({
                    "page": page_num,
                    "status": "error",
                    "text": f"Error: {str(e)}",
                })
                print(f"[OCR/pages] Page {page_num}/{total_pages}: ERROR - {e}")

        success_count = sum(1 for r in results if r["status"] == "success")
        print(f"[OCR/pages] Done: {success_count}/{total_pages} pages OK")

        return {
            "status": "success",
            "total_pages": total_pages,
            "task_type": task_type,
            "model": active_model,
            "results": results,
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"OCR processing error: {str(e)}",
        )
    finally:
        # Clean up ALL temp files
        for _, img_path in page_images:
            if img_path and img_path != tmp_path and os.path.exists(img_path):
                try:
                    os.unlink(img_path)
                except OSError:
                    pass
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

# ---------------------------------------------------------------------------
# Thai OCR Correction
# ---------------------------------------------------------------------------

# System prompt for Thai OCR text correction
THAI_CORRECT_SYSTEM_PROMPT = """คุณคือระบบแก้ไขคำผิดภาษาไทยจาก OCR

กฎ:
1. รับข้อความที่ OCR อ่านผิด
2. ตอบกลับเฉพาะข้อความที่แก้ไขแล้วเท่านั้น
3. ห้ามอธิบาย ห้ามวิเคราะห์ ห้ามใส่หมายเหตุ
4. ห้ามเปลี่ยนพยัญชนะ แก้เฉพาะตำแหน่งสระ วรรณยุกต์ ช่องว่าง
5. ข้อความอังกฤษ ตัวเลข HTML ให้คงไว้ไม่ต้องแก้

วิธีแก้: แยกอักษรที่ OCR เห็นทีละตัว แล้วประกอบเป็นคำที่ถูกต้อง

ตัวอย่าง:
Input: หวงั
Output: หวัง

Input: ครมีกนัแดด
Output: ครีมกันแดด

Input: จงัหวดัชลบรีุ
Output: จังหวัดชลบุรี

Input: ตวัเลอืกสนิค้า
Output: ตัวเลือกสินค้า

Input: แพทยผิ์วหนงั
Output: แพทย์ผิวหนัง

Input: Hello World 12345
Output: Hello World 12345"""

# Common OCR mistakes dictionary (fast lookup)
THAI_OCR_CORRECTIONS = {
    "ตําบล": "ตำบล",
    "ตาํบล": "ตำบล",
    "อําเภอ": "อำเภอ",
    "อาํเภอ": "อำเภอ",
    "จงัหวดั": "จังหวัด",
    "จังหวดั": "จังหวัด",
    "กรงุเทพมหานคร": "กรุงเทพมหานคร",
    "กรงุเทพ": "กรุงเทพ",
    "กรงุเทพม หานคร": "กรุงเทพมหานคร",
    "ครมี": "ครีม",
    "สนิคา้": "สินค้า",
    "สนิค้า": "สินค้า",
    "ชอืสนิคา้": "ชื่อสินค้า",
    "ชื่อสนิคา้": "ชื่อสินค้า",
    "ชอืสนิคา้่": "ชื่อสินค้า",
    "ตวัเลอืกสนิค้า": "ตัวเลือกสินค้า",
    "ตวเลอืกสินค้า": "ตัวเลือกสินค้า",
    "ตวัเลอืก สนคิ้า": "ตัวเลือกสินค้า",
    "ตวเลอกสนคา": "ตัวเลือกสินค้า",
    "ชลบรีุ": "ชลบุรี",
    "มนีบรีุ": "มีนบุรี",
    "บรีุ": "บุรี",
    "จรเข้บวั": "จรเข้บัว",
    "จรเขบ้วั": "จรเข้บัว",
    "ลาดปลาเคา้": "ลาดปลาเค้า",
    "เมอืง": "เมือง",
    "หมู่บา้น": "หมู่บ้าน",
    "หมบู่้าน": "หมู่บ้าน",
    "บา้น": "บ้าน",
    "ถนนร่มเกลา้": "ถนนร่มเกล้า",
    "ปกปอ้ง": "ปกป้อง",
    "พรอมบำรงุ้": "พร้อมบำรุง",
    "ฟนฟู": "ฟื้นฟู",
    "มออาชพัืี": "มืออาชีพ",
    "ลดเลือนรืิ้้วรอย": "ลดเลือนริ้วรอย",
    "คมุมนั": "คุมมัน",
    "คุมมันั": "คุมมัน",
    "กันแดดคุมมันั": "กันแดดคุมมัน",
    "กนแดดคมุมนั": "กันแดดคุมมัน",
    "ครีมกนัแดด": "ครีมกันแดด",
    "ครมีกันแดด": "ครีมกันแดด",
    "ครมีกนแดด": "ครีมกันแดด",
    "กนแดด": "กันแดด",
    "ครีมกนั": "ครีมกัน",
    "สง่ฟรี": "ส่งฟรี",
    "ผิ์ว": "ผิว",
    "หนงั": "หนัง",
    "แพทยผิ์ว": "แพทย์ผิว",
    "แพทยผ์วิ": "แพทย์ผิว",
    "แพทยผิ์วหนงั": "แพทย์ผิวหนัง",
    "หวงั": "หวัง",
    "เชงิเนนิ": "เชิงเนิน",
    "สตูร": "สูตร",
    "เข ต": "เขต",
    "จงัหวดัชลบรีุ": "จังหวัดชลบุรี",
    "จงัหวดักรงุเทพมหานคร": "จังหวัดกรุงเทพมหานคร",
    "จงัหวดักรุงเทพมหานคร": "จังหวัดกรุงเทพมหานคร",
    "จงัหวัดระยอง": "จังหวัดระยอง",
    "ครมีกันแดดสตูรแพทย์ผิวหนงั": "ครีมกันแดดสูตรแพทย์ผิวหนัง",
    "ครีมกนัแดดสตูรแพทยผ์วิหนัง": "ครีมกันแดดสูตรแพทย์ผิวหนัง",
    "ศริผลกลุ": "ศิริผลกุล",
}


def _apply_dict_corrections(text: str) -> str:
    """Apply rule-based corrections (JSON mappings + character rules)."""
    corrector = get_corrector()
    return corrector.correct_text(text)


@app.post("/ocr/correct", tags=["Thai Correction"])
async def correct_ocr_text(
    text: str = Form(..., description="OCR text to correct"),
    use_ai: bool = Form(True, description="Use AI for advanced correction (slower but better)"),
    use_dict: bool = Form(True, description="Apply dictionary corrections first (fast)"),
):
    """
    Correct garbled Thai OCR text

    **Two correction methods:**
    - **Dictionary** (fast): exact match replacement of known OCR errors
    - **AI** (slower): sends text to LM Studio with Thai character decomposition prompt

    Send raw OCR text → get corrected Thai text back
    """
    corrected = text

    # Step 1: Dictionary corrections (fast)
    if use_dict:
        corrected = _apply_dict_corrections(corrected)

    # Step 2: AI correction (slower, better for unknown errors)
    if use_ai:
        try:
            response = client.chat.completions.create(
                model=CORRECTION_MODEL,
                messages=[
                    {"role": "system", "content": THAI_CORRECT_SYSTEM_PROMPT},
                    {"role": "user", "content": f"แก้ไขข้อความนี้:\n\n{corrected}"},
                ],
                max_tokens=len(corrected) * 3,  # Allow enough room
                extra_body={
                    "repetition_penalty": 1.3,
                    "temperature": 0.1,
                    "top_p": 0.6,
                },
            )
            ai_result = response.choices[0].message.content
            if ai_result and len(ai_result.strip()) > 0:
                corrected = ai_result.strip()
        except Exception as e:
            print(f"[correct] AI correction failed: {e}")
            # Fall back to dictionary-only result

    return {
        "status": "success",
        "original": text,
        "corrected": corrected,
        "methods": {
            "dictionary": use_dict,
            "ai": use_ai,
        },
    }


@app.post("/ocr/full", tags=["OCR"])
async def ocr_full_pipeline(
    file: UploadFile = File(..., description="PDF or Image file"),
    task_type: str = Form("v1.5", description="OCR type: default, structure, v1.5"),
    page_num: int = Form(1, description="Page number (PDF only)"),
    figure_language: str = Form("Thai", description="Figure language: Thai / English"),
    image_dim: int = Form(1200, description="Max image dimension"),
    max_tokens: int = Form(4096, description="Max OCR output tokens"),
    repetition_penalty: float = Form(1.5, description="OCR repetition penalty"),
    correct_ai: bool = Form(True, description="Use AI to correct OCR text"),
    correct_dict: bool = Form(True, description="Use dictionary to correct OCR text"),
):
    """
    Full pipeline: OCR + Thai text correction in one step

    1. OCR the file (same as /ocr)
    2. Correct Thai text errors (same as /ocr/correct)
    3. Return both raw and corrected text
    """
    ext = _get_extension(file.filename or "")
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported: {ext}")
    if task_type not in ("default", "structure", "v1.5"):
        raise HTTPException(status_code=400, detail="Invalid task_type")

    tmp_path = None
    try:
        tmp_path = _save_upload_to_temp(file)
        total_pages = 1
        if ext == ".pdf":
            total_pages = _get_pdf_page_count(tmp_path)
            if page_num < 1 or page_num > total_pages:
                raise HTTPException(status_code=400, detail=f"page_num must be 1-{total_pages}")

        # Step 1: OCR
        raw_text = _ocr_single_page(
            file_path=tmp_path,
            task_type=task_type,
            page_num=page_num,
            figure_language=figure_language,
            image_dim=image_dim,
            max_tokens=max_tokens,
            repetition_penalty=repetition_penalty,
        )

        # Step 2: Correct
        corrected = raw_text
        if correct_dict:
            corrected = _apply_dict_corrections(corrected)

        if correct_ai:
            try:
                response = client.chat.completions.create(
                    model=CORRECTION_MODEL,
                    messages=[
                        {"role": "system", "content": THAI_CORRECT_SYSTEM_PROMPT},
                        {"role": "user", "content": f"แก้ไขข้อความนี้:\n\n{corrected}"},
                    ],
                    max_tokens=len(corrected) * 3,
                    extra_body={
                        "repetition_penalty": 1.3,
                        "temperature": 0.1,
                        "top_p": 0.6,
                    },
                )
                ai_result = response.choices[0].message.content
                if ai_result and len(ai_result.strip()) > 0:
                    corrected = ai_result.strip()
            except Exception as e:
                print(f"[full] AI correction failed: {e}")

        return {
            "status": "success",
            "page": page_num,
            "total_pages": total_pages,
            "task_type": task_type,
            "model": active_model,
            "raw_text": raw_text,
            "corrected_text": corrected,
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Text-only Correction (no OCR, no GPU needed for dict mode)
# ---------------------------------------------------------------------------
from pydantic import BaseModel
from typing import List


class TextCorrectRequest(BaseModel):
    """Request body for batch text correction."""
    texts: List[str]
    use_ai: bool = False
    use_dict: bool = True


class TextCorrectSingleRequest(BaseModel):
    """Request body for single text correction."""
    text: str
    use_ai: bool = False
    use_dict: bool = True


@app.post("/text/correct", tags=["Thai Correction"])
async def correct_text_batch(req: TextCorrectRequest):
    """
    Correct Thai OCR text (batch) — ไม่ต้องใช้ GPU

    **ส่ง JSON:**
    ```json
    {
        "texts": ["ครมีกนัแดดสตูรแพทยผิ์วหนงั", "จงัหวดัชลบรีุ"],
        "use_dict": true,
        "use_ai": false
    }
    ```

    - **use_dict=true** (default): ใช้ dictionary 50+ คำ แก้ทันที ไม่ต้องใช้ model
    - **use_ai=true** (optional): ส่งให้ LM Studio แก้ด้วย AI เพิ่ม (ต้องโหลด model)
    """
    results = []
    for text in req.texts:
        corrected = text

        if req.use_dict:
            corrected = _apply_dict_corrections(corrected)

        if req.use_ai:
            try:
                response = client.chat.completions.create(
                    model=CORRECTION_MODEL,
                    messages=[
                        {"role": "system", "content": THAI_CORRECT_SYSTEM_PROMPT},
                        {"role": "user", "content": f"แก้ไขข้อความนี้:\n\n{corrected}"},
                    ],
                    max_tokens=max(len(corrected) * 3, 512),
                    extra_body={
                        "repetition_penalty": 1.3,
                        "temperature": 0.1,
                        "top_p": 0.6,
                    },
                )
                ai_result = response.choices[0].message.content
                if ai_result and len(ai_result.strip()) > 0:
                    corrected = ai_result.strip()
            except Exception as e:
                print(f"[text/correct] AI failed: {e}")

        results.append({
            "original": text,
            "corrected": corrected,
            "changed": text != corrected,
        })

    return {
        "status": "success",
        "total": len(results),
        "methods": {"dictionary": req.use_dict, "ai": req.use_ai},
        "results": results,
    }


@app.post("/text/correct/single", tags=["Thai Correction"])
async def correct_text_single(req: TextCorrectSingleRequest):
    """
    Correct Thai OCR text (single) — ไม่ต้องใช้ GPU

    **ส่ง JSON:**
    ```json
    {
        "text": "ครมีกนัแดดสตูรแพทยผิ์วหนงั",
        "use_dict": true,
        "use_ai": false
    }
    ```
    """
    corrected = req.text

    if req.use_dict:
        corrected = _apply_dict_corrections(corrected)

    if req.use_ai:
        try:
            response = client.chat.completions.create(
                model=CORRECTION_MODEL,
                messages=[
                    {"role": "system", "content": THAI_CORRECT_SYSTEM_PROMPT},
                    {"role": "user", "content": f"แก้ไขข้อความนี้:\n\n{corrected}"},
                ],
                max_tokens=max(len(corrected) * 3, 512),
                extra_body={
                    "repetition_penalty": 1.3,
                    "temperature": 0.1,
                    "top_p": 0.6,
                },
            )
            ai_result = response.choices[0].message.content
            if ai_result and len(ai_result.strip()) > 0:
                corrected = ai_result.strip()
        except Exception as e:
            print(f"[text/correct/single] AI failed: {e}")

    return {
        "status": "success",
        "original": req.text,
        "corrected": corrected,
        "changed": req.text != corrected,
        "methods": {"dictionary": req.use_dict, "ai": req.use_ai},
    }


# ---------------------------------------------------------------------------
# Address Formatting endpoint
# ---------------------------------------------------------------------------

class FormatAddressRequest(BaseModel):
    """Request body for address formatting."""
    text: str
    correct_ocr: bool = True


@app.post("/text/format-address", tags=["Thai Correction"])
async def format_address(req: FormatAddressRequest):
    """
    แก้คำผิด OCR + จัดรูปที่อยู่ไทย

    เช่น: "เลขที่หมู่ที่ตำบลไผ่ล้อม, อำเภอบางกระทุ่ม, จังหวัดพิษณุโลก 19/7 3"
    → "เลขที่ 19/7 หมู่ที่ 3 ตำบลไผ่ล้อม, อำเภอบางกระทุ่ม, จังหวัดพิษณุโลก"
    """
    from thai_ocr_corrector import format_thai_address

    corrected = req.text
    if req.correct_ocr:
        corrected = _apply_dict_corrections(corrected)

    formatted = format_thai_address(corrected)

    return {
        "status": "success",
        "original": req.text,
        "corrected": corrected,
        "formatted": formatted,
        "changed": req.text != formatted,
    }


# ---------------------------------------------------------------------------
# Learning / Self-improvement endpoints
# ---------------------------------------------------------------------------

class LearnRequest(BaseModel):
    """Request body for learning new corrections."""
    ocr_text: str
    correct_text: str


class DetectRulesRequest(BaseModel):
    """Request body for detecting rules."""
    ocr_text: str
    correct_text: str


@app.post("/text/learn", tags=["Thai Learning"])
async def learn_correction(req: LearnRequest):
    """
    สอนคำใหม่: ส่งคำผิดจาก OCR + คำที่ถูกต้อง

    ระบบจะ:
    1. วิเคราะห์ว่ากฎไหนควรใช้ (vowel swap, tone error, etc.)
    2. เพิ่มลง ocr_corrections.json อัตโนมัติ
    3. ใช้งานได้ทันทีโดยไม่ต้อง restart

    ```json
    {"ocr_text": "หนงั", "correct_text": "หนัง"}
    ```
    """
    corrector = get_corrector()

    # Check if already exists
    if req.ocr_text in corrector.mapping:
        return {
            "status": "exists",
            "message": "Mapping already exists",
            "existing_correct": corrector.mapping[req.ocr_text],
        }

    # Learn and save
    entry = corrector.learn(req.ocr_text, req.correct_text)

    return {
        "status": "learned",
        "entry": entry,
        "total_mappings": len(corrector.mapping),
    }


@app.post("/text/detect-rules", tags=["Thai Learning"])
async def detect_rules(req: DetectRulesRequest):
    """
    ดูว่ากฎไหนควรใช้ (ไม่บันทึก แค่แสดงผล)

    ```json
    {"ocr_text": "หนงั", "correct_text": "หนัง"}
    ```
    """
    corrector = get_corrector()
    error_type, rules = corrector.detect_rules(req.ocr_text, req.correct_text)

    return {
        "ocr_text": req.ocr_text,
        "correct_text": req.correct_text,
        "detected_type": error_type,
        "detected_rules": rules,
    }


@app.post("/text/reload", tags=["Thai Learning"])
async def reload_corrections():
    """
    Reload corrections จาก ocr_corrections.json
    ใช้เมื่อแก้ไขไฟล์ JSON ด้วยมือแล้วต้องการ refresh
    """
    corrector = get_corrector()
    count = corrector.reload()
    return {
        "status": "reloaded",
        "total_mappings": count,
    }


# ---------------------------------------------------------------------------
# Thai Address Parsing
# ---------------------------------------------------------------------------

THAI_ADDRESS_SYSTEM_PROMPT = """คุณคือระบบแยกที่อยู่ไทยจากข้อความ OCR ของใบปะหน้าพัสดุ

กฎ:
1. แก้คำผิดจาก OCR ก่อน (สระสลับ วรรณยุกต์ผิดที่)
2. แยกที่อยู่เป็น JSON ตามโครงสร้างที่อยู่ไทย
3. ตอบเฉพาะ JSON เท่านั้น ห้ามอธิบาย ห้ามใส่ข้อความอื่น

JSON format:
{
  "sender_name": "ชื่อผู้ส่ง",
  "sender_address": {
    "house_no": "บ้านเลขที่",
    "moo": "หมู่",
    "soi": "ซอย",
    "road": "ถนน",
    "tambon": "ตำบล/แขวง",
    "amphoe": "อำเภอ/เขต",
    "province": "จังหวัด",
    "postal_code": "รหัสไปรษณีย์"
  },
  "receiver_name": "ชื่อผู้รับ",
  "receiver_phone": "เบอร์โทร",
  "receiver_address": {
    "house_no": "บ้านเลขที่",
    "moo": "หมู่",
    "soi": "ซอย",
    "road": "ถนน",
    "tambon": "ตำบล/แขวง",
    "amphoe": "อำเภอ/เขต",
    "province": "จังหวัด",
    "postal_code": "รหัสไปรษณีย์"
  },
  "order_id": "หมายเลขออเดอร์",
  "tracking_no": "หมายเลขติดตามพัสดุ",
  "shipping_date": "วันที่ส่ง",
  "platform": "Shopee/TikTok/Lazada"
}

ถ้าไม่มีข้อมูลบางฟิลด์ ให้ใส่ "" (ว่าง)
แก้คำผิดจาก OCR ให้ถูกต้องก่อนใส่ลงฟิลด์

ตัวอย่าง:
Input: จาก V*ea** C**c 39/2 ซอยลาดปลาเคา้ 34 แขวงจรเขบ้วั เขตลาดพร้าว กรงุเทพมหานคร 10230 ถึง นาย สมชาย (+)6689***1234 262/89 ม.11 ต.หนองขาม ศรีราชา ชลบรีุ 20230
Output:
{
  "sender_name": "V*ea** C**c",
  "sender_address": {"house_no": "39/2", "moo": "", "soi": "ลาดปลาเค้า 34", "road": "", "tambon": "จรเข้บัว", "amphoe": "ลาดพร้าว", "province": "กรุงเทพมหานคร", "postal_code": "10230"},
  "receiver_name": "นาย สมชาย",
  "receiver_phone": "(+)6689***1234",
  "receiver_address": {"house_no": "262/89", "moo": "11", "soi": "", "road": "", "tambon": "หนองขาม", "amphoe": "ศรีราชา", "province": "ชลบุรี", "postal_code": "20230"},
  "order_id": "",
  "tracking_no": "",
  "shipping_date": "",
  "platform": ""
}"""


class AddressParseRequest(BaseModel):
    """Request body for address parsing."""
    text: str
    correct_dict: bool = True


@app.post("/text/parse-address", tags=["Thai Correction"])
async def parse_thai_address(req: AddressParseRequest):
    """
    Parse Thai shipping label text into structured address

    **ส่ง JSON:**
    ```json
    {
        "text": "จาก V*ea** 39/2 ซอยลาดปลาเคา้ ...",
        "correct_dict": true
    }
    ```

    Returns structured JSON with sender/receiver name, address fields, order ID, etc.
    Requires CORRECTION_MODEL (llama-3-typhoon) loaded in LM Studio.
    """
    corrected = req.text

    # Step 1: Dictionary correction first
    if req.correct_dict:
        corrected = _apply_dict_corrections(corrected)

    # Step 2: AI parse address
    try:
        response = client.chat.completions.create(
            model=CORRECTION_MODEL,
            messages=[
                {"role": "system", "content": THAI_ADDRESS_SYSTEM_PROMPT},
                {"role": "user", "content": corrected},
            ],
            max_tokens=2048,
            extra_body={
                "repetition_penalty": 1.2,
                "temperature": 0.1,
                "top_p": 0.6,
            },
        )
        ai_result = response.choices[0].message.content.strip()

        # Try to parse JSON from AI response
        parsed = None
        try:
            parsed = json.loads(ai_result)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            import re
            m = re.search(r'\{[\s\S]*\}', ai_result)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass

        if parsed:
            return {
                "status": "success",
                "corrected_text": corrected,
                "address": parsed,
            }
        else:
            return {
                "status": "partial",
                "corrected_text": corrected,
                "raw_ai_response": ai_result,
                "error": "Could not parse AI response as JSON",
            }

    except Exception as e:
        print(f"[parse-address] AI failed: {e}")
        return {
            "status": "error",
            "corrected_text": corrected,
            "error": str(e),
        }

# ---------------------------------------------------------------------------
# Run server
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("API_PORT", "8000"))
    if _is_port_in_use(port):
        print(f"[ERROR] Port {port} is already in use.")
        print(f"[HINT] {_describe_existing_service(port)}")
        print("[HINT] Stop the existing process, or run this API on another port.")
        if os.name == "nt":
            print(f"[HINT] PowerShell: $env:API_PORT=\"{port + 1}\"; python api_server.py")
        else:
            print(f"[HINT] Shell: API_PORT={port + 1} python api_server.py")
        sys.exit(1)

    print(f"[*] Starting Typhoon OCR API Server on port {port}")
    print(f"[>] Backend: {'Remote API' if USE_REMOTE else 'LM Studio'}")
    print(f"[>] Base URL: {active_base_url}")
    print(f"[>] Model: {active_model}")
    print(f"[>] Swagger UI: http://localhost:{port}/docs")
    uvicorn.run(app, host="0.0.0.0", port=port)
