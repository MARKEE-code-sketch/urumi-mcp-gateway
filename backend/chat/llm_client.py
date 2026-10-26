import asyncio
import json
import re

import httpx


class ChatFailure(Exception):
    def __init__(self, code, message, state='failed', retry_after=None):
        self.code, self.message, self.state = code, message, state
        self.retry_after = retry_after
        super().__init__(code)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')


def retry_delay(headers):
    value = headers.get('retry-after')
    try:
        if value is not None:
            if len(value) > 64:
                return None
            seconds = float(value)
        else:
            value = headers.get('x-ratelimit-reset-tokens', '')
            match = re.fullmatch(r'(?:(\d+)m)?(\d+(?:\.\d+)?)s', value) if len(value) <= 64 else None
            if not match:
                return None
            seconds = int(match[1] or 0) * 60 + float(match[2])
        return seconds if 0 <= seconds <= 60 else None
    except ValueError:
        return None


class GroqClient:
    model = 'openai/gpt-oss-20b'

    def __init__(self, key, client=None):
        self.key = key
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(15, connect=3, pool=3), follow_redirects=False, trust_env=False)
        self.owns_client = client is None

    def redact(self, value):
        return value.replace(self.key, '[REDACTED]') if self.key else value

    async def close(self):
        if self.owns_client:
            await self.client.aclose()

    async def complete(self, messages, tools, final=False):
        payload = {'model': self.model, 'messages': messages, 'stream': False,
                   'max_completion_tokens': 1024, 'tool_choice': 'none' if final else 'auto'}
        if tools and not final:
            payload['tools'] = tools
        raw = self.redact(encoded(payload).decode()).encode()
        if len(raw) > 256 * 1024:
            raise ChatFailure('CHAT_LIMIT', 'The chat context limit was reached; results are partial.', 'limit_reached')
        try:
            async with asyncio.timeout(20):
                async with self.client.stream('POST', 'https://api.groq.com/openai/v1/chat/completions',
                        headers={'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json',
                                 'Accept-Encoding': 'identity'}, content=raw) as response:
                    if response.status_code != 200:
                        code = {401: 'PROVIDER_AUTH_FAILED', 403: 'PROVIDER_AUTH_FAILED',
                                429: 'PROVIDER_RATE_LIMIT'}.get(response.status_code, 'PROVIDER_UNAVAILABLE')
                        message = ('The language model rate limit was reached; earlier tool results remain visible.'
                                   if response.status_code == 429 else
                                   'The language model is unavailable; earlier tool results remain visible.')
                        raise ChatFailure(code, message,
                                          retry_after=retry_delay(response.headers) if response.status_code == 429 else None)
                    if response.headers.get('content-encoding', 'identity').lower() != 'identity':
                        raise ChatFailure('PROVIDER_INVALID_REPLY', 'The model returned unsupported content.')
                    data = bytearray()
                    async for chunk in response.aiter_raw():
                        data.extend(chunk)
                        if len(data) > 128 * 1024:
                            raise ChatFailure('CHAT_LIMIT', 'The model response limit was reached.', 'limit_reached')
            if self.key and self.key.encode() in data:
                raise ChatFailure('PROVIDER_INVALID_REPLY', 'The model returned unsafe content.')
            parsed = json.loads(data)
            choice = parsed['choices'][0]
            if choice['finish_reason'] == 'length':
                raise ChatFailure('CHAT_LIMIT', 'The model token limit was reached; results are partial.', 'limit_reached')
            if choice['finish_reason'] not in ('stop', 'tool_calls'):
                raise ValueError()
            message = choice['message']
            if not isinstance(message, dict) or message.get('role') != 'assistant':
                raise ValueError()
            return message
        except (TimeoutError, httpx.TimeoutException):
            raise ChatFailure('PROVIDER_TIMEOUT', 'The model deadline expired; earlier tool results remain visible.') from None
        except httpx.HTTPError:
            raise ChatFailure('PROVIDER_UNAVAILABLE', 'The language model is unavailable.') from None
        except (ValueError, KeyError, IndexError, TypeError, UnicodeError):
            raise ChatFailure('PROVIDER_INVALID_REPLY', 'The model returned an invalid reply.') from None
