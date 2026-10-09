"""Bounded SQL pagination; absent page retains the original list contract."""
import re
from buyer_service import BuyerError

PAGE_SIZE = 25


def requested_page(query, key='page'):
    if key not in query:
        return None
    values = query[key]
    if len(values) != 1 or not re.fullmatch(r'[1-9][0-9]{0,6}', values[0]):
        raise BuyerError(400, 'Invalid pagination.')
    page = int(values[0])
    if page > 1_000_000:
        raise BuyerError(400, 'Invalid pagination.')
    return page


def query_list(db, sql, args=(), *, order, page=None, legacy_limit=None,
               legacy_offset=0, order_args=()):
    # SQL and order are developer-owned strings; all user values are parameters.
    if page is not None:
        if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= 1_000_000:
            raise BuyerError(400, 'Invalid pagination.')
        if not db.in_transaction:
            db.execute('BEGIN')
        total = db.execute('SELECT count(*) FROM ('+sql+') page_count', args).fetchone()[0]
        rows = [dict(row) for row in db.execute(sql+' ORDER BY '+order+' LIMIT ? OFFSET ?',
                (*args, *order_args, PAGE_SIZE, (page-1)*PAGE_SIZE))]
        return {'items': rows, 'page': page, 'pageSize': PAGE_SIZE, 'total': total,
                'pages': (total+PAGE_SIZE-1)//PAGE_SIZE,
                'hasMore': page*PAGE_SIZE < total}
    suffix = ' ORDER BY '+order
    values = (*args, *order_args)
    if legacy_limit is not None:
        suffix += ' LIMIT ? OFFSET ?'
        values += (legacy_limit, legacy_offset)
    return [dict(row) for row in db.execute(sql+suffix, values)]


def list_items(result):
    return result['items'] if isinstance(result, dict) else result
