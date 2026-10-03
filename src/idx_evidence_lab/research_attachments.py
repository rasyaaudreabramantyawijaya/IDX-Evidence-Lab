"""Ephemeral user-owned attachments. Never execute files or treat them as instructions."""
import base64
import hashlib
from io import BytesIO
from pathlib import PurePosixPath

MAX_FILE_BYTES = 5 * 1024 * 1024
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.m4v', '.avi', '.mkv', '.webm', '.mpg', '.mpeg', '.wmv', '.flv', '.3gp', '.ts', '.mts', '.m2ts', '.vob', '.ogv'}


def read_attachment(value):
    if not isinstance(value, dict) or not all(isinstance(value.get(k), str) for k in ('name', 'mime', 'data')):
        raise ValueError('INVALID_ATTACHMENT')
    name = PurePosixPath(value['name'].replace('\\', '/')).name[:160]
    suffix = PurePosixPath(name).suffix.lower()
    if not name or suffix in VIDEO_EXTENSIONS or value['mime'].lower().startswith('video/'):
        raise ValueError('VIDEO_NOT_ALLOWED')
    if len(value['data']) > (MAX_FILE_BYTES + 2) // 3 * 4:
        raise ValueError('ATTACHMENT_TOO_LARGE')
    try:
        raw = base64.b64decode(value['data'], validate=True)
    except ValueError:
        raise ValueError('INVALID_ATTACHMENT') from None
    if not raw or len(raw) > MAX_FILE_BYTES:
        raise ValueError('ATTACHMENT_TOO_LARGE')
    # Refuse common video/container signatures even when the extension is disguised.
    still_image_brands = {b'heic', b'heix', b'hevc', b'hevx', b'mif1', b'msf1', b'avif', b'avis'}
    if ((raw[4:8] == b'ftyp' and raw[8:12] not in still_image_brands) or raw[:4] == b'\x1aE\xdf\xa3' or
        raw[:4] == b'OggS' or raw[:4] in {b'\x00\x00\x01\xba', b'\x00\x00\x01\xb3'} or
        (raw[:4] == b'RIFF' and raw[8:12] == b'AVI ')):
        raise ValueError('VIDEO_NOT_ALLOWED')
    text, notice = '', 'Format belum dapat dibaca; tidak digunakan sebagai bukti analisis.'
    if raw.startswith(b'%PDF-'):
        try:
            import fitz
            with fitz.open(stream=raw, filetype='pdf') as doc:
                if doc.is_encrypted:
                    raise ValueError('Encrypted document')
                parts = []
                for page in list(range(min(len(doc), 30))):
                    parts.append(doc[page].get_text()[:10000])
                    if sum(map(len, parts)) >= 24000:
                        break
                text = '\n'.join(parts)[:24000]
                notice = 'Ekstraksi teks lokal; maksimum 30 halaman / 24.000 karakter. Tabel dan tata letak perlu diperiksa.'
        except Exception:
            notice = 'PDF terenkripsi, rusak atau tanpa teks terbaca; belum menjadi bukti analisis.'
    elif suffix in {'.txt', '.csv', '.tsv', '.json', '.md', '.log', '.yaml', '.yml'}:
        try:
            text = raw.decode('utf-8-sig')[:24000]
            if '\x00' in text:
                text = ''
            notice = 'Teks UTF-8 lokal; maksimum 24.000 karakter. Klaim pengguna belum diverifikasi.'
        except UnicodeDecodeError:
            notice = 'Encoding teks belum didukung; gunakan UTF-8.'
    elif value['mime'].startswith('image/') or suffix in {'.png', '.jpg', '.jpeg', '.webp', '.heic', '.gif', '.bmp', '.tiff'}:
        notice = 'Foto dilampirkan lokal. OCR/analisis visual belum tersedia; isi foto tidak dianggap sudah dibaca.'
    return {'id': 'U:' + hashlib.sha256(raw).hexdigest(), 'name': name,
            'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
            'text': text.strip(), 'status': 'READABLE' if text.strip() else 'UNREADABLE', 'notice': notice}
