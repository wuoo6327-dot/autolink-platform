"""Private operating-premises and inventory evidence for supplier applications."""
import io
import warnings
from datetime import date
from PIL import Image, ImageOps, UnidentifiedImageError
from buyer_service import BuyerError, text

PHOTO_KINDS = {'PREMISES_PHOTO', 'INVENTORY_PHOTO'}


def evidence_fields(body):
    count = body.get('inventoryCount')
    if count is not None and (isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 1_000_000):
        raise BuyerError(400, 'Invalid inventory quantity.')
    basis = body.get('inventoryBasis', '')
    if basis not in ('', 'OWNED', 'AUTHORIZED', 'MIXED'):
        raise BuyerError(400, 'Invalid inventory basis.')
    as_of = text(body.get('inventoryAsOf'), 'inventory date', 10)
    if as_of:
        try:
            parsed = date.fromisoformat(as_of)
            if parsed > date.today() or parsed.isoformat() != as_of:
                raise ValueError()
        except ValueError as exc:
            raise BuyerError(400, 'Invalid inventory date.') from exc
    return {'premises_address': text(body.get('premisesAddress'), 'operating premises address', 320),
            'inventory_count': count, 'inventory_basis': basis, 'inventory_as_of': as_of}


def require_evidence(db, supplier_id, fields):
    if not fields['premises_address'] or fields['inventory_count'] is None or not fields['inventory_basis'] or not fields['inventory_as_of']:
        raise BuyerError(409, 'Complete operating premises and inventory information before submitting.')
    kinds = {r[0] for r in db.execute('SELECT kind FROM supplier_documents WHERE supplier_id=?', (supplier_id,))}
    if not PHOTO_KINDS.issubset(kinds):
        raise BuyerError(409, 'Upload operating premises and inventory photos before submitting.')


def sanitize_photo(raw, mime):
    if mime not in ('image/png', 'image/jpeg'):
        raise BuyerError(400, 'Operating premises and inventory evidence must be PNG or JPEG photos.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in ('PNG', 'JPEG') or (mime == 'image/png') != (image.format == 'PNG') or min(image.size) < 200:
                    raise BuyerError(400, 'A matching PNG/JPEG of at least 200 × 200 pixels is required.')
                image.verify()
            with Image.open(io.BytesIO(raw)) as original:
                image = ImageOps.exif_transpose(original).convert('RGB')
                image.thumbnail((2400, 2400))
                out = io.BytesIO()
                image.save(out, 'JPEG', quality=88, optimize=True)
                return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise BuyerError(400, 'Image cannot be decoded safely.') from exc
