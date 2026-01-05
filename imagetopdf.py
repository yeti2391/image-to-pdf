#!/usr/bin/env python3
import argparse
import os
import sys
import tempfile
import logging
from pathlib import Path
from PIL import Image
import img2pdf
import subprocess

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}

def find_image_files(folder: Path):
    imgs = [p for p in sorted(folder.iterdir()) if p.suffix.lower() in IMAGE_EXT and p.is_file()]
    return imgs

def images_to_pdf(images, out_pdf_path: Path):
    if not images:
        raise ValueError("No images to convert")
    # Open images to ensure they're readable and convert multi-frame tiff if any
    img_bytes = []
    # Use img2pdf to keep original quality and sizing
    img_paths = [str(p) for p in images]
    with open(out_pdf_path, "wb") as f:
        f.write(img2pdf.convert(img_paths))
    logging.info("PDF creado: %s", out_pdf_path)

def run_ocr_on_pdf(input_pdf: Path, output_pdf: Path, lang: str = "eng", deskew: bool = True, clean: bool = True):
    """
    Usa ocrmypdf (CLI). Requiere ocrmypdf y tesseract instalados en el sistema.
    """
    cmd = [
        "ocrmypdf",
        "--skip-text",          # evita reprocesar PDFs que ya tienen texto
        "--output-type", "pdfa",# opcional: producir PDF/A (puedes quitarlo si no quieres)
    ]
    if lang:
        cmd += ["-l", lang]
    if deskew:
        cmd += ["--deskew"]
    if not clean:
        cmd += ["--clean", "none"]
    cmd += [str(input_pdf), str(output_pdf)]
    logging.info("Ejecutando OCR: %s", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logging.info("OCR aplicado: %s", output_pdf)
    except subprocess.CalledProcessError as e:
        logging.error("ocrmypdf falló: %s", e.stderr.decode(errors="ignore"))
        raise

def process_folder(folder: Path, lang: str, overwrite: bool):
    images = find_image_files(folder)
    if not images:
        logging.debug("No hay imágenes en %s", folder)
        return False
    out_pdf_name = f"{folder.name}.pdf"
    out_pdf_path = folder / out_pdf_name
    tmp_pdf = folder / (folder.name + "_noocr_tmp.pdf")
    ocr_pdf = out_pdf_path

    if out_pdf_path.exists() and not overwrite:
        logging.info("Saltando %s (ya existe). Usa --overwrite para forzar.", out_pdf_path)
        return False

    try:
        images_to_pdf(images, tmp_pdf)
    except Exception as e:
        logging.error("Error creando PDF en %s: %s", folder, e)
        if tmp_pdf.exists():
            tmp_pdf.unlink(missing_ok=True)
        return False

    try:
        # Aplicar OCR a tmp_pdf y escribir en out_pdf_path (temporal luego renombrar)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tf:
            temp_ocr_out = Path(tf.name)
        run_ocr_on_pdf(tmp_pdf, temp_ocr_out, lang=lang)
        # Mover resultado final
        if out_pdf_path.exists():
            out_pdf_path.unlink()
        temp_ocr_out.replace(out_pdf_path)
        logging.info("PDF final con OCR guardado: %s", out_pdf_path)
    except Exception as e:
        logging.error("Error aplicando OCR en %s: %s", folder, e)
        # si OCR falla, podemos conservar el PDF sin OCR (opcional). Aquí lo eliminamos.
        if out_pdf_path.exists():
            out_pdf_path.unlink(missing_ok=True)
        return False
    finally:
        tmp_pdf.unlink(missing_ok=True)
    return True

def walk_and_process(root: Path, lang: str, overwrite: bool, include_root: bool):
    processed = 0
    for dirpath, dirnames, filenames in os.walk(root):
        folder = Path(dirpath)
        # si no queremos procesar la carpeta raíz como carpeta de documentos, saltarla
        if not include_root and folder == root:
            continue
        try:
            ok = process_folder(folder, lang, overwrite)
            if ok:
                processed += 1
        except Exception as e:
            logging.error("Error procesando carpeta %s: %s", folder, e)
    logging.info("Proceso finalizado. Carpetas procesadas: %d", processed)

def parse_args():
    p = argparse.ArgumentParser(description="Convertir imágenes en subcarpetas a PDF con OCR")
    p.add_argument("root", nargs="?", default=".", help="Carpeta raíz donde buscar subcarpetas (por defecto: .)")
    p.add_argument("--lang", "-l", default="spa", help="Idiomas para Tesseract (por defecto: spa). Usa códigos de Tesseract, p.ej. 'spa+eng'.")
    p.add_argument("--overwrite", action="store_true", help="Sobrescribir PDFs existentes")
    p.add_argument("--include-root", action="store_true", help="Procesar también la carpeta raíz como si fuera una subcarpeta")
    return p.parse_args()

def main():
    args = parse_args()
    root = Path(args.root).resolve()
    if not root.exists() or not root.is_dir():
        logging.error("La ruta raíz no existe o no es carpeta: %s", root)
        sys.exit(1)
    logging.info("Iniciando en: %s", root)
    walk_and_process(root, lang=args.lang, overwrite=args.overwrite, include_root=args.include_root)

if __name__ == "__main__":
    main()
