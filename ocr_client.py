"""
OCR Client - ส่ง PDF ทีละหน้าไปยัง API server

Usage:
    py ocr_client.py <pdf_file> [--task default|structure|v1.5] [--pages 1,3,5] [--output result.json]

Examples:
    py ocr_client.py document.pdf
    py ocr_client.py document.pdf --task structure
    py ocr_client.py document.pdf --pages 1,2,3
    py ocr_client.py document.pdf --output result.json
"""

import argparse
import json
import os
import sys
import time
import requests
from pypdf import PdfReader

API_URL = os.getenv("OCR_API_URL", "http://localhost:8000")


def get_pdf_page_count(pdf_path: str) -> int:
    reader = PdfReader(pdf_path)
    return len(reader.pages)


def ocr_single_page(pdf_path: str, page_num: int, task_type: str = "v1.5", figure_language: str = "Thai") -> dict:
    """Send a single page to the OCR API."""
    url = f"{API_URL}/ocr"
    with open(pdf_path, "rb") as f:
        files = {"file": (os.path.basename(pdf_path), f, "application/pdf")}
        data = {
            "task_type": task_type,
            "page_num": page_num,
            "figure_language": figure_language,
        }
        response = requests.post(url, files=files, data=data, timeout=600)
    return response.json()


def main():
    parser = argparse.ArgumentParser(description="OCR Client - PDF to text via Typhoon OCR API")
    parser.add_argument("pdf_file", help="Path to PDF file")
    parser.add_argument("--task", default="v1.5", choices=["default", "structure", "v1.5"],
                        help="OCR task type (default: v1.5)")
    parser.add_argument("--pages", default=None,
                        help="Comma-separated page numbers (e.g., 1,3,5). Default: all pages")
    parser.add_argument("--output", default=None,
                        help="Output JSON file path. Default: <pdf_name>_ocr.json")
    parser.add_argument("--lang", default="Thai", choices=["Thai", "English"],
                        help="Figure description language (default: Thai)")
    args = parser.parse_args()

    pdf_path = args.pdf_file
    if not os.path.exists(pdf_path):
        print(f"[ERROR] File not found: {pdf_path}")
        sys.exit(1)

    # Get total pages
    total_pages = get_pdf_page_count(pdf_path)
    print(f"[INFO] PDF: {pdf_path}")
    print(f"[INFO] Total pages: {total_pages}")
    print(f"[INFO] Task type: {args.task}")
    print(f"[INFO] API: {API_URL}")
    print()

    # Determine which pages to process
    if args.pages:
        page_list = [int(p.strip()) for p in args.pages.split(",")]
    else:
        page_list = list(range(1, total_pages + 1))

    # Process each page one at a time
    results = []
    for i, page_num in enumerate(page_list):
        print(f"[{i+1}/{len(page_list)}] Processing page {page_num}...", end=" ", flush=True)
        start_time = time.time()

        try:
            result = ocr_single_page(pdf_path, page_num, args.task, args.lang)
            elapsed = time.time() - start_time

            if result.get("status") == "success":
                text_preview = result["text"][:80].replace("\n", " ")
                print(f"OK ({elapsed:.1f}s) - {text_preview}...")
                results.append({
                    "page": page_num,
                    "status": "success",
                    "text": result["text"],
                    "time_seconds": round(elapsed, 1),
                })
            else:
                print(f"ERROR ({elapsed:.1f}s) - {result.get('detail', 'Unknown error')}")
                results.append({
                    "page": page_num,
                    "status": "error",
                    "text": result.get("detail", str(result)),
                    "time_seconds": round(elapsed, 1),
                })
        except requests.exceptions.Timeout:
            print("TIMEOUT (>600s)")
            results.append({
                "page": page_num,
                "status": "timeout",
                "text": "Request timed out after 600 seconds",
            })
        except Exception as e:
            print(f"ERROR - {str(e)}")
            results.append({
                "page": page_num,
                "status": "error",
                "text": str(e),
            })

    # Summary
    print()
    success_count = sum(1 for r in results if r["status"] == "success")
    print(f"[DONE] {success_count}/{len(page_list)} pages processed successfully")

    # Save results
    output_path = args.output or os.path.splitext(pdf_path)[0] + "_ocr.json"
    output_data = {
        "source_file": os.path.basename(pdf_path),
        "total_pages": total_pages,
        "task_type": args.task,
        "results": results,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"[SAVED] {output_path}")


if __name__ == "__main__":
    main()
