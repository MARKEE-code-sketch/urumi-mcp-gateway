import re
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from backend.chat.llm_client import ChatFailure, encoded


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError()
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError()
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class DayWindow:
    start: datetime
    end: datetime
    enabled: bool

    @classmethod
    def capture(cls, message, now):
        if now.tzinfo is None:
            raise ValueError('Clock must be timezone aware.')
        local = now.astimezone(ZoneInfo('Asia/Kolkata'))
        return cls(local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc),
                   now.astimezone(timezone.utc), bool(re.search(r'\btoday\b', message, re.I)))

    def applies(self, tool, shop_slug):
        return self.enabled and tool['server_slug'] == shop_slug and tool['upstream_name'] == 'list_orders'

    def check_arguments(self, arguments):
        try:
            if (timestamp(arguments.get('created_from')) != self.start or
                    timestamp(arguments.get('created_to')) != self.end or arguments.get('page') != 1 or
                    'status' in arguments):
                raise ValueError()
        except (ValueError, TypeError, OverflowError):
            raise ChatFailure('TODAY_ARGUMENTS_INVALID', 'Today requires the fixed shop-day bounds, page 1 and no status filter.') from None

    def append_page(self, result, arguments, items, seen):
        try:
            data = result.get('structuredContent')
            if not isinstance(data, dict):
                raise ValueError()
            if (type(data['page']) is not int or data['page'] != arguments.get('page', 1) or
                    type(data['per_page']) is not int or data['per_page'] != arguments.get('per_page', 20) or
                    type(data['has_more']) is not bool or not isinstance(data['items'], list)):
                raise ValueError()
            if data['has_more'] and not data['items']:
                raise ValueError()
            for order in data['items']:
                if (not isinstance(order, dict) or type(order.get('id')) is not int or order['id'] in seen or
                        not self.start <= timestamp(order.get('date_created')) <= self.end):
                    raise ValueError()
                seen.add(order['id'])
                items.append(order)
            aggregate = {'items': items, 'complete': not data['has_more'], 'source': 'chat_page_aggregation'}
            if len(encoded(aggregate)) > 32 * 1024:
                raise ChatFailure('CHAT_LIMIT', 'Order results exceed the chat limit; the answer is partial.', 'limit_reached')
            return aggregate
        except (ValueError, TypeError, KeyError, OverflowError):
            raise ChatFailure('ORDER_PAGE_INVALID', 'The shop returned invalid/repeated order pages; results are partial.') from None
