"""Bounded excerpts for the observed documentation-search presentation format."""
from backend.chat.llm_client import encoded

SEARCH_BUDGET = 4 * 1024


def excerpt_search(data, tool):
    if (not tool or tool.get('upstream_name') != 'microsoft_docs_search'
            or data.get('isError') or data.get('text') or len(encoded(data)) <= SEARCH_BUDGET):
        return data
    structured = data.get('structuredContent')
    if not isinstance(structured, dict) or set(structured) != {'results'}:
        return data
    items = structured['results']
    fields = {'title', 'content', 'contentUrl'}
    if (not isinstance(items, list) or not items
            or any(not isinstance(item, dict) or set(item) != fields
                   or any(not isinstance(item[key], str) for key in fields) for item in items)):
        return data

    def prefix(text, limit):
        return text.encode('utf-8')[:limit].decode('utf-8', errors='ignore')

    excerpt = {'text': [], 'isError': False, 'structuredContent': {'results': []},
               'chat_excerpt': {'returned_results': len(items), 'retained_results': 0}}
    retained = excerpt['structuredContent']['results']
    for item in items[:10]:
        # Keep the complete source URL. Never produce a broken shortened link.
        retained.append({'title': prefix(item['title'], 256),
                         'content': prefix(item['content'], 384), 'contentUrl': item['contentUrl']})
        excerpt['chat_excerpt']['retained_results'] = len(retained)
        if len(encoded(excerpt)) > SEARCH_BUDGET:
            retained.pop()
            excerpt['chat_excerpt']['retained_results'] = len(retained)
            break
    return excerpt if retained else data
