from datetime import datetime
from uuid import UUID


def safe_row(row, fields):
    return {field: (row[field].isoformat().replace('+00:00', 'Z')
                    if isinstance(row[field], datetime) else str(row[field])
                    if isinstance(row[field], UUID) else row[field]) for field in fields}


def page_result(rows, page, per_page):
    return {'items': rows[:per_page], 'page': page, 'per_page': per_page,
            'has_more': len(rows) > per_page}
