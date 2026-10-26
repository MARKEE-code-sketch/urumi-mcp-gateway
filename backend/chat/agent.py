import asyncio
import copy
import json
from datetime import datetime, timezone
from uuid import uuid4

import anyio
import jsonschema

from backend.errors import PlatformError, unavailable
from backend.gateway.context import get_context, invocation_context, request_context
from backend.chat.day_window import DayWindow
from backend.chat.llm_client import ChatFailure, encoded
from backend.chat.prompts import instructions
from backend.chat.search_results import excerpt_search

UNCERTAIN = {'AUDIT_FINALIZATION_FAILED', 'UPSTREAM_TIMEOUT', 'TIMEOUT', 'INTERRUPTED',
             'UPSTREAM_UNAVAILABLE', 'UPSTREAM_PROTOCOL_ERROR', 'CONNECTION_FAILED'}
READS = {'woocommerce': {'list_products', 'list_orders', 'get_order'}, 'inventory': {'lookup_sku'}}
KEYWORDS = {'$schema', '$id', '$ref', '$defs', 'definitions', 'type', 'properties', 'required',
            'additionalProperties', 'items', 'enum', 'const', 'minimum', 'maximum', 'exclusiveMinimum',
            'exclusiveMaximum', 'multipleOf', 'minLength', 'maxLength', 'pattern', 'format', 'minItems',
            'maxItems', 'uniqueItems', 'anyOf', 'oneOf', 'allOf', 'title', 'description', 'default',
            'examples', 'nullable'}
SAFE_PATTERNS = {r'\S', r'^(0|[1-9][0-9]*)(\.[0-9]{1,2})?$'}


def bounded_json(value, depth=0, remaining=None):
    remaining = [512] if remaining is None else remaining
    remaining[0] -= 1
    if remaining[0] < 0 or depth > 20:
        raise ValueError()
    if isinstance(value, dict):
        for item in value.values():
            bounded_json(item, depth + 1, remaining)
    elif isinstance(value, list):
        for item in value:
            bounded_json(item, depth + 1, remaining)


def compatible_schema(schema):
    if not isinstance(schema, dict) or schema.get('type') != 'object':
        return False
    remaining = [256]
    def visit(node, depth=0, refs=()):
        remaining[0] -= 1
        if depth > 10 or remaining[0] < 0:
            raise ValueError()
        if isinstance(node, bool):
            return
        if not isinstance(node, dict) or set(node) - KEYWORDS:
            raise ValueError()
        if 'pattern' in node and node['pattern'] not in SAFE_PATTERNS:
            raise ValueError()
        if '$ref' in node:
            ref = node['$ref']
            if not isinstance(ref, str) or not ref.startswith('#/') or ref in refs:
                raise ValueError()
            target = schema
            for token in ref[2:].split('/'):
                target = target[token.replace('~1', '/').replace('~0', '~')]
            visit(target, depth + 1, refs + (ref,))
        for key in ('properties', '$defs', 'definitions'):
            for value in node.get(key, {}).values():
                visit(value, depth + 1, refs)
        for key in ('items', 'additionalProperties'):
            if key in node:
                visit(node[key], depth + 1, refs)
        for key in ('anyOf', 'oneOf', 'allOf'):
            for value in node.get(key, []):
                visit(value, depth + 1, refs)
    try:
        if len(encoded(schema)) > 16 * 1024:
            return False
        bounded_json(schema)
        visit(schema)
        jsonschema.validators.validator_for(schema).check_schema(schema)
        return True
    except (ValueError, KeyError, TypeError, AttributeError, jsonschema.SchemaError, RecursionError):
        return False


def result_object(result):
    return result.model_dump(mode='json', exclude_none=True) if hasattr(result, 'model_dump') else result


def result_text(result, tool=None):
    result = result_object(result)
    if not isinstance(result, dict) or not isinstance(result.get('content', []), list):
        raise ChatFailure('TOOL_CONTENT_UNSUPPORTED', 'The gateway result cannot be displayed completely in chat.')
    content = []
    for block in result.get('content', []):
        if not isinstance(block, dict) or block.get('type') != 'text' or not isinstance(block.get('text'), str):
            raise ChatFailure('TOOL_CONTENT_UNSUPPORTED', 'The gateway returned content chat cannot display completely.')
        content.append(block['text'])
    data = {'text': content, 'isError': result.get('isError', False)}
    if 'structuredContent' in result:
        data['structuredContent'] = result['structuredContent']
        if len(content) == 1:
            try:
                parsed = json.loads(content[0])
                # Some MCP servers send the same JSON in both representations.
                # Canonical serialization preserves JSON type distinctions (true != 1).
                if json.dumps(parsed, sort_keys=True, allow_nan=False) == json.dumps(
                        data['structuredContent'], sort_keys=True, allow_nan=False):
                    data['text'] = []
            except (ValueError, TypeError, RecursionError):
                pass
    try:
        data = excerpt_search(data, tool)
        raw = encoded(data)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ChatFailure('TOOL_CONTENT_UNSUPPORTED', 'The gateway returned content chat cannot represent completely.') from None
    if len(raw) > 32 * 1024:
        raise ChatFailure('CHAT_LIMIT', 'The gateway result exceeds the chat limit; results are partial.', 'limit_reached')
    return raw.decode()


class ChatAgent:
    def __init__(self, provider, gateway, identity, clock=None, deadline=120, shop_slug='woocommerce'):
        self.provider, self.gateway, self.identity = provider, gateway, identity
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.deadline, self.shop_slug, self.active = deadline, shop_slug, 0
        self.blocking_tasks = set()

    async def blocking(self, function, *args):
        # Cancellation cannot kill a Python thread. Keep its capacity occupied
        # until it actually exits, instead of spawning replacements indefinitely.
        if len(self.blocking_tasks) >= 2:
            raise unavailable()
        task = asyncio.create_task(anyio.to_thread.run_sync(function, *args))
        self.blocking_tasks.add(task)
        def finished(done):
            self.blocking_tasks.discard(done)
            if not done.cancelled():
                done.exception()
        task.add_done_callback(finished)
        return await asyncio.shield(task)

    async def _identity(self, principal):
        return await self.blocking(self.identity.revalidate, principal)

    async def run(self, principal, message):
        if self.active >= 2 or not getattr(self.provider, 'key', True):
            raise unavailable()
        self.active += 1
        calls, notes = [], []
        context = get_context()
        try:
            if context is None:
                with request_context(max_completions=12):
                    return await self._bounded(principal, message, calls, notes)
            return await self._bounded(principal, message, calls, notes)
        finally:
            self.active -= 1

    async def _bounded(self, principal, message, calls, notes):
        started = False
        request_id = str(get_context().request_id)
        try:
            async with asyncio.timeout(self.deadline) as deadline:
                principal = await self._identity(principal)
                catalog = await self.gateway.list_tools(principal)
                if len(catalog) > 64:
                    raise ChatFailure('CHAT_LIMIT', 'The tool catalog exceeds chat limits; no tools were executed.', 'limit_reached')
                tools, mapping = [], {}
                for tool in catalog:
                    if not compatible_schema(tool['inputSchema']):
                        notes.append('Some discovered tools have schemas chat cannot use.')
                        continue
                    mapping[tool['name']] = tool
                    tools.append({'type': 'function', 'function': {'name': tool['name'],
                        'description': tool.get('description', ''), 'parameters': tool['inputSchema']}})
                if len(tools) > 64 or len(encoded(tools)) > 64 * 1024:
                    raise ChatFailure('CHAT_LIMIT', 'The tool catalog exceeds chat limits; no tools were executed.', 'limit_reached')
                window = DayWindow.capture(message, self.clock())
                messages = [{'role': 'system', 'content': instructions(window)}, {'role': 'user', 'content': message}]
                ids, writes, retained = set(), set(), 0
                for round_number in range(1, 9):
                    principal = await self._identity(principal)
                    started = True
                    try:
                        response = await self.provider.complete(messages, tools, final=round_number == 8)
                    except ChatFailure as error:
                        delay = error.retry_after
                        if (error.code != 'PROVIDER_RATE_LIMIT' or not calls
                                or type(delay) not in (int, float) or not 0 <= delay <= 60
                                or asyncio.get_running_loop().time() + delay >= deadline.when()):
                            raise
                        notes.append('The model hit a rate limit; completed tool calls were not repeated.')
                        await asyncio.sleep(delay)
                        principal = await self._identity(principal)
                        response = await self.provider.complete(messages, tools, final=round_number == 8)
                    requested = response.get('tool_calls') or []
                    if not requested:
                        answer = response.get('content')
                        if not isinstance(answer, str) or not answer.strip():
                            raise ChatFailure('PROVIDER_INVALID_REPLY', 'The model returned no usable answer.')
                        if len(answer.encode('utf-8')) > 16 * 1024:
                            raise ChatFailure('CHAT_LIMIT', 'The model answer exceeds chat limits; results are partial.', 'limit_reached')
                        return self._reply(request_id, 'completed', answer, calls, notes)
                    if round_number == 8 or not isinstance(requested, list) or len(requested) != 1:
                        raise ChatFailure('PROVIDER_INVALID_REPLY', 'The model requested an unsupported tool batch.')
                    call = requested[0]
                    try:
                        call_id, function = call['id'], call['function']
                        name, raw_arguments = function['name'], function['arguments']
                        if (call.get('type') != 'function' or not isinstance(call_id, str) or
                                not call_id.strip() or len(call_id) > 128 or call_id in ids or name not in mapping or
                                not isinstance(raw_arguments, str) or len(raw_arguments.encode()) > 8192):
                            raise ValueError()
                        arguments = json.loads(raw_arguments, parse_constant=lambda value: (_ for _ in ()).throw(ValueError()))
                        if not isinstance(arguments, dict):
                            raise ValueError()
                        bounded_json(arguments)
                        tool = mapping[name]
                        validator = jsonschema.validators.validator_for(tool['inputSchema'])(
                            tool['inputSchema'], format_checker=jsonschema.FormatChecker())
                        await self.blocking(validator.validate, arguments)
                    except (ValueError, KeyError, TypeError, UnicodeError, jsonschema.ValidationError, RecursionError):
                        raise ChatFailure('MODEL_TOOL_INVALID', 'The model requested an invalid or repeated tool call.') from None
                    ids.add(call_id)
                    # Sorting makes differently ordered JSON objects the same write.
                    fingerprint = (name, json.dumps(arguments, sort_keys=True, separators=(',', ':'), allow_nan=False))
                    read = tool['upstream_name'] in READS.get(tool['server_slug'], set())
                    if not read:
                        if fingerprint in writes:
                            raise ChatFailure('WRITE_REPLAY_REJECTED', 'A repeated write was stopped; inspect the earlier result before retrying.')
                        writes.add(fingerprint)
                    today = window.applies(tool, self.shop_slug)
                    if today:
                        window.check_arguments(arguments)
                    items, seen = [], set()
                    current_arguments = copy.deepcopy(arguments)
                    while True:
                        if len(calls) >= 12:
                            raise ChatFailure('CHAT_LIMIT', 'The tool-call limit was reached; results are partial.', 'limit_reached')
                        result, outcome = await self._invoke(principal, tool, current_arguments, calls)
                        if today and outcome != 'success':
                            raise ChatFailure('ORDER_PAGE_FAILED', 'An order page failed; results are partial. Earlier pages are not the complete day.')
                        try:
                            text = result_text(result, tool)
                        except ChatFailure as error:
                            if outcome == 'success' and not read:
                                raise ChatFailure(error.code, 'The gateway reported success, but chat could not display the complete result. Do not repeat the action without checking its effects.', error.state) from None
                            raise
                        excerpt = json.loads(text).get('chat_excerpt')
                        if excerpt:
                            notes.append('Chat used shortened excerpts from '
                                         f"{excerpt['retained_results']} of {excerpt['returned_results']} "
                                         'returned search results; open the links for full text.')
                        if today and outcome == 'success':
                            aggregate = window.append_page(result_object(result), current_arguments, items, seen)
                            text = encoded(aggregate).decode()
                            if not aggregate['complete']:
                                current_arguments['page'] = current_arguments.get('page', 1) + 1
                                continue
                        break
                    retained += len(text.encode())
                    if retained > 96 * 1024:
                        raise ChatFailure('CHAT_LIMIT', 'The accumulated tool results exceed chat limits; results are partial.', 'limit_reached')
                    messages.append({'role': 'assistant', 'content': response.get('content'), 'tool_calls': requested})
                    messages.append({'role': 'tool', 'tool_call_id': call_id, 'content': text})
        except TimeoutError:
            return self._reply(request_id, 'limit_reached', 'The chat deadline expired; results are partial. A dispatched action may have occurred.', calls, notes)
        except ChatFailure as error:
            return self._reply(request_id, error.state, error.message, calls, notes)
        except PlatformError as error:
            if not started:
                raise
            return self._reply(request_id, 'failed', 'A required identity or gateway check failed; no further tools were dispatched.', calls, notes)
        except asyncio.CancelledError:
            raise
        except Exception:
            if not started:
                raise unavailable() from None
            return self._reply(request_id, 'failed', 'Chat processing failed safely; inspect the visible tool outcomes.', calls, notes)

    async def _invoke(self, principal, tool, arguments, calls):
        invocation_id = str(uuid4())
        reply, failure = None, None
        outcome = 'unknown'
        try:
            with invocation_context(invocation_id):
                reply = await self.gateway.invoke_tool(principal, tool['name'], arguments)
            outcome = reply['outcome']
            return_result = reply['result']
        except PlatformError as error:
            failure = error
            outcome = 'denied' if error.code == 'AUDIT_UNAVAILABLE' or error.status in (401, 403) else 'unknown'
        finally:
            context = get_context()
            metadata = next((item for item in context.completions if item['invocation_id'] == invocation_id), {})
            context.completions[:] = [item for item in context.completions if item['invocation_id'] != invocation_id]
            code = metadata.get('error_code') or (failure.code if failure else None)
            call = {'call_id': invocation_id, 'tool_name': tool['name'],
                    'server_id': metadata.get('server_id', str(tool['server_id'])), 'outcome': outcome,
                    'duration_ms': metadata.get('duration_ms'),
                    'audit_id': metadata.get('audit_id', str(reply['audit_id']) if reply and reply.get('audit_id') else None)}
            if code:
                call['error_code'] = code
            calls.append(call)
        if failure:
            if failure.code == 'AUDIT_UNAVAILABLE':
                raise ChatFailure(failure.code, 'Not dispatched: activity storage is unavailable. No saved audit record exists.')
            raise ChatFailure(failure.code, 'The gateway could not confirm completion; remote effects may be uncertain.')
        if outcome in ('timeout', 'unknown') or code in UNCERTAIN:
            raise ChatFailure(code or 'OUTCOME_UNKNOWN', 'The tool outcome is uncertain; no further actions were attempted. Inspect the remote state before retrying.')
        return return_result, outcome

    def _reply(self, request_id, state, answer, calls, notes):
        if any(call['outcome'] != 'success' for call in calls):
            notes = notes + ['Some tool attempts did not succeed or have uncertain outcomes; inspect their activity before retrying.']
        note = '\n'.join(dict.fromkeys(notes))
        if note:
            answer = answer + '\n' + note
            if len(answer.encode()) > 16 * 1024:
                answer = 'Inspect the tool activity for observed outcomes.\n' + note
        redact = getattr(self.provider, 'redact', lambda value: value)
        return {'request_id': request_id, 'state': state, 'answer': redact(answer), 'tool_calls': calls}
