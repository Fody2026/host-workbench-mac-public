# -*- coding: utf-8 -*-
"""常见文档读取：doc/docx/pdf/rtf/odt/txt/md/html/pptx/ppt/xlsx/xls/csv/epub/wps
   .doc / .wps / .xls / .ppt 通过本机 Word / Excel / PowerPoint（或 WPS）转换后再读。
"""
import os
import re
import csv
import json
import zipfile
import tempfile
import subprocess
import logging

logger = logging.getLogger(__name__)

DOC_EXTS = (".docx", ".doc", ".docm", ".dotx", ".pdf", ".rtf", ".odt", ".txt", ".md",
            ".html", ".htm", ".pptx", ".ppt", ".xlsx", ".xlsm", ".xls", ".csv", ".tsv",
            ".epub", ".wps")
FILE_FILTER = ("文档 (*.docx *.doc *.docm *.dotx *.pdf *.rtf *.odt *.txt *.md *.html *.htm "
               "*.pptx *.ppt *.xlsx *.xls *.xlsm *.csv *.tsv *.epub *.wps)")

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _ps(script, timeout=120):
    """用 PowerShell 调 Office COM；不依赖 pywin32"""
    import base64
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
           "-EncodedCommand", enc]
    return subprocess.run(cmd, capture_output=True, timeout=timeout,
                          creationflags=CREATE_NO_WINDOW)


def _quote(path):
    return str(path).replace("'", "''")


def _office_convert(src, out, kind):
    """kind: word / excel / ppt；返回 out 是否存在"""
    src, out = os.path.abspath(src), os.path.abspath(out)
    s, o = _quote(src), _quote(out)
    if kind == "word":
        script = f"""
$ErrorActionPreference='Stop'
$w=$null
try {{ $w=New-Object -ComObject Word.Application }} catch {{ }}
if ($w -eq $null) {{ try {{ $w=New-Object -ComObject KWps.Application }} catch {{ }} }}
if ($w -eq $null) {{ throw 'no-word' }}
$w.Visible=$false
$w.DisplayAlerts=0
$doc=$w.Documents.Open('{s}',$false,$true)
$o='{o}'
$doc.SaveAs([ref]$o,[ref]16)
$doc.Close($false)
$w.Quit()
"""
    elif kind == "excel":
        script = f"""
$ErrorActionPreference='Stop'
$e=New-Object -ComObject Excel.Application
$e.Visible=$false
$e.DisplayAlerts=$false
$wb=$e.Workbooks.Open('{s}')
$wb.SaveAs('{o}',51)
$wb.Close($false)
$e.Quit()
"""
    else:
        script = f"""
$ErrorActionPreference='Stop'
$p=New-Object -ComObject PowerPoint.Application
$pres=$p.Presentations.Open('{s}',$true,$false,$false)
$pres.SaveAs('{o}',24)
$pres.Close()
$p.Quit()
"""
    try:
        r = _ps(script)
        if not os.path.exists(out) or os.path.getsize(out) < 10:
            err = (r.stderr or b"")
            try:
                err = err.decode("utf-8", "ignore")
            except Exception:
                err = str(err)
            logger.warning("Office 转换失败 %s: %s", src, err[:300])
            return False
        return True
    except Exception as e:
        logger.warning("Office 转换异常 %s: %s", src, e)
        return False


def _convert_temp(src, kind):
    ext = ".docx" if kind == "word" else (".xlsx" if kind == "excel" else ".pptx")
    tmp = tempfile.mkdtemp(prefix="hostdoc_")
    out = os.path.join(tmp, "converted" + ext)
    if not _office_convert(src, out, kind):
        return None
    return out


def _read_docx(path):
    from docx import Document
    doc = Document(path)
    paras = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
    rows = []
    for tb in getattr(doc, "tables", []):
        for row in tb.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                rows.append(cells)
    return paras, rows


def _read_pptx(path):
    from pptx import Presentation
    prs = Presentation(path)
    paras, rows = [], []
    for slide in prs.slides:
        for shape in slide.shapes:
            try:
                if getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip():
                    paras.append(shape.text_frame.text.strip())
                if getattr(shape, "has_table", False):
                    for row in shape.table.rows:
                        cells = [c.text.strip() for c in row.cells]
                        if any(cells):
                            rows.append(cells)
            except Exception:
                continue
    return paras, rows


def _read_xlsx(path):
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = []
    for row in ws.iter_rows(values_only=True):
        cells = ["" if v is None else str(v).strip() for v in row]
        if any(cells):
            rows.append(cells)
    wb.close()
    return rows


def _read_csv(path):
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            with open(path, encoding=enc, newline="") as f:
                return [row for row in csv.reader(f) if any(c.strip() for c in row)]
        except UnicodeDecodeError:
            continue
    with open(path, encoding="utf-8", errors="ignore", newline="") as f:
        return [row for row in csv.reader(f) if any(c.strip() for c in row)]


class _HTMLText:
    def __init__(self):
        self.parts = []
        self.skip = 0

    def feed(self, html):
        from html.parser import HTMLParser

        outer = self

        class P(HTMLParser):
            def handle_starttag(self, tag, attrs):
                if tag in ("script", "style"):
                    outer.skip += 1
                if tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4"):
                    outer.parts.append("\n")

            def handle_endtag(self, tag):
                if tag in ("script", "style") and outer.skip:
                    outer.skip -= 1
                if tag in ("p", "div", "li", "tr", "h1", "h2", "h3", "h4"):
                    outer.parts.append("\n")

            def handle_data(self, data):
                if not outer.skip:
                    outer.parts.append(data)

        P().feed(html or "")
        return "".join(self.parts)


def _read_odt(path, name="content.xml"):
    with zipfile.ZipFile(path) as z:
        if name not in z.namelist():
            return ""
        xml = z.read(name)
    text = xml.decode("utf-8", errors="ignore")
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(text)
        lines = []
        for p in root.iter():
            if p.tag.endswith("}p") or p.tag == "p":
                s = "".join(p.itertext()).strip()
                if s:
                    lines.append(s)
        if lines:
            return "\n".join(lines)
    except Exception:
        pass
    return re.sub(r"<[^>]+>", "\n", text)


def _read_epub(path):
    chunks = []
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.lower().endswith((".xhtml", ".html", ".htm"))]
        for n in sorted(names):
            try:
                chunks.append(_HTMLText().feed(z.read(n).decode("utf-8", errors="ignore")))
            except Exception:
                continue
    return "\n".join(chunks)


def _read_pdf(path):
    from pypdf import PdfReader
    reader = PdfReader(path)
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(pages)


def _read_rtf(path):
    from striprtf.striprtf import rtf_to_text
    with open(path, encoding="utf-8", errors="ignore") as f:
        return rtf_to_text(f.read(), errors="ignore")


def _decode_text(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-16", "gbk", "utf-8"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="ignore")


def read_document(path):
    """通用读取：返回 (paragraphs, table_rows)"""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".docx", ".docm", ".dotx"):
        return _read_docx(path)
    if ext == ".doc":
        tmp = _convert_temp(path, "word")
        if not tmp:
            raise RuntimeError("读取 .doc 需要本机安装 Word / WPS；也可以另存为 .docx 再导入。")
        try:
            return _read_docx(tmp)
        finally:
            try:
                os.remove(tmp)
                os.rmdir(os.path.dirname(tmp))
            except Exception:
                pass
    if ext == ".wps":
        tmp = _convert_temp(path, "word")
        if not tmp:
            raise RuntimeError("读取 .wps 需要本机安装 WPS / Word；也可以另存为 .docx 再导入。")
        try:
            return _read_docx(tmp)
        finally:
            try:
                os.remove(tmp)
                os.rmdir(os.path.dirname(tmp))
            except Exception:
                pass
    if ext == ".pdf":
        text = _read_pdf(path)
        return _lines(text), []
    if ext == ".rtf":
        return _lines(_read_rtf(path)), []
    if ext == ".odt":
        return _lines(_read_odt(path)), []
    if ext in (".html", ".htm"):
        return _lines(_HTMLText().feed(_decode_text(path))), []
    if ext == ".epub":
        return _lines(_read_epub(path)), []
    if ext == ".pptx":
        return _read_pptx(path)
    if ext == ".ppt":
        tmp = _convert_temp(path, "ppt")
        if not tmp:
            raise RuntimeError("读取 .ppt 需要本机安装 PowerPoint / WPS；也可以另存为 .pptx 再导入。")
        try:
            return _read_pptx(tmp)
        finally:
            try:
                os.remove(tmp)
                os.rmdir(os.path.dirname(tmp))
            except Exception:
                pass
    if ext in (".xlsx", ".xlsm"):
        return [], _read_xlsx(path)
    if ext == ".xls":
        tmp = _convert_temp(path, "excel")
        if not tmp:
            raise RuntimeError("读取 .xls 需要本机安装 Excel / WPS；也可以另存为 .xlsx 再导入。")
        try:
            return [], _read_xlsx(tmp)
        finally:
            try:
                os.remove(tmp)
                os.rmdir(os.path.dirname(tmp))
            except Exception:
                pass
    if ext in (".csv", ".tsv"):
        return [], _read_csv(path)
    # txt / md / json / xml 等纯文本
    text = _decode_text(path)
    return _lines(text), []


def _lines(text):
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def read_text(path):
    """给主持助理用：整篇文字"""
    paras, rows = read_document(path)
    chunks = list(paras)
    for row in rows:
        line = " | ".join(x for x in row if x)
        if line.strip():
            chunks.append(line)
    return "\n".join(chunks).strip()
